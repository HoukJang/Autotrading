"""Execution engine for batch+intraday hybrid trading architecture.

This package contains:
- OrderManager: wraps AlpacaAdapter for order lifecycle management
- EntryManager: MOO and confirmation-window entry logic
- ExitRuleEngine: SL/TP, time-based, and re-entry block logic
- PositionMonitor: real-time position streaming and exit evaluation
"""
from autotrader.execution.order_manager import OrderManager
from autotrader.execution.entry_manager import EntryManager
from autotrader.execution.exit_rules import ExitRuleEngine
from autotrader.execution.position_monitor import PositionMonitor

__all__ = [
    "OrderManager",
    "EntryManager",
    "ExitRuleEngine",
    "PositionMonitor",
]
