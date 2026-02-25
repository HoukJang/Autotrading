import pytest
from autotrader.core.types import Signal, AccountInfo, Position
from autotrader.core.config import RiskConfig
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer


@pytest.fixture
def config():
    return RiskConfig(
        max_position_pct=0.10,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.05,
        max_open_positions=3,
    )


@pytest.fixture
def account():
    return AccountInfo(
        account_id="test", buying_power=100_000.0,
        portfolio_value=100_000.0, cash=100_000.0, equity=100_000.0,
    )


class TestRiskManager:
    def test_approve_valid_signal(self, config, account):
        rm = RiskManager(config)
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=0.8)
        assert rm.validate(sig, account, positions=[]) is True

    def test_reject_too_many_positions(self, config, account):
        rm = RiskManager(config)
        existing = [
            Position(symbol=s, quantity=10, avg_entry_price=100, market_value=1000, unrealized_pnl=0, side="long")
            for s in ["AAPL", "MSFT", "GOOGL"]
        ]
        sig = Signal(strategy="test", symbol="TSLA", direction="long", strength=0.8)
        assert rm.validate(sig, account, positions=existing) is False

    def test_allow_close_even_at_limit(self, config, account):
        rm = RiskManager(config)
        existing = [
            Position(symbol=s, quantity=10, avg_entry_price=100, market_value=1000, unrealized_pnl=0, side="long")
            for s in ["AAPL", "MSFT", "GOOGL"]
        ]
        sig = Signal(strategy="test", symbol="AAPL", direction="close", strength=1.0)
        assert rm.validate(sig, account, positions=existing) is True

    def test_reject_daily_loss_exceeded(self, config):
        rm = RiskManager(config)
        rm.record_pnl(-2500.0)  # > 2% of 100k
        account = AccountInfo("test", 97_500, 97_500, 97_500, 97_500)
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=0.5)
        assert rm.validate(sig, account, positions=[]) is False


class TestPositionSizer:
    def test_size_by_risk_pct(self, config, account):
        sizer = PositionSizer(config)
        qty = sizer.calculate(price=150.0, account=account)
        max_value = account.equity * config.max_position_pct  # 10000
        expected_qty = int(max_value / 150.0)  # 66
        assert qty == expected_qty

    def test_zero_price(self, config, account):
        sizer = PositionSizer(config)
        assert sizer.calculate(price=0.0, account=account) == 0
