"""Unit tests for rotation types."""
from datetime import datetime, timezone

import pytest

from autotrader.rotation.types import WatchlistEntry, RotationState, RotationEvent


class TestWatchlistEntry:
    def test_creation(self):
        now = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 3, 13, 19, 0, tzinfo=timezone.utc)
        entry = WatchlistEntry(symbol="AAPL", added_at=now, deadline=deadline)
        assert entry.symbol == "AAPL"
        assert entry.reason == "rotation"

    def test_is_past_deadline_before(self):
        deadline = datetime(2026, 3, 13, 19, 0, tzinfo=timezone.utc)
        entry = WatchlistEntry(
            symbol="AAPL",
            added_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
            deadline=deadline,
        )
        before = datetime(2026, 3, 13, 18, 0, tzinfo=timezone.utc)
        assert not entry.is_past_deadline(before)

    def test_is_past_deadline_after(self):
        deadline = datetime(2026, 3, 13, 19, 0, tzinfo=timezone.utc)
        entry = WatchlistEntry(
            symbol="AAPL",
            added_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
            deadline=deadline,
        )
        after = datetime(2026, 3, 13, 20, 0, tzinfo=timezone.utc)
        assert entry.is_past_deadline(after)

    def test_is_past_deadline_exact(self):
        deadline = datetime(2026, 3, 13, 19, 0, tzinfo=timezone.utc)
        entry = WatchlistEntry(
            symbol="AAPL",
            added_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
            deadline=deadline,
        )
        assert entry.is_past_deadline(deadline)

    def test_custom_reason(self):
        entry = WatchlistEntry(
            symbol="MSFT",
            added_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
            deadline=datetime(2026, 3, 13, tzinfo=timezone.utc),
            reason="earnings",
        )
        assert entry.reason == "earnings"


class TestRotationState:
    def test_initial_empty(self):
        state = RotationState()
        assert state.active_symbols == []
        assert state.watchlist == {}
        assert state.is_halted is False
        assert state.last_rotation is None
        assert state.weekly_start_equity == 0.0
        assert state.rotation_history == []

    def test_mutable(self):
        state = RotationState()
        state.active_symbols.append("AAPL")
        state.is_halted = True
        assert "AAPL" in state.active_symbols
        assert state.is_halted is True


class TestRotationEvent:
    def test_creation(self):
        event = RotationEvent(
            timestamp=datetime.now(timezone.utc),
            symbols_in=["AAPL"],
            symbols_out=["MSFT"],
            watchlist_added=["MSFT"],
            watchlist_removed=[],
            active_count=15,
            watchlist_count=1,
        )
        assert event.symbols_in == ["AAPL"]
        assert event.symbols_out == ["MSFT"]
        assert event.watchlist_added == ["MSFT"]
        assert event.active_count == 15
        assert event.watchlist_count == 1
