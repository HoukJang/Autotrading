"""Tests for UnifiedExitEngine.

Covers all exit rule types in both PriceMode.BAR_CLOSE and
PriceMode.INTRADAY, plus edge cases like both-hit disambiguation
and consistent results when close == high == low.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from autotrader.core.types import Bar
from autotrader.trading.constants import (
    ADAPTIVE_MR_TP_ATR_LONG,
    ADAPTIVE_MR_TP_ATR_SHORT,
    EMERGENCY_BARS_NEEDED,
    EMERGENCY_LOSS_CONFIRM_PCT,
    EMERGENCY_LOSS_IMMEDIATE_PCT,
    MAX_HOLD_DAYS,
    MR_AUXILIARY_TP_ATR_MULT,
    SL_ATR_MULT,
    STAGE1_BE_ACTIVATION_ATR,
    STAGE2_PROFIT_ACTIVATION_ATR,
    STAGE2_PROFIT_LOCK_ATR,
    TP_ATR_MULT,
    TRAILING_ACTIVATION_ATR,
    TRAILING_ATR_MULT,
)
from autotrader.trading.exit_engine import UnifiedExitEngine
from autotrader.trading.types import ExitContext, PriceMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date(2025, 6, 15)
YESTERDAY = date(2025, 6, 14)
TS = datetime(2025, 6, 15, 20, 0, 0, tzinfo=timezone.utc)

STRATEGY_BM = "breakout_momentum"
STRATEGY_MR = "rsi_mean_reversion"
STRATEGY_EMA = "ema_cross_trend"


def _bar(
    close: float,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    symbol: str = "AAPL",
) -> Bar:
    """Create a bar with sensible defaults."""
    if high is None:
        high = close
    if low is None:
        low = close
    if open_ is None:
        open_ = close
    return Bar(
        symbol=symbol, timestamp=TS,
        open=open_, high=high, low=low, close=close,
        volume=1000.0,
    )


def _ctx(
    strategy: str = STRATEGY_BM,
    direction: str = "long",
    entry_price: float = 100.0,
    entry_atr: float = 2.0,
    entry_date: date = YESTERDAY,
    bars_held: int = 1,
    **kwargs,
) -> ExitContext:
    """Create an ExitContext with sensible defaults."""
    return ExitContext(
        symbol="AAPL",
        strategy=strategy,
        direction=direction,
        entry_price=entry_price,
        entry_date=entry_date,
        qty=10,
        entry_atr=entry_atr,
        bars_held=bars_held,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# SL tests
# ---------------------------------------------------------------------------

class TestStopLoss:
    """Test stop-loss in both price modes."""

    def test_sl_hit_bar_close_long(self):
        """SL triggers when close <= sl_price in BAR_CLOSE mode."""
        engine = UnifiedExitEngine()
        # BM long: SL = 2.5 ATR -> sl = 100 - 2.5*2 = 95
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=94.5)  # below 95
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"

    def test_sl_no_hit_bar_close_long(self):
        """SL does not trigger when close > sl_price."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=96.0)  # above 95
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False

    def test_sl_hit_intraday_long(self):
        """In INTRADAY mode, SL triggers on bar.low for long positions."""
        engine = UnifiedExitEngine()
        # BM long: SL = 100 - 2.5*2 = 95
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        # Low touches SL but close recovers
        bar = _bar(close=97.0, low=94.5, high=98.0, open_=97.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"

    def test_sl_hit_intraday_short(self):
        """In INTRADAY mode, SL triggers on bar.high for short positions."""
        engine = UnifiedExitEngine()
        # MR short: SL = 0.75 ATR -> sl = 100 + 0.75*2 = 101.5
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=100.5, high=102.0, low=100.0, open_=100.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"

    def test_sl_no_hit_intraday_long(self):
        """Low stays above SL, no trigger."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=97.0, low=95.5, high=98.0)  # low > 95
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is False


# ---------------------------------------------------------------------------
# TP tests
# ---------------------------------------------------------------------------

class TestTakeProfit:
    """Test take-profit in both price modes."""

    def test_tp_hit_bar_close_long(self):
        """TP triggers when close >= tp_price in BAR_CLOSE mode."""
        engine = UnifiedExitEngine()
        # BM long: TP = 4.0 ATR -> tp = 100 + 4.0*2 = 108
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=109.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(108.0)

    def test_tp_hit_intraday_long(self):
        """TP triggers on bar.high in INTRADAY mode."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=107.0, high=109.0, low=106.0, open_=106.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(108.0)

    def test_tp_hit_intraday_short(self):
        """TP triggers on bar.low for short positions in INTRADAY mode."""
        engine = UnifiedExitEngine()
        # ema_cross_trend short: TP = 5.0 ATR -> tp = 100 - 5*2 = 90
        ctx = _ctx(strategy=STRATEGY_EMA, direction="short",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=91.0, low=89.0, high=92.0, open_=91.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(90.0)

    def test_tp_no_hit_bar_close_long(self):
        """Close below TP, no trigger."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=107.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False

    def test_indicator_tp_rsi_mean_reversion_long(self):
        """RSI-based TP triggers for MR long when RSI > 50."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        indicators = {"RSI_14": 55.0, "BBANDS_20": {"pct_b": 0.6}}
        bar = _bar(close=101.0)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert "tp_rsi" in decision.reason

    def test_indicator_tp_rsi_mean_reversion_short(self):
        """RSI-based TP triggers for MR short when RSI < 50."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0)
        indicators = {"RSI_14": 45.0, "BBANDS_20": {"pct_b": 0.4}}
        bar = _bar(close=99.0)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert "tp_rsi" in decision.reason

    def test_auxiliary_atr_tp_mr_long(self):
        """Auxiliary 2.0 ATR cap for MR long when indicator TP has not fired."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        # RSI below 50 so indicator TP does not fire, but close >= 104 (2.0*2=4)
        indicators = {"RSI_14": 40.0, "BBANDS_20": {"pct_b": 0.3}}
        bar = _bar(close=105.0)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(104.0)


# ---------------------------------------------------------------------------
# Trailing stop tests
# ---------------------------------------------------------------------------

class TestTrailingStop:
    """Test trailing stop activation and trigger."""

    def test_trailing_not_active_before_threshold(self):
        """Trailing stop does not fire before activation threshold is met."""
        engine = UnifiedExitEngine()
        # BM long: activation = 1.5 ATR -> need high >= 100 + 1.5*2 = 103
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=102.0)  # below 103
        bar = _bar(close=98.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        # SL would fire at 95, close=98 is above SL -> hold
        assert decision.should_exit is False

    def test_trailing_activates_and_triggers(self):
        """Trailing stop activates after threshold and triggers on pullback."""
        engine = UnifiedExitEngine()
        # BM long: activation = 1.5 ATR -> high >= 103 activates
        # Trail stop = max(entry, high - 2.0*ATR) = max(100, 106-4) = 102
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=106.0)
        bar = _bar(close=101.5)  # below 102
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "trailing_stop"
        assert decision.updated_context.trailing_active is True

    def test_trailing_short_trigger(self):
        """Trailing stop for short position triggers on bounce."""
        engine = UnifiedExitEngine()
        # EMA short: activation = 1.5 ATR -> low <= 100 - 1.5*2 = 97
        # Trail stop = min(entry, low + 2*2) = min(100, 94+4) = 98
        ctx = _ctx(strategy=STRATEGY_EMA, direction="short",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_low=94.0)
        bar = _bar(close=98.5)  # above 98
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "trailing_stop"

    def test_trailing_intraday_uses_bar_low(self):
        """In INTRADAY mode, trailing uses bar.low for long positions."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=106.0, bars_held=3)
        # Trail stop = max(100, 106 - 4) = 102
        # bar.low = 101.5 <= 102 -> triggers
        bar = _bar(close=103.0, low=101.5, high=104.0, open_=103.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "trailing_stop"


# ---------------------------------------------------------------------------
# 2-stage SL upgrade tests
# ---------------------------------------------------------------------------

class TestStageSLUpgrade:
    """Test breakeven and profit-lock SL upgrades."""

    def test_stage1_breakeven(self):
        """Stage 1: SL moves to breakeven after price moves 1.5 ATR."""
        engine = UnifiedExitEngine()
        # BM long: SL base = 100 - 2.5*2 = 95
        # After highest_price >= 100 + 1.5*2 = 103 -> SL = max(95, 100) = 100
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=103.5)
        # Close at 99.5 -> below breakeven SL of 100
        bar = _bar(close=99.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"
        assert decision.updated_context.stage1_done is True

    def test_stage2_profit_lock(self):
        """Stage 2: SL locks profit after price moves beyond activation."""
        engine = UnifiedExitEngine()
        # BM long: after highest >= 100 + 1.2*2 = 102.4
        # SL = max(95, 100 + 0.4*2) = max(95, 100.8) = 100.8
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=103.0)
        # Close at 100.5 -> below profit-locked SL of 100.8
        bar = _bar(close=100.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"
        assert decision.updated_context.stage2_done is True

    def test_stage2_short_profit_lock(self):
        """Stage 2 for short: SL moves down to lock profit."""
        engine = UnifiedExitEngine()
        # MR short: SL base = 100 + 0.75*2 = 101.5
        # After lowest <= 100 - 1.2*2 = 97.6
        # SL = min(101.5, 100 - 0.4*2) = min(101.5, 99.2) = 99.2
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_low=97.0)
        # Close at 99.5 -> above 99.2 SL
        bar = _bar(close=99.5)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"
        assert decision.updated_context.stage2_done is True


# ---------------------------------------------------------------------------
# Time exit tests
# ---------------------------------------------------------------------------

class TestTimeExit:
    """Test time-based exit."""

    def test_time_exit_triggers_at_max_hold(self):
        """Position exits when bars_held >= max_hold_days."""
        engine = UnifiedExitEngine()
        max_days = MAX_HOLD_DAYS[STRATEGY_MR]  # 5
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    bars_held=max_days)
        # Price in safe zone (no SL/TP)
        bar = _bar(close=100.0)
        indicators = {"RSI_14": 40.0, "BBANDS_20": {"pct_b": 0.3}}
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "time_exit"

    def test_no_time_exit_before_max(self):
        """Position holds when bars_held < max_hold_days."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    bars_held=2)
        bar = _bar(close=100.0)
        indicators = {"RSI_14": 40.0, "BBANDS_20": {"pct_b": 0.3}}
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False

    def test_no_time_exit_for_strategy_without_limit(self):
        """Strategies not in MAX_HOLD_DAYS have no time limit."""
        engine = UnifiedExitEngine()
        # BM is not in MAX_HOLD_DAYS
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    bars_held=100)
        bar = _bar(close=100.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        # BM has no time limit, and close=100 is above SL of 95
        assert decision.should_exit is False


# ---------------------------------------------------------------------------
# Emergency exit tests
# ---------------------------------------------------------------------------

class TestEmergencyExit:
    """Test Day-1 emergency stops."""

    def test_emergency_immediate_10pct(self):
        """Immediate exit on -10% loss on entry day."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0)
        # -11% loss
        bar = _bar(close=89.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "emergency_immediate"

    def test_emergency_confirmed_7pct(self):
        """Confirmed exit after EMERGENCY_BARS_NEEDED consecutive bars at -7%."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0,
                    consecutive_loss_bars=EMERGENCY_BARS_NEEDED - 1)
        # -8% loss (above 7% threshold)
        bar = _bar(close=92.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "emergency_confirmed"

    def test_emergency_7pct_increments_counter(self):
        """Counter increments but no exit when not enough consecutive bars."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0,
                    consecutive_loss_bars=0)
        bar = _bar(close=92.0)  # -8%
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False
        assert decision.updated_context.consecutive_loss_bars == 1

    def test_emergency_counter_resets_on_recovery(self):
        """Counter resets when loss drops below -7%."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0,
                    consecutive_loss_bars=1)
        bar = _bar(close=95.0)  # only -5%, below 7% threshold
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False
        assert decision.updated_context.consecutive_loss_bars == 0

    def test_emergency_short_direction(self):
        """Emergency works for short positions (price going up = loss)."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0)
        bar = _bar(close=111.0)  # +11% loss for short
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is True
        assert decision.reason == "emergency_immediate"

    def test_no_sl_tp_on_entry_day(self):
        """SL/TP are NOT checked on entry day, even if they would trigger."""
        engine = UnifiedExitEngine()
        # BM long: SL = 95, but entry day -> only emergency checks
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    entry_date=TODAY, bars_held=0)
        bar = _bar(close=96.0)  # above emergency thresholds
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.should_exit is False


# ---------------------------------------------------------------------------
# Both-hit disambiguation tests (INTRADAY only)
# ---------------------------------------------------------------------------

class TestBothHitDisambiguation:
    """When both SL and TP are hit in the same bar (INTRADAY mode),
    open proximity decides which fires first."""

    def test_both_hit_sl_closer_to_open(self):
        """SL fires when open is closer to SL than TP."""
        engine = UnifiedExitEngine()
        # BM long: SL = 100 - 2.5*2 = 95, TP = 100 + 4.0*2 = 108
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        # open=96, closer to SL=95 than to TP=108
        bar = _bar(close=100.0, low=94.0, high=109.0, open_=96.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "sl_hit"

    def test_both_hit_tp_closer_to_open(self):
        """TP fires when open is closer to TP than SL."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        # open=107, closer to TP=108 than to SL=95
        bar = _bar(close=100.0, low=94.0, high=109.0, open_=107.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"


# ---------------------------------------------------------------------------
# Mode consistency tests
# ---------------------------------------------------------------------------

class TestModeConsistency:
    """Both modes produce consistent results when close == high == low."""

    def test_sl_same_result_flat_bar(self):
        """SL result is the same in both modes for a flat bar."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        flat_bar = _bar(close=94.0, high=94.0, low=94.0, open_=94.0)

        dec_close = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.BAR_CLOSE)
        dec_intra = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.INTRADAY)

        assert dec_close.should_exit == dec_intra.should_exit
        assert dec_close.reason == dec_intra.reason

    def test_tp_same_result_flat_bar(self):
        """TP result is the same in both modes for a flat bar."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        flat_bar = _bar(close=109.0, high=109.0, low=109.0, open_=109.0)

        dec_close = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.BAR_CLOSE)
        dec_intra = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.INTRADAY)

        assert dec_close.should_exit == dec_intra.should_exit
        assert dec_close.reason == dec_intra.reason

    def test_hold_same_result_flat_bar(self):
        """Hold result is the same in both modes for a flat bar in safe zone."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        flat_bar = _bar(close=100.0, high=100.0, low=100.0, open_=100.0)

        dec_close = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.BAR_CLOSE)
        dec_intra = engine.evaluate(ctx, flat_bar, {}, TODAY, PriceMode.INTRADAY)

        assert dec_close.should_exit is False
        assert dec_intra.should_exit is False


# ---------------------------------------------------------------------------
# Re-entry blocking tests
# ---------------------------------------------------------------------------

class TestReentryBlocking:
    """Test the closed_today / re-entry block mechanism."""

    def test_record_and_check_reentry(self):
        engine = UnifiedExitEngine()
        assert engine.is_reentry_blocked("AAPL") is False
        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True
        assert engine.is_reentry_blocked("MSFT") is False

    def test_new_trading_day_clears(self):
        engine = UnifiedExitEngine()
        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True
        engine.on_new_trading_day(TODAY)
        assert engine.is_reentry_blocked("AAPL") is False


# ---------------------------------------------------------------------------
# MFE/MAE tracking tests
# ---------------------------------------------------------------------------

class TestMFEMAETracking:
    """Updated context should reflect MFE/MAE from bar high/low."""

    def test_mfe_mae_updated(self):
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        bar = _bar(close=101.0, high=103.0, low=99.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert decision.updated_context.mfe_price == 103.0
        assert decision.updated_context.mae_price == 99.0

    def test_original_context_not_mutated(self):
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        original_mfe = ctx.mfe_price
        bar = _bar(close=101.0, high=110.0, low=99.0)
        engine.evaluate(ctx, bar, {}, TODAY, PriceMode.BAR_CLOSE)
        assert ctx.mfe_price == original_mfe  # not mutated


# ---------------------------------------------------------------------------
# INTRADAY trailing stop with bars_held < 2
# ---------------------------------------------------------------------------

class TestTrailingStopIntradayMinBars:
    """Trailing stop requires bars_held >= 2 in INTRADAY mode."""

    def test_trailing_not_triggered_bars_held_0(self):
        """Trailing stop should NOT fire when bars_held < 2 in INTRADAY mode."""
        engine = UnifiedExitEngine()
        # BM long: activation = 1.5 ATR -> high >= 103 activates
        # With trailing_high=106, trail_stop = max(100, 106-4) = 102
        # But bars_held=0 means trailing should NOT be checked
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=106.0, bars_held=0,
                    entry_date=YESTERDAY)
        # bar.low = 101.5 would trigger trailing if active, but bars_held < 2
        bar = _bar(close=103.0, low=101.5, high=104.0, open_=103.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        # SL at 95, TP at 108 -- neither hit, trailing suppressed by bars_held
        assert decision.reason != "trailing_stop"

    def test_trailing_not_triggered_bars_held_1(self):
        """Trailing stop should NOT fire when bars_held == 1 in INTRADAY mode."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=106.0, bars_held=1)
        bar = _bar(close=103.0, low=101.5, high=104.0, open_=103.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.reason != "trailing_stop"

    def test_trailing_fires_at_bars_held_2(self):
        """Trailing stop fires when bars_held >= 2 in INTRADAY mode."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_BM, direction="long",
                    entry_price=100.0, entry_atr=2.0,
                    trailing_high=106.0, bars_held=2)
        # trail_stop = max(100, 106 - 4) = 102, bar.low=101.5 <= 102
        bar = _bar(close=103.0, low=101.5, high=104.0, open_=103.0)
        decision = engine.evaluate(ctx, bar, {}, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "trailing_stop"


# ---------------------------------------------------------------------------
# Indicator TP in INTRADAY mode
# ---------------------------------------------------------------------------

class TestIndicatorTPIntraday:
    """Test indicator-based TP checks in INTRADAY mode."""

    def test_rsi_tp_intraday_long(self):
        """RSI-based TP triggers for MR long in INTRADAY mode when RSI > 50."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        indicators = {"RSI_14": 55.0, "BBANDS_20": {"pct_b": 0.6}}
        bar = _bar(close=101.0, high=102.0, low=100.0, open_=100.5)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert "tp_rsi" in decision.reason

    def test_bb_tp_intraday_short(self):
        """BB-based TP triggers for MR short in INTRADAY mode when pct_b < 0.50."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0)
        indicators = {"BBANDS_20": {"pct_b": 0.3}}
        bar = _bar(close=99.0, high=100.0, low=98.0, open_=99.5)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_bb"

    def test_auxiliary_atr_tp_intraday_long(self):
        """Auxiliary ATR cap fires in INTRADAY when indicator TP does not."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="long",
                    entry_price=100.0, entry_atr=2.0)
        # RSI below 50 and pct_b below 0.50 so indicator TP does not fire
        indicators = {"RSI_14": 40.0, "BBANDS_20": {"pct_b": 0.3}}
        # MR_AUXILIARY_TP_ATR_MULT = 2.0 -> tp = 100 + 2.0*2 = 104
        # bar.high = 105 >= 104 -> hits auxiliary ATR TP
        # bar.low must stay above stage2 SL (100.8) to avoid SL firing first
        bar = _bar(close=103.0, high=105.0, low=101.0, open_=101.0)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(104.0)

    def test_auxiliary_atr_tp_intraday_short(self):
        """Auxiliary ATR cap fires for MR short in INTRADAY when RSI high."""
        engine = UnifiedExitEngine()
        ctx = _ctx(strategy=STRATEGY_MR, direction="short",
                    entry_price=100.0, entry_atr=2.0)
        # RSI above 50, pct_b above 0.50 so indicator TP does not fire for short
        indicators = {"RSI_14": 60.0, "BBANDS_20": {"pct_b": 0.7}}
        # tp = 100 - 2.0*2 = 96, bar.low = 96 hits TP exactly
        # bar.high must stay below stage2 SL. Stage2 activates when
        # trailing_low <= 100 - 1.2*2 = 97.6. bar.low=96 < 97.6 triggers it.
        # Stage2 SL = min(101.5, 100 - 0.4*2) = 99.2
        # bar.high must be below 99.2 to avoid SL hit.
        bar = _bar(close=97.0, high=99.0, low=96.0, open_=98.0)
        decision = engine.evaluate(ctx, bar, indicators, TODAY, PriceMode.INTRADAY)
        assert decision.should_exit is True
        assert decision.reason == "tp_hit"
        assert decision.exit_price == pytest.approx(96.0)


# ---------------------------------------------------------------------------
# ExitContext __post_init__ defaults
# ---------------------------------------------------------------------------

class TestExitContextDefaults:
    """Test ExitContext __post_init__ sets trailing_high/low from entry_price."""

    def test_trailing_high_defaults_to_entry_price(self):
        """When trailing_high is not set, it defaults to entry_price."""
        ctx = ExitContext(
            symbol="AAPL", strategy=STRATEGY_BM, direction="long",
            entry_price=150.0, entry_date=YESTERDAY, qty=10, entry_atr=3.0,
        )
        assert ctx.trailing_high == 150.0

    def test_trailing_low_defaults_to_entry_price(self):
        """When trailing_low is not set, it defaults to entry_price."""
        ctx = ExitContext(
            symbol="AAPL", strategy=STRATEGY_MR, direction="short",
            entry_price=80.0, entry_date=YESTERDAY, qty=5, entry_atr=1.5,
        )
        assert ctx.trailing_low == 80.0

    def test_mfe_defaults_to_entry_price(self):
        """When mfe_price is not set, it defaults to entry_price."""
        ctx = ExitContext(
            symbol="AAPL", strategy=STRATEGY_BM, direction="long",
            entry_price=120.0, entry_date=YESTERDAY, qty=10, entry_atr=2.0,
        )
        assert ctx.mfe_price == 120.0

    def test_mae_defaults_to_entry_price(self):
        """When mae_price is not set, it defaults to entry_price."""
        ctx = ExitContext(
            symbol="AAPL", strategy=STRATEGY_BM, direction="long",
            entry_price=120.0, entry_date=YESTERDAY, qty=10, entry_atr=2.0,
        )
        assert ctx.mae_price == 120.0

    def test_explicit_values_preserved(self):
        """When trailing_high/low are explicitly set, they are not overwritten."""
        ctx = ExitContext(
            symbol="AAPL", strategy=STRATEGY_BM, direction="long",
            entry_price=100.0, entry_date=YESTERDAY, qty=10, entry_atr=2.0,
            trailing_high=110.0, trailing_low=90.0,
            mfe_price=115.0, mae_price=88.0,
        )
        assert ctx.trailing_high == 110.0
        assert ctx.trailing_low == 90.0
        assert ctx.mfe_price == 115.0
        assert ctx.mae_price == 88.0
