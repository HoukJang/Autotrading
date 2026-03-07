"""Position lifecycle tracking with MFE/MAE calculation.

Tracks open positions bar-by-bar to compute Maximum Favorable Excursion (MFE),
Maximum Adverse Excursion (MAE), and exit reason metadata for strategy optimization.

Uses the unified ``HeldPosition`` type from ``autotrader.trading.types``.
The former ``TrackedPosition`` dataclass has been merged into ``HeldPosition``
and is re-exported here as a type alias for backward compatibility.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from zoneinfo import ZoneInfo

from autotrader.trading.types import HeldPosition
from autotrader.trading.position_book import PositionBook

# Backward-compatible alias: code that imports TrackedPosition from this
# module continues to work unchanged.  Will be removed in a future cleanup.
TrackedPosition = HeldPosition

_ET = ZoneInfo("America/New_York")


class OpenPositionTracker:
    """Tracks open positions for MFE/MAE calculation.

    Delegates storage to a shared PositionBook (single source of truth).
    Each bar, call update_prices() to track high/low extremes.
    On close, call close_position() to retrieve the final HeldPosition
    with computed MFE/MAE values.
    """

    def __init__(self, position_book: PositionBook | None = None) -> None:
        # Delegate to shared PositionBook. When no book is injected
        # (backward compat / standalone tests), create a private one.
        # Note: cannot use ``position_book or PositionBook()`` because an
        # empty PositionBook is falsy due to __len__ returning 0.
        self._position_book: PositionBook = position_book if position_book is not None else PositionBook()

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

        This method preserves the original TrackedPosition construction
        interface.  The ``entry_time`` datetime is converted to a
        US/Eastern date for ``entry_date_et`` and also stored as
        ``_entry_time`` for callers that need the full datetime.

        Args:
            symbol: Ticker symbol.
            strategy: Strategy that generated the entry signal.
            direction: "long" or "short".
            entry_price: Execution price at entry.
            entry_time: Datetime of entry (UTC recommended).
            quantity: Number of shares.
        """
        # Derive entry_date_et from entry_time
        if entry_time.tzinfo is not None:
            entry_date_et = entry_time.astimezone(_ET).date()
        else:
            # Assume UTC if naive
            entry_date_et = entry_time.replace(tzinfo=timezone.utc).astimezone(_ET).date()

        held = HeldPosition(
            symbol=symbol,
            strategy=strategy,
            direction=direction,  # type: ignore[arg-type]
            entry_price=entry_price,
            entry_atr=0.0,  # Not available from tracker context
            entry_date_et=entry_date_et,
            qty=quantity,
            highest_price=entry_price,
            lowest_price=entry_price,
            _entry_time=entry_time,
        )
        self._position_book.add(held)

    def add_position(self, position: HeldPosition) -> None:
        """Register an existing HeldPosition for MFE/MAE tracking.

        Preferred over ``open_position()`` when a fully-constructed
        HeldPosition is already available (e.g. from EntryManager).

        Delegates to PositionBook.add(). If the position is already
        in the book (added by another subsystem), this is a no-op.

        Args:
            position: A HeldPosition to track.
        """
        if not self._position_book.has(position.symbol):
            self._position_book.add(position)

    def update_prices(
        self, symbol: str, high: float, low: float, close: float
    ) -> None:
        """Update price extremes for an open position.

        No-op if the symbol is not being tracked.

        Args:
            symbol: Ticker symbol.
            high: Bar high price.
            low: Bar low price.
            close: Bar close price (reserved for future use).
        """
        self._position_book.update_prices(symbol, high, low, close)

    def close_position(self, symbol: str) -> HeldPosition | None:
        """Remove and return the tracked position on close.

        Args:
            symbol: Ticker symbol to close.

        Returns:
            The HeldPosition with final MFE/MAE data, or None if not tracked.
        """
        return self._position_book.close_position(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if a symbol is currently being tracked."""
        return self._position_book.has_position(symbol)

    def get_position(self, symbol: str) -> HeldPosition | None:
        """Get the tracked position without removing it.

        Args:
            symbol: Ticker symbol.

        Returns:
            The HeldPosition if tracked, None otherwise.
        """
        return self._position_book.get_position(symbol)

    @property
    def open_symbols(self) -> list[str]:
        """List all currently tracked symbol names."""
        return self._position_book.open_symbols
