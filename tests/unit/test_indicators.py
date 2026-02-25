import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator, IndicatorSpec
from autotrader.indicators.engine import IndicatorEngine
from autotrader.indicators.builtin.moving_average import SMA, EMA
from autotrader.indicators.builtin.momentum import RSI
from autotrader.indicators.builtin.volatility import ATR


def _make_bars(closes: list[float], symbol: str = "AAPL") -> deque[Bar]:
    bars = deque()
    for i, c in enumerate(closes):
        bars.append(Bar(
            symbol=symbol,
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=c, high=c + 1, low=c - 1, close=c, volume=100.0,
        ))
    return bars


class TestSMA:
    def test_sma_basic(self):
        sma = SMA(period=3)
        bars = _make_bars([10.0, 20.0, 30.0])
        result = sma.calculate(bars)
        assert result == pytest.approx(20.0)

    def test_sma_warmup(self):
        sma = SMA(period=5)
        assert sma.warmup_period == 5
        bars = _make_bars([10.0, 20.0])  # not enough
        result = sma.calculate(bars)
        assert result is None


class TestEMA:
    def test_ema_basic(self):
        ema = EMA(period=3)
        bars = _make_bars([10.0, 20.0, 30.0, 40.0, 50.0])
        result = ema.calculate(bars)
        assert isinstance(result, float)
        assert result > 30.0  # EMA weights recent values more


class TestRSI:
    def test_rsi_all_gains(self):
        rsi = RSI(period=14)
        bars = _make_bars([float(i) for i in range(1, 20)])
        result = rsi.calculate(bars)
        assert result is not None
        assert result > 90.0  # all upward movement

    def test_rsi_warmup(self):
        rsi = RSI(period=14)
        assert rsi.warmup_period == 15  # period + 1
        bars = _make_bars([10.0, 20.0])
        assert rsi.calculate(bars) is None


class TestATR:
    def test_atr_basic(self):
        atr = ATR(period=3)
        bars = _make_bars([10.0, 12.0, 11.0, 13.0, 12.0])
        result = atr.calculate(bars)
        assert result is not None
        assert result > 0


class TestIndicatorEngine:
    def test_register_and_compute(self):
        engine = IndicatorEngine()
        engine.register(IndicatorSpec("SMA", {"period": 3}))
        bars = _make_bars([10.0, 20.0, 30.0])
        results = engine.compute(bars)
        assert "SMA_3" in results
        assert results["SMA_3"] == pytest.approx(20.0)

    def test_compute_multiple(self):
        engine = IndicatorEngine()
        engine.register(IndicatorSpec("SMA", {"period": 3}))
        engine.register(IndicatorSpec("RSI", {"period": 14}))
        bars = _make_bars([float(i) for i in range(1, 20)])
        results = engine.compute(bars)
        assert "SMA_3" in results
        assert "RSI_14" in results
