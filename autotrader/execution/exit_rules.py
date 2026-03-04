"""ExitRuleEngine: per-bar exit evaluation for held positions.

Thin wrapper around the unified ``UnifiedExitEngine`` from
``autotrader.trading.exit_engine``.  All exit logic lives in the
unified engine; this module translates between the live-system's
``HeldPosition`` / ``ExitDecision`` types and the unified engine's
``ExitContext`` / ``ExitDecision`` types.

Exit hierarchy (evaluated by UnifiedExitEngine, first match wins):
  1. Day 1 emergency stops only (no SL/TP checks on entry day)
  2. Day 2+ SL/TP from actual fill price using strategy ATR multipliers
  3. Trailing stops (ema_cross_trend uses this)
  4. Time-based exit when max_hold_days reached
  5. (Re-entry blocking is a side effect, not an exit check)

Public interface is fully preserved for callers (PositionMonitor,
EntryManager, tests).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from autotrader.core.types import Bar
from autotrader.trading.exit_engine import UnifiedExitEngine
from autotrader.trading.types import ExitContext, PriceMode
from autotrader.trading.types import ExitDecision as _UnifiedExitDecision

logger = logging.getLogger("autotrader.execution.exit_rules")

# All exit-rule constants are defined in the trading.constants SSOT module.
# Re-exported here under their original underscore-prefixed names for
# backward compatibility (tests, batch_simulator, scripts import from here).
from autotrader.trading.constants import (
    EMERGENCY_LOSS_CONFIRM_PCT as _EMERGENCY_LOSS_CONFIRM_PCT,
    EMERGENCY_LOSS_IMMEDIATE_PCT as _EMERGENCY_LOSS_IMMEDIATE_PCT,
    EMERGENCY_BARS_NEEDED as _EMERGENCY_BARS_NEEDED,
    STAGE1_BE_ACTIVATION_ATR as _STAGE1_BE_ACTIVATION_ATR,
    STAGE2_PROFIT_ACTIVATION_ATR as _STAGE2_PROFIT_ACTIVATION_ATR,
    STAGE2_PROFIT_LOCK_ATR as _STAGE2_PROFIT_LOCK_ATR,
    MAX_HOLD_DAYS as _MAX_HOLD_DAYS,
    SL_ATR_MULT as _SL_ATR_MULT,
    TP_ATR_MULT as _TP_ATR_MULT,
    TRAILING_STRATEGIES as _TRAILING_STRATEGIES,
    TRAILING_ATR_MULT as _TRAILING_ATR_MULT,
    TRAILING_ACTIVATION_ATR as _TRAILING_ACTIVATION_ATR,
)


@dataclass
class HeldPosition:
    """Runtime state for a position being monitored by PositionMonitor.

    This is the primary data carrier between ExitRuleEngine and
    PositionMonitor.  All fields are mutable because they are updated
    bar-by-bar.

    Attributes:
        symbol: Ticker symbol.
        strategy: Strategy that opened the position.
        direction: "long" or "short".
        entry_price: Actual fill price (NOT signal price).
        entry_atr: ATR value at the time of entry (used to anchor SL/TP).
        entry_date_et: Calendar date of entry in US/Eastern timezone.
        bars_held: Number of daily bars elapsed since entry (incremented by
            PositionMonitor on each new daily bar).
        qty: Number of shares held.
        highest_price: Highest price observed since entry (for trailing stop).
        lowest_price: Lowest price observed since entry (for trailing stop).
        consecutive_loss_bars: Counter for emergency -7% confirmation logic.
    """

    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_price: float
    entry_atr: float
    entry_date_et: date
    bars_held: int = 0
    qty: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float("inf")
    consecutive_loss_bars: int = 0
    entry_adx: float = 0.0

    def __post_init__(self) -> None:
        # Initialise price extremes from entry price when not explicitly set.
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == float("inf"):
            self.lowest_price = self.entry_price

    def update_price_extremes(self, high: float, low: float) -> None:
        """Update MFE/MAE tracking with new bar high/low."""
        self.highest_price = max(self.highest_price, high)
        self.lowest_price = min(self.lowest_price, low)


@dataclass(frozen=True)
class ExitDecision:
    """Result of an exit-rule evaluation for a single bar.

    Attributes:
        action: "hold" if no exit triggered, "exit" if the position should
            be closed immediately.
        reason: Human-readable reason string for logging and trade records.
        target_price: Suggested exit price for limit orders; 0.0 means
            use a market order at current price.
        is_emergency: True for emergency Day-1 stops (use market order
            regardless of target_price).
    """

    action: Literal["hold", "exit"]
    reason: str = ""
    target_price: float = 0.0
    is_emergency: bool = False


_HOLD = ExitDecision(action="hold")

# Reason mapping: unified engine reason -> live engine reason.
# Reasons not in this map are passed through unchanged.
_REASON_MAP: dict[str, str] = {
    "sl_hit": "stop_loss",
    "tp_hit": "take_profit",
    # These pass through unchanged:
    # "trailing_stop", "time_exit", "emergency_immediate",
    # "emergency_confirmed", "tp_rsi_*", "tp_bb", "tp_ema5"
}


def _to_exit_context(position: HeldPosition) -> ExitContext:
    """Convert a HeldPosition to an ExitContext for the unified engine."""
    return ExitContext(
        symbol=position.symbol,
        strategy=position.strategy,
        direction=position.direction,
        entry_price=position.entry_price,
        entry_date=position.entry_date_et,
        qty=int(position.qty),
        entry_atr=position.entry_atr,
        bars_held=position.bars_held,
        trailing_high=position.highest_price,
        trailing_low=position.lowest_price,
        mfe_price=position.highest_price,
        mae_price=position.lowest_price,
        consecutive_loss_bars=position.consecutive_loss_bars,
    )


def _apply_context_to_position(
    position: HeldPosition, ctx: ExitContext,
) -> None:
    """Apply updated state from ExitContext back to the HeldPosition."""
    position.highest_price = ctx.trailing_high
    position.lowest_price = ctx.trailing_low
    position.consecutive_loss_bars = ctx.consecutive_loss_bars


def _translate_decision(
    unified: _UnifiedExitDecision,
    position: HeldPosition,
) -> ExitDecision:
    """Translate a unified ExitDecision to the live ExitDecision type.

    Also applies updated state from the unified context back to the
    HeldPosition (MFE/MAE, consecutive_loss_bars, etc.).
    """
    # Always apply context updates back to position
    _apply_context_to_position(position, unified.updated_context)

    if not unified.should_exit:
        return _HOLD

    # Map unified reason to live reason
    reason = unified.reason
    mapped_reason = _REASON_MAP.get(reason, reason)

    is_emergency = reason in ("emergency_immediate", "emergency_confirmed")

    return ExitDecision(
        action="exit",
        reason=mapped_reason,
        target_price=unified.exit_price,
        is_emergency=is_emergency,
    )


class ExitRuleEngine:
    """Evaluates exit conditions for held positions on each new bar.

    Delegates all exit logic to ``UnifiedExitEngine`` from the trading
    core, translating between live-system types (``HeldPosition``,
    ``ExitDecision``) and unified types (``ExitContext``,
    ``ExitDecision``).

    Usage pattern:
    1. Instantiate once and share across all monitored positions.
    2. On each new daily bar, call ``evaluate(position, bar_close, bar_high,
       bar_low, indicators, current_date_et)`` for every held position.
    3. If the returned ExitDecision.action == "exit", pass to OrderManager.
    4. After a position is closed, call ``record_close(symbol, date_et)`` to
       engage the re-entry block for the rest of the trading day.
    5. At the start of each new US Eastern trading day, call
       ``on_new_trading_day()`` to clear the re-entry block set.

    Re-entry blocking prevents same-symbol re-entry on the same calendar day
    in US Eastern time, across all strategies and directions.
    """

    def __init__(self) -> None:
        self._unified = UnifiedExitEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        position: HeldPosition,
        bar_close: float,
        bar_high: float,
        bar_low: float,
        indicators: dict,
        current_date_et: date,
    ) -> ExitDecision:
        """Evaluate exit rules for a single bar.

        Args:
            position: The HeldPosition state (mutated in place for trailing
                stop tracking; bars_held is incremented by PositionMonitor,
                NOT here).
            bar_close: Current bar close price.
            bar_high: Current bar high price.
            bar_low: Current bar low price.
            indicators: Computed indicator dict for the symbol (ATR, RSI, etc.).
            current_date_et: Today's date in US/Eastern timezone.

        Returns:
            ExitDecision with action, reason, and optional target_price.
        """
        # Build a synthetic Bar for the unified engine
        bar = Bar(
            symbol=position.symbol,
            open=bar_close,  # open not used in BAR_CLOSE mode
            high=bar_high,
            low=bar_low,
            close=bar_close,
            volume=0,
            timestamp=datetime.now(timezone.utc),
        )

        # Convert HeldPosition to ExitContext
        ctx = _to_exit_context(position)

        # Delegate to unified engine
        unified_decision = self._unified.evaluate(
            ctx=ctx,
            bar=bar,
            indicators=indicators,
            current_date=current_date_et,
            price_mode=PriceMode.BAR_CLOSE,
        )

        # Translate back to live types and apply state to position
        return _translate_decision(unified_decision, position)

    def record_close(self, symbol: str) -> None:
        """Block the symbol from re-entry for the rest of the current day.

        Must be called after every position close (profit, stop, or time exit)
        so that duplicate entries are prevented.

        Args:
            symbol: The ticker that was just closed.
        """
        self._unified.record_close(symbol)
        logger.debug("Re-entry blocked for %s (today)", symbol)

    def is_reentry_blocked(self, symbol: str) -> bool:
        """Return True if the symbol is blocked from re-entry today.

        Args:
            symbol: Ticker to check.
        """
        return self._unified.is_reentry_blocked(symbol)

    def on_new_trading_day(self, today_et: date) -> None:
        """Clear the re-entry block set at the start of a new trading day.

        Should be called once at market open (or at the start of the batch
        scan run) each trading day.

        Args:
            today_et: Today's date in US/Eastern.  Used to guard against
                duplicate calls within the same session.
        """
        old_count = len(self._unified._closed_today)
        self._unified.on_new_trading_day(today_et)
        if old_count and self._unified._last_clear_date == today_et:
            logger.info(
                "Re-entry block cleared for new trading day %s (%d symbols released)",
                today_et, old_count,
            )

    # ------------------------------------------------------------------
    # Utility (kept for backward compatibility -- tests use these)
    # ------------------------------------------------------------------

    @staticmethod
    def _loss_pct(position: HeldPosition, current_price: float) -> float:
        """Return the loss fraction from entry (positive = loss)."""
        if position.entry_price <= 0:
            return 0.0
        if position.direction == "long":
            return max(0.0, (position.entry_price - current_price) / position.entry_price)
        else:
            return max(0.0, (current_price - position.entry_price) / position.entry_price)

    @staticmethod
    def _get_atr(indicators: dict, fallback_atr: float) -> float:
        """Extract ATR from indicator dict with fallback to entry-time ATR."""
        atr = indicators.get("ATR_14")
        if isinstance(atr, (int, float)) and atr > 0:
            return float(atr)
        return fallback_atr if fallback_atr > 0 else 1.0
