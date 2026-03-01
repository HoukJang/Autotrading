"""EntryManager: orchestrates Group A (MOO) and Group B (confirmation) entries.

Entry architecture:
  - Group A (breakout_momentum, rsi_mean_reversion):
      Market-on-Open orders submitted at 9:30 AM ET.
      SL/TP anchored to actual fill price.
  - Group B (currently empty):
      Confirmation window 9:45-10:00 AM ET.
      Long confirm: current price >= prev_close * (1 - GAP_TOLERANCE)
      Unconfirmed candidates are DISCARDED at 10:00 AM.

Daily constraints enforced here:
  - Max 3 new entries per day.
  - Max 8 concurrent long positions.
  - Max 3 concurrent short positions.
  - Max 9 total positions.
  - Per-strategy caps: BM=2, MR=4.
  - Re-entry block checked via ExitRuleEngine.is_reentry_blocked().
  - Regime-based entry blocking (breakout blocked, MR short blocked).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from zoneinfo import ZoneInfo

from autotrader.core.types import AccountInfo, Position, Signal
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.regime_detector import MarketRegime
from autotrader.risk.gdr_manager import GDRManager
from autotrader.risk.manager import RiskManager

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger("autotrader.execution.entry_manager")

# Entry group membership
_GROUP_A_STRATEGIES: frozenset[str] = frozenset({"breakout_momentum", "rsi_mean_reversion"})
_GROUP_B_STRATEGIES: frozenset[str] = frozenset()

# Confirmation window gap tolerance (3 bps)
_GAP_TOLERANCE: float = 0.003

# Daily limits
_MAX_DAILY_ENTRIES: int = 3
_MAX_LONG_POSITIONS: int = 8             # Iter 29: increased from 6
_MAX_SHORT_POSITIONS: int = 3
_MAX_TOTAL_POSITIONS: int = 9            # Overall position cap

# Per-strategy position caps (prevents single strategy from dominating)
_MAX_STRATEGY_POSITIONS: dict[str, int] = {
    "breakout_momentum": 2,              # BM: max 2 concurrent (LOCKED)
    "rsi_mean_reversion": 4,             # MR: max 4 concurrent
}
_DEFAULT_STRATEGY_CAP: int = 2           # Fallback for unknown strategies


@dataclass
class Candidate:
    """A signal from the nightly batch scan pending execution.

    Attributes:
        signal: The original Signal object from strategy scanning.
        prev_close: Previous day closing price used for confirmation checks.
        atr: ATR at scan time (used to anchor SL if fill price differs
            from signal price).
        indicators: Full indicator dict at scan time for TP checks.
    """

    signal: Signal
    prev_close: float
    atr: float
    indicators: dict


class EntryManager:
    """Manages the two-group entry workflow for the batch+intraday system.

    Lifecycle:
    1. At market open (after nightly scan), load candidates via
       ``load_candidates()``.
    2. At 9:30 AM ET: call ``execute_moo()`` for Group A.
    3. Between 9:45 and 10:00 AM ET: call ``execute_confirmation()``
       repeatedly (or once at 9:45 and once at 10:00).
    4. At 10:00 AM ET: call ``close_entry_window()`` to discard remaining
       Group B candidates.

    The manager is responsible for calling OrderManager and then creating
    HeldPosition objects which it hands off to PositionMonitor.

    Args:
        order_manager: Configured OrderManager instance.
        allocation_engine: AllocationEngine for position sizing.
        risk_manager: RiskManager for max-position and daily-loss checks.
        exit_rule_engine: ExitRuleEngine used for re-entry block checks.
    """

    def __init__(
        self,
        order_manager: OrderManager,
        allocation_engine: AllocationEngine,
        risk_manager: RiskManager,
        exit_rule_engine: ExitRuleEngine,
        gdr_manager: GDRManager | None = None,
    ) -> None:
        self._order_manager = order_manager
        self._allocation_engine = allocation_engine
        self._risk_manager = risk_manager
        self._exit_rule_engine = exit_rule_engine
        self._gdr_manager = gdr_manager

        # Pending candidates by group
        self._group_a: list[Candidate] = []
        self._group_b: list[Candidate] = []

        # Per-day counters (reset via on_new_trading_day)
        self._daily_entry_count: int = 0
        self._last_entry_date: date | None = None

        # HeldPosition objects created this session (handed to PositionMonitor)
        self._new_positions: list[HeldPosition] = []

    # ------------------------------------------------------------------
    # Setup and lifecycle
    # ------------------------------------------------------------------

    def load_candidates(self, candidates: list[Candidate]) -> None:
        """Load the nightly scan candidates for today's session.

        Groups candidates by strategy membership.  Must be called before
        ``execute_moo()`` or ``execute_confirmation()``.

        Args:
            candidates: List of Candidate objects from NightlyScanner /
                GapFilter pipeline.
        """
        self._group_a = [c for c in candidates if c.signal.strategy in _GROUP_A_STRATEGIES]
        self._group_b = [c for c in candidates if c.signal.strategy in _GROUP_B_STRATEGIES]
        self._new_positions.clear()
        logger.info(
            "Candidates loaded: %d Group-A (MOO), %d Group-B (confirmation)",
            len(self._group_a), len(self._group_b),
        )

    def on_new_trading_day(self, today_et: date) -> None:
        """Reset daily entry counter at market open.

        Args:
            today_et: Today's date in US/Eastern timezone.
        """
        if self._last_entry_date != today_et:
            self._daily_entry_count = 0
            self._last_entry_date = today_et
            self._group_a.clear()
            self._group_b.clear()
            self._new_positions.clear()
            logger.info("EntryManager reset for new trading day %s", today_et)

    # ------------------------------------------------------------------
    # Group A: Market-on-Open
    # ------------------------------------------------------------------

    async def execute_moo(
        self,
        account: AccountInfo,
        positions: list[Position],
        regime: MarketRegime,
        current_date_et: date,
    ) -> list[HeldPosition]:
        """Submit Group A (MOO) market orders at market open (9:30 AM ET).

        Orders are submitted immediately as market orders.  After each fill,
        a stop-loss order is placed on the broker side as a safety net.

        Args:
            account: Current account snapshot.
            positions: Current open positions list.
            regime: Current market regime for allocation sizing.
            current_date_et: Today's US Eastern date.

        Returns:
            List of HeldPosition objects for successfully opened positions.
        """
        entered: list[HeldPosition] = []

        for candidate in list(self._group_a):
            if not self._can_enter(candidate.signal, account, positions, regime, current_date_et):
                continue

            result = await self._submit_entry(candidate, account, positions, regime)
            if result is None:
                continue

            held = self._create_held_position(
                signal=candidate.signal,
                fill_price=result.fill_price,
                fill_qty=result.filled_qty,
                atr=candidate.atr,
                entry_date_et=current_date_et,
            )
            entered.append(held)
            self._new_positions.append(held)
            self._daily_entry_count += 1

            # Record entry in GDR manager
            if self._gdr_manager is not None:
                self._gdr_manager.record_entry(candidate.signal.strategy)

            # Submit broker-side stop-loss order for safety
            await self._submit_broker_sl(candidate.signal, result.fill_price, result.filled_qty, result.order_id)

            logger.info(
                "Group-A entry: %s %s %.0f @ %.2f (strategy=%s, day=%s)",
                candidate.signal.direction, candidate.signal.symbol,
                result.filled_qty, result.fill_price,
                candidate.signal.strategy, current_date_et,
            )

        self._group_a.clear()
        return entered

    # ------------------------------------------------------------------
    # Group B: Confirmation window (9:45-10:00 AM ET)
    # ------------------------------------------------------------------

    async def execute_confirmation(
        self,
        account: AccountInfo,
        positions: list[Position],
        regime: MarketRegime,
        current_date_et: date,
        current_prices: dict[str, float],
    ) -> list[HeldPosition]:
        """Submit confirmed Group B candidates during the confirmation window.

        A long candidate is confirmed if current_price >= prev_close * (1 - GAP_TOL).
        A short candidate is confirmed if current_price <= prev_close * (1 + GAP_TOL).
        Unconfirmed candidates remain pending for the next call.

        This method is designed to be called repeatedly between 9:45 and
        10:00 AM ET.  Call ``close_entry_window()`` at 10:00 to discard
        remaining unconfirmed candidates.

        Args:
            account: Current account snapshot.
            positions: Current open positions list.
            regime: Current market regime.
            current_date_et: Today's US Eastern date.
            current_prices: Mapping of symbol -> current intraday price.

        Returns:
            List of HeldPosition objects for successfully opened positions.
        """
        entered: list[HeldPosition] = []
        remaining: list[Candidate] = []

        for candidate in self._group_b:
            symbol = candidate.signal.symbol
            current_price = current_prices.get(symbol)

            if current_price is None:
                remaining.append(candidate)
                continue

            if not self._is_confirmed(candidate, current_price):
                remaining.append(candidate)
                continue

            if not self._can_enter(candidate.signal, account, positions, regime, current_date_et):
                # Skip but don't keep pending; entry constraints are hard stops
                continue

            result = await self._submit_entry(candidate, account, positions, regime)
            if result is None:
                continue

            held = self._create_held_position(
                signal=candidate.signal,
                fill_price=result.fill_price,
                fill_qty=result.filled_qty,
                atr=candidate.atr,
                entry_date_et=current_date_et,
            )
            entered.append(held)
            self._new_positions.append(held)
            self._daily_entry_count += 1

            # Record entry in GDR manager
            if self._gdr_manager is not None:
                self._gdr_manager.record_entry(candidate.signal.strategy)

            await self._submit_broker_sl(candidate.signal, result.fill_price, result.filled_qty, result.order_id)

            logger.info(
                "Group-B entry (confirmed): %s %s %.0f @ %.2f (strategy=%s)",
                candidate.signal.direction, candidate.signal.symbol,
                result.filled_qty, result.fill_price, candidate.signal.strategy,
            )

        self._group_b = remaining
        return entered

    def close_entry_window(self) -> int:
        """Discard all remaining unconfirmed Group B candidates at 10:00 AM ET.

        Returns:
            Number of candidates that were discarded.
        """
        discarded = len(self._group_b)
        if discarded:
            symbols = [c.signal.symbol for c in self._group_b]
            logger.info(
                "Entry window closed: discarding %d unconfirmed Group-B candidates: %s",
                discarded, symbols,
            )
        self._group_b.clear()
        return discarded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_confirmed(self, candidate: Candidate, current_price: float) -> bool:
        """Check if a candidate passes the intraday confirmation rule."""
        direction = candidate.signal.direction
        prev_close = candidate.prev_close
        if direction == "long":
            # Long confirm: price has NOT gapped down too much from prev close
            threshold = prev_close * (1.0 - _GAP_TOLERANCE)
            return current_price >= threshold
        else:  # short
            # Short confirm: price has NOT gapped up too much from prev close
            threshold = prev_close * (1.0 + _GAP_TOLERANCE)
            return current_price <= threshold

    def _can_enter(
        self,
        signal: Signal,
        account: AccountInfo,
        positions: list[Position],
        regime: MarketRegime,
        current_date_et: date,
    ) -> bool:
        """Check all pre-entry constraints.

        Returns False (and logs the reason) if any constraint is violated.
        Checks are ordered: re-entry -> daily limit -> total cap ->
        direction caps -> duplicate -> per-strategy cap -> regime block ->
        risk manager -> allocation engine.
        """
        symbol = signal.symbol
        direction = signal.direction
        strategy_name = signal.strategy

        # GDR entry limit check (per-strategy drawdown response)
        if self._gdr_manager is not None:
            if not self._gdr_manager.can_enter_strategy(strategy_name):
                logger.info("GDR blocked entry for %s (%s)", symbol, strategy_name)
                return False

        # Re-entry block
        if self._exit_rule_engine.is_reentry_blocked(symbol):
            logger.debug("Skipping %s: re-entry blocked today", symbol)
            return False

        # Daily entry limit
        if self._daily_entry_count >= _MAX_DAILY_ENTRIES:
            logger.info("Daily entry limit reached (%d)", _MAX_DAILY_ENTRIES)
            return False

        # Total position cap (before direction caps)
        total_count = len(positions)
        if total_count >= _MAX_TOTAL_POSITIONS:
            logger.info(
                "Total position cap reached (%d/%d)",
                total_count, _MAX_TOTAL_POSITIONS,
            )
            return False

        # Direction position caps
        long_count = sum(1 for p in positions if p.side == "long")
        short_count = sum(1 for p in positions if p.side == "short")
        if direction == "long" and long_count >= _MAX_LONG_POSITIONS:
            logger.info("Max long positions reached (%d)", _MAX_LONG_POSITIONS)
            return False
        if direction == "short" and short_count >= _MAX_SHORT_POSITIONS:
            logger.info("Max short positions reached (%d)", _MAX_SHORT_POSITIONS)
            return False

        # Duplicate position check
        if any(p.symbol == symbol for p in positions):
            logger.debug("Skipping %s: position already open", symbol)
            return False

        # Per-strategy position cap
        strategy_count = sum(
            1 for p in positions
            if getattr(p, "_strategy", None) == strategy_name
        )
        cap = _MAX_STRATEGY_POSITIONS.get(strategy_name, _DEFAULT_STRATEGY_CAP)
        if strategy_count >= cap:
            logger.info(
                "Strategy %s cap reached (%d/%d)",
                strategy_name, strategy_count, cap,
            )
            return False

        # Regime-based entry blocking
        from autotrader.portfolio.regime_detector import RegimeDetector
        alloc = RegimeDetector.get_allocation(regime)
        if strategy_name == "breakout_momentum" and alloc.get("breakout_blocked"):
            logger.info("Regime %s: breakout entry blocked", regime.value)
            return False
        if (strategy_name == "rsi_mean_reversion"
                and direction == "short"
                and alloc.get("mr_short_blocked")):
            logger.info("Regime %s: MR short entry blocked", regime.value)
            return False

        # RiskManager validation (max positions, daily loss, drawdown)
        if not self._risk_manager.validate(signal, account, positions):
            logger.info("Risk rejected entry: %s %s", direction, symbol)
            return False

        # AllocationEngine: strategy weight check
        if not self._allocation_engine.should_enter(signal.strategy, regime, strategy_count):
            logger.debug(
                "AllocationEngine blocked entry: strategy=%s, regime=%s",
                signal.strategy, regime.value,
            )
            return False

        return True

    async def _submit_entry(
        self,
        candidate: Candidate,
        account: AccountInfo,
        positions: list[Position],
        regime: MarketRegime,
    ) -> _EntryResult | None:
        """Size and submit an entry order.  Returns fill details or None."""
        signal = candidate.signal
        # Use ATR-based stop distance for accurate risk sizing.
        # Calculate the actual SL distance using the strategy-specific multiplier.
        direction = signal.direction
        atr = candidate.atr
        mult = self._get_sl_mult(signal.strategy, direction)
        actual_stop_distance = mult * atr if atr > 0 else None

        # Fetch latest price for sizing (use prev_close as proxy if needed)
        price = candidate.prev_close  # Will be replaced by fill price

        # GDR risk adjustment
        gdr_mult = 1.0
        safety_net = False
        if self._gdr_manager is not None:
            gdr_mult = self._gdr_manager.get_risk_multiplier(signal.strategy)
            safety_net = self._gdr_manager.is_safety_net_active

        qty = self._allocation_engine.get_position_size(
            strategy_name=signal.strategy,
            price=price,
            equity=account.equity,
            regime=regime,
            atr=atr,                         # Raw ATR for weight-only fallback
            direction=direction,
            stop_distance=actual_stop_distance,  # Strategy-specific SL distance
            gdr_risk_mult=gdr_mult,
            safety_net_active=safety_net,
        )
        if qty <= 0:
            logger.debug(
                "Zero qty for %s %s (equity=%.0f, price=%.2f)",
                direction, signal.symbol, account.equity, price,
            )
            return None

        # Cash check
        required = price * qty
        if account.cash < required:
            logger.info(
                "Insufficient cash for %s: need %.2f, have %.2f",
                signal.symbol, required, account.cash,
            )
            return None

        side: Literal["buy", "sell"] = "buy" if direction == "long" else "sell"
        result = await self._order_manager.submit_entry(
            symbol=signal.symbol,
            side=side,
            qty=float(qty),
            order_type="market",
        )
        if result is None or result.status not in ("filled", "partially_filled"):
            return None

        return _EntryResult(
            order_id=result.order_id,
            fill_price=result.filled_price,
            filled_qty=result.filled_qty,
        )

    async def _submit_broker_sl(
        self,
        signal: Signal,
        fill_price: float,
        qty: float,
        order_id: str,
    ) -> None:
        """Place a broker-side stop order using the actual fill price."""
        direction = signal.direction
        mult = self._get_sl_mult(signal.strategy, direction)
        atr = signal.metadata.get("entry_atr", 0.0) if signal.metadata else 0.0

        if atr <= 0:
            logger.warning(
                "Cannot place broker SL for %s: no ATR in metadata", signal.symbol,
            )
            return

        if direction == "long":
            stop_price = fill_price - mult * atr
            sl_side: Literal["buy", "sell"] = "sell"
        else:
            stop_price = fill_price + mult * atr
            sl_side = "buy"

        if stop_price <= 0:
            return

        await self._order_manager.submit_stop_loss(
            symbol=signal.symbol,
            side=sl_side,
            qty=qty,
            stop_price=round(stop_price, 2),
            parent_order_id=order_id,
        )

    def _create_held_position(
        self,
        signal: Signal,
        fill_price: float,
        fill_qty: float,
        atr: float,
        entry_date_et: date,
    ) -> HeldPosition:
        """Construct a HeldPosition from fill data."""
        return HeldPosition(
            symbol=signal.symbol,
            strategy=signal.strategy,
            direction=signal.direction,  # type: ignore[arg-type]
            entry_price=fill_price,
            entry_atr=atr,
            entry_date_et=entry_date_et,
            bars_held=0,
            qty=fill_qty,
            highest_price=fill_price,
            lowest_price=fill_price,
        )

    @staticmethod
    def _get_sl_mult(strategy: str, direction: str) -> float:
        """Return the SL ATR multiplier for a strategy/direction pair."""
        from autotrader.execution.exit_rules import _SL_ATR_MULT
        return _SL_ATR_MULT.get(strategy, {}).get(direction, 2.0)


# ---------------------------------------------------------------------------
# Internal helper dataclass (not exported)
# ---------------------------------------------------------------------------

@dataclass
class _EntryResult:
    """Fill details returned from a successful order submission."""

    order_id: str
    fill_price: float
    filled_qty: float
