"""
Virtual Signal Tracker

Tracks all trigger signals regardless of execution status.
Records outcomes when TP/SL is hit for performance scoring.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import uuid

from ..analysis.triggers import TriggerSignal


@dataclass
class SignalRecord:
    """
    Record of a trigger signal with outcome.
    """
    id: str
    timestamp: datetime
    trigger_name: str
    signal: str  # 'LONG' or 'SHORT'
    entry_price: float
    tp: float
    sl: float
    regime: str
    executed: bool  # Was it actually traded?
    outcome: Optional[str] = None  # 'TP', 'SL', or None (still open)
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_timestamp: Optional[datetime] = None


class VirtualSignalTracker:
    """
    Tracks all trigger signals and their outcomes.

    Features:
    - Records all signals (executed or not)
    - Tracks TP/SL hits
    - Calculates PnL for scoring
    - Maintains signal history
    """

    def __init__(self):
        """Initialize tracker."""
        self.signals: List[SignalRecord] = []
        self.active_signals: Dict[str, SignalRecord] = {}

    def record_signal(
        self,
        timestamp: datetime,
        trigger_name: str,
        signal: TriggerSignal,
        executed: bool,
    ) -> str:
        """
        Record a new signal.

        Args:
            timestamp: Signal generation time
            trigger_name: Name of trigger that generated signal
            signal: TriggerSignal object
            executed: Whether the signal was actually executed

        Returns:
            signal_id: Unique identifier for this signal
        """
        signal_id = str(uuid.uuid4())

        record = SignalRecord(
            id=signal_id,
            timestamp=timestamp,
            trigger_name=trigger_name,
            signal=signal.signal,
            entry_price=signal.entry_price,
            tp=signal.tp,
            sl=signal.sl,
            regime=signal.regime,
            executed=executed,
        )

        self.signals.append(record)
        self.active_signals[signal_id] = record

        return signal_id

    def update_outcomes(self, current_bar: pd.Series, current_time: datetime):
        """
        Update active signals by checking TP/SL hits.

        Args:
            current_bar: Current OHLC bar
            current_time: Current timestamp
        """
        for signal_id, record in list(self.active_signals.items()):
            outcome = None
            exit_price = None

            # Check TP/SL based on direction
            if record.signal == 'LONG':
                # TP hit?
                if current_bar['high'] >= record.tp:
                    outcome = 'TP'
                    exit_price = record.tp
                # SL hit?
                elif current_bar['low'] <= record.sl:
                    outcome = 'SL'
                    exit_price = record.sl

            elif record.signal == 'SHORT':
                # TP hit?
                if current_bar['low'] <= record.tp:
                    outcome = 'TP'
                    exit_price = record.tp
                # SL hit?
                elif current_bar['high'] >= record.sl:
                    outcome = 'SL'
                    exit_price = record.sl

            # If outcome occurred, close the signal
            if outcome:
                self._close_signal(signal_id, outcome, exit_price, current_time)

    def _close_signal(
        self,
        signal_id: str,
        outcome: str,
        exit_price: float,
        exit_timestamp: datetime
    ):
        """
        Close a signal and calculate PnL.

        Args:
            signal_id: Signal ID
            outcome: 'TP' or 'SL'
            exit_price: Exit price
            exit_timestamp: Exit time
        """
        record = self.active_signals.pop(signal_id)

        # Calculate PnL (per contract in points)
        if record.signal == 'LONG':
            pnl = exit_price - record.entry_price
        else:  # SHORT
            pnl = record.entry_price - exit_price

        # Update record
        record.outcome = outcome
        record.exit_price = exit_price
        record.pnl = pnl
        record.exit_timestamp = exit_timestamp

    def get_signal_history(
        self,
        trigger_name: Optional[str] = None,
        regime: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[SignalRecord]:
        """
        Get filtered signal history.

        Args:
            trigger_name: Filter by trigger
            regime: Filter by regime
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            List of matching SignalRecords
        """
        results = []

        for record in self.signals:
            # Filters
            if trigger_name and record.trigger_name != trigger_name:
                continue
            if regime and record.regime != regime:
                continue
            if start_time and record.timestamp < start_time:
                continue
            if end_time and record.timestamp > end_time:
                continue

            results.append(record)

        return results

    def get_active_signals(self) -> List[SignalRecord]:
        """
        Get all active (not yet closed) signals.

        Returns:
            List of active SignalRecords
        """
        return list(self.active_signals.values())

    def get_statistics(self) -> Dict:
        """
        Get overall statistics.

        Returns:
            Statistics dictionary
        """
        closed_signals = [s for s in self.signals if s.outcome is not None]

        if len(closed_signals) == 0:
            return {
                'total_signals': len(self.signals),
                'closed_signals': 0,
                'active_signals': len(self.active_signals),
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'total_pnl': 0.0,
            }

        wins = [s for s in closed_signals if s.outcome == 'TP']
        losses = [s for s in closed_signals if s.outcome == 'SL']

        total_pnl = sum(s.pnl for s in closed_signals)
        avg_pnl = total_pnl / len(closed_signals)
        win_rate = len(wins) / len(closed_signals)

        return {
            'total_signals': len(self.signals),
            'closed_signals': len(closed_signals),
            'active_signals': len(self.active_signals),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'total_pnl': total_pnl,
        }
