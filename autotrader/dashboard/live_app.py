"""AutoTrader v2 - Live Trading Dashboard.

Dark-themed trading terminal with real-time monitoring.
Reads JSONL log files produced by the live trading loop.

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
from autotrader.dashboard.components.position_panel import render_position_panel
from autotrader.dashboard.components.trade_log import render_trade_log
from autotrader.dashboard.components.strategy_analysis import render_strategy_analysis

# -- Page config ---------------------------------------------------------------
st.set_page_config(
    page_title="AutoTrader v2",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- Sidebar controls ----------------------------------------------------------
st.sidebar.title("Settings")
auto_refresh = st.sidebar.toggle("Auto Refresh (30s)", value=True)
refresh_btn = st.sidebar.button("Refresh Now")

st.sidebar.divider()
trade_log_path = st.sidebar.text_input(
    "Trade Log", value="data/live_trades.jsonl",
)
equity_log_path = st.sidebar.text_input(
    "Equity Log", value="data/equity_snapshots.jsonl",
)

# Dashboard settings for components
_SETTINGS = {
    "rotation_day": 5,  # Saturday
    "weekly_loss_limit_pct": 0.05,
    "max_open_positions": 8,
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
data = data_loader.compute_metrics(trades_df, equity_df)

# ==============================================================================
# [A] Status Bar
# ==============================================================================
render_status_bar(data, _SETTINGS)

# ==============================================================================
# [B] KPI Cards
# ==============================================================================
render_kpi_cards(data)

st.divider()

# ==============================================================================
# [C] Main Area: Equity Chart (65%) | Position Panel (35%)
# ==============================================================================
col_chart, col_positions = st.columns([0.65, 0.35])

with col_chart:
    render_equity_section(equity_df, trades_df)

with col_positions:
    render_position_panel(data)

st.divider()

# ==============================================================================
# [D] Lower Tabs
# ==============================================================================
tab_trades, tab_analysis = st.tabs(["Trade Log", "Strategy Analysis"])

with tab_trades:
    render_trade_log(trades_df)

with tab_analysis:
    render_strategy_analysis(trades_df, equity_df)
