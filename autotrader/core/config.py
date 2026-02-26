"""Core configuration management module."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class SystemConfig(BaseModel):
    """System-level configuration."""

    model_config = ConfigDict(use_enum_values=True)

    name: str = "AutoTrader v2"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_dir: str = "logs"


class BrokerConfig(BaseModel):
    """Broker configuration."""

    model_config = ConfigDict(use_enum_values=True)

    type: Literal["paper", "alpaca"] = "paper"
    paper_balance: float = 100_000.0

    @field_validator("paper_balance")
    @classmethod
    def validate_balance(cls, v: float) -> float:
        """Validate that paper balance is positive."""
        if v <= 0:
            raise ValueError("paper_balance must be positive")
        return v


class AlpacaConfig(BaseModel):
    """Alpaca broker-specific configuration."""

    model_config = ConfigDict(use_enum_values=True)

    feed: Literal["iex", "sip"] = "iex"
    paper: bool = True


class DataConfig(BaseModel):
    """Data storage and retrieval configuration."""

    model_config = ConfigDict(use_enum_values=True)

    bar_history_size: int = 500
    store_type: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "data/autotrader.db"

    @field_validator("bar_history_size")
    @classmethod
    def validate_bar_history_size(cls, v: int) -> int:
        """Validate that bar_history_size is positive."""
        if v <= 0:
            raise ValueError("bar_history_size must be positive")
        return v


class RiskConfig(BaseModel):
    """Risk management configuration."""

    model_config = ConfigDict(use_enum_values=True)

    max_position_pct: float = 0.10
    daily_loss_limit_pct: float = 0.02
    max_drawdown_pct: float = 0.05
    max_open_positions: int = 5

    @field_validator("max_position_pct", "daily_loss_limit_pct", "max_drawdown_pct")
    @classmethod
    def validate_percentages(cls, v: float) -> float:
        """Validate that percentages are between 0 and 1."""
        if not 0 < v < 1:
            raise ValueError("Percentage values must be between 0 and 1")
        return v

    @field_validator("max_open_positions")
    @classmethod
    def validate_positions(cls, v: int) -> int:
        """Validate that max_open_positions is positive."""
        if v <= 0:
            raise ValueError("max_open_positions must be positive")
        return v


class RotationConfig(BaseModel):
    """Weekly rotation and watchlist configuration."""

    model_config = ConfigDict(use_enum_values=True)

    max_universe_size: int = 15
    max_concurrent_positions: int = 3
    weekly_loss_limit_pct: float = 0.05
    force_close_day: int = 4  # 0=Mon, 4=Fri
    force_close_hour: int = 14  # 14:00 UTC
    rotation_day: int = 5  # 5=Saturday

    @field_validator("weekly_loss_limit_pct")
    @classmethod
    def validate_loss_limit(cls, v: float) -> float:
        """Validate that weekly_loss_limit_pct is between 0 and 1."""
        if not 0 < v < 1:
            raise ValueError("weekly_loss_limit_pct must be between 0 and 1")
        return v


class Settings(BaseModel):
    """Root settings configuration."""

    model_config = ConfigDict(use_enum_values=True)

    system: SystemConfig = SystemConfig()
    broker: BrokerConfig = BrokerConfig()
    alpaca: AlpacaConfig = AlpacaConfig()
    data: DataConfig = DataConfig()
    risk: RiskConfig = RiskConfig()
    symbols: list[str] = ["AAPL", "MSFT", "GOOGL"]

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        """Validate symbols list."""
        if not isinstance(v, list):
            raise ValueError("symbols must be a list")
        # Each symbol should be a non-empty string
        for symbol in v:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("Each symbol must be a non-empty string")
        return v


def load_settings(path: Path | str) -> Settings:
    """Load settings from a YAML configuration file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Settings instance with loaded configuration.

    Raises:
        FileNotFoundError: If configuration file does not exist.
        yaml.YAMLError: If YAML is invalid.
        ValueError: If configuration is invalid.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        raw_config = {}

    return Settings.model_validate(raw_config)
