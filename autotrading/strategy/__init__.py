"""
Strategy Module

Phase 4: Adaptive Strategy Management System

Components:
- VirtualSignalTracker: Tracks all signals regardless of execution
- TimeBasedScorer: Calculates performance scores with time + regime dimensions
- BudgetAllocator: Allocates position size based on account balance
- PositionManager: Tracks active positions and enforces limits
- LossLimitManager: Manages trading pauses after consecutive losses
- StrategySelector: Selects signals to execute based on constraints
- PerformanceReporter: Generates daily performance reports
- AdaptiveStrategyManager: Main orchestrator
"""

from .virtual_signal_tracker import VirtualSignalTracker, SignalRecord
from .time_based_scorer import TimeBasedScorer
from .budget_allocator import BudgetAllocator
from .position_manager import PositionManager, Position
from .loss_limit_manager import LossLimitManager
from .strategy_selector import StrategySelector, SignalCandidate, ExecutionDecision
from .performance_reporter import PerformanceReporter
from .adaptive_strategy_manager import AdaptiveStrategyManager

__all__ = [
    'VirtualSignalTracker',
    'SignalRecord',
    'TimeBasedScorer',
    'BudgetAllocator',
    'PositionManager',
    'Position',
    'LossLimitManager',
    'StrategySelector',
    'SignalCandidate',
    'ExecutionDecision',
    'PerformanceReporter',
    'AdaptiveStrategyManager',
]
