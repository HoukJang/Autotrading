"""Event-driven rotation triggers based on regime changes and VIX spikes.

Supplements the weekly rotation schedule with mid-week rotation
when significant market regime changes are detected.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from autotrader.portfolio.regime_detector import MarketRegime
from autotrader.portfolio.regime_tracker import RegimeTransition

logger = logging.getLogger(__name__)


class EventDrivenRotation:
    """Determines when mid-week rotation should be triggered.

    Triggers on:
    - Configured regime transitions (e.g., ``TREND->HIGH_VOLATILITY``)
    - VIX spike above threshold

    Respects a cooldown period between triggers to prevent excessive rotation.

    Args:
        cooldown_hours: Minimum hours between consecutive triggers.
        vix_spike_trigger: VIX value threshold that triggers rotation.
        regime_triggers: List of ``"FROM->TO"`` patterns. Use ``"*"``
            as wildcard for either side.
        enabled: Whether event-driven rotation is active.
    """

    def __init__(
        self,
        cooldown_hours: int = 48,
        vix_spike_trigger: float = 30.0,
        regime_triggers: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._cooldown = timedelta(hours=cooldown_hours)
        self._vix_spike_trigger = vix_spike_trigger
        self._regime_triggers = regime_triggers or []
        self._enabled = enabled
        self._last_triggered: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_trigger_rotation(
        self,
        transition: RegimeTransition | None = None,
        vix_value: float | None = None,
    ) -> tuple[bool, str]:
        """Check if an event-driven rotation should be triggered.

        Args:
            transition: A confirmed regime transition from
                :class:`~autotrader.portfolio.regime_tracker.RegimeTracker`.
            vix_value: Current VIX value.

        Returns:
            Tuple of ``(should_trigger, reason_string)``.
            When ``should_trigger`` is ``False``, ``reason`` may explain
            why (e.g. cooldown active) or be empty when nothing matched.
        """
        if not self._enabled:
            return False, "event-driven rotation disabled"

        # Check cooldown
        if self._last_triggered is not None:
            elapsed = datetime.now(timezone.utc) - self._last_triggered
            if elapsed < self._cooldown:
                remaining = self._cooldown - elapsed
                return (
                    False,
                    f"cooldown active ({remaining.total_seconds() / 3600:.1f}h remaining)",
                )

        # Check regime transition triggers
        if transition is not None:
            for trigger in self._regime_triggers:
                parts = trigger.split("->")
                if len(parts) != 2:
                    logger.warning(
                        "Skipping malformed regime trigger pattern: %s", trigger
                    )
                    continue
                from_regime, to_regime = parts
                prev_match = (
                    from_regime == "*"
                    or from_regime == transition.previous.value
                )
                curr_match = (
                    to_regime == "*"
                    or to_regime == transition.current.value
                )
                if prev_match and curr_match:
                    logger.info(
                        "Event-driven rotation triggered: %s "
                        "(actual: %s->%s)",
                        trigger,
                        transition.previous.value,
                        transition.current.value,
                    )
                    return True, f"regime transition matched: {trigger}"

        # Check VIX spike
        if vix_value is not None and vix_value >= self._vix_spike_trigger:
            logger.info(
                "Event-driven rotation triggered: VIX %.1f >= %.1f",
                vix_value,
                self._vix_spike_trigger,
            )
            return True, f"VIX spike: {vix_value:.1f} >= {self._vix_spike_trigger}"

        return False, ""

    def mark_triggered(self) -> None:
        """Record that a rotation was triggered.

        Starts the cooldown timer from now.
        """
        self._last_triggered = datetime.now(timezone.utc)
        logger.info("Event-driven rotation marked as triggered; cooldown started.")
