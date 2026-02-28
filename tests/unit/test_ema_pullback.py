"""Comprehensive tests for EmaPullback strategy using TDD approach."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.ema_pullback import EmaPullback


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_bar(
    symbol: str = "TEST",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: float = 1000.0,
    timestamp: datetime | None = None,
) -> Bar:
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    o = open_ if open_ is not None else close
    ts = timestamp if timestamp is not None else datetime(2026, 1, 15, 10, 0)
    return Bar(
        symbol=symbol,
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=close,
        volume=volume,
    )


def _make_ctx(
    symbol: str = "TEST",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: float = 1000.0,
    indicators: dict | None = None,
    history: deque | None = None,
) -> MarketContext:
    bar = _make_bar(
        symbol=symbol,
        close=close,
        high=high,
        low=low,
        open_=open_,
        volume=volume,
    )
    if history is None:
        history = deque([bar], maxlen=500)
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


def _full_indicators(
    rsi: float = 45.0,
    atr: float = 2.0,
    ema_21: float = 100.0,
) -> dict:
    """Return a complete indicator dict ready for the strategy."""
    return {
        "RSI_14": rsi,
        "ATR_14": atr,
        "EMA_21": ema_21,
    }


def _make_rising_history(
    symbol: str = "TEST",
    num_bars: int = 10,
    start_close: float = 90.0,
    end_close: float = 100.0,
) -> deque:
    """Build a history deque with steadily rising closes (for EMA rising check)."""
    bars = []
    step = (end_close - start_close) / max(num_bars - 1, 1)
    for i in range(num_bars):
        c = round(start_close + step * i, 2)
        bars.append(_make_bar(symbol=symbol, close=c))
    return deque(bars, maxlen=500)


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = EmaPullback()
        assert strategy.name == "ema_pullback"

    def test_required_indicators_keys(self):
        strategy = EmaPullback()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "EMA_21" in keys

    def test_required_indicators_count(self):
        strategy = EmaPullback()
        assert len(strategy.required_indicators) == 3


# ===================================================================
# 2. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_when_indicators_empty(self):
        strategy = EmaPullback()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_none(self):
        strategy = EmaPullback()
        indicators = _full_indicators()
        indicators["RSI_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema_21_none(self):
        strategy = EmaPullback()
        indicators = _full_indicators()
        indicators["EMA_21"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_below_range(self):
        """RSI < 35 should block entry."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # First bar: close below EMA (pullback condition)
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)  # sets prev_close_below_ema = True

        # Second bar: close recovers above EMA but RSI too low
        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=30.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_signal_when_rsi_above_range(self):
        """RSI > 55 should block entry."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # First bar: close below EMA
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        # Second bar: recover above EMA but RSI too high
        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=60.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_signal_when_ema_not_rising(self):
        """Entry requires EMA to be rising (recent > prior average)."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # Build a FLAT or declining history so _is_ema_rising returns False
        flat_bars = [_make_bar(close=100.0) for _ in range(10)]
        history = deque(flat_bars, maxlen=500)

        # First bar: close below EMA
        bar_below = _make_bar(close=99.0)
        history.append(bar_below)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        # Declining history: add a bar at exact same level (flat, not rising)
        bar_recover = _make_bar(close=101.0)
        history.append(bar_recover)
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        # With flat history, _is_ema_rising should return False
        assert signal is None

    def test_no_signal_without_prev_close_below_ema(self):
        """Entry requires previous close to have been below EMA."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # First call: close ABOVE ema -> prev_close_below_ema stays False
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=102.0)
        ctx = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)  # prev_close_below_ema = False (102 > 100)

        # Second call: still above EMA -> no pullback -> no entry
        history.append(_make_bar(close=103.0))
        ctx = _make_ctx(
            close=103.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 3. Long Entry
# ===================================================================


class TestLongEntry:
    def test_long_entry_conditions_met(self):
        """prev_close < EMA, current close >= EMA, EMA rising, RSI 35-55 -> long."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # Rising history with pullback below EMA
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)

        # Bar 1: close below EMA (sets prev_close_below_ema)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        # Bar 2: close recovers above EMA
        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "TEST"
        assert signal.strategy == "ema_pullback"

    def test_long_entry_metadata_sub_strategy(self):
        strategy = EmaPullback()
        ema_21 = 100.0

        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "ema_pullback_long"

    def test_long_entry_metadata_stop_loss(self):
        """stop_loss = close - 1.5 * ATR."""
        strategy = EmaPullback()
        ema_21 = 100.0
        atr = 3.0
        close = 101.0

        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=close))
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=45.0, atr=atr, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 1.5 * atr)

    def test_long_entry_rsi_at_lower_bound(self):
        """RSI exactly == 35 should trigger entry (35 <= RSI <= 55)."""
        strategy = EmaPullback()
        ema_21 = 100.0

        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=35.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_long_entry_rsi_at_upper_bound(self):
        """RSI exactly == 55 should trigger entry (boundary is inclusive)."""
        strategy = EmaPullback()
        ema_21 = 100.0

        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=55.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=55.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        # RSI at exactly 55 should pass (55 > RSI_MAX means 55 > 55 is False, so not blocked)
        assert signal is not None
        assert signal.direction == "long"

    def test_long_entry_strength_bounded(self):
        """Strength should be in (0, 1.0] range."""
        strategy = EmaPullback()
        ema_21 = 100.0

        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=40.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert 0.0 < signal.strength <= 1.0


# ===================================================================
# 4. Exit -- EMA Breakdown
# ===================================================================


class TestExit:
    def _enter_long(self, strategy: EmaPullback) -> None:
        """Helper: force a long entry."""
        ema_21 = 100.0
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_exit_after_2_consecutive_closes_below_ema(self):
        """2 consecutive closes below EMA(21) -> close signal with reason='ema_breakdown'."""
        strategy = EmaPullback()
        self._enter_long(strategy)
        ema_21 = 100.0

        # First close below EMA
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is None  # Only 1 bar below, need 2

        # Second consecutive close below EMA
        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=38.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "ema_breakdown"

    def test_no_exit_with_only_1_close_below_ema(self):
        """A single close below EMA(21) should not trigger exit."""
        strategy = EmaPullback()
        self._enter_long(strategy)
        ema_21 = 100.0

        # One bar below EMA
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

        # Recovery above EMA resets counter
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_counter_resets_on_close_above_ema(self):
        """If close goes back above EMA between two below-EMA bars, counter resets."""
        strategy = EmaPullback()
        self._enter_long(strategy)
        ema_21 = 100.0

        # First below
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
        )
        strategy.on_context(ctx)

        # Recovery (resets counter)
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
        )
        strategy.on_context(ctx)

        # Below again (counter = 1, not 2)
        ctx = _make_ctx(
            close=99.5,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is None  # Only 1 consecutive bar below


# ===================================================================
# 5. Re-entry After Exit
# ===================================================================


class TestReentry:
    def test_can_reenter_after_exit(self):
        """After exiting, the strategy should allow a new entry."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # First entry
        history = _make_rising_history(num_bars=10, start_close=90.0, end_close=99.0)
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history,
        )
        strategy.on_context(ctx)

        history.append(_make_bar(close=101.0))
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_21=ema_21),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "long"

        # Exit via 2 consecutive closes below EMA
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=40.0, ema_21=ema_21),
        )
        strategy.on_context(ctx)

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=38.0, ema_21=ema_21),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "close"

        # Now prev_close_below_ema is True (98 < 100), so attempt re-entry
        # with a fresh rising history
        history2 = _make_rising_history(num_bars=10, start_close=91.0, end_close=101.0)
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=42.0, atr=2.0, ema_21=ema_21),
            history=history2,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"


# ===================================================================
# 6. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entering on AAPL should not affect GOOG state."""
        strategy = EmaPullback()
        ema_21 = 100.0

        # AAPL: set up pullback
        history_aapl = _make_rising_history(
            symbol="AAPL", num_bars=10, start_close=90.0, end_close=99.0,
        )
        ctx = _make_ctx(
            symbol="AAPL",
            close=99.0,
            indicators=_full_indicators(rsi=45.0, ema_21=ema_21),
            history=history_aapl,
        )
        strategy.on_context(ctx)

        history_aapl.append(_make_bar(symbol="AAPL", close=101.0))
        ctx = _make_ctx(
            symbol="AAPL",
            close=101.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_21=ema_21),
            history=history_aapl,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.symbol == "AAPL"

        # GOOG: neutral (no pullback setup)
        ctx = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=50.0, atr=4.0, ema_21=195.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None
