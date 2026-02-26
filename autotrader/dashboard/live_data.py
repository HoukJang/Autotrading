"""Live trading data loader for the Streamlit dashboard.

Reads JSONL log files written by TradeLogger and provides pandas
DataFrames with computed metrics for live dashboard visualization.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Column definitions for empty DataFrames
_TRADE_COLUMNS = [
    "timestamp", "symbol", "strategy", "direction", "side",
    "quantity", "price", "pnl", "regime", "equity_after",
]

_EQUITY_COLUMNS = [
    "timestamp", "equity", "cash", "regime", "position_count", "open_positions",
]


@dataclass
class LiveDashboardData:
    """Container for live dashboard data."""

    trades_df: pd.DataFrame
    equity_df: pd.DataFrame
    current_equity: float
    current_cash: float
    current_regime: str
    current_positions: list[str]
    total_trades: int
    winning_trades: int
    total_pnl: float
    max_drawdown: float
    profit_factor: float


def load_trades(path: str = "data/live_trades.jsonl") -> pd.DataFrame:
    """Load trades JSONL into DataFrame.

    Returns an empty DataFrame with correct columns if the file
    does not exist or contains no valid records. Corrupt lines are
    skipped with a warning.
    """
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame(columns=_TRADE_COLUMNS)

    records: list[dict] = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(data)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping corrupt trade line %d: %s", line_num, line[:80],
                )

    if not records:
        return pd.DataFrame(columns=_TRADE_COLUMNS)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_equity(path: str = "data/equity_snapshots.jsonl") -> pd.DataFrame:
    """Load equity snapshots into DataFrame.

    Returns an empty DataFrame with correct columns if the file
    does not exist or contains no valid records. Corrupt lines are
    skipped with a warning.
    """
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame(columns=_EQUITY_COLUMNS)

    records: list[dict] = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(data)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping corrupt equity line %d: %s", line_num, line[:80],
                )

    if not records:
        return pd.DataFrame(columns=_EQUITY_COLUMNS)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def compute_metrics(
    trades_df: pd.DataFrame, equity_df: pd.DataFrame,
) -> LiveDashboardData:
    """Compute dashboard metrics from trade and equity data.

    Derives current account state from the latest equity snapshot,
    calculates win rate, max drawdown, and profit factor from
    historical trade and equity data.
    """
    # Current state from latest equity snapshot
    if equity_df.empty:
        current_equity = 0.0
        current_cash = 0.0
        current_regime = "UNKNOWN"
        current_positions: list[str] = []
    else:
        latest = equity_df.iloc[-1]
        current_equity = float(latest["equity"])
        current_cash = float(latest["cash"])
        current_regime = str(latest["regime"])
        positions_raw = latest["open_positions"]
        current_positions = (
            positions_raw if isinstance(positions_raw, list) else []
        )

    # Trade statistics
    total_trades = len(trades_df)
    if total_trades == 0:
        return LiveDashboardData(
            trades_df=trades_df,
            equity_df=equity_df,
            current_equity=current_equity,
            current_cash=current_cash,
            current_regime=current_regime,
            current_positions=current_positions,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            max_drawdown=0.0,
            profit_factor=0.0,
        )

    pnl_series = trades_df["pnl"]
    winning_mask = pnl_series > 0
    losing_mask = pnl_series < 0
    winning_trades = int(winning_mask.sum())
    total_pnl = float(pnl_series.sum())

    # Profit factor
    winning_sum = float(pnl_series[winning_mask].sum())
    losing_sum = float(pnl_series[losing_mask].sum())

    if winning_sum == 0.0:
        profit_factor = 0.0
    elif losing_sum == 0.0:
        profit_factor = float("inf")
    else:
        profit_factor = winning_sum / abs(losing_sum)

    # Max drawdown from equity curve (peak-to-trough percentage)
    max_drawdown = _compute_max_drawdown(equity_df)

    return LiveDashboardData(
        trades_df=trades_df,
        equity_df=equity_df,
        current_equity=current_equity,
        current_cash=current_cash,
        current_regime=current_regime,
        current_positions=current_positions,
        total_trades=total_trades,
        winning_trades=winning_trades,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
    )


def _compute_max_drawdown(equity_df: pd.DataFrame) -> float:
    """Compute max drawdown as a percentage from the equity curve.

    Tracks the running peak and finds the largest percentage drop
    from any peak to a subsequent trough. Returns 0.0 if no equity
    data is available or equity never declines.
    """
    if equity_df.empty or "equity" not in equity_df.columns:
        return 0.0

    equity = equity_df["equity"]
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    max_dd = float(drawdown.min())
    return abs(max_dd)


def per_strategy_metrics(trades_df: pd.DataFrame) -> dict[str, dict]:
    """Compute metrics grouped by strategy.

    Returns a dict mapping strategy name to a dict containing:
    trade_count, win_rate, total_pnl, avg_pnl.
    """
    if trades_df.empty:
        return {}

    result: dict[str, dict] = {}
    for strategy, group in trades_df.groupby("strategy"):
        pnls = group["pnl"]
        wins = int((pnls > 0).sum())
        count = len(group)
        result[str(strategy)] = {
            "trade_count": count,
            "win_rate": wins / count if count > 0 else 0.0,
            "total_pnl": float(pnls.sum()),
            "avg_pnl": float(pnls.mean()),
        }
    return result


def per_regime_metrics(trades_df: pd.DataFrame) -> dict[str, dict]:
    """Compute metrics grouped by regime.

    Returns a dict mapping regime name to a dict containing:
    trade_count, win_rate, total_pnl.
    """
    if trades_df.empty:
        return {}

    result: dict[str, dict] = {}
    for regime, group in trades_df.groupby("regime"):
        pnls = group["pnl"]
        wins = int((pnls > 0).sum())
        count = len(group)
        result[str(regime)] = {
            "trade_count": count,
            "win_rate": wins / count if count > 0 else 0.0,
            "total_pnl": float(pnls.sum()),
        }
    return result


def per_symbol_metrics(trades_df: pd.DataFrame) -> dict[str, dict]:
    """Compute metrics grouped by symbol.

    Returns a dict mapping symbol name to a dict containing:
    trade_count, win_rate, total_pnl, avg_pnl.
    """
    if trades_df.empty:
        return {}

    result: dict[str, dict] = {}
    for symbol, group in trades_df.groupby("symbol"):
        pnls = group["pnl"]
        wins = int((pnls > 0).sum())
        count = len(group)
        result[str(symbol)] = {
            "trade_count": count,
            "win_rate": wins / count if count > 0 else 0.0,
            "total_pnl": float(pnls.sum()),
            "avg_pnl": float(pnls.mean()),
        }
    return result
