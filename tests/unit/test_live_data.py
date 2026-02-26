"""Tests for live trading data loader module."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from autotrader.dashboard.live_data import (
    LiveDashboardData,
    compute_metrics,
    load_equity,
    load_trades,
    per_regime_metrics,
    per_strategy_metrics,
    per_symbol_metrics,
)


# ---------------------------------------------------------------------------
# Helper: write JSONL lines to a file
# ---------------------------------------------------------------------------

def _write_jsonl(path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _make_trade(
    *,
    timestamp: str = "2026-01-15T10:00:00Z",
    symbol: str = "AAPL",
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    side: str = "sell",
    quantity: float = 10,
    price: float = 150.0,
    pnl: float = 25.0,
    regime: str = "TREND",
    equity_after: float = 10025.0,
    metadata: dict | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "strategy": strategy,
        "direction": direction,
        "side": side,
        "quantity": quantity,
        "price": price,
        "pnl": pnl,
        "regime": regime,
        "equity_after": equity_after,
        "metadata": metadata or {},
    }


def _make_equity(
    *,
    timestamp: str = "2026-01-15T10:00:00Z",
    equity: float = 10000.0,
    cash: float = 5000.0,
    regime: str = "TREND",
    position_count: int = 2,
    open_positions: list[str] | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "equity": equity,
        "cash": cash,
        "regime": regime,
        "position_count": position_count,
        "open_positions": open_positions or ["AAPL", "MSFT"],
    }


# ===========================================================================
# load_trades tests
# ===========================================================================

class TestLoadTrades:

    def test_load_trades_empty_file(self, tmp_path):
        """An empty JSONL file returns an empty DataFrame with correct columns."""
        trade_file = tmp_path / "trades.jsonl"
        trade_file.write_text("", encoding="utf-8")

        df = load_trades(str(trade_file))

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "timestamp" in df.columns
        assert "symbol" in df.columns
        assert "pnl" in df.columns

    def test_load_trades_with_data(self, tmp_path):
        """Valid JSONL lines are parsed into a DataFrame with correct types."""
        trade_file = tmp_path / "trades.jsonl"
        records = [
            _make_trade(timestamp="2026-01-15T10:00:00Z", symbol="AAPL", pnl=25.0),
            _make_trade(timestamp="2026-01-16T11:00:00Z", symbol="MSFT", pnl=-10.0),
            _make_trade(timestamp="2026-01-17T09:30:00Z", symbol="GOOGL", pnl=50.0),
        ]
        _write_jsonl(trade_file, records)

        df = load_trades(str(trade_file))

        assert len(df) == 3
        assert df["symbol"].tolist() == ["AAPL", "MSFT", "GOOGL"]
        assert df["pnl"].tolist() == [25.0, -10.0, 50.0]
        # Timestamp should be parsed as datetime
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_load_trades_missing_file(self, tmp_path):
        """A non-existent file returns an empty DataFrame, no exception."""
        df = load_trades(str(tmp_path / "nonexistent.jsonl"))

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "timestamp" in df.columns

    def test_load_trades_corrupt_lines_skipped(self, tmp_path):
        """Corrupt JSONL lines are skipped; valid lines are kept."""
        trade_file = tmp_path / "trades.jsonl"
        valid_1 = _make_trade(symbol="AAPL", pnl=10.0)
        valid_2 = _make_trade(symbol="MSFT", pnl=20.0)

        with open(trade_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(valid_1) + "\n")
            f.write("THIS IS NOT JSON\n")
            f.write("{broken json\n")
            f.write(json.dumps(valid_2) + "\n")

        df = load_trades(str(trade_file))

        assert len(df) == 2
        assert df["symbol"].tolist() == ["AAPL", "MSFT"]


# ===========================================================================
# load_equity tests
# ===========================================================================

class TestLoadEquity:

    def test_load_equity_with_data(self, tmp_path):
        """Valid equity JSONL lines are parsed correctly."""
        eq_file = tmp_path / "equity.jsonl"
        records = [
            _make_equity(
                timestamp="2026-01-15T10:00:00Z",
                equity=10000.0, cash=5000.0,
                open_positions=["AAPL"],
            ),
            _make_equity(
                timestamp="2026-01-16T10:00:00Z",
                equity=10200.0, cash=4800.0,
                open_positions=["AAPL", "MSFT"],
            ),
        ]
        _write_jsonl(eq_file, records)

        df = load_equity(str(eq_file))

        assert len(df) == 2
        assert df["equity"].tolist() == [10000.0, 10200.0]
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_load_equity_missing_file(self, tmp_path):
        """A non-existent equity file returns an empty DataFrame."""
        df = load_equity(str(tmp_path / "nonexistent.jsonl"))

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "equity" in df.columns


# ===========================================================================
# compute_metrics tests
# ===========================================================================

class TestComputeMetrics:

    def test_compute_metrics_basic(self, tmp_path):
        """Basic metric computation with a mix of winning and losing trades."""
        trade_file = tmp_path / "trades.jsonl"
        eq_file = tmp_path / "equity.jsonl"

        trades = [
            _make_trade(pnl=50.0, regime="TREND", strategy="rsi_mean_reversion"),
            _make_trade(pnl=-20.0, regime="TREND", strategy="rsi_mean_reversion"),
            _make_trade(pnl=30.0, regime="RANGING", strategy="bb_squeeze"),
            _make_trade(pnl=-10.0, regime="RANGING", strategy="bb_squeeze"),
        ]
        _write_jsonl(trade_file, trades)

        equities = [
            _make_equity(
                timestamp="2026-01-15T10:00:00Z",
                equity=10000.0, cash=5000.0, regime="TREND",
                open_positions=["AAPL", "MSFT"],
            ),
            _make_equity(
                timestamp="2026-01-20T10:00:00Z",
                equity=10050.0, cash=5050.0, regime="RANGING",
                open_positions=["GOOGL"],
            ),
        ]
        _write_jsonl(eq_file, equities)

        trades_df = load_trades(str(trade_file))
        equity_df = load_equity(str(eq_file))
        result = compute_metrics(trades_df, equity_df)

        assert isinstance(result, LiveDashboardData)
        assert result.total_trades == 4
        assert result.winning_trades == 2
        assert result.total_pnl == pytest.approx(50.0)
        # Current state from latest equity snapshot
        assert result.current_equity == pytest.approx(10050.0)
        assert result.current_cash == pytest.approx(5050.0)
        assert result.current_regime == "RANGING"
        assert result.current_positions == ["GOOGL"]
        # Profit factor: 80.0 / 30.0
        assert result.profit_factor == pytest.approx(80.0 / 30.0)

    def test_compute_metrics_empty(self):
        """Empty DataFrames produce zero metrics without errors."""
        trades_df = pd.DataFrame(columns=[
            "timestamp", "symbol", "strategy", "direction", "side",
            "quantity", "price", "pnl", "regime", "equity_after",
        ])
        equity_df = pd.DataFrame(columns=[
            "timestamp", "equity", "cash", "regime", "position_count",
            "open_positions",
        ])

        result = compute_metrics(trades_df, equity_df)

        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.total_pnl == 0.0
        assert result.max_drawdown == 0.0
        assert result.profit_factor == 0.0
        assert result.current_equity == 0.0
        assert result.current_regime == "UNKNOWN"
        assert result.current_positions == []

    def test_max_drawdown_calculation(self, tmp_path):
        """Max drawdown tracks peak-to-trough percentage correctly."""
        eq_file = tmp_path / "equity.jsonl"
        # Equity: 10000 -> 11000 (peak) -> 9350 (trough, -15%) -> 10500
        equities = [
            _make_equity(timestamp="2026-01-01T10:00:00Z", equity=10000.0),
            _make_equity(timestamp="2026-01-02T10:00:00Z", equity=11000.0),
            _make_equity(timestamp="2026-01-03T10:00:00Z", equity=9350.0),
            _make_equity(timestamp="2026-01-04T10:00:00Z", equity=10500.0),
        ]
        _write_jsonl(eq_file, equities)

        # Need at least one trade for compute_metrics to compute drawdown
        trade_file = tmp_path / "trades.jsonl"
        _write_jsonl(trade_file, [_make_trade(pnl=10.0)])

        trades_df = load_trades(str(trade_file))
        equity_df = load_equity(str(eq_file))
        result = compute_metrics(trades_df, equity_df)

        # Drawdown from 11000 -> 9350 = (11000 - 9350) / 11000 = 15.0%
        assert result.max_drawdown == pytest.approx(1650.0 / 11000.0, rel=1e-6)

    def test_profit_factor_no_losses(self, tmp_path):
        """Profit factor is inf when there are no losing trades."""
        trade_file = tmp_path / "trades.jsonl"
        eq_file = tmp_path / "equity.jsonl"

        trades = [
            _make_trade(pnl=50.0),
            _make_trade(pnl=30.0),
            _make_trade(pnl=20.0),
        ]
        _write_jsonl(trade_file, trades)
        _write_jsonl(eq_file, [_make_equity()])

        trades_df = load_trades(str(trade_file))
        equity_df = load_equity(str(eq_file))
        result = compute_metrics(trades_df, equity_df)

        assert math.isinf(result.profit_factor)
        assert result.profit_factor > 0


# ===========================================================================
# Per-group metric tests
# ===========================================================================

class TestPerStrategyMetrics:

    def test_per_strategy_metrics(self, tmp_path):
        """Metrics are correctly grouped by strategy name."""
        trade_file = tmp_path / "trades.jsonl"
        trades = [
            _make_trade(strategy="rsi_mean_reversion", pnl=50.0),
            _make_trade(strategy="rsi_mean_reversion", pnl=-20.0),
            _make_trade(strategy="bb_squeeze", pnl=30.0),
            _make_trade(strategy="bb_squeeze", pnl=10.0),
            _make_trade(strategy="bb_squeeze", pnl=-5.0),
        ]
        _write_jsonl(trade_file, trades)
        df = load_trades(str(trade_file))

        result = per_strategy_metrics(df)

        assert "rsi_mean_reversion" in result
        assert "bb_squeeze" in result

        rsi = result["rsi_mean_reversion"]
        assert rsi["trade_count"] == 2
        assert rsi["win_rate"] == pytest.approx(0.5)
        assert rsi["total_pnl"] == pytest.approx(30.0)
        assert rsi["avg_pnl"] == pytest.approx(15.0)

        bb = result["bb_squeeze"]
        assert bb["trade_count"] == 3
        assert bb["win_rate"] == pytest.approx(2.0 / 3.0)
        assert bb["total_pnl"] == pytest.approx(35.0)
        assert bb["avg_pnl"] == pytest.approx(35.0 / 3.0)


class TestPerRegimeMetrics:

    def test_per_regime_metrics(self, tmp_path):
        """Metrics are correctly grouped by regime."""
        trade_file = tmp_path / "trades.jsonl"
        trades = [
            _make_trade(regime="TREND", pnl=40.0),
            _make_trade(regime="TREND", pnl=-15.0),
            _make_trade(regime="RANGING", pnl=20.0),
        ]
        _write_jsonl(trade_file, trades)
        df = load_trades(str(trade_file))

        result = per_regime_metrics(df)

        assert "TREND" in result
        assert "RANGING" in result

        trend = result["TREND"]
        assert trend["trade_count"] == 2
        assert trend["win_rate"] == pytest.approx(0.5)
        assert trend["total_pnl"] == pytest.approx(25.0)

        ranging = result["RANGING"]
        assert ranging["trade_count"] == 1
        assert ranging["win_rate"] == pytest.approx(1.0)
        assert ranging["total_pnl"] == pytest.approx(20.0)


class TestPerSymbolMetrics:

    def test_per_symbol_metrics(self, tmp_path):
        """Metrics are correctly grouped by symbol."""
        trade_file = tmp_path / "trades.jsonl"
        trades = [
            _make_trade(symbol="AAPL", pnl=30.0),
            _make_trade(symbol="AAPL", pnl=-10.0),
            _make_trade(symbol="AAPL", pnl=20.0),
            _make_trade(symbol="MSFT", pnl=-5.0),
            _make_trade(symbol="MSFT", pnl=15.0),
        ]
        _write_jsonl(trade_file, trades)
        df = load_trades(str(trade_file))

        result = per_symbol_metrics(df)

        assert "AAPL" in result
        assert "MSFT" in result

        aapl = result["AAPL"]
        assert aapl["trade_count"] == 3
        assert aapl["win_rate"] == pytest.approx(2.0 / 3.0)
        assert aapl["total_pnl"] == pytest.approx(40.0)
        assert aapl["avg_pnl"] == pytest.approx(40.0 / 3.0)

        msft = result["MSFT"]
        assert msft["trade_count"] == 2
        assert msft["win_rate"] == pytest.approx(0.5)
        assert msft["total_pnl"] == pytest.approx(10.0)
        assert msft["avg_pnl"] == pytest.approx(5.0)
