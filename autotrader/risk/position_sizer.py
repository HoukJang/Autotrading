from __future__ import annotations

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo


class PositionSizer:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def calculate(self, price: float, account: AccountInfo) -> int:
        if price <= 0:
            return 0
        max_value = account.equity * self._config.max_position_pct
        return int(max_value / price)
