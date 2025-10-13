"""
Adaptive Strategy Manager

Main orchestrator for Phase 4 adaptive strategy system.
Integrates all components and provides unified API.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import uuid

from ..analysis import RegimeDetector, EnergyAccumulator, RegimeResult, EnergyResult
from ..analysis.triggers import BaseTrigger, TriggerSignal
from .virtual_signal_tracker import VirtualSignalTracker
from .time_based_scorer import TimeBasedScorer
from .budget_allocator import BudgetAllocator
from .position_manager import PositionManager
from .loss_limit_manager import LossLimitManager
from .strategy_selector import StrategySelector
from .performance_reporter import PerformanceReporter


class AdaptiveStrategyManager:
    """
    Phase 4: Adaptive Strategy Manager

    Orchestrates the entire adaptive strategy system:
    - Tracks all signals (virtual + executed)
    - Calculates time-based performance scores
    - Allocates budget dynamically
    - Enforces position and loss limits
    - Generates performance reports

    Usage:
        manager = AdaptiveStrategyManager(
            triggers=[BollingerTrigger(), MACrossTrigger(), ...],
            account_balance=100000.0,
        )

        # Every bar
        decisions = manager.process_bar(current_bar, history)

        # Execute decisions
        for decision in decisions:
            if decision.execute:
                place_order(decision.signal, decision.position_size)

        # Daily report
        report = manager.generate_daily_report(date)
    """

    def __init__(
        self,
        triggers: List[BaseTrigger],
        account_balance: float,
        risk_percentage: float = 0.02,
        contract_value: float = 15000.0,
        window_minutes: int = 30,
        decay_days: int = 30,
        decay_lambda: float = 0.1,
        max_consecutive_losses: int = 3,
        pause_minutes: int = 30,
    ):
        """
        Initialize adaptive strategy manager.

        Args:
            triggers: List of trigger instances
            account_balance: Initial account balance
            risk_percentage: Risk percentage (default 2%)
            contract_value: Value per contract
            window_minutes: Time window for scoring (30 min)
            decay_days: Max lookback days (30 days)
            decay_lambda: Decay rate (0.1)
            max_consecutive_losses: Pause after N losses (3)
            pause_minutes: Pause duration (30 min)
        """
        self.triggers = triggers
        self.trigger_names = [t.name for t in triggers]
        self.account_balance = account_balance

        # Core components
        self.regime_detector = RegimeDetector()
        self.energy_accumulator = EnergyAccumulator()

        # Phase 4 components
        self.tracker = VirtualSignalTracker()
        self.scorer = TimeBasedScorer(
            window_minutes=window_minutes,
            decay_days=decay_days,
            decay_lambda=decay_lambda,
        )
        self.allocator = BudgetAllocator(
            risk_percentage=risk_percentage,
            contract_value=contract_value,
        )
        self.position_manager = PositionManager()
        self.loss_limit_manager = LossLimitManager(
            max_consecutive_losses=max_consecutive_losses,
            pause_minutes=pause_minutes,
        )
        self.selector = StrategySelector(
            tracker=self.tracker,
            scorer=self.scorer,
            allocator=self.allocator,
            position_manager=self.position_manager,
            loss_limit_manager=self.loss_limit_manager,
        )
        self.reporter = PerformanceReporter(tracker=self.tracker)

    def process_bar(
        self,
        current_bar: pd.Series,
        history: pd.DataFrame,
    ) -> List:
        """
        Process a single bar.

        Workflow:
        1. Update outcomes for active signals (TP/SL check)
        2. Detect regime and energy
        3. Generate signals from all triggers
        4. Evaluate and select signals to execute
        5. Return execution decisions

        Args:
            current_bar: Current OHLC bar
            history: Full OHLCV history up to current bar

        Returns:
            List of ExecutionDecisions
        """
        current_time = current_bar.name

        # 1. Update outcomes (check TP/SL hits)
        self.tracker.update_outcomes(current_bar, current_time)

        # 2. Detect regime and energy
        regime_result = self.regime_detector.detect(history)
        energy_result = self.energy_accumulator.calculate(history, regime_result)

        # 3. Generate signals from all triggers
        trigger_signals = {}
        for trigger in self.triggers:
            signal = trigger.check_entry(history, regime_result, energy_result)
            if signal:
                trigger_signals[trigger.name] = signal

        # 4. If no signals, return empty
        if len(trigger_signals) == 0:
            return []

        # 5. Evaluate signals and select executions
        decisions = self.selector.evaluate_signals(
            trigger_signals=trigger_signals,
            current_time=current_time,
            current_regime=regime_result.regime.value,
            account_balance=self.account_balance,
        )

        # 6. Record all signals in tracker (executed or not)
        for decision in decisions:
            signal_id = self.tracker.record_signal(
                timestamp=current_time,
                trigger_name=decision.trigger_name,
                signal=decision.signal,
                executed=decision.execute,
            )

            # If executed, add to position manager
            if decision.execute:
                position_id = str(uuid.uuid4())
                self.position_manager.open_position(
                    position_id=position_id,
                    signal_id=signal_id,
                    trigger_name=decision.trigger_name,
                    direction=decision.signal.signal,
                    size=decision.position_size,
                    entry_price=decision.signal.entry_price,
                    tp=decision.signal.tp,
                    sl=decision.signal.sl,
                    entry_time=current_time,
                )

        return decisions

    def update_account_balance(self, new_balance: float):
        """
        Update account balance.

        Args:
            new_balance: New account balance
        """
        self.account_balance = new_balance

    def initialize_from_backtest(
        self,
        historical_data: pd.DataFrame,
    ):
        """
        Initialize scores from backtest data.

        Process:
        1. Run backtest on historical data
        2. Populate tracker with historical signals
        3. Scores will be calculated from this data

        Args:
            historical_data: Historical OHLCV data
        """
        print(f"Initializing from backtest ({len(historical_data)} bars)...")

        min_bars = 120
        for i in range(min_bars, len(historical_data)):
            history = historical_data.iloc[:i+1]
            current_bar = historical_data.iloc[i]

            # Process bar (this populates tracker)
            decisions = self.process_bar(current_bar, history)

        stats = self.tracker.get_statistics()
        print(f"Backtest initialization complete:")
        print(f"  Total signals: {stats['total_signals']}")
        print(f"  Closed signals: {stats['closed_signals']}")
        print(f"  Win rate: {stats['win_rate']:.2%}")
        print(f"  Total PnL: {stats['total_pnl']:.2f}")

    def generate_daily_report(self, date: datetime) -> Dict:
        """
        Generate daily performance report.

        Args:
            date: Date to report

        Returns:
            Report dictionary
        """
        return self.reporter.generate_daily_report(
            date=date,
            trigger_names=self.trigger_names,
        )

    def print_status(self, current_time: datetime):
        """
        Print current system status.

        Args:
            current_time: Current timestamp
        """
        print("\n" + "=" * 80)
        print(f"ADAPTIVE STRATEGY MANAGER STATUS - {current_time}")
        print("=" * 80)

        # Budget info
        budget_info = self.allocator.get_budget_info(self.account_balance)
        print(f"\nBudget:")
        print(f"  Account Balance: ${budget_info['account_balance']:,.2f}")
        print(f"  Risk Percentage: {budget_info['risk_percentage']:.1%}")
        print(f"  Total Budget: ${budget_info['total_budget']:,.2f}")
        print(f"  Total Position Size: {budget_info['total_position_size']} contracts")

        # Position info
        pos_stats = self.position_manager.get_statistics()
        print(f"\nPositions:")
        print(f"  Active Positions: {pos_stats['total_positions']}")
        print(f"  Total Size: {pos_stats['total_size']} contracts")
        print(f"  Net Position: {pos_stats['net_position']} contracts")

        # Loss limit status
        loss_status = self.loss_limit_manager.get_status(current_time)
        print(f"\nLoss Limit:")
        print(f"  Consecutive Losses: {loss_status['consecutive_losses']}")
        print(f"  Is Paused: {loss_status['is_paused']}")
        if loss_status['is_paused']:
            print(f"  Pause Until: {loss_status['pause_until']}")

        # Tracker stats
        tracker_stats = self.tracker.get_statistics()
        print(f"\nSignal Tracker:")
        print(f"  Total Signals: {tracker_stats['total_signals']}")
        print(f"  Closed: {tracker_stats['closed_signals']}")
        print(f"  Active: {tracker_stats['active_signals']}")
        print(f"  Win Rate: {tracker_stats['win_rate']:.2%}")
        print(f"  Total PnL: {tracker_stats['total_pnl']:.2f}")

        print("=" * 80 + "\n")

    def get_current_scores(
        self,
        current_time: datetime,
        current_regime: str,
    ) -> Dict[str, float]:
        """
        Get current scores for all triggers.

        Args:
            current_time: Current timestamp
            current_regime: Current regime

        Returns:
            {trigger_name: score}
        """
        return self.scorer.get_all_scores(
            trigger_names=self.trigger_names,
            current_time=current_time,
            current_regime=current_regime,
            signal_history=self.tracker.signals,
        )

    def save_state(self, filepath: str):
        """
        Save manager state to file.

        Args:
            filepath: Path to save
        """
        # TODO: Implement state serialization
        pass

    def load_state(self, filepath: str):
        """
        Load manager state from file.

        Args:
            filepath: Path to load
        """
        # TODO: Implement state deserialization
        pass
