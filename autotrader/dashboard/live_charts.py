"""Plotly chart functions for the live trading dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

# Consistent color scheme
GREEN = "#2ecc71"
RED = "#e74c3c"
BLUE = "#3498db"
PURPLE = "#8e44ad"
ORANGE = "#e67e22"
GRAY = "#95a5a6"

# Regime color mapping
REGIME_COLORS = {
    "TREND": GREEN,
    "RANGING": BLUE,
    "HIGH_VOLATILITY": RED,
    "UNCERTAIN": GRAY,
}

# Regime background tint mapping (semi-transparent for bands)
REGIME_TINTS = {
    "TREND": "rgba(46, 204, 113, 0.10)",
    "RANGING": "rgba(52, 152, 219, 0.10)",
    "HIGH_VOLATILITY": "rgba(231, 76, 60, 0.10)",
    "UNCERTAIN": "rgba(149, 165, 166, 0.10)",
}


def live_equity_curve(equity_df: pd.DataFrame) -> go.Figure:
    """Equity curve over time with regime color bands.

    Parameters
    ----------
    equity_df : pd.DataFrame
        Columns: timestamp, equity, cash, regime
    """
    fig = go.Figure()
    if equity_df.empty:
        return fig

    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=equity_df["equity"],
        mode="lines",
        name="Equity",
        line=dict(color=BLUE, width=2),
    ))

    # Add regime color bands as vrect shapes
    if "regime" in equity_df.columns:
        regimes = equity_df["regime"].values
        timestamps = equity_df["timestamp"].values
        i = 0
        while i < len(regimes):
            current_regime = regimes[i]
            start_idx = i
            while i < len(regimes) and regimes[i] == current_regime:
                i += 1
            end_idx = i - 1
            tint = REGIME_TINTS.get(str(current_regime), REGIME_TINTS["UNCERTAIN"])
            fig.add_vrect(
                x0=timestamps[start_idx],
                x1=timestamps[end_idx],
                fillcolor=tint,
                layer="below",
                line_width=0,
            )

    fig.update_layout(
        title="Live Equity Curve",
        xaxis_title="Time",
        yaxis_title="Equity ($)",
        hovermode="x unified",
        height=400,
    )
    return fig


def live_drawdown_chart(equity_df: pd.DataFrame) -> go.Figure:
    """Drawdown percentage chart from equity curve.

    Parameters
    ----------
    equity_df : pd.DataFrame
        Columns: timestamp, equity
    """
    fig = go.Figure()
    if equity_df.empty:
        return fig

    equity = equity_df["equity"]
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak

    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=drawdown,
        mode="lines",
        fill="tozeroy",
        line=dict(color=RED),
        fillcolor="rgba(231, 76, 60, 0.3)",
        name="Drawdown",
    ))

    fig.update_layout(
        title="Drawdown",
        xaxis_title="Time",
        yaxis_title="Drawdown (%)",
        yaxis_tickformat=".1%",
        hovermode="x unified",
        height=250,
    )
    return fig


def live_pnl_by_strategy(trades_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart: total PnL per strategy.

    Parameters
    ----------
    trades_df : pd.DataFrame
        Columns: strategy, pnl
    """
    if trades_df.empty:
        return go.Figure()

    grouped = trades_df.groupby("strategy")["pnl"].sum().sort_values()
    colors = [GREEN if p >= 0 else RED for p in grouped.values]

    fig = go.Figure(go.Bar(
        x=grouped.values,
        y=grouped.index.tolist(),
        orientation="h",
        marker_color=colors,
        text=[f"${p:+,.2f}" for p in grouped.values],
        textposition="outside",
    ))
    fig.update_layout(
        title="PnL by Strategy",
        xaxis_title="Total PnL ($)",
        height=350,
    )
    return fig


def live_trade_timeline(trades_df: pd.DataFrame) -> go.Figure:
    """Scatter chart showing trades over time.

    Parameters
    ----------
    trades_df : pd.DataFrame
        Columns: timestamp, pnl, symbol, strategy, direction
    """
    if trades_df.empty:
        return go.Figure()

    direction_colors = {
        "long": GREEN,
        "short": RED,
        "close": GRAY,
    }

    fig = go.Figure()
    for direction in trades_df["direction"].unique():
        subset = trades_df[trades_df["direction"] == direction]
        color = direction_colors.get(str(direction).lower(), GRAY)
        sizes = subset["pnl"].abs()
        max_pnl = sizes.max() if sizes.max() > 0 else 1.0
        marker_sizes = (sizes / max_pnl * 20).clip(lower=5)

        fig.add_trace(go.Scatter(
            x=subset["timestamp"],
            y=subset["pnl"],
            mode="markers",
            name=str(direction),
            marker=dict(color=color, size=marker_sizes),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Strategy: %{customdata[1]}<br>"
                "PnL: $%{y:+,.2f}<extra></extra>"
            ),
            customdata=subset[["symbol", "strategy"]].values,
        ))

    fig.update_layout(
        title="Trade Timeline",
        xaxis_title="Time",
        yaxis_title="PnL ($)",
        hovermode="closest",
        height=350,
    )
    return fig


def live_regime_pie(equity_df: pd.DataFrame) -> go.Figure:
    """Pie chart of time spent in each regime.

    Parameters
    ----------
    equity_df : pd.DataFrame
        Columns: regime
    """
    if equity_df.empty:
        return go.Figure()

    counts = equity_df["regime"].value_counts()
    colors = [REGIME_COLORS.get(str(r), GRAY) for r in counts.index]

    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.4,
        marker=dict(colors=colors),
        textinfo="label+percent",
    ))
    fig.update_layout(title="Regime Distribution", height=300)
    return fig


def live_win_rate_gauge(win_rate: float) -> go.Figure:
    """Gauge chart showing win rate (0-100%).

    Parameters
    ----------
    win_rate : float
        Win rate as a fraction (0.0 to 1.0).
    """
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=win_rate * 100,
        number=dict(suffix="%"),
        title=dict(text="Win Rate"),
        gauge=dict(
            axis=dict(range=[0, 100]),
            bar=dict(color=BLUE),
            steps=[
                dict(range=[0, 30], color="rgba(231, 76, 60, 0.3)"),
                dict(range=[30, 50], color="rgba(230, 126, 34, 0.3)"),
                dict(range=[50, 100], color="rgba(46, 204, 113, 0.3)"),
            ],
            threshold=dict(
                line=dict(color=RED, width=2),
                thickness=0.75,
                value=50,
            ),
        ),
    ))
    fig.update_layout(height=250)
    return fig


def live_cumulative_pnl(trades_df: pd.DataFrame) -> go.Figure:
    """Cumulative PnL over time.

    Parameters
    ----------
    trades_df : pd.DataFrame
        Columns: timestamp, pnl
    """
    if trades_df.empty:
        return go.Figure()

    sorted_df = trades_df.sort_values("timestamp")
    cum_pnl = sorted_df["pnl"].cumsum()

    fig = go.Figure(go.Scatter(
        x=sorted_df["timestamp"],
        y=cum_pnl,
        mode="lines+markers",
        line=dict(color=PURPLE),
        name="Cumulative PnL",
    ))
    fig.update_layout(
        title="Cumulative PnL Over Time",
        xaxis_title="Time",
        yaxis_title="Cumulative PnL ($)",
        height=350,
    )
    return fig


def live_pnl_by_symbol(trades_df: pd.DataFrame) -> go.Figure:
    """Bar chart: total PnL per symbol.

    Parameters
    ----------
    trades_df : pd.DataFrame
        Columns: symbol, pnl
    """
    if trades_df.empty:
        return go.Figure()

    grouped = trades_df.groupby("symbol")["pnl"].sum().sort_values(ascending=False)
    colors = [GREEN if p >= 0 else RED for p in grouped.values]

    fig = go.Figure(go.Bar(
        x=grouped.index.tolist(),
        y=grouped.values,
        marker_color=colors,
        text=[f"${p:+,.2f}" for p in grouped.values],
        textposition="outside",
    ))
    fig.update_layout(
        title="PnL by Symbol",
        yaxis_title="Total PnL ($)",
        height=350,
    )
    return fig


def live_position_summary_table(positions_df: pd.DataFrame) -> go.Figure:
    """Table showing current open positions.

    Parameters
    ----------
    positions_df : pd.DataFrame
        Columns: symbol, side, quantity, avg_entry_price, unrealized_pnl
    """
    if positions_df.empty:
        fig = go.Figure(go.Table(
            header=dict(
                values=["Symbol", "Side", "Qty", "Avg Entry", "Unrealized PnL"],
                fill_color="#2c3e50",
                font=dict(color="white"),
                align="center",
            ),
            cells=dict(
                values=[[], [], [], [], []],
                align="center",
            ),
        ))
        fig.update_layout(title="Open Positions", height=300)
        return fig

    pnl_colors = [GREEN if v >= 0 else RED for v in positions_df["unrealized_pnl"]]
    # Build cell font colors: default dark for all columns, colored for PnL column
    n_rows = len(positions_df)
    default_color = "#2c3e50"
    font_colors = [
        [default_color] * n_rows,  # symbol
        [default_color] * n_rows,  # side
        [default_color] * n_rows,  # quantity
        [default_color] * n_rows,  # avg_entry_price
        pnl_colors,                # unrealized_pnl
    ]

    fig = go.Figure(go.Table(
        header=dict(
            values=["Symbol", "Side", "Qty", "Avg Entry", "Unrealized PnL"],
            fill_color="#2c3e50",
            font=dict(color="white"),
            align="center",
        ),
        cells=dict(
            values=[
                positions_df["symbol"].tolist(),
                positions_df["side"].tolist(),
                positions_df["quantity"].tolist(),
                [f"${p:,.2f}" for p in positions_df["avg_entry_price"]],
                [f"${p:+,.2f}" for p in positions_df["unrealized_pnl"]],
            ],
            font=dict(color=font_colors),
            align="center",
        ),
    ))
    fig.update_layout(title="Open Positions", height=300)
    return fig
