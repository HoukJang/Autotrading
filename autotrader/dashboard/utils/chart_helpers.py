"""Plotly chart helper functions for the trading dashboard."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from autotrader.dashboard.theme import COLORS, REGIME_COLORS, REGIME_TINTS


def get_chart_layout(**overrides: Any) -> dict:
    """Return a base Plotly layout dict styled for the dark trading theme.

    Any keyword arguments are merged on top of the defaults, allowing
    callers to override individual properties (e.g. ``title``, ``height``).
    """
    base: dict[str, Any] = {
        "paper_bgcolor": COLORS["bg_card"],
        "plot_bgcolor": COLORS["bg_primary"],
        "font": {
            "color": COLORS["text_primary"],
            "family": "Inter, system-ui, sans-serif",
            "size": 12,
        },
        "title": {
            "text": "",
            "font": {
                "size": 14,
                "color": COLORS["text_primary"],
            },
        },
        "xaxis": {
            "gridcolor": COLORS["bg_section"],
            "zerolinecolor": COLORS["bg_section"],
            "tickfont": {"color": COLORS["text_secondary"]},
        },
        "yaxis": {
            "gridcolor": COLORS["bg_section"],
            "zerolinecolor": COLORS["bg_section"],
            "tickfont": {"color": COLORS["text_secondary"]},
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": COLORS["text_secondary"], "size": 11},
        },
        "margin": {"l": 50, "r": 20, "t": 40, "b": 40},
        "hovermode": "x unified",
    }

    # Shallow-merge overrides (one level deep for nested dicts)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value

    return base


def apply_regime_bands(
    fig: Any,
    equity_df: pd.DataFrame,
    row: int = 1,
    col: int = 1,
) -> None:
    """Add vertical regime-colored bands (vrect shapes) to a Plotly figure.

    Parameters
    ----------
    fig:
        A ``plotly.graph_objects.Figure`` (or subplots figure).
    equity_df:
        DataFrame with at least ``timestamp`` and ``regime`` columns.
        Must be sorted by timestamp.
    row, col:
        Subplot row/col indices (1-based). Defaults target a single-panel
        figure.

    The function mutates *fig* in place and returns ``None``.
    """
    if equity_df.empty or "regime" not in equity_df.columns:
        return

    df = equity_df.sort_values("timestamp").reset_index(drop=True)

    # Build contiguous regime spans
    regimes = df["regime"].values
    timestamps = df["timestamp"].values

    span_start = 0
    for i in range(1, len(regimes)):
        if regimes[i] != regimes[span_start]:
            _add_regime_vrect(
                fig, timestamps[span_start], timestamps[i - 1],
                str(regimes[span_start]), row, col,
            )
            span_start = i

    # Final span
    if len(regimes) > 0:
        _add_regime_vrect(
            fig, timestamps[span_start], timestamps[-1],
            str(regimes[span_start]), row, col,
        )


def _add_regime_vrect(
    fig: Any,
    x0: Any,
    x1: Any,
    regime: str,
    row: int,
    col: int,
) -> None:
    """Add a single regime vrect shape to the figure."""
    fill_color = REGIME_TINTS.get(regime, REGIME_TINTS["UNCERTAIN"])
    border_color = REGIME_COLORS.get(regime, REGIME_COLORS["UNCERTAIN"])

    fig.add_vrect(
        x0=x0,
        x1=x1,
        fillcolor=fill_color,
        line={"color": border_color, "width": 0.5},
        layer="below",
        row=row,
        col=col,
    )


def render_daily_pnl_chart(
    trades_df: pd.DataFrame,
    *,
    height: int = 250,
    chart_key: str | None = None,
    max_days: int | None = None,
) -> None:
    """Render a daily PnL bar chart from close trades.

    Parameters
    ----------
    trades_df:
        DataFrame of trades with at least ``timestamp`` and ``pnl`` columns.
    height:
        Chart height in pixels (default 250).
    chart_key:
        Optional Streamlit element key for deduplication.
    max_days:
        If set, only show the most recent *max_days* days.
    """
    if trades_df.empty:
        st.caption("No close trades for daily PnL chart.")
        return

    df = trades_df.copy()
    if "timestamp" not in df.columns:
        st.caption("No timestamp column for daily PnL chart.")
        return

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily = (
        df.groupby("date")["pnl"].sum().reset_index()
        if "pnl" in df.columns
        else pd.DataFrame()
    )

    if daily.empty:
        st.caption("No PnL data for daily chart.")
        return

    daily.columns = ["date", "pnl"]
    daily = daily.sort_values("date").reset_index(drop=True)
    if max_days is not None and len(daily) > max_days:
        daily = daily.tail(max_days).reset_index(drop=True)
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
            height=height,
            yaxis={"title": "PnL ($)"},
            xaxis={"title": ""},
            showlegend=False,
        )
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key)
