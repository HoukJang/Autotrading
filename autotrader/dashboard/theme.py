"""Dashboard theme constants - dark trading terminal style."""


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a hex color string to an rgba() CSS string."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


# ---------------------------------------------------------------------------
# Core palette
# ---------------------------------------------------------------------------
COLORS = {
    # Background layers
    "bg_primary": "#0E1117",
    "bg_card": "#1A1D23",
    "bg_section": "#262730",
    "bg_hover": "#2D3039",
    # Text
    "text_primary": "#FAFAFA",
    "text_secondary": "#A0A4AB",
    "text_muted": "#6B7280",
    # Semantic
    "profit": "#00D26A",
    "loss": "#FF4757",
    "warning": "#FFA502",
    "info": "#3B82F6",
    "neutral": "#6B7280",
}

# ---------------------------------------------------------------------------
# Regime colors (solid)
# ---------------------------------------------------------------------------
REGIME_COLORS = {
    "TREND_UP": "#00D26A",
    "TREND_DOWN": "#FF4757",
    "RANGING": "#3B82F6",
    "HIGH_VOLATILITY": "#FFA502",
    "UNCERTAIN": "#6B7280",
}

# ---------------------------------------------------------------------------
# Regime tints (low-opacity backgrounds for chart bands)
# ---------------------------------------------------------------------------
REGIME_TINTS = {
    regime: _hex_to_rgba(color, 0.08)
    for regime, color in REGIME_COLORS.items()
}

# ---------------------------------------------------------------------------
# Strategy colors
# ---------------------------------------------------------------------------
STRATEGY_COLORS = {
    "breakout_momentum": "#F59E0B",
    "rsi_mean_reversion": "#8B5CF6",
}

# ---------------------------------------------------------------------------
# Strategy display names
# ---------------------------------------------------------------------------
STRATEGY_NAMES = {
    "breakout_momentum": "Breakout Momentum",
    "rsi_mean_reversion": "RSI Mean Reversion",
    "rotation_manager": "Rotation Manager",
}
