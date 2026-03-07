"""Tests for OrderLedger -- persistent order tracking."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autotrader.execution.order_ledger import (
    OrderLedger,
    OrderRecord,
    OrderState,
    PENDING_STATES,
    TERMINAL_STATES,
)


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "test_ledger.jsonl"


@pytest.fixture
def ledger(ledger_path: Path) -> OrderLedger:
    return OrderLedger(path=ledger_path)


def _make_record(**overrides) -> OrderRecord:
    defaults = dict(
        order_id="ord-001",
        symbol="AAPL",
        side="buy",
        direction="long",
        order_type="market",
        order_role="entry",
        strategy="breakout_momentum",
        qty_requested=100.0,
    )
    defaults.update(overrides)
    return OrderRecord(**defaults)


class TestOrderRecordDefaults:
    def test_timestamps_auto_set(self):
        rec = _make_record()
        assert rec.submitted_at != ""
        assert rec.updated_at != ""

    def test_state_defaults_to_submitted(self):
        rec = _make_record()
        assert rec.state == OrderState.SUBMITTED

    def test_state_coercion_from_string(self):
        rec = _make_record(state="filled")
        assert rec.state == OrderState.FILLED


class TestOrderLedgerPersistence:
    def test_record_submission_creates_file(self, ledger: OrderLedger, ledger_path: Path):
        rec = _make_record()
        ledger.record_submission(rec)
        assert ledger_path.exists()
        lines = ledger_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["order_id"] == "ord-001"
        assert data["state"] == "submitted"

    def test_load_replays_records(self, ledger: OrderLedger, ledger_path: Path):
        rec = _make_record()
        ledger.record_submission(rec)
        ledger.record_fill("ord-001", qty_filled=100, fill_price=150.0)

        # Create a new ledger and load
        ledger2 = OrderLedger(path=ledger_path)
        orders = ledger2.load()
        assert len(orders) == 1
        assert orders["ord-001"].state == OrderState.FILLED
        assert orders["ord-001"].fill_price == 150.0

    def test_last_line_wins(self, ledger: OrderLedger, ledger_path: Path):
        rec = _make_record()
        ledger.record_submission(rec)
        ledger.record_fill("ord-001", 100, 150.0)
        ledger.record_cancel("ord-001")  # This should NOT happen normally

        ledger2 = OrderLedger(path=ledger_path)
        orders = ledger2.load()
        assert orders["ord-001"].state == OrderState.CANCELLED

    def test_multiple_orders(self, ledger: OrderLedger):
        ledger.record_submission(_make_record(order_id="ord-001", symbol="AAPL"))
        ledger.record_submission(_make_record(order_id="ord-002", symbol="MSFT"))
        ledger.record_submission(_make_record(order_id="ord-003", symbol="GOOG"))

        assert ledger.get_order("ord-001") is not None
        assert ledger.get_order("ord-002") is not None
        assert ledger.get_order("ord-003") is not None
        assert ledger.get_order("ord-999") is None

    def test_empty_file_loads_ok(self, ledger: OrderLedger):
        orders = ledger.load()
        assert len(orders) == 0

    def test_corrupted_lines_skipped(self, ledger: OrderLedger, ledger_path: Path):
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "w") as f:
            f.write("NOT VALID JSON\n")
            rec = _make_record()
            from dataclasses import asdict
            f.write(json.dumps(asdict(rec)) + "\n")

        orders = ledger.load()
        assert len(orders) == 1


class TestStateTransitions:
    def test_record_fill(self, ledger: OrderLedger):
        ledger.record_submission(_make_record())
        ledger.record_fill("ord-001", qty_filled=100, fill_price=150.5)

        rec = ledger.get_order("ord-001")
        assert rec.state == OrderState.FILLED
        assert rec.qty_filled == 100.0
        assert rec.fill_price == 150.5

    def test_record_partial_fill(self, ledger: OrderLedger):
        ledger.record_submission(_make_record())
        ledger.record_fill("ord-001", qty_filled=50, fill_price=150.5, partial=True)

        rec = ledger.get_order("ord-001")
        assert rec.state == OrderState.PARTIALLY_FILLED

    def test_record_cancel(self, ledger: OrderLedger):
        ledger.record_submission(_make_record())
        ledger.record_cancel("ord-001")

        rec = ledger.get_order("ord-001")
        assert rec.state == OrderState.CANCELLED

    def test_record_terminal_rejected(self, ledger: OrderLedger):
        ledger.record_submission(_make_record())
        ledger.record_terminal("ord-001", OrderState.REJECTED)

        rec = ledger.get_order("ord-001")
        assert rec.state == OrderState.REJECTED

    def test_record_terminal_rejects_non_terminal(self, ledger: OrderLedger):
        ledger.record_submission(_make_record())
        ledger.record_terminal("ord-001", OrderState.SUBMITTED)
        # Should not change state -- SUBMITTED is not terminal
        rec = ledger.get_order("ord-001")
        assert rec.state == OrderState.SUBMITTED

    def test_fill_unknown_order_ignored(self, ledger: OrderLedger):
        ledger.record_fill("nonexistent", 100, 150.0)
        assert ledger.get_order("nonexistent") is None

    def test_cancel_unknown_order_ignored(self, ledger: OrderLedger):
        ledger.record_cancel("nonexistent")
        assert ledger.get_order("nonexistent") is None


class TestLinkSlOrder:
    def test_link_sl_order(self, ledger: OrderLedger):
        ledger.record_submission(_make_record(order_id="entry-001"))
        ledger.record_submission(_make_record(
            order_id="sl-001", order_role="stop_loss", order_type="stop",
            parent_order_id="entry-001",
        ))
        ledger.link_sl_order("entry-001", "sl-001")

        rec = ledger.get_order("entry-001")
        assert rec.sl_order_id == "sl-001"

    def test_link_sl_unknown_entry_ignored(self, ledger: OrderLedger):
        ledger.link_sl_order("nonexistent", "sl-001")
        # Should not crash


class TestQueries:
    def test_get_pending_entries(self, ledger: OrderLedger):
        ledger.record_submission(_make_record(order_id="e1", order_role="entry"))
        ledger.record_submission(_make_record(order_id="e2", order_role="entry"))
        ledger.record_submission(_make_record(order_id="sl1", order_role="stop_loss"))
        ledger.record_fill("e1", 100, 150.0)

        pending = ledger.get_pending_entries()
        assert len(pending) == 1
        assert pending[0].order_id == "e2"

    def test_get_pending_stop_losses(self, ledger: OrderLedger):
        ledger.record_submission(_make_record(
            order_id="sl1", order_role="stop_loss", symbol="AAPL",
        ))
        ledger.record_submission(_make_record(
            order_id="sl2", order_role="stop_loss", symbol="MSFT",
        ))
        ledger.record_fill("sl1", 100, 145.0)

        pending = ledger.get_pending_stop_losses()
        assert len(pending) == 1
        assert "MSFT" in pending


class TestCompact:
    def test_compact_removes_old_terminal(self, ledger: OrderLedger, ledger_path: Path):
        rec = _make_record(order_id="old-001")
        ledger.record_submission(rec)
        ledger.record_fill("old-001", 100, 150.0)
        # Manually set updated_at far in the past
        order = ledger.get_order("old-001")
        order.updated_at = "2020-01-01T00:00:00+00:00"

        rec2 = _make_record(order_id="new-001")
        ledger.record_submission(rec2)  # Still pending

        removed = ledger.compact(keep_hours=1)
        assert removed == 1
        assert ledger.get_order("old-001") is None
        assert ledger.get_order("new-001") is not None

    def test_compact_keeps_pending(self, ledger: OrderLedger):
        rec = _make_record(order_id="pending-001")
        ledger.record_submission(rec)
        # Even with old timestamp, pending should be kept
        order = ledger.get_order("pending-001")
        order.updated_at = "2020-01-01T00:00:00+00:00"

        removed = ledger.compact(keep_hours=1)
        assert removed == 0
        assert ledger.get_order("pending-001") is not None


class TestDictToRecord:
    def test_round_trip(self, ledger: OrderLedger, ledger_path: Path):
        rec = _make_record(
            entry_atr=3.5,
            limit_price=155.0,
            stop_price=None,
            metadata={"sub_strategy": "breakout_momentum_long"},
        )
        ledger.record_submission(rec)

        ledger2 = OrderLedger(path=ledger_path)
        orders = ledger2.load()
        loaded = orders["ord-001"]

        assert loaded.symbol == "AAPL"
        assert loaded.entry_atr == 3.5
        assert loaded.limit_price == 155.0
        assert loaded.stop_price is None
        assert loaded.metadata["sub_strategy"] == "breakout_momentum_long"


class TestEnumSets:
    def test_pending_states(self):
        assert OrderState.SUBMITTED in PENDING_STATES
        assert OrderState.PENDING_FILL in PENDING_STATES
        assert OrderState.PARTIALLY_FILLED in PENDING_STATES
        assert OrderState.FILLED not in PENDING_STATES

    def test_terminal_states(self):
        assert OrderState.FILLED in TERMINAL_STATES
        assert OrderState.CANCELLED in TERMINAL_STATES
        assert OrderState.EXPIRED in TERMINAL_STATES
        assert OrderState.REJECTED in TERMINAL_STATES
        assert OrderState.SUBMITTED not in TERMINAL_STATES
