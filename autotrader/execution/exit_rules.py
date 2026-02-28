"""ExitRuleEngine: per-bar exit evaluation for held positions.

Exit hierarchy (evaluated in order, first match wins):
  1. Day 1 emergency stops only (no SL/TP checks on entry day)
  2. Day 2+ SL/TP from actual fill price using strategy ATR multipliers
  3. Trailing stops (no strategies currently use this)
  4. Time-based exit when max_hold_days reached
  5. (Re-entry blocking is a side effect, not an exit check)

The engine is stateless per call; all position state is passed in via
HeldPosition objects managed by PositionMonitor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger("autotrader.execution.exit_rules")

# Emergency exit thresholds (Day 1 only, overrides everything)
_EMERGENCY_LOSS_CONFIRM_PCT: float = 0.07   # -7%: need 2 consecutive bars
_EMERGENCY_LOSS_IMMEDIATE_PCT: float = 0.10  # -10%: immediate single-bar exit
_EMERGENCY_BARS_NEEDED: int = 2             # bars at -7% before triggering

# Breakeven stop: once price moves this many ATRs in our favour, move SL to entry
_BREAKEVEN_ACTIVATION_ATR: float = 0.6

# Strategy-specific max hold days
_MAX_HOLD_DAYS: dict[str, int] = {
    "rsi_mean_reversion": 5,
    "consecutive_down": 5,
}

# Strategy-specific SL ATR multipliers (by direction)
_SL_ATR_MULT: dict[str, dict[str, float]] = {
    "rsi_mean_reversion": {"long": 1.0, "short": 1.5},
    "consecutive_down": {"long": 1.0},
}

# Strategy-specific TP ATR multipliers (None = use indicator-based TP)
_TP_ATR_MULT: dict[str, float | None] = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
}

# Strategies that use trailing stops
_TRAILING_STRATEGIES: frozenset[str] = frozenset()
_TRAILING_ATR_MULT: float = 2.0

# Per-strategy trailing stop activation thresholds (ATR multiples of favourable move)
_TRAILING_ACTIVATION_ATR: dict[str, float] = {}


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


class ExitRuleEngine:
    """Evaluates exit conditions for held positions on each new bar.

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
        # Set of symbols that may not be re-entered today.
        self._closed_today: set[str] = set()
        # Last date the block set was cleared (ET).
        self._last_clear_date: date | None = None

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
        position.update_price_extremes(bar_high, bar_low)

        is_entry_day = (position.entry_date_et == current_date_et)

        if is_entry_day:
            return self._evaluate_emergency(position, bar_close)

        # Day 2+ evaluation
        atr = self._get_atr(indicators, position.entry_atr)
        decision = self._evaluate_sl(position, bar_close, atr)
        if decision.action == "exit":
            return decision

        decision = self._evaluate_tp(position, bar_close, indicators, atr)
        if decision.action == "exit":
            return decision

        decision = self._evaluate_trailing(position, bar_close, atr)
        if decision.action == "exit":
            return decision

        decision = self._evaluate_time(position)
        if decision.action == "exit":
            return decision

        return _HOLD

    def record_close(self, symbol: str) -> None:
        """Block the symbol from re-entry for the rest of the current day.

        Must be called after every position close (profit, stop, or time exit)
        so that duplicate entries are prevented.

        Args:
            symbol: The ticker that was just closed.
        """
        self._closed_today.add(symbol)
        logger.debug("Re-entry blocked for %s (today)", symbol)

    def is_reentry_blocked(self, symbol: str) -> bool:
        """Return True if the symbol is blocked from re-entry today.

        Args:
            symbol: Ticker to check.
        """
        return symbol in self._closed_today

    def on_new_trading_day(self, today_et: date) -> None:
        """Clear the re-entry block set at the start of a new trading day.

        Should be called once at market open (or at the start of the batch
        scan run) each trading day.

        Args:
            today_et: Today's date in US/Eastern.  Used to guard against
                duplicate calls within the same session.
        """
        if self._last_clear_date != today_et:
            cleared_count = len(self._closed_today)
            self._closed_today.clear()
            self._last_clear_date = today_et
            if cleared_count:
                logger.info(
                    "Re-entry block cleared for new trading day %s (%d symbols released)",
                    today_et, cleared_count,
                )

    # ------------------------------------------------------------------
    # Private evaluation helpers
    # ------------------------------------------------------------------

    def _evaluate_emergency(
        self, position: HeldPosition, bar_close: float,
    ) -> ExitDecision:
        """Day-1 emergency stop checks only.

        Triggers on:
        - Immediate: -10% loss from entry in a single bar.
        - Confirmed: -7% loss over _EMERGENCY_BARS_NEEDED consecutive bars.
        """
        loss_pct = self._loss_pct(position, bar_close)

        if loss_pct >= _EMERGENCY_LOSS_IMMEDIATE_PCT:
            logger.warning(
                "Emergency exit (immediate -%.1f%%) for %s %s @ %.2f (entry=%.2f)",
                loss_pct * 100, position.direction, position.symbol,
                bar_close, position.entry_price,
            )
            return ExitDecision(
                action="exit",
                reason="emergency_immediate",
                target_price=bar_close,
                is_emergency=True,
            )

        if loss_pct >= _EMERGENCY_LOSS_CONFIRM_PCT:
            position.consecutive_loss_bars += 1
            if position.consecutive_loss_bars >= _EMERGENCY_BARS_NEEDED:
                logger.warning(
                    "Emergency exit (confirmed -7%% x%d) for %s %s @ %.2f",
                    position.consecutive_loss_bars, position.direction,
                    position.symbol, bar_close,
                )
                return ExitDecision(
                    action="exit",
                    reason="emergency_confirmed",
                    target_price=bar_close,
                    is_emergency=True,
                )
        else:
            # Reset counter if loss recovered below threshold
            position.consecutive_loss_bars = 0

        return _HOLD

    def _evaluate_sl(
        self, position: HeldPosition, bar_close: float, atr: float,
    ) -> ExitDecision:
        """Standard stop-loss check with breakeven upgrade.

        Once price has moved _BREAKEVEN_ACTIVATION_ATR in our favour,
        the stop loss is raised (long) or lowered (short) to the entry
        price, so the trade can no longer result in a loss.
        """
        mult = _SL_ATR_MULT.get(position.strategy, {}).get(position.direction, 2.0)
        sl_distance = mult * atr
        if position.direction == "long":
            sl_price = position.entry_price - sl_distance
            # Breakeven upgrade: if price reached entry + activation ATR, floor SL at entry
            if position.highest_price >= position.entry_price + _BREAKEVEN_ACTIVATION_ATR * atr:
                sl_price = max(sl_price, position.entry_price)
            if bar_close <= sl_price:
                logger.info(
                    "SL triggered for LONG %s: close=%.2f <= sl=%.2f",
                    position.symbol, bar_close, sl_price,
                )
                return ExitDecision(
                    action="exit", reason="stop_loss", target_price=sl_price,
                )
        else:  # short
            sl_price = position.entry_price + sl_distance
            # Breakeven upgrade for short
            if position.lowest_price <= position.entry_price - _BREAKEVEN_ACTIVATION_ATR * atr:
                sl_price = min(sl_price, position.entry_price)
            if bar_close >= sl_price:
                logger.info(
                    "SL triggered for SHORT %s: close=%.2f >= sl=%.2f",
                    position.symbol, bar_close, sl_price,
                )
                return ExitDecision(
                    action="exit", reason="stop_loss", target_price=sl_price,
                )
        return _HOLD

    def _evaluate_tp(
        self,
        position: HeldPosition,
        bar_close: float,
        indicators: dict,
        atr: float,
    ) -> ExitDecision:
        """Take-profit check using strategy-specific targets.

        Strategies with tp_atr_mult use a fixed ATR target from entry.
        Strategies without it (None) use indicator-based signals (RSI/BB).
        """
        tp_atr_mult = _TP_ATR_MULT.get(position.strategy)
        strategy = position.strategy

        if tp_atr_mult is not None:
            # Fixed ATR take-profit (ema_pullback)
            if position.direction == "long":
                tp_price = position.entry_price + tp_atr_mult * atr
                if bar_close >= tp_price:
                    logger.info(
                        "TP hit (ATR x%.1f) for LONG %s: close=%.2f >= tp=%.2f",
                        tp_atr_mult, position.symbol, bar_close, tp_price,
                    )
                    return ExitDecision(
                        action="exit", reason="take_profit", target_price=tp_price,
                    )
            else:
                tp_price = position.entry_price - tp_atr_mult * atr
                if bar_close <= tp_price:
                    return ExitDecision(
                        action="exit", reason="take_profit", target_price=tp_price,
                    )
            return _HOLD

        # Indicator-based TP
        rsi = indicators.get("RSI_14")
        bb = indicators.get("BBANDS_20")
        pct_b = bb.get("pct_b", 0.5) if isinstance(bb, dict) else None

        if strategy == "rsi_mean_reversion":
            if position.direction == "long":
                if (rsi is not None and rsi > 50.0) or (pct_b is not None and pct_b > 0.50):
                    reason = f"tp_rsi_{rsi:.1f}" if rsi is not None else "tp_bb"
                    return ExitDecision(
                        action="exit", reason=reason, target_price=bar_close,
                    )
            else:  # short
                if (rsi is not None and rsi < 50.0) or (pct_b is not None and pct_b < 0.50):
                    reason = f"tp_rsi_{rsi:.1f}" if rsi is not None else "tp_bb"
                    return ExitDecision(
                        action="exit", reason=reason, target_price=bar_close,
                    )

        elif strategy == "consecutive_down":
            # Long-only: exit when close > EMA(5) (bounce target)
            ema_5 = indicators.get("EMA_5")
            if ema_5 is not None and bar_close > ema_5:
                return ExitDecision(
                    action="exit", reason="tp_ema5", target_price=bar_close,
                )

        # Auxiliary ATR TP for rsi_mean_reversion: cap gains at 2.0 ATR
        # even if indicator-based TP hasn't triggered yet
        if strategy == "rsi_mean_reversion":
            atr_tp_mult = 2.0
            if position.direction == "long":
                atr_tp_price = position.entry_price + atr_tp_mult * atr
                if bar_close >= atr_tp_price:
                    return ExitDecision(
                        action="exit", reason="take_profit", target_price=atr_tp_price,
                    )
            else:
                atr_tp_price = position.entry_price - atr_tp_mult * atr
                if bar_close <= atr_tp_price:
                    return ExitDecision(
                        action="exit", reason="take_profit", target_price=atr_tp_price,
                    )

        return _HOLD

    def _evaluate_trailing(
        self, position: HeldPosition, bar_close: float, atr: float,
    ) -> ExitDecision:
        """Trailing stop for strategies that use them (currently none).

        Activation conditions:
        - Price must have moved at least activation ATR in our favour to start trailing.
        - Trail stop is floored at entry price (trailing can never cause a loss).
        """
        if position.strategy not in _TRAILING_STRATEGIES:
            return _HOLD

        # Per-strategy activation threshold (default 1.5 ATR)
        activation_atr = _TRAILING_ACTIVATION_ATR.get(position.strategy, 1.5)

        if position.direction == "long":
            if position.highest_price < position.entry_price + activation_atr * atr:
                return _HOLD
            trail_stop = max(
                position.entry_price,
                position.highest_price - _TRAILING_ATR_MULT * atr,
            )
            if bar_close <= trail_stop:
                logger.info(
                    "Trailing stop for LONG %s: close=%.2f <= trail=%.2f (high=%.2f)",
                    position.symbol, bar_close, trail_stop, position.highest_price,
                )
                return ExitDecision(
                    action="exit", reason="trailing_stop", target_price=trail_stop,
                )
        else:  # short
            if position.lowest_price > position.entry_price - activation_atr * atr:
                return _HOLD
            trail_stop = min(
                position.entry_price,
                position.lowest_price + _TRAILING_ATR_MULT * atr,
            )
            if bar_close >= trail_stop:
                logger.info(
                    "Trailing stop for SHORT %s: close=%.2f >= trail=%.2f (low=%.2f)",
                    position.symbol, bar_close, trail_stop, position.lowest_price,
                )
                return ExitDecision(
                    action="exit", reason="trailing_stop", target_price=trail_stop,
                )
        return _HOLD

    def _evaluate_time(self, position: HeldPosition) -> ExitDecision:
        """Time-based exit when maximum hold period is reached."""
        max_days = _MAX_HOLD_DAYS.get(position.strategy, 5)
        if position.bars_held >= max_days:
            logger.info(
                "Time exit for %s %s after %d bars (max=%d)",
                position.strategy, position.symbol, position.bars_held, max_days,
            )
            return ExitDecision(
                action="exit", reason="time_exit", target_price=0.0,
            )
        return _HOLD

    # ------------------------------------------------------------------
    # Utility
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
