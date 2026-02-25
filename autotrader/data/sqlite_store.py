from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from autotrader.core.types import Bar
from autotrader.data.store import DataStore


class SQLiteStore(DataStore):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save_bars(self, bars: list[Bar]) -> None:
        assert self._db is not None
        await self._db.executemany(
            "INSERT OR IGNORE INTO bars (symbol, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(b.symbol, b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume) for b in bars],
        )
        await self._db.commit()

    async def load_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT symbol, timestamp, open, high, low, close, volume FROM bars WHERE symbol = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (symbol, start.isoformat(), end.isoformat()),
        )
        rows = await cursor.fetchall()
        return [
            Bar(
                symbol=r[0],
                timestamp=datetime.fromisoformat(r[1]),
                open=r[2], high=r[3], low=r[4], close=r[5], volume=r[6],
            )
            for r in rows
        ]
