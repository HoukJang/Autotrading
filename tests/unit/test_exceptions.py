"""Unit tests for core exceptions."""
import pytest
from autotrader.core.exceptions import (
    AutoTraderError,
    ConfigError,
    BrokerError,
    ConnectionError,
    OrderError,
    RiskLimitError,
    DataError,
    StrategyError,
)


class TestExceptionHierarchy:
    def test_exception_hierarchy(self):
        assert issubclass(ConfigError, AutoTraderError)
        assert issubclass(BrokerError, AutoTraderError)
        assert issubclass(ConnectionError, BrokerError)
        assert issubclass(OrderError, BrokerError)
        assert issubclass(RiskLimitError, AutoTraderError)
        assert issubclass(DataError, AutoTraderError)
        assert issubclass(StrategyError, AutoTraderError)

    def test_base_exception_is_exception(self):
        assert issubclass(AutoTraderError, Exception)


class TestAutoTraderError:
    def test_base_exception_message(self):
        err = AutoTraderError("Something went wrong")
        assert str(err) == "Something went wrong"


class TestConfigError:
    def test_config_error_message(self):
        err = ConfigError("Invalid API key configuration")
        assert str(err) == "Invalid API key configuration"


class TestBrokerError:
    def test_broker_error_message(self):
        err = BrokerError("Broker API error")
        assert str(err) == "Broker API error"


class TestConnectionError:
    def test_connection_error_message(self):
        err = ConnectionError("Alpaca", "Connection timeout after 30s")
        assert "Alpaca" in str(err)
        assert "Connection timeout after 30s" in str(err)
        assert err.broker == "Alpaca"
        assert err.reason == "Connection timeout after 30s"

    def test_connection_error_various_brokers(self):
        err = ConnectionError("Interactive Brokers", "Network unreachable")
        assert err.broker == "Interactive Brokers"

    def test_connection_error_format(self):
        err = ConnectionError("Alpaca", "timeout")
        assert str(err) == "[Alpaca] Connection failed: timeout"


class TestOrderError:
    def test_order_error_message(self):
        err = OrderError("AAPL", "insufficient buying power")
        assert "AAPL" in str(err)
        assert "insufficient buying power" in str(err)
        assert err.symbol == "AAPL"
        assert err.reason == "insufficient buying power"

    def test_order_error_various_symbols(self):
        err = OrderError("BTC/USD", "invalid quantity")
        assert err.symbol == "BTC/USD"

    def test_order_error_format(self):
        err = OrderError("AAPL", "order rejected")
        assert str(err) == "[AAPL] Order error: order rejected"


class TestRiskLimitError:
    def test_risk_limit_error_message(self):
        err = RiskLimitError("max_position_size", "Position exceeds 50% of portfolio")
        assert "max_position_size" in str(err)
        assert "Position exceeds 50% of portfolio" in str(err)
        assert err.rule == "max_position_size"
        assert err.detail == "Position exceeds 50% of portfolio"

    def test_risk_limit_error_format(self):
        err = RiskLimitError("daily_loss_limit", "Daily loss limit of $5000 reached")
        assert str(err) == "Risk limit [daily_loss_limit]: Daily loss limit of $5000 reached"

    def test_risk_limit_error_various_rules(self):
        err = RiskLimitError("sector_concentration", "Technology sector at 40% max")
        assert err.rule == "sector_concentration"


class TestDataError:
    def test_data_error_message(self):
        err = DataError("Failed to fetch historical data for AAPL")
        assert str(err) == "Failed to fetch historical data for AAPL"


class TestStrategyError:
    def test_strategy_error_message(self):
        err = StrategyError("Strategy initialization failed: missing required indicator")
        assert str(err) == "Strategy initialization failed: missing required indicator"


class TestExceptionInstances:
    def test_raise_config_error(self):
        with pytest.raises(ConfigError):
            raise ConfigError("bad config")

    def test_raise_connection_error(self):
        with pytest.raises(ConnectionError):
            raise ConnectionError("Alpaca", "timeout")

    def test_raise_order_error(self):
        with pytest.raises(OrderError):
            raise OrderError("AAPL", "rejected")

    def test_raise_risk_limit_error(self):
        with pytest.raises(RiskLimitError):
            raise RiskLimitError("max_position", "limit exceeded")

    def test_raise_data_error(self):
        with pytest.raises(DataError):
            raise DataError("bad data")

    def test_raise_strategy_error(self):
        with pytest.raises(StrategyError):
            raise StrategyError("strategy failed")

    def test_catch_as_autotrader_error(self):
        with pytest.raises(AutoTraderError):
            raise ConfigError("test")

    def test_catch_broker_error_as_autotrader_error(self):
        with pytest.raises(AutoTraderError):
            raise ConnectionError("Alpaca", "timeout")
