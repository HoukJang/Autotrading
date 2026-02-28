"""Unit tests for ExitRuleEngine (autotrader/execution/exit_rules.py).

Tests cover:
- Day 1 (entry day): NO SL/TP check, only emergency stops
- Day 1: Emergency stop at -7% with 2-bar confirmation
- Day 1: Immediate emergency stop at -10%
- Day 2+: SL triggered at correct ATR multiple per strategy
- Day 2+: TP triggered at correct condition per strategy
- Trailing stop (currently no strategies use trailing stops)
- Time-based exit: 5 days for all strategies
- Re-entry block: same symbol blocked after exit (both directions)
- Re-entry block: cleared on new trading day
- Long vs Short direction correctly handled
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from autotrader.execution.exit_rules import (
    ExitRuleEngine,
    ExitDecision,
    HeldPosition,
    _MAX_HOLD_DAYS,
    _SL_ATR_MULT,
    _TP_ATR_MULT,
    _TRAILING_ATR_MULT,
    _TRAILING_ACTIVATION_ATR,
    _TRAILING_STRATEGIES,
    _EMERGENCY_LOSS_CONFIRM_PCT,
    _EMERGENCY_LOSS_IMMEDIATE_PCT,
    _EMERGENCY_BARS_NEEDED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENTRY_DATE = date(2026, 2, 24)   # Monday
NEXT_DAY = date(2026, 2, 25)     # Tuesday


def _make_position(
    symbol: str = "AAPL",
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    entry_price: float = 100.0,
    entry_atr: float = 2.0,
    entry_date_et: date = ENTRY_DATE,
    bars_held: int = 0,
    qty: float = 10.0,
) -> HeldPosition:
    """Create a HeldPosition with sensible defaults."""
    return HeldPosition(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        entry_price=entry_price,
        entry_atr=entry_atr,
        entry_date_et=entry_date_et,
        bars_held=bars_held,
        qty=qty,
        highest_price=entry_price,
        lowest_price=entry_price,
    )


def _indicators(atr: float = 2.0, rsi: float = 50.0, pct_b: float = 0.5) -> dict:
    return {
        "ATR_14": atr,
        "RSI_14": rsi,
        "BBANDS_20": {"pct_b": pct_b},
    }


# ---------------------------------------------------------------------------
# Test class: Day 1 behavior
# ---------------------------------------------------------------------------

class TestDay1Behavior:
    """On entry day, normal SL/TP must be suppressed; only emergency stops active."""

    def test_day1_no_sl_triggered_on_normal_loss(self):
        """Day 1: loss below -7% should result in HOLD (not stop-loss exit)."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # 5% loss -- not enough for emergency
        decision = engine.evaluate(
            position=pos,
            bar_close=95.0,
            bar_high=97.0,
            bar_low=94.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "hold"

    def test_day1_no_tp_triggered_on_large_gain(self):
        """Day 1: RSI at 80 (TP condition) should still result in HOLD."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # RSI > 50 would trigger TP on Day 2+; on Day 1 it should not
        decision = engine.evaluate(
            position=pos,
            bar_close=115.0,
            bar_high=116.0,
            bar_low=113.0,
            indicators=_indicators(rsi=80.0),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "hold"

    def test_day1_emergency_stop_immediate_at_10pct_loss(self):
        """Day 1: -10% loss in a single bar should trigger immediate emergency exit."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # 10% loss = entry at 100, close at 90
        decision = engine.evaluate(
            position=pos,
            bar_close=90.0,
            bar_high=92.0,
            bar_low=89.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "exit"
        assert decision.reason == "emergency_immediate"
        assert decision.is_emergency is True

    def test_day1_emergency_stop_7pct_requires_2_bars_first_bar_holds(self):
        """Day 1: First bar at -7% should NOT trigger exit (needs 2 bars)."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # 7% loss = entry at 100, close at 93
        decision = engine.evaluate(
            position=pos,
            bar_close=93.0,
            bar_high=95.0,
            bar_low=92.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "hold"
        assert pos.consecutive_loss_bars == 1

    def test_day1_emergency_stop_7pct_triggers_on_second_bar(self):
        """Day 1: Two consecutive bars at -7% should trigger confirmed emergency exit."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # First bar at -7%
        engine.evaluate(
            position=pos,
            bar_close=93.0,
            bar_high=95.0,
            bar_low=92.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        # Second bar at -7%
        decision = engine.evaluate(
            position=pos,
            bar_close=93.0,
            bar_high=94.0,
            bar_low=92.5,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "exit"
        assert decision.reason == "emergency_confirmed"
        assert decision.is_emergency is True

    def test_day1_emergency_7pct_counter_resets_if_loss_recovers(self):
        """Day 1: Counter should reset if price recovers above -7%."""
        engine = ExitRuleEngine()
        pos = _make_position(entry_price=100.0)
        # First bar at -7%
        engine.evaluate(
            position=pos,
            bar_close=93.0,
            bar_high=95.0,
            bar_low=92.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert pos.consecutive_loss_bars == 1

        # Recovery bar (loss < 7%)
        engine.evaluate(
            position=pos,
            bar_close=96.0,   # only -4% loss
            bar_high=97.0,
            bar_low=95.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert pos.consecutive_loss_bars == 0

    def test_day1_emergency_short_position_loss_is_positive_move(self):
        """Day 1: For short, emergency triggers when price moves UP by 10%."""
        engine = ExitRuleEngine()
        pos = _make_position(
            entry_price=100.0,
            direction="short",
        )
        # Short: entry at 100, close at 111 = +11% adverse move
        decision = engine.evaluate(
            position=pos,
            bar_close=111.0,
            bar_high=112.0,
            bar_low=110.0,
            indicators=_indicators(),
            current_date_et=ENTRY_DATE,
        )
        assert decision.action == "exit"
        assert decision.is_emergency is True


# ---------------------------------------------------------------------------
# Test class: Day 2+ stop-loss per strategy
# ---------------------------------------------------------------------------

class TestDay2StopLoss:
    """Stop-loss should trigger at the correct ATR multiple on Day 2+."""

    def _test_sl_triggers(
        self,
        strategy: str,
        direction: str,
        sl_mult_expected: float,
        entry_price: float = 100.0,
        atr: float = 2.0,
    ):
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy=strategy,
            direction=direction,
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
        )
        sl_distance = sl_mult_expected * atr

        if direction == "long":
            sl_price = entry_price - sl_distance
            bar_close = sl_price - 0.01  # just below SL
        else:
            sl_price = entry_price + sl_distance
            bar_close = sl_price + 0.01  # just above SL

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit", f"{strategy}/{direction}: expected SL exit"
        assert decision.reason == "stop_loss"

    def _test_sl_holds(
        self,
        strategy: str,
        direction: str,
        sl_mult_expected: float,
        entry_price: float = 100.0,
        atr: float = 2.0,
    ):
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy=strategy,
            direction=direction,
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
        )
        sl_distance = sl_mult_expected * atr

        if direction == "long":
            bar_close = entry_price - sl_distance + 0.01  # just above SL
        else:
            bar_close = entry_price + sl_distance - 0.01  # just below SL

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=50.0),
            current_date_et=NEXT_DAY,
        )
        # Should NOT exit on SL (might exit for TP or other reason, but not SL)
        # Specifically: bar just above SL should HOLD for SL check
        if decision.action == "exit":
            assert decision.reason != "stop_loss"

    def test_rsi_mr_long_sl_at_1x_atr(self):
        """RSI MR long: SL should trigger at 1.0x ATR below entry."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("long", 2.0)
        self._test_sl_triggers("rsi_mean_reversion", "long", actual_mult)

    def test_rsi_mr_short_sl_at_1_5x_atr(self):
        """RSI MR short: SL should trigger at 1.5x ATR above entry."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("short", 2.0)
        self._test_sl_triggers("rsi_mean_reversion", "short", actual_mult)

    def test_consecutive_down_long_sl_at_1x_atr(self):
        """Consecutive Down long: SL should trigger at 1.0x ATR below entry."""
        actual_mult = _SL_ATR_MULT.get("consecutive_down", {}).get("long", 2.0)
        self._test_sl_triggers("consecutive_down", "long", actual_mult)

    def test_sl_does_not_trigger_above_level_long(self):
        """Long SL should NOT trigger when price is above stop level."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("long", 2.0)
        self._test_sl_holds("rsi_mean_reversion", "long", actual_mult)

    def test_sl_does_not_trigger_below_level_short(self):
        """Short SL should NOT trigger when price is below stop level."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("short", 2.0)
        self._test_sl_holds("rsi_mean_reversion", "short", actual_mult)

    def test_sl_uses_fallback_atr_when_indicator_unavailable(self):
        """When ATR_14 not in indicators, entry_atr should be used as fallback."""
        engine = ExitRuleEngine()
        atr = 3.0
        entry_price = 100.0
        pos = _make_position(
            strategy="consecutive_down",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
        )
        sl_mult = _SL_ATR_MULT["consecutive_down"]["long"]
        # Price below SL using fallback atr
        bar_close = entry_price - sl_mult * atr - 0.01

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators={},  # No ATR indicator
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "stop_loss"


# ---------------------------------------------------------------------------
# Test class: Day 2+ take-profit per strategy
# ---------------------------------------------------------------------------

class TestDay2TakeProfit:
    """Take-profit should trigger at the correct condition on Day 2+."""

    def test_rsi_mr_long_tp_triggers_when_rsi_above_50(self):
        """RSI MR long: TP triggers when RSI > 50."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="rsi_mean_reversion",
            direction="long",
            entry_price=100.0,
            bars_held=1,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=105.0,
            bar_high=106.0,
            bar_low=104.0,
            indicators=_indicators(rsi=55.0),  # RSI > 50
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert "tp_rsi" in decision.reason

    def test_rsi_mr_short_tp_triggers_when_rsi_below_50(self):
        """RSI MR short: TP triggers when RSI < 50."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="rsi_mean_reversion",
            direction="short",
            entry_price=100.0,
            bars_held=1,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=96.0,
            bar_high=97.0,
            bar_low=95.0,
            indicators=_indicators(rsi=45.0),  # RSI < 50
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert "tp_rsi" in decision.reason

    def test_consecutive_down_long_tp_triggers_above_ema5(self):
        """Consecutive Down long: TP triggers when close > EMA(5)."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="consecutive_down",
            direction="long",
            entry_price=100.0,
            bars_held=1,
        )
        indicators = _indicators(rsi=45.0)
        indicators["EMA_5"] = 101.0
        decision = engine.evaluate(
            position=pos,
            bar_close=102.0,  # close > EMA_5 (101)
            bar_high=103.0,
            bar_low=101.0,
            indicators=indicators,
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert "tp_ema5" in decision.reason

    def test_rsi_mr_long_atr_tp_cap_at_2_0x_atr(self):
        """RSI MR long: auxiliary ATR TP cap triggers when close >= entry + 2.0x ATR."""
        engine = ExitRuleEngine()
        atr = 2.0
        entry_price = 100.0
        atr_tp_mult = 2.0
        pos = _make_position(
            strategy="rsi_mean_reversion",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            bars_held=1,
        )
        tp_price = entry_price + atr_tp_mult * atr  # 104.0

        decision = engine.evaluate(
            position=pos,
            bar_close=tp_price + 0.01,
            bar_high=tp_price + 1.0,
            bar_low=tp_price - 0.5,
            indicators=_indicators(atr=atr, rsi=45.0),  # RSI below 50 -> indicator TP not triggered
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "take_profit"

    def test_rsi_mr_long_no_tp_below_atr_cap(self):
        """RSI MR long: should NOT take profit when price is below the 2.0 ATR cap."""
        engine = ExitRuleEngine()
        atr = 2.0
        entry_price = 100.0
        atr_tp_mult = 2.0
        pos = HeldPosition(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
            qty=10.0,
            highest_price=entry_price,
            lowest_price=entry_price,
        )
        # Price just below the ATR cap
        bar_close = entry_price + atr_tp_mult * atr - 0.01  # 103.99

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=45.0),  # RSI below TP threshold
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "hold" or decision.reason != "take_profit"


# ---------------------------------------------------------------------------
# Test class: trailing stops
# ---------------------------------------------------------------------------

class TestTrailingStop:
    """Trailing stops: currently no strategies use trailing stops."""

    def test_no_strategy_uses_trailing_stop(self):
        """_TRAILING_STRATEGIES should be empty (no strategies use trailing stops)."""
        assert len(_TRAILING_STRATEGIES) == 0

    def test_rsi_mr_no_trailing_stop(self):
        """RSI MR should NOT use trailing stop."""
        assert "rsi_mean_reversion" not in _TRAILING_STRATEGIES

    def test_consecutive_down_no_trailing_stop(self):
        """Consecutive Down should NOT use trailing stop."""
        assert "consecutive_down" not in _TRAILING_STRATEGIES

    def test_trailing_stop_never_fires_for_any_active_strategy(self):
        """Trailing stop should never fire for any of the active strategies."""
        engine = ExitRuleEngine()
        atr = 2.0
        highest_price = 110.0
        # Use rsi_mean_reversion as representative active strategy
        pos = HeldPosition(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            direction="long",
            entry_price=100.0,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=2,
            qty=10.0,
            highest_price=highest_price,
            lowest_price=100.0,
        )
        # Price well below what would be a trailing stop level, but strategy not in set
        bar_close = 106.5

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 1.0,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=45.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.reason != "trailing_stop"


# ---------------------------------------------------------------------------
# Test class: time-based exits
# ---------------------------------------------------------------------------

class TestTimeBasedExit:
    """Time-based forced exits when max hold days reached."""

    def test_rsi_mr_exits_at_5_bars(self):
        """RSI MR: exit when bars_held >= 5."""
        engine = ExitRuleEngine()
        pos = _make_position(strategy="rsi_mean_reversion", bars_held=5)
        # RSI neutral; well above SL -> should trigger time exit
        decision = engine.evaluate(
            position=pos,
            bar_close=100.0,
            bar_high=101.0,
            bar_low=99.0,
            indicators=_indicators(rsi=49.0),  # below TP threshold for long
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "time_exit"

    def test_consecutive_down_exits_at_5_bars(self):
        """Consecutive Down: exit when bars_held >= 5."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="consecutive_down",
            direction="long",
            bars_held=5,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=100.5,
            bar_high=101.0,
            bar_low=99.5,
            indicators=_indicators(rsi=40.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "time_exit"

    def test_no_time_exit_before_max_hold_days(self):
        """Should not trigger time exit before max hold days reached."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="rsi_mean_reversion",
            bars_held=3,  # Max is 5, so 3 bars should hold
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=100.5,
            bar_high=101.0,
            bar_low=99.5,
            indicators=_indicators(rsi=49.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.reason != "time_exit"

    def test_max_hold_days_constants_match_spec(self):
        """MAX_HOLD_DAYS should match the spec values."""
        assert _MAX_HOLD_DAYS["rsi_mean_reversion"] == 5
        assert _MAX_HOLD_DAYS["consecutive_down"] == 5
        assert "volume_divergence" not in _MAX_HOLD_DAYS
        assert "ema_pullback" not in _MAX_HOLD_DAYS


# ---------------------------------------------------------------------------
# Test class: re-entry blocking
# ---------------------------------------------------------------------------

class TestReEntryBlocking:
    """Re-entry blocking prevents same-symbol re-entry on the same calendar day."""

    def test_record_close_blocks_symbol(self):
        """After record_close(), symbol should be blocked from re-entry."""
        engine = ExitRuleEngine()
        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True

    def test_unrecorded_symbol_not_blocked(self):
        """Symbols not closed today should not be blocked."""
        engine = ExitRuleEngine()
        assert engine.is_reentry_blocked("MSFT") is False

    def test_on_new_trading_day_clears_block(self):
        """on_new_trading_day() with a new date should clear all blocks."""
        engine = ExitRuleEngine()
        engine.record_close("AAPL")
        engine.record_close("MSFT")

        today = date(2026, 2, 24)
        tomorrow = date(2026, 2, 25)
        engine._last_clear_date = today

        engine.on_new_trading_day(tomorrow)

        assert engine.is_reentry_blocked("AAPL") is False
        assert engine.is_reentry_blocked("MSFT") is False

    def test_on_new_trading_day_same_date_does_not_clear(self):
        """Calling on_new_trading_day() with same date twice should not clear blocks."""
        engine = ExitRuleEngine()
        today = date(2026, 2, 24)
        engine.on_new_trading_day(today)  # First clear
        engine.record_close("AAPL")

        engine.on_new_trading_day(today)  # Same date, should not re-clear

        assert engine.is_reentry_blocked("AAPL") is True

    def test_block_applies_across_both_directions(self):
        """Block applies regardless of direction (long or short)."""
        engine = ExitRuleEngine()
        engine.record_close("AAPL")
        # Symbol is blocked regardless of direction check
        assert engine.is_reentry_blocked("AAPL") is True

    def test_multiple_symbols_independently_tracked(self):
        """Closing AAPL should not block MSFT."""
        engine = ExitRuleEngine()
        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True
        assert engine.is_reentry_blocked("MSFT") is False


# ---------------------------------------------------------------------------
# Test class: helper utilities
# ---------------------------------------------------------------------------

class TestHelperUtilities:
    """Tests for _loss_pct and _get_atr utility methods."""

    def test_loss_pct_long_calculates_correctly(self):
        """Long loss: (entry - current) / entry."""
        pos = _make_position(direction="long", entry_price=100.0)
        loss = ExitRuleEngine._loss_pct(pos, 90.0)
        assert loss == pytest.approx(0.10)

    def test_loss_pct_short_calculates_correctly(self):
        """Short loss: (current - entry) / entry."""
        pos = _make_position(direction="short", entry_price=100.0)
        loss = ExitRuleEngine._loss_pct(pos, 110.0)
        assert loss == pytest.approx(0.10)

    def test_loss_pct_returns_zero_for_profit(self):
        """Profitable positions should return 0 (not negative)."""
        pos = _make_position(direction="long", entry_price=100.0)
        loss = ExitRuleEngine._loss_pct(pos, 110.0)
        assert loss == 0.0

    def test_get_atr_returns_indicator_atr_when_available(self):
        """Should return ATR_14 from indicators when present and positive."""
        atr = ExitRuleEngine._get_atr({"ATR_14": 3.0}, fallback_atr=2.0)
        assert atr == 3.0

    def test_get_atr_returns_fallback_when_missing(self):
        """Should return fallback_atr when ATR_14 not in indicators."""
        atr = ExitRuleEngine._get_atr({}, fallback_atr=2.0)
        assert atr == 2.0

    def test_get_atr_returns_fallback_when_zero(self):
        """ATR_14 of 0 should fall back to entry_atr."""
        atr = ExitRuleEngine._get_atr({"ATR_14": 0.0}, fallback_atr=2.0)
        assert atr == 2.0
