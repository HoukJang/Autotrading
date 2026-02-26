import json
import pytest
from autotrader.portfolio.trade_logger import TradeLogger, LiveTradeRecord, EquitySnapshot


class TestLiveTradeRecord:
    def test_create_record(self):
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z",
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            direction="long",
            side="buy",
            quantity=10,
            price=150.0,
            pnl=0.0,
            regime="TREND",
            equity_after=10000.0,
            metadata={},
        )
        assert record.symbol == "AAPL"
        assert record.strategy == "rsi_mean_reversion"
        assert record.pnl == 0.0

    def test_record_is_frozen(self):
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="test", direction="long", side="buy",
            quantity=10, price=100.0, pnl=0.0,
            regime="TREND", equity_after=10000.0, metadata={},
        )
        with pytest.raises(AttributeError):
            record.symbol = "MSFT"


class TestEquitySnapshot:
    def test_create_snapshot(self):
        snap = EquitySnapshot(
            timestamp="2026-01-01T00:00:00Z",
            equity=10000.0,
            cash=5000.0,
            regime="TREND",
            position_count=3,
            open_positions=["AAPL", "MSFT", "GOOGL"],
        )
        assert snap.equity == 10000.0
        assert snap.position_count == 3
        assert len(snap.open_positions) == 3

    def test_snapshot_is_frozen(self):
        snap = EquitySnapshot(
            timestamp="2026-01-01T00:00:00Z", equity=10000.0,
            cash=5000.0, regime="TREND", position_count=0,
            open_positions=[],
        )
        with pytest.raises(AttributeError):
            snap.equity = 20000.0


class TestTradeLogger:
    def test_log_trade_creates_file(self, tmp_path):
        trade_path = str(tmp_path / "trades.jsonl")
        equity_path = str(tmp_path / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="test", direction="long", side="buy",
            quantity=10, price=100.0, pnl=0.0,
            regime="TREND", equity_after=10000.0, metadata={},
        )
        logger.log_trade(record)
        assert (tmp_path / "trades.jsonl").exists()

    def test_log_trade_appends_jsonl(self, tmp_path):
        trade_path = str(tmp_path / "trades.jsonl")
        equity_path = str(tmp_path / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        for i in range(3):
            record = LiveTradeRecord(
                timestamp=f"2026-01-0{i+1}T00:00:00Z", symbol="AAPL",
                strategy="test", direction="long", side="buy",
                quantity=10, price=100.0 + i, pnl=float(i),
                regime="TREND", equity_after=10000.0, metadata={},
            )
            logger.log_trade(record)
        trades = logger.read_trades()
        assert len(trades) == 3
        assert trades[0].price == 100.0
        assert trades[2].price == 102.0

    def test_log_equity_snapshot(self, tmp_path):
        trade_path = str(tmp_path / "trades.jsonl")
        equity_path = str(tmp_path / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        snap = EquitySnapshot(
            timestamp="2026-01-01T00:00:00Z", equity=10000.0,
            cash=5000.0, regime="TREND", position_count=2,
            open_positions=["AAPL", "MSFT"],
        )
        logger.log_equity(snap)
        snapshots = logger.read_equity()
        assert len(snapshots) == 1
        assert snapshots[0].equity == 10000.0

    def test_read_trades_empty_file(self, tmp_path):
        trade_path = str(tmp_path / "trades.jsonl")
        equity_path = str(tmp_path / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        trades = logger.read_trades()
        assert trades == []

    def test_corrupt_line_skipped(self, tmp_path):
        trade_path = tmp_path / "trades.jsonl"
        equity_path = str(tmp_path / "equity.jsonl")
        # Write a valid line, then a corrupt line, then another valid line
        valid = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="test", direction="long", side="buy",
            quantity=10, price=100.0, pnl=0.0,
            regime="TREND", equity_after=10000.0, metadata={},
        )
        logger = TradeLogger(str(trade_path), equity_path)
        logger.log_trade(valid)
        # Append corrupt line
        with open(trade_path, "a") as f:
            f.write("THIS IS NOT JSON\n")
        logger.log_trade(valid)
        trades = logger.read_trades()
        assert len(trades) == 2  # Corrupt line skipped

    def test_log_trade_with_metadata(self, tmp_path):
        trade_path = str(tmp_path / "trades.jsonl")
        equity_path = str(tmp_path / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="test", direction="close", side="sell",
            quantity=10, price=155.0, pnl=50.0,
            regime="RANGING", equity_after=10050.0,
            metadata={"exit_reason": "force_close"},
        )
        logger.log_trade(record)
        trades = logger.read_trades()
        assert trades[0].metadata == {"exit_reason": "force_close"}

    def test_creates_parent_directories(self, tmp_path):
        trade_path = str(tmp_path / "subdir" / "nested" / "trades.jsonl")
        equity_path = str(tmp_path / "subdir" / "nested" / "equity.jsonl")
        logger = TradeLogger(trade_path, equity_path)
        record = LiveTradeRecord(
            timestamp="2026-01-01T00:00:00Z", symbol="AAPL",
            strategy="test", direction="long", side="buy",
            quantity=10, price=100.0, pnl=0.0,
            regime="TREND", equity_after=10000.0, metadata={},
        )
        logger.log_trade(record)
        assert len(logger.read_trades()) == 1
