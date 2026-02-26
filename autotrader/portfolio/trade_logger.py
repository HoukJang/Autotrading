"""Live trade and equity logging for performance tracking.

Appends trade records and equity snapshots to JSONL files
for post-hoc analysis and performance monitoring.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

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
    """Append-only JSONL logger for trades and equity snapshots."""

    def __init__(self, trade_log_path: str, equity_log_path: str) -> None:
        self._trade_path = Path(trade_log_path)
        self._equity_path = Path(equity_log_path)

    def log_trade(self, record: LiveTradeRecord) -> None:
        """Append a trade record to the JSONL log."""
        self._trade_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._trade_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def log_equity(self, snapshot: EquitySnapshot) -> None:
        """Append an equity snapshot to the JSONL log."""
        self._equity_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._equity_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def read_trades(self) -> list[LiveTradeRecord]:
        """Read all trade records, skipping corrupt lines.

        Handles old records that lack the newer fields (exit_reason,
        mfe, mae, bars_held) by supplying defaults.
        """
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

    def read_equity(self) -> list[EquitySnapshot]:
        """Read all equity snapshots, skipping corrupt lines."""
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
