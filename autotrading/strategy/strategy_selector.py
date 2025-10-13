"""
Strategy Selector

Selects which signals to execute based on scores, budget, and constraints.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from ..analysis.triggers import TriggerSignal
from .time_based_scorer import TimeBasedScorer
from .budget_allocator import BudgetAllocator
from .position_manager import PositionManager
from .loss_limit_manager import LossLimitManager
from .virtual_signal_tracker import VirtualSignalTracker


@dataclass
class SignalCandidate:
    """
    Signal candidate for execution evaluation.
    """
    trigger_name: str
    signal: TriggerSignal
    score: float
    allocated_budget: float


@dataclass
class ExecutionDecision:
    """
    Execution decision for a signal.
    """
    trigger_name: str
    signal: TriggerSignal
    execute: bool
    position_size: int
    reason: str


class StrategySelector:
    """
    Selects signals for execution based on:
    - Performance scores
    - Budget allocation
    - Position limits
    - Net position calculation
    - Loss limits
    """

    def __init__(
        self,
        tracker: VirtualSignalTracker,
        scorer: TimeBasedScorer,
        allocator: BudgetAllocator,
        position_manager: PositionManager,
        loss_limit_manager: LossLimitManager,
    ):
        """
        Initialize strategy selector.

        Args:
            tracker: Virtual signal tracker
            scorer: Time-based scorer
            allocator: Budget allocator
            position_manager: Position manager
            loss_limit_manager: Loss limit manager
        """
        self.tracker = tracker
        self.scorer = scorer
        self.allocator = allocator
        self.position_manager = position_manager
        self.loss_limit_manager = loss_limit_manager

    def evaluate_signals(
        self,
        trigger_signals: Dict[str, TriggerSignal],  # {trigger_name: signal}
        current_time: datetime,
        current_regime: str,
        account_balance: float,
    ) -> List[ExecutionDecision]:
        """
        Evaluate all signals and decide which to execute.

        Process:
        1. Calculate scores for all triggers
        2. Allocate budget based on scores
        3. Handle direction conflicts (net position)
        4. Handle budget overflow (score ranking)
        5. Apply position limits
        6. Apply loss limits

        Args:
            trigger_signals: {trigger_name: TriggerSignal}
            current_time: Current timestamp
            current_regime: Current regime
            account_balance: Account balance

        Returns:
            List of ExecutionDecisions
        """
        # 1. Check loss limit
        if not self.loss_limit_manager.can_trade(current_time):
            # Pause active - no execution but still track signals
            decisions = []
            for trigger_name, signal in trigger_signals.items():
                decisions.append(ExecutionDecision(
                    trigger_name=trigger_name,
                    signal=signal,
                    execute=False,
                    position_size=0,
                    reason='loss_limit_pause',
                ))
            return decisions

        # 2. Calculate scores for all triggers
        all_trigger_names = list(trigger_signals.keys())
        trigger_scores = self.scorer.get_all_scores(
            trigger_names=all_trigger_names,
            current_time=current_time,
            current_regime=current_regime,
            signal_history=self.tracker.signals,
        )

        # 3. Allocate budget
        budget_allocation = self.allocator.allocate(
            trigger_scores=trigger_scores,
            account_balance=account_balance,
        )

        # 4. Create signal candidates
        candidates = []
        for trigger_name, signal in trigger_signals.items():
            candidate = SignalCandidate(
                trigger_name=trigger_name,
                signal=signal,
                score=trigger_scores[trigger_name],
                allocated_budget=budget_allocation[trigger_name],
            )
            candidates.append(candidate)

        # 5. Handle direction conflicts and calculate net positions
        net_positions = self._calculate_net_positions(candidates)

        # 6. Apply budget constraints
        max_total_size = self.allocator.calculate_total_position_size(account_balance)
        current_size = self.position_manager.get_total_position_size()
        available_size = max_total_size - current_size

        execution_decisions = self._select_executions(
            net_positions=net_positions,
            available_size=available_size,
        )

        return execution_decisions

    def _calculate_net_positions(
        self,
        candidates: List[SignalCandidate]
    ) -> List[SignalCandidate]:
        """
        Calculate net positions from conflicting signals.

        Handles LONG vs SHORT conflicts:
        - If both LONG and SHORT signals exist, calculate net position
        - Both are logged, but only net is executed

        Args:
            candidates: List of signal candidates

        Returns:
            List of net position candidates
        """
        # Group by direction
        long_candidates = [c for c in candidates if c.signal.signal == 'LONG']
        short_candidates = [c for c in candidates if c.signal.signal == 'SHORT']

        # Calculate total budgets
        total_long_budget = sum(c.allocated_budget for c in long_candidates)
        total_short_budget = sum(c.allocated_budget for c in short_candidates)

        net_budget = total_long_budget - total_short_budget

        # Net position
        net_positions = []

        if net_budget > 0:
            # Net LONG
            # Scale down LONG positions proportionally
            if total_long_budget > 0:
                scale_factor = net_budget / total_long_budget
                for candidate in long_candidates:
                    net_candidate = SignalCandidate(
                        trigger_name=candidate.trigger_name,
                        signal=candidate.signal,
                        score=candidate.score,
                        allocated_budget=candidate.allocated_budget * scale_factor,
                    )
                    net_positions.append(net_candidate)

        elif net_budget < 0:
            # Net SHORT
            # Scale down SHORT positions proportionally
            if total_short_budget > 0:
                scale_factor = abs(net_budget) / total_short_budget
                for candidate in short_candidates:
                    net_candidate = SignalCandidate(
                        trigger_name=candidate.trigger_name,
                        signal=candidate.signal,
                        score=candidate.score,
                        allocated_budget=candidate.allocated_budget * scale_factor,
                    )
                    net_positions.append(net_candidate)

        # If net_budget == 0, no positions

        return net_positions

    def _select_executions(
        self,
        net_positions: List[SignalCandidate],
        available_size: int,
    ) -> List[ExecutionDecision]:
        """
        Select which signals to execute given budget constraints.

        Strategy:
        - Sort by score (highest first)
        - Execute in order until budget exhausted
        - Signals with budget < 1.0 are not executed (but logged)

        Args:
            net_positions: Net position candidates
            available_size: Available position size

        Returns:
            List of ExecutionDecisions
        """
        # Sort by score (highest first)
        sorted_candidates = sorted(
            net_positions,
            key=lambda c: c.score,
            reverse=True
        )

        decisions = []
        remaining_size = available_size

        for candidate in sorted_candidates:
            # Check if budget >= 1.0
            if candidate.allocated_budget < 1.0:
                decisions.append(ExecutionDecision(
                    trigger_name=candidate.trigger_name,
                    signal=candidate.signal,
                    execute=False,
                    position_size=0,
                    reason='insufficient_budget',
                ))
                continue

            # Calculate position size
            requested_size = int(candidate.allocated_budget)

            # Check if we have enough capacity
            if requested_size > remaining_size:
                # Partial or no execution
                if remaining_size >= 1:
                    # Execute with available size
                    decisions.append(ExecutionDecision(
                        trigger_name=candidate.trigger_name,
                        signal=candidate.signal,
                        execute=True,
                        position_size=remaining_size,
                        reason='partial_budget',
                    ))
                    remaining_size = 0
                else:
                    # No capacity left
                    decisions.append(ExecutionDecision(
                        trigger_name=candidate.trigger_name,
                        signal=candidate.signal,
                        execute=False,
                        position_size=0,
                        reason='budget_exhausted',
                    ))
            else:
                # Full execution
                decisions.append(ExecutionDecision(
                    trigger_name=candidate.trigger_name,
                    signal=candidate.signal,
                    execute=True,
                    position_size=requested_size,
                    reason='executed',
                ))
                remaining_size -= requested_size

        return decisions
