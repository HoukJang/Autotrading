"""Live trade and equity logging for performance tracking.

Appends trade records and equity snapshots to JSONL files
for post-hoc analysis and performance monitoring.

Supports optional SQLite backend via StateStore for durable,
queryable storage with automatic JSONL migration on first startup.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autotrader.data.state_store import StateStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveTradeRecord:
    """Single trade execution record for live performance tracking."""

    timestamp: str
    symbol: str
    strategy: str
    direction: str
    side: str
    quantity: float
    price: float
    pnl: float
    regime: str
    equity_after: float
    metadata: dict
    exit_reason: str = ""
    mfe: float = 0.0
    mae: float = 0.0
    bars_held: int = 0


@dataclass(frozen=True)
class EquitySnapshot:
    """Point-in-time equity snapshot for drawdown and curve tracking."""

    timestamp: str
    equity: float
    cash: float
    regime: str
    position_count: int
    open_positions: list[str]


class TradeLogger:
    """Append-only JSONL logger for trades and equity snapshots.

    When a StateStore is attached via ``set_state_store()``, all writes
    go to SQLite first (primary) then JSONL (backup).  Reads prefer
    SQLite when available, falling back to JSONL parsing.
    """

    def __init__(self, trade_log_path: str, equity_log_path: str) -> None:
        self._trade_path = Path(trade_log_path)
        self._equity_path = Path(equity_log_path)
        self._write_lock = threading.Lock()
        self._state_store: StateStore | None = None
        self._migration_done = False

    # ── StateStore integration ────────────────────────────────────────

    def set_state_store(self, store: StateStore) -> None:
        """Attach a StateStore for SQLite-backed persistence.

        On first call, migrates any existing JSONL data into the DB
        if the corresponding DB tables are empty.
        """
        self._state_store = store
        if not self._migration_done:
            self._migrate_jsonl_to_db()
            self._migration_done = True

    # ── conversion helpers ────────────────────────────────────────────

    @staticmethod
    def _trade_to_dict(record: LiveTradeRecord) -> dict:
        return {
            "timestamp": record.timestamp,
            "symbol": record.symbol,
            "strategy": record.strategy,
            "direction": record.direction,
            "side": record.side,
            "quantity": record.quantity,
            "price": record.price,
            "pnl": record.pnl,
            "regime": record.regime,
            "equity_after": record.equity_after,
            "metadata": record.metadata,
            "exit_reason": getattr(record, "exit_reason", ""),
            "mfe": getattr(record, "mfe", 0.0),
            "mae": getattr(record, "mae", 0.0),
            "bars_held": getattr(record, "bars_held", 0),
        }

    @staticmethod
    def _equity_to_dict(snapshot: EquitySnapshot) -> dict:
        return {
            "timestamp": snapshot.timestamp,
            "equity": snapshot.equity,
            "cash": snapshot.cash,
            "regime": snapshot.regime,
            "position_count": snapshot.position_count,
            "open_positions": snapshot.open_positions,
        }

    # ── write methods ─────────────────────────────────────────────────

    def log_trade(self, record: LiveTradeRecord) -> None:
        """Append a trade record to SQLite (if available) and JSONL.

        SQLite is written first as the primary store.  JSONL is kept
        as a durable backup.  SQLite failures are logged but do not
        prevent the JSONL write from proceeding.
        """
        # SQLite primary write
        if self._state_store is not None:
            try:
                self._state_store.insert_trade(self._trade_to_dict(record))
            except Exception:
                logger.exception("Failed to write trade to SQLite, falling back to JSONL only")

        # JSONL backup write
        self._trade_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
            with open(self._trade_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def log_equity(self, snapshot: EquitySnapshot) -> None:
        """Append an equity snapshot to SQLite (if available) and JSONL.

        SQLite is written first as the primary store.  JSONL is kept
        as a durable backup.  SQLite failures are logged but do not
        prevent the JSONL write from proceeding.
        """
        # SQLite primary write
        if self._state_store is not None:
            try:
                self._state_store.insert_equity_snapshot(
                    self._equity_to_dict(snapshot)
                )
            except Exception:
                logger.exception("Failed to write equity snapshot to SQLite, falling back to JSONL only")

        # JSONL backup write
        self._equity_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
            with open(self._equity_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snapshot)) + "\n")
                f.flush()
                os.fsync(f.fileno())

    # ── read methods ──────────────────────────────────────────────────

    def read_trades(self) -> list[LiveTradeRecord]:
        """Read all trade records.

        Tries SQLite first; falls back to JSONL if the DB has no rows
        or if a read error occurs.  Handles old records that lack the
        newer fields (exit_reason, mfe, mae, bars_held) by supplying
        defaults.
        """
        if self._state_store is not None:
            try:
                rows = self._state_store.load_trades()
                if rows:
                    return [self._dict_to_trade(r) for r in rows]
            except Exception:
                logger.exception("Failed to read trades from SQLite, falling back to JSONL")

        return self._read_trades_jsonl()

    def read_equity(self) -> list[EquitySnapshot]:
        """Read all equity snapshots.

        Tries SQLite first; falls back to JSONL if the DB has no rows
        or if a read error occurs.
        """
        if self._state_store is not None:
            try:
                rows = self._state_store.load_equity_snapshots()
                if rows:
                    return [self._dict_to_equity(r) for r in rows]
            except Exception:
                logger.exception("Failed to read equity snapshots from SQLite, falling back to JSONL")

        return self._read_equity_jsonl()

    # ── JSONL reading (original logic) ────────────────────────────────

    def _read_trades_jsonl(self) -> list[LiveTradeRecord]:
        """Read trade records from JSONL, skipping corrupt lines."""
        if not self._trade_path.exists():
            return []
        records: list[LiveTradeRecord] = []
        with open(self._trade_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(LiveTradeRecord(
                        timestamp=data["timestamp"],
                        symbol=data["symbol"],
                        strategy=data["strategy"],
                        direction=data["direction"],
                        side=data["side"],
                        quantity=data["quantity"],
                        price=data["price"],
                        pnl=data["pnl"],
                        regime=data["regime"],
                        equity_after=data["equity_after"],
                        metadata=data["metadata"],
                        exit_reason=data.get("exit_reason", ""),
                        mfe=data.get("mfe", 0.0),
                        mae=data.get("mae", 0.0),
                        bars_held=data.get("bars_held", 0),
                    ))
                except (json.JSONDecodeError, TypeError, KeyError):
                    logger.warning("Skipping corrupt trade log line: %s", line[:80])
        return records

    def _read_equity_jsonl(self) -> list[EquitySnapshot]:
        """Read equity snapshots from JSONL, skipping corrupt lines."""
        if not self._equity_path.exists():
            return []
        snapshots: list[EquitySnapshot] = []
        with open(self._equity_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    snapshots.append(EquitySnapshot(**data))
                except (json.JSONDecodeError, TypeError, KeyError):
                    logger.warning("Skipping corrupt equity log line: %s", line[:80])
        return snapshots

    # ── dict-to-dataclass helpers ─────────────────────────────────────

    @staticmethod
    def _dict_to_trade(d: dict) -> LiveTradeRecord:
        """Convert a StateStore dict row back to a LiveTradeRecord."""
        meta = d.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        return LiveTradeRecord(
            timestamp=d["timestamp"],
            symbol=d["symbol"],
            strategy=d["strategy"],
            direction=d["direction"],
            side=d["side"],
            quantity=d["quantity"],
            price=d["price"],
            pnl=d.get("pnl", 0.0),
            regime=d.get("regime", "UNKNOWN"),
            equity_after=d.get("equity_after", 0.0),
            metadata=meta,
            exit_reason=d.get("exit_reason", ""),
            mfe=d.get("mfe", 0.0),
            mae=d.get("mae", 0.0),
            bars_held=d.get("bars_held", 0),
        )

    @staticmethod
    def _dict_to_equity(d: dict) -> EquitySnapshot:
        """Convert a StateStore dict row back to an EquitySnapshot."""
        positions = d.get("open_positions", [])
        if isinstance(positions, str):
            try:
                positions = json.loads(positions)
            except (json.JSONDecodeError, TypeError):
                positions = []
        return EquitySnapshot(
            timestamp=d["timestamp"],
            equity=d["equity"],
            cash=d["cash"],
            regime=d.get("regime", "UNKNOWN"),
            position_count=d.get("position_count", 0),
            open_positions=positions,
        )

    # ── JSONL -> SQLite migration ─────────────────────────────────────

    def _migrate_jsonl_to_db(self) -> None:
        """One-time migration: copy JSONL data into SQLite tables.

        Only runs if the DB tables are empty AND the JSONL files exist.
        Equity snapshots are inserted in batches of 500 to handle
        potentially large files without excessive memory pressure.
        """
        if self._state_store is None:
            return

        try:
            self._migrate_trades()
            self._migrate_equity()
        except Exception:
            logger.exception("JSONL-to-SQLite migration failed; will retry next startup")
            self._migration_done = False

    def _migrate_trades(self) -> None:
        """Migrate trades from JSONL to SQLite if DB is empty."""
        assert self._state_store is not None
        existing = self._state_store.load_trades()
        if existing:
            logger.debug("Trades table already has %d rows, skipping migration", len(existing))
            return

        records = self._read_trades_jsonl()
        if not records:
            return

        logger.info("Migrating %d trades from JSONL to SQLite", len(records))
        for record in records:
            try:
                self._state_store.insert_trade(self._trade_to_dict(record))
            except Exception:
                logger.warning("Failed to migrate trade record: %s %s", record.timestamp, record.symbol)

    def _migrate_equity(self) -> None:
        """Migrate equity snapshots from JSONL to SQLite if DB is empty.

        Inserts in batches of 500 to handle large files.
        """
        assert self._state_store is not None
        existing = self._state_store.load_equity_snapshots()
        if existing:
            logger.debug("Equity table already has %d rows, skipping migration", len(existing))
            return

        snapshots = self._read_equity_jsonl()
        if not snapshots:
            return

        logger.info("Migrating %d equity snapshots from JSONL to SQLite", len(snapshots))
        batch_size = 500
        for i in range(0, len(snapshots), batch_size):
            batch = snapshots[i : i + batch_size]
            for snap in batch:
                try:
                    self._state_store.insert_equity_snapshot(
                        self._equity_to_dict(snap)
                    )
                except Exception:
                    logger.warning(
                        "Failed to migrate equity snapshot: %s", snap.timestamp
                    )
