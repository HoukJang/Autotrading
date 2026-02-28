"""Position panel component for the live trading dashboard (Tab 3).

Renders open position cards with SL/TP levels, MFE/MAE, days held,
and day-skip status. Also shows recent trades and daily PnL chart.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from autotrader.dashboard.theme import COLORS, STRATEGY_COLORS, STRATEGY_NAMES
from autotrader.dashboard.utils.chart_helpers import get_chart_layout
from autotrader.dashboard.utils.formatters import fmt_currency, fmt_pnl, fmt_pct


def render_position_panel(data) -> None:
    """Render the current open positions panel (compact sidebar view).

    Parameters
    ----------
    data:
        A DashboardData instance with ``current_positions`` (list of
        symbol strings) and ``trades_df`` (trade history DataFrame).
    """
    positions = getattr(data, "current_positions", [])
    trades_df = getattr(data, "trades_df", None)
    pos_count = len(positions) if positions else 0

    st.subheader(f"Open Positions ({pos_count} / 8)")

    if not positions:
        _render_empty_state(trades_df)
        return

    for symbol in positions:
        _render_position_card(symbol, trades_df)


def render_positions_tab(data) -> None:
    """Render the full Positions and Trades tab (Tab 3).

    Includes open positions table with SL/TP details, recent trades
    table with exit reasons, and a daily PnL bar chart.

    Parameters
    ----------
    data:
        A DashboardData instance.
    """
    positions = getattr(data, "current_positions", [])
    trades_df = getattr(data, "trades_df", None)

    # -- Open Positions Table -----------------------------------------------
    st.subheader(f"Open Positions ({len(positions)} / 8)")

    if not positions:
        st.info("No open positions currently.")
    else:
        _render_open_positions_table(positions, trades_df)

    st.divider()

    # -- Recent Trades Table ------------------------------------------------
    st.subheader("Recent Trades (Last 50)")
    if trades_df is None or trades_df.empty:
        st.info("No trades recorded yet.")
    else:
        _render_recent_trades_table(trades_df)

    st.divider()

    # -- Daily PnL Bar Chart ------------------------------------------------
    st.subheader("Daily PnL")
    if trades_df is not None and not trades_df.empty:
        _render_daily_pnl_chart(trades_df)
    else:
        st.info("No trade data for daily PnL chart.")


# ---------------------------------------------------------------------------
# Open positions table (detailed)
# ---------------------------------------------------------------------------

def _render_open_positions_table(
    positions: list[str],
    trades_df: pd.DataFrame | None,
) -> None:
    """Render a detailed DataFrame table of open positions."""
    rows = []
    today = date.today()

    for symbol in positions:
        row = _extract_position_row(symbol, trades_df, today)
        rows.append(row)

    if not rows:
        st.info("No position data available.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.apply(_style_position_table, axis=1),
        use_container_width=True,
        hide_index=True,
    )


def _extract_position_row(
    symbol: str,
    trades_df: pd.DataFrame | None,
    today: date,
) -> dict:
    """Extract a single position row dict for the positions table."""
    strategy = "--"
    direction = "--"
    entry_price = None
    bars_held = 0
    sl_price = None
    tp_price = None
    mfe = None
    mae = None
    entry_date = None

    if trades_df is not None and not trades_df.empty:
        if "symbol" in trades_df.columns:
            sym_trades = trades_df[trades_df["symbol"] == symbol]
        else:
            sym_trades = trades_df.iloc[0:0]

        if not sym_trades.empty:
            if "side" in sym_trades.columns:
                entries = sym_trades[sym_trades["side"] == "entry"]
            else:
                entries = sym_trades

            if not entries.empty:
                if "timestamp" in entries.columns:
                    latest_entry = entries.sort_values("timestamp", ascending=False).iloc[0]
                else:
                    latest_entry = entries.iloc[-1]

                strategy = STRATEGY_NAMES.get(
                    str(latest_entry.get("strategy", "") if hasattr(latest_entry, "get") else latest_entry["strategy"] if "strategy" in entries.columns else ""),
                    "--",
                )

                if "direction" in entries.columns:
                    direction = str(latest_entry["direction"])

                if "price" in entries.columns:
                    entry_price = float(latest_entry["price"])
                elif "entry_price" in entries.columns:
                    entry_price = float(latest_entry["entry_price"])

                if "bars_held" in entries.columns:
                    try:
                        bars_held = int(latest_entry["bars_held"])
                    except (ValueError, TypeError):
                        bars_held = 0

                if "timestamp" in entries.columns:
                    ts = latest_entry["timestamp"]
                    if hasattr(ts, "date"):
                        entry_date = ts.date()

                # Extract SL/TP from metadata if available
                meta = latest_entry.get("metadata") if hasattr(latest_entry, "get") else (latest_entry["metadata"] if "metadata" in entries.columns else None)
                if isinstance(meta, dict):
                    sl_price = meta.get("stop_loss") or meta.get("sl_price")
                    tp_price = meta.get("take_profit") or meta.get("tp_price")
                elif isinstance(meta, str):
                    import json
                    try:
                        meta_dict = json.loads(meta)
                        sl_price = meta_dict.get("stop_loss") or meta_dict.get("sl_price")
                        tp_price = meta_dict.get("take_profit") or meta_dict.get("tp_price")
                    except (json.JSONDecodeError, TypeError):
                        pass

                if "mfe" in entries.columns:
                    try:
                        mfe = float(latest_entry["mfe"])
                    except (ValueError, TypeError):
                        pass

                if "mae" in entries.columns:
                    try:
                        mae = float(latest_entry["mae"])
                    except (ValueError, TypeError):
                        pass

    # Day-skip protection: Day 1 is protected (SL/TP not active until Day 2)
    days_held = 0
    if entry_date is not None:
        days_held = (today - entry_date).days

    day_skip_status = "Protected (Day 1)" if days_held == 0 else f"Active SL/TP (Day {days_held + 1})"

    return {
        "Symbol": symbol,
        "Strategy": strategy,
        "Dir": direction.upper()[:1] if direction != "--" else "--",
        "Entry": f"${entry_price:,.2f}" if entry_price is not None else "--",
        "SL": f"${sl_price:,.2f}" if sl_price is not None else "--",
        "TP": f"${tp_price:,.2f}" if tp_price is not None else "--",
        "Days": days_held,
        "Bars Held": bars_held,
        "MFE": f"+${mfe:,.2f}" if mfe is not None else "--",
        "MAE": f"-${abs(mae):,.2f}" if mae is not None else "--",
        "Status": day_skip_status,
    }


def _style_position_table(row: pd.Series) -> list[str]:
    """Apply row-level styling to position table."""
    styles = [""] * len(row)
    if "Dir" in row.index:
        dir_idx = row.index.get_loc("Dir")
        if row["Dir"] == "L":
            styles[dir_idx] = f"color: {COLORS['profit']}; font-weight: bold"
        elif row["Dir"] == "S":
            styles[dir_idx] = f"color: {COLORS['loss']}; font-weight: bold"
    return styles


# ---------------------------------------------------------------------------
# Recent trades table
# ---------------------------------------------------------------------------

_RECENT_TRADE_COLS = [
    "timestamp", "symbol", "strategy", "direction",
    "price", "pnl", "exit_reason", "bars_held",
]


def _render_recent_trades_table(trades_df: pd.DataFrame) -> None:
    """Render the last 50 closed trades."""
    df = trades_df.copy()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp", ascending=False)

    # Filter to close/exit trades only where possible
    if "side" in df.columns:
        close_df = df[df["side"] == "exit"].head(50)
    elif "direction" in df.columns:
        close_df = df[df["direction"] == "close"].head(50)
    else:
        close_df = df.head(50)

    if close_df.empty:
        st.caption("No closed trades yet.")
        return

    display_cols = [c for c in _RECENT_TRADE_COLS if c in close_df.columns]
    display = close_df[display_cols].reset_index(drop=True)

    if "strategy" in display.columns:
        display["strategy"] = display["strategy"].map(
            lambda s: STRATEGY_NAMES.get(str(s), str(s))
        )

    def _style_pnl(val):
        try:
            num = float(val)
        except (TypeError, ValueError):
            return ""
        if num > 0:
            return f"color: {COLORS['profit']}"
        if num < 0:
            return f"color: {COLORS['loss']}"
        return f"color: {COLORS['neutral']}"

    pnl_cols = [c for c in ("pnl",) if c in display.columns]
    if pnl_cols:
        st.dataframe(
            display.style.map(_style_pnl, subset=pnl_cols),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.dataframe(display, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Daily PnL chart
# ---------------------------------------------------------------------------

def _render_daily_pnl_chart(trades_df: pd.DataFrame) -> None:
    """Render a daily PnL bar chart."""
    df = trades_df.copy()

    if "timestamp" not in df.columns:
        st.caption("No timestamp column for daily PnL chart.")
        return

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily = df.groupby("date")["pnl"].sum().reset_index() if "pnl" in df.columns else pd.DataFrame()

    if daily.empty:
        st.caption("No PnL data for daily chart.")
        return

    bar_colors = [
        COLORS["profit"] if v >= 0 else COLORS["loss"]
        for v in daily["pnl"]
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
            height=280,
            yaxis={"title": "PnL ($)"},
            xaxis={"title": ""},
            showlegend=False,
        )
    )
    st.plotly_chart(fig, use_container_width=True, key="daily_pnl_positions")


# ---------------------------------------------------------------------------
# Sidebar compact card
# ---------------------------------------------------------------------------

def _render_empty_state(trades_df) -> None:
    """Render the empty positions placeholder."""
    active_count = 0
    if trades_df is not None and not trades_df.empty and "symbol" in trades_df.columns:
        active_count = trades_df["symbol"].nunique()

    universe_text = (
        f"Active universe: {active_count} symbols"
        if active_count > 0
        else "Active universe: --"
    )

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['bg_section']};
            border-radius: 8px;
            padding: 32px 24px;
            text-align: center;
        ">
            <div style="
                color: {COLORS['text_secondary']};
                font-size: 1.05em;
                font-weight: 600;
                margin-bottom: 8px;
            ">No open positions</div>
            <div style="
                color: {COLORS['text_muted']};
                font-size: 0.9em;
                margin-bottom: 4px;
            ">Waiting for batch scan entries...</div>
            <div style="
                color: {COLORS['text_muted']};
                font-size: 0.85em;
            ">{universe_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_position_card(symbol: str, trades_df) -> None:
    """Render a single compact position card for the sidebar panel."""
    strategy = "--"
    strategy_key = ""
    direction = "--"
    entry_price = None
    bars_held = None
    pnl = None
    sl_price = None
    tp_price = None

    if trades_df is not None and not trades_df.empty:
        sym_trades = (
            trades_df[trades_df["symbol"] == symbol]
            if "symbol" in trades_df.columns
            else trades_df.iloc[0:0]
        )

        if not sym_trades.empty:
            if "side" in sym_trades.columns:
                entries = sym_trades[sym_trades["side"] == "entry"]
            elif "direction" in sym_trades.columns:
                entries = sym_trades[sym_trades["direction"].isin(["long", "short"])]
            else:
                entries = sym_trades

            if not entries.empty:
                if "timestamp" in entries.columns:
                    latest_entry = entries.sort_values("timestamp", ascending=False).iloc[0]
                else:
                    latest_entry = entries.iloc[-1]

                strategy_key = (
                    str(latest_entry.get("strategy", ""))
                    if hasattr(latest_entry, "get")
                    else (
                        str(latest_entry["strategy"])
                        if "strategy" in entries.columns
                        else ""
                    )
                )
                strategy = STRATEGY_NAMES.get(strategy_key, strategy_key or "--")

                if "direction" in entries.columns:
                    direction = str(latest_entry["direction"])

                if "price" in entries.columns:
                    entry_price = float(latest_entry["price"])
                elif "entry_price" in entries.columns:
                    entry_price = float(latest_entry["entry_price"])

                if "bars_held" in entries.columns:
                    try:
                        bars_held = int(latest_entry["bars_held"])
                    except (ValueError, TypeError):
                        bars_held = None

                # SL/TP from metadata
                meta = (
                    latest_entry.get("metadata")
                    if hasattr(latest_entry, "get")
                    else (
                        latest_entry["metadata"]
                        if "metadata" in entries.columns
                        else None
                    )
                )
                if isinstance(meta, dict):
                    sl_price = meta.get("stop_loss") or meta.get("sl_price")
                    tp_price = meta.get("take_profit") or meta.get("tp_price")

            if "pnl" in sym_trades.columns:
                last_trade = sym_trades.iloc[-1]
                last_pnl = last_trade["pnl"]
                if last_pnl is not None and last_pnl != 0:
                    pnl = float(last_pnl)

    strat_color = STRATEGY_COLORS.get(strategy_key, COLORS["text_muted"])
    dir_short = "S" if direction.lower() == "short" else "L"
    dir_bg = COLORS["loss"] if direction.lower() == "short" else COLORS["profit"]

    price_text = f"${entry_price:,.2f}" if entry_price is not None else "--"
    bars_text = f"{bars_held}d" if bars_held is not None else "--"
    sl_text = f"SL ${sl_price:,.2f}" if sl_price is not None else ""
    tp_text = f"TP ${tp_price:,.2f}" if tp_price is not None else ""
    level_text = " | ".join(filter(None, [sl_text, tp_text])) or "--"

    pnl_html = ""
    if pnl is not None:
        pnl_color = COLORS["profit"] if pnl >= 0 else COLORS["loss"]
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_html = (
            f'<span style="color:{pnl_color};font-size:0.9em;font-weight:600">'
            f"{pnl_sign}${pnl:,.2f}</span>"
        )

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border-left: 3px solid {strat_color};
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 8px;
        ">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="color:{COLORS['text_primary']};font-size:1.05em;font-weight:700">{symbol}</span>
                    <span style="
                        background-color:{dir_bg}22;color:{dir_bg};
                        font-size:0.75em;font-weight:700;
                        padding:2px 6px;border-radius:4px">{dir_short}</span>
                </div>
                {pnl_html}
            </div>
            <div style="color:{COLORS['text_secondary']};font-size:0.82em;margin-bottom:3px">{strategy}</div>
            <div style="display:flex;gap:12px;color:{COLORS['text_muted']};font-size:0.80em">
                <span>Entry: {price_text}</span>
                <span>Held: {bars_text}</span>
            </div>
            <div style="color:{COLORS['text_muted']};font-size:0.78em;margin-top:2px">{level_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
