"""
Time-Based Performance Scorer

Calculates trigger performance scores based on time windows and regime.
Uses exponential decay to emphasize recent performance.
"""

from typing import List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

from .virtual_signal_tracker import SignalRecord


class TimeBasedScorer:
    """
    Time-based performance scoring with exponential decay.

    Features:
    - Rolling time window (30 minutes default)
    - Exponential decay (recent data more important)
    - Time + Regime dimension
    - Minimum sample requirement
    """

    def __init__(
        self,
        window_minutes: int = 30,
        decay_days: int = 30,
        decay_lambda: float = 0.1,
        min_samples: int = 10,
        default_score: float = 0.5,
    ):
        """
        Initialize scorer.

        Args:
            window_minutes: Rolling time window size
            decay_days: Maximum days to look back
            decay_lambda: Exponential decay rate
            min_samples: Minimum signals required for reliable score
            default_score: Default score when insufficient data
        """
        self.window_minutes = window_minutes
        self.decay_days = decay_days
        self.decay_lambda = decay_lambda
        self.min_samples = min_samples
        self.default_score = default_score

    def calculate_score(
        self,
        trigger_name: str,
        current_time: datetime,
        current_regime: str,
        signal_history: List[SignalRecord],
    ) -> float:
        """
        Calculate performance score for trigger at current time + regime.

        Args:
            trigger_name: Trigger to score
            current_time: Current timestamp
            current_regime: Current regime (TREND or RANGE)
            signal_history: All historical signals

        Returns:
            score: PnL per signal (exponentially weighted)
        """
        # 1. Get time window
        time_window = self._get_time_window(current_time)

        # 2. Filter relevant signals
        relevant_signals = self._filter_signals(
            signal_history=signal_history,
            trigger_name=trigger_name,
            regime=current_regime,
            time_window=time_window,
            current_time=current_time,
        )

        # 3. Check minimum samples
        if len(relevant_signals) < self.min_samples:
            return self.default_score

        # 4. Calculate weighted score
        total_pnl = 0.0
        total_weight = 0.0

        for sig in relevant_signals:
            # Exponential decay weight
            days_ago = (current_time - sig['timestamp']).total_seconds() / 86400
            weight = np.exp(-self.decay_lambda * days_ago)

            total_pnl += sig['pnl'] * weight
            total_weight += weight

        # 5. Normalize
        if total_weight == 0:
            return self.default_score

        score = total_pnl / total_weight

        return score

    def _get_time_window(self, timestamp: datetime) -> Tuple[datetime, datetime]:
        """
        Get rolling time window.

        Args:
            timestamp: Current time

        Returns:
            (start_time, end_time) tuple
        """
        end_time = timestamp
        start_time = end_time - timedelta(minutes=self.window_minutes)
        return (start_time, end_time)

    def _filter_signals(
        self,
        signal_history: List[SignalRecord],
        trigger_name: str,
        regime: str,
        time_window: Tuple[datetime, datetime],
        current_time: datetime,
    ) -> List[dict]:
        """
        Filter signals by trigger, regime, and time window.

        Args:
            signal_history: All signals
            trigger_name: Filter by trigger
            regime: Filter by regime
            time_window: Time window to match
            current_time: Current time

        Returns:
            List of relevant signals with metadata
        """
        start_window, end_window = time_window
        cutoff_time = current_time - timedelta(days=self.decay_days)

        relevant = []

        for record in signal_history:
            # Skip if not closed yet
            if record.outcome is None:
                continue

            # Filter by trigger
            if record.trigger_name != trigger_name:
                continue

            # Filter by regime
            if record.regime != regime:
                continue

            # Filter by decay cutoff
            if record.timestamp < cutoff_time:
                continue

            # Check if signal's time window overlaps with current window
            sig_window = self._get_time_window(record.timestamp)
            if self._windows_overlap(time_window, sig_window):
                relevant.append({
                    'timestamp': record.timestamp,
                    'pnl': record.pnl,
                })

        return relevant

    def _windows_overlap(
        self,
        window1: Tuple[datetime, datetime],
        window2: Tuple[datetime, datetime]
    ) -> bool:
        """
        Check if two time windows overlap.

        Args:
            window1: (start1, end1)
            window2: (start2, end2)

        Returns:
            True if windows overlap
        """
        start1, end1 = window1
        start2, end2 = window2

        return not (end1 < start2 or end2 < start1)

    def get_all_scores(
        self,
        trigger_names: List[str],
        current_time: datetime,
        current_regime: str,
        signal_history: List[SignalRecord],
    ) -> dict:
        """
        Calculate scores for all triggers.

        Args:
            trigger_names: List of trigger names
            current_time: Current timestamp
            current_regime: Current regime
            signal_history: Signal history

        Returns:
            {trigger_name: score}
        """
        scores = {}

        for trigger_name in trigger_names:
            score = self.calculate_score(
                trigger_name=trigger_name,
                current_time=current_time,
                current_regime=current_regime,
                signal_history=signal_history,
            )
            scores[trigger_name] = score

        return scores
