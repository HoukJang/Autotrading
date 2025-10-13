"""
Performance Reporter

Generates daily performance reports for adaptive strategy system.
"""

from typing import Dict, List
from datetime import datetime, timedelta
import json

from .virtual_signal_tracker import VirtualSignalTracker, SignalRecord


class PerformanceReporter:
    """
    Generates performance reports and analytics.

    Features:
    - Daily performance summaries
    - Trigger-specific analytics
    - Time slot performance
    - Budget allocation tracking
    """

    def __init__(self, tracker: VirtualSignalTracker):
        """
        Initialize performance reporter.

        Args:
            tracker: Virtual signal tracker
        """
        self.tracker = tracker

    def generate_daily_report(
        self,
        date: datetime,
        trigger_names: List[str],
    ) -> Dict:
        """
        Generate daily performance report.

        Args:
            date: Date to report on
            trigger_names: List of trigger names

        Returns:
            Report dictionary
        """
        # Get day's signals
        start_time = date.replace(hour=0, minute=0, second=0)
        end_time = date.replace(hour=23, minute=59, second=59)

        day_signals = self.tracker.get_signal_history(
            start_time=start_time,
            end_time=end_time,
        )

        # Overall statistics
        overall_stats = self._calculate_overall_stats(day_signals)

        # Trigger-specific statistics
        trigger_stats = {}
        for trigger_name in trigger_names:
            trigger_signals = [s for s in day_signals if s.trigger_name == trigger_name]
            trigger_stats[trigger_name] = self._calculate_trigger_stats(trigger_signals)

        # Time slot performance
        time_slot_stats = self._calculate_time_slot_stats(day_signals)

        # Execution statistics
        execution_stats = self._calculate_execution_stats(day_signals)

        report = {
            'date': date.strftime('%Y-%m-%d'),
            'overall': overall_stats,
            'by_trigger': trigger_stats,
            'by_time_slot': time_slot_stats,
            'execution': execution_stats,
        }

        return report

    def _calculate_overall_stats(self, signals: List[SignalRecord]) -> Dict:
        """Calculate overall daily statistics."""
        closed = [s for s in signals if s.outcome is not None]

        if len(closed) == 0:
            return {
                'total_signals': len(signals),
                'executed_signals': len([s for s in signals if s.executed]),
                'closed_signals': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'max_win': 0.0,
                'max_loss': 0.0,
            }

        wins = [s for s in closed if s.outcome == 'TP']
        losses = [s for s in closed if s.outcome == 'SL']

        win_pnls = [s.pnl for s in wins] if wins else [0.0]
        loss_pnls = [s.pnl for s in losses] if losses else [0.0]

        return {
            'total_signals': len(signals),
            'executed_signals': len([s for s in signals if s.executed]),
            'closed_signals': len(closed),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(closed),
            'total_pnl': sum(s.pnl for s in closed),
            'avg_pnl': sum(s.pnl for s in closed) / len(closed),
            'max_win': max(win_pnls),
            'max_loss': min(loss_pnls),
        }

    def _calculate_trigger_stats(self, signals: List[SignalRecord]) -> Dict:
        """Calculate statistics for a specific trigger."""
        closed = [s for s in signals if s.outcome is not None]

        if len(closed) == 0:
            return {
                'signals': len(signals),
                'executed': len([s for s in signals if s.executed]),
                'closed': 0,
                'win_rate': 0.0,
                'pnl': 0.0,
            }

        wins = [s for s in closed if s.outcome == 'TP']

        return {
            'signals': len(signals),
            'executed': len([s for s in signals if s.executed]),
            'closed': len(closed),
            'wins': len(wins),
            'losses': len(closed) - len(wins),
            'win_rate': len(wins) / len(closed),
            'pnl': sum(s.pnl for s in closed),
            'avg_pnl': sum(s.pnl for s in closed) / len(closed),
        }

    def _calculate_time_slot_stats(self, signals: List[SignalRecord]) -> Dict:
        """Calculate performance by 30-minute time slots."""
        # Group by 30-minute slots
        slots = {}

        for signal in signals:
            if signal.outcome is None:
                continue

            # Get 30-minute slot
            slot = signal.timestamp.replace(
                minute=(signal.timestamp.minute // 30) * 30,
                second=0,
                microsecond=0
            )
            slot_key = slot.strftime('%H:%M')

            if slot_key not in slots:
                slots[slot_key] = []

            slots[slot_key].append(signal)

        # Calculate stats for each slot
        slot_stats = {}
        for slot_key, slot_signals in slots.items():
            wins = [s for s in slot_signals if s.outcome == 'TP']
            slot_stats[slot_key] = {
                'count': len(slot_signals),
                'wins': len(wins),
                'losses': len(slot_signals) - len(wins),
                'win_rate': len(wins) / len(slot_signals),
                'pnl': sum(s.pnl for s in slot_signals),
            }

        return slot_stats

    def _calculate_execution_stats(self, signals: List[SignalRecord]) -> Dict:
        """Calculate execution statistics."""
        total = len(signals)
        executed = len([s for s in signals if s.executed])
        skipped = total - executed

        execution_rate = executed / total if total > 0 else 0.0

        return {
            'total_signals': total,
            'executed': executed,
            'skipped': skipped,
            'execution_rate': execution_rate,
        }

    def save_report(self, report: Dict, filepath: str):
        """
        Save report to file.

        Args:
            report: Report dictionary
            filepath: Path to save file
        """
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)

    def print_summary(self, report: Dict):
        """
        Print report summary to console.

        Args:
            report: Report dictionary
        """
        print("=" * 80)
        print(f"DAILY PERFORMANCE REPORT - {report['date']}")
        print("=" * 80)

        overall = report['overall']
        print(f"\nOverall Performance:")
        print(f"  Total Signals: {overall['total_signals']}")
        print(f"  Executed: {overall['executed_signals']}")
        print(f"  Closed: {overall['closed_signals']}")
        print(f"  Win Rate: {overall['win_rate']:.2%}")
        print(f"  Total PnL: {overall['total_pnl']:.2f}")
        print(f"  Avg PnL: {overall['avg_pnl']:.2f}")

        print(f"\nBy Trigger:")
        for trigger, stats in report['by_trigger'].items():
            print(f"  {trigger}:")
            print(f"    Signals: {stats['signals']} | Executed: {stats['executed']}")
            print(f"    Win Rate: {stats['win_rate']:.2%} | PnL: {stats['pnl']:.2f}")

        print(f"\nExecution:")
        exec_stats = report['execution']
        print(f"  Execution Rate: {exec_stats['execution_rate']:.2%}")
        print(f"  Executed: {exec_stats['executed']} | Skipped: {exec_stats['skipped']}")

        print("=" * 80)
