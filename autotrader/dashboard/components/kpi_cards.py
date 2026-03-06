"""KPI cards component for the live trading dashboard.

Renders a row of 6 key performance indicator metric cards showing
account equity, today's PnL, open positions, current regime, win rate,
and max drawdown.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.theme import COLORS, REGIME_COLORS
from autotrader.dashboard.utils.formatters import fmt_currency, fmt_pnl, fmt_pct, fmt_pnl_pct


def render_kpi_cards(data) -> None:
    """Render 6 KPI metric cards in a single row.

    Parameters
    ----------
    data:
        A DashboardData instance with fields: current_equity, today_pnl,
        today_pnl_pct, max_drawdown, winning_trades, total_trades,
        current_regime, current_positions.
    """
    col_equity, col_today, col_pos, col_regime, col_wr, col_dd = st.columns(
        [1.5, 1.2, 1, 1.2, 1, 1],
    )

    # -- 1. Account Equity ---------------------------------------------------
    with col_equity:
        current_equity = getattr(data, "current_equity", 0.0)
        total_pnl = getattr(data, "total_pnl", 0.0)
        total_trades = getattr(data, "total_trades", 0)
        if total_trades == 0:
            pnl_delta = "No closed trades"
        else:
            pnl_delta = f"{fmt_pnl(total_pnl)} total"
        st.metric(
            "Account Equity",
            fmt_currency(current_equity),
            delta=pnl_delta,
        )

    # -- 2. Today's PnL ------------------------------------------------------
    with col_today:
        today_pnl = getattr(data, "today_pnl", 0.0)
        today_pnl_pct = getattr(data, "today_pnl_pct", 0.0)
        today_pct_text = fmt_pnl_pct(today_pnl_pct)
        st.metric(
            "Today PnL",
            fmt_pnl(today_pnl),
            delta=today_pct_text,
        )

    # -- 3. Open Positions ---------------------------------------------------
    with col_pos:
        positions = getattr(data, "current_positions", [])
        pos_count = len(positions) if positions else 0
        max_pos = 8
        deployed_pct = getattr(data, "capital_deployed_pct", 0.0)
        st.metric(
            "Positions",
            f"{pos_count} / {max_pos}",
            delta=f"{deployed_pct*100:.0f}% deployed",
            delta_color="off",
        )

    # -- 4. Regime -----------------------------------------------------------
    with col_regime:
        regime = getattr(data, "current_regime", "UNKNOWN")
        spy_adx = getattr(data, "spy_adx", None)
        regime_color = REGIME_COLORS.get(str(regime), COLORS["neutral"])
        regime_text = str(regime)
        if spy_adx is not None:
            regime_text = f"{regime} (ADX {spy_adx:.1f})"
        dead_zone_html = ""
        if spy_adx is not None and 20 <= spy_adx <= 28:
            dead_zone_html = f"""
                <div style="
                    color: {COLORS['warning']};
                    font-size: 0.75em;
                    margin-top: 4px;
                ">Dead Zone (20-28)</div>"""
        st.markdown(
            f"""
            <div style="
                background-color: {regime_color}22;
                border: 1px solid {regime_color};
                border-radius: 8px;
                padding: 12px 16px;
                text-align: center;
                margin-top: 4px;
            ">
                <div style="
                    color: {COLORS['text_secondary']};
                    font-size: 0.85em;
                    margin-bottom: 4px;
                ">Regime</div>
                <div style="
                    color: {regime_color};
                    font-size: 1.1em;
                    font-weight: 700;
                ">{regime_text}</div>{dead_zone_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -- 5. Win Rate ---------------------------------------------------------
    with col_wr:
        total_trades = getattr(data, "total_trades", 0)
        winning_trades = getattr(data, "winning_trades", 0)
        if total_trades > 0:
            win_rate = winning_trades / total_trades
            wr_display = fmt_pct(win_rate)
        else:
            wr_display = "--"
        wr_delta = f"n={total_trades}"
        if total_trades < 30:
            wr_delta += " (low confidence)"
        st.metric("Win Rate", wr_display, delta=wr_delta, delta_color="off")

    # -- 6. Max Drawdown -----------------------------------------------------
    with col_dd:
        max_dd = getattr(data, "max_drawdown", 0.0)
        dd_display = f"-{fmt_pct(max_dd)}" if max_dd > 0 else fmt_pct(0.0)
        dd_limit = "15% limit"
        st.metric("Max Drawdown", dd_display, delta=dd_limit, delta_color="off")
