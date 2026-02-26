"""Position panel component for the live trading dashboard.

Renders open position cards with entry details extracted from trade
history, styled with strategy-specific colors and dark card backgrounds.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.theme import COLORS, STRATEGY_COLORS, STRATEGY_NAMES


def render_position_panel(data) -> None:
    """Render the current open positions panel.

    Parameters
    ----------
    data:
        A DashboardData instance with ``current_positions`` (list of
        symbol strings) and ``trades_df`` (trade history DataFrame).
    """
    positions = getattr(data, "current_positions", [])
    trades_df = getattr(data, "trades_df", None)
    pos_count = len(positions) if positions else 0

    st.subheader(f"Positions ({pos_count})")

    # -- No positions --------------------------------------------------------
    if not positions:
        _render_empty_state(trades_df)
        return

    # -- Has positions -------------------------------------------------------
    for symbol in positions:
        _render_position_card(symbol, trades_df)


def _render_empty_state(trades_df) -> None:
    """Render the empty positions placeholder."""
    # Count active universe symbols from recent trades
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
            ">Waiting for signals...</div>
            <div style="
                color: {COLORS['text_muted']};
                font-size: 0.85em;
            ">{universe_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_position_card(symbol: str, trades_df) -> None:
    """Render a single position card for the given symbol.

    Extracts the most recent entry trade from trades_df to populate
    strategy, direction, entry price, and bars held.
    """
    strategy = "--"
    strategy_key = ""
    direction = "--"
    entry_price = None
    bars_held = None
    pnl = None

    if trades_df is not None and not trades_df.empty:
        sym_trades = trades_df[trades_df["symbol"] == symbol] if "symbol" in trades_df.columns else trades_df.iloc[0:0]

        if not sym_trades.empty:
            # Find entry trades (side == "entry" or direction in ["long", "short"])
            if "side" in sym_trades.columns:
                entries = sym_trades[sym_trades["side"] == "entry"]
            elif "direction" in sym_trades.columns:
                entries = sym_trades[
                    sym_trades["direction"].isin(["long", "short"])
                ]
            else:
                entries = sym_trades

            if not entries.empty:
                if "timestamp" in entries.columns:
                    latest_entry = entries.sort_values(
                        "timestamp", ascending=False,
                    ).iloc[0]
                else:
                    latest_entry = entries.iloc[-1]

                strategy_key = str(
                    latest_entry.get("strategy", ""),
                ) if hasattr(latest_entry, "get") else str(
                    latest_entry["strategy"],
                ) if "strategy" in entries.columns else ""

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

            # Check for PnL from the most recent trade for this symbol
            if "pnl" in sym_trades.columns:
                last_trade = sym_trades.iloc[-1]
                last_pnl = last_trade["pnl"]
                if last_pnl is not None and last_pnl != 0:
                    pnl = float(last_pnl)

    # Determine colors
    strat_color = STRATEGY_COLORS.get(strategy_key, COLORS["text_muted"])
    dir_short = "S" if direction.lower() == "short" else "L"
    dir_bg = COLORS["loss"] if direction.lower() == "short" else COLORS["profit"]

    # Build detail lines
    price_text = f"${entry_price:,.2f}" if entry_price is not None else "--"
    bars_text = f"{bars_held} bars" if bars_held is not None else "--"

    pnl_html = ""
    if pnl is not None:
        pnl_color = COLORS["profit"] if pnl >= 0 else COLORS["loss"]
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_html = (
            f'<span style="color:{pnl_color};font-size:0.9em;'
            f'font-weight:600">{pnl_sign}${pnl:,.2f}</span>'
        )

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border-left: 3px solid {strat_color};
            border-radius: 6px;
            padding: 12px 16px;
            margin-bottom: 8px;
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            ">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="
                        color: {COLORS['text_primary']};
                        font-size: 1.05em;
                        font-weight: 700;
                    ">{symbol}</span>
                    <span style="
                        background-color: {dir_bg}22;
                        color: {dir_bg};
                        font-size: 0.75em;
                        font-weight: 700;
                        padding: 2px 6px;
                        border-radius: 4px;
                    ">{dir_short}</span>
                </div>
                {pnl_html}
            </div>
            <div style="
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 4px;
            ">
                <span style="
                    display: inline-block;
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background-color: {strat_color};
                "></span>
                <span style="
                    color: {COLORS['text_secondary']};
                    font-size: 0.85em;
                ">{strategy}</span>
            </div>
            <div style="
                display: flex;
                gap: 16px;
                color: {COLORS['text_muted']};
                font-size: 0.82em;
            ">
                <span>Entry: {price_text}</span>
                <span>Held: {bars_text}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
