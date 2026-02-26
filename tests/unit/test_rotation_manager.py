"""Unit tests for RotationManager."""
from datetime import datetime, timezone

import pytest

from autotrader.core.config import RotationConfig
from autotrader.core.types import Signal
from autotrader.rotation.manager import RotationManager
from autotrader.rotation.types import WatchlistEntry
from autotrader.universe import UniverseResult


def _signal(symbol: str, direction: str, strategy: str = "test") -> Signal:
    return Signal(strategy=strategy, symbol=symbol, direction=direction, strength=1.0)


class TestFilterSignals:
    def setup_method(self):
        self.mgr = RotationManager(RotationConfig())
        self.mgr._state.active_symbols = ["AAPL", "MSFT"]
        self.mgr._state.watchlist = {
            "GOOG": WatchlistEntry(
                symbol="GOOG",
                added_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
                deadline=datetime(2026, 3, 13, 14, 0, tzinfo=timezone.utc),
            ),
        }

    def test_allows_close_for_any_symbol(self):
        signals = [_signal("GOOG", "close")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 1
        assert result[0].direction == "close"

    def test_allows_close_for_active_symbol(self):
        signals = [_signal("AAPL", "close")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 1

    def test_allows_entry_for_active_symbol(self):
        signals = [_signal("AAPL", "long")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 1

    def test_allows_short_for_active_symbol(self):
        signals = [_signal("MSFT", "short")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 1

    def test_blocks_entry_for_watchlist_symbol(self):
        signals = [_signal("GOOG", "long")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 0

    def test_blocks_entry_for_unknown_symbol(self):
        signals = [_signal("TSLA", "long")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 0

    def test_blocks_all_entries_when_halted(self):
        self.mgr._state.is_halted = True
        signals = [_signal("AAPL", "long"), _signal("AAPL", "close")]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 1
        assert result[0].direction == "close"

    def test_mixed_signals_filtering(self):
        signals = [
            _signal("AAPL", "long"),   # active -> pass
            _signal("GOOG", "long"),   # watchlist -> block
            _signal("GOOG", "close"),  # close -> pass
            _signal("TSLA", "short"),  # unknown -> block
            _signal("MSFT", "close"),  # close -> pass
        ]
        result = self.mgr.filter_signals(signals)
        assert len(result) == 3
        symbols_directions = [(s.symbol, s.direction) for s in result]
        assert ("AAPL", "long") in symbols_directions
        assert ("GOOG", "close") in symbols_directions
        assert ("MSFT", "close") in symbols_directions

    def test_empty_signals(self):
        result = self.mgr.filter_signals([])
        assert result == []

    def test_properties(self):
        assert set(self.mgr.active_symbols) == {"AAPL", "MSFT"}
        assert set(self.mgr.watchlist_symbols) == {"GOOG"}


class TestApplyRotation:
    def test_moves_held_symbols_to_watchlist(self):
        mgr = RotationManager(RotationConfig())
        mgr._state.active_symbols = ["AAPL", "MSFT", "GOOG"]
        universe = UniverseResult(
            symbols=["AAPL", "MSFT", "AMZN"],
            scored=[],
            timestamp=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
            rotation_in=["AMZN"],
            rotation_out=["GOOG"],
        )
        event = mgr.apply_rotation(universe, open_position_symbols=["GOOG"])
        assert "GOOG" in mgr.watchlist_symbols
        assert "GOOG" in event.watchlist_added
        assert set(mgr.active_symbols) == {"AAPL", "MSFT", "AMZN"}

    def test_drops_unheld_symbols(self):
        mgr = RotationManager(RotationConfig())
        mgr._state.active_symbols = ["AAPL", "GOOG"]
        universe = UniverseResult(
            symbols=["AAPL", "MSFT"],
            scored=[],
            timestamp=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
            rotation_in=["MSFT"],
            rotation_out=["GOOG"],
        )
        event = mgr.apply_rotation(universe, open_position_symbols=[])
        assert "GOOG" not in mgr.watchlist_symbols
        assert len(event.watchlist_added) == 0

    def test_computes_deadline_next_friday(self):
        mgr = RotationManager(RotationConfig())
        # Saturday March 7, 2026 rotation
        sat = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
        universe = UniverseResult(
            symbols=["AAPL"],
            scored=[],
            timestamp=sat,
            rotation_in=[],
            rotation_out=["MSFT"],
        )
        mgr._state.active_symbols = ["MSFT"]
        mgr.apply_rotation(universe, open_position_symbols=["MSFT"])
        entry = mgr._state.watchlist["MSFT"]
        # Deadline should be Friday March 13, 14:00 UTC
        assert entry.deadline.weekday() == 4  # Friday
        assert entry.deadline.hour == 14

    def test_clears_previous_watchlist_if_symbol_returns(self):
        mgr = RotationManager(RotationConfig())
        mgr._state.active_symbols = ["AAPL"]
        mgr._state.watchlist = {
            "GOOG": WatchlistEntry(
                symbol="GOOG",
                added_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                deadline=datetime(2026, 3, 6, 14, 0, tzinfo=timezone.utc),
            ),
        }
        universe = UniverseResult(
            symbols=["AAPL", "GOOG"],
            scored=[],
            timestamp=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
            rotation_in=["GOOG"],
            rotation_out=[],
        )
        event = mgr.apply_rotation(universe, open_position_symbols=["GOOG"])
        # GOOG should no longer be on watchlist since it's back in active
        assert "GOOG" not in mgr.watchlist_symbols
        assert "GOOG" in event.watchlist_removed
        assert "GOOG" in mgr.active_symbols

    def test_records_event_in_history(self):
        mgr = RotationManager(RotationConfig())
        mgr._state.active_symbols = ["AAPL"]
        universe = UniverseResult(
            symbols=["AAPL", "MSFT"],
            scored=[],
            timestamp=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
            rotation_in=["MSFT"],
            rotation_out=[],
        )
        event = mgr.apply_rotation(universe, open_position_symbols=[])
        assert len(mgr._state.rotation_history) == 1
        assert mgr._state.rotation_history[0] is event

    def test_updates_last_rotation(self):
        mgr = RotationManager(RotationConfig())
        ts = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
        universe = UniverseResult(
            symbols=["AAPL"],
            scored=[],
            timestamp=ts,
            rotation_in=[],
            rotation_out=[],
        )
        mgr.apply_rotation(universe, open_position_symbols=[])
        assert mgr._state.last_rotation == ts

    def test_resets_halt_on_new_rotation(self):
        mgr = RotationManager(RotationConfig())
        mgr._state.is_halted = True
        mgr._state.active_symbols = ["AAPL"]
        universe = UniverseResult(
            symbols=["AAPL"],
            scored=[],
            timestamp=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
            rotation_in=[],
            rotation_out=[],
        )
        mgr.apply_rotation(universe, open_position_symbols=[], new_equity=3000.0)
        assert mgr._state.is_halted is False
        assert mgr._state.weekly_start_equity == 3000.0
