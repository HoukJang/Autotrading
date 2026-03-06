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
from streamlit_autorefresh import st_autorefresh

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
_REFRESH_INTERVAL_MS = 30_000  # 30 seconds

if auto_refresh:
    st_autorefresh(interval=_REFRESH_INTERVAL_MS, key="live_autorefresh")

if refresh_btn:
    st.rerun()

# -- Load data -----------------------------------------------------------------
trades_df = data_loader.load_trades(trade_log_path)
equity_df = data_loader.load_equity(equity_log_path)
batch_data = data_loader.load_batch_results(batch_results_path)
open_positions = data_loader.load_open_positions()
dashboard_data = data_loader.compute_metrics(
    trades_df, equity_df, batch_raw=getattr(batch_data, "raw", None),
)
risk_metrics = data_loader.compute_risk_metrics(
    dashboard_data,
    max_drawdown_limit_pct=_SETTINGS["max_drawdown_limit_pct"],
    daily_loss_limit_pct=_SETTINGS["daily_loss_limit_pct"],
    max_positions=_SETTINGS["max_open_positions"],
    open_positions=open_positions,
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

    # Market Context Widget (#11)
    _spy_adx = getattr(dashboard_data, "spy_adx", None)
    if _spy_adx is not None:
        from autotrader.dashboard.theme import COLORS

        st.markdown(
            f'<div style="margin:8px 0 4px 0;color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600">'
            f'Market Context</div>',
            unsafe_allow_html=True,
        )
        ctx_col1, ctx_col2, ctx_col3 = st.columns(3)

        with ctx_col1:
            adx_color = COLORS["warning"] if 20 <= _spy_adx <= 28 else COLORS["info"]
            st.markdown(
                f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:10px 14px">'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.78em">SPY ADX</div>'
                f'<div style="color:{adx_color};font-size:1.3em;font-weight:700">{_spy_adx:.1f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with ctx_col2:
            # Active strategies based on ADX
            if _spy_adx > 28:
                active = "BM + MR"
            elif _spy_adx < 20:
                active = "MR only"
            else:
                active = "None (Dead Zone)"
            active_color = COLORS["warning"] if "Dead Zone" in active else COLORS["profit"]
            st.markdown(
                f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:10px 14px">'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.78em">Active Strategies</div>'
                f'<div style="color:{active_color};font-size:1.1em;font-weight:700">{active}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with ctx_col3:
            # Regime duration: count consecutive days with current regime
            _regime_duration = 0
            if not equity_df.empty and "regime" in equity_df.columns:
                regimes = equity_df.sort_values("timestamp")["regime"].values
                if len(regimes) > 0:
                    current_r = regimes[-1]
                    for i in range(len(regimes) - 1, -1, -1):
                        if regimes[i] == current_r:
                            _regime_duration += 1
                        else:
                            break
            current_regime = getattr(dashboard_data, "current_regime", "UNKNOWN")
            st.markdown(
                f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:10px 14px">'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.78em">Regime Duration</div>'
                f'<div style="color:{COLORS["text_primary"]};font-size:1.1em;font-weight:700">'
                f'{current_regime} ({_regime_duration}d)</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # Equity Curve (full width) | Positions Panel (sidebar)
    col_chart, col_positions = st.columns([0.65, 0.35])

    with col_chart:
        render_equity_section(equity_df, trades_df)

    with col_positions:
        render_position_panel(dashboard_data)

    # Daily PnL Mini Chart (recent 20 days)
    if trades_df is not None and not trades_df.empty:
        from autotrader.dashboard.utils.chart_helpers import render_daily_pnl_chart

        close_trades = (
            trades_df[trades_df["side"] == "exit"]
            if "side" in trades_df.columns
            else trades_df
        )
        if not close_trades.empty:
            render_daily_pnl_chart(
                close_trades,
                height=180,
                chart_key="overview_daily_pnl",
                max_days=20,
            )

# ==============================================================================
# Tab 2: Nightly Scan Results
# ==============================================================================
with tab_scan:
    render_scan_results(batch_data, dashboard_data=dashboard_data)

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
    render_risk_dashboard(risk_metrics, open_positions=open_positions)
