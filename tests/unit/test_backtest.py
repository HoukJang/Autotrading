import pytest
from collections import deque
from datetime import datetime, timezone, timedelta

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.core.config import RiskConfig
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy
from autotrader.backtest.engine import BacktestEngine


class BuyAndHold(Strategy):
    name = "buy_and_hold"
    required_indicators = []
    _bought = False

    def on_context(self, ctx: MarketContext) -> Signal | None:
        if not self._bought:
            self._bought = True
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="long", strength=1.0)
        return None


def _make_bars(n: int, start_price: float = 100.0, trend: float = 1.0) -> list[Bar]:
    bars = []
    price = start_price
    for i in range(n):
        bars.append(Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=price, high=price + 1, low=price - 1, close=price + trend, volume=1000,
        ))
        price += trend
    return bars


class TestBacktestEngine:
    def test_run_backtest(self):
        bars = _make_bars(20, start_price=100.0, trend=0.5)
        engine = BacktestEngine(
            initial_balance=100_000.0,
            risk_config=RiskConfig(),
        )
        engine.add_strategy(BuyAndHold())
        result = engine.run(bars)
        assert result.total_trades >= 1
        assert result.final_equity > 100_000.0  # price went up

    def test_backtest_metrics(self):
        bars = _make_bars(50, start_price=100.0, trend=0.5)
        engine = BacktestEngine(initial_balance=100_000.0, risk_config=RiskConfig())
        engine.add_strategy(BuyAndHold())
        result = engine.run(bars)
        assert "win_rate" in result.metrics
        assert "profit_factor" in result.metrics
