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
    async def test_submit_market_order(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "AAPL"
        mock_order.status = "accepted"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order
        mock_client_cls.return_value = mock_client

        await adapter.connect()
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await adapter.submit_order(order)
        assert result.order_id == "order-123"
        assert result.status == "accepted"
