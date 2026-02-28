"""Comprehensive tests for VolumeDivergence strategy using TDD approach."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.volume_divergence import VolumeDivergence


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
    rsi: float = 40.0,
    atr: float = 2.0,
    ema_50: float = 95.0,
) -> dict:
    """Return a complete indicator dict ready for the strategy."""
    return {
        "RSI_14": rsi,
        "ATR_14": atr,
        "EMA_50": ema_50,
    }


def _make_divergence_history(
    symbol: str = "TEST",
    num_bars: int = 11,
    start_close: float = 110.0,
    end_close: float = 100.0,
    prior_vol: float = 5000.0,
    recent_vol: float = 2000.0,
) -> deque:
    """Build a history with declining price AND declining volume.

    Creates `num_bars` total bars:
    - Bars 0 to (num_bars - VOL_RECENT_BARS - VOL_PRIOR_BARS - 1): earlier bars with prior_vol
    - Next VOL_PRIOR_BARS bars: prior volume window with prior_vol
    - Last VOL_RECENT_BARS bars: recent volume window with recent_vol
    Prices decline from start_close to end_close.
    """
    bars = []
    step = (start_close - end_close) / max(num_bars - 1, 1)
    # Need enough bars: PRICE_LOOKBACK(5) + VOL_RECENT(3) + VOL_PRIOR(3) = 11
    for i in range(num_bars):
        c = round(start_close - step * i, 2)
        # Volume transitions: first bars have prior_vol, last 3 have recent_vol
        if i >= num_bars - 3:
            vol = recent_vol
        elif i >= num_bars - 6:
            vol = prior_vol
        else:
            vol = prior_vol
        bars.append(_make_bar(symbol=symbol, close=c, volume=vol))

    return deque(bars, maxlen=500)


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = VolumeDivergence()
        assert strategy.name == "volume_divergence"

    def test_required_indicators_keys(self):
        strategy = VolumeDivergence()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "EMA_50" in keys

    def test_required_indicators_count(self):
        strategy = VolumeDivergence()
        assert len(strategy.required_indicators) == 3


# ===================================================================
# 2. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_when_indicators_empty(self):
        strategy = VolumeDivergence()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_none(self):
        strategy = VolumeDivergence()
        indicators = _full_indicators()
        indicators["RSI_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema_50_none(self):
        strategy = VolumeDivergence()
        indicators = _full_indicators()
        indicators["EMA_50"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_price_hasnt_declined(self):
        """Current close >= close[5] means no price decline -> no entry."""
        strategy = VolumeDivergence()
        # Flat history: no price decline
        bars = [_make_bar(close=100.0, volume=5000.0) for _ in range(11)]
        history = deque(bars, maxlen=500)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=40.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_volume_not_declining(self):
        """If recent avg volume >= prior avg volume, no divergence."""
        strategy = VolumeDivergence()
        # Declining price but INCREASING volume
        history = _make_divergence_history(
            start_close=110.0,
            end_close=100.0,
            prior_vol=2000.0,
            recent_vol=5000.0,  # recent vol > prior vol
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=40.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_at_45(self):
        """RSI == 45 should NOT trigger (requires strictly < 45)."""
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=45.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_close_below_ema_50(self):
        """Close <= EMA(50) blocks entry."""
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=100.0, end_close=90.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=90.0,
            indicators=_full_indicators(rsi=35.0, ema_50=95.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_insufficient_history(self):
        """Not enough history bars should produce no signal."""
        strategy = VolumeDivergence()
        # Only 3 bars -- need at least 11 (5+3+3)
        bars = [_make_bar(close=100.0 - i, volume=5000.0) for i in range(3)]
        history = deque(bars, maxlen=500)
        ctx = _make_ctx(
            close=97.0,
            indicators=_full_indicators(rsi=35.0, ema_50=90.0),
            history=history,
        )
        assert strategy.on_context(ctx) is None


# ===================================================================
# 3. Long Entry
# ===================================================================


class TestLongEntry:
    def test_long_entry_conditions_met(self):
        """5-day price decline + declining volume + RSI < 45 + close > EMA(50) -> long."""
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "TEST"
        assert signal.strategy == "volume_divergence"

    def test_long_entry_metadata_sub_strategy(self):
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "vol_div_long"

    def test_long_entry_metadata_stop_loss(self):
        """stop_loss = close - 1.5 * ATR."""
        strategy = VolumeDivergence()
        atr = 3.0
        close = 100.0
        history = _make_divergence_history(
            start_close=110.0, end_close=close,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=35.0, atr=atr, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 1.5 * atr)

    def test_long_entry_metadata_vol_ratio(self):
        """Metadata should include vol_ratio."""
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert "vol_ratio" in signal.metadata
        assert 0.0 < signal.metadata["vol_ratio"] <= 1.0

    def test_long_entry_strength_bounded(self):
        """Strength should be in (0, 1.0] range."""
        strategy = VolumeDivergence()
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=1000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert 0.0 < signal.strength <= 1.0


# ===================================================================
# 4. Exit -- Volume Spike
# ===================================================================


class TestExit:
    def _enter_long(self, strategy: VolumeDivergence) -> None:
        """Helper: force a long entry."""
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_exit_on_volume_spike_with_positive_close(self):
        """volume > 1.5x avg + positive close -> close signal with reason='volume_spike_tp'."""
        strategy = VolumeDivergence()
        self._enter_long(strategy)

        # Build history with 20 bars of avg volume 1000
        bars = [
            _make_bar(close=100.0 + i * 0.1, open_=100.0, volume=1000.0)
            for i in range(20)
        ]
        # Add current bar: volume spike (1600 > 1.5 * 1000) + positive close (close > open)
        spike_bar = _make_bar(close=103.0, open_=101.0, volume=1600.0)
        bars.append(spike_bar)
        history = deque(bars, maxlen=500)

        ctx = MarketContext(
            symbol="TEST",
            bar=spike_bar,
            indicators=_full_indicators(rsi=50.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "volume_spike_tp"

    def test_no_exit_when_volume_not_spike(self):
        """Volume below 1.5x avg should not trigger exit."""
        strategy = VolumeDivergence()
        self._enter_long(strategy)

        # 20 bars of volume 1000, current bar volume = 1400 (< 1.5 * 1000)
        bars = [
            _make_bar(close=100.0, open_=99.5, volume=1000.0)
            for _ in range(20)
        ]
        normal_bar = _make_bar(close=102.0, open_=101.0, volume=1400.0)
        bars.append(normal_bar)
        history = deque(bars, maxlen=500)

        ctx = MarketContext(
            symbol="TEST",
            bar=normal_bar,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_exit_when_volume_spike_but_negative_close(self):
        """Volume spike with negative close (close <= open) should not trigger exit."""
        strategy = VolumeDivergence()
        self._enter_long(strategy)

        bars = [
            _make_bar(close=100.0, open_=99.5, volume=1000.0)
            for _ in range(20)
        ]
        # Negative candle: close < open, even with volume spike
        neg_bar = _make_bar(close=99.0, open_=101.0, volume=2000.0)
        bars.append(neg_bar)
        history = deque(bars, maxlen=500)

        ctx = MarketContext(
            symbol="TEST",
            bar=neg_bar,
            indicators=_full_indicators(rsi=45.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_exit_when_insufficient_history_for_avg(self):
        """Exit requires 20 bars of history for volume average."""
        strategy = VolumeDivergence()
        self._enter_long(strategy)

        # Only 5 bars of history
        bars = [_make_bar(close=100.0, volume=1000.0) for _ in range(5)]
        spike_bar = _make_bar(close=103.0, open_=101.0, volume=2000.0)
        bars.append(spike_bar)
        history = deque(bars, maxlen=500)

        ctx = MarketContext(
            symbol="TEST",
            bar=spike_bar,
            indicators=_full_indicators(rsi=50.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 5. Re-entry After Exit
# ===================================================================


class TestReentry:
    def test_can_reenter_after_exit(self):
        """After exiting, the strategy should allow a new entry."""
        strategy = VolumeDivergence()

        # First entry
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "long"

        # Force exit via volume spike
        bars = [
            _make_bar(close=100.0 + i * 0.1, open_=100.0, volume=1000.0)
            for i in range(20)
        ]
        spike_bar = _make_bar(close=105.0, open_=103.0, volume=1600.0)
        bars.append(spike_bar)
        exit_history = deque(bars, maxlen=500)

        ctx = MarketContext(
            symbol="TEST",
            bar=spike_bar,
            indicators=_full_indicators(rsi=55.0, atr=2.0, ema_50=95.0),
            history=exit_history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "close"

        # Re-entry with new divergence history
        history2 = _make_divergence_history(
            start_close=112.0, end_close=101.0,
            prior_vol=5000.0, recent_vol=1500.0,
        )
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=33.0, atr=2.0, ema_50=96.0),
            history=history2,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_no_double_entry(self):
        """While in a position, entry conditions should not produce a new signal."""
        strategy = VolumeDivergence()

        # Enter
        history = _make_divergence_history(
            start_close=110.0, end_close=100.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=35.0, atr=2.0, ema_50=95.0),
            history=history,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None and signal.direction == "long"

        # Same conditions but already in position -> should check exit, not entry
        # No volume spike, so no exit either
        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=33.0, atr=2.0, ema_50=95.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 6. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entering on AAPL should not affect GOOG state."""
        strategy = VolumeDivergence()

        # Enter AAPL
        history_aapl = _make_divergence_history(
            symbol="AAPL",
            start_close=160.0, end_close=150.0,
            prior_vol=5000.0, recent_vol=2000.0,
        )
        ctx = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(rsi=35.0, atr=3.0, ema_50=145.0),
            history=history_aapl,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "AAPL"

        # GOOG neutral
        ctx = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=50.0, atr=4.0, ema_50=195.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None
