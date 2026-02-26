"""Dashboard UI components for the upper section of the trading dashboard."""

from autotrader.dashboard.components.equity_chart import render_equity_section
from autotrader.dashboard.components.kpi_cards import render_kpi_cards
from autotrader.dashboard.components.position_panel import render_position_panel
from autotrader.dashboard.components.status_bar import render_status_bar

__all__ = [
    "render_equity_section",
    "render_kpi_cards",
    "render_position_panel",
    "render_status_bar",
]
