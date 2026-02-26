"""Rotation manager for weekly universe rotation and watchlist management."""
from __future__ import annotations

import logging
from datetime import datetime

from autotrader.core.config import RotationConfig
from autotrader.core.types import Signal
from autotrader.rotation.types import RotationState

logger = logging.getLogger(__name__)


class RotationManager:
    """Manages weekly rotation of trading universe with watchlist support.

    Sits as a signal filter between strategy signal generation and order
    execution. Strategies remain unaware of watchlists.
    """

    def __init__(
        self,
        config: RotationConfig,
        earnings_cal: object | None = None,
    ) -> None:
        self._config = config
        self._earnings_cal = earnings_cal
        self._state = RotationState()

    @property
    def active_symbols(self) -> list[str]:
        """Currently active trading symbols."""
        return list(self._state.active_symbols)

    @property
    def watchlist_symbols(self) -> list[str]:
        """Symbols on watchlist (rotated out but still holding positions)."""
        return list(self._state.watchlist.keys())

    @property
    def state(self) -> RotationState:
        """Current rotation state."""
        return self._state

    def filter_signals(self, signals: list[Signal]) -> list[Signal]:
        """Filter signals based on active universe and watchlist.

        - Close signals always pass through (for any symbol).
        - Entry signals (long/short) only pass for active symbols.
        - When halted, only close signals pass.
        """
        filtered: list[Signal] = []
        for sig in signals:
            if sig.direction == "close":
                filtered.append(sig)
                continue
            if self._state.is_halted:
                continue
            if sig.symbol in self._state.active_symbols:
                filtered.append(sig)
        return filtered
