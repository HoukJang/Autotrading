"""Trade log component -- filterable trade history with daily PnL chart."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from autotrader.dashboard.theme import COLORS, STRATEGY_NAMES
from autotrader.dashboard.utils.chart_helpers import get_chart_layout
from autotrader.dashboard.utils.formatters import fmt_currency, fmt_pnl, pnl_color


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _style_pnl(val: object) -> str:
    """Return CSS color string for a PnL cell value."""
    try:
        num = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if num > 0:
        return f"color: {COLORS['profit']}"
    if num < 0:
        return f"color: {COLORS['loss']}"
    return f"color: {COLORS['neutral']}"


def _apply_filters(
    df: pd.DataFrame,
    date_from: date,
    date_to: date,
    strategies: list[str],
    directions: list[str],
    result_filter: str,
) -> pd.DataFrame:
    """Return a filtered copy of *df* based on the user's selections."""
    mask = pd.Series(True, index=df.index)

    # Date range
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"])
        mask &= ts.dt.date >= date_from
        mask &= ts.dt.date <= date_to

    # Strategy
    if strategies and "strategy" in df.columns:
        mask &= df["strategy"].isin(strategies)

    # Direction
    if directions and "direction" in df.columns:
        mask &= df["direction"].isin(directions)

    # Result (winners / losers) -- only meaningful for close trades
    if result_filter == "Winners" and "pnl" in df.columns:
        mask &= df["pnl"] > 0
    elif result_filter == "Losers" and "pnl" in df.columns:
        mask &= df["pnl"] < 0

    return df.loc[mask].copy()


# ------------------------------------------------------------------
# Daily PnL chart (close trades only)
# ------------------------------------------------------------------


def _render_daily_pnl_chart(close_df: pd.DataFrame) -> None:
    """Render a daily PnL bar chart from close trades."""
    if close_df.empty:
        st.caption("No close trades in the selected range for daily PnL chart.")
        return

    df = close_df.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily = df.groupby("date")["pnl"].sum().reset_index()
    daily.columns = ["date", "pnl"]

    bar_colors = [
        COLORS["profit"] if v >= 0 else COLORS["loss"] for v in daily["pnl"]
    ]

    fig = go.Figure(
        go.Bar(
            x=daily["date"],
            y=daily["pnl"],
            marker_color=bar_colors,
            hovertemplate="Date: %{x}<br>PnL: %{y:$,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **get_chart_layout(
            title={"text": "Daily PnL"},
            height=250,
            yaxis={"title": "PnL ($)"},
            xaxis={"title": ""},
            showlegend=False,
        )
    )

    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------
# Trade table
# ------------------------------------------------------------------

_DISPLAY_COLS = [
    "timestamp",
    "symbol",
    "strategy",
    "direction",
    "side",
    "quantity",
    "price",
    "pnl",
    "regime",
    "exit_reason",
    "bars_held",
    "mfe",
    "mae",
]


def _render_trade_table(df: pd.DataFrame, total_count: int) -> None:
    """Render a styled trade table sorted by timestamp descending."""
    # Keep only columns that exist in the dataframe
    cols = [c for c in _DISPLAY_COLS if c in df.columns]
    display = df[cols].sort_values("timestamp", ascending=False).reset_index(drop=True)

    # Map strategy keys to display names where applicable
    if "strategy" in display.columns:
        display["strategy"] = display["strategy"].map(
            lambda s: STRATEGY_NAMES.get(s, s)
        )

    st.caption(f"Showing {len(display)} of {total_count} trades")

    # Style the PnL-related columns
    pnl_cols_present = [c for c in ("pnl", "mfe", "mae") if c in display.columns]

    if pnl_cols_present:
        styled = display.style.map(_style_pnl, subset=pnl_cols_present)
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.dataframe(display, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def render_trade_log(trades_df: pd.DataFrame) -> None:
    """Render the full trade log tab with filters, daily PnL chart, and table."""

    if trades_df is None or trades_df.empty:
        st.info(
            "No trades recorded yet. Start live trading to see trade history."
        )
        return

    df = trades_df.copy()

    # Ensure timestamp is datetime
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # ------------------------------------------------------------------
    # Filter row
    # ------------------------------------------------------------------
    all_strategies = sorted(df["strategy"].unique().tolist()) if "strategy" in df.columns else []
    all_directions = (
        sorted(df["direction"].unique().tolist()) if "direction" in df.columns else ["long", "short", "close"]
    )

    today = date.today()
    default_from = today - timedelta(days=30)

    col_date, col_strat, col_dir, col_result = st.columns(4)

    with col_date:
        date_range = st.date_input(
            "Date range",
            value=(default_from, today),
            key="trade_log_date_range",
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            date_from, date_to = date_range
        else:
            date_from, date_to = default_from, today

    with col_strat:
        selected_strategies = st.multiselect(
            "Strategy",
            options=all_strategies,
            default=all_strategies,
            key="trade_log_strategy",
        )

    with col_dir:
        selected_directions = st.multiselect(
            "Direction",
            options=all_directions,
            default=all_directions,
            key="trade_log_direction",
        )

    with col_result:
        result_filter = st.selectbox(
            "Result",
            options=["All", "Winners", "Losers"],
            index=0,
            key="trade_log_result",
        )

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------
    filtered = _apply_filters(
        df, date_from, date_to, selected_strategies, selected_directions, result_filter
    )

    # ------------------------------------------------------------------
    # Daily PnL chart (close trades only from filtered set)
    # ------------------------------------------------------------------
    close_trades = filtered.loc[filtered["direction"] == "close"] if "direction" in filtered.columns else filtered
    _render_daily_pnl_chart(close_trades)

    # ------------------------------------------------------------------
    # Trade table
    # ------------------------------------------------------------------
    _render_trade_table(filtered, total_count=len(df))
