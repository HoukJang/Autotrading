"""Unit tests for core types."""
import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar, Signal, Order, MarketContext, OrderResult, Position, AccountInfo


class TestBar:
    def test_create_bar(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
        )
        assert bar.symbol == "AAPL"
        assert bar.close == 151.0

    def test_bar_midpoint(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=148.0, close=151.0, volume=1000.0,
        )
        assert bar.midpoint == 150.0  # (high + low) / 2

    def test_bar_is_immutable(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=148.0, close=151.0, volume=1000.0,
        )
        with pytest.raises(AttributeError):
            bar.close = 152.0


class TestSignal:
    def test_create_long_signal(self):
        sig = Signal(strategy="momentum", symbol="AAPL", direction="long", strength=0.8)
        assert sig.direction == "long"
        assert 0.0 <= sig.strength <= 1.0

    def test_signal_strength_clamped(self):
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=1.5)
        assert sig.strength == 1.0

    def test_signal_strength_clamped_negative(self):
        sig = Signal(strategy="test", symbol="AAPL", direction="short", strength=-0.5)
        assert sig.strength == 0.0

    def test_signal_with_metadata(self):
        meta = {"score": 42, "confidence": 0.95}
        sig = Signal(strategy="ml", symbol="BTC", direction="long", strength=0.7, metadata=meta)
        assert sig.metadata == meta

    def test_signal_is_immutable(self):
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=0.5)
        with pytest.raises(AttributeError):
            sig.strength = 0.8


class TestOrder:
    def test_market_order(self):
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        assert order.limit_price is None
        assert order.stop_price is None
        assert order.time_in_force == "day"

    def test_limit_order(self):
        order = Order(symbol="AAPL", side="buy", quantity=5, order_type="limit", limit_price=150.0)
        assert order.limit_price == 150.0

    def test_stop_order(self):
        order = Order(symbol="AAPL", side="sell", quantity=10, order_type="stop", stop_price=145.0)
        assert order.stop_price == 145.0

    def test_stop_limit_order(self):
        order = Order(
            symbol="AAPL", side="buy", quantity=5, order_type="stop_limit",
            limit_price=150.0, stop_price=149.0
        )
        assert order.limit_price == 150.0
        assert order.stop_price == 149.0

    def test_order_time_in_force(self):
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market", time_in_force="gtc")
        assert order.time_in_force == "gtc"

    def test_order_is_immutable(self):
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        with pytest.raises(AttributeError):
            order.quantity = 20


class TestOrderResult:
    def test_order_result_filled(self):
        result = OrderResult(
            order_id="123", symbol="AAPL", status="filled",
            filled_qty=10.0, filled_price=150.5
        )
        assert result.status == "filled"
        assert result.filled_qty == 10.0

    def test_order_result_partially_filled(self):
        result = OrderResult(
            order_id="124", symbol="AAPL", status="partially_filled",
            filled_qty=5.0, filled_price=150.5
        )
        assert result.status == "partially_filled"
        assert result.filled_qty == 5.0

    def test_order_result_is_immutable(self):
        result = OrderResult(order_id="123", symbol="AAPL", status="accepted")
        with pytest.raises(AttributeError):
            result.status = "filled"


class TestPosition:
    def test_long_position(self):
        pos = Position(
            symbol="AAPL", quantity=100.0, avg_entry_price=150.0,
            market_value=15250.0, unrealized_pnl=250.0, side="long"
        )
        assert pos.side == "long"
        assert pos.quantity == 100.0

    def test_short_position(self):
        pos = Position(
            symbol="AAPL", quantity=50.0, avg_entry_price=150.0,
            market_value=7600.0, unrealized_pnl=-100.0, side="short"
        )
        assert pos.side == "short"

    def test_position_is_immutable(self):
        pos = Position(
            symbol="AAPL", quantity=100.0, avg_entry_price=150.0,
            market_value=15250.0, unrealized_pnl=250.0, side="long"
        )
        with pytest.raises(AttributeError):
            pos.quantity = 200.0


class TestAccountInfo:
    def test_account_info_creation(self):
        acc = AccountInfo(
            account_id="ACC123", buying_power=10000.0,
            portfolio_value=25000.0, cash=5000.0, equity=20000.0
        )
        assert acc.account_id == "ACC123"
        assert acc.buying_power == 10000.0

    def test_account_info_is_immutable(self):
        acc = AccountInfo(
            account_id="ACC123", buying_power=10000.0,
            portfolio_value=25000.0, cash=5000.0, equity=20000.0
        )
        with pytest.raises(AttributeError):
            acc.cash = 6000.0


class TestMarketContext:
    def test_create_context(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
        )
        ctx = MarketContext(symbol="AAPL", bar=bar, indicators={"SMA_20": 149.5}, history=deque([bar]))
        assert ctx.indicators["SMA_20"] == 149.5
        assert len(ctx.history) == 1

    def test_context_with_nested_indicators(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
        )
        indicators = {
            "SMA_20": 149.5,
            "BB": {"upper": 152.0, "middle": 150.0, "lower": 148.0}
        }
        ctx = MarketContext(symbol="AAPL", bar=bar, indicators=indicators, history=deque([bar]))
        assert ctx.indicators["BB"]["upper"] == 152.0

    def test_context_history_deque(self):
        bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
                open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
            ),
            Bar(
                symbol="AAPL",
                timestamp=datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc),
                open=151.0, high=153.0, low=150.0, close=152.0, volume=1100.0,
            ),
        ]
        ctx = MarketContext(symbol="AAPL", bar=bars[1], indicators={}, history=deque(bars))
        assert len(ctx.history) == 2
        assert ctx.history[0].close == 151.0
        assert ctx.history[1].close == 152.0
