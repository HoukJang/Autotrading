import pytest
from unittest.mock import patch, AsyncMock

from autotrader.main import AutoTrader
from autotrader.core.config import Settings


class TestAutoTrader:
    def test_create_with_defaults(self):
        app = AutoTrader(Settings())
        assert app is not None

    def test_create_paper_broker(self):
        settings = Settings()
        settings.broker.type = "paper"
        app = AutoTrader(settings)
        from autotrader.broker.paper import PaperBroker
        assert isinstance(app._broker, PaperBroker)
