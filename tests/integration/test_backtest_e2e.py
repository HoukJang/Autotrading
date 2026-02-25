"""End-to-end backtest integration test.

Verifies that all modules work together: strategy generates signals,
indicators compute values, risk manager validates, simulator executes,
and the engine produces valid results.
"""
import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.core.config import RiskConfig
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy
from autotrader.backtest.engine import BacktestEngine


class SMAMomentum(Strategy):
    """Strategy that buys when price is above SMA, closes when below."""
    name = "sma_momentum"
    required_indicators = [IndicatorSpec(name="SMA", params={"period": 5})]
    _in_position = False

    def on_context(self, ctx: MarketContext) -> Signal | None:
        sma_val = ctx.indicators.get("SMA_5")
        if sma_val is None:
            return None

        if not self._in_position and ctx.bar.close > sma_val:
            self._in_position = True
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="long", strength=0.8)
        elif self._in_position and ctx.bar.close < sma_val:
            self._in_position = False
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="close", strength=1.0)
        return None


def _make_wave_bars(n: int) -> list[Bar]:
    """Generate bars with up-down wave pattern to trigger buy/sell."""
    bars = []
    for i in range(n):
        # Oscillating price: goes up for 10 bars, down for 10 bars
        cycle = i % 20
        if cycle < 10:
            price = 100.0 + cycle * 2.0
        else:
            price = 100.0 + (20 - cycle) * 2.0
        bars.append(Bar(
            symbol="TEST",
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=price - 0.5, high=price + 1, low=price - 1, close=price, volume=1000,
        ))
    return bars


class TestBacktestE2E:
    def test_full_backtest_with_indicators(self):
        """Full pipeline: bars -> indicators -> strategy -> risk -> execution -> metrics."""
        bars = _make_wave_bars(60)
        engine = BacktestEngine(initial_balance=100_000.0, risk_config=RiskConfig())
        engine.add_strategy(SMAMomentum())
        result = engine.run(bars)

        # Should have executed trades (both opens and closes)
        assert result.total_trades >= 2
        # Equity curve should have entries for each bar + initial
        assert len(result.equity_curve) == len(bars) + 1
        # Metrics should have standard keys
        assert "win_rate" in result.metrics
        assert "profit_factor" in result.metrics
        assert "total_pnl" in result.metrics
        assert "max_drawdown" in result.metrics

    def test_backtest_preserves_initial_on_no_trades(self):
        """With only 2 bars, SMA(5) never fires, so no trades happen."""
        bars = _make_wave_bars(2)
        engine = BacktestEngine(initial_balance=50_000.0, risk_config=RiskConfig())
        engine.add_strategy(SMAMomentum())
        result = engine.run(bars)

        assert result.total_trades == 0
        assert result.final_equity == 50_000.0

    def test_backtest_equity_curve_monotonic_start(self):
        """Equity curve starts at initial balance."""
        bars = _make_wave_bars(30)
        engine = BacktestEngine(initial_balance=100_000.0, risk_config=RiskConfig())
        engine.add_strategy(SMAMomentum())
        result = engine.run(bars)

        assert result.equity_curve[0] == 100_000.0


class TestPaperBrokerE2E:
    """Integration test for PaperBroker with full order lifecycle."""

    async def test_full_order_lifecycle(self):
        from autotrader.broker.paper import PaperBroker
        from autotrader.core.types import Order

        broker = PaperBroker(initial_balance=100_000.0)
        await broker.connect()
        assert broker.connected

        # Set price and buy
        broker.set_price("AAPL", 150.0)
        buy_order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await broker.submit_order(buy_order)
        assert result.status == "filled"
        assert result.filled_qty == 10

        # Check position exists
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

        # Check account
        account = await broker.get_account()
        assert account.cash == 100_000.0 - 150.0 * 10

        # Sell
        broker.set_price("AAPL", 160.0)
        sell_order = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        result = await broker.submit_order(sell_order)
        assert result.status == "filled"

        # Position should be closed
        positions = await broker.get_positions()
        assert len(positions) == 0

        # Profit = (160-150)*10 = 100
        account = await broker.get_account()
        assert account.equity == 100_100.0

        await broker.disconnect()


class TestAutoTraderE2E:
    """Integration test for AutoTrader initialization."""

    def test_autotrader_creates_all_components(self):
        from autotrader.main import AutoTrader
        from autotrader.core.config import Settings

        app = AutoTrader(Settings())
        assert app._broker is not None
        assert app._indicator_engine is not None
        assert app._strategy_engine is not None
        assert app._risk_manager is not None
        assert app._bus is not None

    async def test_autotrader_start_stop(self):
        from autotrader.main import AutoTrader
        from autotrader.core.config import Settings

        app = AutoTrader(Settings())
        await app.start()
        assert app._broker.connected
        await app.stop()
        assert not app._broker.connected
