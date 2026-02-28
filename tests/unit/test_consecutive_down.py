"""Comprehensive tests for ConsecutiveDown strategy using TDD approach."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.consecutive_down import ConsecutiveDown


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
    rsi: float = 50.0,
    atr: float = 2.0,
    ema_50: float = 95.0,
    ema_5: float = 99.0,
) -> dict:
    """Return a complete indicator dict ready for the strategy."""
    return {
        "RSI_14": rsi,
        "ATR_14": atr,
        "EMA_50": ema_50,
        "EMA_5": ema_5,
    }


def _make_consecutive_down_history(
    symbol: str = "TEST",
    start_close: float = 106.0,
    down_days: int = 3,
    final_close: float = 100.0,
) -> deque:
    """Build a history deque with consecutive down closes followed by a final bar.

    Returns a deque where the last `down_days` bars have consecutively
    decreasing closes, ending with `final_close`.
    """
    bars = []
    # First bar (anchor) -- before the down sequence
    bars.append(_make_bar(symbol=symbol, close=start_close))

    step = (start_close - final_close) / down_days
    for i in range(1, down_days + 1):
        c = start_close - step * i
        bars.append(_make_bar(symbol=symbol, close=round(c, 2)))

    return deque(bars, maxlen=500)


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = ConsecutiveDown()
        assert strategy.name == "consecutive_down"

    def test_required_indicators_keys(self):
        strategy = ConsecutiveDown()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "EMA_50" in keys
        assert "EMA_5" in keys

    def test_required_indicators_count(self):
        strategy = ConsecutiveDown()
        assert len(strategy.required_indicators) == 4


# ===================================================================
# 2. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_when_indicators_empty(self):
        """No signal when indicators are missing."""
        strategy = ConsecutiveDown()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_none(self):
        strategy = ConsecutiveDown()
        indicators = _full_indicators()
        indicators["RSI_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema_50_none(self):
        strategy = ConsecutiveDown()
        indicators = _full_indicators()
        indicators["EMA_50"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_fewer_than_3_consecutive_down_days(self):
        """Only 2 consecutive down days should not trigger entry."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=104.0, down_days=2, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_at_50(self):
        """RSI == 50 should NOT trigger (requires strictly < 50)."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=50.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_close_below_ema_50(self):
        """Close <= EMA(50) should block entry."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=96.0, down_days=3, final_close=90.0,
        )
        ctx = _make_ctx(
            close=90.0,
            indicators=_full_indicators(rsi=30.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_close_equal_ema_50(self):
        """Close exactly == EMA(50) should also block (requires strictly >)."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=100.0, down_days=3, final_close=95.0,
        )
        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(rsi=30.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None


# ===================================================================
# 3. Long Entry
# ===================================================================


class TestLongEntry:
    def test_long_entry_conditions_met(self):
        """3+ consecutive down closes + close > EMA(50) + RSI < 40 -> long signal."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "TEST"
        assert signal.strategy == "consecutive_down"

    def test_long_entry_with_4_down_days(self):
        """4 consecutive down days should also trigger."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=108.0, down_days=4, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=25.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_long_entry_metadata_sub_strategy(self):
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "consec_down_long"

    def test_long_entry_metadata_stop_loss(self):
        """stop_loss = close - 1.5 * ATR."""
        strategy = ConsecutiveDown()
        atr = 3.0
        close = 100.0
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=close,
        )
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=30.0, atr=atr, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 1.5 * atr)

    def test_long_entry_metadata_down_days(self):
        """Metadata should contain the count of consecutive down days."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["down_days"] == 3

    def test_long_entry_strength_bounded(self):
        """Strength should be in (0, 1.0] range."""
        strategy = ConsecutiveDown()
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=10.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert 0.0 < signal.strength <= 1.0


# ===================================================================
# 4. Exit -- Target
# ===================================================================


class TestExit:
    def _enter_long(self, strategy: ConsecutiveDown) -> None:
        """Helper: force a long entry using valid conditions."""
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_exit_when_close_above_ema5(self):
        """close > EMA(5) triggers exit with reason='target'."""
        strategy = ConsecutiveDown()
        self._enter_long(strategy)

        ctx = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_50=95.0, ema_5=101.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "target"

    def test_no_exit_when_close_below_ema5(self):
        """close <= EMA(5) should not trigger exit."""
        strategy = ConsecutiveDown()
        self._enter_long(strategy)

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0, ema_5=101.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_exit_when_close_equal_ema5(self):
        """close == EMA(5) should NOT trigger exit (requires strictly >)."""
        strategy = ConsecutiveDown()
        self._enter_long(strategy)

        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=40.0, atr=2.0, ema_50=95.0, ema_5=101.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 5. Re-entry After Exit
# ===================================================================


class TestReentry:
    def test_can_reenter_after_exit(self):
        """After exiting, the strategy should allow a new entry."""
        strategy = ConsecutiveDown()

        # First entry
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "long"

        # Exit
        ctx = _make_ctx(
            close=103.0,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_50=95.0, ema_5=101.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "close"

        # Re-entry
        history2 = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=99.0,
        )
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=28.0, atr=2.0, ema_50=95.0),
            history=history2,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_no_double_entry(self):
        """While in a position, entry conditions should not produce a new signal."""
        strategy = ConsecutiveDown()

        # Enter long
        history = _make_consecutive_down_history(
            start_close=106.0, down_days=3, final_close=100.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "long"

        # Same oversold conditions but already in position -> no exit signal since close < ema_5
        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=25.0, atr=2.0, ema_50=95.0, ema_5=101.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 6. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entering on AAPL should not affect GOOG state."""
        strategy = ConsecutiveDown()

        # Enter AAPL
        history = _make_consecutive_down_history(
            symbol="AAPL", start_close=156.0, down_days=3, final_close=150.0,
        )
        ctx = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(rsi=30.0, atr=3.0, ema_50=145.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "AAPL"

        # GOOG neutral indicators -> no signal
        ctx = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=50.0, atr=4.0, ema_50=195.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None
