"""Dashboard UI components for the AutoTrader v3 trading dashboard."""

from autotrader.dashboard.components.equity_chart import render_equity_section
from autotrader.dashboard.components.kpi_cards import render_kpi_cards
from autotrader.dashboard.components.position_panel import (
    render_position_panel,
    render_positions_tab,
)
from autotrader.dashboard.components.status_bar import render_status_bar
from autotrader.dashboard.components.strategy_analysis import render_strategy_analysis
from autotrader.dashboard.components.trade_log import render_trade_log
from autotrader.dashboard.components.scan_results import render_scan_results
from autotrader.dashboard.components.risk_dashboard import render_risk_dashboard

__all__ = [
    "render_equity_section",
    "render_kpi_cards",
    "render_position_panel",
    "render_positions_tab",
    "render_status_bar",
    "render_strategy_analysis",
    "render_trade_log",
    "render_scan_results",
    "render_risk_dashboard",
]
