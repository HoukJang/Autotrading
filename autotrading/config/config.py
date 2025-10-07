"""
Configuration Management
Centralized configuration for the trading system
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from decimal import Decimal
from dotenv import load_dotenv
import yaml

# Load environment variables
load_dotenv()


@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str = field(default_factory=lambda: os.getenv('DB_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(os.getenv('DB_PORT', 5432)))
    name: str = field(default_factory=lambda: os.getenv('DB_NAME', 'trading_db'))
    user: str = field(default_factory=lambda: os.getenv('DB_USER', 'trader'))
    password: str = field(default_factory=lambda: os.getenv('DB_PASSWORD', ''))
    pool_size: int = field(default_factory=lambda: int(os.getenv('DB_POOL_SIZE', 10)))
    pool_max_overflow: int = field(default_factory=lambda: int(os.getenv('DB_POOL_MAX_OVERFLOW', 20)))

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def asyncpg_url(self) -> str:
        """Get asyncpg connection URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class BrokerConfig:
    """Interactive Brokers configuration"""
    host: str = field(default_factory=lambda: os.getenv('IB_HOST', '127.0.0.1'))
    port: int = field(default_factory=lambda: int(os.getenv('IB_PORT', 7497)))
    client_id: int = field(default_factory=lambda: int(os.getenv('IB_CLIENT_ID', 1)))

    @property
    def is_tws(self) -> bool:
        """Check if using TWS (port 7497) or Gateway (port 4001)"""
        return self.port == 7497

    @property
    def connection_name(self) -> str:
        """Get connection type name"""
        return "TWS" if self.is_tws else "IB Gateway"


@dataclass
class RiskConfig:
    """Risk management configuration"""
    max_position_size: int = field(
        default_factory=lambda: int(os.getenv('MAX_POSITION_SIZE', 5))
    )
    max_portfolio_risk: float = field(
        default_factory=lambda: float(os.getenv('MAX_PORTFOLIO_RISK', 0.02))
    )
    max_drawdown: float = field(
        default_factory=lambda: float(os.getenv('MAX_DRAWDOWN', 0.05))
    )
    emergency_liquidate_on_disconnect: bool = field(
        default_factory=lambda: os.getenv('EMERGENCY_LIQUIDATE_ON_DISCONNECT', 'true').lower() == 'true'
    )
    max_daily_loss: Optional[Decimal] = field(
        default_factory=lambda: Decimal(os.getenv('MAX_DAILY_LOSS', '0')) or None
    )
    max_daily_trades: Optional[int] = field(
        default_factory=lambda: int(os.getenv('MAX_DAILY_TRADES', '0')) or None
    )


@dataclass
class PositionSizingConfig:
    """Position sizing configuration"""
    method: str = field(
        default_factory=lambda: os.getenv('POSITION_SIZING_METHOD', 'fixed')
    )
    default_size: int = field(
        default_factory=lambda: int(os.getenv('DEFAULT_POSITION_SIZE', 1))
    )
    size_multiplier: float = field(
        default_factory=lambda: float(os.getenv('POSITION_SIZE_MULTIPLIER', 1.0))
    )

    # Trading parameters
    default_stop_loss_pct: float = field(
        default_factory=lambda: float(os.getenv('DEFAULT_STOP_LOSS_PCT', 0.02))
    )
    default_take_profit_pct: float = field(
        default_factory=lambda: float(os.getenv('DEFAULT_TAKE_PROFIT_PCT', 0.04))
    )
    trailing_stop_enabled: bool = field(
        default_factory=lambda: os.getenv('TRAILING_STOP_ENABLED', 'false').lower() == 'true'
    )
    trailing_stop_pct: float = field(
        default_factory=lambda: float(os.getenv('TRAILING_STOP_PCT', 0.015))
    )


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    file: str = field(default_factory=lambda: os.getenv('LOG_FILE', 'logs/trading_system.log'))
    max_bytes: int = field(default_factory=lambda: int(os.getenv('LOG_MAX_BYTES', 104857600)))
    backup_count: int = field(default_factory=lambda: int(os.getenv('LOG_BACKUP_COUNT', 10)))


@dataclass
class PerformanceConfig:
    """Performance and optimization configuration"""
    tick_buffer_size: int = field(
        default_factory=lambda: int(os.getenv('TICK_BUFFER_SIZE', 10000))
    )
    bar_buffer_size: int = field(
        default_factory=lambda: int(os.getenv('BAR_BUFFER_SIZE', 1000))
    )
    event_queue_size: int = field(
        default_factory=lambda: int(os.getenv('EVENT_QUEUE_SIZE', 10000))
    )
    max_workers: int = field(
        default_factory=lambda: int(os.getenv('MAX_WORKERS', 4))
    )


@dataclass
class DataConfig:
    """Data collection and storage configuration"""
    save_tick_data: bool = field(
        default_factory=lambda: os.getenv('SAVE_TICK_DATA', 'false').lower() == 'true'
    )
    save_bar_data: bool = field(
        default_factory=lambda: os.getenv('SAVE_BAR_DATA', 'true').lower() == 'true'
    )
    data_retention_days: int = field(
        default_factory=lambda: int(os.getenv('DATA_RETENTION_DAYS', 365))
    )


@dataclass
class MonitoringConfig:
    """System monitoring configuration"""
    health_check_interval: int = field(
        default_factory=lambda: int(os.getenv('HEALTH_CHECK_INTERVAL', 30))
    )
    metrics_interval: int = field(
        default_factory=lambda: int(os.getenv('METRICS_INTERVAL', 60))
    )
    performance_calc_interval: int = field(
        default_factory=lambda: int(os.getenv('PERFORMANCE_CALC_INTERVAL', 300))
    )


class TradingConfig:
    """Main trading system configuration"""

    _instance: Optional['TradingConfig'] = None

    def __new__(cls) -> 'TradingConfig':
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize configuration"""
        if self._initialized:
            return

        self._initialized = True
        self.environment = os.getenv('ENVIRONMENT', 'development')

        # Component configurations
        self.database = DatabaseConfig()
        self.broker = BrokerConfig()
        self.risk = RiskConfig()
        self.position_sizing = PositionSizingConfig()
        self.logging = LoggingConfig()
        self.performance = PerformanceConfig()
        self.data = DataConfig()
        self.monitoring = MonitoringConfig()

        # Load additional settings from YAML if exists
        self._load_yaml_config()

    def _load_yaml_config(self) -> None:
        """Load additional configuration from YAML file"""
        config_file = Path(__file__).parent / 'settings.yaml'
        if config_file.exists():
            with open(config_file, 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    self._merge_config(yaml_config)

    def _merge_config(self, yaml_config: Dict[str, Any]) -> None:
        """Merge YAML configuration with environment variables"""
        # Environment variables take precedence
        for section, values in yaml_config.items():
            if hasattr(self, section) and isinstance(values, dict):
                section_obj = getattr(self, section)
                for key, value in values.items():
                    if hasattr(section_obj, key):
                        # Only set if not already set by environment variable
                        current_value = getattr(section_obj, key)
                        if current_value is None or current_value == '':
                            setattr(section_obj, key, value)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == 'development'

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == 'production'

    def validate(self) -> bool:
        """
        Validate configuration

        Returns:
            True if valid, raises exception if not
        """
        import sys
        from pathlib import Path
        # Add parent directory to path for imports
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.exceptions import ConfigurationError

        # Check database password
        if not self.database.password:
            raise ConfigurationError(
                "Database password not set",
                config_key='DB_PASSWORD'
            )

        # Check broker connection
        if self.broker.port not in [7497, 4001]:
            raise ConfigurationError(
                f"Invalid IB port: {self.broker.port}. Must be 7497 (TWS) or 4001 (Gateway)",
                config_key='IB_PORT',
                actual_value=self.broker.port
            )

        # Check risk parameters
        if not 0 < self.risk.max_portfolio_risk < 1:
            raise ConfigurationError(
                f"Invalid max portfolio risk: {self.risk.max_portfolio_risk}. Must be between 0 and 1",
                config_key='MAX_PORTFOLIO_RISK',
                actual_value=self.risk.max_portfolio_risk
            )

        # Check position sizing
        if self.position_sizing.method not in ['fixed', 'volatility', 'kelly']:
            raise ConfigurationError(
                f"Invalid position sizing method: {self.position_sizing.method}",
                config_key='POSITION_SIZING_METHOD',
                actual_value=self.position_sizing.method,
                expected_type='fixed|volatility|kelly'
            )

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'environment': self.environment,
            'database': {
                'host': self.database.host,
                'port': self.database.port,
                'name': self.database.name,
                'user': self.database.user,
                'pool_size': self.database.pool_size
            },
            'broker': {
                'host': self.broker.host,
                'port': self.broker.port,
                'client_id': self.broker.client_id,
                'connection_type': self.broker.connection_name
            },
            'risk': {
                'max_position_size': self.risk.max_position_size,
                'max_portfolio_risk': self.risk.max_portfolio_risk,
                'max_drawdown': self.risk.max_drawdown,
                'emergency_liquidate': self.risk.emergency_liquidate_on_disconnect
            },
            'position_sizing': {
                'method': self.position_sizing.method,
                'default_size': self.position_sizing.default_size,
                'multiplier': self.position_sizing.size_multiplier
            }
        }

    def print_config(self) -> None:
        """Print configuration summary"""
        print("=" * 50)
        print("Trading System Configuration")
        print("=" * 50)
        print(f"Environment: {self.environment}")
        print(f"\nDatabase:")
        print(f"  Host: {self.database.host}:{self.database.port}")
        print(f"  Database: {self.database.name}")
        print(f"  User: {self.database.user}")
        print(f"\nBroker:")
        print(f"  Connection: {self.broker.connection_name}")
        print(f"  Host: {self.broker.host}:{self.broker.port}")
        print(f"  Client ID: {self.broker.client_id}")
        print(f"\nRisk Management:")
        print(f"  Max Position Size: {self.risk.max_position_size}")
        print(f"  Max Portfolio Risk: {self.risk.max_portfolio_risk:.2%}")
        print(f"  Max Drawdown: {self.risk.max_drawdown:.2%}")
        print(f"  Emergency Liquidate: {self.risk.emergency_liquidate_on_disconnect}")
        print(f"\nPosition Sizing:")
        print(f"  Method: {self.position_sizing.method}")
        print(f"  Default Size: {self.position_sizing.default_size}")
        print(f"  Size Multiplier: {self.position_sizing.size_multiplier}")
        print("=" * 50)


# Singleton instance
_config: Optional[TradingConfig] = None


def get_config() -> TradingConfig:
    """Get configuration singleton instance"""
    global _config
    if _config is None:
        _config = TradingConfig()
    return _config