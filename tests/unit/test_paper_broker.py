import pytest
from autotrader.core.types import Order
from autotrader.broker.paper import PaperBroker


@pytest.fixture
def broker():
    return PaperBroker(initial_balance=100_000.0)


class TestPaperBroker:
    async def test_connect_disconnect(self, broker):
        await broker.connect()
        assert broker.connected
        await broker.disconnect()
        assert not broker.connected

    async def test_get_account(self, broker):
        await broker.connect()
        account = await broker.get_account()
        assert account.cash == 100_000.0
        assert account.equity == 100_000.0

    async def test_submit_market_buy(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await broker.submit_order(order)
        assert result.status == "filled"
        assert result.filled_qty == 10
        assert result.filled_price == 150.0

    async def test_positions_after_buy(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(order)
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

    async def test_submit_market_sell(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(buy)

        broker.set_price("AAPL", 155.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        result = await broker.submit_order(sell)
        assert result.status == "filled"

        account = await broker.get_account()
        assert account.cash == 100_000.0 + (155.0 - 150.0) * 10

    async def test_cancel_order(self, broker):
        await broker.connect()
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=100.0)
        result = await broker.submit_order(order)
        cancelled = await broker.cancel_order(result.order_id)
        assert cancelled is True

    async def test_insufficient_buying_power(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10_000, order_type="market")
        result = await broker.submit_order(order)
        assert result.status == "rejected"
