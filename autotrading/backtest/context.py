"""
Execution context for strategies with Point-in-Time data access guarantee.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import pandas as pd

from .position import Position, Account


class Context(ABC):
    """
    Abstract execution context interface.

    Provides strategies with access to:
    - Historical market data (Point-in-Time guaranteed)
    - Current position and account information
    - Current simulation/trading time

    Both backtesting and live trading implement this interface,
    allowing strategies to work seamlessly in both environments.
    """

    @abstractmethod
    def get_history(self, lookback: Optional[int] = None) -> pd.DataFrame:
        """
        Get historical market data up to current time (Point-in-Time guaranteed).

        Args:
            lookback: Number of bars to return (None = all available history)

        Returns:
            DataFrame with columns [open, high, low, close, volume]
            and datetime index. NEVER includes future data.

        Example:
            # Get last 20 bars
            recent = context.get_history(lookback=20)

            # Get all available history
            all_data = context.get_history()
        """
        pass

    @property
    @abstractmethod
    def position(self) -> Optional[Position]:
        """
        Get current position.

        Returns:
            Current position if exists, None otherwise
        """
        pass

    @property
    @abstractmethod
    def account(self) -> Account:
        """
        Get account information.

        Returns:
            Account object with balance, equity, etc.
        """
        pass

    @property
    @abstractmethod
    def current_time(self) -> datetime:
        """
        Get current simulation or trading time.

        Returns:
            Current datetime
        """
        pass


class BacktestContext(Context):
    """
    Backtesting execution context with strict Point-in-Time enforcement.

    This context ensures that strategies can only access data up to the current
    simulation time, preventing look-ahead bias.
    """

    def __init__(self, data: pd.DataFrame, account: Account):
        """
        Initialize backtest context.

        Args:
            data: Full dataset (will be accessed in PIT manner)
            account: Account object to track
        """
        self._data = data
        self._account = account
        self._current_index = 0
        self._position: Optional[Position] = None

    def update(self, index: int, position: Optional[Position] = None):
        """
        Update context to current time step (called by BacktestEngine).

        Args:
            index: Current bar index in the dataset
            position: Current position (if any)
        """
        self._current_index = index
        self._position = position

        # Update position price if exists
        if self._position and index < len(self._data):
            current_bar = self._data.iloc[index]
            self._position.update_price(current_bar['close'])

        # Update account equity
        self._account.update_equity(self._position)

    def get_history(self, lookback: Optional[int] = None) -> pd.DataFrame:
        """
        Get historical data up to current index (Point-in-Time guaranteed).

        Args:
            lookback: Number of bars to return (None = all history up to now)

        Returns:
            DataFrame with historical data (NEVER includes future data)
        """
        if self._current_index == 0:
            # At first bar, return empty DataFrame with correct columns
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

        # Get data up to (but not including) current index
        # This ensures we only see data that would have been available
        history = self._data.iloc[:self._current_index]

        if lookback is not None and lookback > 0:
            # Return only last N bars
            history = history.iloc[-lookback:]

        return history.copy()

    @property
    def position(self) -> Optional[Position]:
        """Get current position."""
        return self._position

    @property
    def account(self) -> Account:
        """Get account information."""
        return self._account

    @property
    def current_time(self) -> datetime:
        """Get current simulation time."""
        if self._current_index < len(self._data):
            return self._data.index[self._current_index]
        return datetime.now()

    @property
    def current_bar_index(self) -> int:
        """Get current bar index (for debugging)."""
        return self._current_index

    def __repr__(self) -> str:
        return (f"BacktestContext(time={self.current_time}, "
                f"index={self._current_index}/{len(self._data)}, "
                f"position={self._position is not None})")
