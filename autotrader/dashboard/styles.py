"""Global CSS styles for the trading dashboard.

Provides reusable CSS classes for cards, KPIs, badges, empty states,
tooltips, and spacers.  Injected once at the top of live_app.py via
``st.markdown(get_global_css(), unsafe_allow_html=True)``.
"""
from __future__ import annotations

from autotrader.dashboard.theme import COLORS


def get_global_css() -> str:
    """Return a ``<style>`` block with all global dashboard CSS classes."""
    return f"""<style>
/* ── Card ─────────────────────────────────────────── */
.at-card {{
    background-color: {COLORS["bg_card"]};
    border: 1px solid {COLORS["bg_section"]};
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 10px;
}}

/* ── KPI card ─────────────────────────────────────── */
.at-kpi {{
    background-color: {COLORS["bg_card"]};
    border: 1px solid {COLORS["bg_section"]};
    border-radius: 10px;
    padding: 16px 18px;
    text-align: center;
    position: relative;
}}
.at-kpi .at-kpi-label {{
    color: {COLORS["text_muted"]};
    font-size: 0.82em;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
}}
.at-kpi .at-kpi-value {{
    font-size: 1.45em;
    font-weight: 700;
    line-height: 1.2;
}}
.at-kpi .at-kpi-delta {{
    color: {COLORS["text_muted"]};
    font-size: 0.78em;
    margin-top: 4px;
}}

/* ── Badge ────────────────────────────────────────── */
.at-badge {{
    display: inline-block;
    font-size: 0.75em;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
}}
.at-badge-safe {{
    background-color: {COLORS["profit"]}22;
    color: {COLORS["profit"]};
}}
.at-badge-caution {{
    background-color: {COLORS["warning"]}22;
    color: {COLORS["warning"]};
}}
.at-badge-danger {{
    background-color: {COLORS["loss"]}22;
    color: {COLORS["loss"]};
}}

/* ── Empty state ──────────────────────────────────── */
.at-empty {{
    background-color: {COLORS["bg_card"]};
    border: 1px solid {COLORS["bg_section"]};
    border-radius: 10px;
    padding: 36px 24px;
    text-align: center;
}}
.at-empty .at-empty-title {{
    color: {COLORS["text_secondary"]};
    font-size: 1.05em;
    font-weight: 600;
    margin-bottom: 8px;
}}
.at-empty .at-empty-desc {{
    color: {COLORS["text_muted"]};
    font-size: 0.88em;
    line-height: 1.6;
}}

/* ── Tooltip (CSS-only hover) ─────────────────────── */
.at-tooltip {{
    position: relative;
    cursor: help;
    border-bottom: 1px dotted {COLORS["text_muted"]};
}}
.at-tooltip .at-tooltip-text {{
    visibility: hidden;
    opacity: 0;
    position: absolute;
    bottom: 125%;
    left: 50%;
    transform: translateX(-50%);
    background-color: {COLORS["bg_section"]};
    color: {COLORS["text_secondary"]};
    font-size: 0.78em;
    font-weight: 400;
    padding: 6px 10px;
    border-radius: 6px;
    white-space: nowrap;
    z-index: 100;
    transition: opacity 0.2s;
    pointer-events: none;
}}
.at-tooltip:hover .at-tooltip-text {{
    visibility: visible;
    opacity: 1;
}}

/* ── Spacer ───────────────────────────────────────── */
.at-spacer {{
    margin-top: 12px;
    margin-bottom: 4px;
}}

/* ── Section caption ──────────────────────────────── */
.at-section-caption {{
    color: {COLORS["text_muted"]};
    font-size: 0.82em;
    margin-bottom: 10px;
}}
</style>"""
