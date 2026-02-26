from __future__ import annotations

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo, Position, Signal


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._daily_pnl: float = 0.0
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0

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

    def reset_daily_pnl(self) -> None:
        """Reset daily PnL accumulator to zero.

        Called at the start of each trading day to begin fresh daily tracking.
        """
        self._daily_pnl = 0.0

    def reset_peak_equity(self, current_equity: float) -> None:
        """Reset peak equity to given value and clear daily PnL.

        Called on weekly rotation to prevent permanent drawdown lockout.
        After a drawdown limit is hit, the rotation resets the baseline
        so the system can resume trading in the new rotation cycle.

        Args:
            current_equity: The current account equity to use as the new peak.
        """
        self._peak_equity = current_equity
        self._current_equity = current_equity
        self._daily_pnl = 0.0

    def update_peak(self, equity: float) -> None:
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

    @property
    def get_drawdown(self) -> float:
        """Return current drawdown as a percentage (0.0 to 1.0).

        Returns:
            Current drawdown fraction. 0.0 means at peak, 0.10 means 10% below peak.
            Returns 0.0 if peak equity has not been set yet.
        """
        if self._peak_equity <= 0:
            return 0.0
        drawdown = (self._peak_equity - self._current_equity) / self._peak_equity
        return max(0.0, drawdown)

    def _check_max_positions(self, positions: list[Position]) -> bool:
        return len(positions) < self._config.max_open_positions

    def _check_daily_loss(self, account: AccountInfo) -> bool:
        limit = account.equity * self._config.daily_loss_limit_pct
        return abs(self._daily_pnl) < limit or self._daily_pnl >= 0

    def _check_drawdown(self, account: AccountInfo) -> bool:
        if self._peak_equity == 0:
            self._peak_equity = account.equity
            self._current_equity = account.equity
            return True
        self._current_equity = account.equity
        if account.equity > self._peak_equity:
            self._peak_equity = account.equity
        drawdown = (self._peak_equity - account.equity) / self._peak_equity
        return drawdown < self._config.max_drawdown_pct
