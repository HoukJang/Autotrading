"""Rotation module for weekly universe rotation and watchlist management."""
from autotrader.rotation.types import WatchlistEntry, RotationState, RotationEvent
from autotrader.rotation.manager import RotationManager
from autotrader.rotation.backtest_engine import RotationBacktestEngine, RotationBacktestResult
from autotrader.rotation.event_driven import EventDrivenRotation

__all__ = [
    "WatchlistEntry",
    "RotationState",
    "RotationEvent",
    "RotationManager",
    "RotationBacktestEngine",
    "RotationBacktestResult",
    "EventDrivenRotation",
]
