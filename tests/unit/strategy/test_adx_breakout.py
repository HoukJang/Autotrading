"""Unit tests for AdxBreakout strategy (autotrader/strategy/adx_breakout.py).

Tests cover:
- Entry signal generation with valid conditions
- No signal when ADX < 25
- No signal when EMA10 < EMA21 (downtrend)
- No signal when RSI outside 40-65
- No signal when price too far from EMA10
- Signal metadata includes entry_adx and stop_loss
- Direction is always "long"
- Position state tracking (in_position, no exit signals)
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.adx_breakout import AdxBreakout


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


def _full_indicators(
    rsi: float = 50.0,
    atr: float = 2.0,
    adx: float = 30.0,
    ema_10: float = 100.0,
    ema_21: float = 98.0,
) -> dict:
    """Return a complete indicator dict for AdxBreakout."""
    return {
        "RSI_14": rsi,
        "ATR_14": atr,
        "ADX_14": adx,
        "EMA_10": ema_10,
        "EMA_21": ema_21,
    }


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = AdxBreakout()
        assert strategy.name == "adx_breakout"

    def test_required_indicators_keys(self):
        strategy = AdxBreakout()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "ADX_14" in keys
        assert "EMA_10" in keys
        assert "EMA_21" in keys

    def test_required_indicators_count(self):
        strategy = AdxBreakout()
        assert len(strategy.required_indicators) == 5


# ===================================================================
# 2. Valid Entry Signal
# ===================================================================


class TestValidEntry:
    def test_entry_all_conditions_met(self):
        """ADX>25, EMA10>EMA21, close near EMA10, RSI 40-65 -> long signal."""
        strategy = AdxBreakout()
        # close=100, EMA10=100 -> close is exactly at EMA10 (within range)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "adx_breakout"
        assert signal.symbol == "TEST"

    def test_entry_direction_always_long(self):
        """AdxBreakout is long-only."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_entry_at_pullback_lower_bound(self):
        """Close at EMA10 * 0.985 (lower bound) should still enter."""
        strategy = AdxBreakout()
        ema_10 = 100.0
        close = ema_10 * 0.985  # exactly at lower bound
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=ema_10, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None

    def test_entry_at_pullback_upper_bound(self):
        """Close at EMA10 * 1.005 (upper bound) should still enter."""
        strategy = AdxBreakout()
        ema_10 = 100.0
        close = ema_10 * 1.005  # exactly at upper bound
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=ema_10, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None

    def test_signal_strength_calculation(self):
        """strength = min(1.0, (adx-25)/25 + (rsi-40)/50)."""
        strategy = AdxBreakout()
        adx = 35.0
        rsi = 55.0
        expected = min(1.0, (adx - 25.0) / 25.0 + (rsi - 40.0) / 50.0)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=rsi, adx=adx, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(expected, abs=1e-6)


# ===================================================================
# 3. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_when_adx_below_25(self):
        """ADX <= 25 means no trending market confirmed."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=24.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_exactly_25(self):
        """ADX == 25 is the boundary -- should NOT trigger (requires > 25)."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=25.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema10_below_ema21(self):
        """EMA10 <= EMA21 means downtrend -- no long entry."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=97.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_ema10_equals_ema21(self):
        """EMA10 == EMA21 is not an uptrend -- no entry."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=98.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_below_40(self):
        """RSI < 40 is too oversold for a trend entry."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=35.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_above_65(self):
        """RSI > 65 is overbought for entry."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=70.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_at_boundary_40(self):
        """RSI == 40 should still enter (>= 40)."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=40.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None  # 40 is included

    def test_no_signal_when_rsi_at_boundary_65(self):
        """RSI == 65 should still enter (<= 65)."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=65.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None  # 65 is included

    def test_no_signal_when_price_too_far_below_ema10(self):
        """Close below EMA10 * 0.985 is too far from EMA10."""
        strategy = AdxBreakout()
        ema_10 = 100.0
        close = ema_10 * 0.984  # just below lower bound
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=ema_10, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_price_too_far_above_ema10(self):
        """Close above EMA10 * 1.005 is too far from EMA10."""
        strategy = AdxBreakout()
        ema_10 = 100.0
        close = ema_10 * 1.006  # just above upper bound
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=ema_10, ema_21=98.0, atr=2.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_indicators_missing(self):
        """No signal when any indicator is missing."""
        strategy = AdxBreakout()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_none(self):
        """No signal when ADX is None."""
        strategy = AdxBreakout()
        indicators = _full_indicators()
        indicators["ADX_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None


# ===================================================================
# 4. Signal Metadata
# ===================================================================


class TestMetadata:
    def test_metadata_has_entry_adx(self):
        """Signal metadata must include entry_adx."""
        strategy = AdxBreakout()
        adx = 32.0
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=adx, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["entry_adx"] == pytest.approx(adx)

    def test_metadata_has_stop_loss(self):
        """Signal metadata must include stop_loss = close - 1.5 * ATR."""
        strategy = AdxBreakout()
        atr = 3.0
        close = 100.0
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=atr,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 1.5 * atr)

    def test_metadata_has_sub_strategy(self):
        """Signal metadata must include sub_strategy."""
        strategy = AdxBreakout()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "adx_breakout_long"


# ===================================================================
# 5. Position State
# ===================================================================


class TestPositionState:
    def test_no_exit_signal_when_in_position(self):
        """Once in position, strategy returns None (exit handled by ExitRuleEngine)."""
        strategy = AdxBreakout()
        # Enter
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None
        assert signal.direction == "long"

        # Subsequent bars should return None (no close signal)
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
        """While in position, no new entry signal should be generated."""
        strategy = AdxBreakout()
        # Enter
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None

        # Same conditions again -- should be None (already in position)
        ctx_same = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=100.0, ema_21=98.0, atr=2.0,
            ),
        )
        result = strategy.on_context(ctx_same)
        assert result is None


# ===================================================================
# 6. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entry on AAPL should not affect GOOG state."""
        strategy = AdxBreakout()

        # Enter on AAPL
        ctx_aapl = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=150.0, ema_21=148.0, atr=3.0,
            ),
        )
        signal = strategy.on_context(ctx_aapl)
        assert signal is not None
        assert signal.symbol == "AAPL"

        # GOOG with valid entry conditions should also enter
        ctx_goog = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(
                rsi=50.0, adx=30.0, ema_10=200.0, ema_21=198.0, atr=4.0,
            ),
        )
        signal = strategy.on_context(ctx_goog)
        assert signal is not None
        assert signal.symbol == "GOOG"
