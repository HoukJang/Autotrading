"""Tests for position lifecycle tracking with MFE/MAE calculation."""
from datetime import datetime

import pytest

from autotrader.portfolio.position_tracker import OpenPositionTracker, TrackedPosition


class TestTrackedPosition:
    """Unit tests for TrackedPosition dataclass and computed properties."""

    def _make_position(
        self, direction: str = "long", entry_price: float = 100.0
    ) -> TrackedPosition:
        return TrackedPosition(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            direction=direction,
            entry_price=entry_price,
            entry_time=datetime(2026, 1, 15, 9, 30),
            quantity=10,
            highest_price=entry_price,
            lowest_price=entry_price,
        )

    def test_mfe_long_position(self):
        """Long: highest goes to +10%, MFE = 10%."""
        pos = self._make_position("long", entry_price=100.0)
        # Price rises to 110, dips to 95
        pos.update(high=105.0, low=98.0, close=103.0)
        pos.update(high=110.0, low=101.0, close=108.0)
        assert pos.mfe == pytest.approx(0.10)

    def test_mae_long_position(self):
        """Long: lowest goes to -5%, MAE = 5%."""
        pos = self._make_position("long", entry_price=100.0)
        # Price dips to 95
        pos.update(high=102.0, low=95.0, close=99.0)
        pos.update(high=104.0, low=97.0, close=103.0)
        assert pos.mae == pytest.approx(0.05)

    def test_mfe_short_position(self):
        """Short: lowest goes to -8%, MFE = 8%."""
        pos = self._make_position("short", entry_price=100.0)
        # Price drops to 92
        pos.update(high=101.0, low=95.0, close=96.0)
        pos.update(high=97.0, low=92.0, close=93.0)
        assert pos.mfe == pytest.approx(0.08)

    def test_mae_short_position(self):
        """Short: highest goes to +3%, MAE = 3%."""
        pos = self._make_position("short", entry_price=100.0)
        # Price rises to 103 against short
        pos.update(high=103.0, low=99.0, close=101.0)
        pos.update(high=102.0, low=96.0, close=97.0)
        assert pos.mae == pytest.approx(0.03)

    def test_update_prices_tracks_extremes(self):
        """Multiple updates correctly track max high and min low."""
        pos = self._make_position("long", entry_price=100.0)
        pos.update(high=105.0, low=98.0, close=102.0)
        pos.update(high=103.0, low=96.0, close=100.0)
        pos.update(high=112.0, low=99.0, close=110.0)
        pos.update(high=108.0, low=94.0, close=106.0)
        assert pos.highest_price == 112.0
        assert pos.lowest_price == 94.0

    def test_bar_count_increments(self):
        """Each update call increments bar_count by 1."""
        pos = self._make_position("long")
        assert pos.bar_count == 0
        pos.update(high=101.0, low=99.0, close=100.0)
        assert pos.bar_count == 1
        pos.update(high=102.0, low=98.0, close=101.0)
        assert pos.bar_count == 2
        pos.update(high=103.0, low=97.0, close=100.0)
        assert pos.bar_count == 3

    def test_mfe_mae_at_entry_are_zero(self):
        """Before any updates, MFE and MAE are both zero."""
        pos = self._make_position("long", entry_price=100.0)
        assert pos.mfe == pytest.approx(0.0)
        assert pos.mae == pytest.approx(0.0)

    def test_mfe_mae_short_at_entry_are_zero(self):
        """Short position: before any updates, MFE and MAE are both zero."""
        pos = self._make_position("short", entry_price=100.0)
        assert pos.mfe == pytest.approx(0.0)
        assert pos.mae == pytest.approx(0.0)


class TestOpenPositionTracker:
    """Unit tests for OpenPositionTracker container."""

    def _make_tracker_with_position(
        self, symbol: str = "AAPL", direction: str = "long"
    ) -> OpenPositionTracker:
        tracker = OpenPositionTracker()
        tracker.open_position(
            symbol=symbol,
            strategy="rsi_mean_reversion",
            direction=direction,
            entry_price=100.0,
            entry_time=datetime(2026, 1, 15, 9, 30),
            quantity=10,
        )
        return tracker

    def test_open_and_close_position(self):
        """Basic lifecycle: open, verify exists, close, verify gone."""
        tracker = self._make_tracker_with_position("AAPL")
        assert tracker.has_position("AAPL")
        closed = tracker.close_position("AAPL")
        assert closed is not None
        assert closed.symbol == "AAPL"
        assert not tracker.has_position("AAPL")

    def test_has_position(self):
        """has_position returns True when open, False when closed."""
        tracker = self._make_tracker_with_position("AAPL")
        assert tracker.has_position("AAPL") is True
        assert tracker.has_position("MSFT") is False
        tracker.close_position("AAPL")
        assert tracker.has_position("AAPL") is False

    def test_close_returns_tracked_position(self):
        """close_position returns the TrackedPosition with correct data."""
        tracker = self._make_tracker_with_position("AAPL")
        tracker.update_prices("AAPL", high=110.0, low=95.0, close=105.0)
        closed = tracker.close_position("AAPL")
        assert isinstance(closed, TrackedPosition)
        assert closed.symbol == "AAPL"
        assert closed.strategy == "rsi_mean_reversion"
        assert closed.direction == "long"
        assert closed.entry_price == 100.0
        assert closed.highest_price == 110.0
        assert closed.lowest_price == 95.0
        assert closed.bar_count == 1
        assert closed.mfe == pytest.approx(0.10)
        assert closed.mae == pytest.approx(0.05)

    def test_close_nonexistent_returns_none(self):
        """Closing an unknown symbol returns None."""
        tracker = OpenPositionTracker()
        result = tracker.close_position("FAKE")
        assert result is None

    def test_open_symbols_property(self):
        """open_symbols lists all currently tracked symbols."""
        tracker = OpenPositionTracker()
        assert tracker.open_symbols == []
        tracker.open_position(
            symbol="AAPL", strategy="test", direction="long",
            entry_price=100.0, entry_time=datetime(2026, 1, 15), quantity=10,
        )
        tracker.open_position(
            symbol="MSFT", strategy="test", direction="short",
            entry_price=200.0, entry_time=datetime(2026, 1, 15), quantity=5,
        )
        tracker.open_position(
            symbol="GOOGL", strategy="test", direction="long",
            entry_price=150.0, entry_time=datetime(2026, 1, 15), quantity=8,
        )
        symbols = tracker.open_symbols
        assert sorted(symbols) == ["AAPL", "GOOGL", "MSFT"]

    def test_update_prices_no_position_is_noop(self):
        """Updating prices for a non-tracked symbol does nothing."""
        tracker = OpenPositionTracker()
        tracker.update_prices("FAKE", high=110.0, low=90.0, close=100.0)
        assert not tracker.has_position("FAKE")

    def test_get_position_returns_reference(self):
        """get_position returns the tracked position without removing it."""
        tracker = self._make_tracker_with_position("AAPL")
        pos = tracker.get_position("AAPL")
        assert pos is not None
        assert pos.symbol == "AAPL"
        # Still tracked after get
        assert tracker.has_position("AAPL")

    def test_get_position_nonexistent_returns_none(self):
        """get_position for unknown symbol returns None."""
        tracker = OpenPositionTracker()
        assert tracker.get_position("FAKE") is None

    def test_open_position_initializes_extremes_at_entry(self):
        """highest_price and lowest_price start at entry_price."""
        tracker = self._make_tracker_with_position("AAPL")
        pos = tracker.get_position("AAPL")
        assert pos is not None
        assert pos.highest_price == 100.0
        assert pos.lowest_price == 100.0

    def test_multiple_positions_independent(self):
        """Multiple positions are tracked independently."""
        tracker = OpenPositionTracker()
        tracker.open_position(
            symbol="AAPL", strategy="strat_a", direction="long",
            entry_price=100.0, entry_time=datetime(2026, 1, 15), quantity=10,
        )
        tracker.open_position(
            symbol="MSFT", strategy="strat_b", direction="short",
            entry_price=200.0, entry_time=datetime(2026, 1, 15), quantity=5,
        )
        # Update only AAPL
        tracker.update_prices("AAPL", high=110.0, low=95.0, close=105.0)
        aapl = tracker.get_position("AAPL")
        msft = tracker.get_position("MSFT")
        assert aapl is not None
        assert msft is not None
        assert aapl.highest_price == 110.0
        assert aapl.bar_count == 1
        # MSFT untouched
        assert msft.highest_price == 200.0
        assert msft.bar_count == 0
