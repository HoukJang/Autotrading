"""KPI cards component for the live trading dashboard.

Renders two rows of 3 custom HTML KPI cards showing account value,
today's P&L, open positions, market mood, win rate, and safety level.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.theme import (
    COLORS,
    REGIME_BEGINNER_LABELS,
    REGIME_COLORS,
)
from autotrader.dashboard.utils.formatters import (
    fmt_currency,
    fmt_pct,
    fmt_pnl,
    fmt_pnl_pct,
    pnl_color,
)
from autotrader.trading.constants import MAX_LONG_POSITIONS


def render_kpi_cards(data) -> None:
    """Render 6 KPI cards in a 3+3 custom HTML grid.

    Parameters
    ----------
    data:
        A DashboardData instance with fields: current_equity, today_pnl,
        today_pnl_pct, max_drawdown, winning_trades, total_trades,
        current_regime, current_positions, total_pnl, capital_deployed_pct,
        spy_adx.
    """
    # ── Row 1 ────────────────────────────────────────────────────────────
    r1c1, r1c2, r1c3 = st.columns(3)

    # -- 1. Account Value --------------------------------------------------
    with r1c1:
        current_equity = getattr(data, "current_equity", 0.0)
        total_pnl = getattr(data, "total_pnl", 0.0)
        total_trades = getattr(data, "total_trades", 0)

        if total_trades == 0:
            delta_html = "No closed trades"
        else:
            pnl_clr = pnl_color(total_pnl)
            delta_html = (
                f'<span style="color:{pnl_clr}">{fmt_pnl(total_pnl)} total</span>'
            )

        st.markdown(
            _kpi_html(
                label="Account Value",
                value=fmt_currency(current_equity),
                value_color=COLORS["text_primary"],
                delta=delta_html,
            ),
            unsafe_allow_html=True,
        )

    # -- 2. Today's P&L ----------------------------------------------------
    with r1c2:
        today_pnl = getattr(data, "today_pnl", 0.0)
        today_pnl_pct = getattr(data, "today_pnl_pct", 0.0)
        pnl_clr = pnl_color(today_pnl)

        st.markdown(
            _kpi_html(
                label="Today's P&L",
                value=fmt_pnl(today_pnl),
                value_color=pnl_clr,
                delta=fmt_pnl_pct(today_pnl_pct),
            ),
            unsafe_allow_html=True,
        )

    # -- 3. Open Positions -------------------------------------------------
    with r1c3:
        positions = getattr(data, "current_positions", [])
        pos_count = len(positions) if positions else 0
        max_pos = MAX_LONG_POSITIONS
        deployed_pct = getattr(data, "capital_deployed_pct", 0.0)

        st.markdown(
            _kpi_html(
                label="Open Positions",
                value=f"{pos_count} / {max_pos}",
                value_color=COLORS["text_primary"],
                delta=f"{deployed_pct * 100:.0f}% deployed",
            ),
            unsafe_allow_html=True,
        )

    # ── Row 2 ────────────────────────────────────────────────────────────
    r2c1, r2c2, r2c3 = st.columns(3)

    # -- 4. Market Mood ----------------------------------------------------
    with r2c1:
        regime = getattr(data, "current_regime", "UNKNOWN")
        spy_adx = getattr(data, "spy_adx", None)
        regime_str = str(regime)
        regime_color = REGIME_COLORS.get(regime_str, COLORS["neutral"])
        friendly_regime = REGIME_BEGINNER_LABELS.get(regime_str, regime_str)

        # Strategy activity description based on ADX zones
        if spy_adx is not None and 20 <= spy_adx <= 28:
            activity_text = "Quiet market - strategies paused"
            activity_color = COLORS["warning"]
        elif spy_adx is not None and spy_adx > 28:
            activity_text = "All strategies active"
            activity_color = COLORS["profit"]
        elif spy_adx is not None and spy_adx < 20:
            activity_text = "Mean reversion active"
            activity_color = COLORS["info"]
        else:
            activity_text = ""
            activity_color = COLORS["text_muted"]

        # Build delta content
        delta_parts = []
        if spy_adx is not None:
            delta_parts.append(f"SPY ADX {spy_adx:.1f}")
        if activity_text:
            delta_parts.append(
                f'<span style="color:{activity_color}">{activity_text}</span>'
            )
        delta_content = (
            "<br>".join(delta_parts) if delta_parts else ""
        )

        st.markdown(
            _kpi_html(
                label="Market Mood",
                value=friendly_regime,
                value_color=regime_color,
                delta=delta_content,
            ),
            unsafe_allow_html=True,
        )

    # -- 5. Win Rate -------------------------------------------------------
    with r2c2:
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

        # Wrap label with tooltip
        label_html = (
            '<span class="at-tooltip">Win Rate'
            '<span class="at-tooltip-text">'
            "How often your trades make money"
            "</span></span>"
        )

        st.markdown(
            _kpi_html(
                label=label_html,
                value=wr_display,
                value_color=COLORS["text_primary"],
                delta=wr_delta,
                raw_label=True,
            ),
            unsafe_allow_html=True,
        )

    # -- 6. Safety Level ---------------------------------------------------
    with r2c3:
        max_dd = getattr(data, "max_drawdown", 0.0)
        dd_pct = max_dd * 100

        if dd_pct < 5:
            safety_label = "Safe"
            safety_color = COLORS["profit"]
        elif dd_pct <= 10:
            safety_label = "Moderate"
            safety_color = COLORS["warning"]
        else:
            safety_label = "Elevated"
            safety_color = COLORS["loss"]

        delta_text = f"-{dd_pct:.1f}% drawdown" if max_dd > 0 else "0.0% drawdown"

        st.markdown(
            _kpi_html(
                label="Safety Level",
                value=safety_label,
                value_color=safety_color,
                delta=delta_text,
            ),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Private HTML builder
# ---------------------------------------------------------------------------

def _kpi_html(
    *,
    label: str,
    value: str,
    value_color: str,
    delta: str,
    raw_label: bool = False,
) -> str:
    """Build an at-kpi HTML card.

    Parameters
    ----------
    label:
        Card title text (plain text or raw HTML if *raw_label* is True).
    value:
        Main metric value.
    value_color:
        CSS color for the value text.
    delta:
        Sub-text below the value (may contain HTML spans).
    raw_label:
        If True, *label* is injected as-is (for tooltip HTML).
    """
    label_content = label if raw_label else label
    return (
        f'<div class="at-kpi">'
        f'<div class="at-kpi-label">{label_content}</div>'
        f'<div class="at-kpi-value" style="color:{value_color}">{value}</div>'
        f'<div class="at-kpi-delta">{delta}</div>'
        f"</div>"
    )
