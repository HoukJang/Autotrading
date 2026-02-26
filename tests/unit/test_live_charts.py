"""Tests for live trading dashboard chart functions."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from autotrader.dashboard.live_charts import (
    live_cumulative_pnl,
    live_drawdown_chart,
    live_equity_curve,
    live_pnl_by_strategy,
    live_pnl_by_symbol,
    live_position_summary_table,
    live_regime_pie,
    live_trade_timeline,
    live_win_rate_gauge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equity_df(n: int = 5) -> pd.DataFrame:
    """Create a minimal equity DataFrame."""
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="D"),
        "equity": [1000, 1050, 1020, 1080, 1100][:n],
        "cash": [200, 180, 190, 170, 160][:n],
        "regime": ["TREND", "TREND", "RANGING", "HIGH_VOLATILITY", "UNCERTAIN"][:n],
    })


def _trades_df(n: int = 4) -> pd.DataFrame:
    """Create a minimal trades DataFrame."""
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="D"),
        "pnl": [50.0, -20.0, 30.0, -10.0][:n],
        "symbol": ["AAPL", "MSFT", "AAPL", "GOOG"][:n],
        "strategy": ["RsiMeanReversion", "BbSqueeze", "AdxPullback", "RsiMeanReversion"][:n],
        "direction": ["long", "short", "long", "close"][:n],
    })


def _positions_df(n: int = 3) -> pd.DataFrame:
    """Create a minimal positions DataFrame."""
    return pd.DataFrame({
        "symbol": ["AAPL", "MSFT", "GOOG"][:n],
        "side": ["long", "short", "long"][:n],
        "quantity": [10, 5, 8][:n],
        "avg_entry_price": [150.0, 310.0, 140.0][:n],
        "unrealized_pnl": [120.50, -45.30, 67.80][:n],
    })


# ---------------------------------------------------------------------------
# Equity Curve
# ---------------------------------------------------------------------------

class TestLiveEquityCurve:
    def test_live_equity_curve_empty(self) -> None:
        fig = live_equity_curve(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_live_equity_curve_with_data(self) -> None:
        fig = live_equity_curve(_equity_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 400


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------

class TestLiveDrawdownChart:
    def test_live_drawdown_chart_empty(self) -> None:
        fig = live_drawdown_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_live_drawdown_chart_with_data(self) -> None:
        fig = live_drawdown_chart(_equity_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 250
        # Drawdown values should be <= 0
        y_vals = list(fig.data[0].y)
        assert all(v <= 0 for v in y_vals)


# ---------------------------------------------------------------------------
# PnL by Strategy
# ---------------------------------------------------------------------------

class TestLivePnlByStrategy:
    def test_live_pnl_by_strategy_empty(self) -> None:
        fig = live_pnl_by_strategy(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_live_pnl_by_strategy_with_data(self) -> None:
        fig = live_pnl_by_strategy(_trades_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 350


# ---------------------------------------------------------------------------
# Trade Timeline
# ---------------------------------------------------------------------------

class TestLiveTradeTimeline:
    def test_live_trade_timeline_with_data(self) -> None:
        fig = live_trade_timeline(_trades_df())
        assert isinstance(fig, go.Figure)
        # One trace per unique direction
        assert len(fig.data) >= 1
        assert fig.layout.height == 350


# ---------------------------------------------------------------------------
# Regime Pie
# ---------------------------------------------------------------------------

class TestLiveRegimePie:
    def test_live_regime_pie_with_data(self) -> None:
        fig = live_regime_pie(_equity_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 300


# ---------------------------------------------------------------------------
# Win Rate Gauge
# ---------------------------------------------------------------------------

class TestLiveWinRateGauge:
    def test_live_win_rate_gauge(self) -> None:
        fig = live_win_rate_gauge(0.65)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 250
        # The gauge indicator should show 65%
        assert fig.data[0].value == 65.0


# ---------------------------------------------------------------------------
# Cumulative PnL
# ---------------------------------------------------------------------------

class TestLiveCumulativePnl:
    def test_live_cumulative_pnl_with_data(self) -> None:
        fig = live_cumulative_pnl(_trades_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 350
        # Cumulative sum of [50, -20, 30, -10] = [50, 30, 60, 50]
        y_vals = list(fig.data[0].y)
        assert y_vals[-1] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# PnL by Symbol
# ---------------------------------------------------------------------------

class TestLivePnlBySymbol:
    def test_live_pnl_by_symbol_with_data(self) -> None:
        fig = live_pnl_by_symbol(_trades_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 350


# ---------------------------------------------------------------------------
# Position Summary Table
# ---------------------------------------------------------------------------

class TestLivePositionSummaryTable:
    def test_live_position_summary_table_with_data(self) -> None:
        fig = live_position_summary_table(_positions_df())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        assert fig.layout.height == 300
        # Table should have header values
        header_vals = fig.data[0].header.values
        assert len(header_vals) == 5

    def test_live_position_summary_table_empty(self) -> None:
        fig = live_position_summary_table(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1  # Table trace is still present
        assert fig.layout.height == 300
