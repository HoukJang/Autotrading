"""Strategy analysis component for the trading dashboard (Tab 4).

Renders per-strategy performance table, per-regime performance,
strategy-regime heatmap, SL/TP hit analysis, and PnL by symbol chart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from autotrader.dashboard.theme import (
    COLORS,
    REGIME_COLORS,
    STRATEGY_COLORS,
    STRATEGY_NAMES,
)
from autotrader.dashboard.utils.chart_helpers import get_chart_layout
from autotrader.dashboard.utils.formatters import fmt_currency, fmt_pct, fmt_pnl


# ------------------------------------------------------------------
# Metric computation helpers
# ------------------------------------------------------------------


def _max_consecutive_losses(pnl_series: pd.Series) -> int:
    """Return the length of the longest consecutive-loss streak."""
    if pnl_series.empty:
        return 0
    is_loss = (pnl_series < 0).astype(int)
    groups = is_loss.ne(is_loss.shift()).cumsum()
    streaks = is_loss.groupby(groups).agg(["sum", "count"])
    loss_streaks = streaks.loc[streaks["sum"] == streaks["count"], "count"]
    if loss_streaks.empty:
        return 0
    return int(loss_streaks.max())


def _compute_strategy_metrics(close_df: pd.DataFrame) -> pd.DataFrame:
    """Build a per-strategy metrics DataFrame from close trades."""
    rows: list[dict] = []

    strategies = sorted(close_df["strategy"].unique()) if not close_df.empty else []

    for strat in strategies:
        sdf = close_df.loc[close_df["strategy"] == strat].sort_values("timestamp")
        total = len(sdf)
        if total == 0:
            continue

        winners = sdf.loc[sdf["pnl"] > 0, "pnl"]
        losers = sdf.loc[sdf["pnl"] < 0, "pnl"]

        win_rate = len(winners) / total if total > 0 else 0.0
        gross_profit = winners.sum() if not winners.empty else 0.0
        gross_loss = abs(losers.sum()) if not losers.empty else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        total_pnl = sdf["pnl"].sum()
        avg_pnl = sdf["pnl"].mean()
        avg_bars = float(sdf["bars_held"].mean()) if "bars_held" in sdf.columns else 0.0
        max_cl = _max_consecutive_losses(sdf["pnl"].reset_index(drop=True))

        rows.append(
            {
                "Strategy": STRATEGY_NAMES.get(strat, strat),
                "Trades": total,
                "Win Rate": win_rate,
                "Profit Factor": profit_factor,
                "Total PnL": total_pnl,
                "Avg PnL": avg_pnl,
                "Avg Bars Held": avg_bars,
                "Max Consec. Loss": max_cl,
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Section 1: Strategy Performance Table
# ------------------------------------------------------------------


def _render_performance_table(metrics_df: pd.DataFrame) -> None:
    """Display the per-strategy metrics table."""
    st.subheader("Strategy Performance")

    if metrics_df.empty:
        st.caption("No close trades available for performance analysis.")
        return

    display = metrics_df.copy()
    display["Win Rate"] = display["Win Rate"].map(lambda v: f"{v * 100:.1f}%")
    display["Profit Factor"] = display["Profit Factor"].map(
        lambda v: "Inf" if v == float("inf") else f"{v:.2f}"
    )
    display["Total PnL"] = display["Total PnL"].map(fmt_pnl)
    display["Avg PnL"] = display["Avg PnL"].map(fmt_pnl)
    display["Avg Bars Held"] = display["Avg Bars Held"].map(lambda v: f"{v:.1f}")
    display["Max Consec. Loss"] = display["Max Consec. Loss"].astype(int)

    st.dataframe(display, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Section 2: Per-Regime Performance Table
# ------------------------------------------------------------------


def _render_regime_performance(close_df: pd.DataFrame) -> None:
    """Display per-regime trade performance."""
    st.subheader("Performance by Regime")

    if close_df.empty or "regime" not in close_df.columns:
        st.caption("No regime data available.")
        return

    rows = []
    for regime, group in close_df.groupby("regime"):
        pnls = group["pnl"]
        wins = int((pnls > 0).sum())
        count = len(group)
        rows.append(
            {
                "Regime": str(regime),
                "Trades": count,
                "Win Rate": f"{wins / count * 100:.1f}%" if count > 0 else "--",
                "Total PnL": fmt_pnl(float(pnls.sum())),
                "Avg PnL": fmt_pnl(float(pnls.mean())),
            }
        )

    if not rows:
        st.caption("No regime data available.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Section 3: Cumulative PnL + PnL by Strategy bar
# ------------------------------------------------------------------


def _render_cumulative_pnl(close_df: pd.DataFrame) -> None:
    """Render cumulative PnL line chart (left) and total PnL bar chart (right)."""
    st.subheader("Strategy PnL Breakdown")

    if close_df.empty:
        st.caption("No close trades available.")
        return

    col_left, col_right = st.columns([0.6, 0.4])
    strategies = sorted(close_df["strategy"].unique())

    with col_left:
        fig_cum = go.Figure()
        for strat in strategies:
            sdf = close_df.loc[close_df["strategy"] == strat].sort_values("timestamp")
            if sdf.empty:
                continue
            cum_pnl = sdf["pnl"].cumsum()
            color = STRATEGY_COLORS.get(strat, COLORS["info"])
            name = STRATEGY_NAMES.get(strat, strat)
            fig_cum.add_trace(
                go.Scatter(
                    x=sdf["timestamp"],
                    y=cum_pnl,
                    mode="lines",
                    name=name,
                    line={"color": color, "width": 2},
                    hovertemplate=f"{name}<br>Date: %{{x}}<br>Cumulative PnL: %{{y:$,.2f}}<extra></extra>",
                )
            )

        fig_cum.update_layout(
            **get_chart_layout(
                title={"text": "Cumulative PnL by Strategy"},
                height=350,
                yaxis={"title": "Cumulative PnL ($)"},
                xaxis={"title": ""},
            )
        )
        st.plotly_chart(fig_cum, use_container_width=True, key="cumulative_pnl")

    with col_right:
        totals = (
            close_df.groupby("strategy")["pnl"]
            .sum()
            .reindex(strategies)
            .fillna(0.0)
        )
        display_names = [STRATEGY_NAMES.get(s, s) for s in totals.index]
        bar_colors = [
            COLORS["profit"] if v >= 0 else COLORS["loss"] for v in totals.values
        ]
        fig_bar = go.Figure(
            go.Bar(
                y=display_names,
                x=totals.values,
                orientation="h",
                marker_color=bar_colors,
                text=[fmt_pnl(v) for v in totals.values],
                textposition="auto",
                textfont={"color": COLORS["text_primary"]},
                hovertemplate="Strategy: %{y}<br>Total PnL: %{x:$,.2f}<extra></extra>",
            )
        )
        fig_bar.update_layout(
            **get_chart_layout(
                title={"text": "Total PnL by Strategy"},
                height=350,
                xaxis={"title": "PnL ($)"},
                yaxis={"title": ""},
                showlegend=False,
            )
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="total_pnl_bar")


# ------------------------------------------------------------------
# Section 4: Regime-Strategy Heatmap
# ------------------------------------------------------------------

_REGIME_ORDER = ["TREND", "RANGING", "HIGH_VOLATILITY", "UNCERTAIN"]


def _render_regime_heatmap(close_df: pd.DataFrame) -> None:
    """Render a win-rate heatmap: strategies (rows) vs regimes (columns)."""
    st.subheader("Win Rate by Strategy and Regime")

    if close_df.empty or "regime" not in close_df.columns:
        st.caption("Not enough data to build the regime-strategy heatmap.")
        return

    strategies = sorted(close_df["strategy"].unique())
    regimes = [r for r in _REGIME_ORDER if r in close_df["regime"].unique()]

    if not regimes:
        st.caption("No regime data available.")
        return

    z_values: list[list[float]] = []
    text_values: list[list[str]] = []

    for strat in strategies:
        row_z: list[float] = []
        row_t: list[str] = []
        for regime in regimes:
            subset = close_df.loc[
                (close_df["strategy"] == strat) & (close_df["regime"] == regime)
            ]
            if len(subset) == 0:
                row_z.append(float("nan"))
                row_t.append("N/A")
            else:
                wr = (subset["pnl"] > 0).sum() / len(subset)
                row_z.append(wr)
                row_t.append(f"{wr * 100:.0f}%\n({len(subset)})")
        z_values.append(row_z)
        text_values.append(row_t)

    y_labels = [STRATEGY_NAMES.get(s, s) for s in strategies]

    fig = go.Figure(
        go.Heatmap(
            z=z_values,
            x=regimes,
            y=y_labels,
            text=text_values,
            texttemplate="%{text}",
            textfont={"size": 12, "color": COLORS["text_primary"]},
            colorscale=[
                [0.0, COLORS["loss"]],
                [0.5, COLORS["warning"]],
                [1.0, COLORS["profit"]],
            ],
            zmin=0,
            zmax=1,
            colorbar={
                "title": {"text": "Win Rate", "font": {"color": COLORS["text_secondary"]}},
                "tickformat": ".0%",
                "tickfont": {"color": COLORS["text_secondary"]},
            },
            hovertemplate=(
                "Strategy: %{y}<br>"
                "Regime: %{x}<br>"
                "Win Rate: %{text}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **get_chart_layout(
            height=300,
            xaxis={"title": "", "side": "bottom"},
            yaxis={"title": "", "autorange": "reversed"},
            showlegend=False,
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="regime_heatmap")


# ------------------------------------------------------------------
# Section 5: SL/TP Hit Analysis
# ------------------------------------------------------------------


def _render_exit_analysis(close_df: pd.DataFrame) -> None:
    """Render a stacked bar chart showing exit reason distribution per strategy."""
    st.subheader("Exit Reason Analysis")

    if close_df.empty or "exit_reason" not in close_df.columns:
        st.caption("No exit reason data available.")
        return

    # Count exit reasons per strategy
    strategies = sorted(close_df["strategy"].unique())
    exit_reasons = close_df["exit_reason"].dropna().unique().tolist()

    if not exit_reasons:
        st.caption("No exit reason data found.")
        return

    # Color map for exit reasons
    exit_colors = {
        "stop_loss": COLORS["loss"],
        "sl": COLORS["loss"],
        "take_profit": COLORS["profit"],
        "tp": COLORS["profit"],
        "target": COLORS["profit"],
        "timeout": COLORS["warning"],
        "time": COLORS["warning"],
        "emergency": "#FF0000",
        "manual": COLORS["neutral"],
    }

    fig = go.Figure()

    for reason in exit_reasons:
        counts = []
        for strat in strategies:
            strat_df = close_df[close_df["strategy"] == strat]
            count = int((strat_df["exit_reason"] == reason).sum())
            counts.append(count)

        color = exit_colors.get(str(reason).lower(), COLORS["info"])
        fig.add_trace(
            go.Bar(
                name=str(reason),
                x=[STRATEGY_NAMES.get(s, s) for s in strategies],
                y=counts,
                marker_color=color,
                hovertemplate=f"Exit: {reason}<br>Strategy: %{{x}}<br>Count: %{{y}}<extra></extra>",
            )
        )

    fig.update_layout(
        **get_chart_layout(
            title={"text": "Exit Reasons by Strategy"},
            height=320,
            barmode="stack",
            xaxis={"title": ""},
            yaxis={"title": "Trade Count"},
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="exit_analysis")


# ------------------------------------------------------------------
# Section 6: PnL by Symbol
# ------------------------------------------------------------------


def _render_pnl_by_symbol(close_df: pd.DataFrame) -> None:
    """Render a horizontal bar chart of total PnL per symbol (top 15)."""
    st.subheader("PnL by Symbol")

    if close_df.empty or "symbol" not in close_df.columns:
        st.caption("No symbol-level PnL data available.")
        return

    symbol_pnl = close_df.groupby("symbol")["pnl"].sum()
    top15 = symbol_pnl.reindex(
        symbol_pnl.abs().nlargest(15).index
    ).sort_values()

    if top15.empty:
        st.caption("No symbol-level PnL data available.")
        return

    bar_colors = [
        COLORS["profit"] if v >= 0 else COLORS["loss"] for v in top15.values
    ]

    fig = go.Figure(
        go.Bar(
            y=top15.index.tolist(),
            x=top15.values,
            orientation="h",
            marker_color=bar_colors,
            text=[fmt_pnl(v) for v in top15.values],
            textposition="auto",
            textfont={"color": COLORS["text_primary"]},
            hovertemplate="Symbol: %{y}<br>Total PnL: %{x:$,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **get_chart_layout(
            title={"text": "PnL by Symbol (Top 15)"},
            height=350,
            xaxis={"title": "PnL ($)"},
            yaxis={"title": ""},
            showlegend=False,
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="pnl_by_symbol")


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def render_strategy_analysis(
    trades_df: pd.DataFrame, equity_df: pd.DataFrame
) -> None:
    """Render the strategy analysis tab with metrics, charts, and heatmap."""
    if trades_df is None or trades_df.empty:
        st.info(
            "No trades recorded yet. Start live trading to see strategy analysis."
        )
        return

    df = trades_df.copy()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Only close trades carry realized PnL
    if "direction" in df.columns:
        close_df = df.loc[df["direction"] == "close"].copy()
    elif "side" in df.columns:
        close_df = df.loc[df["side"] == "exit"].copy()
    else:
        close_df = df.copy()

    # Section 1: Performance table
    metrics = _compute_strategy_metrics(close_df)
    _render_performance_table(metrics)

    st.divider()

    # Section 2: Per-regime performance
    _render_regime_performance(close_df)

    st.divider()

    # Section 3: Cumulative PnL + bar chart
    _render_cumulative_pnl(close_df)

    st.divider()

    # Section 4: Regime-Strategy heatmap
    _render_regime_heatmap(close_df)

    st.divider()

    # Section 5: SL/TP hit analysis
    _render_exit_analysis(close_df)

    st.divider()

    # Section 6: PnL by symbol
    _render_pnl_by_symbol(close_df)
