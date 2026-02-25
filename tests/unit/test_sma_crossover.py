"""Tests for SMA Crossover strategy.

TDD tests validating dual moving average crossover signal generation.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.sma_crossover import SmaCrossover


def _make_ctx(
    symbol: str,
    close: float,
    fast_sma: float | None,
    slow_sma: float | None,
    fast_period: int = 10,
    slow_period: int = 30,
) -> MarketContext:
    bar = Bar(
        symbol,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        close,
        close + 1,
        close - 1,
        close,
        100,
    )
    indicators: dict[str, float | dict | None] = {}
    if fast_sma is not None:
        indicators[f"SMA_{fast_period}"] = fast_sma
    if slow_sma is not None:
        indicators[f"SMA_{slow_period}"] = slow_sma
    return MarketContext(symbol=symbol, bar=bar, indicators=indicators, history=deque([bar]))


class TestSmaCrossover:
    def test_no_signal_when_indicators_none(self):
        """Warmup period: missing indicator values should return None."""
        strategy = SmaCrossover()
        ctx = _make_ctx("AAPL", 150.0, fast_sma=None, slow_sma=None)
        assert strategy.on_context(ctx) is None

    def test_no_signal_on_first_bar(self):
        """First bar with indicators has no previous state, should return None."""
        strategy = SmaCrossover()
        ctx = _make_ctx("AAPL", 150.0, fast_sma=152.0, slow_sma=148.0)
        assert strategy.on_context(ctx) is None

    def test_long_signal_on_golden_cross(self):
        """Fast SMA crossing above slow SMA should produce a long signal."""
        strategy = SmaCrossover()
        # First bar: fast below slow (no signal, establishes state)
        ctx1 = _make_ctx("AAPL", 150.0, fast_sma=148.0, slow_sma=152.0)
        assert strategy.on_context(ctx1) is None

        # Second bar: fast above slow (golden cross)
        ctx2 = _make_ctx("AAPL", 155.0, fast_sma=153.0, slow_sma=151.0)
        signal = strategy.on_context(ctx2)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "sma_crossover"
        assert signal.symbol == "AAPL"
        assert 0.0 <= signal.strength <= 1.0

    def test_close_signal_on_death_cross(self):
        """Fast SMA crossing below slow SMA should produce a close signal."""
        strategy = SmaCrossover()
        # First bar: fast above slow
        ctx1 = _make_ctx("AAPL", 155.0, fast_sma=153.0, slow_sma=151.0)
        assert strategy.on_context(ctx1) is None

        # Second bar: fast below slow (death cross)
        ctx2 = _make_ctx("AAPL", 148.0, fast_sma=149.0, slow_sma=152.0)
        signal = strategy.on_context(ctx2)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strategy == "sma_crossover"
        assert signal.symbol == "AAPL"

    def test_no_signal_when_trend_continues(self):
        """No crossover (fast stays above slow) should return None."""
        strategy = SmaCrossover()
        # First bar: fast above slow
        ctx1 = _make_ctx("AAPL", 155.0, fast_sma=153.0, slow_sma=151.0)
        assert strategy.on_context(ctx1) is None

        # Second bar: fast still above slow (no crossover)
        ctx2 = _make_ctx("AAPL", 156.0, fast_sma=154.0, slow_sma=151.5)
        assert strategy.on_context(ctx2) is None

    def test_per_symbol_state_isolation(self):
        """Different symbols should maintain independent crossover state."""
        strategy = SmaCrossover()

        # AAPL: fast below slow
        ctx_aapl1 = _make_ctx("AAPL", 150.0, fast_sma=148.0, slow_sma=152.0)
        strategy.on_context(ctx_aapl1)

        # MSFT: fast above slow
        ctx_msft1 = _make_ctx("MSFT", 300.0, fast_sma=305.0, slow_sma=295.0)
        strategy.on_context(ctx_msft1)

        # AAPL: golden cross
        ctx_aapl2 = _make_ctx("AAPL", 155.0, fast_sma=153.0, slow_sma=151.0)
        signal_aapl = strategy.on_context(ctx_aapl2)
        assert signal_aapl is not None
        assert signal_aapl.direction == "long"
        assert signal_aapl.symbol == "AAPL"

        # MSFT: death cross
        ctx_msft2 = _make_ctx("MSFT", 290.0, fast_sma=292.0, slow_sma=296.0)
        signal_msft = strategy.on_context(ctx_msft2)
        assert signal_msft is not None
        assert signal_msft.direction == "close"
        assert signal_msft.symbol == "MSFT"

    def test_required_indicators_spec(self):
        """Strategy should declare correct IndicatorSpec for SMA indicators."""
        strategy = SmaCrossover()
        specs = strategy.required_indicators
        assert len(specs) == 2

        keys = {spec.key for spec in specs}
        assert "SMA_10" in keys
        assert "SMA_30" in keys

        for spec in specs:
            assert spec.name == "SMA"
            assert "period" in spec.params

    def test_custom_periods(self):
        """Custom fast_period=5, slow_period=20 should work correctly."""
        strategy = SmaCrossover(fast_period=5, slow_period=20)

        # Verify indicator specs use custom periods
        keys = {spec.key for spec in strategy.required_indicators}
        assert "SMA_5" in keys
        assert "SMA_20" in keys

        # First bar: fast below slow
        ctx1 = _make_ctx("AAPL", 150.0, fast_sma=148.0, slow_sma=152.0, fast_period=5, slow_period=20)
        assert strategy.on_context(ctx1) is None

        # Second bar: golden cross with custom periods
        ctx2 = _make_ctx("AAPL", 155.0, fast_sma=153.0, slow_sma=151.0, fast_period=5, slow_period=20)
        signal = strategy.on_context(ctx2)
        assert signal is not None
        assert signal.direction == "long"
