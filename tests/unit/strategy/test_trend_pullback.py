"""Unit tests for TrendPullback strategy.

Tests cover:
- Required indicators specification
- Entry conditions: trend confirmation, EMA slope, ADX range, proximity,
  RSI range, reversal candle
- Exit conditions: EMA structure break (2 consecutive closes below EMA(21))
- Signal output: strategy name, direction, strength calculation
- Edge cases: insufficient history, missing indicators, boundary values
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.trend_pullback import (
    TrendPullback,
    ADX_MAX,
    ADX_MIN,
    ADX_PERIOD,
    ATR_PERIOD,
    EMA_LONG_PERIOD,
    EMA_SHORT_PERIOD,
    PROXIMITY_LOWER,
    PROXIMITY_UPPER,
    RSI_MAX,
    RSI_MIN,
    RSI_PERIOD,
    SLOPE_LOOKBACK,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)


def _make_bar(
    symbol: str = "AAPL",
    close: float = 100.0,
    open_: float = 99.5,
    high: float = 101.0,
    low: float = 99.0,
    volume: float = 1_000_000.0,
    ts: datetime = TS,
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_ctx(
    symbol: str = "AAPL",
    close: float = 100.0,
    open_: float = 99.5,
    high: float = 101.0,
    low: float = 99.0,
    ema_21: float = 99.0,
    ema_50: float = 95.0,
    adx: float = 25.0,
    rsi: float = 48.0,
    atr: float = 2.0,
    history_len: int = 60,
) -> MarketContext:
    """Create a MarketContext with the given indicator values."""
    bar = _make_bar(symbol=symbol, close=close, open_=open_, high=high, low=low)
    indicators: dict = {
        f"EMA_{EMA_SHORT_PERIOD}": ema_21,
        f"EMA_{EMA_LONG_PERIOD}": ema_50,
        f"ADX_{ADX_PERIOD}": adx,
        f"RSI_{RSI_PERIOD}": rsi,
        f"ATR_{ATR_PERIOD}": atr,
    }
    # Build minimal history
    history: deque[Bar] = deque(maxlen=500)
    for i in range(history_len):
        history.append(_make_bar(symbol=symbol, close=close - 0.01 * i))
    history.append(bar)  # current bar at end
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators,
        history=history,
    )


def _warm_up_ema_history(strategy: TrendPullback, symbol: str, ema_values: list[float]) -> None:
    """Inject EMA(21) history directly into strategy state for slope checks."""
    strategy._ema_history[symbol] = list(ema_values)


# ---------------------------------------------------------------------------
# Test class: Required indicators
# ---------------------------------------------------------------------------

class TestRequiredIndicators:
    """Validate required indicator specs."""

    def test_strategy_name(self):
        s = TrendPullback()
        assert s.name == "trend_pullback"

    def test_required_indicator_count(self):
        s = TrendPullback()
        assert len(s.required_indicators) == 5

    def test_required_ema_21(self):
        s = TrendPullback()
        keys = [spec.key for spec in s.required_indicators]
        assert "EMA_21" in keys

    def test_required_ema_50(self):
        s = TrendPullback()
        keys = [spec.key for spec in s.required_indicators]
        assert "EMA_50" in keys

    def test_required_adx_14(self):
        s = TrendPullback()
        keys = [spec.key for spec in s.required_indicators]
        assert "ADX_14" in keys

    def test_required_rsi_14(self):
        s = TrendPullback()
        keys = [spec.key for spec in s.required_indicators]
        assert "RSI_14" in keys

    def test_required_atr_14(self):
        s = TrendPullback()
        keys = [spec.key for spec in s.required_indicators]
        assert "ATR_14" in keys


# ---------------------------------------------------------------------------
# Test class: Entry conditions
# ---------------------------------------------------------------------------

class TestEntryConditions:
    """Test that each entry condition is properly enforced."""

    def _setup_strategy_with_slope(self, symbol: str = "AAPL", ema_current: float = 99.0):
        """Create a TrendPullback with warmed-up EMA history (positive slope)."""
        s = TrendPullback()
        # Build EMA history: rising slope (current > 5 bars ago)
        ema_5_bars_ago = ema_current - 1.0  # clearly rising
        ema_values = [ema_5_bars_ago] + [
            ema_5_bars_ago + (ema_current - ema_5_bars_ago) * i / SLOPE_LOOKBACK
            for i in range(1, SLOPE_LOOKBACK + 1)
        ]
        _warm_up_ema_history(s, symbol, ema_values)
        return s

    def test_valid_entry_produces_signal(self):
        """All conditions met should produce a long signal."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(
            close=100.0, open_=99.5, ema_21=99.0, ema_50=95.0,
            adx=25.0, rsi=48.0, atr=2.0,
        )
        signal = s.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "trend_pullback"

    def test_entry_blocked_when_close_below_ema50(self):
        """Close <= EMA(50) should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=94.0, ema_21=93.5, ema_50=95.0, adx=25.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_ema_slope_flat(self):
        """EMA(21) not rising should block entry."""
        s = TrendPullback()
        # Flat/declining slope
        ema_values = [99.0] * (SLOPE_LOOKBACK + 1)
        _warm_up_ema_history(s, "AAPL", ema_values)
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_adx_below_range(self):
        """ADX < 15 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=14.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_adx_above_range(self):
        """ADX > 35 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=36.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_at_adx_boundary_min(self):
        """ADX == 15 (exact min) should allow entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=15.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is not None

    def test_entry_at_adx_boundary_max(self):
        """ADX == 35 (exact max) should allow entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=35.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is not None

    def test_entry_blocked_when_price_too_far_above_ema(self):
        """close / EMA(21) > 1.02 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=102.5, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0)
        # ratio = 102.5 / 99.0 = 1.035 > 1.02
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_price_too_far_below_ema(self):
        """close / EMA(21) < 0.97 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=95.0, ema_21=99.0, ema_50=94.0, adx=25.0, rsi=48.0)
        # ratio = 95.0 / 99.0 = 0.959 < 0.97
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_rsi_too_low(self):
        """RSI < 35 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=30.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_rsi_too_high(self):
        """RSI > 60 should block entry."""
        s = self._setup_strategy_with_slope()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=65.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_red_candle_and_no_hammer(self):
        """Red candle (close < open) without hammer pattern should block entry."""
        s = self._setup_strategy_with_slope()
        # Red candle: close < open, and no long lower wick
        ctx = _make_ctx(
            close=99.0, open_=100.0, high=100.5, low=98.5,
            ema_21=98.5, ema_50=95.0, adx=25.0, rsi=48.0,
        )
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_allowed_with_hammer_pattern(self):
        """Hammer pattern (red candle with long lower wick) should allow entry."""
        s = self._setup_strategy_with_slope(ema_current=99.5)
        # Red candle with hammer: open=100, close=99.5, low=97
        # body = 0.5, lower_wick = min(100, 99.5) - 97 = 2.5 > 0.5 * 1.5
        ctx = _make_ctx(
            close=99.5, open_=100.0, high=100.5, low=97.0,
            ema_21=99.5, ema_50=95.0, adx=25.0, rsi=48.0,
        )
        signal = s.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_entry_blocked_when_insufficient_ema_history(self):
        """Not enough EMA history for slope check should block entry."""
        s = TrendPullback()
        # Only 3 EMA values (need SLOPE_LOOKBACK + 1 = 6)
        _warm_up_ema_history(s, "AAPL", [98.0, 98.5, 99.0])
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_entry_blocked_when_indicators_missing(self):
        """Missing indicators should block entry."""
        s = TrendPullback()
        bar = _make_bar(close=100.0)
        ctx = MarketContext(
            symbol="AAPL",
            bar=bar,
            indicators={},  # empty
            history=deque([bar]),
        )
        signal = s.on_context(ctx)
        assert signal is None


# ---------------------------------------------------------------------------
# Test class: Signal output
# ---------------------------------------------------------------------------

class TestSignalOutput:
    """Validate signal metadata and strength calculation."""

    def _make_entry_signal(self, adx: float = 25.0):
        s = TrendPullback()
        ema_values = [98.0] + [98.0 + 0.2 * i for i in range(1, SLOPE_LOOKBACK + 1)]
        _warm_up_ema_history(s, "AAPL", ema_values)
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=adx, rsi=48.0)
        return s.on_context(ctx)

    def test_signal_strategy_name(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert signal.strategy == "trend_pullback"

    def test_signal_direction_is_long(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert signal.direction == "long"

    def test_signal_strength_at_adx_15(self):
        """At ADX=15: strength = 0.5 + (15-15)/40 = 0.5."""
        signal = self._make_entry_signal(adx=15.0)
        assert signal is not None
        assert signal.strength == pytest.approx(0.5, abs=0.01)

    def test_signal_strength_at_adx_35(self):
        """At ADX=35: strength = 0.5 + (35-15)/40 = 1.0."""
        signal = self._make_entry_signal(adx=35.0)
        assert signal is not None
        assert signal.strength == pytest.approx(1.0, abs=0.01)

    def test_signal_strength_at_adx_25(self):
        """At ADX=25: strength = 0.5 + (25-15)/40 = 0.75."""
        signal = self._make_entry_signal(adx=25.0)
        assert signal is not None
        assert signal.strength == pytest.approx(0.75, abs=0.01)

    def test_signal_metadata_contains_stop_loss(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert "stop_loss" in signal.metadata

    def test_signal_metadata_contains_adx(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert "adx" in signal.metadata

    def test_signal_metadata_contains_rsi(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert "rsi" in signal.metadata

    def test_signal_metadata_contains_ema_slope(self):
        signal = self._make_entry_signal()
        assert signal is not None
        assert "ema_slope" in signal.metadata


# ---------------------------------------------------------------------------
# Test class: Exit conditions
# ---------------------------------------------------------------------------

class TestExitConditions:
    """Test strategy-level exit (EMA structure break)."""

    def _setup_in_position(self, symbol: str = "AAPL"):
        """Create a strategy with an active position."""
        s = TrendPullback()
        # Warm up EMA history
        ema_values = [98.0 + 0.2 * i for i in range(SLOPE_LOOKBACK + 1)]
        _warm_up_ema_history(s, symbol, ema_values)

        # Generate entry signal first
        ctx = _make_ctx(
            symbol=symbol,
            close=100.0, open_=99.5, ema_21=99.0, ema_50=95.0,
            adx=25.0, rsi=48.0,
        )
        signal = s.on_context(ctx)
        assert signal is not None  # verify we entered
        return s

    def test_single_close_below_ema_holds(self):
        """One close below EMA(21) should NOT trigger exit."""
        s = self._setup_in_position()
        ctx = _make_ctx(close=98.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=45.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_two_consecutive_closes_below_ema_exits(self):
        """Two consecutive closes below EMA(21) should trigger structure break exit."""
        s = self._setup_in_position()

        # First close below EMA(21)
        ctx1 = _make_ctx(close=98.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=45.0)
        signal1 = s.on_context(ctx1)
        assert signal1 is None

        # Second consecutive close below EMA(21)
        ctx2 = _make_ctx(close=97.5, ema_21=98.5, ema_50=95.0, adx=24.0, rsi=42.0)
        signal2 = s.on_context(ctx2)
        assert signal2 is not None
        assert signal2.direction == "close"
        assert signal2.metadata.get("exit_reason") == "structure_break"

    def test_recovery_resets_consecutive_count(self):
        """Close above EMA(21) after one close below should reset counter."""
        s = self._setup_in_position()

        # First close below EMA(21)
        ctx1 = _make_ctx(close=98.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=45.0)
        s.on_context(ctx1)

        # Recovery: close above EMA(21)
        ctx2 = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=50.0)
        signal2 = s.on_context(ctx2)
        assert signal2 is None

        # Another single close below -- should NOT exit (counter reset)
        ctx3 = _make_ctx(close=98.5, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=45.0)
        signal3 = s.on_context(ctx3)
        assert signal3 is None


# ---------------------------------------------------------------------------
# Test class: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_no_signal_on_first_call_without_history(self):
        """First call without EMA history should return None."""
        s = TrendPullback()
        ctx = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0)
        signal = s.on_context(ctx)
        assert signal is None

    def test_ema_slope_accumulates_over_calls(self):
        """EMA history should accumulate across multiple on_context calls."""
        s = TrendPullback()
        # Call on_context enough times to build slope history
        for i in range(SLOPE_LOOKBACK + 1):
            ema_val = 98.0 + 0.2 * i
            ctx = _make_ctx(
                close=100.0, open_=99.5, ema_21=ema_val, ema_50=95.0,
                adx=25.0, rsi=48.0,
            )
            signal = s.on_context(ctx)

        # After SLOPE_LOOKBACK + 1 calls, should have enough history
        # The last call should produce a signal
        assert signal is not None

    def test_different_symbols_tracked_independently(self):
        """Different symbols should have independent state."""
        s = TrendPullback()
        ema_values = [98.0 + 0.2 * i for i in range(SLOPE_LOOKBACK + 1)]
        _warm_up_ema_history(s, "AAPL", ema_values)
        _warm_up_ema_history(s, "MSFT", ema_values)

        # Enter AAPL
        ctx_aapl = _make_ctx(
            symbol="AAPL",
            close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0,
        )
        signal_aapl = s.on_context(ctx_aapl)
        assert signal_aapl is not None

        # MSFT should also be able to enter independently
        ctx_msft = _make_ctx(
            symbol="MSFT",
            close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0,
        )
        signal_msft = s.on_context(ctx_msft)
        assert signal_msft is not None

    def test_no_entry_while_in_position(self):
        """Should not generate entry signal while already in position."""
        s = TrendPullback()
        ema_values = [98.0 + 0.2 * i for i in range(SLOPE_LOOKBACK + 1)]
        _warm_up_ema_history(s, "AAPL", ema_values)

        # Enter
        ctx1 = _make_ctx(close=100.0, ema_21=99.0, ema_50=95.0, adx=25.0, rsi=48.0)
        signal1 = s.on_context(ctx1)
        assert signal1 is not None
        assert signal1.direction == "long"

        # Try to enter again -- should return None (or exit signal)
        ctx2 = _make_ctx(close=101.0, ema_21=99.5, ema_50=95.0, adx=25.0, rsi=50.0)
        signal2 = s.on_context(ctx2)
        # While in position, should check exit, not entry. Close above EMA -> hold.
        assert signal2 is None
