"""Plotly chart functions for the backtest dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd


def equity_curve_chart(eq_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if eq_df.empty:
        return fig
    for symbol in eq_df["symbol"].unique():
        subset = eq_df[eq_df["symbol"] == symbol]
        fig.add_trace(go.Scatter(
            x=subset["timestamp"],
            y=subset["equity"],
            mode="lines",
            name=symbol,
        ))
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Time",
        yaxis_title="Equity ($)",
        hovermode="x unified",
        height=400,
    )
    return fig


def strategy_allocation_pie(trades_df: pd.DataFrame) -> go.Figure:
    if trades_df.empty:
        return go.Figure()
    counts = trades_df["sub_strategy"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.4,
        textinfo="label+percent+value",
    ))
    fig.update_layout(title="Strategy Allocation (Trade Count)", height=350)
    return fig


def per_strategy_pnl_bar(per_substrategy: dict[str, dict]) -> go.Figure:
    if not per_substrategy:
        return go.Figure()
    names = list(per_substrategy.keys())
    pnls = [per_substrategy[n]["total_pnl"] for n in names]
    colors = ["#2ecc71" if p >= 0 else "#e74c3c" for p in pnls]
    fig = go.Figure(go.Bar(
        x=names,
        y=pnls,
        marker_color=colors,
        text=[f"${p:+,.2f}" for p in pnls],
        textposition="outside",
    ))
    fig.update_layout(
        title="PnL by Sub-Strategy",
        yaxis_title="Total PnL ($)",
        height=350,
    )
    return fig


def per_symbol_pnl_bar(per_symbol: dict[str, dict]) -> go.Figure:
    if not per_symbol:
        return go.Figure()
    symbols = list(per_symbol.keys())
    pnls = [per_symbol[s].get("total_pnl", 0) for s in symbols]
    colors = ["#2ecc71" if p >= 0 else "#e74c3c" for p in pnls]
    fig = go.Figure(go.Bar(
        x=symbols,
        y=pnls,
        marker_color=colors,
        text=[f"${p:+,.2f}" for p in pnls],
        textposition="outside",
    ))
    fig.update_layout(
        title="PnL by Symbol",
        yaxis_title="Total PnL ($)",
        height=400,
    )
    return fig


def pnl_distribution_histogram(trades_df: pd.DataFrame) -> go.Figure:
    if trades_df.empty:
        return go.Figure()
    fig = go.Figure(go.Histogram(
        x=trades_df["pnl"],
        nbinsx=30,
        marker_color="#3498db",
    ))
    fig.update_layout(
        title="PnL Distribution",
        xaxis_title="PnL ($)",
        yaxis_title="Count",
        height=350,
    )
    return fig


def exit_reason_pie(trades_df: pd.DataFrame) -> go.Figure:
    if trades_df.empty:
        return go.Figure()
    counts = trades_df["exit_reason"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        textinfo="label+percent+value",
    ))
    fig.update_layout(title="Exit Reason Breakdown", height=350)
    return fig


def cumulative_pnl_chart(trades_df: pd.DataFrame) -> go.Figure:
    if trades_df.empty:
        return go.Figure()
    sorted_df = trades_df.sort_values("exit_time")
    cum_pnl = sorted_df["pnl"].cumsum()
    fig = go.Figure(go.Scatter(
        x=sorted_df["exit_time"],
        y=cum_pnl,
        mode="lines+markers",
        line=dict(color="#8e44ad"),
        name="Cumulative PnL",
    ))
    fig.update_layout(
        title="Cumulative PnL Over Time",
        xaxis_title="Exit Time",
        yaxis_title="Cumulative PnL ($)",
        height=350,
    )
    return fig


def bars_held_histogram(trades_df: pd.DataFrame) -> go.Figure:
    if trades_df.empty:
        return go.Figure()
    fig = go.Figure(go.Histogram(
        x=trades_df["bars_held"],
        nbinsx=20,
        marker_color="#e67e22",
    ))
    fig.update_layout(
        title="Bars Held Distribution",
        xaxis_title="Bars Held",
        yaxis_title="Count",
        height=350,
    )
    return fig
