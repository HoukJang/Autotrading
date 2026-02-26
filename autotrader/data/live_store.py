"""SQLite storage for live trading data.

Provides structured storage and querying for trades, equity snapshots,
regime changes, and rotation events. Complements the JSONL-based
TradeLogger with SQL query capabilities.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from autotrader.portfolio.trade_logger import EquitySnapshot, LiveTradeRecord

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    pnl REAL NOT NULL,
    regime TEXT NOT NULL,
    equity_after REAL NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    regime TEXT NOT NULL,
    position_count INTEGER NOT NULL,
    open_positions TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS regime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    previous_regime TEXT NOT NULL,
    current_regime TEXT NOT NULL,
    bars_in_new_regime INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rotation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    trigger TEXT NOT NULL,
    reason TEXT DEFAULT '',
    symbols_in TEXT DEFAULT '[]',
    symbols_out TEXT DEFAULT '[]'
);
"""


class LiveDataStore:
    """SQLite-backed storage for live trading analytics.

    Stores trades, equity snapshots, regime transitions, and rotation
    events in a local SQLite database for structured querying.

    Supports use as a context manager::

        with LiveDataStore("path/to/db.sqlite") as store:
            store.insert_trade(record)
    """

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_TABLES)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> LiveDataStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    def list_tables(self) -> list[str]:
        """Return names of all user-created tables in the database."""
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  Trades                                                              #
    # ------------------------------------------------------------------ #

    def insert_trade(self, record: LiveTradeRecord) -> None:
        """Insert a single trade record into the database."""
        self._conn.execute(
            """INSERT INTO trades
               (timestamp, symbol, strategy, direction, side,
                quantity, price, pnl, regime, equity_after, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.timestamp,
                record.symbol,
                record.strategy,
                record.direction,
                record.side,
                record.quantity,
                record.price,
                record.pnl,
                record.regime,
                record.equity_after,
                json.dumps(record.metadata),
            ),
        )
        self._conn.commit()

    def query_trades(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
        regime: str | None = None,
    ) -> list[dict]:
        """Query trades with optional filters.

        Args:
            strategy: Filter by strategy name.
            symbol: Filter by ticker symbol.
            regime: Filter by market regime at time of trade.

        Returns:
            List of trade rows as dictionaries, ordered by insertion.
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []
        if strategy is not None:
            query += " AND strategy = ?"
            params.append(strategy)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if regime is not None:
            query += " AND regime = ?"
            params.append(regime)
        query += " ORDER BY id"
        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  Equity Snapshots                                                    #
    # ------------------------------------------------------------------ #

    def insert_equity_snapshot(self, snapshot: EquitySnapshot) -> None:
        """Insert an equity snapshot into the database."""
        self._conn.execute(
            """INSERT INTO equity_snapshots
               (timestamp, equity, cash, regime, position_count, open_positions)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot.timestamp,
                snapshot.equity,
                snapshot.cash,
                snapshot.regime,
                snapshot.position_count,
                json.dumps(snapshot.open_positions),
            ),
        )
        self._conn.commit()

    def query_equity_snapshots(self) -> list[dict]:
        """Return all equity snapshots ordered by insertion."""
        cursor = self._conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  Regime History                                                       #
    # ------------------------------------------------------------------ #

    def insert_regime_change(
        self,
        timestamp: str,
        previous_regime: str,
        current_regime: str,
        bars_in_new_regime: int,
    ) -> None:
        """Record a confirmed regime transition."""
        self._conn.execute(
            """INSERT INTO regime_history
               (timestamp, previous_regime, current_regime, bars_in_new_regime)
               VALUES (?, ?, ?, ?)""",
            (timestamp, previous_regime, current_regime, bars_in_new_regime),
        )
        self._conn.commit()

    def query_regime_history(self) -> list[dict]:
        """Return all regime transitions ordered by insertion."""
        cursor = self._conn.execute(
            "SELECT * FROM regime_history ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  Rotation Events                                                     #
    # ------------------------------------------------------------------ #

    def insert_rotation_event(
        self,
        timestamp: str,
        trigger: str,
        reason: str,
        symbols_in: list[str],
        symbols_out: list[str],
    ) -> None:
        """Record a universe rotation event."""
        self._conn.execute(
            """INSERT INTO rotation_events
               (timestamp, trigger, reason, symbols_in, symbols_out)
               VALUES (?, ?, ?, ?, ?)""",
            (
                timestamp,
                trigger,
                reason,
                json.dumps(symbols_in),
                json.dumps(symbols_out),
            ),
        )
        self._conn.commit()

    def query_rotation_events(self) -> list[dict]:
        """Return all rotation events ordered by insertion."""
        cursor = self._conn.execute(
            "SELECT * FROM rotation_events ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]
