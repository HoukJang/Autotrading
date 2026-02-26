"""Rotation data types for watchlist and rotation state management."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WatchlistEntry:
    """A symbol on the watchlist waiting for position exit or force close."""

    symbol: str
    added_at: datetime
    deadline: datetime
    reason: str = "rotation"

    def is_past_deadline(self, current_time: datetime) -> bool:
        """Check if the current time is at or past the deadline."""
        return current_time >= self.deadline


@dataclass
class RotationEvent:
    """Record of a single rotation event."""

    timestamp: datetime
    symbols_in: list[str]
    symbols_out: list[str]
    watchlist_added: list[str]
    watchlist_removed: list[str]
    active_count: int
    watchlist_count: int


@dataclass
class RotationState:
    """Mutable state for the rotation manager."""

    active_symbols: list[str] = field(default_factory=list)
    watchlist: dict[str, WatchlistEntry] = field(default_factory=dict)
    last_rotation: datetime | None = None
    weekly_start_equity: float = 0.0
    is_halted: bool = False
    rotation_history: list[RotationEvent] = field(default_factory=list)
