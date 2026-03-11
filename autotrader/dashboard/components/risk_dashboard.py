"""Risk dashboard component for the trading dashboard (Tab 5).

Renders real-time risk utilization metrics including drawdown, daily loss,
position counts, entry limits, and re-entry blocks.
"""
from __future__ import annotations

import streamlit as st

from autotrader.dashboard.data_loader import load_open_positions
from autotrader.dashboard.theme import COLORS
from autotrader.dashboard.utils.formatters import fmt_pct
from autotrader.trading.constants import MAX_DAILY_ENTRIES, MAX_LONG_POSITIONS


def render_risk_dashboard(risk_metrics, open_positions=None) -> None:
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

    st.subheader("Safety Overview")
    st.caption("How much of your risk budget is being used")

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
        max_pos = getattr(risk_metrics, "max_positions", MAX_LONG_POSITIONS)
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

    st.divider()

    # -- Row 4: Worst-case scenario and Traffic light --------------------
    col_worst, col_traffic = st.columns(2)

    with col_worst:
        _render_worst_case(risk_metrics)

    with col_traffic:
        _render_entry_traffic_light(risk_metrics)

    st.divider()

    # -- Row 5: Sector concentration ------------------------------------
    _render_sector_concentration(open_positions)


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
        Current value in the same unit as *limit* (e.g. 0.03 for 3%
        drawdown when limit is 0.15 for 15%).
    limit:
        The limit value.  The bar fills to ``current / limit``.
    format_fn:
        Callable to format the current value for display text.
    suffix_label:
        Text to append after the limit value (e.g., "limit").
    key:
        Unique key for the Streamlit progress widget.
    """
    usage_ratio = min(1.0, max(0.0, current / limit)) if limit > 0 else 0.0

    if usage_ratio >= 0.8:
        bar_color = COLORS["loss"]
        status_icon = "Danger"
        badge_class = "at-badge-danger"
    elif usage_ratio >= 0.5:
        bar_color = COLORS["warning"]
        status_icon = "Caution"
        badge_class = "at-badge-caution"
    else:
        bar_color = COLORS["profit"]
        status_icon = "Safe"
        badge_class = "at-badge-safe"

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
                <span class="{badge_class}" style="
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
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Long vs Short</div>',
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
    max_entries = getattr(risk_metrics, "max_entries_today", MAX_DAILY_ENTRIES)
    usage_ratio = min(1.0, entries_today / max_entries if max_entries > 0 else 0.0)

    if usage_ratio >= 1.0:
        color = COLORS["loss"]
        status = "Daily Limit"
    elif usage_ratio >= 0.67:
        color = COLORS["warning"]
        status = "Almost Full"
    else:
        color = COLORS["profit"]
        status = "Available"

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Trades Opened Today</div>',
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
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Stocks on Cooldown</div>',
        unsafe_allow_html=True,
    )

    if not reentry_blocks:
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.85em">No stocks on cooldown. All symbols are available for trading.</div>',
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
                {len(reentry_blocks)} stock(s) need a cooldown period before re-entry
            </div>
            <div>{badges_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_worst_case(risk_metrics) -> None:
    """Render worst-case scenario card showing total loss if all SLs hit."""
    worst_loss = getattr(risk_metrics, "worst_case_loss", 0.0)
    worst_pct = getattr(risk_metrics, "worst_case_pct", 0.0)
    positions = getattr(risk_metrics, "worst_case_positions", [])

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Maximum Risk</div>',
        unsafe_allow_html=True,
    )

    if not positions:
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.85em">No open positions.</div>',
            unsafe_allow_html=True,
        )
        return

    color = COLORS["loss"]
    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {color}44;
            border-radius: 8px;
            padding: 16px;
        ">
            <div style="color:{color};font-size:1.6em;font-weight:700;margin-bottom:4px">
                -${worst_loss:,.0f} (-{worst_pct*100:.1f}%)
            </div>
            <div style="color:{COLORS['text_muted']};font-size:0.82em;margin-bottom:10px">
                If all stop-losses hit simultaneously
            </div>
        """,
        unsafe_allow_html=True,
    )

    # Per-position breakdown
    for p in sorted(positions, key=lambda x: x.get("loss", 0)):
        loss = p.get("loss", 0)
        sym = p.get("symbol", "?")
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;font-size:0.82em;padding:2px 0">'
            f'<span style="color:{COLORS["text_secondary"]}">{sym}</span>'
            f'<span style="color:{color}">${loss:,.0f}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def _render_entry_traffic_light(risk_metrics) -> None:
    """Render entry gate status as a traffic light."""
    can_enter = getattr(risk_metrics, "can_enter_new", True)
    checks = getattr(risk_metrics, "entry_checks", [])

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Can We Open New Trades?</div>',
        unsafe_allow_html=True,
    )
    st.caption("All conditions must pass before the system opens new positions")

    # Big YES/NO badge
    if can_enter:
        badge_color = COLORS["profit"]
        badge_text = "Open for Trading"
    else:
        badge_color = COLORS["loss"]
        badge_text = "Trading Paused"

    st.markdown(
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {badge_color}44;
            border-radius: 8px;
            padding: 16px;
        ">
            <div style="
                display:inline-block;
                background-color:{badge_color}22;
                color:{badge_color};
                font-size:1.2em;
                font-weight:700;
                padding:6px 16px;
                border-radius:6px;
                margin-bottom:12px;
            ">{badge_text}</div>
        """,
        unsafe_allow_html=True,
    )

    # Individual checks
    for check in checks:
        ok = check.get("ok", True)
        name = check.get("name", "")
        detail = check.get("detail", "")
        icon_color = COLORS["profit"] if ok else COLORS["loss"]
        icon = "Pass" if ok else "Blocked"
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'font-size:0.82em;padding:3px 0">'
            f'<span style="color:{COLORS["text_secondary"]}">{name}</span>'
            f'<div style="display:flex;gap:8px;align-items:center">'
            f'<span style="color:{COLORS["text_muted"]}">{detail}</span>'
            f'<span style="color:{icon_color};font-weight:700;font-size:0.85em">{icon}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def _render_sector_concentration(open_positions=None) -> None:
    """Render sector concentration of open positions."""
    from autotrader.dashboard.utils.metrics import SP500_SECTORS

    st.markdown(
        f'<div style="color:{COLORS["text_secondary"]};font-size:0.9em;font-weight:600;margin-bottom:8px">Sector Spread</div>',
        unsafe_allow_html=True,
    )

    if not open_positions:
        positions = load_open_positions()
    else:
        positions = open_positions

    if not positions:
        st.markdown(
            f'<div style="color:{COLORS["text_muted"]};font-size:0.85em">No open positions for sector analysis.</div>',
            unsafe_allow_html=True,
        )
        return

    sector_counts: dict[str, int] = {}
    for sym in positions:
        sector = SP500_SECTORS.get(sym, "Other")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    total = sum(sector_counts.values())
    if total == 0:
        return

    # Sort by count descending
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])

    st.markdown(
        f'<div style="background-color:{COLORS["bg_card"]};border:1px solid {COLORS["bg_section"]};'
        f'border-radius:8px;padding:12px 16px">',
        unsafe_allow_html=True,
    )

    for sector, count in sorted_sectors:
        pct = count / total * 100
        bar_color = COLORS["warning"] if pct >= 50 else COLORS["info"]
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'font-size:0.85em;padding:4px 0">'
            f'<span style="color:{COLORS["text_secondary"]}">{sector}</span>'
            f'<div style="display:flex;gap:8px;align-items:center">'
            f'<div style="background:{COLORS["bg_section"]};border-radius:3px;width:80px;height:4px;overflow:hidden">'
            f'<div style="background:{bar_color};width:{pct:.0f}%;height:100%"></div></div>'
            f'<span style="color:{bar_color};font-weight:600">{count} ({pct:.0f}%)</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # Warning if any sector > 50% (only meaningful with 4+ positions)
    if total >= 4:
        for sector, count in sorted_sectors:
            if count / total >= 0.5:
                st.markdown(
                    f'<div style="color:{COLORS["warning"]};font-size:0.8em;margin-top:8px">'
                    f'Warning: {sector} concentration at {count/total*100:.0f}%</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)
