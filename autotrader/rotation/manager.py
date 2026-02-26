"""Rotation manager for weekly universe rotation and watchlist management."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from autotrader.core.config import RotationConfig
from autotrader.core.types import Signal
from autotrader.rotation.types import RotationEvent, RotationState, WatchlistEntry
from autotrader.universe import UniverseResult

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

    def apply_rotation(
        self,
        universe: UniverseResult,
        open_position_symbols: list[str],
        new_equity: float | None = None,
    ) -> RotationEvent:
        """Apply a new universe rotation.

        Symbols rotated out with open positions go to watchlist.
        Symbols rotated out without positions are dropped immediately.
        Symbols returning from watchlist are removed from watchlist.
        """
        watchlist_added: list[str] = []
        watchlist_removed: list[str] = []

        # Remove symbols from watchlist if they're back in the new universe
        for sym in list(self._state.watchlist.keys()):
            if sym in universe.symbols:
                del self._state.watchlist[sym]
                watchlist_removed.append(sym)

        # Move rotated-out symbols with open positions to watchlist
        for sym in universe.rotation_out:
            if sym in open_position_symbols and sym not in self._state.watchlist:
                deadline = self._compute_deadline(universe.timestamp)
                self._state.watchlist[sym] = WatchlistEntry(
                    symbol=sym,
                    added_at=universe.timestamp,
                    deadline=deadline,
                )
                watchlist_added.append(sym)

        # Update active symbols
        self._state.active_symbols = list(universe.symbols)
        self._state.last_rotation = universe.timestamp

        # Reset halt state and update weekly equity on new rotation
        self._state.is_halted = False
        if new_equity is not None:
            self._state.weekly_start_equity = new_equity

        event = RotationEvent(
            timestamp=universe.timestamp,
            symbols_in=list(universe.rotation_in),
            symbols_out=list(universe.rotation_out),
            watchlist_added=watchlist_added,
            watchlist_removed=watchlist_removed,
            active_count=len(self._state.active_symbols),
            watchlist_count=len(self._state.watchlist),
        )
        self._state.rotation_history.append(event)

        logger.info(
            "Rotation applied: %d active, %d watchlist, +%d/-%d symbols",
            event.active_count,
            event.watchlist_count,
            len(event.symbols_in),
            len(event.symbols_out),
        )
        return event

    def _compute_deadline(self, rotation_timestamp: datetime) -> datetime:
        """Compute the force-close deadline (next configured day/hour)."""
        target_day = self._config.force_close_day
        target_hour = self._config.force_close_hour
        dt = rotation_timestamp
        # Find the next occurrence of target_day
        days_ahead = (target_day - dt.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        deadline = dt.replace(
            hour=target_hour, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        return deadline

    def get_force_close_symbols(
        self,
        current_time: datetime,
        open_position_symbols: list[str],
    ) -> list[str]:
        """Get symbols that should be force-closed now.

        Returns symbols from the watchlist that are past their deadline
        and still have open positions. When halted, returns all open positions.
        Also checks earnings calendar for E-3 force close.
        """
        if self._state.is_halted:
            return list(open_position_symbols)

        force_close: list[str] = []

        # Watchlist deadline force close
        for sym, entry in self._state.watchlist.items():
            if sym in open_position_symbols and entry.is_past_deadline(current_time):
                force_close.append(sym)

        # Earnings E-3 force close
        if self._earnings_cal is not None:
            check_date = current_time.date() if hasattr(current_time, "date") else current_time
            for sym in open_position_symbols:
                if sym not in force_close and self._earnings_cal.should_force_close(sym, check_date):
                    force_close.append(sym)

        return force_close

    def check_weekly_loss_limit(self, current_equity: float) -> bool:
        """Check if weekly loss limit has been breached.

        Returns True if breached (and sets halted state).
        """
        if self._state.weekly_start_equity <= 0:
            return False
        loss_pct = (
            (self._state.weekly_start_equity - current_equity)
            / self._state.weekly_start_equity
        )
        if loss_pct >= self._config.weekly_loss_limit_pct:
            self._state.is_halted = True
            logger.warning(
                "Weekly loss limit breached: %.2f%% (limit: %.2f%%)",
                loss_pct * 100,
                self._config.weekly_loss_limit_pct * 100,
            )
            return True
        return False

    def on_position_closed(self, symbol: str) -> None:
        """Notify that a position has been closed (natural exit or force close).

        Removes the symbol from watchlist if present.
        """
        if symbol in self._state.watchlist:
            del self._state.watchlist[symbol]
            logger.info("Watchlist symbol %s position closed, removed from watchlist", symbol)
