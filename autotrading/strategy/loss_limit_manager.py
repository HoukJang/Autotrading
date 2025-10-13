"""
Loss Limit Manager

Manages trading pauses based on consecutive losses.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class TradeResult:
    """Record of a trade result."""
    timestamp: datetime
    outcome: str  # 'TP' or 'SL'
    pnl: float


class LossLimitManager:
    """
    Manages trading pauses after consecutive losses.

    Features:
    - Tracks consecutive loss count
    - Pauses trading after N consecutive losses
    - Automatically resumes after pause period
    - Score calculation continues during pause
    """

    def __init__(
        self,
        max_consecutive_losses: int = 3,
        pause_minutes: int = 30,
    ):
        """
        Initialize loss limit manager.

        Args:
            max_consecutive_losses: Pause after this many consecutive losses
            pause_minutes: Pause duration in minutes
        """
        self.max_consecutive_losses = max_consecutive_losses
        self.pause_minutes = pause_minutes

        self.consecutive_losses = 0
        self.pause_until: Optional[datetime] = None
        self.trade_history: list = []

    def record_trade(self, timestamp: datetime, outcome: str, pnl: float):
        """
        Record a trade outcome.

        Args:
            timestamp: Trade timestamp
            outcome: 'TP' or 'SL'
            pnl: Profit/loss
        """
        result = TradeResult(
            timestamp=timestamp,
            outcome=outcome,
            pnl=pnl,
        )

        self.trade_history.append(result)

        # Update consecutive loss count
        if outcome == 'SL':
            self.consecutive_losses += 1

            # Check if pause needed
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.pause_until = timestamp + timedelta(minutes=self.pause_minutes)

        elif outcome == 'TP':
            # Reset consecutive losses on win
            self.consecutive_losses = 0
            self.pause_until = None  # Cancel any pause

    def can_trade(self, current_time: datetime) -> bool:
        """
        Check if trading is allowed.

        Args:
            current_time: Current timestamp

        Returns:
            True if trading is allowed
        """
        # Check if paused
        if self.pause_until is not None:
            if current_time < self.pause_until:
                return False
            else:
                # Pause period ended
                self.pause_until = None
                self.consecutive_losses = 0

        return True

    def get_status(self, current_time: datetime) -> dict:
        """
        Get current status.

        Args:
            current_time: Current timestamp

        Returns:
            Status dictionary
        """
        is_paused = not self.can_trade(current_time)

        status = {
            'consecutive_losses': self.consecutive_losses,
            'is_paused': is_paused,
            'pause_until': self.pause_until,
            'total_trades': len(self.trade_history),
        }

        if is_paused and self.pause_until:
            time_remaining = (self.pause_until - current_time).total_seconds() / 60
            status['pause_minutes_remaining'] = max(0, time_remaining)

        return status

    def reset(self):
        """Reset all counters and pause state."""
        self.consecutive_losses = 0
        self.pause_until = None

    def get_recent_performance(self, lookback_count: int = 10) -> dict:
        """
        Get recent trade performance.

        Args:
            lookback_count: Number of recent trades to analyze

        Returns:
            Performance statistics
        """
        recent_trades = self.trade_history[-lookback_count:]

        if len(recent_trades) == 0:
            return {
                'count': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
            }

        wins = [t for t in recent_trades if t.outcome == 'TP']
        losses = [t for t in recent_trades if t.outcome == 'SL']

        total_pnl = sum(t.pnl for t in recent_trades)
        win_rate = len(wins) / len(recent_trades)

        return {
            'count': len(recent_trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
        }
