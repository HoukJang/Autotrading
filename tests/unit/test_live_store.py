"""Tests for SQLite live data store."""
import pytest
from datetime import datetime, timezone
from autotrader.data.live_store import LiveDataStore
from autotrader.portfolio.trade_logger import LiveTradeRecord, EquitySnapshot


class TestLiveDataStoreInit:
    def test_creates_database(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = LiveDataStore(db_path)
        assert (tmp_path / "test.db").exists()
        store.close()

    def test_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = LiveDataStore(db_path)
        tables = store.list_tables()
        assert "trades" in tables
        assert "equity_snapshots" in tables
        assert "regime_history" in tables
        assert "rotation_events" in tables
        store.close()


class TestTradeStorage:
    def test_insert_and_query_trade(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="adx_pullback", direction="long", side="buy",
            quantity=10, price=150.0, pnl=0.0,
            regime="TREND", equity_after=10000.0, metadata={},
        )
        store.insert_trade(record)
        trades = store.query_trades()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"
        assert trades[0]["strategy"] == "adx_pullback"
        store.close()

    def test_query_trades_by_strategy(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        for strat in ["adx_pullback", "rsi_mean_reversion", "adx_pullback"]:
            store.insert_trade(LiveTradeRecord(
                timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
                strategy=strat, direction="long", side="buy",
                quantity=10, price=100.0, pnl=0.0,
                regime="TREND", equity_after=10000.0, metadata={},
            ))
        trades = store.query_trades(strategy="adx_pullback")
        assert len(trades) == 2
        store.close()

    def test_query_trades_by_symbol(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        for sym in ["AAPL", "MSFT", "AAPL"]:
            store.insert_trade(LiveTradeRecord(
                timestamp="2026-01-01T00:00:00Z", symbol=sym,
                strategy="test", direction="long", side="buy",
                quantity=10, price=100.0, pnl=0.0,
                regime="TREND", equity_after=10000.0, metadata={},
            ))
        trades = store.query_trades(symbol="MSFT")
        assert len(trades) == 1
        store.close()

    def test_query_trades_by_regime(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        for regime in ["TREND", "RANGING", "TREND"]:
            store.insert_trade(LiveTradeRecord(
                timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
                strategy="test", direction="long", side="buy",
                quantity=10, price=100.0, pnl=0.0,
                regime=regime, equity_after=10000.0, metadata={},
            ))
        trades = store.query_trades(regime="RANGING")
        assert len(trades) == 1
        store.close()


class TestEquityStorage:
    def test_insert_and_query_equity(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        snap = EquitySnapshot(
            timestamp="2026-01-01T00:00:00Z", equity=10000.0,
            cash=5000.0, regime="TREND", position_count=3,
            open_positions=["AAPL", "MSFT", "GOOGL"],
        )
        store.insert_equity_snapshot(snap)
        snaps = store.query_equity_snapshots()
        assert len(snaps) == 1
        assert snaps[0]["equity"] == 10000.0
        store.close()

    def test_multiple_snapshots_ordered(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        for i in range(5):
            store.insert_equity_snapshot(EquitySnapshot(
                timestamp=f"2026-01-0{i+1}T00:00:00Z", equity=10000.0 + i * 100,
                cash=5000.0, regime="TREND", position_count=i,
                open_positions=[],
            ))
        snaps = store.query_equity_snapshots()
        assert len(snaps) == 5
        assert snaps[0]["equity"] == 10000.0
        assert snaps[4]["equity"] == 10400.0
        store.close()


class TestRegimeHistoryStorage:
    def test_insert_and_query_regime(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        store.insert_regime_change(
            timestamp="2026-01-01T00:00:00Z",
            previous_regime="UNCERTAIN",
            current_regime="TREND",
            bars_in_new_regime=3,
        )
        history = store.query_regime_history()
        assert len(history) == 1
        assert history[0]["previous_regime"] == "UNCERTAIN"
        assert history[0]["current_regime"] == "TREND"
        store.close()


class TestRotationEventStorage:
    def test_insert_and_query_rotation(self, tmp_path):
        store = LiveDataStore(str(tmp_path / "test.db"))
        store.insert_rotation_event(
            timestamp="2026-01-01T00:00:00Z",
            trigger="weekly",
            reason="scheduled rotation",
            symbols_in=["AAPL", "MSFT"],
            symbols_out=["GOOGL"],
        )
        events = store.query_rotation_events()
        assert len(events) == 1
        assert events[0]["trigger"] == "weekly"
        store.close()


class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with LiveDataStore(db_path) as store:
            store.insert_trade(LiveTradeRecord(
                timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
                strategy="test", direction="long", side="buy",
                quantity=10, price=100.0, pnl=0.0,
                regime="TREND", equity_after=10000.0, metadata={},
            ))
        # Connection closed, but can reopen
        with LiveDataStore(db_path) as store:
            trades = store.query_trades()
            assert len(trades) == 1
