"""Streamlit live trading dashboard for AutoTrader v2.

Displays real-time equity curves, trade history, per-strategy/regime
analysis, and open positions by reading JSONL log files produced by
the live trading loop.

Usage:
    streamlit run autotrader/dashboard/live_app.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root on path so autotrader package is importable
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd

from autotrader.dashboard import live_data, live_charts

# ── Page configuration ───────────────────────────────────────────────
st.set_page_config(
    page_title="AutoTrader v2 - Live Dashboard",
    layout="wide",
    page_icon="chart_with_upwards_trend",
)

# ── Sidebar controls ─────────────────────────────────────────────────
st.sidebar.title("Controls")
auto_refresh = st.sidebar.toggle("Auto Refresh (30s)", value=True)
refresh_btn = st.sidebar.button("Refresh Now")

st.sidebar.divider()
st.sidebar.subheader("Data Sources")
trade_log_path = st.sidebar.text_input(
    "Trade Log", value="data/live_trades.jsonl",
)
equity_log_path = st.sidebar.text_input(
    "Equity Log", value="data/equity_snapshots.jsonl",
)

# ── Auto-refresh logic ───────────────────────────────────────────────
_REFRESH_INTERVAL = 30  # seconds

if auto_refresh:
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    elapsed = time.time() - st.session_state.last_refresh
    remaining = max(0, int(_REFRESH_INTERVAL - elapsed))
    if elapsed > _REFRESH_INTERVAL:
        st.session_state.last_refresh = time.time()
        st.rerun()
    st.sidebar.caption(f"Next refresh in {remaining}s")

if refresh_btn:
    st.session_state.last_refresh = time.time()
    st.rerun()

# ── Title and timestamp ──────────────────────────────────────────────
st.title("AutoTrader v2 - Live Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ── Load data ─────────────────────────────────────────────────────────
trades_df = live_data.load_trades(trade_log_path)
equity_df = live_data.load_equity(equity_log_path)
data = live_data.compute_metrics(trades_df, equity_df)

# ── Top metrics row ──────────────────────────────────────────────────
win_rate = (
    data.winning_trades / data.total_trades if data.total_trades > 0 else 0.0
)
pf_display = (
    f"{data.profit_factor:.2f}"
    if data.profit_factor != float("inf")
    else "inf"
)

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Equity", f"${data.current_equity:,.2f}")
col2.metric("Total PnL", f"${data.total_pnl:+,.2f}")
col3.metric("Win Rate", f"{win_rate:.1%}")
col4.metric("Profit Factor", pf_display)
col5.metric("Max Drawdown", f"{data.max_drawdown:.2%}")
col6.metric("Regime", data.current_regime)
col7.metric("Positions", f"{len(data.current_positions)}")

# ── Tabs ──────────────────────────────────────────────────────────────
tab_overview, tab_trades, tab_analysis, tab_positions = st.tabs(
    ["Overview", "Trade History", "Analysis", "Positions"],
)

# ════════════════════════════════════════════════════════════════════════
# Tab 1: Overview
# ════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.plotly_chart(live_charts.live_equity_curve(equity_df), key="eq_curve")
    st.plotly_chart(live_charts.live_drawdown_chart(equity_df), key="dd_chart")

    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(live_charts.live_win_rate_gauge(win_rate), key="wr_gauge")
    with col_right:
        st.plotly_chart(live_charts.live_regime_pie(equity_df), key="regime_pie")

# ════════════════════════════════════════════════════════════════════════
# Tab 2: Trade History
# ════════════════════════════════════════════════════════════════════════
with tab_trades:
    if trades_df.empty:
        st.info("No trades recorded yet. Waiting for signals...")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            all_symbols = sorted(trades_df["symbol"].unique().tolist())
            sel_symbols = st.multiselect(
                "Symbol", all_symbols, default=all_symbols, key="trade_sym",
            )
        with filter_col2:
            all_strategies = sorted(trades_df["strategy"].unique().tolist())
            sel_strategies = st.multiselect(
                "Strategy", all_strategies, default=all_strategies,
                key="trade_strat",
            )
        with filter_col3:
            all_directions = sorted(trades_df["direction"].unique().tolist())
            sel_directions = st.multiselect(
                "Direction", all_directions, default=all_directions,
                key="trade_dir",
            )

        filtered = trades_df.copy()
        if sel_symbols:
            filtered = filtered[filtered["symbol"].isin(sel_symbols)]
        if sel_strategies:
            filtered = filtered[filtered["strategy"].isin(sel_strategies)]
        if sel_directions:
            filtered = filtered[filtered["direction"].isin(sel_directions)]

        display_cols = [
            "timestamp", "symbol", "strategy", "direction", "side",
            "quantity", "price", "pnl", "regime", "equity_after",
        ]
        existing_cols = [c for c in display_cols if c in filtered.columns]
        display_df = filtered[existing_cols].sort_values(
            "timestamp", ascending=False,
        )

        pnl_subset = ["pnl"] if "pnl" in display_df.columns else []
        st.dataframe(
            display_df.style.map(
                lambda v: (
                    "color: #2ecc71"
                    if isinstance(v, (int, float)) and v > 0
                    else (
                        "color: #e74c3c"
                        if isinstance(v, (int, float)) and v < 0
                        else ""
                    )
                ),
                subset=pnl_subset,
            ),
            height=500,
        )
        st.caption(f"Showing {len(filtered)} of {len(trades_df)} trades")

# ════════════════════════════════════════════════════════════════════════
# Tab 3: Analysis
# ════════════════════════════════════════════════════════════════════════
with tab_analysis:
    if trades_df.empty:
        st.info("No trades to analyze yet.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(
                live_charts.live_pnl_by_strategy(trades_df), key="strat_pnl",
            )
        with col_b:
            st.plotly_chart(
                live_charts.live_pnl_by_symbol(trades_df), key="sym_pnl",
            )

        col_c, col_d = st.columns(2)
        with col_c:
            st.plotly_chart(
                live_charts.live_trade_timeline(trades_df), key="timeline",
            )
        with col_d:
            st.plotly_chart(
                live_charts.live_cumulative_pnl(trades_df), key="cum_pnl",
            )

        st.subheader("Strategy Performance")
        strat_metrics = live_data.per_strategy_metrics(trades_df)
        if strat_metrics:
            strat_rows = []
            for name, m in strat_metrics.items():
                strat_rows.append({
                    "Strategy": name,
                    "Trades": m["trade_count"],
                    "Win Rate": f"{m['win_rate']:.1%}",
                    "Total PnL": f"${m['total_pnl']:+,.2f}",
                    "Avg PnL": f"${m['avg_pnl']:+,.2f}",
                })
            st.dataframe(pd.DataFrame(strat_rows))

        st.subheader("Regime Performance")
        regime_metrics = live_data.per_regime_metrics(trades_df)
        if regime_metrics:
            regime_rows = []
            for name, m in regime_metrics.items():
                regime_rows.append({
                    "Regime": name,
                    "Trades": m["trade_count"],
                    "Win Rate": f"{m['win_rate']:.1%}",
                    "Total PnL": f"${m['total_pnl']:+,.2f}",
                })
            st.dataframe(pd.DataFrame(regime_rows))

# ════════════════════════════════════════════════════════════════════════
# Tab 4: Positions
# ════════════════════════════════════════════════════════════════════════
with tab_positions:
    st.subheader("Current Open Positions")
    if not data.current_positions:
        st.info("No open positions.")
    else:
        st.write(f"**Symbols:** {', '.join(data.current_positions)}")

    if not trades_df.empty:
        st.subheader("Per-Symbol Performance")
        sym_metrics = live_data.per_symbol_metrics(trades_df)
        if sym_metrics:
            sym_rows = []
            for sym, m in sym_metrics.items():
                sym_rows.append({
                    "Symbol": sym,
                    "Trades": m["trade_count"],
                    "Win Rate": f"{m['win_rate']:.1%}",
                    "Total PnL": f"${m['total_pnl']:+,.2f}",
                    "Avg PnL": f"${m['avg_pnl']:+,.2f}",
                })
            st.dataframe(pd.DataFrame(sym_rows))
