"""Risk dashboard component for the trading dashboard (Tab 5).

Renders real-time risk utilization metrics including drawdown, daily loss,
position counts, entry limits, and re-entry blocks.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.theme import COLORS
from autotrader.dashboard.utils.formatters import fmt_pct


def render_risk_dashboard(risk_metrics) -> None:
    """Render the risk dashboard tab with metrics and visual limit bars.

    Parameters
    ----------
    risk_metrics:
        A RiskMetrics instance with fields: current_drawdown_pct,
        max_drawdown_limit_pct, today_loss_pct, daily_loss_limit_pct,
        open_positions_count, max_positions, long_count, short_count,
        entries_today, max_entries_today, reentry_blocks.
    """
    if risk_metrics is None:
        st.info("Risk metrics not available.")
        return

    st.subheader("Risk Utilization")

    # -- Row 1: Three main risk bars ----------------------------------------
    col_dd, col_daily, col_pos = st.columns(3)

    with col_dd:
        _render_limit_bar(
            label="Max Drawdown",
            current=getattr(risk_metrics, "current_drawdown_pct", 0.0),
            limit=getattr(risk_metrics, "max_drawdown_limit_pct", 0.15),
            format_fn=lambda v: fmt_pct(v),
            suffix_label="limit",
            key="dd_bar",
        )

    with col_daily:
        _render_limit_bar(
            label="Daily Loss",
            current=getattr(risk_metrics, "today_loss_pct", 0.0),
            limit=getattr(risk_metrics, "daily_loss_limit_pct", 0.02),
            format_fn=lambda v: fmt_pct(v),
            suffix_label="limit",
            key="daily_bar",
        )

    with col_pos:
        open_count = getattr(risk_metrics, "open_positions_count", 0)
        max_pos = getattr(risk_metrics, "max_positions", 8)
        _render_limit_bar(
            label="Position Slots",
            current=open_count / max_pos if max_pos > 0 else 0.0,
            limit=1.0,
            format_fn=lambda v: f"{int(v * max_pos)} / {max_pos}",
            suffix_label="max",
            key="pos_bar",
        )

    st.divider()

    # -- Row 2: Direction exposure and entry count --------------------------
    col_dir, col_entries = st.columns([1, 1])

    with col_dir:
        _render_direction_exposure(risk_metrics)

    with col_entries:
        _render_entry_count(risk_metrics)

    st.divider()

    # -- Row 3: Re-entry blocks ---------------------------------------------
    _render_reentry_blocks(risk_metrics)


def _render_limit_bar(
    label: str,
    current: float,
    limit: float,
    format_fn,
    suffix_label: str,
    key: str,
) -> None:
    """Render a single risk limit bar with color-coded progress.

    Green < 50%, Yellow 50-80%, Red > 80% of the limit.

    Parameters
    ----------
    label:
        Display label for the metric.
    current:
        Current ratio (0.0 to 1.0+) where 1.0 = at limit.
    limit:
        The limit value (used for display only, current is pre-normalized).
    format_fn:
        Callable to format the current value for display text.
    suffix_label:
        Text to append after the limit value (e.g., "limit").
    key:
        Unique key for the Streamlit progress widget.
    """
    usage_ratio = min(1.0, max(0.0, current))

    if usage_ratio >= 0.8:
        bar_color = COLORS["loss"]
        status_icon = "CRITICAL"
    elif usage_ratio >= 0.5:
        bar_color = COLORS["warning"]
        status_icon = "WARNING"
    else:
        bar_color = COLORS["profit"]
        status_icon = "OK"

    # Format display values
    current_display = format_fn(current)
    limit_display = format_fn(1.0) if limit == 1.0 else fmt_pct(limit)
    pct_used = f"{usage_ratio * 100:.0f}%"

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['bg_section']};
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 8px;
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            ">
                <span style="color:{COLORS['text_secondary']};font-size:0.9em;font-weight:600">{label}</span>
                <span style="
                    color: {bar_color};
                    font-size: 0.75em;
                    font-weight: 700;
                    background-color: {bar_color}22;
                    padding: 2px 8px;
                    border-radius: 4px;
                ">{status_icon}</span>
            </div>
            <div style="
                display: flex;
                justify-content: space-between;
                margin-bottom: 6px;
            ">
                <span style="color:{bar_color};font-size:1.3em;font-weight:700">{current_display}</span>
                <span style="color:{COLORS['text_muted']};font-size:0.85em">{pct_used} used</span>
            </div>
            <div style="
                background-color: {COLORS['bg_section']};
                border-radius: 4px;
                height: 6px;
                overflow: hidden;
            ">
                <div style="
                    background-color: {bar_color};
                    width: {usage_ratio * 100:.1f}%;
                    height: 100%;
                    border-radius: 4px;
                    transition: width 0.3s ease;
                "></div>
            </div>
            <div style="color:{COLORS['text_muted']};font-size:0.78em;margin-top:4px">
                Limit: {limit_display}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_direction_exposure(risk_metrics) -> None:
    """Render long vs short position direction breakdown."""
    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Direction Exposure</div>',
        unsafe_allow_html=True,
    )

    long_count = getattr(risk_metrics, "long_count", 0)
    short_count = getattr(risk_metrics, "short_count", 0)
    total = long_count + short_count

    col_long, col_short = st.columns(2)

    with col_long:
        st.markdown(
            f"""
            <div style="
                background-color: {COLORS['profit']}22;
                border: 1px solid {COLORS['profit']}44;
                border-radius: 8px;
                padding: 16px;
                text-align: center;
            ">
                <div style="color:{COLORS['text_muted']};font-size:0.8em;margin-bottom:4px">LONG</div>
                <div style="color:{COLORS['profit']};font-size:1.8em;font-weight:700">{long_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_short:
        st.markdown(
            f"""
            <div style="
                background-color: {COLORS['loss']}22;
                border: 1px solid {COLORS['loss']}44;
                border-radius: 8px;
                padding: 16px;
                text-align: center;
            ">
                <div style="color:{COLORS['text_muted']};font-size:0.8em;margin-bottom:4px">SHORT</div>
                <div style="color:{COLORS['loss']};font-size:1.8em;font-weight:700">{short_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if total > 0:
        long_pct = long_count / total * 100
        short_pct = short_count / total * 100
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.8em;margin-top:6px">'
            f'Long: {long_pct:.0f}% | Short: {short_pct:.0f}%</div>',
            unsafe_allow_html=True,
        )


def _render_entry_count(risk_metrics) -> None:
    """Render today's entry count vs daily limit."""
    entries_today = getattr(risk_metrics, "entries_today", 0)
    max_entries = getattr(risk_metrics, "max_entries_today", 3)
    usage_ratio = min(1.0, entries_today / max_entries if max_entries > 0 else 0.0)

    if usage_ratio >= 1.0:
        color = COLORS["loss"]
        status = "LIMIT REACHED"
    elif usage_ratio >= 0.67:
        color = COLORS["warning"]
        status = "NEAR LIMIT"
    else:
        color = COLORS["profit"]
        status = "OK"

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Daily Entry Count</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['bg_section']};
            border-radius: 8px;
            padding: 16px;
        ">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                <span style="color:{color};font-size:1.8em;font-weight:700">{entries_today} / {max_entries}</span>
                <span style="
                    color:{color};font-size:0.75em;font-weight:700;
                    background-color:{color}22;padding:2px 8px;border-radius:4px
                ">{status}</span>
            </div>
            <div style="
                background-color:{COLORS['bg_section']};
                border-radius:4px;height:6px;overflow:hidden
            ">
                <div style="
                    background-color:{color};
                    width:{usage_ratio * 100:.1f}%;
                    height:100%;border-radius:4px
                "></div>
            </div>
            <div style="color:{COLORS['text_muted']};font-size:0.78em;margin-top:4px">
                Max {max_entries} new entries per trading day
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_reentry_blocks(risk_metrics) -> None:
    """Render the list of symbols blocked from re-entry today."""
    reentry_blocks = getattr(risk_metrics, "reentry_blocks", [])

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Re-entry Blocks (Today)</div>',
        unsafe_allow_html=True,
    )

    if not reentry_blocks:
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.85em">No re-entry blocks active today.</div>',
            unsafe_allow_html=True,
        )
        return

    # Render each blocked symbol as a badge
    badges_html = " ".join(
        f'<span style="'
        f'display:inline-block;'
        f'background-color:{COLORS["warning"]}22;'
        f'color:{COLORS["warning"]};'
        f'border:1px solid {COLORS["warning"]}44;'
        f'border-radius:4px;'
        f'padding:3px 10px;'
        f'margin:3px;'
        f'font-size:0.85em;'
        f'font-weight:600;'
        f'">{symbol}</span>'
        for symbol in reentry_blocks
    )

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['bg_section']};
            border-radius: 8px;
            padding: 12px 16px;
        ">
            <div style="color:{COLORS['warning']};font-size:0.8em;margin-bottom:8px">
                {len(reentry_blocks)} symbol(s) blocked from re-entry today
            </div>
            <div>{badges_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
