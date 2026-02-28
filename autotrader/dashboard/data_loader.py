"""Dashboard data loader with caching and derived metrics.

Supports both live trade/equity JSONL files and nightly batch scan JSON files
produced by the batch scanner component of AutoTrader v3.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column definitions for empty DataFrames
# ---------------------------------------------------------------------------
_TRADE_COLUMNS = [
    "timestamp", "symbol", "strategy", "direction", "side",
    "quantity", "price", "pnl", "regime", "equity_after",
    "metadata", "exit_reason", "mfe", "mae", "bars_held",
]

_EQUITY_COLUMNS = [
    "timestamp", "equity", "cash", "regime", "position_count",
    "open_positions",
]

_CANDIDATE_COLUMNS = [
    "rank", "symbol", "strategy", "direction", "score",
    "entry_group", "sl_price", "tp_price", "atr",
    "gap_filter_status",
]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class DashboardData:
    """Aggregated dashboard state including raw data and derived metrics."""

    trades_df: pd.DataFrame
    equity_df: pd.DataFrame
    current_equity: float = 0.0
    current_cash: float = 0.0
    current_regime: str = "UNKNOWN"
    current_positions: list[str] = field(default_factory=list)
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    today_pnl: float = 0.0
    today_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    last_update: str = ""


@dataclass
class BatchScanData:
    """Results from the nightly batch scanner."""

    scan_timestamp: str = ""
    total_scanned: int = 0
    signals_generated: int = 0
    candidates_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    all_scores: list[float] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class RiskMetrics:
    """Current risk utilization metrics."""

    current_drawdown_pct: float = 0.0
    max_drawdown_limit_pct: float = 0.15
    today_loss_pct: float = 0.0
    daily_loss_limit_pct: float = 0.02
    open_positions_count: int = 0
    max_positions: int = 8
    long_count: int = 0
    short_count: int = 0
    entries_today: int = 0
    max_entries_today: int = 3
    reentry_blocks: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders (cached)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def load_trades(path: str = "data/live_trades.jsonl") -> pd.DataFrame:
    """Load the trades JSONL file into a DataFrame.

    Returns an empty DataFrame with the correct columns when the file is
    missing or contains no valid records. Corrupt lines are skipped with
    a warning.
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
                records.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping corrupt trade line %d: %s", line_num, line[:80],
                )

    if not records:
        return pd.DataFrame(columns=_TRADE_COLUMNS)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    return df


@st.cache_data(ttl=30)
def load_equity(path: str = "data/equity_snapshots.jsonl") -> pd.DataFrame:
    """Load equity snapshots JSONL into a DataFrame.

    Returns an empty DataFrame with the correct columns when the file is
    missing or contains no valid records. Corrupt lines are skipped with
    a warning.
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
                records.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping corrupt equity line %d: %s", line_num, line[:80],
                )

    if not records:
        return pd.DataFrame(columns=_EQUITY_COLUMNS)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    return df


@st.cache_data(ttl=30)
def load_batch_results(path: str = "data/batch_results.json") -> BatchScanData:
    """Load the latest nightly batch scan results JSON.

    Expected JSON structure:
    {
        "scan_timestamp": "2026-02-27T22:00:00Z",
        "total_scanned": 503,
        "signals_generated": 25,
        "candidates": [
            {
                "rank": 1,
                "symbol": "AAPL",
                "strategy": "rsi_mean_reversion",
                "direction": "long",
                "score": 0.87,
                "entry_group": "MOO",
                "sl_price": 180.50,
                "tp_price": 195.00,
                "atr": 3.20,
                "gap_filter_status": "passed"
            }
        ],
        "all_scores": [0.12, 0.34, ...]
    }

    Returns an empty BatchScanData when the file is missing or malformed.
    """
    file_path = Path(path)
    if not file_path.exists():
        return BatchScanData()

    try:
        with open(file_path, encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Failed to load batch results from %s: %s", path, exc)
        return BatchScanData()

    candidates_raw = raw.get("candidates", [])
    if candidates_raw:
        candidates_df = pd.DataFrame(candidates_raw)
        # Ensure all expected columns exist
        for col in _CANDIDATE_COLUMNS:
            if col not in candidates_df.columns:
                candidates_df[col] = None
    else:
        candidates_df = pd.DataFrame(columns=_CANDIDATE_COLUMNS)

    return BatchScanData(
        scan_timestamp=str(raw.get("scan_timestamp", "")),
        total_scanned=int(raw.get("total_scanned", 0)),
        signals_generated=int(raw.get("signals_generated", 0)),
        candidates_df=candidates_df,
        all_scores=list(raw.get("all_scores", [])),
        raw=raw,
    )


@st.cache_data(ttl=30)
def load_batch_candidates(path: str = "data/batch_candidates.json") -> pd.DataFrame:
    """Load filtered candidates after gap filter from JSON.

    This file is written after the gap check is complete (post-open).
    Expected JSON: array of candidate objects with gap_filter_status updated.

    Returns an empty DataFrame when the file is missing or malformed.
    """
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame(columns=_CANDIDATE_COLUMNS)

    try:
        with open(file_path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Failed to load batch candidates from %s: %s", path, exc)
        return pd.DataFrame(columns=_CANDIDATE_COLUMNS)

    if not raw:
        return pd.DataFrame(columns=_CANDIDATE_COLUMNS)

    df = pd.DataFrame(raw) if isinstance(raw, list) else pd.DataFrame(raw.get("candidates", []))
    for col in _CANDIDATE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
def compute_metrics(
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
) -> DashboardData:
    """Derive all dashboard metrics from raw trade and equity data.

    Computes current account state, win rate, max drawdown, profit factor,
    today's PnL, and the timestamp of the most recent data point.
    """
    # -- Current state from latest equity snapshot -------------------------
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
        positions_raw = latest.get("open_positions", [])
        current_positions = (
            positions_raw if isinstance(positions_raw, list) else []
        )

    # -- Last update timestamp ---------------------------------------------
    last_update = _resolve_last_update(trades_df, equity_df)

    # -- Empty-trade fast path ---------------------------------------------
    total_trades = len(trades_df)
    if total_trades == 0:
        return DashboardData(
            trades_df=trades_df,
            equity_df=equity_df,
            current_equity=current_equity,
            current_cash=current_cash,
            current_regime=current_regime,
            current_positions=current_positions,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            today_pnl=0.0,
            today_pnl_pct=0.0,
            max_drawdown=_compute_max_drawdown(equity_df),
            profit_factor=0.0,
            last_update=last_update,
        )

    # -- Trade statistics --------------------------------------------------
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

    # Today's PnL (close trades whose timestamp falls on today)
    today_pnl = _compute_today_pnl(trades_df)
    today_pnl_pct = (today_pnl / current_equity) if current_equity > 0 else 0.0

    # Max drawdown from equity curve
    max_drawdown = _compute_max_drawdown(equity_df)

    return DashboardData(
        trades_df=trades_df,
        equity_df=equity_df,
        current_equity=current_equity,
        current_cash=current_cash,
        current_regime=current_regime,
        current_positions=current_positions,
        total_trades=total_trades,
        winning_trades=winning_trades,
        total_pnl=total_pnl,
        today_pnl=today_pnl,
        today_pnl_pct=today_pnl_pct,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        last_update=last_update,
    )


def compute_risk_metrics(
    data: DashboardData,
    max_drawdown_limit_pct: float = 0.15,
    daily_loss_limit_pct: float = 0.02,
    max_positions: int = 8,
    max_entries_today: int = 3,
) -> RiskMetrics:
    """Calculate current risk utilization metrics.

    Computes drawdown usage, daily loss usage, position counts by direction,
    and today's entry count vs limits.

    Parameters
    ----------
    data:
        DashboardData with trades and equity information.
    max_drawdown_limit_pct:
        Maximum allowed drawdown as a fraction (default 0.15 = 15%).
    daily_loss_limit_pct:
        Maximum allowed daily loss as a fraction (default 0.02 = 2%).
    max_positions:
        Maximum number of simultaneous open positions (default 8).
    max_entries_today:
        Maximum new entries per day (default 3).
    """
    # -- Drawdown usage ----------------------------------------------------
    current_drawdown_pct = data.max_drawdown

    # -- Daily loss usage --------------------------------------------------
    today_loss_pct = max(0.0, -data.today_pnl_pct)

    # -- Position direction breakdown --------------------------------------
    long_count = 0
    short_count = 0
    open_positions_count = len(data.current_positions)

    if not data.trades_df.empty and "direction" in data.trades_df.columns:
        # Find the most recent trade entry direction per open symbol
        for symbol in data.current_positions:
            sym_trades = data.trades_df[data.trades_df["symbol"] == symbol]
            if sym_trades.empty:
                continue
            if "side" in sym_trades.columns:
                entries = sym_trades[sym_trades["side"] == "entry"]
            else:
                entries = sym_trades

            if not entries.empty:
                last_entry = entries.iloc[-1]
                direction = str(last_entry.get("direction", "")).lower() if hasattr(last_entry, "get") else str(last_entry["direction"]).lower()
                if direction == "long":
                    long_count += 1
                elif direction == "short":
                    short_count += 1

    # -- Today's entries count ---------------------------------------------
    entries_today = 0
    reentry_blocks: list[str] = []

    if not data.trades_df.empty and "timestamp" in data.trades_df.columns:
        today = date.today()
        today_mask = data.trades_df["timestamp"].dt.date == today

        if "side" in data.trades_df.columns:
            today_entries = data.trades_df[today_mask & (data.trades_df["side"] == "entry")]
        else:
            today_entries = data.trades_df[today_mask]

        entries_today = len(today_entries)

        # Symbols that had entries and exits today (re-entry blocks)
        if "symbol" in today_entries.columns and "exit_reason" in data.trades_df.columns:
            today_exits = data.trades_df[today_mask & data.trades_df["exit_reason"].notna()]
            if not today_exits.empty and "symbol" in today_exits.columns:
                reentry_blocks = today_exits["symbol"].unique().tolist()

    return RiskMetrics(
        current_drawdown_pct=current_drawdown_pct,
        max_drawdown_limit_pct=max_drawdown_limit_pct,
        today_loss_pct=today_loss_pct,
        daily_loss_limit_pct=daily_loss_limit_pct,
        open_positions_count=open_positions_count,
        max_positions=max_positions,
        long_count=long_count,
        short_count=short_count,
        entries_today=entries_today,
        max_entries_today=max_entries_today,
        reentry_blocks=reentry_blocks,
    )


# ---------------------------------------------------------------------------
# Per-group metrics
# ---------------------------------------------------------------------------
def per_strategy_metrics(trades_df: pd.DataFrame) -> dict[str, dict]:
    """Compute metrics grouped by strategy.

    Returns a dict mapping strategy name to a dict with:
    trade_count, win_rate, total_pnl, avg_pnl, avg_bars_held,
    max_consecutive_losses.
    """
    if trades_df.empty:
        return {}

    result: dict[str, dict] = {}
    for strategy, group in trades_df.groupby("strategy"):
        pnls = group["pnl"]
        wins = int((pnls > 0).sum())
        count = len(group)

        # Average bars held (graceful if column missing)
        avg_bars_held = 0.0
        if "bars_held" in group.columns:
            bars = pd.to_numeric(group["bars_held"], errors="coerce")
            avg_bars_held = float(bars.mean()) if not bars.isna().all() else 0.0

        # Max consecutive losses
        max_consec_losses = _max_consecutive_losses(pnls)

        result[str(strategy)] = {
            "trade_count": count,
            "win_rate": wins / count if count > 0 else 0.0,
            "total_pnl": float(pnls.sum()),
            "avg_pnl": float(pnls.mean()),
            "avg_bars_held": avg_bars_held,
            "max_consecutive_losses": max_consec_losses,
        }
    return result


def per_regime_metrics(trades_df: pd.DataFrame) -> dict[str, dict]:
    """Compute metrics grouped by regime.

    Returns a dict mapping regime name to a dict with:
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

    Returns a dict mapping symbol name to a dict with:
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


def daily_pnl(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate trade PnL by calendar date.

    Returns a DataFrame with columns ``[date, pnl]`` sorted by date.
    Returns an empty DataFrame with those columns when no trades exist.
    """
    if trades_df.empty or "timestamp" not in trades_df.columns:
        return pd.DataFrame(columns=["date", "pnl"])

    df = trades_df.copy()
    df["date"] = df["timestamp"].dt.date
    grouped = df.groupby("date")["pnl"].sum().reset_index()
    grouped.columns = ["date", "pnl"]
    return grouped.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
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


def _compute_today_pnl(trades_df: pd.DataFrame) -> float:
    """Sum PnL for trades whose timestamp falls on today's date."""
    if trades_df.empty or "timestamp" not in trades_df.columns:
        return 0.0

    today = date.today()
    today_mask = trades_df["timestamp"].dt.date == today
    return float(trades_df.loc[today_mask, "pnl"].sum())


def _resolve_last_update(
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
) -> str:
    """Determine the latest timestamp across trades and equity data.

    Returns an ISO-format string or an empty string when no data exists.
    """
    candidates = []

    if not trades_df.empty and "timestamp" in trades_df.columns:
        candidates.append(trades_df["timestamp"].max())

    if not equity_df.empty and "timestamp" in equity_df.columns:
        candidates.append(equity_df["timestamp"].max())

    if not candidates:
        return ""

    latest = max(candidates)
    return str(latest)


def _max_consecutive_losses(pnl_series: pd.Series) -> int:
    """Count the longest streak of consecutive losing trades."""
    max_streak = 0
    current_streak = 0
    for pnl in pnl_series:
        if pnl < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return max_streak
