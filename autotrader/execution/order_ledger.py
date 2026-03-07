"""Persistent order tracking ledger to eliminate ghost fills.

Every order submitted to Alpaca is recorded to disk BEFORE the broker
response is processed.  On startup, pending orders are reconciled.

Storage: append-only JSONL at ``data/order_ledger.jsonl``.
Each line is a complete OrderRecord snapshot at a state transition.
On load(), all lines are replayed -- last line per order_id wins.
Writes use flush() + os.fsync() for crash safety.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

logger = logging.getLogger("autotrader.execution.order_ledger")


class OrderState(str, Enum):
    SUBMITTED = "submitted"
    PENDING_FILL = "pending_fill"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


PENDING_STATES = {OrderState.SUBMITTED, OrderState.PENDING_FILL, OrderState.PARTIALLY_FILLED}
TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELLED, OrderState.EXPIRED, OrderState.REJECTED}


@dataclass
class OrderRecord:
    """Snapshot of an order at a given state transition."""

    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    direction: Literal["long", "short"]
    order_type: str  # "market" / "limit" / "stop"
    order_role: Literal["entry", "exit", "stop_loss"]
    strategy: str
    qty_requested: float
    qty_filled: float = 0.0
    fill_price: float = 0.0
    state: OrderState = OrderState.SUBMITTED
    submitted_at: str = ""
    updated_at: str = ""
    entry_atr: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    sl_order_id: str | None = None
    parent_order_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.submitted_at:
            self.submitted_at = now
        if not self.updated_at:
            self.updated_at = now
        if isinstance(self.state, str):
            self.state = OrderState(self.state)


_DEFAULT_PATH = Path("data/order_ledger.jsonl")


class OrderLedger:
    """Append-only JSONL ledger for durable order state tracking."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._orders: dict[str, OrderRecord] = {}

    def load(self) -> dict[str, OrderRecord]:
        """Replay JSONL file; last line per order_id wins."""
        self._orders.clear()
        if not self._path.exists():
            logger.info("No ledger file at %s; starting empty", self._path)
            return self._orders
        corrupted, total = 0, 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                total += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    record = self._dict_to_record(json.loads(line))
                    self._orders[record.order_id] = record
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    corrupted += 1
                    logger.warning("Corrupted ledger line %d (%s); skipping", total, exc)
        logger.info(
            "Loaded order ledger: %d order(s) from %d line(s) (%d corrupted)",
            len(self._orders), total, corrupted,
        )
        return self._orders

    def _append(self, record: OrderRecord) -> None:
        """Append one record line with fsync for crash safety."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._orders[record.order_id] = record

    # -- State transitions --------------------------------------------------

    def record_submission(self, record: OrderRecord) -> None:
        """Record a newly submitted order. Persists immediately."""
        record.state = OrderState.SUBMITTED
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._append(record)
        logger.debug(
            "Ledger: SUBMITTED %s %s %s %.0f (role=%s, strategy=%s)",
            record.side, record.symbol, record.order_type,
            record.qty_requested, record.order_role, record.strategy,
        )

    def record_fill(self, order_id: str, qty_filled: float,
                     fill_price: float, partial: bool = False) -> None:
        """Update an order to FILLED or PARTIALLY_FILLED."""
        record = self._orders.get(order_id)
        if record is None:
            logger.warning("record_fill: unknown order_id %s", order_id)
            return
        record.qty_filled = qty_filled
        record.fill_price = fill_price
        record.state = OrderState.PARTIALLY_FILLED if partial else OrderState.FILLED
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._append(record)

    def record_cancel(self, order_id: str) -> None:
        """Update an order to CANCELLED."""
        self.record_terminal(order_id, OrderState.CANCELLED)

    def record_terminal(self, order_id: str, state: OrderState) -> None:
        """Update an order to any terminal state."""
        if state not in TERMINAL_STATES:
            logger.warning("record_terminal: %s is not a terminal state", state)
            return
        record = self._orders.get(order_id)
        if record is None:
            logger.warning("record_terminal: unknown order_id %s", order_id)
            return
        record.state = state
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._append(record)

    def link_sl_order(self, entry_order_id: str, sl_order_id: str) -> None:
        """Link a stop-loss order to its parent entry order."""
        record = self._orders.get(entry_order_id)
        if record is None:
            logger.warning("link_sl_order: unknown entry order_id %s", entry_order_id)
            return
        record.sl_order_id = sl_order_id
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._append(record)

    # -- Queries -------------------------------------------------------------

    def get_pending_entries(self) -> list[OrderRecord]:
        """Return entry orders still in a pending state."""
        return [r for r in self._orders.values()
                if r.order_role == "entry" and r.state in PENDING_STATES]

    def get_pending_stop_losses(self) -> dict[str, OrderRecord]:
        """Return symbol -> OrderRecord for active stop-loss orders."""
        result: dict[str, OrderRecord] = {}
        for r in self._orders.values():
            if r.order_role == "stop_loss" and r.state in PENDING_STATES:
                result[r.symbol] = r
        return result

    def get_order(self, order_id: str) -> OrderRecord | None:
        """Look up an order by its Alpaca order ID."""
        return self._orders.get(order_id)

    # -- Maintenance ---------------------------------------------------------

    def compact(self, keep_hours: int = 72) -> int:
        """Rewrite ledger keeping pending + recent terminal orders.

        Returns number of orders removed.
        """
        now, keep, removed = datetime.now(timezone.utc), [], 0
        for record in self._orders.values():
            if record.state in PENDING_STATES:
                keep.append(record)
                continue
            try:
                updated = datetime.fromisoformat(record.updated_at)
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                age_hours = (now - updated).total_seconds() / 3600.0
                if age_hours <= keep_hours:
                    keep.append(record)
                else:
                    removed += 1
            except (ValueError, TypeError):
                keep.append(record)
        # Atomic rewrite: tmp + rename
        tmp_path = self._path.with_suffix(".tmp")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            for record in keep:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(self._path))
        self._orders = {r.order_id: r for r in keep}
        logger.info("Ledger compacted: kept %d, removed %d", len(keep), removed)
        return removed

    # -- Internal ------------------------------------------------------------

    @staticmethod
    def _dict_to_record(raw: dict) -> OrderRecord:
        """Deserialize a JSON dict into an OrderRecord."""
        return OrderRecord(
            order_id=raw["order_id"],
            symbol=raw["symbol"],
            side=raw["side"],
            direction=raw["direction"],
            order_type=raw["order_type"],
            order_role=raw["order_role"],
            strategy=raw["strategy"],
            qty_requested=float(raw["qty_requested"]),
            qty_filled=float(raw.get("qty_filled", 0.0)),
            fill_price=float(raw.get("fill_price", 0.0)),
            state=OrderState(raw.get("state", "submitted")),
            submitted_at=raw.get("submitted_at", ""),
            updated_at=raw.get("updated_at", ""),
            entry_atr=float(raw.get("entry_atr", 0.0)),
            limit_price=raw.get("limit_price"),
            stop_price=raw.get("stop_price"),
            sl_order_id=raw.get("sl_order_id"),
            parent_order_id=raw.get("parent_order_id"),
            metadata=raw.get("metadata", {}),
        )
