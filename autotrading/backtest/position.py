"""
Position and Account models for portfolio management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
from decimal import Decimal

from .orders import Order, OrderSide


class PositionSide(Enum):
    """Position side enumeration."""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """
    Represents a trading position (single instrument).

    Assumes only one position can be held at a time (either LONG or SHORT, not both).
    """
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    entry_commission: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized profit/loss."""
        if self.side == PositionSide.LONG:
            pnl = (self.current_price - self.entry_price) * self.quantity
        else:  # SHORT
            pnl = (self.entry_price - self.current_price) * self.quantity

        return pnl - self.entry_commission

    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized profit/loss percentage."""
        if self.entry_price == 0:
            return 0.0
        return (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100

    def update_price(self, price: float):
        """Update current market price."""
        self.current_price = price

    def __repr__(self) -> str:
        """String representation of the position."""
        return (f"Position({self.side.value} {self.quantity} {self.symbol} @ {self.entry_price:.2f}, "
                f"current={self.current_price:.2f}, PnL={self.unrealized_pnl:.2f})")


@dataclass
class Trade:
    """
    Represents a completed trade (entry + exit).
    """
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: datetime
    exit_price: float
    exit_time: datetime
    entry_commission: float
    exit_commission: float
    pnl: float
    pnl_pct: float

    def __repr__(self) -> str:
        """String representation of the trade."""
        return (f"Trade({self.side.value} {self.quantity} {self.symbol}, "
                f"entry={self.entry_price:.2f}, exit={self.exit_price:.2f}, "
                f"PnL={self.pnl:.2f} ({self.pnl_pct:.2f}%))")


@dataclass
class Account:
    """
    Represents a trading account with balance tracking.
    """
    initial_balance: float
    balance: float
    equity: float = 0.0
    total_commission: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    peak_equity: float = 0.0
    trades: List[Trade] = field(default_factory=list)

    def __post_init__(self):
        """Initialize derived fields."""
        if self.equity == 0.0:
            self.equity = self.balance
        if self.peak_equity == 0.0:
            self.peak_equity = self.balance

    def update_equity(self, position: Optional[Position] = None):
        """
        Update account equity based on current position.

        Args:
            position: Current position (if any)
        """
        if position:
            self.equity = self.balance + position.unrealized_pnl
        else:
            self.equity = self.balance

        # Update peak equity for drawdown calculation
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

    def add_commission(self, commission: float):
        """Add commission cost."""
        self.total_commission += commission
        self.balance -= commission

    def close_trade(self, trade: Trade):
        """
        Record a closed trade and update account.

        Args:
            trade: Completed trade
        """
        self.trades.append(trade)
        self.total_trades += 1
        self.balance += trade.pnl
        self.total_pnl += trade.pnl

        if trade.pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        self.update_equity()

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def total_return(self) -> float:
        """Calculate total return percentage."""
        if self.initial_balance == 0:
            return 0.0
        return ((self.equity - self.initial_balance) / self.initial_balance) * 100

    @property
    def max_drawdown(self) -> float:
        """Calculate maximum drawdown percentage."""
        if self.peak_equity == 0:
            return 0.0
        drawdown = ((self.peak_equity - self.equity) / self.peak_equity) * 100
        return max(0.0, drawdown)

    def __repr__(self) -> str:
        """String representation of the account."""
        return (f"Account(balance={self.balance:.2f}, equity={self.equity:.2f}, "
                f"PnL={self.total_pnl:.2f}, trades={self.total_trades}, "
                f"win_rate={self.win_rate:.1f}%)")
