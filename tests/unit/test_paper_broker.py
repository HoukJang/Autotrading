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


class TestPaperBrokerShort:
    async def test_short_sell_creates_short_position(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        # Sell without existing long = open short
        order = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        result = await broker.submit_order(order)
        assert result.status == "filled"
        assert result.filled_qty == 10
        assert result.filled_price == 100.0
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].side == "short"
        assert positions[0].quantity == 10
        assert positions[0].avg_entry_price == 100.0

    async def test_buy_to_cover_closes_short(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        # Open short
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        # Buy to cover
        broker.set_price("AAPL", 90.0)
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await broker.submit_order(buy)
        assert result.status == "filled"
        positions = await broker.get_positions()
        assert len(positions) == 0

    async def test_short_pnl_positive_when_price_drops(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        # Price drops
        broker.set_price("AAPL", 90.0)
        positions = await broker.get_positions()
        assert positions[0].unrealized_pnl == 100.0  # (100-90)*10 = +100

    async def test_short_pnl_negative_when_price_rises(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        broker.set_price("AAPL", 110.0)
        positions = await broker.get_positions()
        assert positions[0].unrealized_pnl == -100.0  # (100-110)*10 = -100

    async def test_equity_includes_short_unrealized(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        # Cash after short: 10000 + 1000 (proceeds) = 11000
        # Short liability at same price: 1000
        # Equity: 11000 - 1000 = 10000 (unchanged initially)
        account = await broker.get_account()
        assert account.equity == 10_000.0

        # Price drops to 90
        broker.set_price("AAPL", 90.0)
        account = await broker.get_account()
        # Equity: 11000 - 900 = 10100 (+100 profit)
        assert account.equity == 10_100.0

    async def test_sell_closes_long_before_shorting(self):
        """If long exists, sell first reduces long; excess does NOT auto-short."""
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        # Open long 10 shares
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(buy)
        # Sell exactly 10 (close long entirely)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        result = await broker.submit_order(sell)
        assert result.status == "filled"
        positions = await broker.get_positions()
        assert len(positions) == 0

    async def test_partial_cover_short(self):
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        # Partial cover
        buy = Order(symbol="AAPL", side="buy", quantity=5, order_type="market")
        result = await broker.submit_order(buy)
        assert result.status == "filled"
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 5
        assert positions[0].side == "short"

    async def test_short_cash_accounting(self):
        """Opening short adds proceeds to cash, covering subtracts."""
        broker = PaperBroker(10_000.0)
        await broker.connect()
        broker.set_price("AAPL", 100.0)
        # Short: proceeds = 100*10 = 1000 added to cash
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        await broker.submit_order(sell)
        assert broker._cash == 11_000.0  # 10000 + 1000
        # Cover at 90: cost = 90*10 = 900 deducted
        broker.set_price("AAPL", 90.0)
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(buy)
        assert broker._cash == 10_100.0  # 11000 - 900
