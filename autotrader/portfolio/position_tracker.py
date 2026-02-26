"""Position lifecycle tracking with MFE/MAE calculation.

Tracks open positions bar-by-bar to compute Maximum Favorable Excursion (MFE),
Maximum Adverse Excursion (MAE), and exit reason metadata for strategy optimization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TrackedPosition:
    """A single tracked position with price extreme tracking.

    Attributes:
        symbol: Ticker symbol.
        strategy: Strategy name that opened the position.
        direction: "long" or "short".
        entry_price: Price at entry.
        entry_time: Datetime when the position was opened.
        quantity: Number of shares.
        highest_price: Highest price observed since entry.
        lowest_price: Lowest price observed since entry.
        bar_count: Number of bars elapsed since entry.
    """

    symbol: str
    strategy: str
    direction: str  # "long" or "short"
    entry_price: float
    entry_time: datetime
    quantity: float
    highest_price: float = 0.0
    lowest_price: float = float("inf")
    bar_count: int = 0

    def update(self, high: float, low: float, close: float) -> None:
        """Update with new bar data.

        Args:
            high: Bar high price.
            low: Bar low price.
            close: Bar close price (reserved for future use).
        """
        self.highest_price = max(self.highest_price, high)
        self.lowest_price = min(self.lowest_price, low)
        self.bar_count += 1

    @property
    def mfe(self) -> float:
        """Maximum Favorable Excursion (best unrealized profit %).

        For long positions: (highest - entry) / entry
        For short positions: (entry - lowest) / entry
        """
        if self.direction == "long":
            return (self.highest_price - self.entry_price) / self.entry_price
        else:  # short
            return (self.entry_price - self.lowest_price) / self.entry_price

    @property
    def mae(self) -> float:
        """Maximum Adverse Excursion (worst unrealized loss %).

        For long positions: (entry - lowest) / entry
        For short positions: (highest - entry) / entry
        """
        if self.direction == "long":
            return (self.entry_price - self.lowest_price) / self.entry_price
        else:  # short
            return (self.highest_price - self.entry_price) / self.entry_price


class OpenPositionTracker:
    """Tracks open positions for MFE/MAE calculation.

    Maintains a dictionary of TrackedPosition instances keyed by symbol.
    Each bar, call update_prices() to track high/low extremes.
    On close, call close_position() to retrieve the final TrackedPosition
    with computed MFE/MAE values.
    """

    def __init__(self) -> None:
        self._positions: dict[str, TrackedPosition] = {}

    def open_position(
        self,
        symbol: str,
        strategy: str,
        direction: str,
        entry_price: float,
        entry_time: datetime,
        quantity: float,
    ) -> None:
        """Register a new open position for tracking.

        Args:
            symbol: Ticker symbol.
            strategy: Strategy that generated the entry signal.
            direction: "long" or "short".
            entry_price: Execution price at entry.
            entry_time: Datetime of entry.
            quantity: Number of shares.
        """
        self._positions[symbol] = TrackedPosition(
            symbol=symbol,
            strategy=strategy,
            direction=direction,
            entry_price=entry_price,
            entry_time=entry_time,
            quantity=quantity,
            highest_price=entry_price,
            lowest_price=entry_price,
        )

    def update_prices(
        self, symbol: str, high: float, low: float, close: float
    ) -> None:
        """Update price extremes for an open position.

        No-op if the symbol is not being tracked.

        Args:
            symbol: Ticker symbol.
            high: Bar high price.
            low: Bar low price.
            close: Bar close price.
        """
        if symbol in self._positions:
            self._positions[symbol].update(high, low, close)

    def close_position(self, symbol: str) -> TrackedPosition | None:
        """Remove and return the tracked position on close.

        Args:
            symbol: Ticker symbol to close.

        Returns:
            The TrackedPosition with final MFE/MAE data, or None if not tracked.
        """
        return self._positions.pop(symbol, None)

    def has_position(self, symbol: str) -> bool:
        """Check if a symbol is currently being tracked."""
        return symbol in self._positions

    def get_position(self, symbol: str) -> TrackedPosition | None:
        """Get the tracked position without removing it.

        Args:
            symbol: Ticker symbol.

        Returns:
            The TrackedPosition if tracked, None otherwise.
        """
        return self._positions.get(symbol)

    @property
    def open_symbols(self) -> list[str]:
        """List all currently tracked symbol names."""
        return list(self._positions.keys())
