"""Strategy analysis component -- per-strategy metrics, cumulative PnL, and regime heatmap."""
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
    # Group consecutive identical values, then find max group length where loss
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
        avg_bars = sdf["bars_held"].mean() if "bars_held" in sdf.columns else 0.0
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

    # Format for display
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
# Section 2: Cumulative PnL + PnL by Strategy bar
# ------------------------------------------------------------------


def _render_cumulative_pnl(close_df: pd.DataFrame) -> None:
    """Render cumulative PnL line chart (left) and total PnL bar chart (right)."""
    st.subheader("Strategy PnL Breakdown")

    if close_df.empty:
        st.caption("No close trades available.")
        return

    col_left, col_right = st.columns([0.6, 0.4])

    strategies = sorted(close_df["strategy"].unique())

    # --- Left: Cumulative PnL lines ---
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
                    hovertemplate=f"{name}<br>"
                    "Date: %{x}<br>"
                    "Cumulative PnL: %{y:$,.2f}<extra></extra>",
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
        st.plotly_chart(fig_cum, use_container_width=True)

    # --- Right: Total PnL horizontal bar ---
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
        st.plotly_chart(fig_bar, use_container_width=True)


# ------------------------------------------------------------------
# Section 3: Regime-Strategy Heatmap
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

    # Build matrix: rows = strategies, cols = regimes, values = win rate
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
                row_t.append(f"{wr * 100:.0f}%")
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
            textfont={"size": 13, "color": COLORS["text_primary"]},
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

    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------
# Section 4: PnL by Symbol
# ------------------------------------------------------------------


def _render_pnl_by_symbol(close_df: pd.DataFrame) -> None:
    """Render a horizontal bar chart of total PnL per symbol (top 15)."""
    st.subheader("PnL by Symbol")

    if close_df.empty or "symbol" not in close_df.columns:
        st.caption("No symbol-level PnL data available.")
        return

    symbol_pnl = close_df.groupby("symbol")["pnl"].sum()
    # Top 15 by absolute PnL
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

    st.plotly_chart(fig, use_container_width=True)


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

    # Ensure timestamp is datetime
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Only close trades carry realized PnL
    close_df = df.loc[df["direction"] == "close"].copy() if "direction" in df.columns else df.copy()

    # Section 1: Performance table
    metrics = _compute_strategy_metrics(close_df)
    _render_performance_table(metrics)

    st.divider()

    # Section 2: Cumulative PnL + bar chart
    _render_cumulative_pnl(close_df)

    st.divider()

    # Section 3: Regime-Strategy heatmap
    _render_regime_heatmap(close_df)

    st.divider()

    # Section 4: PnL by symbol
    _render_pnl_by_symbol(close_df)
