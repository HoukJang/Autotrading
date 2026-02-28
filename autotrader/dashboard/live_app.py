"""AutoTrader v3 - Nightly Batch Trading Dashboard.

Dark-themed trading terminal with 5 tabs covering the full nightly batch
architecture: Overview, Nightly Scan Results, Positions and Trades,
Strategy Analysis, and Risk Dashboard.

Reads JSONL log files for live trade and equity data, plus JSON files
produced by the nightly batch scanner.

Usage:
    streamlit run autotrader/dashboard/live_app.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from autotrader.dashboard import data_loader
from autotrader.dashboard.components.status_bar import render_status_bar
from autotrader.dashboard.components.kpi_cards import render_kpi_cards
from autotrader.dashboard.components.equity_chart import render_equity_section
from autotrader.dashboard.components.position_panel import (
    render_position_panel,
    render_positions_tab,
)
from autotrader.dashboard.components.trade_log import render_trade_log
from autotrader.dashboard.components.strategy_analysis import render_strategy_analysis
from autotrader.dashboard.components.scan_results import render_scan_results
from autotrader.dashboard.components.risk_dashboard import render_risk_dashboard

# -- Page config ---------------------------------------------------------------
st.set_page_config(
    page_title="AutoTrader v3",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- Sidebar controls ----------------------------------------------------------
st.sidebar.title("AutoTrader v3")
st.sidebar.caption("Nightly Batch Trading System")

auto_refresh = st.sidebar.toggle("Auto Refresh (30s)", value=True)
refresh_btn = st.sidebar.button("Refresh Now")

st.sidebar.divider()
st.sidebar.subheader("Data Paths")

trade_log_path = st.sidebar.text_input(
    "Trade Log",
    value="data/live_trades.jsonl",
)
equity_log_path = st.sidebar.text_input(
    "Equity Log",
    value="data/equity_snapshots.jsonl",
)
batch_results_path = st.sidebar.text_input(
    "Batch Results",
    value="data/batch_results.json",
)
batch_candidates_path = st.sidebar.text_input(
    "Batch Candidates",
    value="data/batch_candidates.json",
)

st.sidebar.divider()
st.sidebar.subheader("Settings")

max_drawdown_limit = st.sidebar.slider(
    "Max Drawdown Limit (%)",
    min_value=5,
    max_value=30,
    value=15,
    step=1,
) / 100.0

daily_loss_limit = st.sidebar.slider(
    "Daily Loss Limit (%)",
    min_value=1,
    max_value=10,
    value=2,
    step=1,
) / 100.0

# Dashboard settings shared across components
_SETTINGS = {
    "rotation_day": 5,              # Saturday (weekday index 5)
    "weekly_loss_limit_pct": 0.05,
    "max_open_positions": 8,
    "max_drawdown_limit_pct": max_drawdown_limit,
    "daily_loss_limit_pct": daily_loss_limit,
}

# -- Auto-refresh logic --------------------------------------------------------
_REFRESH_INTERVAL = 30

if auto_refresh:
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    elapsed = time.time() - st.session_state.last_refresh
    if elapsed > _REFRESH_INTERVAL:
        st.session_state.last_refresh = time.time()
        st.rerun()

if refresh_btn:
    st.session_state.last_refresh = time.time()
    st.rerun()

# -- Load data -----------------------------------------------------------------
trades_df = data_loader.load_trades(trade_log_path)
equity_df = data_loader.load_equity(equity_log_path)
dashboard_data = data_loader.compute_metrics(trades_df, equity_df)
batch_data = data_loader.load_batch_results(batch_results_path)
risk_metrics = data_loader.compute_risk_metrics(
    dashboard_data,
    max_drawdown_limit_pct=_SETTINGS["max_drawdown_limit_pct"],
    daily_loss_limit_pct=_SETTINGS["daily_loss_limit_pct"],
    max_positions=_SETTINGS["max_open_positions"],
)

# Pass last scan timestamp to status bar settings
_SETTINGS["last_scan_timestamp"] = getattr(batch_data, "scan_timestamp", "")

# ==============================================================================
# [A] Status Bar (always visible above tabs)
# ==============================================================================
render_status_bar(dashboard_data, _SETTINGS)

# ==============================================================================
# [B] Main Tabs
# ==============================================================================
tab_overview, tab_scan, tab_positions, tab_analysis, tab_risk = st.tabs([
    "Overview",
    "Nightly Scan",
    "Positions & Trades",
    "Strategy Analysis",
    "Risk Dashboard",
])

# ==============================================================================
# Tab 1: Overview
# ==============================================================================
with tab_overview:
    # KPI Cards Row
    render_kpi_cards(dashboard_data)

    st.divider()

    # Equity Curve (full width) | Positions Panel (sidebar)
    col_chart, col_positions = st.columns([0.65, 0.35])

    with col_chart:
        render_equity_section(equity_df, trades_df)

    with col_positions:
        render_position_panel(dashboard_data)

# ==============================================================================
# Tab 2: Nightly Scan Results
# ==============================================================================
with tab_scan:
    render_scan_results(batch_data)

# ==============================================================================
# Tab 3: Positions and Trades
# ==============================================================================
with tab_positions:
    render_positions_tab(dashboard_data)

# ==============================================================================
# Tab 4: Strategy Analysis
# ==============================================================================
with tab_analysis:
    render_strategy_analysis(trades_df, equity_df)

# ==============================================================================
# Tab 5: Risk Dashboard
# ==============================================================================
with tab_risk:
    render_risk_dashboard(risk_metrics)
