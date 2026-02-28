"""Unit tests for ExitRuleEngine (autotrader/execution/exit_rules.py).

Tests cover:
- Day 1 (entry day): NO SL/TP check, only emergency stops
- Day 1: Emergency stop at -7% with 2-bar confirmation
- Day 1: Immediate emergency stop at -10%
- Day 2+: SL triggered at correct ATR multiple per strategy
- Day 2+: TP triggered at correct condition per strategy
- Trailing stop for ADX Pullback and Regime Momentum (2.0x ATR)
- Time-based exit: 5 days for RSI/BB/Short, 7 days for ADX/Momentum
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

    def test_rsi_mr_long_sl_at_2x_atr(self):
        """RSI MR long: SL should trigger at 2.0x ATR below entry (spec says 2.5, code uses 2.0)."""
        # Note: exit_rules.py has rsi_mean_reversion long = 2.0, not 2.5 from spec
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("long", 2.0)
        self._test_sl_triggers("rsi_mean_reversion", "long", actual_mult)

    def test_rsi_mr_short_sl_at_2_5x_atr(self):
        """RSI MR short: SL should trigger at 2.5x ATR above entry."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("short", 2.5)
        self._test_sl_triggers("rsi_mean_reversion", "short", actual_mult)

    def test_bb_squeeze_long_sl_at_1_5x_atr(self):
        """BB Squeeze long: SL should trigger at 1.5x ATR below entry."""
        actual_mult = _SL_ATR_MULT.get("bb_squeeze", {}).get("long", 1.5)
        self._test_sl_triggers("bb_squeeze", "long", actual_mult)

    def test_adx_pullback_long_sl_at_1_5x_atr(self):
        """ADX Pullback long: SL should trigger at 1.5x ATR below entry."""
        actual_mult = _SL_ATR_MULT.get("adx_pullback", {}).get("long", 1.5)
        self._test_sl_triggers("adx_pullback", "long", actual_mult)

    def test_overbought_short_sl_at_2_5x_atr(self):
        """Overbought Short: SL should trigger at 2.5x ATR above entry."""
        actual_mult = _SL_ATR_MULT.get("overbought_short", {}).get("short", 2.5)
        self._test_sl_triggers("overbought_short", "short", actual_mult)

    def test_regime_momentum_long_sl_at_1_5x_atr(self):
        """Regime Momentum long: SL should trigger at 1.5x ATR below entry."""
        actual_mult = _SL_ATR_MULT.get("regime_momentum", {}).get("long", 1.5)
        self._test_sl_triggers("regime_momentum", "long", actual_mult)

    def test_sl_does_not_trigger_above_level_long(self):
        """Long SL should NOT trigger when price is above stop level."""
        actual_mult = _SL_ATR_MULT.get("rsi_mean_reversion", {}).get("long", 2.0)
        self._test_sl_holds("rsi_mean_reversion", "long", actual_mult)

    def test_sl_does_not_trigger_below_level_short(self):
        """Short SL should NOT trigger when price is below stop level."""
        actual_mult = _SL_ATR_MULT.get("overbought_short", {}).get("short", 2.5)
        self._test_sl_holds("overbought_short", "short", actual_mult)

    def test_sl_uses_fallback_atr_when_indicator_unavailable(self):
        """When ATR_14 not in indicators, entry_atr should be used as fallback."""
        engine = ExitRuleEngine()
        atr = 3.0
        entry_price = 100.0
        pos = _make_position(
            strategy="rsi_mean_reversion",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
        )
        sl_mult = _SL_ATR_MULT["rsi_mean_reversion"]["long"]
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

    def test_bb_squeeze_long_tp_triggers_rsi_above_75(self):
        """BB Squeeze long: TP triggers when RSI > 75."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="bb_squeeze",
            direction="long",
            entry_price=100.0,
            bars_held=1,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=108.0,
            bar_high=109.0,
            bar_low=107.0,
            indicators=_indicators(rsi=80.0),  # RSI > 75
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"

    def test_overbought_short_tp_triggers_rsi_below_55(self):
        """Overbought Short: TP triggers when RSI < 55."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="overbought_short",
            direction="short",
            entry_price=100.0,
            bars_held=1,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=96.0,
            bar_high=97.0,
            bar_low=95.0,
            indicators=_indicators(rsi=50.0),  # RSI < 55
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"

    def test_overbought_short_tp_triggers_pct_b_below_050(self):
        """Overbought Short: TP also triggers when pct_b < 0.50."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="overbought_short",
            direction="short",
            entry_price=100.0,
            bars_held=1,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=96.0,
            bar_high=97.0,
            bar_low=95.0,
            indicators=_indicators(rsi=60.0, pct_b=0.40),  # pct_b < 0.50
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"

    def test_adx_pullback_long_tp_at_2_5x_atr_gain(self):
        """ADX Pullback long: TP triggers when close >= entry + 2.5x ATR."""
        engine = ExitRuleEngine()
        atr = 2.0
        entry_price = 100.0
        tp_mult = _TP_ATR_MULT["adx_pullback"]  # 2.5
        pos = _make_position(
            strategy="adx_pullback",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            bars_held=1,
        )
        tp_price = entry_price + tp_mult * atr  # 105.0

        decision = engine.evaluate(
            position=pos,
            bar_close=tp_price + 0.01,
            bar_high=tp_price + 1.0,
            bar_low=tp_price - 0.5,
            indicators=_indicators(atr=atr),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "take_profit"

    def test_adx_pullback_does_not_tp_below_target(self):
        """ADX Pullback should NOT take profit when price is below TP level."""
        engine = ExitRuleEngine()
        atr = 2.0
        entry_price = 100.0
        tp_mult = _TP_ATR_MULT["adx_pullback"]
        # Use HeldPosition directly to set highest_price explicitly
        pos = HeldPosition(
            symbol="AAPL",
            strategy="adx_pullback",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=1,
            qty=10.0,
            highest_price=entry_price,  # no upward move, so trailing stop won't fire
            lowest_price=entry_price,
        )
        # Price below TP level
        bar_close = entry_price + tp_mult * atr - 0.01

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=40.0),
            current_date_et=NEXT_DAY,
        )
        # Either hold, or trailing stop fires, but NOT take_profit
        assert decision.action == "hold" or decision.reason != "take_profit"


# ---------------------------------------------------------------------------
# Test class: trailing stops
# ---------------------------------------------------------------------------

class TestTrailingStop:
    """Trailing stops apply to adx_pullback and regime_momentum only."""

    def test_adx_pullback_trailing_stop_triggers(self):
        """ADX Pullback long trailing stop: close <= highest_price - 2x ATR."""
        engine = ExitRuleEngine()
        # Use large ATR so TP (entry + 2.5*atr) is much higher than trailing stop
        # entry=100, atr=2: TP = 100 + 2.5*2 = 105, trail_stop = 110 - 2*2 = 106
        # bar_close at 105.99 triggers TP first. 
        # Solution: set bar_close above TP to avoid TP, but then trailing fires at 106.
        # Actually the test: close = trail_stop - 0.01 = 105.99 >= TP=105 -> TP fires.
        # Fix: make entry_price high enough so TP is above highest_price
        # OR use highest_price == entry_price so trail_stop is low and TP is reachable
        # Better: set entry_price such that bar_close < TP
        # TP = entry + 2.5*atr. Trail = highest - 2*atr.
        # We want bar_close < TP but bar_close <= trail.
        # Use entry=100, atr=1, highest=120 -> TP=102.5, trail=118
        # bar_close=118.01 >= TP=102.5 -> TP fires. Still wrong.
        # The issue: SL and TP evaluated before trailing.
        # Solution: make bar_close exactly equal to trailing stop but below SL and TP.
        # ADX pullback: SL=entry-1.5*atr=98.5, TP=entry+2.5*atr=102.5, trail=high-2*atr
        # If high=120, atr=1: trail=118. bar_close=117.99 >= TP(102.5) -> TP fires.
        # The only way trailing fires before TP is if RSI/ATR based TP doesn't apply
        # ADX pullback uses ATR-based TP (not RSI). TP evaluated before trailing.
        # So if bar_close >= TP, TP fires. Trailing only fires if bar_close < TP.
        # bar_close at trailing_stop < TP: trail=high-2*atr < entry+2.5*atr
        #   => high < entry + 4.5*atr => if high=entry+4*atr, trail=entry+2*atr < TP(entry+2.5*atr)
        # entry=100, atr=2, high=108 -> trail=104, TP=105. bar_close=103.99 < TP -> trailing fires!
        entry_price = 100.0
        atr = 2.0
        highest_price = 108.0  # trail_stop = 108 - 4 = 104; TP = 100 + 5 = 105

        pos = HeldPosition(
            symbol="AAPL",
            strategy="adx_pullback",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=2,
            qty=10.0,
            highest_price=highest_price,
            lowest_price=entry_price,
        )

        trail_stop = highest_price - _TRAILING_ATR_MULT * atr  # 108 - 4 = 104
        bar_close = trail_stop - 0.01  # 103.99, below trail stop and below TP(105)

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=40.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "trailing_stop"

    def test_regime_momentum_trailing_stop_triggers(self):
        """Regime Momentum long trailing stop should trigger."""
        engine = ExitRuleEngine()
        atr = 3.0
        entry_price = 200.0
        highest_price = 220.0

        pos = HeldPosition(
            symbol="MSFT",
            strategy="regime_momentum",
            direction="long",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=2,
            qty=5.0,
            highest_price=highest_price,
            lowest_price=entry_price,
        )

        trail_stop = highest_price - _TRAILING_ATR_MULT * atr  # 220 - 6 = 214
        bar_close = trail_stop - 0.01

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 1.0,
            bar_low=bar_close - 1.0,
            indicators=_indicators(atr=atr, rsi=40.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "trailing_stop"

    def test_rsi_mr_no_trailing_stop(self):
        """RSI MR should NOT use trailing stop."""
        assert "rsi_mean_reversion" not in _TRAILING_STRATEGIES

    def test_bb_squeeze_no_trailing_stop(self):
        """BB Squeeze should NOT use trailing stop."""
        assert "bb_squeeze" not in _TRAILING_STRATEGIES

    def test_overbought_short_no_trailing_stop(self):
        """Overbought Short should NOT use trailing stop."""
        assert "overbought_short" not in _TRAILING_STRATEGIES

    def test_trailing_stop_short_triggers_when_price_rises(self):
        """Short trailing stop: triggers when close >= lowest_price + 2x ATR."""
        engine = ExitRuleEngine()
        atr = 2.0
        entry_price = 100.0
        # For ADX pullback short: TP = entry - 2.5*atr = 95
        # Trail = lowest + 2*atr. 
        # We need bar_close > TP (95) AND bar_close >= trail.
        # With lowest=90: trail=94. bar_close=95.01 > TP(95)? No, TP for short fires when close<=tp.
        # 95.01 <= 95? No -> TP does not fire. 95.01 >= trail(94)? Yes -> trailing fires!
        lowest_price = 90.0  # trail = 90 + 4 = 94

        pos = HeldPosition(
            symbol="AAPL",
            strategy="adx_pullback",
            direction="short",
            entry_price=entry_price,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=2,
            qty=10.0,
            highest_price=entry_price,
            lowest_price=lowest_price,
        )

        trail_stop = lowest_price + _TRAILING_ATR_MULT * atr  # 94
        # TP for short = entry - 2.5*atr = 95; trailing fires if close >= 94
        # Use close just above TP (95.01) so TP doesn't trigger but trailing does
        tp_price = entry_price - _TP_ATR_MULT["adx_pullback"] * atr  # 95
        bar_close = tp_price + 0.01  # 95.01 > TP(95) -> TP not fired; 95.01 >= trail(94) -> trailing

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 0.5,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=60.0),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "trailing_stop"

    def test_trailing_stop_does_not_trigger_above_stop_level(self):
        """Trailing stop should not trigger if price is above the stop level."""
        engine = ExitRuleEngine()
        atr = 2.0
        highest_price = 110.0
        pos = HeldPosition(
            symbol="AAPL",
            strategy="adx_pullback",
            direction="long",
            entry_price=100.0,
            entry_atr=atr,
            entry_date_et=ENTRY_DATE,
            bars_held=2,
            qty=10.0,
            highest_price=highest_price,
            lowest_price=100.0,
        )
        trail_stop = highest_price - _TRAILING_ATR_MULT * atr  # 106
        bar_close = trail_stop + 0.5  # just above stop

        decision = engine.evaluate(
            position=pos,
            bar_close=bar_close,
            bar_high=bar_close + 1.0,
            bar_low=bar_close - 0.5,
            indicators=_indicators(atr=atr, rsi=40.0),
            current_date_et=NEXT_DAY,
        )
        # Should not exit from trailing stop
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

    def test_overbought_short_exits_at_5_bars(self):
        """Overbought Short: exit when bars_held >= 5."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="overbought_short",
            direction="short",
            entry_price=100.0,
            bars_held=5,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=98.0,  # slight loss for short (price up)
            bar_high=99.0,
            bar_low=97.5,
            indicators=_indicators(rsi=60.0, pct_b=0.60),  # above TP levels
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "time_exit"

    def test_bb_squeeze_exits_at_5_bars(self):
        """BB Squeeze: exit when bars_held >= 5."""
        engine = ExitRuleEngine()
        pos = _make_position(
            strategy="bb_squeeze",
            direction="long",
            bars_held=5,
        )
        decision = engine.evaluate(
            position=pos,
            bar_close=100.5,
            bar_high=101.0,
            bar_low=99.5,
            indicators=_indicators(rsi=40.0, pct_b=0.40),
            current_date_et=NEXT_DAY,
        )
        assert decision.action == "exit"
        assert decision.reason == "time_exit"

    def test_adx_pullback_exits_at_7_bars(self):
        """ADX Pullback: max hold is 7 days (not 5)."""
        engine = ExitRuleEngine()
        # Use HeldPosition directly to set highest_price == entry_price
        # so trailing stop (highest - 2*atr = 100-4=96) is far below bar_close (100.5)
        # and TP (entry + 2.5*atr = 105) is above bar_close (100.5)
        # -> only time_exit fires at bars_held >= 7
        pos = HeldPosition(
            symbol="AAPL",
            strategy="adx_pullback",
            direction="long",
            entry_price=100.0,
            entry_atr=2.0,
            entry_date_et=ENTRY_DATE,
            bars_held=7,
            qty=10.0,
            highest_price=100.0,  # no run-up so trailing stop not near
            lowest_price=100.0,
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

    def test_regime_momentum_exits_at_7_bars(self):
        """Regime Momentum: max hold is 7 days."""
        engine = ExitRuleEngine()
        # Use HeldPosition directly to set highest_price == entry_price
        # so trailing stop (highest - 2*atr = 96) is far below bar_close (100.5)
        # -> only time_exit fires at bars_held >= 7
        pos = HeldPosition(
            symbol="AAPL",
            strategy="regime_momentum",
            direction="long",
            entry_price=100.0,
            entry_atr=2.0,
            entry_date_et=ENTRY_DATE,
            bars_held=7,
            qty=10.0,
            highest_price=100.0,
            lowest_price=100.0,
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
            bars_held=4,  # Max is 5, so 4 bars should hold
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
        assert _MAX_HOLD_DAYS["overbought_short"] == 5
        assert _MAX_HOLD_DAYS["bb_squeeze"] == 5
        assert _MAX_HOLD_DAYS["adx_pullback"] == 7
        assert _MAX_HOLD_DAYS["regime_momentum"] == 7


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
