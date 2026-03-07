"""Tests for PositionBook: single source of truth for position tracking."""
from datetime import date

import pytest

from autotrader.trading.position_book import PositionBook
from autotrader.trading.types import HeldPosition
from autotrader.trading.constants import MAX_TOTAL_POSITIONS


def _make_held(
    symbol: str = "AAPL",
    strategy: str = "breakout_momentum",
    direction: str = "long",
    entry_price: float = 150.0,
) -> HeldPosition:
    return HeldPosition(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        entry_price=entry_price,
        entry_atr=2.0,
        entry_date_et=date(2026, 3, 1),
        qty=10,
    )


class TestPositionBookBasics:
    """Core add/remove/get/has operations."""

    def test_add_and_get(self):
        book = PositionBook()
        held = _make_held("AAPL")
        assert book.add(held) is True
        assert book.get("AAPL") is held

    def test_add_returns_true_on_success(self):
        book = PositionBook()
        assert book.add(_make_held("AAPL")) is True

    def test_has_returns_true_when_present(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        assert book.has("AAPL") is True

    def test_has_returns_false_when_absent(self):
        book = PositionBook()
        assert book.has("AAPL") is False

    def test_remove_returns_position(self):
        book = PositionBook()
        held = _make_held("AAPL")
        book.add(held)
        removed = book.remove("AAPL")
        assert removed is held
        assert book.has("AAPL") is False

    def test_remove_returns_none_when_absent(self):
        book = PositionBook()
        assert book.remove("FAKE") is None

    def test_get_returns_none_when_absent(self):
        book = PositionBook()
        assert book.get("FAKE") is None

    def test_symbols_property(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        book.add(_make_held("MSFT"))
        assert sorted(book.symbols) == ["AAPL", "MSFT"]

    def test_count_property(self):
        book = PositionBook()
        assert book.count == 0
        book.add(_make_held("AAPL"))
        assert book.count == 1
        book.add(_make_held("MSFT"))
        assert book.count == 2
        book.remove("AAPL")
        assert book.count == 1


class TestDuplicateAndCapacity:
    """Duplicate add and capacity limit checks."""

    def test_duplicate_add_returns_false(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        result = book.add(_make_held("AAPL", strategy="rsi_mean_reversion"))
        assert result is False
        # Original strategy preserved
        assert book.get("AAPL").strategy == "breakout_momentum"

    def test_capacity_limit(self):
        book = PositionBook()
        for i in range(MAX_TOTAL_POSITIONS):
            sym = f"SYM{i}"
            assert book.add(_make_held(sym)) is True
        assert book.count == MAX_TOTAL_POSITIONS
        # Adding one more should fail
        assert book.add(_make_held("OVERFLOW")) is False
        assert book.count == MAX_TOTAL_POSITIONS

    def test_capacity_frees_after_remove(self):
        book = PositionBook()
        for i in range(MAX_TOTAL_POSITIONS):
            book.add(_make_held(f"SYM{i}"))
        # Full -- cannot add
        assert book.add(_make_held("NEW")) is False
        # Remove one
        book.remove("SYM0")
        # Now we can add
        assert book.add(_make_held("NEW")) is True


class TestByStrategy:
    """Strategy-based filtering."""

    def test_by_strategy_returns_matching(self):
        book = PositionBook()
        book.add(_make_held("AAPL", strategy="breakout_momentum"))
        book.add(_make_held("MSFT", strategy="rsi_mean_reversion"))
        book.add(_make_held("GOOGL", strategy="breakout_momentum"))

        bm = book.by_strategy("breakout_momentum")
        assert len(bm) == 2
        assert {p.symbol for p in bm} == {"AAPL", "GOOGL"}

    def test_by_strategy_returns_empty_for_unknown(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        assert book.by_strategy("nonexistent") == []


class TestStrategyMap:
    """strategy_map() method."""

    def test_strategy_map(self):
        book = PositionBook()
        book.add(_make_held("AAPL", strategy="breakout_momentum"))
        book.add(_make_held("MSFT", strategy="rsi_mean_reversion"))
        sm = book.strategy_map()
        assert sm == {
            "AAPL": "breakout_momentum",
            "MSFT": "rsi_mean_reversion",
        }

    def test_strategy_map_empty(self):
        book = PositionBook()
        assert book.strategy_map() == {}


class TestAllPositions:
    """all_positions() method."""

    def test_all_positions(self):
        book = PositionBook()
        h1 = _make_held("AAPL")
        h2 = _make_held("MSFT")
        book.add(h1)
        book.add(h2)
        all_pos = book.all_positions()
        assert len(all_pos) == 2
        assert h1 in all_pos
        assert h2 in all_pos


class TestSnapshotRoundTrip:
    """Snapshot serialization and deserialization."""

    def test_to_snapshot(self):
        book = PositionBook()
        held = _make_held("AAPL")
        held.bars_held = 3
        held.highest_price = 160.0
        held.lowest_price = 140.0
        held.consecutive_loss_bars = 1
        held.entry_adx = 30.0
        book.add(held)

        snap = book.to_snapshot()
        assert "AAPL" in snap
        rec = snap["AAPL"]
        assert rec["symbol"] == "AAPL"
        assert rec["strategy"] == "breakout_momentum"
        assert rec["direction"] == "long"
        assert rec["entry_price"] == 150.0
        assert rec["bars_held"] == 3
        assert rec["highest_price"] == 160.0
        assert rec["lowest_price"] == 140.0
        assert rec["consecutive_loss_bars"] == 1
        assert rec["entry_adx"] == 30.0

    def test_from_snapshot_restores(self):
        book = PositionBook()
        held = _make_held("AAPL")
        held.bars_held = 5
        held.highest_price = 170.0
        held.lowest_price = 130.0
        held.consecutive_loss_bars = 2
        held.entry_adx = 25.0
        book.add(held)

        snap = book.to_snapshot()

        # Restore into a new book
        book2 = PositionBook()
        book2.from_snapshot(snap)

        assert book2.has("AAPL")
        restored = book2.get("AAPL")
        assert restored.symbol == "AAPL"
        assert restored.strategy == "breakout_momentum"
        assert restored.direction == "long"
        assert restored.entry_price == 150.0
        assert restored.entry_atr == 2.0
        assert restored.entry_date_et == date(2026, 3, 1)
        assert restored.bars_held == 5
        assert restored.highest_price == 170.0
        assert restored.lowest_price == 130.0
        assert restored.consecutive_loss_bars == 2
        assert restored.entry_adx == 25.0

    def test_from_snapshot_clears_existing(self):
        book = PositionBook()
        book.add(_make_held("OLD"))
        assert book.has("OLD")

        snap = {"AAPL": {
            "symbol": "AAPL", "strategy": "bm", "direction": "long",
            "entry_price": 100.0, "entry_atr": 1.0,
            "entry_date_et": "2026-03-01", "qty": 5,
        }}
        book.from_snapshot(snap)
        assert not book.has("OLD")
        assert book.has("AAPL")


class TestBackwardCompat:
    """Backward-compatible method aliases."""

    def test_close_position_alias(self):
        book = PositionBook()
        held = _make_held("AAPL")
        book.add(held)
        closed = book.close_position("AAPL")
        assert closed is held
        assert not book.has("AAPL")

    def test_has_position_alias(self):
        book = PositionBook()
        assert book.has_position("AAPL") is False
        book.add(_make_held("AAPL"))
        assert book.has_position("AAPL") is True

    def test_get_position_alias(self):
        book = PositionBook()
        held = _make_held("AAPL")
        book.add(held)
        assert book.get_position("AAPL") is held

    def test_open_symbols_alias(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        book.add(_make_held("MSFT"))
        assert sorted(book.open_symbols) == ["AAPL", "MSFT"]

    def test_update_prices(self):
        book = PositionBook()
        held = _make_held("AAPL", entry_price=100.0)
        book.add(held)
        book.update_prices("AAPL", high=110.0, low=95.0, close=105.0)
        assert held.highest_price == 110.0
        assert held.lowest_price == 95.0

    def test_update_prices_noop_for_missing(self):
        """update_prices for a missing symbol is a no-op."""
        book = PositionBook()
        book.update_prices("FAKE", high=100, low=90, close=95)
        # No error, no position created


class TestDunderMethods:
    """__len__, __contains__, __iter__."""

    def test_len(self):
        book = PositionBook()
        assert len(book) == 0
        book.add(_make_held("AAPL"))
        assert len(book) == 1

    def test_contains(self):
        book = PositionBook()
        book.add(_make_held("AAPL"))
        assert "AAPL" in book
        assert "MSFT" not in book

    def test_iter(self):
        book = PositionBook()
        h1 = _make_held("AAPL")
        h2 = _make_held("MSFT")
        book.add(h1)
        book.add(h2)
        items = list(book)
        assert len(items) == 2
        assert h1 in items
        assert h2 in items


class TestMergeSnapshot:
    """merge_snapshot(): updates tracking fields without replacing positions."""

    def test_merge_updates_tracking_fields(self):
        """Tracking fields are updated from snapshot data."""
        book = PositionBook()
        held = _make_held("AAPL", entry_price=150.0)
        book.add(held)

        snapshot = {
            "AAPL": {
                "bars_held": 5,
                "highest_price": 170.0,
                "lowest_price": 130.0,
                "consecutive_loss_bars": 2,
                "entry_adx": 32.5,
            }
        }
        book.merge_snapshot(snapshot)

        assert held.bars_held == 5
        assert held.highest_price == 170.0
        assert held.lowest_price == 130.0
        assert held.consecutive_loss_bars == 2
        assert held.entry_adx == 32.5

    def test_merge_preserves_identity_fields(self):
        """Identity/quantity fields are NOT changed by merge."""
        book = PositionBook()
        held = _make_held("AAPL", entry_price=150.0, strategy="breakout_momentum")
        book.add(held)

        snapshot = {
            "AAPL": {
                "symbol": "AAPL",
                "strategy": "rsi_mean_reversion",
                "direction": "short",
                "entry_price": 999.0,
                "qty": 999,
                "bars_held": 3,
                "highest_price": 160.0,
                "lowest_price": 140.0,
                "consecutive_loss_bars": 1,
                "entry_adx": 28.0,
            }
        }
        book.merge_snapshot(snapshot)

        # Identity/quantity fields must remain unchanged
        assert held.symbol == "AAPL"
        assert held.strategy == "breakout_momentum"
        assert held.direction == "long"
        assert held.entry_price == 150.0
        assert held.qty == 10
        # Tracking fields are updated
        assert held.bars_held == 3
        assert held.highest_price == 160.0

    def test_merge_skips_unknown_symbols(self):
        """Symbols not in the book are silently skipped."""
        book = PositionBook()
        held = _make_held("AAPL")
        book.add(held)

        snapshot = {
            "MSFT": {
                "bars_held": 10,
                "highest_price": 400.0,
                "lowest_price": 350.0,
                "consecutive_loss_bars": 0,
                "entry_adx": 20.0,
            }
        }
        book.merge_snapshot(snapshot)

        # AAPL unchanged, MSFT not added
        assert book.count == 1
        assert held.bars_held == 0  # default, not modified

    def test_merge_empty_snapshot(self):
        """Empty snapshot is a no-op."""
        book = PositionBook()
        held = _make_held("AAPL")
        held.bars_held = 3
        book.add(held)

        book.merge_snapshot({})
        assert held.bars_held == 3  # unchanged

    def test_merge_partial_fields(self):
        """Only fields present in snapshot are updated; others keep defaults."""
        book = PositionBook()
        held = _make_held("AAPL", entry_price=100.0)
        held.bars_held = 0
        held.highest_price = 100.0
        held.lowest_price = 100.0
        held.consecutive_loss_bars = 0
        held.entry_adx = 0.0
        book.add(held)

        snapshot = {
            "AAPL": {
                "bars_held": 7,
                "highest_price": 120.0,
                # lowest_price, consecutive_loss_bars, entry_adx omitted
            }
        }
        book.merge_snapshot(snapshot)

        assert held.bars_held == 7
        assert held.highest_price == 120.0
        # Fields not in snapshot keep their current values
        assert held.lowest_price == 100.0
        assert held.consecutive_loss_bars == 0
        assert held.entry_adx == 0.0

    def test_merge_multiple_positions(self):
        """Merge correctly updates multiple positions."""
        book = PositionBook()
        aapl = _make_held("AAPL", entry_price=150.0)
        msft = _make_held("MSFT", entry_price=300.0)
        book.add(aapl)
        book.add(msft)

        snapshot = {
            "AAPL": {
                "bars_held": 3,
                "highest_price": 160.0,
                "lowest_price": 140.0,
                "consecutive_loss_bars": 0,
                "entry_adx": 30.0,
            },
            "MSFT": {
                "bars_held": 7,
                "highest_price": 320.0,
                "lowest_price": 280.0,
                "consecutive_loss_bars": 1,
                "entry_adx": 25.0,
            },
        }
        book.merge_snapshot(snapshot)

        assert aapl.bars_held == 3
        assert aapl.highest_price == 160.0
        assert msft.bars_held == 7
        assert msft.highest_price == 320.0
        assert msft.lowest_price == 280.0
