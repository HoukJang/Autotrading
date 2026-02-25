from __future__ import annotations

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo, Position, Signal


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._daily_pnl: float = 0.0
        self._peak_equity: float = 0.0

    def validate(self, signal: Signal, account: AccountInfo, positions: list[Position]) -> bool:
        if signal.direction == "close":
            return True
        return all([
            self._check_max_positions(positions),
            self._check_daily_loss(account),
            self._check_drawdown(account),
        ])

    def record_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    def update_peak(self, equity: float) -> None:
        if equity > self._peak_equity:
            self._peak_equity = equity

    def _check_max_positions(self, positions: list[Position]) -> bool:
        return len(positions) < self._config.max_open_positions

    def _check_daily_loss(self, account: AccountInfo) -> bool:
        limit = account.equity * self._config.daily_loss_limit_pct
        return abs(self._daily_pnl) < limit or self._daily_pnl >= 0

    def _check_drawdown(self, account: AccountInfo) -> bool:
        if self._peak_equity == 0:
            self._peak_equity = account.equity
            return True
        drawdown = (self._peak_equity - account.equity) / self._peak_equity
        return drawdown < self._config.max_drawdown_pct
