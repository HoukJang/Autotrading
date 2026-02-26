"""Debounced regime change detection.

Wraps raw MarketRegime classification with a confirmation counter
to prevent regime flickering from triggering premature strategy changes.
A regime change must persist for N consecutive bars before being confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from autotrader.portfolio.regime_detector import MarketRegime


@dataclass(frozen=True)
class RegimeTransition:
    """Record of a confirmed regime change."""

    previous: MarketRegime
    current: MarketRegime
    timestamp: datetime
    bars_in_new_regime: int


class RegimeTracker:
    """Debounced regime tracker requiring confirmation bars.

    A regime change must persist for ``confirmation_bars`` consecutive
    :meth:`update` calls before being confirmed as a transition.
    """

    def __init__(self, confirmation_bars: int = 3) -> None:
        self._confirmation_bars = confirmation_bars
        self._confirmed_regime: MarketRegime = MarketRegime.UNCERTAIN
        self._pending_regime: MarketRegime | None = None
        self._pending_count: int = 0
        self._history: list[RegimeTransition] = []

    @property
    def confirmed_regime(self) -> MarketRegime:
        """The current confirmed (debounced) regime."""
        return self._confirmed_regime

    @property
    def history(self) -> list[RegimeTransition]:
        """List of all confirmed regime transitions, oldest first."""
        return list(self._history)

    def update(
        self, raw_regime: MarketRegime, timestamp: datetime
    ) -> RegimeTransition | None:
        """Process a new raw regime classification.

        Args:
            raw_regime: The latest raw regime from :class:`RegimeDetector`.
            timestamp: Timestamp of the bar that produced this classification.

        Returns:
            A :class:`RegimeTransition` if a confirmed change occurred,
            otherwise ``None``.
        """
        if raw_regime == self._confirmed_regime:
            # Same as confirmed -> reset any pending candidate
            self._pending_regime = None
            self._pending_count = 0
            return None

        if raw_regime == self._pending_regime:
            self._pending_count += 1
        else:
            self._pending_regime = raw_regime
            self._pending_count = 1

        if self._pending_count >= self._confirmation_bars:
            transition = RegimeTransition(
                previous=self._confirmed_regime,
                current=raw_regime,
                timestamp=timestamp,
                bars_in_new_regime=self._pending_count,
            )
            self._confirmed_regime = raw_regime
            self._pending_regime = None
            self._pending_count = 0
            self._history.append(transition)
            return transition

        return None
