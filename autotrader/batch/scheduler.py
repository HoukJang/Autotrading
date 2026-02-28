"""BatchScheduler: asyncio-based scheduler for the nightly batch pipeline.

Scheduled tasks (all times in US/Eastern):
    20:00 ET  -- NIGHTLY_SCAN    Run NightlyScanner for the next trading day
    09:25 ET  -- GAP_FILTER      Run GapFilter on the 12 ranked candidates
    09:30 ET  -- MARKET_OPEN     Market open notification / signal dispatch hook
    09:45 ET  -- OPEN_MONITOR    Post-open price check (optional hook)
    10:00 ET  -- POST_OPEN       Confirm open positions are in line with signals

Market awareness:
    - Skips weekends (Saturday, Sunday) automatically.
    - Skips NYSE market holidays using a built-in holiday set for the next
      few years (extendable).  No external API required.

Retry policy:
    Each task is retried up to MAX_RETRIES times with exponential backoff
    (base=30s) on failure before being abandoned for that session.

Dashboard integration:
    next_event() returns a dict describing the next scheduled task so the
    Streamlit dashboard can display it without polling the scheduler loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("US/Eastern")

# Retry settings
_MAX_RETRIES = 3
_BACKOFF_BASE_SECS = 30.0

# Named task IDs
TASK_NIGHTLY_SCAN = "NIGHTLY_SCAN"
TASK_GAP_FILTER = "GAP_FILTER"
TASK_MARKET_OPEN = "MARKET_OPEN"
TASK_OPEN_MONITOR = "OPEN_MONITOR"
TASK_POST_OPEN = "POST_OPEN"

# Default schedule: (task_id, hour, minute) all in ET
_DEFAULT_SCHEDULE: list[tuple[str, int, int]] = [
    (TASK_NIGHTLY_SCAN, 20, 0),
    (TASK_GAP_FILTER, 9, 25),
    (TASK_MARKET_OPEN, 9, 30),
    (TASK_OPEN_MONITOR, 9, 45),
    (TASK_POST_OPEN, 10, 0),
]

# NYSE market holidays (add years as needed).
# Format: date(year, month, day)
_NYSE_HOLIDAYS: frozenset[date] = frozenset(
    [
        # 2025
        date(2025, 1, 1),   # New Year's Day
        date(2025, 1, 20),  # MLK Day
        date(2025, 2, 17),  # Presidents' Day
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day
        date(2025, 6, 19),  # Juneteenth
        date(2025, 7, 4),   # Independence Day
        date(2025, 9, 1),   # Labor Day
        date(2025, 11, 27), # Thanksgiving
        date(2025, 12, 25), # Christmas
        # 2026
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # MLK Day
        date(2026, 2, 16),  # Presidents' Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
    ]
)


def _is_trading_day(d: date) -> bool:
    """Return True if *d* is a NYSE trading day (not weekend or holiday)."""
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    return d not in _NYSE_HOLIDAYS


def _next_trading_day(reference: date) -> date:
    """Return the next trading day >= reference."""
    d = reference
    while not _is_trading_day(d):
        d += timedelta(days=1)
    return d


@dataclass
class ScheduledTask:
    """Metadata for a single scheduled task entry."""

    task_id: str
    hour: int    # ET hour
    minute: int  # ET minute
    callback: Callable[[], Awaitable[Any]]
    # Dynamic state
    last_run_at: datetime | None = None
    last_status: str = "pending"  # "pending", "running", "success", "failed"
    run_count: int = 0
    error_count: int = 0


@dataclass
class NextEventInfo:
    """Information about the next scheduled event, for dashboard display."""

    task_id: str
    scheduled_at: datetime  # UTC
    seconds_until: float


class BatchScheduler:
    """asyncio-based scheduler for the nightly batch pipeline.

    Usage::

        scheduler = BatchScheduler()
        scheduler.register(TASK_NIGHTLY_SCAN, scanner.run_scheduled)
        scheduler.register(TASK_GAP_FILTER, gap_filter.run_scheduled)
        await scheduler.run_forever()

    The scheduler loop sleeps until the next scheduled task, fires it,
    and then sleeps again.  It is safe to call stop() from another
    coroutine or from a signal handler.
    """

    def __init__(
        self,
        schedule: list[tuple[str, int, int]] | None = None,
    ) -> None:
        """
        Args:
            schedule: List of (task_id, hour_ET, minute_ET) tuples.
                      Defaults to _DEFAULT_SCHEDULE if not provided.
        """
        raw_schedule = schedule if schedule is not None else _DEFAULT_SCHEDULE
        self._schedule_config: list[tuple[str, int, int]] = raw_schedule
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        task_id: str,
        callback: Callable[[], Awaitable[Any]],
    ) -> None:
        """Register a callback for a named task.

        The task_id must appear in the schedule config or be added via
        add_schedule_entry().  If called multiple times with the same
        task_id, the callback is replaced.

        Args:
            task_id: One of the TASK_* constants (or a custom string).
            callback: Async callable with no required arguments.
        """
        # Find the schedule entry to get hour/minute
        matching = [
            (h, m) for tid, h, m in self._schedule_config if tid == task_id
        ]
        if not matching:
            raise ValueError(
                f"task_id '{task_id}' is not in the scheduler config. "
                f"Available: {[t for t, _, _ in self._schedule_config]}"
            )
        hour, minute = matching[0]

        if task_id in self._tasks:
            self._tasks[task_id].callback = callback
            logger.debug("BatchScheduler: updated callback for %s", task_id)
        else:
            self._tasks[task_id] = ScheduledTask(
                task_id=task_id,
                hour=hour,
                minute=minute,
                callback=callback,
            )
            logger.debug(
                "BatchScheduler: registered %s at %02d:%02d ET", task_id, hour, minute
            )

    def add_schedule_entry(
        self,
        task_id: str,
        hour: int,
        minute: int,
        callback: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """Add a new schedule entry (not in the default config).

        Args:
            task_id: Unique task identifier.
            hour: ET hour (0-23).
            minute: ET minute (0-59).
            callback: Optional async callable; can be set later via register().
        """
        self._schedule_config.append((task_id, hour, minute))
        if callback is not None:
            self._tasks[task_id] = ScheduledTask(
                task_id=task_id,
                hour=hour,
                minute=minute,
                callback=callback,
            )

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Start the scheduler loop and run until stop() is called.

        The loop:
            1. Determines the next task to run (across all registered tasks).
            2. Sleeps until that task's scheduled time.
            3. Checks if the target date is a trading day; if not, skips.
            4. Executes the task with retry/backoff.
            5. Repeats.
        """
        self._running = True
        self._stop_event.clear()
        logger.info(
            "BatchScheduler: starting with %d registered tasks", len(self._tasks)
        )

        while not self._stop_event.is_set():
            next_run = self._compute_next_run()
            if next_run is None:
                logger.warning(
                    "BatchScheduler: no tasks registered; sleeping 60s"
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            task, fire_at_utc = next_run
            now_utc = datetime.now(tz=ET).astimezone().__class__.now(
                tz=__import__("datetime").timezone.utc
            )
            wait_secs = max(0.0, (fire_at_utc - now_utc).total_seconds())

            logger.info(
                "BatchScheduler: next task '%s' at %s ET (%.0fs from now)",
                task.task_id,
                fire_at_utc.astimezone(ET).strftime("%Y-%m-%d %H:%M"),
                wait_secs,
            )

            # Sleep until scheduled time (interruptible by stop())
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=wait_secs
                )
                # stop_event was set during wait
                break
            except asyncio.TimeoutError:
                pass  # expected: time elapsed, run the task

            if self._stop_event.is_set():
                break

            # Confirm this date is a trading day
            fire_date_et = fire_at_utc.astimezone(ET).date()
            if not _is_trading_day(fire_date_et):
                logger.info(
                    "BatchScheduler: skipping '%s' on %s (non-trading day)",
                    task.task_id,
                    fire_date_et,
                )
                # Mark as skipped so _compute_next_run advances past this slot
                task.last_run_at = fire_at_utc
                task.last_status = "skipped"
                continue

            # Execute with retries
            await self._execute_with_retry(task)

        self._running = False
        logger.info("BatchScheduler: stopped")

    def stop(self) -> None:
        """Signal the scheduler loop to stop after the current sleep finishes."""
        logger.info("BatchScheduler: stop requested")
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Dashboard integration
    # ------------------------------------------------------------------

    def next_event(self) -> NextEventInfo | None:
        """Return information about the next scheduled event.

        Returns None if no tasks are registered.  Useful for dashboard
        display without polling the internal scheduler state.
        """
        next_run = self._compute_next_run()
        if next_run is None:
            return None

        task, fire_at_utc = next_run
        from datetime import timezone as _tz
        now_utc = datetime.now(tz=_tz.utc)
        secs = max(0.0, (fire_at_utc - now_utc).total_seconds())
        return NextEventInfo(
            task_id=task.task_id,
            scheduled_at=fire_at_utc,
            seconds_until=secs,
        )

    def task_status(self) -> list[dict[str, Any]]:
        """Return current status of all registered tasks for dashboard display."""
        return [
            {
                "task_id": t.task_id,
                "scheduled_et": f"{t.hour:02d}:{t.minute:02d}",
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "last_status": t.last_status,
                "run_count": t.run_count,
                "error_count": t.error_count,
            }
            for t in sorted(self._tasks.values(), key=lambda x: (x.hour, x.minute))
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_next_run(
        self,
    ) -> tuple[ScheduledTask, datetime] | None:
        """Find the task with the earliest upcoming fire time.

        For each registered task, compute when it should next run:
            - If it has never run, compute the next occurrence of its
              (hour, minute) in ET from now.
            - If it last ran today (or later), schedule for the next
              calendar day's occurrence.

        Returns:
            Tuple of (task, fire_at_utc) or None if no tasks registered.
        """
        if not self._tasks:
            return None

        from datetime import timezone as _tz
        now_et = datetime.now(tz=ET)

        best_task: ScheduledTask | None = None
        best_fire: datetime | None = None

        for task in self._tasks.values():
            fire_et = _next_occurrence_et(now_et, task.hour, task.minute)
            # If we just ran this task (within the last 60 seconds), advance to tomorrow
            if task.last_run_at is not None:
                last_run_et = task.last_run_at.astimezone(ET)
                if last_run_et.date() == fire_et.date() and last_run_et.hour == task.hour:
                    # Already ran today at this hour -> schedule for tomorrow same time
                    fire_et = fire_et + timedelta(days=1)
                    fire_et = fire_et.replace(
                        hour=task.hour,
                        minute=task.minute,
                        second=0,
                        microsecond=0,
                    )

            fire_utc = fire_et.astimezone(_tz.utc)

            if best_fire is None or fire_utc < best_fire:
                best_fire = fire_utc
                best_task = task

        if best_task is None or best_fire is None:
            return None

        return (best_task, best_fire)

    async def _execute_with_retry(self, task: ScheduledTask) -> None:
        """Run the task callback with exponential-backoff retry on failure."""
        task.last_run_at = datetime.now(tz=ET)
        task.last_status = "running"
        task.run_count += 1

        for attempt in range(_MAX_RETRIES):
            try:
                logger.info(
                    "BatchScheduler: executing '%s' (attempt %d/%d)",
                    task.task_id,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                t0 = time.monotonic()
                await task.callback()
                elapsed = time.monotonic() - t0
                task.last_status = "success"
                logger.info(
                    "BatchScheduler: '%s' completed in %.1fs", task.task_id, elapsed
                )
                return

            except Exception as exc:
                task.error_count += 1
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_BASE_SECS * (2 ** attempt)
                    logger.warning(
                        "BatchScheduler: '%s' attempt %d failed: %s -- retrying in %.0fs",
                        task.task_id,
                        attempt + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "BatchScheduler: '%s' failed after %d attempts: %s",
                        task.task_id,
                        _MAX_RETRIES,
                        exc,
                        exc_info=True,
                    )
                    task.last_status = "failed"


def _next_occurrence_et(now_et: datetime, hour: int, minute: int) -> datetime:
    """Return the next datetime in ET at (hour, minute) >= now.

    If today's (hour, minute) is still in the future, returns today.
    Otherwise returns tomorrow at (hour, minute).
    """
    candidate = now_et.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now_et:
        candidate += timedelta(days=1)
    return candidate
