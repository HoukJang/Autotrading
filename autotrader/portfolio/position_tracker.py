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

# Backward-compatible alias: code that imports TrackedPosition from this
# module continues to work unchanged.  Will be removed in a future cleanup.
TrackedPosition = HeldPosition

_ET = ZoneInfo("America/New_York")


class OpenPositionTracker:
    """Tracks open positions for MFE/MAE calculation.

    Maintains a dictionary of HeldPosition instances keyed by symbol.
    Each bar, call update_prices() to track high/low extremes.
    On close, call close_position() to retrieve the final HeldPosition
    with computed MFE/MAE values.
    """

    def __init__(self) -> None:
        self._positions: dict[str, HeldPosition] = {}

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

        self._positions[symbol] = HeldPosition(
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

    def add_position(self, position: HeldPosition) -> None:
        """Register an existing HeldPosition for MFE/MAE tracking.

        Preferred over ``open_position()`` when a fully-constructed
        HeldPosition is already available (e.g. from EntryManager).

        Args:
            position: A HeldPosition to track.
        """
        self._positions[position.symbol] = position

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
        pos = self._positions.get(symbol)
        if pos is not None:
            pos.update(high, low, close)

    def close_position(self, symbol: str) -> HeldPosition | None:
        """Remove and return the tracked position on close.

        Args:
            symbol: Ticker symbol to close.

        Returns:
            The HeldPosition with final MFE/MAE data, or None if not tracked.
        """
        return self._positions.pop(symbol, None)

    def has_position(self, symbol: str) -> bool:
        """Check if a symbol is currently being tracked."""
        return symbol in self._positions

    def get_position(self, symbol: str) -> HeldPosition | None:
        """Get the tracked position without removing it.

        Args:
            symbol: Ticker symbol.

        Returns:
            The HeldPosition if tracked, None otherwise.
        """
        return self._positions.get(symbol)

    @property
    def open_symbols(self) -> list[str]:
        """List all currently tracked symbol names."""
        return list(self._positions.keys())
