from __future__ import annotations

import warnings

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo

# DEPRECATED: This module is superseded by autotrader.trading.position_sizer
# which provides risk-based sizing with stop-distance awareness.
# This legacy class remains because main.py and backtest/simulator.py still
# reference it.  New code should use autotrader.trading.position_sizer.PositionSizer.


class PositionSizer:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def calculate(self, price: float, account: AccountInfo) -> int:
        if price <= 0:
            return 0
        max_value = account.equity * self._config.max_position_pct
        return int(max_value / price)
