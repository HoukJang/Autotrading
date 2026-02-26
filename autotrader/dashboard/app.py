"""Streamlit backtest dashboard for AutoTrader v2.

Usage:
    streamlit run autotrader/dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root on path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd

from autotrader.dashboard import data_loader, charts

st.set_page_config(
    page_title="AutoTrader v2 - Backtest Dashboard",
    layout="wide",
)

st.title("AutoTrader v2 - Backtest Dashboard")

# ── Sidebar: file selector ──────────────────────────────────────────────
data_dir = _PROJECT_ROOT / "data" / "backtest_results"
result_files = data_loader.list_result_files(data_dir)

if not result_files:
    st.warning("No backtest results found in data/backtest_results/. "
               "Run `python scripts/run_backtest_dashboard.py` first.")
    st.stop()

selected_file = st.sidebar.selectbox(
    "Result File",
    result_files,
    format_func=lambda p: p.name,
)

data = data_loader.BacktestDashboardData.from_json(selected_file)
df_trades = data_loader.trades_df(data)
df_equity = data_loader.equity_df(data)

# ── Tabs ────────────────────────────────────────────────────────────────
tab_overview, tab_trades, tab_symbol, tab_analysis = st.tabs(
    ["Overview", "Trades", "Per-Symbol", "Analysis"]
)

# ════════════════════════════════════════════════════════════════════════
# Tab 1: Overview
# ════════════════════════════════════════════════════════════════════════
with tab_overview:
    agg = data.aggregate_metrics
    initial = data.config.get("initial_balance", 100_000)
    final_equity = agg.get("final_equity", initial)
    total_pnl = agg.get("total_pnl", 0)
    win_rate = agg.get("win_rate", 0)
    pf = agg.get("profit_factor", 0)
    if isinstance(pf, str):
        pf_display = pf
    else:
        pf_display = f"{pf:.2f}"

    # Compute max drawdown across all symbols
    all_max_dd = max(
        (m.get("max_drawdown", 0) for m in data.per_symbol_metrics.values()),
        default=0,
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Equity", f"${final_equity:,.2f}")
    col2.metric("Total PnL", f"${total_pnl:+,.2f}")
    col3.metric("Win Rate", f"{win_rate:.1%}")
    col4.metric("Profit Factor", pf_display)
    col5.metric("Max Drawdown", f"{all_max_dd:.2%}")

    # Equity curve
    st.plotly_chart(
        charts.equity_curve_chart(df_equity),
        use_container_width=True,
        key="overview_equity",
    )

    # Strategy allocation + PnL
    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(
            charts.strategy_allocation_pie(df_trades),
            use_container_width=True,
            key="overview_alloc_pie",
        )
    with col_right:
        st.plotly_chart(
            charts.per_strategy_pnl_bar(data.per_substrategy_metrics),
            use_container_width=True,
            key="overview_strategy_pnl",
        )

    # Config info
    with st.expander("Backtest Config"):
        st.json(data.config)

# ════════════════════════════════════════════════════════════════════════
# Tab 2: Trades
# ════════════════════════════════════════════════════════════════════════
with tab_trades:
    if df_trades.empty:
        st.info("No trades recorded.")
    else:
        # Filters
        all_symbols = sorted(df_trades["symbol"].unique().tolist())
        all_sub_strats = sorted(df_trades["sub_strategy"].unique().tolist())

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            sel_symbols = st.multiselect("Symbol", all_symbols, default=all_symbols)
        with filter_col2:
            sel_substrats = st.multiselect(
                "Sub-Strategy", all_sub_strats, default=all_sub_strats
            )

        filtered = data_loader.filter_trades(df_trades, sel_symbols, sel_substrats)

        if filtered.empty:
            st.info("No trades match filters.")
        else:
            display_cols = [
                "trade_id", "symbol", "sub_strategy", "entry_time", "exit_time",
                "entry_price", "exit_price", "quantity", "pnl", "pnl_pct",
                "bars_held", "exit_reason",
            ]
            display_df = filtered[display_cols].copy()
            display_df.columns = [
                "#", "Symbol", "Sub-Strategy", "Entry Time", "Exit Time",
                "Entry$", "Exit$", "Qty", "PnL($)", "PnL(%)",
                "Bars", "Exit Reason",
            ]

            st.dataframe(
                display_df.style.map(
                    lambda v: "color: #2ecc71" if isinstance(v, (int, float)) and v > 0
                    else ("color: #e74c3c" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["PnL($)", "PnL(%)"],
                ),
                use_container_width=True,
                height=500,
            )

            st.caption(f"Showing {len(filtered)} of {len(df_trades)} trades")

# ════════════════════════════════════════════════════════════════════════
# Tab 3: Per-Symbol
# ════════════════════════════════════════════════════════════════════════
with tab_symbol:
    # Symbol comparison bar chart
    st.plotly_chart(
        charts.per_symbol_pnl_bar(data.per_symbol_metrics),
        use_container_width=True,
        key="symbol_pnl_bar",
    )

    # Per-symbol metrics table
    if data.per_symbol_metrics:
        rows = []
        for sym, m in data.per_symbol_metrics.items():
            pf_val = m.get("profit_factor", 0)
            rows.append({
                "Symbol": sym,
                "Trades": m.get("total_trades", 0),
                "Win Rate": f"{m.get('win_rate', 0):.1%}",
                "Total PnL": f"${m.get('total_pnl', 0):+,.2f}",
                "Profit Factor": f"{pf_val:.2f}" if pf_val != float("inf") else "inf",
                "Max Drawdown": f"{m.get('max_drawdown', 0):.2%}",
                "Final Equity": f"${m.get('final_equity', 0):,.2f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Overlaid equity curves
    st.plotly_chart(
        charts.equity_curve_chart(df_equity),
        use_container_width=True,
        key="symbol_equity",
    )

# ════════════════════════════════════════════════════════════════════════
# Tab 4: Analysis
# ════════════════════════════════════════════════════════════════════════
with tab_analysis:
    if df_trades.empty:
        st.info("No trades to analyze.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(
                charts.pnl_distribution_histogram(df_trades),
                use_container_width=True,
                key="analysis_pnl_hist",
            )
        with col_b:
            st.plotly_chart(
                charts.exit_reason_pie(df_trades),
                use_container_width=True,
                key="analysis_exit_pie",
            )

        col_c, col_d = st.columns(2)
        with col_c:
            st.plotly_chart(
                charts.cumulative_pnl_chart(df_trades),
                use_container_width=True,
                key="analysis_cum_pnl",
            )
        with col_d:
            st.plotly_chart(
                charts.bars_held_histogram(df_trades),
                use_container_width=True,
                key="analysis_bars_hist",
            )

        # Sub-strategy comparison table
        if data.per_substrategy_metrics:
            st.subheader("Sub-Strategy Comparison")
            ss_rows = []
            for ss, m in data.per_substrategy_metrics.items():
                ss_rows.append({
                    "Sub-Strategy": ss,
                    "Trades": m["trade_count"],
                    "Win Rate": f"{m['win_rate']:.1%}",
                    "Total PnL": f"${m['total_pnl']:+,.2f}",
                    "Avg PnL": f"${m['avg_pnl']:+,.2f}",
                })
            st.dataframe(pd.DataFrame(ss_rows), use_container_width=True)
