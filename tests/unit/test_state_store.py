"""
Comprehensive tests for StateStore -- SQLite facade for AutoTrader runtime state.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from autotrader.data.state_store import StateStore


# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    """Return a StateStore backed by a temporary database."""
    db = str(tmp_path / "test.db")
    s = StateStore(db_path=db)
    yield s
    s.close()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


def _sample_position(**overrides: object) -> dict:
    base = {
        "strategy": "breakout_momentum",
        "direction": "long",
        "entry_price": 150.0,
        "entry_atr": 2.5,
        "entry_date_et": "2026-03-10",
        "qty": 10.0,
        "bars_held": 3,
        "highest_price": 155.0,
        "lowest_price": 148.0,
        "consecutive_loss_bars": 0,
        "entry_adx": 30.0,
        "entry_time": "09:35:00",
        "current_price": 153.0,
        "unrealized_pnl": 30.0,
    }
    base.update(overrides)
    return base


def _sample_order(**overrides: object) -> dict:
    base = {
        "order_id": "ord-001",
        "symbol": "AAPL",
        "side": "buy",
        "direction": "long",
        "order_type": "market",
        "order_role": "entry",
        "strategy": "breakout_momentum",
        "qty_requested": 10.0,
        "qty_filled": 0.0,
        "fill_price": 0.0,
        "state": "submitted",
        "submitted_at": "2026-03-10 09:30:00",
        "updated_at": "2026-03-10 09:30:00",
        "entry_atr": 2.5,
        "limit_price": None,
        "stop_price": None,
        "sl_order_id": None,
        "parent_order_id": None,
        "metadata": {"source": "signal"},
    }
    base.update(overrides)
    return base


def _sample_trade(**overrides: object) -> dict:
    base = {
        "timestamp": "2026-03-10T10:00:00",
        "symbol": "AAPL",
        "strategy": "breakout_momentum",
        "direction": "long",
        "side": "buy",
        "quantity": 10.0,
        "price": 150.0,
        "pnl": 0.0,
        "regime": "TREND_UP",
        "equity_after": 10000.0,
        "metadata": {"reason": "entry"},
        "exit_reason": "",
        "mfe": 5.0,
        "mae": -2.0,
        "bars_held": 0,
    }
    base.update(overrides)
    return base


def _sample_equity_snapshot(**overrides: object) -> dict:
    base = {
        "timestamp": "2026-03-10T16:00:00",
        "equity": 10500.0,
        "cash": 8500.0,
        "regime": "TREND_UP",
        "position_count": 2,
        "open_positions": ["AAPL", "MSFT"],
    }
    base.update(overrides)
    return base


# ═════════════════════════════════════════════════════════════════════════
# TestStateStoreInit
# ═════════════════════════════════════════════════════════════════════════


class TestStateStoreInit:
    def test_db_file_created(self, tmp_path: Path) -> None:
        db = str(tmp_path / "init_test.db")
        s = StateStore(db_path=db)
        assert Path(db).exists()
        s.close()

    def test_wal_mode_enabled(self, store: StateStore) -> None:
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_synchronous_normal(self, store: StateStore) -> None:
        val = store._conn.execute("PRAGMA synchronous").fetchone()[0]
        # NORMAL = 1
        assert val == 1

    def test_busy_timeout(self, store: StateStore) -> None:
        val = store._conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert val == 5000

    def test_row_factory(self, store: StateStore) -> None:
        assert store._conn.row_factory is sqlite3.Row

    def test_all_tables_exist(self, store: StateStore) -> None:
        cur = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {r["name"] for r in cur.fetchall()}
        expected = {
            "positions", "orders", "trades",
            "equity_snapshots", "component_state", "scheduler_events",
        }
        assert expected.issubset(tables)

    def test_idempotent_init(self, db_path: str) -> None:
        """Opening the same DB twice must not raise."""
        s1 = StateStore(db_path=db_path)
        s2 = StateStore(db_path=db_path)
        s1.close()
        s2.close()

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        db = str(tmp_path / "sub" / "dir" / "test.db")
        s = StateStore(db_path=db)
        assert Path(db).exists()
        s.close()

    def test_context_manager(self, tmp_path: Path) -> None:
        db = str(tmp_path / "ctx.db")
        with StateStore(db_path=db) as s:
            assert s is not None
            s.upsert_position("AAPL", _sample_position())
        # connection closed after exit -- re-open to verify data persisted
        s2 = StateStore(db_path=db)
        assert s2.load_position("AAPL") is not None
        s2.close()


# ═════════════════════════════════════════════════════════════════════════
# TestPositions
# ═════════════════════════════════════════════════════════════════════════


class TestPositions:
    def test_upsert_and_load(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position())
        pos = store.load_positions()
        assert "AAPL" in pos
        assert pos["AAPL"]["strategy"] == "breakout_momentum"
        assert pos["AAPL"]["entry_price"] == 150.0

    def test_load_single(self, store: StateStore) -> None:
        store.upsert_position("MSFT", _sample_position(strategy="rsi_mean_reversion"))
        p = store.load_position("MSFT")
        assert p is not None
        assert p["strategy"] == "rsi_mean_reversion"

    def test_load_single_missing(self, store: StateStore) -> None:
        assert store.load_position("NOPE") is None

    def test_overwrite(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position(entry_price=100.0))
        store.upsert_position("AAPL", _sample_position(entry_price=200.0))
        p = store.load_position("AAPL")
        assert p["entry_price"] == 200.0

    def test_remove(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position())
        store.remove_position("AAPL")
        assert store.load_position("AAPL") is None

    def test_remove_nonexistent(self, store: StateStore) -> None:
        """Removing a non-existent symbol should not raise."""
        store.remove_position("NOPE")

    def test_update_mfe_mae(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position())
        store.update_mfe_mae("AAPL", highest_price=160.0, lowest_price=145.0)
        p = store.load_position("AAPL")
        assert p["highest_price"] == 160.0
        assert p["lowest_price"] == 145.0

    def test_update_mfe_mae_preserves_other_fields(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position(entry_price=150.0, bars_held=5))
        store.update_mfe_mae("AAPL", 999.0, 1.0)
        p = store.load_position("AAPL")
        assert p["entry_price"] == 150.0
        assert p["bars_held"] == 5

    def test_updated_at_set(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position())
        p = store.load_position("AAPL")
        assert p["updated_at"] is not None
        assert len(p["updated_at"]) > 0

    def test_multiple_positions(self, store: StateStore) -> None:
        for sym in ["AAPL", "MSFT", "GOOG"]:
            store.upsert_position(sym, _sample_position())
        pos = store.load_positions()
        assert len(pos) == 3

    def test_direction_constraint(self, store: StateStore) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            store.upsert_position("BAD", _sample_position(direction="invalid"))


# ═════════════════════════════════════════════════════════════════════════
# TestOrders
# ═════════════════════════════════════════════════════════════════════════


class TestOrders:
    def test_insert_and_load(self, store: StateStore) -> None:
        store.insert_order(_sample_order())
        orders = store.load_orders()
        assert "ord-001" in orders
        assert orders["ord-001"]["symbol"] == "AAPL"

    def test_load_single(self, store: StateStore) -> None:
        store.insert_order(_sample_order())
        o = store.load_order("ord-001")
        assert o is not None
        assert o["order_id"] == "ord-001"

    def test_load_single_missing(self, store: StateStore) -> None:
        assert store.load_order("nope") is None

    def test_update_state(self, store: StateStore) -> None:
        store.insert_order(_sample_order())
        store.update_order_state("ord-001", "filled", qty_filled=10.0, fill_price=151.0)
        o = store.load_order("ord-001")
        assert o["state"] == "filled"
        assert o["qty_filled"] == 10.0
        assert o["fill_price"] == 151.0

    def test_update_state_with_kwargs(self, store: StateStore) -> None:
        store.insert_order(_sample_order())
        store.update_order_state("ord-001", "filled", sl_order_id="sl-001")
        o = store.load_order("ord-001")
        assert o["sl_order_id"] == "sl-001"

    def test_load_pending_only(self, store: StateStore) -> None:
        store.insert_order(_sample_order(order_id="o1", state="submitted"))
        store.insert_order(_sample_order(order_id="o2", state="filled"))
        store.insert_order(_sample_order(order_id="o3", state="cancelled"))
        store.insert_order(_sample_order(order_id="o4", state="partial"))
        pending = store.load_orders(pending_only=True)
        assert "o1" in pending
        assert "o4" in pending
        assert "o2" not in pending
        assert "o3" not in pending

    def test_load_all(self, store: StateStore) -> None:
        store.insert_order(_sample_order(order_id="o1", state="submitted"))
        store.insert_order(_sample_order(order_id="o2", state="filled"))
        all_orders = store.load_orders(pending_only=False)
        assert len(all_orders) == 2

    def test_compact_orders(self, store: StateStore) -> None:
        old_time = "2020-01-01 00:00:00"
        recent_time = "2099-12-31 23:59:59"
        store.insert_order(
            _sample_order(order_id="old", state="filled", updated_at=old_time)
        )
        store.insert_order(
            _sample_order(order_id="recent", state="filled", updated_at=recent_time)
        )
        store.insert_order(
            _sample_order(order_id="pending", state="submitted", updated_at=old_time)
        )
        deleted = store.compact_orders(keep_hours=72)
        assert deleted == 1  # only old+filled
        remaining = store.load_orders()
        assert "old" not in remaining
        assert "recent" in remaining
        assert "pending" in remaining

    def test_duplicate_order_id_raises(self, store: StateStore) -> None:
        store.insert_order(_sample_order(order_id="dup"))
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_order(_sample_order(order_id="dup"))

    def test_metadata_round_trip(self, store: StateStore) -> None:
        meta = {"source": "scanner", "score": 0.85}
        store.insert_order(_sample_order(metadata=meta))
        o = store.load_order("ord-001")
        assert o["metadata"] == meta

    def test_metadata_string_passthrough(self, store: StateStore) -> None:
        store.insert_order(_sample_order(metadata='{"a":1}'))
        o = store.load_order("ord-001")
        assert o["metadata"] == {"a": 1}


# ═════════════════════════════════════════════════════════════════════════
# TestTrades
# ═════════════════════════════════════════════════════════════════════════


class TestTrades:
    def test_insert_and_load(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade())
        trades = store.load_trades()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"

    def test_load_filtered_by_strategy(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade(strategy="bm"))
        store.insert_trade(_sample_trade(strategy="mr", symbol="MSFT"))
        bm = store.load_trades(strategy="bm")
        assert len(bm) == 1
        assert bm[0]["strategy"] == "bm"

    def test_load_filtered_by_symbol(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade(symbol="AAPL"))
        store.insert_trade(_sample_trade(symbol="MSFT"))
        aapl = store.load_trades(symbol="AAPL")
        assert len(aapl) == 1

    def test_load_filtered_both(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade(symbol="AAPL", strategy="bm"))
        store.insert_trade(_sample_trade(symbol="AAPL", strategy="mr"))
        store.insert_trade(_sample_trade(symbol="MSFT", strategy="bm"))
        result = store.load_trades(strategy="bm", symbol="AAPL")
        assert len(result) == 1

    def test_load_since(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade(timestamp="2026-03-01T10:00:00"))
        store.insert_trade(_sample_trade(timestamp="2026-03-05T10:00:00"))
        store.insert_trade(_sample_trade(timestamp="2026-03-10T10:00:00"))
        recent = store.load_trades_since("2026-03-05T00:00:00")
        assert len(recent) == 2

    def test_ordering_asc(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade(timestamp="2026-03-10T10:00:00"))
        store.insert_trade(_sample_trade(timestamp="2026-03-01T10:00:00"))
        store.insert_trade(_sample_trade(timestamp="2026-03-05T10:00:00"))
        trades = store.load_trades()
        timestamps = [t["timestamp"] for t in trades]
        assert timestamps == sorted(timestamps)

    def test_metadata_round_trip(self, store: StateStore) -> None:
        meta = {"entry_signal": "breakout", "score": 0.9}
        store.insert_trade(_sample_trade(metadata=meta))
        trades = store.load_trades()
        assert trades[0]["metadata"] == meta

    def test_autoincrement_id(self, store: StateStore) -> None:
        store.insert_trade(_sample_trade())
        store.insert_trade(_sample_trade())
        trades = store.load_trades()
        assert trades[0]["id"] < trades[1]["id"]


# ═════════════════════════════════════════════════════════════════════════
# TestEquitySnapshots
# ═════════════════════════════════════════════════════════════════════════


class TestEquitySnapshots:
    def test_insert_and_load(self, store: StateStore) -> None:
        store.insert_equity_snapshot(_sample_equity_snapshot())
        snaps = store.load_equity_snapshots()
        assert len(snaps) == 1
        assert snaps[0]["equity"] == 10500.0

    def test_open_positions_round_trip(self, store: StateStore) -> None:
        store.insert_equity_snapshot(_sample_equity_snapshot(open_positions=["X", "Y"]))
        snaps = store.load_equity_snapshots()
        assert snaps[0]["open_positions"] == ["X", "Y"]

    def test_ordered_by_timestamp(self, store: StateStore) -> None:
        store.insert_equity_snapshot(
            _sample_equity_snapshot(timestamp="2026-03-10T16:00:00")
        )
        store.insert_equity_snapshot(
            _sample_equity_snapshot(timestamp="2026-03-09T16:00:00")
        )
        snaps = store.load_equity_snapshots()
        assert snaps[0]["timestamp"] < snaps[1]["timestamp"]

    def test_multiple_snapshots(self, store: StateStore) -> None:
        for i in range(5):
            store.insert_equity_snapshot(
                _sample_equity_snapshot(
                    timestamp=f"2026-03-{10+i:02d}T16:00:00",
                    equity=10000.0 + i * 100,
                )
            )
        snaps = store.load_equity_snapshots()
        assert len(snaps) == 5


# ═════════════════════════════════════════════════════════════════════════
# TestComponentState
# ═════════════════════════════════════════════════════════════════════════


class TestComponentState:
    def test_save_and_load(self, store: StateStore) -> None:
        store.save_component_state("position_monitor", {"active": True, "count": 3})
        states = store.load_component_states()
        assert "position_monitor" in states
        assert states["position_monitor"]["active"] is True
        assert states["position_monitor"]["count"] == 3

    def test_upsert_overwrite(self, store: StateStore) -> None:
        store.save_component_state("comp", {"v": 1})
        store.save_component_state("comp", {"v": 2})
        states = store.load_component_states()
        assert states["comp"]["v"] == 2

    def test_save_all_transactional(self, store: StateStore) -> None:
        components = {
            "comp_a": {"status": "running"},
            "comp_b": {"status": "idle"},
            "comp_c": {"count": 42},
        }
        store.save_all_component_states(components)
        states = store.load_component_states()
        assert len(states) == 3
        assert states["comp_a"]["status"] == "running"
        assert states["comp_c"]["count"] == 42

    def test_save_all_overwrites_existing(self, store: StateStore) -> None:
        store.save_component_state("comp_a", {"v": 1})
        store.save_all_component_states({"comp_a": {"v": 99}, "comp_b": {"v": 2}})
        states = store.load_component_states()
        assert states["comp_a"]["v"] == 99
        assert states["comp_b"]["v"] == 2

    def test_empty_load(self, store: StateStore) -> None:
        assert store.load_component_states() == {}


# ═════════════════════════════════════════════════════════════════════════
# TestSchedulerEvents
# ═════════════════════════════════════════════════════════════════════════


class TestSchedulerEvents:
    def test_save_and_load(self, store: StateStore) -> None:
        events = {
            "morning_scan": {
                "fired_at": "2026-03-10 09:30:00",
                "result": "success",
                "target_date": "2026-03-10",
            },
            "eod_recon": {
                "fired_at": "2026-03-10 16:00:00",
                "result": "success",
                "target_date": "2026-03-10",
            },
        }
        store.save_scheduler_state("2026-03-10", events)
        date, loaded = store.load_scheduler_state()
        assert date == "2026-03-10"
        assert "morning_scan" in loaded
        assert "eod_recon" in loaded
        assert loaded["morning_scan"]["result"] == "success"

    def test_overwrite_same_date(self, store: StateStore) -> None:
        store.save_scheduler_state("2026-03-10", {"evt1": {"fired_at": "t1"}})
        store.save_scheduler_state("2026-03-10", {"evt2": {"fired_at": "t2"}})
        date, loaded = store.load_scheduler_state()
        assert "evt2" in loaded
        assert "evt1" not in loaded

    def test_loads_latest_date(self, store: StateStore) -> None:
        store.save_scheduler_state("2026-03-09", {"old": {"fired_at": "t1"}})
        store.save_scheduler_state("2026-03-10", {"new": {"fired_at": "t2"}})
        date, loaded = store.load_scheduler_state()
        assert date == "2026-03-10"
        assert "new" in loaded
        assert "old" not in loaded

    def test_empty_load(self, store: StateStore) -> None:
        date, events = store.load_scheduler_state()
        assert date == ""
        assert events == {}

    def test_unique_constraint_within_transaction(self, store: StateStore) -> None:
        """save_scheduler_state deletes before insert, so no conflict."""
        store.save_scheduler_state("2026-03-10", {"e": {"fired_at": "t1"}})
        store.save_scheduler_state("2026-03-10", {"e": {"fired_at": "t2"}})
        _, loaded = store.load_scheduler_state()
        assert loaded["e"]["fired_at"] == "t2"


# ═════════════════════════════════════════════════════════════════════════
# TestTransactions
# ═════════════════════════════════════════════════════════════════════════


class TestTransactions:
    def test_commit_persists(self, store: StateStore) -> None:
        store.begin_transaction()
        store.upsert_position("AAPL", _sample_position())
        store.commit()
        assert store.load_position("AAPL") is not None

    def test_rollback_reverts(self, store: StateStore) -> None:
        store.upsert_position("AAPL", _sample_position())
        store.begin_transaction()
        store.remove_position("AAPL")
        store.rollback()
        assert store.load_position("AAPL") is not None

    def test_cross_table_transaction(self, store: StateStore) -> None:
        store.begin_transaction()
        store.upsert_position("AAPL", _sample_position())
        store.insert_trade(_sample_trade(symbol="AAPL"))
        store.commit()
        assert store.load_position("AAPL") is not None
        assert len(store.load_trades(symbol="AAPL")) == 1

    def test_cross_table_rollback(self, store: StateStore) -> None:
        store.begin_transaction()
        store.upsert_position("AAPL", _sample_position())
        store.insert_trade(_sample_trade(symbol="AAPL"))
        store.rollback()
        assert store.load_position("AAPL") is None
        assert len(store.load_trades(symbol="AAPL")) == 0

    def test_lock_released_after_commit(self, store: StateStore) -> None:
        store.begin_transaction()
        store.commit()
        # Should be able to acquire lock again
        store.begin_transaction()
        store.commit()

    def test_lock_released_after_rollback(self, store: StateStore) -> None:
        store.begin_transaction()
        store.rollback()
        store.begin_transaction()
        store.commit()


# ═════════════════════════════════════════════════════════════════════════
# TestConcurrency
# ═════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    def test_reader_during_write(self, tmp_path: Path) -> None:
        """WAL mode allows reads from a separate connection while writing."""
        db = str(tmp_path / "concurrent.db")
        writer = StateStore(db_path=db)
        writer.upsert_position("AAPL", _sample_position())

        # Open a separate read connection
        read_conn = sqlite3.connect(db)
        read_conn.row_factory = sqlite3.Row
        cur = read_conn.execute("SELECT * FROM positions WHERE symbol='AAPL'")
        row = cur.fetchone()
        assert row is not None
        assert dict(row)["entry_price"] == 150.0

        read_conn.close()
        writer.close()

    def test_concurrent_writes_from_threads(self, tmp_path: Path) -> None:
        """Multiple threads writing through the same StateStore must not corrupt."""
        db = str(tmp_path / "threaded.db")
        store = StateStore(db_path=db)
        errors: list[Exception] = []

        def writer(symbol: str) -> None:
            try:
                store.upsert_position(symbol, _sample_position())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"SYM{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        positions = store.load_positions()
        assert len(positions) == 10
        store.close()

    def test_reader_sees_committed_data(self, tmp_path: Path) -> None:
        """A reader connection sees data after writer commits."""
        db = str(tmp_path / "visibility.db")
        store = StateStore(db_path=db)
        store.upsert_position("X", _sample_position())

        reader = sqlite3.connect(db)
        reader.execute("PRAGMA journal_mode=WAL")
        reader.row_factory = sqlite3.Row
        cur = reader.execute("SELECT COUNT(*) as cnt FROM positions")
        assert cur.fetchone()["cnt"] == 1

        reader.close()
        store.close()
