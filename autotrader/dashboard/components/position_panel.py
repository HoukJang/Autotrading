"""Position panel component for the live trading dashboard (Tab 3).

Renders open position cards with unified dollar+percent format for
P&L, MFE, MAE, SL/TP levels, and days held.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

import plotly.graph_objects as go

from autotrader.dashboard.data_loader import load_open_positions
from autotrader.dashboard.theme import COLORS, EXIT_REASON_LABELS, STRATEGY_COLORS, STRATEGY_NAMES
from autotrader.dashboard.utils.chart_helpers import get_chart_layout
from autotrader.dashboard.utils.formatters import style_pnl
from autotrader.trading.constants import SL_ATR_MULT, TP_ATR_MULT


# ---------------------------------------------------------------------------
# Consolidated position data structure
# ---------------------------------------------------------------------------

@dataclass
class PositionDisplayData:
    """Consolidated position data from all sources."""
    symbol: str
    strategy: str = "--"
    strategy_key: str = ""
    direction: str = "--"
    entry_price: float | None = None
    current_price: float | None = None
    quantity: int | None = None
    sl_price: float | None = None
    tp_price: float | None = None
    entry_date: date | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    mfe_dollar: float | None = None
    mfe_pct: float | None = None
    mae_dollar: float | None = None
    mae_pct: float | None = None
    days_held: int = 0
    pos_value: float | None = None
    sl_dist_pct: float | None = None
    tp_dist_pct: float | None = None
    r_multiple: float | None = None


# ---------------------------------------------------------------------------
# Unified formatting helpers
# ---------------------------------------------------------------------------

def _fmt_dollar_pct(dollar: float | None, pct: float | None) -> str:
    """Format as '+$123 (+1.6%)' with consistent sign."""
    if dollar is None or pct is None:
        return "--"
    if dollar == 0 and pct == 0:
        return "+$0 (+0.0%)"
    sign = "+" if dollar >= 0 else ""
    return f"{sign}${dollar:,.0f} ({sign}{pct * 100:.1f}%)"


def _fmt_price(price: float | None) -> str:
    if price is None:
        return "--"
    return f"${price:,.2f}"


# ---------------------------------------------------------------------------
# Fallback price loader
# ---------------------------------------------------------------------------

def _load_fallback_prices() -> dict[str, float]:
    """Load prev_close prices from batch_results.json as fallback.

    Returns {symbol: prev_close} for all candidates in the latest scan.
    Used when open_positions.json is empty (process not running).
    """
    try:
        import json as _json
        from pathlib import Path

        path = Path("data/batch_results.json")
        if not path.exists():
            return {}
        raw = _json.loads(path.read_text(encoding="utf-8"))
        prices: dict[str, float] = {}
        for c in raw.get("candidates", []):
            sym = c.get("symbol", "")
            pc = c.get("prev_close")
            if sym and pc and pc > 0:
                prices[sym] = float(pc)
        return prices
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Consolidated position data extraction (single source of truth)
# ---------------------------------------------------------------------------

def _extract_position_data(
    symbol: str,
    trades_df: pd.DataFrame | None,
    live: dict | None = None,
    fallback_prices: dict[str, float] | None = None,
) -> PositionDisplayData:
    """Extract and consolidate position data from trades_df and live tracker.

    This is the single source of truth for position data extraction,
    used by both the table view and the card view.

    Args:
        fallback_prices: {symbol: prev_close} from batch_results.json,
            used when live tracker is unavailable.
    """
    data = PositionDisplayData(symbol=symbol)

    # --- Phase 1: Extract from trades_df ---
    if trades_df is not None and not trades_df.empty:
        if "symbol" in trades_df.columns:
            sym_trades = trades_df[trades_df["symbol"] == symbol]
        else:
            sym_trades = trades_df.iloc[0:0]

        if not sym_trades.empty:
            if "side" in sym_trades.columns:
                entries = sym_trades[sym_trades["side"].isin(["entry", "reconciliation_entry"])]
            elif "direction" in sym_trades.columns:
                entries = sym_trades[sym_trades["direction"].isin(["long", "short"])]
            else:
                entries = sym_trades

            if not entries.empty:
                if "timestamp" in entries.columns:
                    latest_entry = entries.sort_values(
                        "timestamp", ascending=False
                    ).iloc[0]
                else:
                    latest_entry = entries.iloc[-1]

                data.strategy_key = str(
                    latest_entry.get("strategy", "")
                    if hasattr(latest_entry, "get")
                    else (
                        latest_entry["strategy"]
                        if "strategy" in entries.columns
                        else ""
                    )
                )
                data.strategy = STRATEGY_NAMES.get(
                    data.strategy_key, data.strategy_key or "--"
                )

                if "direction" in entries.columns:
                    data.direction = str(latest_entry["direction"])

                if "price" in entries.columns:
                    data.entry_price = float(latest_entry["price"])
                elif "entry_price" in entries.columns:
                    data.entry_price = float(latest_entry["entry_price"])

                if "quantity" in entries.columns:
                    try:
                        data.quantity = int(float(latest_entry["quantity"]))
                    except (ValueError, TypeError):
                        pass

                if "timestamp" in entries.columns:
                    ts = latest_entry["timestamp"]
                    if hasattr(ts, "date"):
                        data.entry_date = ts.date()

                # Extract SL/TP from metadata
                meta = (
                    latest_entry.get("metadata")
                    if hasattr(latest_entry, "get")
                    else (
                        latest_entry["metadata"]
                        if "metadata" in entries.columns
                        else None
                    )
                )
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = None
                if isinstance(meta, dict):
                    data.sl_price = meta.get("stop_loss") or meta.get("sl_price")
                    data.tp_price = meta.get("take_profit") or meta.get("tp_price")

                    dir_key = (
                        data.direction.lower()
                        if data.direction != "--"
                        else "long"
                    )

                    if data.sl_price is None and data.entry_price is not None:
                        atr = meta.get("entry_atr", 0)
                        if atr and atr > 0:
                            sl_mult = SL_ATR_MULT.get(
                                data.strategy_key, {}
                            ).get(dir_key, 2.0)
                            if dir_key == "long":
                                data.sl_price = round(
                                    data.entry_price - sl_mult * atr, 2
                                )
                            else:
                                data.sl_price = round(
                                    data.entry_price + sl_mult * atr, 2
                                )

                    if data.tp_price is None and data.entry_price is not None:
                        atr = meta.get("entry_atr", 0)
                        if atr and atr > 0:
                            tp_mult = TP_ATR_MULT.get(data.strategy_key)
                            if tp_mult:
                                if dir_key == "long":
                                    data.tp_price = round(
                                        data.entry_price + tp_mult * atr, 2
                                    )
                                else:
                                    data.tp_price = round(
                                        data.entry_price - tp_mult * atr, 2
                                    )

    # --- Phase 2: Override with live tracker data ---
    if live is not None:
        if data.quantity is None:
            data.quantity = int(live.get("qty", 0)) or None
        if data.entry_price is None:
            data.entry_price = live.get("entry_price")
        if data.direction == "--":
            data.direction = live.get("direction", "--")
        data.current_price = live.get("current_price")
        data.unrealized_pnl = live.get("unrealized_pnl")
        data.unrealized_pnl_pct = live.get("unrealized_pnl_pct")
        data.mfe_dollar = live.get("mfe_dollar", 0.0)
        data.mfe_pct = live.get("mfe_pct", 0.0)
        data.mae_dollar = live.get("mae_dollar", 0.0)
        data.mae_pct = live.get("mae_pct", 0.0)

        if data.entry_date is None:
            entry_date_str = live.get("entry_date_et", "")
            if entry_date_str:
                try:
                    data.entry_date = date.fromisoformat(entry_date_str)
                except ValueError:
                    pass
    else:
        # Fallback: use batch_results prev_close or entry_price
        fb_price = (fallback_prices or {}).get(symbol)
        if fb_price and fb_price > 0:
            data.current_price = fb_price
        elif data.current_price is None and data.entry_price is not None:
            data.current_price = data.entry_price

        # Compute P&L from available prices
        if (
            data.entry_price is not None
            and data.current_price is not None
            and data.quantity is not None
        ):
            dir_lower = data.direction.lower() if data.direction != "--" else "long"
            if dir_lower == "long":
                pnl = (data.current_price - data.entry_price) * data.quantity
            else:
                pnl = (data.entry_price - data.current_price) * data.quantity
            cost = data.entry_price * data.quantity
            pnl_pct = pnl / cost if cost > 0 else 0.0
            data.unrealized_pnl = round(pnl, 2)
            data.unrealized_pnl_pct = round(pnl_pct, 4)
            # MFE/MAE unavailable without tracker
            data.mfe_dollar = 0.0
            data.mfe_pct = 0.0
            data.mae_dollar = 0.0
            data.mae_pct = 0.0

    # --- Phase 3: Compute derived fields ---
    today = date.today()

    if data.entry_date is not None:
        data.days_held = (today - data.entry_date).days

    if data.quantity is not None and data.entry_price is not None:
        data.pos_value = data.quantity * data.entry_price

    if data.current_price and data.current_price > 0:
        dir_lower = data.direction.lower() if data.direction != "--" else "long"
        if data.sl_price is not None:
            if dir_lower == "long":
                data.sl_dist_pct = (
                    data.current_price - data.sl_price
                ) / data.current_price
            else:
                data.sl_dist_pct = (
                    data.sl_price - data.current_price
                ) / data.current_price
        if data.tp_price is not None:
            if dir_lower == "long":
                data.tp_dist_pct = (
                    data.tp_price - data.current_price
                ) / data.current_price
            else:
                data.tp_dist_pct = (
                    data.current_price - data.tp_price
                ) / data.current_price

    if (
        data.unrealized_pnl is not None
        and data.sl_price is not None
        and data.entry_price is not None
        and data.quantity
    ):
        risk_per_share = abs(data.entry_price - data.sl_price)
        total_risk = risk_per_share * abs(data.quantity)
        if total_risk > 0:
            data.r_multiple = data.unrealized_pnl / total_risk

    return data


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_position_panel(data) -> None:
    """Render the current open positions panel (compact sidebar view)."""
    positions = getattr(data, "current_positions", [])
    trades_df = getattr(data, "trades_df", None)
    pos_count = len(positions) if positions else 0

    st.subheader(f"Open Positions ({pos_count} / 8)")

    if not positions:
        _render_empty_state(trades_df)
        return

    live_pos = load_open_positions()
    fallback_prices = _load_fallback_prices() if not live_pos else {}
    for symbol in positions:
        _render_position_card(
            symbol, trades_df, live_pos.get(symbol), fallback_prices,
        )


def render_positions_tab(data) -> None:
    """Render the full Positions and Trades tab (Tab 3)."""
    positions = getattr(data, "current_positions", [])
    trades_df = getattr(data, "trades_df", None)

    # -- Open Positions Table -----------------------------------------------
    st.subheader(f"Open Positions ({len(positions)} / 8)")

    if not positions:
        st.info("No open positions right now. Positions appear when the nightly scan finds opportunities.")
    else:
        _render_open_positions_table(positions, trades_df)

    st.divider()

    # -- Trade View Toggle ------------------------------------------------
    view_mode = st.radio(
        "Trade View", ["Log View", "Round-trip View"],
        horizontal=True, key="trade_view_mode",
    )
    if trades_df is None or trades_df.empty:
        st.info("No trades recorded yet. Trade history builds as the system opens and closes positions.")
    elif view_mode == "Log View":
        st.subheader("Recent Trades (Last 50)")
        _render_recent_trades_table(trades_df)
    else:
        st.subheader("Round-trip Trades")
        _render_roundtrip_view(trades_df)

    st.divider()

    # -- Daily PnL Bar Chart ------------------------------------------------
    st.subheader("Daily PnL (Realized + Unrealized)")
    _render_daily_pnl_with_unrealized(trades_df, current_positions=positions)


# ---------------------------------------------------------------------------
# Open positions table (detailed)
# ---------------------------------------------------------------------------

def _render_open_positions_table(
    positions: list[str],
    trades_df: pd.DataFrame | None,
) -> None:
    """Render a detailed DataFrame table of open positions.

    Provides a toggle between a simplified 8-column basic view and the
    full 17-column detail view.
    """
    live_pos = load_open_positions()
    fallback_prices = _load_fallback_prices()
    rows = []
    today = date.today()

    for symbol in positions:
        row = _extract_position_row(
            symbol, trades_df, today, live_pos.get(symbol), fallback_prices,
        )
        rows.append(row)

    if not rows:
        st.info("No position data available.")
        return

    df = pd.DataFrame(rows)

    # Rename columns for beginner-friendliness
    col_rename = {
        "Dir": "Direction",
        "SL Dist": "Stop Distance",
        "MFE": "Best P&L",
        "MAE": "Worst P&L",
        "R": "R-Multiple",
    }
    df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})

    # Expand direction abbreviations: "L" -> "Long", "S" -> "Short"
    if "Direction" in df.columns:
        dir_map = {"L": "Long", "S": "Short"}
        df["Direction"] = df["Direction"].map(lambda v: dir_map.get(v, v))

    # Toggle between basic and detail view
    show_details = st.toggle(
        "Show all columns", value=False, key="pos_detail_toggle",
    )

    basic_cols = [
        "Symbol", "Strategy", "Direction", "Entry", "Current",
        "P&L", "Days", "Status",
    ]
    basic_cols = [c for c in basic_cols if c in df.columns]

    display_df = df if show_details else df[basic_cols]

    st.dataframe(
        display_df.style.apply(
            _style_position_table, axis=1, renamed=True,
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Legend
    if show_details:
        st.caption(
            "P&L = unrealized profit/loss | "
            "Best P&L = max favorable excursion (best unrealized) | "
            "Worst P&L = max adverse excursion (worst unrealized)"
        )


def _extract_position_row(
    symbol: str,
    trades_df: pd.DataFrame | None,
    today: date,
    live: dict | None = None,
    fallback_prices: dict[str, float] | None = None,
) -> dict:
    """Extract a single position row dict for the positions table.

    Delegates data extraction to _extract_position_data() and formats
    the result as a flat dict suitable for DataFrame rendering.
    """
    data = _extract_position_data(symbol, trades_df, live, fallback_prices)

    # Determine data completeness status
    is_ghost = data.strategy == "--" and data.entry_price is None
    is_stale = data.strategy != "--" and data.current_price is None
    is_estimate = live is None and data.unrealized_pnl is not None

    if is_ghost:
        status = "No Data"
    elif is_stale:
        status = "Stale"
    elif is_estimate:
        status = "Est."
    else:
        status = ""

    # Ghost positions: SL/TP show "N/A" (not applicable) instead of "--" (loading)
    if is_ghost:
        sl_display = "N/A"
        tp_display = "N/A"
        sl_dist_display = "N/A"
        tp_dist_display = "N/A"
        r_display = "N/A"
    else:
        sl_display = _fmt_price(data.sl_price)
        tp_display = _fmt_price(data.tp_price)
        sl_dist_display = f"-{data.sl_dist_pct*100:.1f}%" if data.sl_dist_pct is not None else "--"
        tp_dist_display = f"+{data.tp_dist_pct*100:.1f}%" if data.tp_dist_pct is not None else "--"
        r_display = f"{data.r_multiple:+.2f}R" if data.r_multiple is not None else "--"

    return {
        "Symbol": data.symbol,
        "Status": status,
        "Strategy": data.strategy,
        "Dir": data.direction.upper()[:1] if data.direction != "--" else "--",
        "Qty": str(data.quantity) if data.quantity is not None else "--",
        "Size": f"${data.pos_value:,.0f}" if data.pos_value is not None else "--",
        "Entry": _fmt_price(data.entry_price),
        "Current": _fmt_price(data.current_price),
        "P&L": _fmt_dollar_pct(data.unrealized_pnl, data.unrealized_pnl_pct),
        "SL": sl_display,
        "TP": tp_display,
        "SL Dist": sl_dist_display,
        "TP Dist": tp_dist_display,
        "R": r_display,
        "MFE": _fmt_dollar_pct(data.mfe_dollar, data.mfe_pct),
        "MAE": _fmt_dollar_pct(
            -abs(data.mae_dollar) if data.mae_dollar is not None else None,
            -abs(data.mae_pct) if data.mae_pct is not None else None,
        ),
        "Days": data.days_held,
    }


def _style_position_table(row: pd.Series, renamed: bool = False) -> list[str]:
    """Apply row-level styling to position table.

    Parameters
    ----------
    renamed:
        If True, use the beginner-friendly column names (Direction,
        Best P&L, Worst P&L, R-Multiple) instead of the originals.
    """
    styles = [""] * len(row)

    # Status column styling
    if "Status" in row.index:
        idx = row.index.get_loc("Status")
        status_val = str(row["Status"])
        if status_val == "No Data":
            styles[idx] = (
                f"color: {COLORS['warning']}; font-weight: bold; "
                f"background-color: {COLORS['warning']}18"
            )
        elif status_val == "Stale":
            styles[idx] = f"color: #E2C344; font-weight: bold"
        elif status_val == "Est.":
            styles[idx] = f"color: #8899AA; font-weight: bold"

    # Direction column (supports both old "Dir" and renamed "Direction")
    dir_col = "Direction" if renamed else "Dir"
    if dir_col in row.index:
        idx = row.index.get_loc(dir_col)
        dir_val = str(row[dir_col])
        if dir_val in ("L", "Long"):
            styles[idx] = f"color: {COLORS['profit']}; font-weight: bold"
        elif dir_val in ("S", "Short"):
            styles[idx] = f"color: {COLORS['loss']}; font-weight: bold"

    # Color P&L and related columns (supports both old and renamed names)
    pnl_cols = (
        ("P&L", "Best P&L", "Worst P&L", "R-Multiple")
        if renamed
        else ("P&L", "MFE", "MAE", "R")
    )
    for col in pnl_cols:
        if col in row.index:
            idx = row.index.get_loc(col)
            val = str(row[col])
            if val.startswith("+"):
                styles[idx] = f"color: {COLORS['profit']}; font-weight: bold"
            elif val.startswith("-"):
                styles[idx] = f"color: {COLORS['loss']}; font-weight: bold"

    return styles


# ---------------------------------------------------------------------------
# Daily PnL with unrealized
# ---------------------------------------------------------------------------

def _render_daily_pnl_with_unrealized(
    trades_df: pd.DataFrame | None,
    current_positions: list[str] | None = None,
) -> None:
    """Render daily PnL summary: today's total, per-position breakdown, and history."""
    # -- Collect data ----------------------------------------------------------
    daily_data: dict[str, float] = {}
    realized_today = 0.0

    if trades_df is not None and not trades_df.empty and "timestamp" in trades_df.columns:
        df = trades_df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if "side" in df.columns:
            exits = df[df["side"] == "exit"]
        else:
            exits = df
        if not exits.empty and "pnl" in exits.columns:
            exits = exits.copy()
            exits["date"] = exits["timestamp"].dt.strftime("%Y-%m-%d")
            for d, grp in exits.groupby("date"):
                daily_data[d] = float(grp["pnl"].sum())
            today_str_check = date.today().isoformat()
            realized_today = daily_data.get(today_str_check, 0.0)

    today_str = date.today().isoformat()
    try:
        live_pos = load_open_positions()
        unrealized = sum(p.get("unrealized_pnl", 0.0) for p in live_pos.values())
    except Exception:
        live_pos = {}
        unrealized = 0.0

    # Fallback: compute unrealized from batch_results prev_close
    has_tracked_positions = len(live_pos) > 0
    has_known_positions = bool(current_positions)
    if not has_tracked_positions and has_known_positions and trades_df is not None:
        fb_prices = _load_fallback_prices()
        if fb_prices:
            for sym in current_positions:
                fb = fb_prices.get(sym)
                if fb is None:
                    continue
                sym_data = _extract_position_data(sym, trades_df, fallback_prices=fb_prices)
                if sym_data.unrealized_pnl is not None:
                    unrealized += sym_data.unrealized_pnl

    if unrealized != 0.0 or has_tracked_positions or today_str in daily_data:
        daily_data[today_str] = daily_data.get(today_str, 0.0) + unrealized

    if not daily_data and not has_tracked_positions and not has_known_positions:
        st.info("No PnL data available yet.")
        return

    if not daily_data and has_known_positions and not has_tracked_positions:
        st.warning(
            f"{len(current_positions)} open position(s) detected but live P&L tracking "
            "is unavailable. Data will populate after the next market session."
        )
        return

    today_total = daily_data.get(today_str, 0.0)

    # -- Row 1: Today PnL summary card + per-position breakdown ----------------
    col_summary, col_breakdown = st.columns([0.35, 0.65])

    with col_summary:
        _render_today_pnl_card(today_total, realized_today, unrealized)

    with col_breakdown:
        _render_position_pnl_breakdown(live_pos)

    # -- Row 2: Daily history bar chart (only when 2+ days of data) -----------
    if len(daily_data) >= 2:
        _render_daily_history_chart(daily_data, today_str)


def _render_today_pnl_card(
    today_total: float,
    realized: float,
    unrealized: float,
) -> None:
    """Render today's P&L as a prominent summary card."""
    color = COLORS["profit"] if today_total >= 0 else COLORS["loss"]
    sign = "+" if today_total >= 0 else ""
    border = COLORS["profit"] if today_total >= 0 else COLORS["loss"]
    muted = COLORS["text_muted"]
    secondary = COLORS["text_secondary"]

    # Realized/unrealized sub-line
    parts = []
    if realized != 0.0:
        r_sign = "+" if realized >= 0 else ""
        parts.append(f"Realized {r_sign}${realized:,.0f}")
    if unrealized != 0.0:
        u_sign = "+" if unrealized >= 0 else ""
        parts.append(f"Unrealized {u_sign}${unrealized:,.0f}")
    sub_text = " | ".join(parts) if parts else "No trades today"

    st.markdown(
        f"<div style='background:{COLORS['bg_card']};border-left:3px solid {border};"
        f"border-radius:6px;padding:16px 20px'>"
        f"<div style='color:{secondary};font-size:0.85em;margin-bottom:4px'>Today's P&L</div>"
        f"<div style='color:{color};font-size:1.8em;font-weight:700;line-height:1.2'>"
        f"{sign}${today_total:,.2f}</div>"
        f"<div style='color:{muted};font-size:0.8em;margin-top:6px'>{sub_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_position_pnl_breakdown(live_pos: dict[str, dict]) -> None:
    """Render per-position P&L as a horizontal bar chart."""
    if not live_pos:
        st.caption("No open positions for breakdown.")
        return

    symbols = []
    pnl_values = []
    for sym, pos in live_pos.items():
        pnl = pos.get("unrealized_pnl", 0.0)
        symbols.append(sym)
        pnl_values.append(pnl)

    # Sort by absolute P&L descending
    paired = sorted(zip(symbols, pnl_values), key=lambda x: abs(x[1]), reverse=True)
    symbols = [p[0] for p in paired]
    pnl_values = [p[1] for p in paired]
    bar_colors = [COLORS["profit"] if v >= 0 else COLORS["loss"] for v in pnl_values]

    # Build text annotations
    text_labels = []
    for v in pnl_values:
        sign = "+" if v >= 0 else ""
        text_labels.append(f"{sign}${v:,.0f}")

    fig = go.Figure(
        go.Bar(
            y=symbols,
            x=pnl_values,
            orientation="h",
            marker_color=bar_colors,
            text=text_labels,
            textposition="outside",
            textfont=dict(size=12, color=bar_colors),
            hovertemplate="%{y}: %{x:$,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **get_chart_layout(
            title={"text": "P&L by Position"},
            height=max(120, 50 * len(symbols) + 60),
            showlegend=False,
            xaxis={"title": "", "zeroline": True, "zerolinecolor": COLORS["text_muted"], "zerolinewidth": 1},
            yaxis={"title": "", "autorange": "reversed"},
        )
    )
    fig.update_layout(
        margin=dict(l=60, r=80, t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True, key="position_pnl_breakdown")


def _render_daily_history_chart(daily_data: dict[str, float], today_str: str) -> None:
    """Render daily P&L history as a bar chart + cumulative line."""
    dates = sorted(daily_data.keys())
    values = [daily_data[d] for d in dates]
    bar_colors = [COLORS["profit"] if v >= 0 else COLORS["loss"] for v in values]

    # Cumulative P&L
    cumulative = []
    running = 0.0
    for v in values:
        running += v
        cumulative.append(running)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=dates,
            y=values,
            marker_color=bar_colors,
            name="Daily",
            hovertemplate="Date: %{x}<br>PnL: %{y:$,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cumulative,
            mode="lines+markers",
            name="Cumulative",
            line=dict(color=COLORS["info"], width=2),
            marker=dict(size=5),
            hovertemplate="Date: %{x}<br>Cumulative: %{y:$,.2f}<extra></extra>",
            yaxis="y2",
        )
    )

    fig.update_layout(
        **get_chart_layout(
            title={"text": "Daily P&L History"},
            height=260,
            showlegend=True,
            xaxis={"title": ""},
            yaxis={"title": "Daily ($)"},
        )
    )
    fig.update_layout(
        xaxis_type="category",
        yaxis2=dict(
            title="Cumulative ($)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    st.plotly_chart(fig, use_container_width=True, key="daily_pnl_history")


# ---------------------------------------------------------------------------
# Recent trades table
# ---------------------------------------------------------------------------

_RECENT_TRADE_COLS = [
    "timestamp", "symbol", "side", "strategy", "direction",
    "quantity", "price", "pnl", "exit_reason",
]


def _render_recent_trades_table(trades_df: pd.DataFrame) -> None:
    """Render the last 50 trades (entries and exits)."""
    df = trades_df.copy()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp", ascending=False)

    recent = df.head(50)

    if recent.empty:
        st.caption("No trades recorded yet.")
        return

    display_cols = [c for c in _RECENT_TRADE_COLS if c in recent.columns]
    display = recent[display_cols].reset_index(drop=True)

    # Format timestamp: remove microseconds/timezone, show as MM/DD HH:MM
    if "timestamp" in display.columns:
        display["timestamp"] = pd.to_datetime(display["timestamp"]).dt.strftime("%m/%d %H:%M")

    if "strategy" in display.columns:
        display["strategy"] = display["strategy"].map(
            lambda s: STRATEGY_NAMES.get(str(s), str(s))
        )

    # Format side column for readability
    if "side" in display.columns:
        display["side"] = display["side"].map(
            lambda s: "ENTRY" if s == "entry" else ("EXIT" if s == "exit" else str(s).upper())
        )

    # Format Qty as integer, Price as $x.xx
    if "quantity" in display.columns:
        display["quantity"] = pd.to_numeric(display["quantity"], errors="coerce").map(
            lambda v: f"{int(v)}" if pd.notna(v) else "--"
        )
    if "price" in display.columns:
        display["price"] = pd.to_numeric(display["price"], errors="coerce").map(
            lambda v: f"${v:,.2f}" if pd.notna(v) else "--"
        )

    # For entry rows, clear pnl/exit_reason (they're meaningless)
    if "pnl" in display.columns and "side" in display.columns:
        entry_mask = display["side"] == "ENTRY"
        display.loc[entry_mask, "pnl"] = None
        if "exit_reason" in display.columns:
            display.loc[entry_mask, "exit_reason"] = ""

    # Format PnL as $x.xx, replace None with "--"
    if "pnl" in display.columns:
        display["pnl"] = display["pnl"].map(
            lambda v: f"${float(v):+,.2f}" if pd.notna(v) and v is not None else "--"
        )

    # Map exit reasons to friendly labels
    if "exit_reason" in display.columns:
        display["exit_reason"] = display["exit_reason"].map(
            lambda v: EXIT_REASON_LABELS.get(str(v).lower(), str(v)) if pd.notna(v) and v != "" else v
        )

    # Rename columns for display
    col_rename = {
        "timestamp": "Time", "symbol": "Symbol", "side": "Side",
        "strategy": "Strategy", "direction": "Dir", "quantity": "Qty",
        "price": "Price", "pnl": "PnL", "exit_reason": "Exit Reason",
    }
    display = display.rename(columns={k: v for k, v in col_rename.items() if k in display.columns})

    def _style_trade_row(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        if "Side" in row.index:
            idx = row.index.get_loc("Side")
            if row["Side"] == "ENTRY":
                styles[idx] = f"color: {COLORS['info']}; font-weight: bold"
            elif row["Side"] == "EXIT":
                styles[idx] = f"color: {COLORS['warning']}; font-weight: bold"
        if "PnL" in row.index:
            idx = row.index.get_loc("PnL")
            try:
                val = float(row["PnL"]) if row["PnL"] is not None else None
            except (TypeError, ValueError):
                val = None
            if val is not None:
                if val > 0:
                    styles[idx] = f"color: {COLORS['profit']}; font-weight: bold"
                elif val < 0:
                    styles[idx] = f"color: {COLORS['loss']}; font-weight: bold"
        return styles

    st.dataframe(
        display.style.apply(_style_trade_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Round-trip view
# ---------------------------------------------------------------------------

def _render_roundtrip_view(trades_df: pd.DataFrame) -> None:
    """Match entry+exit trades into round-trips."""
    if trades_df.empty or "side" not in trades_df.columns:
        st.info("No round-trip data available.")
        return

    df = trades_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    entries = df[df["side"].isin(["entry", "reconciliation_entry"])].sort_values("timestamp")
    exits = df[df["side"] == "exit"].sort_values("timestamp")

    rows = []
    used_exits = set()
    for _, entry in entries.iterrows():
        sym = entry["symbol"]
        strat = entry.get("strategy", "--")
        # Find matching exit
        match = exits[
            (exits["symbol"] == sym)
            & (exits["timestamp"] > entry["timestamp"])
            & (~exits.index.isin(used_exits))
        ]
        if match.empty:
            continue
        exit_row = match.iloc[0]
        used_exits.add(exit_row.name)

        entry_ts = entry["timestamp"]
        exit_ts = exit_row["timestamp"]
        hold_days = (exit_ts - entry_ts).days

        dir_raw = str(entry.get("direction", "--")).lower()
        dir_display = "Long" if dir_raw == "long" else ("Short" if dir_raw == "short" else "--")

        rows.append({
            "Symbol": sym,
            "Strategy": STRATEGY_NAMES.get(str(strat), str(strat)),
            "Direction": dir_display,
            "Entry Date": entry_ts.strftime("%m/%d %H:%M"),
            "Entry Price": f"${float(entry.get('price', 0)):,.2f}",
            "Exit Date": exit_ts.strftime("%m/%d %H:%M"),
            "Exit Price": f"${float(exit_row.get('price', 0)):,.2f}",
            "Hold Days": hold_days,
            "PnL": f"${float(exit_row.get('pnl', 0)):+,.2f}",
            "Exit Reason": EXIT_REASON_LABELS.get(str(exit_row.get("exit_reason", "--")).lower(), str(exit_row.get("exit_reason", "--"))),
        })

    if not rows:
        st.info("No completed round-trips found.")
        return

    rt_df = pd.DataFrame(rows)

    def _style_rt(row):
        styles = [""] * len(row)
        if "PnL" in row.index:
            idx = row.index.get_loc("PnL")
            val = str(row["PnL"])
            if val.startswith("+") or (val.startswith("$") and not val.startswith("$-")):
                styles[idx] = f"color: {COLORS['profit']}; font-weight: bold"
            elif "-" in val:
                styles[idx] = f"color: {COLORS['loss']}; font-weight: bold"
        return styles

    st.dataframe(
        rt_df.style.apply(_style_rt, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"{len(rows)} completed round-trips shown")


# ---------------------------------------------------------------------------
# Sidebar compact card
# ---------------------------------------------------------------------------

def _render_empty_state(trades_df) -> None:
    """Render the empty positions placeholder."""
    st.markdown(
        '<div class="at-empty">'
        '<div class="at-empty-title">No open positions</div>'
        '<div class="at-empty-desc">'
        "The system scans S&P 500 stocks every weeknight at 10 PM ET.<br>"
        "New positions appear here when signals are found."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_position_card(
    symbol: str,
    trades_df,
    live: dict | None = None,
    fallback_prices: dict[str, float] | None = None,
) -> None:
    """Render a single compact position card for the sidebar panel.

    Shows a collapsed view by default (symbol, direction, P&L, strategy,
    days held) with an expander for detailed info (entry/current/qty,
    SL/TP, MFE/MAE, proximity bar).

    Delegates data extraction to _extract_position_data() and focuses
    solely on HTML rendering.
    """
    data = _extract_position_data(symbol, trades_df, live, fallback_prices)

    # Unpack for rendering convenience
    strategy_key = data.strategy_key
    strategy = data.strategy
    direction = data.direction
    entry_price = data.entry_price
    current_price = data.current_price
    quantity = data.quantity
    sl_price = data.sl_price
    tp_price = data.tp_price
    unrealized_pnl = data.unrealized_pnl
    unrealized_pnl_pct = data.unrealized_pnl_pct
    days_held = data.days_held if data.days_held > 0 else None

    is_ghost = strategy == "--" and entry_price is None

    # Strategy display for card
    if is_ghost:
        strategy_display = (
            f'<span style="color:{COLORS["warning"]};font-weight:600">Unknown</span>'
            f' <span style="color:{COLORS["text_muted"]};font-size:0.9em">(no trade record)</span>'
        )
    else:
        strategy_display = strategy

    strat_color = STRATEGY_COLORS.get(strategy_key, COLORS["text_muted"])
    dir_short = "S" if direction.lower() == "short" else "L"
    dir_bg = COLORS["loss"] if direction.lower() == "short" else COLORS["profit"]

    days_text = f"{days_held}d" if days_held is not None else "--"

    # P&L display
    pnl_html = ""
    if unrealized_pnl is not None and unrealized_pnl_pct is not None:
        pnl_clr = COLORS["profit"] if unrealized_pnl >= 0 else COLORS["loss"]
        sign = "+" if unrealized_pnl >= 0 else ""
        pnl_html = (
            f'<span style="color:{pnl_clr};font-size:0.95em;font-weight:700">'
            f'{sign}${unrealized_pnl:,.0f} ({sign}{unrealized_pnl_pct * 100:.1f}%)</span>'
        )

    # ── Collapsed view (always visible) ──────────────────────────────
    card_html = (
        f'<div style="background-color:{COLORS["bg_card"]};border-left:3px solid {strat_color};'
        f'border-radius:6px;padding:10px 14px;margin-bottom:2px">'
        # Header: symbol + direction badge + P&L
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<span style="color:{COLORS["text_primary"]};font-size:1.05em;font-weight:700">{symbol}</span>'
        f'<span style="background-color:{dir_bg}22;color:{dir_bg};font-size:0.75em;font-weight:700;'
        f'padding:2px 6px;border-radius:4px">{dir_short}</span>'
        f'</div>{pnl_html}</div>'
        # Strategy + days held
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.82em">'
        f'{strategy_display}'
        f'<span style="color:{COLORS["text_muted"]};margin-left:8px">{days_text} held</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    # ── Detailed view (inside expander) ──────────────────────────────
    with st.expander("Details", expanded=False):
        # Entry/Current/Qty/Size line
        entry_text = _fmt_price(entry_price)
        current_text = (
            f'<span style="color:{COLORS["warning"]}">Price unavailable</span>'
            if current_price is None and not is_ghost and strategy != "--"
            else _fmt_price(current_price)
        )
        qty_text = f"{quantity}" if quantity is not None else "--"
        size_text = ""
        if quantity is not None and entry_price is not None:
            size_text = f"${quantity * entry_price:,.0f}"

        detail_line = (
            f'<div style="display:flex;gap:12px;color:{COLORS["text_muted"]};font-size:0.80em">'
            f'<span>Entry: {entry_text}</span><span>Now: {current_text}</span>'
            f'<span>Qty: {qty_text}</span>'
            f'{"<span>Size: " + size_text + "</span>" if size_text else ""}'
            f'</div>'
        )
        st.markdown(detail_line, unsafe_allow_html=True)

        # SL/TP level text
        if is_ghost:
            level_text = "SL/TP N/A (no trade record)"
        else:
            sl_text = _fmt_price(sl_price)
            tp_text = _fmt_price(tp_price)
            level_text = (
                " | ".join(
                    filter(lambda x: x != "--", [f"SL {sl_text}", f"TP {tp_text}"])
                )
                or "--"
            )
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.78em;margin-top:2px">'
            f'{level_text}</div>',
            unsafe_allow_html=True,
        )

        # MFE/MAE display (unified format)
        if data.mfe_dollar or data.mae_dollar:
            parts = []
            if data.mfe_dollar:
                parts.append(
                    f'<span style="color:{COLORS["profit"]}">MFE +${data.mfe_dollar:,.0f} '
                    f'(+{(data.mfe_pct or 0) * 100:.1f}%)</span>'
                )
            if data.mae_dollar:
                parts.append(
                    f'<span style="color:{COLORS["loss"]}">MAE -${abs(data.mae_dollar):,.0f} '
                    f'(-{abs(data.mae_pct or 0) * 100:.1f}%)</span>'
                )
            if parts:
                st.markdown(
                    f'<div style="display:flex;gap:12px;font-size:0.78em;margin-top:2px">'
                    f'{"".join(parts)}</div>',
                    unsafe_allow_html=True,
                )

        # Proximity bar
        if current_price and sl_price and tp_price:
            dir_lower = direction.lower()
            if dir_lower == "long":
                sl_d = (current_price - sl_price) / current_price * 100
                tp_d = (tp_price - current_price) / current_price * 100
            else:
                sl_d = (sl_price - current_price) / current_price * 100
                tp_d = (current_price - tp_price) / current_price * 100

            total_range = sl_d + tp_d
            if total_range > 0:
                position_pct = sl_d / total_range * 100
                if dir_lower == "long":
                    left_color = COLORS["profit"]
                    right_color = COLORS["loss"]
                else:
                    left_color = COLORS["loss"]
                    right_color = COLORS["profit"]
                proximity_html = (
                    f'<div style="margin-top:4px">'
                    f'<div style="display:flex;justify-content:space-between;font-size:0.72em;color:{COLORS["text_muted"]}">'
                    f'<span>SL -{sl_d:.1f}%</span><span>TP +{tp_d:.1f}%</span></div>'
                    f'<div style="background:linear-gradient(90deg, {left_color}44 0%, {left_color}22 {position_pct:.0f}%, {right_color}22 {position_pct:.0f}%, {right_color}44 100%);'
                    f'height:4px;border-radius:2px;position:relative;margin-top:2px">'
                    f'<div style="position:absolute;left:{position_pct:.0f}%;top:-2px;width:2px;height:8px;background:{COLORS["text_primary"]};border-radius:1px"></div>'
                    f'</div></div>'
                )
                st.markdown(proximity_html, unsafe_allow_html=True)
