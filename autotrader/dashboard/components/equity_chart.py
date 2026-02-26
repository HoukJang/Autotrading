"""Equity chart component for the live trading dashboard.

Renders a combined equity curve and drawdown chart with regime bands
and trade markers using Plotly subplots.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from autotrader.dashboard.theme import COLORS, STRATEGY_COLORS, STRATEGY_NAMES
from autotrader.dashboard.utils.chart_helpers import apply_regime_bands, get_chart_layout


def render_equity_section(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> None:
    """Render the equity curve with drawdown subplot and trade markers.

    Parameters
    ----------
    equity_df:
        DataFrame with columns: timestamp, equity, and optionally regime.
    trades_df:
        DataFrame with columns: timestamp, symbol, strategy, direction,
        side, price, pnl, and optionally equity_after.
    """
    if equity_df.empty:
        st.info("Waiting for live trading data...")
        return

    # -- Period selector -----------------------------------------------------
    period_options = ["1W", "1M", "3M", "ALL"]
    selected_period = st.radio(
        "Period",
        period_options,
        index=3,
        horizontal=True,
        key="equity_period_selector",
    )

    filtered_eq = _filter_by_period(equity_df, selected_period)
    if filtered_eq.empty:
        st.info("No equity data for the selected period.")
        return

    filtered_eq = filtered_eq.sort_values("timestamp").reset_index(drop=True)

    # -- Build subplots ------------------------------------------------------
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.02,
    )

    # Row 1: Equity curve
    fig.add_trace(
        go.Scatter(
            x=filtered_eq["timestamp"],
            y=filtered_eq["equity"],
            mode="lines",
            name="Equity",
            line={"color": COLORS["info"], "width": 2},
            hovertemplate="$%{y:,.2f}<extra>Equity</extra>",
        ),
        row=1,
        col=1,
    )

    # Apply regime bands to equity chart
    apply_regime_bands(fig, filtered_eq, row=1, col=1)

    # Trade markers on equity curve
    _add_trade_markers(fig, trades_df, filtered_eq, row=1, col=1)

    # Row 2: Drawdown
    drawdown_series = _compute_drawdown(filtered_eq)
    fig.add_trace(
        go.Scatter(
            x=filtered_eq["timestamp"],
            y=drawdown_series,
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            fillcolor="rgba(255, 71, 87, 0.15)",
            line={"color": COLORS["loss"], "width": 1},
            hovertemplate="%{y:.2%}<extra>Drawdown</extra>",
        ),
        row=2,
        col=1,
    )

    # -- Layout --------------------------------------------------------------
    layout = get_chart_layout(height=500)
    fig.update_layout(**layout)

    # Axis labels
    fig.update_yaxes(
        title_text="Equity ($)",
        row=1,
        col=1,
        gridcolor=COLORS["bg_section"],
        tickfont={"color": COLORS["text_secondary"]},
    )
    fig.update_yaxes(
        title_text="Drawdown",
        tickformat=".1%",
        row=2,
        col=1,
        gridcolor=COLORS["bg_section"],
        tickfont={"color": COLORS["text_secondary"]},
    )
    fig.update_xaxes(
        gridcolor=COLORS["bg_section"],
        tickfont={"color": COLORS["text_secondary"]},
        row=2,
        col=1,
    )

    st.plotly_chart(fig, use_container_width=True, key="main_equity")


def _filter_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Filter DataFrame rows to the selected time period."""
    if period == "ALL" or df.empty:
        return df

    now = datetime.now(timezone.utc)
    delta_map = {
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
    }
    delta = delta_map.get(period)
    if delta is None:
        return df

    cutoff = now - delta

    ts_col = df["timestamp"]
    if not hasattr(ts_col.dtype, "tz") and str(ts_col.dtype).startswith("datetime64"):
        cutoff = cutoff.replace(tzinfo=None)

    return df[ts_col >= cutoff].copy()


def _compute_drawdown(equity_df: pd.DataFrame) -> pd.Series:
    """Compute drawdown percentage series from equity column."""
    equity = equity_df["equity"]
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    return drawdown.fillna(0.0)


def _add_trade_markers(
    fig: go.Figure,
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    row: int,
    col: int,
) -> None:
    """Add entry/exit trade markers on the equity curve.

    Entry trades are shown as triangles (up for long, down for short)
    in strategy-specific colors. Close trades are shown as X markers
    in gray.
    """
    if trades_df.empty or equity_df.empty:
        return

    # Ensure timestamp columns are comparable
    eq_ts = equity_df["timestamp"]
    min_ts = eq_ts.min()
    max_ts = eq_ts.max()

    # Filter trades within the displayed period
    trades_in_range = trades_df.copy()
    if "timestamp" in trades_in_range.columns:
        ts = trades_in_range["timestamp"]
        trades_in_range = trades_in_range[(ts >= min_ts) & (ts <= max_ts)]

    if trades_in_range.empty:
        return

    # For each trade, find the closest equity value by timestamp
    def _find_equity_at(ts_val):
        """Find the equity value closest to the given timestamp."""
        idx = (eq_ts - ts_val).abs().idxmin()
        return float(equity_df.loc[idx, "equity"])

    # Separate entries and exits
    if "side" not in trades_in_range.columns:
        return

    entries = trades_in_range[trades_in_range["side"] == "entry"]
    exits = trades_in_range[trades_in_range["side"] == "exit"]

    # Entry markers grouped by strategy
    if not entries.empty:
        for strategy, group in entries.groupby("strategy"):
            strategy_color = STRATEGY_COLORS.get(
                str(strategy), COLORS["text_secondary"],
            )
            strategy_name = STRATEGY_NAMES.get(str(strategy), str(strategy))

            timestamps = group["timestamp"].tolist()
            equity_values = [_find_equity_at(ts) for ts in timestamps]
            directions = group["direction"].tolist() if "direction" in group.columns else []

            symbols_list = []
            marker_symbols = []
            for i, d in enumerate(directions):
                if str(d).lower() == "short":
                    marker_symbols.append("triangle-down")
                else:
                    marker_symbols.append("triangle-up")
                sym = group.iloc[i]["symbol"] if "symbol" in group.columns else ""
                symbols_list.append(str(sym))

            hover_texts = [
                f"{sym} ({strategy_name})"
                for sym in symbols_list
            ]

            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=equity_values,
                    mode="markers",
                    name=f"Entry - {strategy_name}",
                    marker={
                        "symbol": marker_symbols,
                        "size": 10,
                        "color": strategy_color,
                        "line": {"width": 1, "color": COLORS["bg_primary"]},
                    },
                    text=hover_texts,
                    hovertemplate="%{text}<br>$%{y:,.2f}<extra></extra>",
                    showlegend=False,
                ),
                row=row,
                col=col,
            )

    # Exit markers
    if not exits.empty:
        timestamps = exits["timestamp"].tolist()
        equity_values = [_find_equity_at(ts) for ts in timestamps]
        symbols_list = (
            exits["symbol"].tolist() if "symbol" in exits.columns else [""] * len(exits)
        )
        hover_texts = [f"Close {sym}" for sym in symbols_list]

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity_values,
                mode="markers",
                name="Exit",
                marker={
                    "symbol": "x",
                    "size": 8,
                    "color": COLORS["neutral"],
                    "line": {"width": 1, "color": COLORS["bg_primary"]},
                },
                text=hover_texts,
                hovertemplate="%{text}<br>$%{y:,.2f}<extra></extra>",
                showlegend=False,
            ),
            row=row,
            col=col,
        )
