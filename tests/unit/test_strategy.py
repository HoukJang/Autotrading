import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy
from autotrader.strategy.registry import StrategyRegistry
from autotrader.strategy.engine import StrategyEngine


class DummyStrategy(Strategy):
    name = "dummy"
    required_indicators = [IndicatorSpec("SMA", {"period": 3})]

    def on_context(self, ctx: MarketContext) -> Signal | None:
        sma = ctx.indicators.get("SMA_3")
        if sma and ctx.bar.close > sma:
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="long", strength=0.5)
        return None


def _make_context(close: float, sma: float) -> MarketContext:
    bar = Bar("AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc), close, close + 1, close - 1, close, 100)
    return MarketContext(symbol="AAPL", bar=bar, indicators={"SMA_3": sma}, history=deque([bar]))


class TestStrategy:
    def test_strategy_generates_signal(self):
        strat = DummyStrategy()
        ctx = _make_context(close=105.0, sma=100.0)
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "long"

    def test_strategy_no_signal(self):
        strat = DummyStrategy()
        ctx = _make_context(close=95.0, sma=100.0)
        sig = strat.on_context(ctx)
        assert sig is None


class TestRegistry:
    def test_register_and_get(self):
        reg = StrategyRegistry()
        strat = DummyStrategy()
        reg.register(strat)
        assert reg.get("dummy") is strat
        assert len(reg.all()) == 1

    def test_duplicate_raises(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy())
        with pytest.raises(ValueError):
            reg.register(DummyStrategy())


class TestStrategyEngine:
    async def test_process_context(self):
        engine = StrategyEngine()
        engine.add_strategy(DummyStrategy())
        ctx = _make_context(close=105.0, sma=100.0)
        signals = await engine.process(ctx)
        assert len(signals) == 1
        assert signals[0].direction == "long"

    async def test_no_signals(self):
        engine = StrategyEngine()
        engine.add_strategy(DummyStrategy())
        ctx = _make_context(close=95.0, sma=100.0)
        signals = await engine.process(ctx)
        assert signals == []
