"""Formatting utilities for the trading dashboard."""
from __future__ import annotations

from autotrader.dashboard.theme import COLORS


def fmt_currency(value: float) -> str:
    """Format a dollar amount as ``$1,234.56`` or ``$-1,234.56``."""
    if value < 0:
        return f"$-{abs(value):,.2f}"
    return f"${value:,.2f}"


def fmt_pnl(value: float) -> str:
    """Format a PnL value with an explicit sign: ``+$1,234.56`` / ``-$1,234.56``."""
    if value >= 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def fmt_pct(value: float) -> str:
    """Format a ratio as a percentage string (0.123 -> ``12.3%``)."""
    return f"{value * 100:.1f}%"


def fmt_pnl_pct(value: float) -> str:
    """Format a ratio as a signed percentage (0.123 -> ``+12.3%``)."""
    pct = value * 100
    if pct >= 0:
        return f"+{pct:.1f}%"
    return f"{pct:.1f}%"


def fmt_delta_time(seconds: float) -> str:
    """Format a time delta into a human-readable Korean string.

    Returns:
        - "just now" equivalent if <60 seconds
        - "N min ago" equivalent if <3600 seconds
        - "N hr ago" equivalent otherwise
    """
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}min ago"
    hours = int(seconds // 3600)
    return f"{hours}hr ago"


def pnl_color(value: float) -> str:
    """Return the appropriate hex color for a PnL value.

    Positive values get the profit color, negative get the loss color,
    and zero gets the neutral color.
    """
    if value > 0:
        return COLORS["profit"]
    if value < 0:
        return COLORS["loss"]
    return COLORS["neutral"]
