"""
Core Infrastructure Module
Provides event system, logging, and exceptions
"""

from .events import (
    Event,
    MarketDataEvent,
    SignalEvent,
    OrderEvent,
    FillEvent,
    RiskEvent,
    SystemEvent
)

from .event_bus import EventBus
from .logger import TradingLogger, get_logger
from .exceptions import (
    TradingSystemError,
    ConnectionError,
    DataError,
    RiskError,
    StrategyError
)

__all__ = [
    # Events
    'Event',
    'MarketDataEvent',
    'SignalEvent',
    'OrderEvent',
    'FillEvent',
    'RiskEvent',
    'SystemEvent',

    # Event Bus
    'EventBus',

    # Logging
    'TradingLogger',
    'get_logger',

    # Exceptions
    'TradingSystemError',
    'ConnectionError',
    'DataError',
    'RiskError',
    'StrategyError'
]