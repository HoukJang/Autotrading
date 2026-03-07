"""UnifiedExitEngine: single implementation of all exit rules.

Replaces the duplicated exit logic between:
  - Live: ``autotrader.execution.exit_rules.ExitRuleEngine``
  - Backtest: ``autotrader.backtest.batch_simulator._check_sl_tp_intraday``

The engine evaluates exit conditions in a strict priority order and
returns an ``ExitDecision`` that includes both the exit verdict AND
the updated position state (trailing, stage upgrades, MFE/MAE, etc.)
so that the caller can persist those changes.

Price mode controls how SL/TP are checked:
  - ``PriceMode.BAR_CLOSE``: checks close only (live behavior)
  - ``PriceMode.INTRADAY``:  checks high/low (backtest behavior),
    with open-proximity disambiguation when both SL and TP are hit.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import replace
from datetime import date

from autotrader.core.types import Bar
from autotrader.trading.constants import (
    ADAPTIVE_MR_TP_ATR_LONG,
    ADAPTIVE_MR_TP_ATR_SHORT,
    EMERGENCY_LOSS_CONFIRM_PCT,
    EMERGENCY_LOSS_IMMEDIATE_PCT,
    EMERGENCY_BARS_NEEDED,
    MAX_HOLD_DAYS,
    MR_AUXILIARY_TP_ATR_MULT,
    SL_ATR_MULT,
    TP_ATR_MULT,
    STAGE1_BE_ACTIVATION_ATR,
    STAGE2_PROFIT_ACTIVATION_ATR,
    STAGE2_PROFIT_LOCK_ATR,
    TRAILING_STRATEGIES,
    TRAILING_ATR_MULT,
    TRAILING_ACTIVATION_ATR,
)
from autotrader.trading.types import ExitContext, ExitDecision, PriceMode

logger = logging.getLogger("autotrader.trading.exit_engine")


def _hold(ctx: ExitContext) -> ExitDecision:
    """Return a hold (no-exit) decision preserving the current context."""
    return ExitDecision(
        should_exit=False,
        reason="",
        exit_price=0.0,
        updated_context=ctx,
    )


class UnifiedExitEngine:
    """Evaluates all exit conditions for a held position on each bar.

    The engine is stateless with respect to position data -- all state
    is passed in via ``ExitContext`` and returned in ``ExitDecision``.

    Re-entry blocking (``closed_today`` set) is managed here as the
    only piece of cross-position state.

    Usage::

        engine = UnifiedExitEngine()

        # On each new trading day (US/Eastern)
        engine.on_new_trading_day(today_et)

        # For each held position + daily bar:
        decision = engine.evaluate(ctx, bar, indicators, today_et, mode)
        if decision.should_exit:
            execute_exit(decision.exit_price, decision.reason)
            engine.record_close(ctx.symbol)
        else:
            # Persist updated state
            position.update_from(decision.updated_context)
    """

    def __init__(self) -> None:
        self._closed_today: set[str] = set()
        self._last_clear_date: date | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        ctx: ExitContext,
        bar: Bar,
        indicators: dict,
        current_date: date,
        price_mode: PriceMode = PriceMode.BAR_CLOSE,
    ) -> ExitDecision:
        """Evaluate all exit rules for a position against a single bar.

        Args:
            ctx: Current position state.  A working copy is made
                internally -- the original is never mutated.
            bar: The daily bar to evaluate against.
            indicators: Computed indicator dict for the symbol.
            current_date: Today's date in US/Eastern.
            price_mode: ``BAR_CLOSE`` for live, ``INTRADAY`` for backtest.

        Returns:
            ExitDecision with ``should_exit``, ``reason``, ``exit_price``,
            and ``updated_context`` reflecting any state changes.
        """
        # Work on a copy so the caller's ctx is never mutated.
        wctx = copy.copy(ctx)

        # Update MFE / MAE tracking
        wctx.mfe_price = max(wctx.mfe_price, bar.high)
        wctx.mae_price = min(wctx.mae_price, bar.low)
        wctx.trailing_high = max(wctx.trailing_high, bar.high)
        wctx.trailing_low = min(wctx.trailing_low, bar.low)

        # --- Entry day: only emergency checks ---
        is_entry_day = wctx.entry_date == current_date
        if is_entry_day:
            return self._evaluate_emergency(wctx, bar.close)

        # --- Day 2+: full exit hierarchy ---
        atr = self._get_atr(indicators, wctx.entry_atr)

        if price_mode == PriceMode.BAR_CLOSE:
            return self._evaluate_bar_close(wctx, bar, indicators, atr)
        else:
            return self._evaluate_intraday(wctx, bar, indicators, atr)

    def record_close(self, symbol: str) -> None:
        """Block re-entry for this symbol for the rest of the trading day."""
        self._closed_today.add(symbol)

    def is_reentry_blocked(self, symbol: str) -> bool:
        """Return True if the symbol is blocked from re-entry today."""
        return symbol in self._closed_today

    def on_new_trading_day(self, today_et: date) -> None:
        """Clear the re-entry block set at the start of a new trading day."""
        if self._last_clear_date != today_et:
            self._closed_today.clear()
            self._last_clear_date = today_et

    @property
    def closed_today_count(self) -> int:
        """Return the number of symbols blocked from re-entry today."""
        return len(self._closed_today)

    # ------------------------------------------------------------------
    # Snapshot (persistence support)
    # ------------------------------------------------------------------

    def to_snapshot(self) -> dict:
        """Serialize ephemeral state for persistence."""
        return {
            "closed_today": list(self._closed_today),
            "last_clear_date": self._last_clear_date.isoformat() if self._last_clear_date else None,
        }

    def from_snapshot(self, data: dict) -> None:
        """Restore ephemeral state from persisted snapshot."""
        self._closed_today = set(data.get("closed_today", []))
        last_clear = data.get("last_clear_date")
        if last_clear:
            self._last_clear_date = date.fromisoformat(last_clear)
        else:
            self._last_clear_date = None

    # ------------------------------------------------------------------
    # BAR_CLOSE mode (live): check SL/TP against close only
    # ------------------------------------------------------------------

    def _evaluate_bar_close(
        self,
        wctx: ExitContext,
        bar: Bar,
        indicators: dict,
        atr: float,
    ) -> ExitDecision:
        """Day 2+ evaluation using close price only (live mode)."""

        # 1. Stop-loss
        sl_price = self._compute_sl_price(wctx, atr)
        wctx.current_sl = sl_price

        if wctx.direction == "long" and bar.close <= sl_price:
            return ExitDecision(
                should_exit=True, reason="sl_hit",
                exit_price=sl_price, updated_context=wctx,
            )
        if wctx.direction == "short" and bar.close >= sl_price:
            return ExitDecision(
                should_exit=True, reason="sl_hit",
                exit_price=sl_price, updated_context=wctx,
            )

        # 2. Take-profit
        tp_result = self._check_tp_close(wctx, bar.close, indicators, atr)
        if tp_result is not None:
            tp_price, tp_reason = tp_result
            wctx.current_tp = tp_price
            return ExitDecision(
                should_exit=True, reason=tp_reason,
                exit_price=tp_price, updated_context=wctx,
            )

        # 3. Trailing stop
        trailing_result = self._check_trailing_close(wctx, bar.close, atr)
        if trailing_result is not None:
            return ExitDecision(
                should_exit=True, reason="trailing_stop",
                exit_price=trailing_result, updated_context=wctx,
            )

        # 4. Time exit
        if self._check_time_exit(wctx):
            return ExitDecision(
                should_exit=True, reason="time_exit",
                exit_price=bar.close, updated_context=wctx,
            )

        return _hold(wctx)

    # ------------------------------------------------------------------
    # INTRADAY mode (backtest): check SL/TP against high/low
    # ------------------------------------------------------------------

    def _evaluate_intraday(
        self,
        wctx: ExitContext,
        bar: Bar,
        indicators: dict,
        atr: float,
    ) -> ExitDecision:
        """Day 2+ evaluation using high/low prices (backtest mode)."""

        # --- Stop-loss ---
        sl_price = self._compute_sl_price(wctx, atr)
        wctx.current_sl = sl_price

        if wctx.direction == "long":
            sl_hit = bar.low <= sl_price
        else:
            sl_hit = bar.high >= sl_price

        # --- Take-profit ---
        tp_hit = False
        tp_price: float | None = None
        tp_reason = "tp_hit"

        tp_atr_mult = TP_ATR_MULT.get(wctx.strategy)
        if tp_atr_mult is not None:
            # Fixed ATR-based TP
            if wctx.direction == "long":
                tp_price = wctx.entry_price + tp_atr_mult * atr
                tp_hit = bar.high >= tp_price
            else:
                tp_price = wctx.entry_price - tp_atr_mult * atr
                tp_hit = bar.low <= tp_price
        else:
            # Indicator-based TP
            tp_hit, tp_price, tp_reason = self._check_indicator_tp_intraday(
                wctx, bar, indicators, atr,
            )

        wctx.current_tp = tp_price

        # --- Trailing stop ---
        trailing_hit = False
        trailing_price: float | None = None

        if wctx.strategy in TRAILING_STRATEGIES and wctx.bars_held >= 2:
            activation_atr = TRAILING_ACTIVATION_ATR.get(wctx.strategy, 1.5)
            if wctx.direction == "long":
                if wctx.trailing_high >= wctx.entry_price + activation_atr * atr:
                    wctx.trailing_active = True
                    trail_stop = max(
                        wctx.entry_price,
                        wctx.trailing_high - TRAILING_ATR_MULT * atr,
                    )
                    if bar.low <= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop
            else:
                if wctx.trailing_low <= wctx.entry_price - activation_atr * atr:
                    wctx.trailing_active = True
                    trail_stop = min(
                        wctx.entry_price,
                        wctx.trailing_low + TRAILING_ATR_MULT * atr,
                    )
                    if bar.high >= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop

        # --- Time exit ---
        time_hit = self._check_time_exit(wctx)

        # --- Determine which exit fires (with disambiguation) ---

        # Both SL and TP hit: use open-proximity to disambiguate
        if sl_hit and tp_hit and tp_price is not None:
            open_to_sl = abs(bar.open - sl_price)
            open_to_tp = abs(bar.open - tp_price)

            if open_to_sl <= open_to_tp:
                return ExitDecision(
                    should_exit=True, reason="sl_hit",
                    exit_price=sl_price, updated_context=wctx,
                )
            else:
                return ExitDecision(
                    should_exit=True, reason=tp_reason,
                    exit_price=tp_price, updated_context=wctx,
                )

        if sl_hit:
            return ExitDecision(
                should_exit=True, reason="sl_hit",
                exit_price=sl_price, updated_context=wctx,
            )

        if tp_hit and tp_price is not None:
            return ExitDecision(
                should_exit=True, reason=tp_reason,
                exit_price=tp_price, updated_context=wctx,
            )

        if trailing_hit and trailing_price is not None:
            return ExitDecision(
                should_exit=True, reason="trailing_stop",
                exit_price=trailing_price, updated_context=wctx,
            )

        if time_hit:
            return ExitDecision(
                should_exit=True, reason="time_exit",
                exit_price=bar.close, updated_context=wctx,
            )

        return _hold(wctx)

    # ------------------------------------------------------------------
    # Stop-loss computation (shared between modes)
    # ------------------------------------------------------------------

    def _compute_sl_price(self, wctx: ExitContext, atr: float) -> float:
        """Compute the effective stop-loss price with 2-stage upgrade.

        Stage 2 is checked first since it provides the more favourable
        upgrade (locks profit rather than just breakeven).
        """
        mult = SL_ATR_MULT.get(wctx.strategy, {}).get(wctx.direction, 2.0)
        sl_distance = mult * atr

        if wctx.direction == "long":
            sl_price = wctx.entry_price - sl_distance

            # Stage 2: profit lock
            if wctx.trailing_high >= wctx.entry_price + STAGE2_PROFIT_ACTIVATION_ATR * atr:
                sl_price = max(sl_price, wctx.entry_price + STAGE2_PROFIT_LOCK_ATR * atr)
                wctx.stage2_done = True
                wctx.stage1_done = True
            # Stage 1: breakeven
            elif wctx.trailing_high >= wctx.entry_price + STAGE1_BE_ACTIVATION_ATR * atr:
                sl_price = max(sl_price, wctx.entry_price)
                wctx.stage1_done = True
        else:
            sl_price = wctx.entry_price + sl_distance

            # Stage 2: profit lock
            if wctx.trailing_low <= wctx.entry_price - STAGE2_PROFIT_ACTIVATION_ATR * atr:
                sl_price = min(sl_price, wctx.entry_price - STAGE2_PROFIT_LOCK_ATR * atr)
                wctx.stage2_done = True
                wctx.stage1_done = True
            # Stage 1: breakeven
            elif wctx.trailing_low <= wctx.entry_price - STAGE1_BE_ACTIVATION_ATR * atr:
                sl_price = min(sl_price, wctx.entry_price)
                wctx.stage1_done = True

        return sl_price

    # ------------------------------------------------------------------
    # Take-profit helpers
    # ------------------------------------------------------------------

    def _check_tp_close(
        self,
        wctx: ExitContext,
        close: float,
        indicators: dict,
        atr: float,
    ) -> tuple[float, str] | None:
        """Check take-profit using close price only (BAR_CLOSE mode).

        Returns (tp_price, reason) or None.
        """
        tp_atr_mult = TP_ATR_MULT.get(wctx.strategy)

        if tp_atr_mult is not None:
            if wctx.direction == "long":
                tp_price = wctx.entry_price + tp_atr_mult * atr
                if close >= tp_price:
                    return tp_price, "tp_hit"
            else:
                tp_price = wctx.entry_price - tp_atr_mult * atr
                if close <= tp_price:
                    return tp_price, "tp_hit"
            return None

        # Indicator-based TP
        result = self._check_indicator_tp_close(wctx, close, indicators, atr)
        return result

    def _check_indicator_tp_close(
        self,
        wctx: ExitContext,
        close: float,
        indicators: dict,
        atr: float,
    ) -> tuple[float, str] | None:
        """Indicator-based TP using close price (live mode)."""
        strategy = wctx.strategy
        direction = wctx.direction

        if strategy == "rsi_mean_reversion":
            rsi = indicators.get("RSI_14")
            bb = indicators.get("BBANDS_20")
            pct_b = bb.get("pct_b", 0.5) if isinstance(bb, dict) else None

            if direction == "long":
                if (rsi is not None and rsi > 50.0) or (pct_b is not None and pct_b > 0.50):
                    reason = f"tp_rsi_{rsi:.1f}" if rsi is not None else "tp_bb"
                    return close, reason
            else:
                if (rsi is not None and rsi < 50.0) or (pct_b is not None and pct_b < 0.50):
                    reason = f"tp_rsi_{rsi:.1f}" if rsi is not None else "tp_bb"
                    return close, reason

            # Auxiliary ATR TP cap
            if direction == "long":
                atr_tp_price = wctx.entry_price + MR_AUXILIARY_TP_ATR_MULT * atr
                if close >= atr_tp_price:
                    return atr_tp_price, "tp_hit"
            else:
                atr_tp_price = wctx.entry_price - MR_AUXILIARY_TP_ATR_MULT * atr
                if close <= atr_tp_price:
                    return atr_tp_price, "tp_hit"

        elif strategy == "consecutive_down":
            ema_5 = indicators.get("EMA_5")
            if ema_5 is not None and close > ema_5:
                return close, "tp_ema5"

        elif strategy == "adaptive_mean_reversion":
            if direction == "long":
                tp_price = wctx.entry_price + ADAPTIVE_MR_TP_ATR_LONG * atr
                if close >= tp_price:
                    return tp_price, "tp_hit"
            else:
                tp_price = wctx.entry_price - ADAPTIVE_MR_TP_ATR_SHORT * atr
                if close <= tp_price:
                    return tp_price, "tp_hit"

        return None

    def _check_indicator_tp_intraday(
        self,
        wctx: ExitContext,
        bar: Bar,
        indicators: dict,
        atr: float,
    ) -> tuple[bool, float | None, str]:
        """Indicator-based TP using high/low (INTRADAY mode).

        Returns (hit, price, reason).
        """
        strategy = wctx.strategy
        direction = wctx.direction
        tp_hit = False
        tp_price: float | None = None
        reason = "tp_hit"

        if strategy == "rsi_mean_reversion":
            rsi = indicators.get("RSI_14")
            bb = indicators.get("BBANDS_20")
            pct_b = bb.get("pct_b", 0.5) if isinstance(bb, dict) else None

            if direction == "long":
                tp_hit = (rsi is not None and rsi > 50.0) or (pct_b is not None and pct_b > 0.50)
            else:
                tp_hit = (rsi is not None and rsi < 50.0) or (pct_b is not None and pct_b < 0.50)

            if tp_hit:
                tp_price = bar.close
                if rsi is not None:
                    reason = f"tp_rsi_{rsi:.1f}"
                else:
                    reason = "tp_bb"

            # Auxiliary ATR TP cap
            if not tp_hit:
                if direction == "long":
                    atr_tp_price = wctx.entry_price + MR_AUXILIARY_TP_ATR_MULT * atr
                    if bar.high >= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price
                else:
                    atr_tp_price = wctx.entry_price - MR_AUXILIARY_TP_ATR_MULT * atr
                    if bar.low <= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price

        elif strategy == "consecutive_down":
            ema_5 = indicators.get("EMA_5")
            if ema_5 is not None and bar.close > ema_5:
                tp_hit = True
                tp_price = bar.close
                reason = "tp_ema5"

        elif strategy == "adaptive_mean_reversion":
            if direction == "long":
                calc_tp = wctx.entry_price + ADAPTIVE_MR_TP_ATR_LONG * atr
                if bar.high >= calc_tp:
                    tp_hit = True
                    tp_price = calc_tp
            else:
                calc_tp = wctx.entry_price - ADAPTIVE_MR_TP_ATR_SHORT * atr
                if bar.low <= calc_tp:
                    tp_hit = True
                    tp_price = calc_tp

        return tp_hit, tp_price, reason

    # ------------------------------------------------------------------
    # Trailing stop helper (BAR_CLOSE mode)
    # ------------------------------------------------------------------

    def _check_trailing_close(
        self,
        wctx: ExitContext,
        close: float,
        atr: float,
    ) -> float | None:
        """Check trailing stop using close price. Returns trail price or None."""
        if wctx.strategy not in TRAILING_STRATEGIES:
            return None

        activation_atr = TRAILING_ACTIVATION_ATR.get(wctx.strategy, 1.5)

        if wctx.direction == "long":
            if wctx.trailing_high < wctx.entry_price + activation_atr * atr:
                return None
            wctx.trailing_active = True
            trail_stop = max(
                wctx.entry_price,
                wctx.trailing_high - TRAILING_ATR_MULT * atr,
            )
            if close <= trail_stop:
                return trail_stop
        else:
            if wctx.trailing_low > wctx.entry_price - activation_atr * atr:
                return None
            wctx.trailing_active = True
            trail_stop = min(
                wctx.entry_price,
                wctx.trailing_low + TRAILING_ATR_MULT * atr,
            )
            if close >= trail_stop:
                return trail_stop

        return None

    # ------------------------------------------------------------------
    # Time exit
    # ------------------------------------------------------------------

    @staticmethod
    def _check_time_exit(wctx: ExitContext) -> bool:
        """Return True if max hold days exceeded."""
        max_days = MAX_HOLD_DAYS.get(wctx.strategy)
        if max_days is None:
            return False
        return wctx.bars_held >= max_days

    # ------------------------------------------------------------------
    # Emergency exits (entry day only)
    # ------------------------------------------------------------------

    def _evaluate_emergency(
        self,
        wctx: ExitContext,
        close: float,
    ) -> ExitDecision:
        """Day-1 emergency stop checks.

        - Immediate: -10% loss from entry in a single bar.
        - Confirmed: -7% loss over EMERGENCY_BARS_NEEDED consecutive bars.
        """
        loss_pct = self._loss_pct(wctx, close)

        if loss_pct >= EMERGENCY_LOSS_IMMEDIATE_PCT:
            logger.warning(
                "Emergency exit (immediate -%.1f%%) for %s %s @ %.2f",
                loss_pct * 100, wctx.direction, wctx.symbol, close,
            )
            return ExitDecision(
                should_exit=True,
                reason="emergency_immediate",
                exit_price=close,
                updated_context=wctx,
            )

        if loss_pct >= EMERGENCY_LOSS_CONFIRM_PCT:
            wctx.consecutive_loss_bars += 1
            if wctx.consecutive_loss_bars >= EMERGENCY_BARS_NEEDED:
                logger.warning(
                    "Emergency exit (confirmed -7%% x%d) for %s %s @ %.2f",
                    wctx.consecutive_loss_bars, wctx.direction,
                    wctx.symbol, close,
                )
                return ExitDecision(
                    should_exit=True,
                    reason="emergency_confirmed",
                    exit_price=close,
                    updated_context=wctx,
                )
        else:
            wctx.consecutive_loss_bars = 0

        return _hold(wctx)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _loss_pct(wctx: ExitContext, current_price: float) -> float:
        """Return loss fraction from entry (positive = loss)."""
        if wctx.entry_price <= 0:
            return 0.0
        if wctx.direction == "long":
            return max(0.0, (wctx.entry_price - current_price) / wctx.entry_price)
        else:
            return max(0.0, (current_price - wctx.entry_price) / wctx.entry_price)

    @staticmethod
    def _get_atr(indicators: dict, fallback_atr: float) -> float:
        """Extract ATR from indicator dict with fallback to entry-time ATR."""
        atr = indicators.get("ATR_14")
        if isinstance(atr, (int, float)) and atr > 0:
            return float(atr)
        return fallback_atr if fallback_atr > 0 else 1.0
