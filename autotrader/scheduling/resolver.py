"""Startup catch-up resolver for missed scheduled events.

When the AutoTrader process starts after one or more scheduled event
times, this module determines which events need to be replayed and
returns them in dependency-safe (topological) order.

Typical usage::

    from autotrader.scheduling import StartupCatchUpResolver

    resolver = StartupCatchUpResolver()
    missed = resolver.resolve(now_et=datetime.now(ET), today_is_market_day=True)
    for event_name in missed:
        await fire_event(event_name)
"""
from __future__ import annotations

import heapq
import logging
from datetime import datetime

from autotrader.scheduling.events import (
    CatchUpPolicy,
    EventDefinition,
    TRADING_EVENTS,
)

logger = logging.getLogger("autotrader.scheduling.resolver")

# Nightly scan boundaries (minutes from midnight).
_NIGHTLY_SCAN_START = 20 * 60   # 20:00 (8 PM)
_MARKET_OPEN_APPROX = 9 * 60   # 09:00 (earliest morning event)


class StartupCatchUpResolver:
    """Resolve which trading events need catch-up when the system starts late.

    On system startup, determines which scheduled events were missed
    and returns them in dependency order for catch-up execution.

    The resolver applies each event's ``CatchUpPolicy`` to decide
    inclusion and uses topological sort on ``depends_on`` edges to
    guarantee correct execution order.
    """

    def __init__(
        self,
        events: dict[str, EventDefinition] | None = None,
    ) -> None:
        self._events = events or TRADING_EVENTS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        now_et: datetime,
        today_is_market_day: bool,
        already_fired: set[str] | None = None,
    ) -> list[str]:
        """Return an ordered list of event names to catch up.

        Args:
            now_et: Current time in US Eastern timezone.
            today_is_market_day: Whether today is a trading day
                (i.e., not a weekend or market holiday).
            already_fired: Event names already executed today
                (from persistent state).  These are excluded from
                catch-up regardless of policy.  ``None`` preserves
                backward-compatible behaviour (no filtering).

        Returns:
            List of event names in dependency-safe execution order.
            Empty list when nothing needs to be caught up.
        """
        now_minutes = now_et.hour * 60 + now_et.minute
        _skip = already_fired or set()

        candidates: list[str] = []
        for name, event in self._events.items():
            if name in _skip:
                logger.debug("Skipping already-fired event: %s", name)
                continue
            if self._should_catch_up(event, now_minutes, today_is_market_day):
                candidates.append(name)

        if not candidates:
            return []

        ordered = self._topological_sort(candidates)

        logger.info(
            "Catch-up resolver: %d event(s) to replay: %s",
            len(ordered),
            ", ".join(ordered),
        )
        return ordered

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _should_catch_up(
        self,
        event: EventDefinition,
        now_minutes: int,
        today_is_market_day: bool,
    ) -> bool:
        """Decide whether a single event should be included in catch-up.

        Args:
            event: The event definition to evaluate.
            now_minutes: Current time as minutes from midnight (ET).
            today_is_market_day: Whether today is a trading day.

        Returns:
            True if the event should be caught up.
        """
        # Nightly scan has its own cross-day logic.
        if event.name == "nightly_scan":
            return self._should_catch_up_nightly_scan(now_minutes)

        # All daytime trading events require a market day.
        if not today_is_market_day:
            return False

        scheduled = event.scheduled_hour * 60 + event.scheduled_minute

        # Event hasn't been missed yet (current time is before scheduled).
        if now_minutes < scheduled:
            return False

        policy = event.catch_up_policy

        if policy == CatchUpPolicy.SKIP:
            return False

        if policy == CatchUpPolicy.ALWAYS:
            return True

        if policy == CatchUpPolicy.CONDITIONAL:
            # When a deadline is specified, only catch up if now < deadline.
            # This prevents the event from running outside its meaningful
            # time window (e.g., gap_filter should only run pre-market).
            if event.catch_up_deadline_hour is not None:
                deadline_min = event.catch_up_deadline_minute or 0
                deadline = event.catch_up_deadline_hour * 60 + deadline_min
                return now_minutes < deadline
            return True

        if policy == CatchUpPolicy.WINDOW:
            if event.catch_up_deadline_hour is None:
                return True
            deadline_min = event.catch_up_deadline_minute or 0
            deadline = event.catch_up_deadline_hour * 60 + deadline_min
            return now_minutes < deadline

        return False

    def _should_catch_up_nightly_scan(self, now_minutes: int) -> bool:
        """Determine whether nightly_scan should be caught up.

        Nightly scan runs at 20:00 and produces candidates for the NEXT
        trading day.  It should be caught up in two windows:

        1. Same evening: system starts between 20:00-23:59.
        2. Next morning: system starts between 00:00-08:59 (before the
           first market event).  We assume the scan was not run overnight.

        Outside these windows the scan is not needed -- either it hasn't
        reached its scheduled time yet, or morning market events have
        already begun (the scan should have been completed before them).
        """
        if now_minutes >= _NIGHTLY_SCAN_START:
            return True
        if now_minutes < _MARKET_OPEN_APPROX:
            return True
        return False

    def _topological_sort(self, event_names: list[str]) -> list[str]:
        """Sort events by dependency order using Kahn's algorithm with a
        priority queue.

        Events with all dependencies satisfied are processed in
        chronological order (by scheduled time), ensuring that the output
        is both dependency-safe and time-ordered.

        Only events present in *event_names* are included in the output.
        Dependencies on events outside the candidate set are ignored
        (assumed already satisfied).

        Args:
            event_names: Candidate event names to sort.

        Returns:
            List of event names in valid execution order.

        Raises:
            ValueError: If a dependency cycle is detected.
        """
        name_set = set(event_names)

        # Build in-degree map and forward adjacency, considering only candidates.
        in_degree: dict[str, int] = {name: 0 for name in event_names}
        adjacency: dict[str, list[str]] = {name: [] for name in event_names}

        for name in event_names:
            event = self._events[name]
            for dep in event.depends_on:
                if dep in name_set:
                    in_degree[name] += 1
                    adjacency[dep].append(name)

        # Priority key: (scheduled_hour, scheduled_minute, name) for
        # deterministic chronological ordering among ready events.
        def _priority(n: str) -> tuple[int, int, str]:
            ev = self._events[n]
            return (ev.scheduled_hour, ev.scheduled_minute, n)

        # Seed the heap with zero-in-degree nodes.
        heap: list[tuple[tuple[int, int, str], str]] = []
        for name, degree in in_degree.items():
            if degree == 0:
                heapq.heappush(heap, (_priority(name), name))

        result: list[str] = []

        while heap:
            _, current = heapq.heappop(heap)
            result.append(current)
            for dependent in adjacency[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    heapq.heappush(heap, (_priority(dependent), dependent))

        if len(result) != len(event_names):
            unsorted = name_set - set(result)
            raise ValueError(
                f"Dependency cycle detected among events: {sorted(unsorted)}"
            )

        return result
