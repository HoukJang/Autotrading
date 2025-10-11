"""
Backtesting framework for trading strategies.

This module provides a comprehensive backtesting engine with:
- Point-in-Time (PIT) data access guarantee
- Limit/Stop order execution simulation
- OCO (One-Cancels-Other) order support
- Strategy state management
- Performance metrics and trade logging
"""

from .orders import Order, OrderType, OrderSide, OrderStatus
from .position import Position, Account
from .broker import Broker, BacktestBroker
from .context import Context, BacktestContext
from .engine import BacktestEngine
from .performance import PerformanceTracker, TradeLog

__all__ = [
    'Order',
    'OrderType',
    'OrderSide',
    'OrderStatus',
    'Position',
    'Account',
    'Broker',
    'BacktestBroker',
    'Context',
    'BacktestContext',
    'BacktestEngine',
    'PerformanceTracker',
    'TradeLog',
]
