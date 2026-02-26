"""KPI cards component for the live trading dashboard.

Renders a row of 6 key performance indicator metric cards showing
total PnL, today PnL, max drawdown, win rate, current regime,
and open position count.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.theme import COLORS, REGIME_COLORS
from autotrader.dashboard.utils.formatters import fmt_pnl, fmt_pct


def render_kpi_cards(data) -> None:
    """Render 6 KPI metric cards in a single row.

    Parameters
    ----------
    data:
        A DashboardData instance with fields: total_pnl, today_pnl,
        max_drawdown, winning_trades, total_trades, current_regime,
        current_positions.
    """
    col_pnl, col_today, col_dd, col_wr, col_regime, col_pos = st.columns(
        [1.5, 1, 1.5, 1, 1, 1],
    )

    # -- 1. Total PnL -------------------------------------------------------
    with col_pnl:
        total_pnl = getattr(data, "total_pnl", 0.0)
        today_pnl = getattr(data, "today_pnl", 0.0)
        delta_text = f"{fmt_pnl(today_pnl)} today"
        st.metric("Total PnL", fmt_pnl(total_pnl), delta=delta_text)

    # -- 2. Today PnL -------------------------------------------------------
    with col_today:
        st.metric("Today PnL", fmt_pnl(today_pnl))

    # -- 3. Max Drawdown -----------------------------------------------------
    with col_dd:
        max_dd = getattr(data, "max_drawdown", 0.0)
        # Display as negative percentage
        dd_display = f"-{fmt_pct(max_dd)}" if max_dd > 0 else fmt_pct(0.0)
        st.metric("Max Drawdown", dd_display)

    # -- 4. Win Rate ---------------------------------------------------------
    with col_wr:
        total_trades = getattr(data, "total_trades", 0)
        winning_trades = getattr(data, "winning_trades", 0)
        if total_trades > 0:
            win_rate = winning_trades / total_trades
            wr_display = fmt_pct(win_rate)
        else:
            wr_display = "--"
        st.metric("Win Rate", wr_display, delta=f"{total_trades} trades")

    # -- 5. Regime -----------------------------------------------------------
    with col_regime:
        regime = getattr(data, "current_regime", "UNKNOWN")
        regime_color = REGIME_COLORS.get(str(regime), COLORS["neutral"])
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
                ">{regime}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -- 6. Positions --------------------------------------------------------
    with col_pos:
        positions = getattr(data, "current_positions", [])
        pos_count = len(positions) if positions else 0
        st.metric("Positions", str(pos_count))
