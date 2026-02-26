"""Unit tests for core configuration module."""
import pytest
from pathlib import Path

from autotrader.core.config import Settings, load_settings


def test_load_default_config(tmp_path):
    """Test loading configuration from YAML file."""
    yaml_content = """
system:
  name: "TestTrader"
  log_level: "DEBUG"
  log_dir: "logs"
broker:
  type: "paper"
  paper_balance: 50000.0
alpaca:
  feed: "iex"
  paper: true
data:
  bar_history_size: 200
  store_type: "sqlite"
  sqlite_path: "data/test.db"
risk:
  max_position_pct: 0.10
  daily_loss_limit_pct: 0.02
  max_drawdown_pct: 0.05
  max_open_positions: 5
symbols:
  - "AAPL"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    settings = load_settings(config_file)
    assert settings.system.name == "TestTrader"
    assert settings.broker.type == "paper"
    assert settings.broker.paper_balance == 50000.0
    assert settings.risk.max_position_pct == 0.10
    assert settings.symbols == ["AAPL"]


def test_settings_defaults():
    """Test default Settings configuration."""
    settings = Settings()
    assert settings.system.log_level == "INFO"
    assert settings.broker.type == "paper"
    assert settings.risk.max_open_positions == 5


def test_system_config_defaults():
    """Test default system configuration values."""
    from autotrader.core.config import SystemConfig
    sys_cfg = SystemConfig()
    assert sys_cfg.name == "AutoTrader v2"
    assert sys_cfg.log_level == "INFO"
    assert sys_cfg.log_dir == "logs"


def test_system_config_custom_values():
    """Test custom system configuration values."""
    from autotrader.core.config import SystemConfig
    sys_cfg = SystemConfig(name="MyTrader", log_level="DEBUG")
    assert sys_cfg.name == "MyTrader"
    assert sys_cfg.log_level == "DEBUG"


def test_broker_config_defaults():
    """Test default broker configuration values."""
    from autotrader.core.config import BrokerConfig
    broker_cfg = BrokerConfig()
    assert broker_cfg.type == "paper"
    assert broker_cfg.paper_balance == 100_000.0


def test_broker_config_alpaca():
    """Test alpaca broker configuration."""
    from autotrader.core.config import BrokerConfig
    broker_cfg = BrokerConfig(type="alpaca")
    assert broker_cfg.type == "alpaca"


def test_alpaca_config_defaults():
    """Test default alpaca configuration values."""
    from autotrader.core.config import AlpacaConfig
    alpaca_cfg = AlpacaConfig()
    assert alpaca_cfg.feed == "iex"
    assert alpaca_cfg.paper is True


def test_alpaca_config_custom():
    """Test custom alpaca configuration."""
    from autotrader.core.config import AlpacaConfig
    alpaca_cfg = AlpacaConfig(feed="sip", paper=False)
    assert alpaca_cfg.feed == "sip"
    assert alpaca_cfg.paper is False


def test_data_config_defaults():
    """Test default data configuration values."""
    from autotrader.core.config import DataConfig
    data_cfg = DataConfig()
    assert data_cfg.bar_history_size == 500
    assert data_cfg.store_type == "sqlite"
    assert data_cfg.sqlite_path == "data/autotrader.db"


def test_data_config_postgres():
    """Test data configuration with postgres store."""
    from autotrader.core.config import DataConfig
    data_cfg = DataConfig(store_type="postgres")
    assert data_cfg.store_type == "postgres"


def test_risk_config_defaults():
    """Test default risk configuration values."""
    from autotrader.core.config import RiskConfig
    risk_cfg = RiskConfig()
    assert risk_cfg.max_position_pct == 0.10
    assert risk_cfg.daily_loss_limit_pct == 0.02
    assert risk_cfg.max_drawdown_pct == 0.15
    assert risk_cfg.max_open_positions == 5


def test_risk_config_custom():
    """Test custom risk configuration."""
    from autotrader.core.config import RiskConfig
    risk_cfg = RiskConfig(
        max_position_pct=0.20,
        daily_loss_limit_pct=0.05,
        max_drawdown_pct=0.10,
        max_open_positions=10
    )
    assert risk_cfg.max_position_pct == 0.20
    assert risk_cfg.daily_loss_limit_pct == 0.05


def test_settings_with_all_configs(tmp_path):
    """Test Settings with all configuration sections."""
    yaml_content = """
system:
  name: "FullConfig"
  log_level: "WARNING"
  log_dir: "logs/production"
broker:
  type: "alpaca"
  paper_balance: 50000.0
alpaca:
  feed: "sip"
  paper: false
data:
  bar_history_size: 1000
  store_type: "postgres"
  sqlite_path: "data/prod.db"
risk:
  max_position_pct: 0.15
  daily_loss_limit_pct: 0.05
  max_drawdown_pct: 0.10
  max_open_positions: 20
symbols:
  - "AAPL"
  - "MSFT"
  - "GOOGL"
  - "TSLA"
"""
    config_file = tmp_path / "full_config.yaml"
    config_file.write_text(yaml_content)

    settings = load_settings(config_file)
    assert settings.system.name == "FullConfig"
    assert settings.system.log_level == "WARNING"
    assert settings.system.log_dir == "logs/production"
    assert settings.broker.type == "alpaca"
    assert settings.broker.paper_balance == 50000.0
    assert settings.alpaca.feed == "sip"
    assert settings.alpaca.paper is False
    assert settings.data.bar_history_size == 1000
    assert settings.data.store_type == "postgres"
    assert settings.risk.max_position_pct == 0.15
    assert len(settings.symbols) == 4


def test_settings_partial_config(tmp_path):
    """Test Settings with partial configuration (using defaults for rest)."""
    yaml_content = """
system:
  name: "Minimal"
"""
    config_file = tmp_path / "minimal_config.yaml"
    config_file.write_text(yaml_content)

    settings = load_settings(config_file)
    assert settings.system.name == "Minimal"
    # Other sections use defaults
    assert settings.broker.type == "paper"
    assert settings.risk.max_open_positions == 5


def test_load_settings_file_not_found():
    """Test load_settings raises error for missing file."""
    with pytest.raises(FileNotFoundError):
        load_settings(Path("/nonexistent/path/config.yaml"))


def test_load_settings_invalid_yaml(tmp_path):
    """Test load_settings raises error for invalid YAML."""
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("{ invalid yaml: [")

    with pytest.raises(Exception):  # YAML parsing error
        load_settings(config_file)


def test_log_level_validation():
    """Test log level validation accepts valid values."""
    from autotrader.core.config import SystemConfig

    for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        sys_cfg = SystemConfig(log_level=level)
        assert sys_cfg.log_level == level


def test_broker_type_validation():
    """Test broker type validation accepts valid values."""
    from autotrader.core.config import BrokerConfig

    for broker_type in ["paper", "alpaca"]:
        broker_cfg = BrokerConfig(type=broker_type)
        assert broker_cfg.type == broker_type


def test_store_type_validation():
    """Test store type validation accepts valid values."""
    from autotrader.core.config import DataConfig

    for store_type in ["sqlite", "postgres"]:
        data_cfg = DataConfig(store_type=store_type)
        assert data_cfg.store_type == store_type


def test_feed_type_validation():
    """Test feed type validation accepts valid values."""
    from autotrader.core.config import AlpacaConfig

    for feed in ["iex", "sip"]:
        alpaca_cfg = AlpacaConfig(feed=feed)
        assert alpaca_cfg.feed == feed


def test_settings_empty_symbols():
    """Test Settings with empty symbols list."""
    from autotrader.core.config import Settings
    settings = Settings(symbols=[])
    assert settings.symbols == []


def test_settings_custom_symbols():
    """Test Settings with custom symbols list."""
    from autotrader.core.config import Settings
    symbols = ["BTC/USD", "ETH/USD", "SPY"]
    settings = Settings(symbols=symbols)
    assert settings.symbols == symbols


class TestRotationConfig:
    def test_defaults(self):
        from autotrader.core.config import RotationConfig
        cfg = RotationConfig()
        assert cfg.max_universe_size == 15
        assert cfg.max_concurrent_positions == 3
        assert cfg.weekly_loss_limit_pct == 0.05
        assert cfg.force_close_day == 4  # Friday
        assert cfg.force_close_hour == 14
        assert cfg.rotation_day == 5  # Saturday

    def test_validates_loss_limit_too_high(self):
        from autotrader.core.config import RotationConfig
        with pytest.raises(ValueError):
            RotationConfig(weekly_loss_limit_pct=1.5)

    def test_validates_loss_limit_negative(self):
        from autotrader.core.config import RotationConfig
        with pytest.raises(ValueError):
            RotationConfig(weekly_loss_limit_pct=-0.1)

    def test_custom_values(self):
        from autotrader.core.config import RotationConfig
        cfg = RotationConfig(
            max_universe_size=20,
            max_concurrent_positions=5,
            weekly_loss_limit_pct=0.10,
            force_close_day=3,
            force_close_hour=15,
            rotation_day=6,
        )
        assert cfg.max_universe_size == 20
        assert cfg.weekly_loss_limit_pct == 0.10


class TestSchedulerConfig:
    def test_defaults(self):
        from autotrader.core.config import SchedulerConfig
        cfg = SchedulerConfig()
        assert cfg.enable_rotation_scheduler is True
        assert cfg.rotation_check_interval_seconds == 300
        assert cfg.regime_proxy_symbol == "SPY"

    def test_custom_values(self):
        from autotrader.core.config import SchedulerConfig
        cfg = SchedulerConfig(
            enable_rotation_scheduler=False,
            rotation_check_interval_seconds=600,
            regime_proxy_symbol="QQQ",
        )
        assert cfg.enable_rotation_scheduler is False
        assert cfg.rotation_check_interval_seconds == 600
        assert cfg.regime_proxy_symbol == "QQQ"


class TestPerformanceConfig:
    def test_defaults(self):
        from autotrader.core.config import PerformanceConfig
        cfg = PerformanceConfig()
        assert cfg.enable_trade_log is True
        assert cfg.trade_log_path == "data/live_trades.jsonl"
        assert cfg.equity_snapshot_path == "data/equity_snapshots.jsonl"
        assert cfg.equity_snapshot_interval == 10

    def test_custom_values(self):
        from autotrader.core.config import PerformanceConfig
        cfg = PerformanceConfig(
            enable_trade_log=False,
            trade_log_path="/tmp/trades.jsonl",
            equity_snapshot_interval=5,
        )
        assert cfg.enable_trade_log is False
        assert cfg.trade_log_path == "/tmp/trades.jsonl"
        assert cfg.equity_snapshot_interval == 5


class TestSettingsWithNewConfigs:
    def test_settings_has_scheduler(self):
        settings = Settings()
        assert hasattr(settings, 'scheduler')
        from autotrader.core.config import SchedulerConfig
        assert isinstance(settings.scheduler, SchedulerConfig)

    def test_settings_has_performance(self):
        settings = Settings()
        assert hasattr(settings, 'performance')
        from autotrader.core.config import PerformanceConfig
        assert isinstance(settings.performance, PerformanceConfig)


class TestMarketSentimentConfig:
    def test_defaults(self):
        from autotrader.core.config import MarketSentimentConfig
        cfg = MarketSentimentConfig()
        assert cfg.enable_vix is True
        assert cfg.vix_symbol == "^VIX"
        assert cfg.cache_ttl_seconds == 3600
        assert cfg.vix_spike_threshold == 30.0

    def test_custom_values(self):
        from autotrader.core.config import MarketSentimentConfig
        cfg = MarketSentimentConfig(enable_vix=False, vix_spike_threshold=25.0)
        assert cfg.enable_vix is False
        assert cfg.vix_spike_threshold == 25.0

    def test_settings_has_sentiment(self):
        from autotrader.core.config import Settings
        s = Settings()
        assert hasattr(s, 'sentiment')
