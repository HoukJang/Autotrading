"""Unit tests for EmaCrossTrend strategy (autotrader/strategy/ema_cross_trend.py).

Tests cover:
- Long crossover entry (EMA10 crosses above EMA21 with ADX>28, ADX rising, momentum, RSI in range)
- Short crossover entry (EMA10 crosses below EMA21 with ADX>28, ADX rising, momentum, RSI in range)
- No signal when ADX < 28
- No signal when ADX not rising (+2.0 over 3 bars)
- No signal when no momentum (2 consecutive closes in direction)
- No signal when no crossover detected (EMA10 already above EMA21)
- No signal when RSI too high for long (>70)
- No signal when RSI too low for short (<30)
- In-position returns None (all exits handled by ExitRuleEngine)
- Signal metadata includes entry_adx and stop_loss (3.0 ATR)
- Signal strength formula: (adx - 28.0) / 22.0 + abs(ema_10 - ema_21) / ema_21 * 10.0
- Required indicators list
- ADX history tracking
- Momentum confirmation
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.ema_cross_trend import EmaCrossTrend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    symbol: str = "TEST",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: float = 1000.0,
    indicators: dict | None = None,
) -> MarketContext:
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


def _make_ctx_with_history(
    symbol: str = "TEST",
    close: float = 100.0,
    indicators: dict | None = None,
    history_closes: list[float] | None = None,
) -> MarketContext:
    """Create MarketContext with specific close price history."""
    bar = Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 15, 10, 0),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )
    history: deque = deque(maxlen=500)
    if history_closes:
        for i, c in enumerate(history_closes):
            h_bar = Bar(
                symbol=symbol,
                timestamp=datetime(2026, 1, 10 + i, 10, 0),
                open=c,
                high=c + 1,
                low=c - 1,
                close=c,
                volume=1000.0,
            )
            history.append(h_bar)
    history.append(bar)
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


def _full_indicators(
    rsi: float = 50.0,
    atr: float = 2.0,
    adx: float = 32.0,
    ema_10: float = 100.0,
    ema_21: float = 98.0,
) -> dict:
    """Return a complete indicator dict for EmaCrossTrend."""
    return {
        "RSI_14": rsi,
        "ATR_14": atr,
        "ADX_14": adx,
        "EMA_10": ema_10,
        "EMA_21": ema_21,
    }


def _prime_ema_state(
    strategy: EmaCrossTrend,
    symbol: str,
    prev_ema10: float,
    prev_ema21: float,
) -> None:
    """Prime the strategy's EMA state for a symbol to enable crossover detection.

    This simulates a previous bar's EMA values being recorded, so that
    the next on_context call can detect a crossover.
    """
    # Feed one bar to set prev EMA state
    ctx = _make_ctx(
        symbol=symbol,
        close=100.0,
        indicators=_full_indicators(
            rsi=50.0,
            adx=20.0,  # Below ADX_MIN so no signal generated
            ema_10=prev_ema10,
            ema_21=prev_ema21,
        ),
    )
    result = strategy.on_context(ctx)
    # Should be None because ADX < 28
    assert result is None


def _feed_bars_for_adx_history(
    strategy: EmaCrossTrend,
    symbol: str,
    adx_values: list[float],
    ema_10: float = 97.0,
    ema_21: float = 98.0,
) -> None:
    """Feed bars to build ADX history. Last bar sets up prev EMA state."""
    for adx_val in adx_values:
        ctx = _make_ctx(
            symbol=symbol,
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0,
                adx=adx_val,
                ema_10=ema_10,
                ema_21=ema_21,
                atr=2.0,
            ),
        )
        strategy.on_context(ctx)


def _setup_full_entry(
    strategy: EmaCrossTrend,
    symbol: str = "TEST",
    direction: str = "long",
    adx_values: list[float] | None = None,
    entry_close: float = 100.0,
    history_closes: list[float] | None = None,
    rsi: float = 50.0,
    adx: float = 32.0,
    atr: float = 2.0,
    ema_10: float | None = None,
    ema_21: float | None = None,
) -> MarketContext:
    """Setup the full entry conditions: ADX history + EMA state + momentum.

    Returns the MarketContext that should produce a signal when passed to on_context.
    """
    if adx_values is None:
        # Default: ADX rising from 27 -> 32 over 4 bars (rise of 5.0 > 2.0 threshold)
        adx_values = [27.0, 28.0, 30.0]

    if direction == "long":
        prev_ema10 = 97.0
        prev_ema21 = 98.0
        if ema_10 is None:
            ema_10 = 100.0
        if ema_21 is None:
            ema_21 = 98.0
        if history_closes is None:
            history_closes = [96.0, 98.0, 99.0]  # 2 consecutive up closes
    else:
        prev_ema10 = 100.0
        prev_ema21 = 98.0
        if ema_10 is None:
            ema_10 = 96.0
        if ema_21 is None:
            ema_21 = 98.0
        if history_closes is None:
            history_closes = [102.0, 100.0, 99.0]  # 2 consecutive down closes
        rsi = rsi if rsi != 50.0 else 45.0
        entry_close = entry_close if entry_close != 100.0 else 97.0

    # Feed ADX history bars (these also set up EMA state on the last bar)
    _feed_bars_for_adx_history(strategy, symbol, adx_values, ema_10=prev_ema10, ema_21=prev_ema21)

    # Create the entry context with momentum history
    ctx = _make_ctx_with_history(
        symbol=symbol,
        close=entry_close,
        indicators=_full_indicators(
            rsi=rsi,
            adx=adx,
            ema_10=ema_10,
            ema_21=ema_21,
            atr=atr,
        ),
        history_closes=history_closes,
    )
    return ctx


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = EmaCrossTrend()
        assert strategy.name == "ema_cross_trend"

    def test_required_indicators_keys(self):
        strategy = EmaCrossTrend()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "ADX_14" in keys
        assert "EMA_10" in keys
        assert "EMA_21" in keys

    def test_required_indicators_count(self):
        strategy = EmaCrossTrend()
        assert len(strategy.required_indicators) == 5

    def test_adx_min_is_28(self):
        assert EmaCrossTrend.ADX_MIN == 28.0

    def test_sl_atr_mult_is_3(self):
        assert EmaCrossTrend.SL_ATR_MULT == 3.0

    def test_adx_rise_threshold(self):
        assert EmaCrossTrend.ADX_RISE_THRESHOLD == 2.0

    def test_min_momentum_bars(self):
        assert EmaCrossTrend.MIN_MOMENTUM_BARS == 2


# ===================================================================
# 2. Long Crossover Entry
# ===================================================================


class TestLongCrossoverEntry:
    def test_long_crossover_entry(self):
        """Full conditions met: EMA crossover + ADX>28 + ADX rising + momentum -> long signal."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="long")
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "ema_cross_trend"
        assert signal.symbol == "TEST"

    def test_long_crossover_at_exact_boundary(self):
        """prev_ema10 == prev_ema21 then ema10 > ema21 -> crossover detected."""
        strategy = EmaCrossTrend()
        # ADX history: rising
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=98.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=99.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"


# ===================================================================
# 3. Short Crossover Entry
# ===================================================================


class TestShortCrossoverEntry:
    def test_short_crossover_entry(self):
        """Full conditions met: EMA crossover + ADX>28 + ADX rising + momentum -> short signal."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="short")
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "short"
        assert signal.strategy == "ema_cross_trend"

    def test_short_crossover_at_exact_boundary(self):
        """prev_ema10 == prev_ema21 then ema10 < ema21 -> short crossover."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=98.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=97.0,
            indicators=_full_indicators(
                rsi=45.0, adx=32.0, ema_10=97.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[102.0, 100.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "short"


# ===================================================================
# 4. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_adx_too_low(self):
        """ADX < 28 -> no signal even with valid crossover."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [20.0, 22.0, 24.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=27.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_adx_exactly_28(self):
        """ADX == 28 is the boundary -- requires > 28."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [23.0, 25.0, 27.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=28.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_no_crossover(self):
        """EMA10 already above EMA21 on both bars -> no crossover -> no signal."""
        strategy = EmaCrossTrend()
        # prev: ema10 (100) > ema21 (98) -- already above
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=100.0, ema_21=98.0)

        # current: ema10 (101) > ema21 (98) -- still above, no cross
        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=101.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_no_crossover_both_below(self):
        """EMA10 below EMA21 on both bars -> no crossover -> no signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=96.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=97.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=97.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        # ema10 still < ema21 -- no crossover in either direction
        assert strategy.on_context(ctx) is None

    def test_no_signal_rsi_too_high_long(self):
        """RSI > 70 blocks long entry even with valid crossover."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=75.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_rsi_too_low_long(self):
        """RSI < 40 blocks long entry."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=35.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_rsi_too_low_short(self):
        """RSI < 30 blocks short entry."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=100.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=97.0,
            indicators=_full_indicators(
                rsi=25.0, adx=32.0, ema_10=96.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[102.0, 100.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_rsi_too_high_short(self):
        """RSI > 60 blocks short entry."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=100.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=97.0,
            indicators=_full_indicators(
                rsi=65.0, adx=32.0, ema_10=96.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[102.0, 100.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_indicators_missing(self):
        """No signal when any indicator is missing."""
        strategy = EmaCrossTrend()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_on_first_bar(self):
        """First bar has no previous EMA state -> no crossover possible."""
        strategy = EmaCrossTrend()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None


# ===================================================================
# 5. ADX Rising Filter
# ===================================================================


class TestADXRisingFilter:
    def test_no_signal_adx_not_rising(self):
        """ADX > 28 but ADX is flat/declining over 3 bars -> no signal."""
        strategy = EmaCrossTrend()
        # ADX flat/declining: 32 -> 31 -> 31 -> 31 (rise = 31 - 32 = -1 < 2.0)
        _feed_bars_for_adx_history(strategy, "TEST", [32.0, 31.0, 31.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=31.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_signal_with_adx_rising(self):
        """ADX > 28 and ADX rose by +2.5 over 3 bars -> signal."""
        strategy = EmaCrossTrend()
        # ADX rising: 27.0 -> 28.5 -> 29.0 then entry at 32.0 (rise = 32.0 - 27.0 = 5.0 > 2.0)
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.5, 29.0], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_adx_rising_at_exact_threshold(self):
        """ADX rise of exactly 2.0 should pass (>= threshold)."""
        strategy = EmaCrossTrend()
        # ADX: 28.0 -> 29.0 -> 29.5 -> 30.0 (rise = 30.0 - 28.0 = 2.0 >= 2.0)
        _feed_bars_for_adx_history(strategy, "TEST", [28.0, 29.0, 29.5], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_adx_rising_just_below_threshold(self):
        """ADX rise of 1.9 (< 2.0) should be rejected."""
        strategy = EmaCrossTrend()
        # ADX: 29.1 -> 30.0 -> 30.5 -> 31.0 (rise = 31.0 - 29.1 = 1.9 < 2.0)
        _feed_bars_for_adx_history(strategy, "TEST", [29.1, 30.0, 30.5], ema_10=97.0, ema_21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=31.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        assert strategy.on_context(ctx) is None

    def test_adx_rising_skipped_with_insufficient_history(self):
        """With < 4 ADX history entries, ADX rising check is skipped (signal can pass)."""
        strategy = EmaCrossTrend()
        # Only prime with 1 bar for EMA state (ADX history will have 2 entries total)
        _prime_ema_state(strategy, "TEST", prev_ema10=97.0, prev_ema21=98.0)

        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        # Only 2 ADX entries (primed bar + this bar), so rising check skipped -> signal
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"


# ===================================================================
# 6. Momentum Filter
# ===================================================================


class TestMomentumFilter:
    def test_no_signal_no_momentum_long(self):
        """Crossover + ADX ok but no 2 consecutive up closes -> no signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        # History: closes go 100 -> 99 -> 101 (not 2 consecutive up, since 99 < 100)
        ctx = _make_ctx_with_history(
            close=101.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=101.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[100.0, 99.0],  # down then up -- not 2 consecutive up
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_no_momentum_short(self):
        """Crossover + ADX ok but no 2 consecutive down closes -> no signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=100.0, ema_21=98.0)

        # History: closes go 96 -> 97 -> 95 (not 2 consecutive down, since 97 > 96)
        ctx = _make_ctx_with_history(
            close=95.0,
            indicators=_full_indicators(
                rsi=45.0, adx=32.0, ema_10=94.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 97.0],  # up then down -- not 2 consecutive down
        )
        assert strategy.on_context(ctx) is None

    def test_signal_with_momentum_long(self):
        """All conditions met including 2 up closes -> signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        # History: 96 -> 98 -> 99 -> close=100 (3 consecutive up)
        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[96.0, 98.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_signal_with_momentum_short(self):
        """All conditions met including 2 down closes -> signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=100.0, ema_21=98.0)

        # History: 102 -> 100 -> 99 -> close=97 (3 consecutive down)
        ctx = _make_ctx_with_history(
            close=97.0,
            indicators=_full_indicators(
                rsi=45.0, adx=32.0, ema_10=96.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[102.0, 100.0, 99.0],
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "short"

    def test_no_momentum_flat_closes(self):
        """Flat closes (equal) should not satisfy momentum for long."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        # History: 100 -> 100 -> 100 (flat, not strictly increasing)
        ctx = _make_ctx_with_history(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
            history_closes=[100.0, 100.0],
        )
        assert strategy.on_context(ctx) is None

    def test_momentum_insufficient_history(self):
        """With < 3 bars in history, momentum check fails -> no signal."""
        strategy = EmaCrossTrend()
        _feed_bars_for_adx_history(strategy, "TEST", [27.0, 28.0, 30.0], ema_10=97.0, ema_21=98.0)

        # Only 1 bar in history (just the current bar)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        # history deque has only 1 bar -> _has_momentum returns False
        assert strategy.on_context(ctx) is None


# ===================================================================
# 7. In-Position Behavior
# ===================================================================


class TestInPosition:
    def test_in_position_returns_none(self):
        """When already in position, returns None (exit handled by ExitRuleEngine)."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="long")
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

        # Subsequent bars should return None
        for _ in range(5):
            ctx = _make_ctx(
                close=105.0,
                indicators=_full_indicators(
                    rsi=60.0, adx=35.0, ema_10=104.0, ema_21=101.0, atr=2.0,
                ),
            )
            result = strategy.on_context(ctx)
            assert result is None

    def test_no_double_entry(self):
        """While in position for one symbol, no new entry for same symbol."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="long")
        signal = strategy.on_context(ctx)
        assert signal is not None

        # Another crossover attempt -- should be None (already in position)
        ctx_same = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=32.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        result = strategy.on_context(ctx_same)
        assert result is None


# ===================================================================
# 8. Signal Metadata
# ===================================================================


class TestMetadata:
    def test_signal_metadata_has_entry_adx(self):
        """Signal metadata must include entry_adx."""
        strategy = EmaCrossTrend()
        adx = 35.0
        ctx = _setup_full_entry(strategy, direction="long", adx=adx)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["entry_adx"] == pytest.approx(adx)

    def test_signal_metadata_has_stop_loss_long(self):
        """Long signal: stop_loss = close - 3.0 * ATR."""
        strategy = EmaCrossTrend()
        atr = 3.0
        close = 100.0
        ctx = _setup_full_entry(strategy, direction="long", entry_close=close, atr=atr, adx=32.0)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 3.0 * atr)

    def test_signal_metadata_has_stop_loss_short(self):
        """Short signal: stop_loss = close + 3.0 * ATR."""
        strategy = EmaCrossTrend()
        atr = 3.0
        close = 97.0
        ctx = _setup_full_entry(strategy, direction="short", entry_close=close, atr=atr, adx=32.0)
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close + 3.0 * atr)

    def test_signal_metadata_has_sub_strategy_long(self):
        """Long signal: sub_strategy is 'ema_cross_long'."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="long")
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "ema_cross_long"

    def test_signal_metadata_has_sub_strategy_short(self):
        """Short signal: sub_strategy is 'ema_cross_short'."""
        strategy = EmaCrossTrend()
        ctx = _setup_full_entry(strategy, direction="short")
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "ema_cross_short"


# ===================================================================
# 9. Signal Strength
# ===================================================================


class TestSignalStrength:
    def test_signal_strength_calculation(self):
        """strength = min(1.0, (adx-28)/22 + abs(ema10-ema21)/ema21 * 10)."""
        strategy = EmaCrossTrend()
        adx = 35.0
        ema_10 = 100.0
        ema_21 = 98.0
        expected = min(1.0, (adx - 28.0) / 22.0 + abs(ema_10 - ema_21) / ema_21 * 10.0)

        ctx = _setup_full_entry(
            strategy, direction="long", adx=adx, ema_10=ema_10, ema_21=ema_21,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(expected, abs=1e-6)

    def test_signal_strength_clamped_to_1(self):
        """Strength should not exceed 1.0."""
        strategy = EmaCrossTrend()
        # Very strong ADX and large EMA spread
        ctx = _setup_full_entry(
            strategy, direction="long", adx=60.0, ema_10=110.0, ema_21=98.0,
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength <= 1.0


# ===================================================================
# 10. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entry on AAPL should not affect GOOG state."""
        strategy = EmaCrossTrend()

        # Enter on AAPL
        ctx_aapl = _setup_full_entry(strategy, symbol="AAPL", direction="long")
        signal = strategy.on_context(ctx_aapl)
        assert signal is not None
        assert signal.symbol == "AAPL"

        # GOOG with valid entry conditions should also enter
        ctx_goog = _setup_full_entry(strategy, symbol="GOOG", direction="long")
        signal = strategy.on_context(ctx_goog)
        assert signal is not None
        assert signal.symbol == "GOOG"


# ===================================================================
# 11. Required Indicators
# ===================================================================


class TestRequiredIndicators:
    def test_required_indicators(self):
        """Verify required_indicators list includes all needed specs."""
        strategy = EmaCrossTrend()
        keys = {spec.key for spec in strategy.required_indicators}
        expected = {"RSI_14", "ATR_14", "ADX_14", "EMA_10", "EMA_21"}
        assert keys == expected
