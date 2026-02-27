import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autotrader.core.types import Order
from autotrader.broker.alpaca_adapter import AlpacaAdapter


@pytest.fixture
def adapter():
    return AlpacaAdapter(api_key="test_key", secret_key="test_secret", paper=True)


class TestAlpacaAdapter:
    def test_init_paper_mode(self, adapter):
        assert adapter._paper is True

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_connect(self, mock_client_cls, adapter):
        await adapter.connect()
        mock_client_cls.assert_called_once_with("test_key", "test_secret", paper=True)
        assert adapter.connected

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_get_account(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_account = MagicMock()
        mock_account.id = "test-id"
        mock_account.buying_power = "100000.0"
        mock_account.portfolio_value = "100000.0"
        mock_account.cash = "100000.0"
        mock_account.equity = "100000.0"
        mock_client.get_account.return_value = mock_account
        mock_client_cls.return_value = mock_client

        await adapter.connect()
        account = await adapter.get_account()
        assert account.buying_power == 100_000.0

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_submit_market_order_filled(self, mock_client_cls, adapter):
        from alpaca.trading.enums import OrderStatus

        mock_client = MagicMock()
        # submit_order returns "accepted" initially
        mock_submit = MagicMock()
        mock_submit.id = "order-123"
        mock_submit.symbol = "AAPL"
        mock_submit.status = OrderStatus.ACCEPTED
        mock_submit.filled_qty = "0"
        mock_submit.filled_avg_price = None
        mock_client.submit_order.return_value = mock_submit

        # get_order_by_id returns "filled" after polling
        mock_filled = MagicMock()
        mock_filled.id = "order-123"
        mock_filled.symbol = "AAPL"
        mock_filled.status = OrderStatus.FILLED
        mock_filled.filled_qty = "10"
        mock_filled.filled_avg_price = "150.50"
        mock_client.get_order_by_id.return_value = mock_filled
        mock_client_cls.return_value = mock_client

        await adapter.connect()
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await adapter.submit_order(order)
        assert result.order_id == "order-123"
        assert result.status == "filled"
        assert result.filled_qty == 10.0
        assert result.filled_price == 150.50
