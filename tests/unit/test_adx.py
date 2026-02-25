import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.indicators.builtin.trend import ADX


def _make_bar(
    close: float,
    high: float,
    low: float,
    minute: int,
    open_: float | None = None,
    symbol: str = "TEST",
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 1, 10, minute, tzinfo=timezone.utc),
        open=open_ if open_ is not None else close,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _make_trending_bars(count: int, start: float = 100.0, step: float = 2.0) -> deque[Bar]:
    """Create bars with a strong upward trend (high > prev high, low > prev low)."""
    bars: deque[Bar] = deque()
    for i in range(count):
        price = start + i * step
        bars.append(_make_bar(
            close=price,
            high=price + 1.0,
            low=price - 1.0,
            minute=i,
        ))
    return bars


def _make_oscillating_bars(count: int, center: float = 100.0, amplitude: float = 5.0) -> deque[Bar]:
    """Create bars oscillating up and down around a center (range-bound)."""
    bars: deque[Bar] = deque()
    for i in range(count):
        offset = amplitude if i % 2 == 0 else -amplitude
        price = center + offset
        bars.append(_make_bar(
            close=price,
            high=price + 1.0,
            low=price - 1.0,
            minute=i,
        ))
    return bars


class TestADX:
    def test_returns_none_insufficient_bars(self):
        adx = ADX(period=14)
        bars = _make_trending_bars(28)  # Need 29, supply 28
        assert adx.calculate(bars) is None

    def test_warmup_period_value(self):
        assert ADX(14).warmup_period == 29
        assert ADX(7).warmup_period == 15

    def test_strong_trend_up(self):
        bars = _make_trending_bars(50, start=100.0, step=2.0)
        adx = ADX(period=14)
        result = adx.calculate(bars)
        assert result is not None
        assert result > 25.0, f"Strong trend should give ADX > 25, got {result}"

    def test_range_bound_low_adx(self):
        bars = _make_oscillating_bars(50, center=100.0, amplitude=5.0)
        adx = ADX(period=14)
        result = adx.calculate(bars)
        assert result is not None
        assert result < 25.0, f"Range-bound should give ADX < 25, got {result}"

    def test_output_range(self):
        bars = _make_trending_bars(50)
        adx = ADX(period=14)
        result = adx.calculate(bars)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_custom_period(self):
        adx = ADX(period=7)
        bars = _make_trending_bars(30)
        result = adx.calculate(bars)
        assert result is not None
        assert isinstance(result, float)

    def test_exact_warmup_returns_value(self):
        adx = ADX(period=14)
        bars = _make_trending_bars(29)  # Exactly warmup_period
        result = adx.calculate(bars)
        assert result is not None
