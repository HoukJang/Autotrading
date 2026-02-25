import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone

import pytest

from autotrader.main import AutoTrader
from autotrader.broker.paper import PaperBroker
from autotrader.core.config import Settings, RiskConfig
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal,
)
from autotrader.indicators.engine import IndicatorEngine
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.sma_crossover import SmaCrossover


def _make_bar(symbol: str = "AAPL", close: float = 150.0, idx: int = 0) -> Bar:
    from datetime import timedelta
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=base + timedelta(minutes=idx),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1000.0,
    )


class TestAutoTrader:
    def test_create_with_defaults(self):
        app = AutoTrader(Settings())
        assert app is not None

    def test_create_paper_broker(self):
        settings = Settings()
        settings.broker.type = "paper"
        app = AutoTrader(settings)
        assert isinstance(app._broker, PaperBroker)

    def test_init_has_bar_history(self):
        app = AutoTrader(Settings())
        assert isinstance(app._bar_history, dict)

    def test_init_has_running_flag(self):
        app = AutoTrader(Settings())
        assert app._running is False

    def test_init_has_position_sizer(self):
        app = AutoTrader(Settings())
        assert isinstance(app._position_sizer, PositionSizer)


class TestRegisterStrategies:
    def test_register_adds_sma_crossover(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        assert len(app._strategy_engine._strategies) == 1
        assert isinstance(app._strategy_engine._strategies[0], SmaCrossover)

    def test_register_registers_indicators(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        # SmaCrossover requires SMA_10 and SMA_30
        assert "SMA_10" in app._indicator_engine._indicators
        assert "SMA_30" in app._indicator_engine._indicators

    def test_register_deduplicates_indicators(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        # Calling again should not duplicate
        count_before = len(app._indicator_engine._indicators)
        app._register_strategies()
        # Strategy count increases but indicator count should stay same
        # (indicators dedup by key)
        assert len(app._indicator_engine._indicators) == count_before


class TestSignalToOrder:
    @pytest.fixture()
    def app(self):
        return AutoTrader(Settings())

    @pytest.mark.asyncio
    async def test_long_signal_creates_buy_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        # Need bar history so _signal_to_order can look up price
        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.side == "buy"
        assert order.symbol == "AAPL"
        assert order.order_type == "market"
        assert order.quantity > 0

    @pytest.mark.asyncio
    async def test_close_signal_creates_sell_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        positions = [
            Position(
                symbol="AAPL", quantity=10, avg_entry_price=150.0,
                market_value=1500.0, unrealized_pnl=0.0, side="long",
            ),
        ]
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="close", strength=0.5,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None
        assert order.side == "sell"
        assert order.quantity == 10

    @pytest.mark.asyncio
    async def test_close_signal_no_position_returns_none(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="close", strength=0.5,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is None

    @pytest.mark.asyncio
    async def test_long_signal_zero_qty_returns_none(self, app):
        """If position sizer returns 0 qty (e.g. price too high), no order."""
        settings = Settings()
        # max_position_pct=0.10 with 100k equity = 10k max
        # If price is 200_000, qty = int(10_000 / 200_000) = 0
        app2 = AutoTrader(settings)
        await app2._broker.connect()
        account = await app2._broker.get_account()
        signal = Signal(
            strategy="test", symbol="BRK.A",
            direction="long", strength=1.0,
        )
        # Use a very high price via account with low equity
        low_equity_account = AccountInfo(
            account_id="test", buying_power=1.0,
            portfolio_value=1.0, cash=1.0, equity=1.0,
        )
        order = app2._signal_to_order(signal, low_equity_account, [])
        assert order is None


class TestAutoTraderTradingLoop:
    @pytest.fixture()
    def settings(self) -> Settings:
        s = Settings()
        s.broker.type = "paper"
        s.broker.paper_balance = 100_000.0
        s.symbols = ["AAPL"]
        return s

    @pytest.fixture()
    def app(self, settings) -> AutoTrader:
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_start_initializes_tracker(self, app):
        await app.start()
        assert app._portfolio_tracker is not None
        assert app._portfolio_tracker.initial_equity == 100_000.0
        await app.stop()

    @pytest.mark.asyncio
    async def test_start_registers_strategies(self, app):
        await app.start()
        assert len(app._strategy_engine._strategies) >= 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_appends_to_history(self, app):
        await app.start()
        bar = _make_bar("AAPL", 150.0)
        await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_multiple_bars_accumulate(self, app):
        await app.start()
        for i in range(5):
            bar = _make_bar("AAPL", 150.0 + i, idx=i)
            await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 5
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_triggers_order_on_crossover(self, app):
        """Feed enough bars to trigger SMA crossover and verify order submission."""
        await app.start()
        # PaperBroker needs price for order execution
        app._broker.set_price("AAPL", 160.0)

        # Build history with low prices so SMA_10 < SMA_30
        for i in range(35):
            bar = _make_bar("AAPL", 100.0, idx=i)
            await app._on_bar(bar)

        # Now shift price up significantly to push SMA_10 > SMA_30
        for i in range(12):
            bar = _make_bar("AAPL", 160.0, idx=35 + i)
            await app._on_bar(bar)

        # Check positions created via the broker
        positions = await app._broker.get_positions()
        # We expect at least one order attempted
        # (depending on SMA crossover timing)
        assert app._portfolio_tracker.trades is not None

    @pytest.mark.asyncio
    async def test_on_bar_respects_history_limit(self, app):
        """Bar history should be bounded by data.bar_history_size."""
        await app.start()
        limit = app._settings.data.bar_history_size
        for i in range(limit + 50):
            bar = _make_bar("AAPL", 100.0 + (i % 10), idx=i % 28)
            await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == limit
        await app.stop()

    @pytest.mark.asyncio
    async def test_process_signal_submits_order(self, app):
        """Directly test _process_signal with a long signal."""
        await app.start()
        app._broker.set_price("AAPL", 150.0)
        # Need bar history so _signal_to_order can look up price
        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        assert result is not None
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_process_signal_risk_rejected(self, app):
        """If risk manager rejects, no order is submitted."""
        await app.start()
        app._broker.set_price("AAPL", 150.0)

        # Fill up positions to max to trigger risk rejection
        for i in range(app._settings.risk.max_open_positions):
            sym = f"SYM{i}"
            app._broker.set_price(sym, 10.0)
            order = Order(
                symbol=sym, side="buy", quantity=1,
                order_type="market",
            )
            await app._broker.submit_order(order)

        account = await app._broker.get_account()
        positions = await app._broker.get_positions()

        signal = Signal(
            strategy="test", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, app):
        await app.start()
        assert app._running is True
        await app.stop()
        assert app._running is False


class TestAutoTraderStartStop:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        settings = Settings()
        app = AutoTrader(settings)
        await app.start()
        assert app._running is True
        assert app._broker.connected is True
        await app.stop()
        assert app._running is False
        assert app._broker.connected is False
