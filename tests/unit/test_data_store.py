import pytest
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.data.sqlite_store import SQLiteStore


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = SQLiteStore(db_path)
    await s.initialize()
    yield s
    await s.close()


class TestSQLiteStore:
    async def test_save_and_load_bars(self, store):
        bars = [
            Bar("AAPL", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), 150, 152, 149, 151, 1000),
            Bar("AAPL", datetime(2026, 1, 15, 10, 1, tzinfo=timezone.utc), 151, 153, 150, 152, 1100),
        ]
        await store.save_bars(bars)
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc),
        )
        assert len(loaded) == 2
        assert loaded[0].close == 151

    async def test_load_empty(self, store):
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        assert loaded == []

    async def test_no_duplicates(self, store):
        bar = Bar("AAPL", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), 150, 152, 149, 151, 1000)
        await store.save_bars([bar])
        await store.save_bars([bar])  # duplicate
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc),
        )
        assert len(loaded) == 1
