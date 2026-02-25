"""Comprehensive tests for AdxPullback strategy using TDD approach."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.adx_pullback import AdxPullback


def _make_ctx(
    symbol="TEST",
    close=100.0,
    high=None,
    low=None,
    open_=None,
    volume=1000.0,
    indicators=None,
):
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    o = open_ if open_ is not None else close
    bar = Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 15, 10, 0),
        open=o,
        high=h,
        low=l,
        close=close,
        volume=volume,
    )
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=deque([bar], maxlen=500),
    )


def _entry_indicators(
    adx=30.0, ema8=105.0, ema21=100.0, rsi=35.0, atr=2.0
):
    """Return indicator dict satisfying all entry conditions by default."""
    return {
        "ADX_14": adx,
        "EMA_8": ema8,
        "EMA_21": ema21,
        "RSI_14": rsi,
        "ATR_14": atr,
    }


class TestAdxPullbackInit:
    """Test strategy initialization."""

    def test_name(self):
        strategy = AdxPullback()
        assert strategy.name == "adx_pullback"

    def test_required_indicators_contain_ema_8(self):
        strategy = AdxPullback()
        keys = [spec.key for spec in strategy.required_indicators]
        assert "EMA_8" in keys

    def test_required_indicators_contain_ema_21(self):
        strategy = AdxPullback()
        keys = [spec.key for spec in strategy.required_indicators]
        assert "EMA_21" in keys

    def test_required_indicators_contain_adx_14(self):
        strategy = AdxPullback()
        keys = [spec.key for spec in strategy.required_indicators]
        assert "ADX_14" in keys

    def test_required_indicators_contain_rsi_14(self):
        strategy = AdxPullback()
        keys = [spec.key for spec in strategy.required_indicators]
        assert "RSI_14" in keys

    def test_required_indicators_contain_atr_14(self):
        strategy = AdxPullback()
        keys = [spec.key for spec in strategy.required_indicators]
        assert "ATR_14" in keys


class TestAdxPullbackNoSignal:
    """Test conditions that should produce no signal."""

    def test_no_signal_when_indicators_none(self):
        strategy = AdxPullback()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_is_none(self):
        strategy = AdxPullback()
        indicators = _entry_indicators()
        indicators["ADX_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_below_25(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(adx=20.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_exactly_25(self):
        """ADX must be strictly greater than 25."""
        strategy = AdxPullback()
        indicators = _entry_indicators(adx=25.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema8_below_ema21(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(ema8=95.0, ema21=100.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema8_equals_ema21(self):
        """EMA(8) must be strictly greater than EMA(21)."""
        strategy = AdxPullback()
        indicators = _entry_indicators(ema8=100.0, ema21=100.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_above_40(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(rsi=45.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_exactly_above_40(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(rsi=40.1)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_close_below_ema21(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(ema21=105.0)
        ctx = _make_ctx(close=100.0, indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_close_equals_ema21(self):
        """close must be strictly greater than EMA(21)."""
        strategy = AdxPullback()
        indicators = _entry_indicators(ema21=100.0)
        ctx = _make_ctx(close=100.0, indicators=indicators)
        assert strategy.on_context(ctx) is None


class TestAdxPullbackEntry:
    """Test long entry conditions."""

    def test_long_entry_all_conditions_met(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(adx=30.0, ema8=105.0, ema21=100.0, rsi=35.0, atr=2.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "adx_pullback"
        assert signal.symbol == "TEST"

    def test_entry_direction_always_long_never_short(self):
        strategy = AdxPullback()
        indicators = _entry_indicators()
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.direction != "short"

    def test_entry_with_rsi_exactly_40(self):
        """RSI <= 40 should trigger entry."""
        strategy = AdxPullback()
        indicators = _entry_indicators(rsi=40.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_entry_strength_calculation(self):
        """Strength = min(1.0, (ADX - 25)/25 + (40 - RSI)/40)."""
        strategy = AdxPullback()
        adx, rsi = 30.0, 35.0
        indicators = _entry_indicators(adx=adx, rsi=rsi)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)

        expected = min(1.0, (adx - 25) / 25 + (40 - rsi) / 40)
        assert signal is not None
        assert abs(signal.strength - expected) < 1e-9

    def test_entry_strength_clamped_to_1(self):
        """Strength should be capped at 1.0 even with extreme values."""
        strategy = AdxPullback()
        indicators = _entry_indicators(adx=80.0, rsi=5.0)
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == 1.0

    def test_entry_metadata_contains_sub_strategy(self):
        strategy = AdxPullback()
        indicators = _entry_indicators()
        ctx = _make_ctx(close=102.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "trend_pullback"

    def test_entry_metadata_contains_stop_loss(self):
        strategy = AdxPullback()
        atr = 2.0
        close = 102.0
        indicators = _entry_indicators(atr=atr)
        ctx = _make_ctx(close=close, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        expected_stop = close - 1.5 * atr
        assert abs(signal.metadata["stop_loss"] - expected_stop) < 1e-9

    def test_no_double_entry_while_in_position(self):
        """Should not generate entry signal when already in position."""
        strategy = AdxPullback()
        indicators = _entry_indicators()
        ctx1 = _make_ctx(close=102.0, indicators=indicators)
        signal1 = strategy.on_context(ctx1)
        assert signal1 is not None
        assert signal1.direction == "long"

        # Second call - still in position, no pullback exit triggered
        ctx2 = _make_ctx(
            close=103.0,
            indicators=_entry_indicators(rsi=50.0),
        )
        signal2 = strategy.on_context(ctx2)
        # Should be None because we are in position and no exit triggered
        assert signal2 is None

    def test_entry_with_different_symbol(self):
        strategy = AdxPullback()
        indicators = _entry_indicators()
        ctx = _make_ctx(symbol="AAPL", close=150.0, indicators=indicators)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.symbol == "AAPL"


class TestAdxPullbackExitRsiTarget:
    """Test exit on RSI > 70 (target)."""

    def test_exit_rsi_above_70(self):
        strategy = AdxPullback()
        # Enter position first
        indicators = _entry_indicators(atr=2.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        # Next bar: RSI > 70 -> exit
        exit_indicators = _entry_indicators(rsi=75.0, atr=2.0)
        ctx_exit = _make_ctx(close=105.0, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.strength == 1.0
        assert signal_exit.metadata["reason"] == "target"


class TestAdxPullbackExitTakeProfit:
    """Test exit on close >= entry + 2.5*ATR."""

    def test_exit_take_profit(self):
        strategy = AdxPullback()
        atr = 2.0
        entry_close = 102.0
        indicators = _entry_indicators(atr=atr)
        ctx_entry = _make_ctx(close=entry_close, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        # Price moves to entry + 2.5*ATR
        take_profit_price = entry_close + 2.5 * atr
        exit_indicators = _entry_indicators(rsi=50.0, atr=atr)
        ctx_exit = _make_ctx(close=take_profit_price, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "take_profit"


class TestAdxPullbackExitTrailingStop:
    """Test trailing stop exit."""

    def test_trailing_stop_updates_highest(self):
        strategy = AdxPullback()
        atr = 2.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, high=103.0, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        # Bar 2: price rises -> highest updates
        indicators_bar2 = _entry_indicators(rsi=50.0, atr=atr)
        ctx_bar2 = _make_ctx(close=106.0, high=107.0, indicators=indicators_bar2)
        signal_bar2 = strategy.on_context(ctx_bar2)
        # No exit yet (RSI not >70, no stop hit)

        # Bar 3: price drops below highest - 2*ATR -> trailing stop
        trailing_threshold = 107.0 - 2.0 * atr  # 103.0
        drop_price = trailing_threshold - 0.5  # 102.5
        indicators_bar3 = _entry_indicators(rsi=50.0, atr=atr)
        ctx_bar3 = _make_ctx(close=drop_price, indicators=indicators_bar3)
        signal_exit = strategy.on_context(ctx_bar3)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "trailing_stop"

    def test_trailing_stop_highest_tracks_high_and_close(self):
        """highest_since_entry should update based on max of close and high.

        We use a large ATR to avoid triggering take_profit prematurely.
        Entry: close=102, high=103, ATR=10 -> take_profit=102+25=127
        Bar 2: close=108, high=115 -> highest=115
        Trailing threshold = 115 - 2*10 = 95
        Bar 3: close=94.5 < 95 -> trailing_stop
        Also check stop_loss: 102 - 1.5*10 = 87. 94.5 > 87, so no stop_loss.
        """
        strategy = AdxPullback()
        atr = 10.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, high=103.0, indicators=indicators)
        strategy.on_context(ctx_entry)

        # Bar 2: high=115 -> highest becomes 115
        indicators_bar2 = _entry_indicators(rsi=50.0, atr=atr)
        ctx_bar2 = _make_ctx(close=108.0, high=115.0, indicators=indicators_bar2)
        strategy.on_context(ctx_bar2)

        # Bar 3: close=94.5, below trailing threshold (95)
        drop_price = 94.5
        indicators_bar3 = _entry_indicators(rsi=50.0, atr=atr)
        ctx_bar3 = _make_ctx(close=drop_price, indicators=indicators_bar3)
        signal_exit = strategy.on_context(ctx_bar3)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "trailing_stop"


class TestAdxPullbackExitTrendReversal:
    """Test exit on EMA dead cross (trend_reversal)."""

    def test_exit_ema_dead_cross(self):
        strategy = AdxPullback()
        atr = 2.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        # EMA dead cross: EMA(8) < EMA(21)
        exit_indicators = _entry_indicators(ema8=98.0, ema21=100.0, rsi=50.0, atr=atr)
        ctx_exit = _make_ctx(close=101.0, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "trend_reversal"


class TestAdxPullbackExitStopLoss:
    """Test exit on stop loss: close <= entry - 1.5*ATR."""

    def test_exit_stop_loss(self):
        """Stop loss fires when close <= entry - 1.5*ATR.

        Entry: close=102, high=102 -> highest=102
        Trailing threshold = 102 - 2*2 = 98
        Stop loss threshold = 102 - 1.5*2 = 99
        Close at 98.5: below stop_loss(99) but above trailing(98) -> stop_loss
        """
        strategy = AdxPullback()
        atr = 2.0
        entry_close = 102.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=entry_close, high=entry_close, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        stop_price = 98.5
        exit_indicators = _entry_indicators(rsi=50.0, atr=atr)
        ctx_exit = _make_ctx(close=stop_price, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "stop_loss"

    def test_exit_stop_loss_below_threshold(self):
        """Stop loss triggers when close drops below entry - 1.5*ATR.

        Use high entry bar to ensure trailing stop threshold is below stop loss
        threshold, so stop_loss is the active exit reason.
        Entry: close=102, high=110 -> highest=110, trailing threshold=110-4=106
        Stop loss threshold = 102-3 = 99
        Close at 98.5 -> below stop loss (99) but above nothing re trailing (106>98.5)
        Actually trailing also triggers (98.5 < 106), so trailing wins by priority.
        To isolate stop_loss, we need trailing threshold > stop loss threshold to NOT fire.
        That means highest - 2*ATR > entry - 1.5*ATR, i.e., highest > entry + 0.5*ATR.
        With highest=close (entry bar high=close), highest=102, trailing=102-4=98.
        stop_loss=102-3=99. If close=98.5: 98.5 < 99 (stop_loss) but 98.5 > 98 (no trailing).
        """
        strategy = AdxPullback()
        atr = 2.0
        entry_close = 102.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        # Set high=entry_close so highest_since_entry = entry_close
        ctx_entry = _make_ctx(close=entry_close, high=entry_close, indicators=indicators)
        strategy.on_context(ctx_entry)

        # close=98.5: below stop_loss(99) but above trailing(98)
        stop_price = 98.5
        exit_indicators = _entry_indicators(rsi=50.0, atr=atr)
        ctx_exit = _make_ctx(close=stop_price, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"
        assert signal_exit.metadata["reason"] == "stop_loss"


class TestAdxPullbackExitTimeout:
    """Test exit on bars_since_entry >= 7 (timeout)."""

    def test_exit_timeout_at_7_bars(self):
        strategy = AdxPullback()
        atr = 2.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        signal_entry = strategy.on_context(ctx_entry)
        assert signal_entry is not None

        # Simulate 6 bars without exit condition (bars_since_entry = 1..6)
        for i in range(6):
            neutral_indicators = _entry_indicators(rsi=50.0, atr=atr, ema8=105.0, ema21=100.0)
            ctx_bar = _make_ctx(close=103.0, indicators=neutral_indicators)
            signal = strategy.on_context(ctx_bar)
            if i < 5:
                # bars_since_entry: 1,2,3,4,5 -> no timeout
                assert signal is None, f"Unexpected signal at bar {i+1}"

        # The 7th bar (bars_since_entry = 7) -> timeout
        # (6 iterations above produced bars_since_entry = 1..6,
        #  last iteration i=5 -> bars_since_entry=6, then this is 7th)
        timeout_indicators = _entry_indicators(rsi=50.0, atr=atr, ema8=105.0, ema21=100.0)
        ctx_timeout = _make_ctx(close=103.0, indicators=timeout_indicators)
        signal_timeout = strategy.on_context(ctx_timeout)
        assert signal_timeout is not None
        assert signal_timeout.direction == "close"
        assert signal_timeout.metadata["reason"] == "timeout"

    def test_no_timeout_at_6_bars(self):
        strategy = AdxPullback()
        atr = 2.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        strategy.on_context(ctx_entry)

        # 6 bars after entry (bars_since_entry 1..6)
        for i in range(6):
            neutral_indicators = _entry_indicators(rsi=50.0, atr=atr, ema8=105.0, ema21=100.0)
            ctx_bar = _make_ctx(close=103.0, indicators=neutral_indicators)
            signal = strategy.on_context(ctx_bar)

        # At bar 6, should NOT be timeout (bars_since_entry = 6)
        assert signal is None


class TestAdxPullbackExitSignalProperties:
    """Test exit signal properties."""

    def test_exit_signal_strength_is_1(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(atr=2.0, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        strategy.on_context(ctx_entry)

        exit_indicators = _entry_indicators(rsi=75.0, atr=2.0)
        ctx_exit = _make_ctx(close=105.0, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.strength == 1.0

    def test_exit_signal_direction_is_close(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(atr=2.0, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        strategy.on_context(ctx_entry)

        exit_indicators = _entry_indicators(rsi=75.0, atr=2.0)
        ctx_exit = _make_ctx(close=105.0, indicators=exit_indicators)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"


class TestAdxPullbackMultiSymbol:
    """Test per-symbol state isolation."""

    def test_separate_state_per_symbol(self):
        strategy = AdxPullback()
        indicators = _entry_indicators()

        ctx_aapl = _make_ctx(symbol="AAPL", close=150.0, indicators=indicators)
        signal_aapl = strategy.on_context(ctx_aapl)
        assert signal_aapl is not None
        assert signal_aapl.symbol == "AAPL"

        # MSFT should still be able to enter independently
        ctx_msft = _make_ctx(symbol="MSFT", close=300.0, indicators=indicators)
        signal_msft = strategy.on_context(ctx_msft)
        assert signal_msft is not None
        assert signal_msft.symbol == "MSFT"

    def test_exit_one_symbol_does_not_affect_other(self):
        strategy = AdxPullback()
        indicators = _entry_indicators(atr=2.0, rsi=35.0)

        # Enter both
        ctx_a = _make_ctx(symbol="A", close=102.0, indicators=indicators)
        strategy.on_context(ctx_a)

        ctx_b = _make_ctx(symbol="B", close=102.0, indicators=indicators)
        strategy.on_context(ctx_b)

        # Exit A via RSI target
        exit_ind = _entry_indicators(rsi=75.0, atr=2.0)
        ctx_a_exit = _make_ctx(symbol="A", close=105.0, indicators=exit_ind)
        signal_a = strategy.on_context(ctx_a_exit)
        assert signal_a is not None
        assert signal_a.direction == "close"

        # B should still be in position (no exit condition)
        neutral_ind = _entry_indicators(rsi=50.0, atr=2.0)
        ctx_b_hold = _make_ctx(symbol="B", close=103.0, indicators=neutral_ind)
        signal_b = strategy.on_context(ctx_b_hold)
        assert signal_b is None  # still holding, no exit triggered


class TestAdxPullbackExitPriority:
    """Test exit condition priority when multiple conditions are true."""

    def test_rsi_target_checked_before_take_profit(self):
        """When both RSI>70 and price>entry+2.5*ATR, RSI target wins (checked first)."""
        strategy = AdxPullback()
        atr = 2.0
        entry_close = 102.0
        indicators = _entry_indicators(atr=atr, rsi=35.0)
        ctx_entry = _make_ctx(close=entry_close, indicators=indicators)
        strategy.on_context(ctx_entry)

        # Both conditions met
        take_profit_price = entry_close + 2.5 * atr + 1.0  # 108.0
        exit_indicators = _entry_indicators(rsi=75.0, atr=atr)
        ctx_exit = _make_ctx(close=take_profit_price, indicators=exit_indicators)
        signal = strategy.on_context(ctx_exit)
        assert signal is not None
        assert signal.metadata["reason"] == "target"

    def test_reentry_after_exit(self):
        """After exiting, strategy should be able to enter again."""
        strategy = AdxPullback()
        indicators = _entry_indicators(atr=2.0, rsi=35.0)
        ctx_entry = _make_ctx(close=102.0, indicators=indicators)
        signal1 = strategy.on_context(ctx_entry)
        assert signal1 is not None

        # Exit via RSI
        exit_ind = _entry_indicators(rsi=75.0, atr=2.0)
        ctx_exit = _make_ctx(close=105.0, indicators=exit_ind)
        signal_exit = strategy.on_context(ctx_exit)
        assert signal_exit is not None
        assert signal_exit.direction == "close"

        # Re-enter
        reentry_ind = _entry_indicators(rsi=35.0, atr=2.0)
        ctx_reentry = _make_ctx(close=102.0, indicators=reentry_ind)
        signal2 = strategy.on_context(ctx_reentry)
        assert signal2 is not None
        assert signal2.direction == "long"
