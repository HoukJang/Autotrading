"""
StateStore -- single-writer SQLite facade for all AutoTrader runtime state.

Uses WAL mode for concurrent reads, a threading.Lock for serialised writes,
and auto-commit semantics on every individual write call unless the caller
explicitly opens a transaction via begin_transaction().
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any


# ── terminal order states used by compact_orders ────────────────────────
_TERMINAL_ORDER_STATES = ("filled", "cancelled", "expired", "rejected")

# ── SQL: table + index creation ─────────────────────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS positions (
    symbol          TEXT PRIMARY KEY,
    strategy        TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    entry_price     REAL NOT NULL,
    entry_atr       REAL NOT NULL DEFAULT 1.0,
    entry_date_et   TEXT NOT NULL,
    qty             REAL NOT NULL,
    bars_held       INTEGER NOT NULL DEFAULT 0,
    highest_price   REAL NOT NULL,
    lowest_price    REAL NOT NULL,
    consecutive_loss_bars INTEGER NOT NULL DEFAULT 0,
    entry_adx       REAL NOT NULL DEFAULT 0.0,
    entry_time      TEXT,
    current_price   REAL,
    unrealized_pnl  REAL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    direction       TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    order_type      TEXT NOT NULL,
    order_role      TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    qty_requested   REAL NOT NULL,
    qty_filled      REAL NOT NULL DEFAULT 0.0,
    fill_price      REAL NOT NULL DEFAULT 0.0,
    state           TEXT NOT NULL DEFAULT 'submitted',
    submitted_at    TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    entry_atr       REAL NOT NULL DEFAULT 0.0,
    limit_price     REAL,
    stop_price      REAL,
    sl_order_id     TEXT,
    parent_order_id TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    direction       TEXT NOT NULL,
    side            TEXT NOT NULL,
    quantity        REAL NOT NULL,
    price           REAL NOT NULL,
    pnl             REAL NOT NULL DEFAULT 0.0,
    regime          TEXT NOT NULL DEFAULT 'UNKNOWN',
    equity_after    REAL NOT NULL DEFAULT 0.0,
    metadata        TEXT NOT NULL DEFAULT '{}',
    exit_reason     TEXT NOT NULL DEFAULT '',
    mfe             REAL NOT NULL DEFAULT 0.0,
    mae             REAL NOT NULL DEFAULT 0.0,
    bars_held       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_side ON trades(side);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    regime          TEXT NOT NULL DEFAULT 'UNKNOWN',
    position_count  INTEGER NOT NULL DEFAULT 0,
    open_positions  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS component_state (
    component_name  TEXT PRIMARY KEY,
    snapshot        TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduler_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    state_date      TEXT NOT NULL,
    event_name      TEXT NOT NULL,
    fired_at        TEXT NOT NULL,
    result          TEXT NOT NULL DEFAULT 'success',
    target_date     TEXT NOT NULL DEFAULT '',
    UNIQUE(state_date, event_name)
);
CREATE INDEX IF NOT EXISTS idx_scheduler_date ON scheduler_events(state_date);
"""


class StateStore:
    """Thread-safe SQLite facade for all AutoTrader runtime state."""

    # ── lifecycle ────────────────────────────────────────────────────────

    def __init__(self, db_path: str = "data/autotrader.db") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._in_transaction = False

        # Ensure parent directory exists
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # PRAGMAs
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            for statement in _SCHEMA_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    self._conn.execute(stmt)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── helpers ──────────────────────────────────────────────────────────

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return dict(row)

    def _auto_commit(self) -> None:
        """Commit unless we are inside a caller-managed transaction."""
        if not self._in_transaction:
            self._conn.commit()

    # ── positions ────────────────────────────────────────────────────────

    def upsert_position(self, symbol: str, position: dict) -> None:
        cols = [
            "symbol", "strategy", "direction", "entry_price", "entry_atr",
            "entry_date_et", "qty", "bars_held", "highest_price",
            "lowest_price", "consecutive_loss_bars", "entry_adx",
            "entry_time", "current_price", "unrealized_pnl", "updated_at",
        ]
        vals = {c: position.get(c) for c in cols}
        vals["symbol"] = symbol
        if vals.get("updated_at") is None:
            vals["updated_at"] = self._now_iso()
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO positions ({col_names}) VALUES ({placeholders})"
        with self._lock:
            self._conn.execute(sql, vals)
            self._auto_commit()

    def update_mfe_mae(
        self, symbol: str, highest_price: float, lowest_price: float
    ) -> None:
        sql = (
            "UPDATE positions SET highest_price=?, lowest_price=?, updated_at=? "
            "WHERE symbol=?"
        )
        with self._lock:
            self._conn.execute(sql, (highest_price, lowest_price, self._now_iso(), symbol))
            self._auto_commit()

    def remove_position(self, symbol: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            self._auto_commit()

    def load_positions(self) -> dict[str, dict]:
        cur = self._conn.execute("SELECT * FROM positions")
        rows = cur.fetchall()
        return {r["symbol"]: self._row_to_dict(r) for r in rows}

    def load_position(self, symbol: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,))
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    # ── orders ───────────────────────────────────────────────────────────

    def insert_order(self, record: dict) -> None:
        cols = [
            "order_id", "symbol", "side", "direction", "order_type",
            "order_role", "strategy", "qty_requested", "qty_filled",
            "fill_price", "state", "submitted_at", "updated_at",
            "entry_atr", "limit_price", "stop_price", "sl_order_id",
            "parent_order_id", "metadata",
        ]
        vals = {}
        for c in cols:
            v = record.get(c)
            if c == "metadata" and not isinstance(v, str):
                v = json.dumps(v if v is not None else {})
            vals[c] = v
        col_names = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = f"INSERT INTO orders ({col_names}) VALUES ({placeholders})"
        with self._lock:
            self._conn.execute(sql, vals)
            self._auto_commit()

    def update_order_state(
        self,
        order_id: str,
        state: str,
        qty_filled: float = 0.0,
        fill_price: float = 0.0,
        **kwargs: Any,
    ) -> None:
        sets = ["state=?", "qty_filled=?", "fill_price=?", "updated_at=?"]
        params: list[Any] = [state, qty_filled, fill_price, self._now_iso()]
        for k, v in kwargs.items():
            sets.append(f"{k}=?")
            params.append(v)
        params.append(order_id)
        sql = f"UPDATE orders SET {', '.join(sets)} WHERE order_id=?"
        with self._lock:
            self._conn.execute(sql, params)
            self._auto_commit()

    def load_orders(self, pending_only: bool = False) -> dict[str, dict]:
        if pending_only:
            placeholders = ", ".join("?" for _ in _TERMINAL_ORDER_STATES)
            sql = f"SELECT * FROM orders WHERE state NOT IN ({placeholders})"
            cur = self._conn.execute(sql, _TERMINAL_ORDER_STATES)
        else:
            cur = self._conn.execute("SELECT * FROM orders")
        rows = cur.fetchall()
        result = {}
        for r in rows:
            d = self._row_to_dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result[d["order_id"]] = d
        return result

    def load_order(self, order_id: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = self._row_to_dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def compact_orders(self, keep_hours: int = 72) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=keep_hours)
        ).strftime("%Y-%m-%d %H:%M:%S")
        placeholders = ", ".join("?" for _ in _TERMINAL_ORDER_STATES)
        sql = (
            f"DELETE FROM orders WHERE state IN ({placeholders}) "
            "AND updated_at < ?"
        )
        params = list(_TERMINAL_ORDER_STATES) + [cutoff]
        with self._lock:
            cur = self._conn.execute(sql, params)
            deleted = cur.rowcount
            self._auto_commit()
        return deleted

    # ── trades ───────────────────────────────────────────────────────────

    def insert_trade(self, record: dict) -> None:
        cols = [
            "timestamp", "symbol", "strategy", "direction", "side",
            "quantity", "price", "pnl", "regime", "equity_after",
            "metadata", "exit_reason", "mfe", "mae", "bars_held",
        ]
        vals = {}
        for c in cols:
            v = record.get(c)
            if c == "metadata" and not isinstance(v, str):
                v = json.dumps(v if v is not None else {})
            vals[c] = v
        col_names = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = f"INSERT INTO trades ({col_names}) VALUES ({placeholders})"
        with self._lock:
            self._conn.execute(sql, vals)
            self._auto_commit()

    def load_trades(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy is not None:
            clauses.append("strategy=?")
            params.append(strategy)
        if symbol is not None:
            clauses.append("symbol=?")
            params.append(symbol)
        sql = "SELECT * FROM trades"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp ASC"
        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def load_trades_since(self, since_iso: str) -> list[dict]:
        sql = "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp ASC"
        cur = self._conn.execute(sql, (since_iso,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    # ── equity snapshots ─────────────────────────────────────────────────

    def insert_equity_snapshot(self, snapshot: dict) -> None:
        cols = [
            "timestamp", "equity", "cash", "regime",
            "position_count", "open_positions",
        ]
        vals = {}
        for c in cols:
            v = snapshot.get(c)
            if c == "open_positions" and not isinstance(v, str):
                v = json.dumps(v if v is not None else [])
            vals[c] = v
        col_names = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = f"INSERT INTO equity_snapshots ({col_names}) VALUES ({placeholders})"
        with self._lock:
            self._conn.execute(sql, vals)
            self._auto_commit()

    def load_equity_snapshots(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY timestamp ASC"
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            if "open_positions" in d and isinstance(d["open_positions"], str):
                try:
                    d["open_positions"] = json.loads(d["open_positions"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    # ── component state ──────────────────────────────────────────────────

    def save_component_state(self, component_name: str, snapshot: dict) -> None:
        sql = (
            "INSERT OR REPLACE INTO component_state "
            "(component_name, snapshot, updated_at) VALUES (?, ?, ?)"
        )
        with self._lock:
            self._conn.execute(
                sql, (component_name, json.dumps(snapshot), self._now_iso())
            )
            self._auto_commit()

    def load_component_states(self) -> dict[str, dict]:
        cur = self._conn.execute("SELECT * FROM component_state")
        rows = cur.fetchall()
        result = {}
        for r in rows:
            d = self._row_to_dict(r)
            try:
                result[d["component_name"]] = json.loads(d["snapshot"])
            except (json.JSONDecodeError, TypeError):
                result[d["component_name"]] = {}
        return result

    def save_all_component_states(self, components: dict[str, dict]) -> None:
        sql = (
            "INSERT OR REPLACE INTO component_state "
            "(component_name, snapshot, updated_at) VALUES (?, ?, ?)"
        )
        now = self._now_iso()
        with self._lock:
            for name, snap in components.items():
                self._conn.execute(sql, (name, json.dumps(snap), now))
            self._conn.commit()

    # ── scheduler events ─────────────────────────────────────────────────

    def save_scheduler_state(
        self, state_date: str, events: dict[str, dict]
    ) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM scheduler_events WHERE state_date=?", (state_date,)
            )
            for event_name, evt in events.items():
                self._conn.execute(
                    "INSERT INTO scheduler_events "
                    "(state_date, event_name, fired_at, result, target_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        state_date,
                        event_name,
                        evt.get("fired_at", self._now_iso()),
                        evt.get("result", "success"),
                        evt.get("target_date", ""),
                    ),
                )
            self._conn.commit()

    def load_scheduler_state(self) -> tuple[str, dict[str, dict]]:
        cur = self._conn.execute(
            "SELECT * FROM scheduler_events "
            "WHERE state_date = (SELECT MAX(state_date) FROM scheduler_events)"
        )
        rows = cur.fetchall()
        if not rows:
            return ("", {})
        state_date = rows[0]["state_date"]
        events: dict[str, dict] = {}
        for r in rows:
            d = self._row_to_dict(r)
            events[d["event_name"]] = d
        return (state_date, events)

    # ── explicit transactions ────────────────────────────────────────────

    def begin_transaction(self) -> None:
        self._lock.acquire()
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True

    def commit(self) -> None:
        try:
            self._conn.commit()
        finally:
            self._in_transaction = False
            self._lock.release()

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        finally:
            self._in_transaction = False
            self._lock.release()
