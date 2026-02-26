"""Unit tests for RotationManager."""
from datetime import datetime, timezone

import pytest

from autotrader.core.config import RotationConfig
from autotrader.core.types import Signal
from autotrader.rotation.manager import RotationManager
from autotrader.rotation.types import WatchlistEntry


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
