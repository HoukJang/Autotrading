"""Unit tests for BatchScheduler (autotrader/batch/scheduler.py).

Tests cover:
- Task registration and execution at correct times
- Weekend skip logic
- Holiday skip logic
- Retry on failure (3 attempts)
- Next event calculation
- Clean shutdown
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zoneinfo import ZoneInfo

from autotrader.batch.scheduler import (
    BatchScheduler,
    TASK_NIGHTLY_SCAN,
    TASK_GAP_FILTER,
    TASK_MARKET_OPEN,
    TASK_OPEN_MONITOR,
    TASK_POST_OPEN,
    NextEventInfo,
    _is_trading_day,
    _next_trading_day,
    _NYSE_HOLIDAYS,
)

ET = ZoneInfo("US/Eastern")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _noop() -> None:
    """A no-op async callback for test task registration."""
    pass


def _make_scheduler(
    schedule: list[tuple[str, int, int]] | None = None,
) -> BatchScheduler:
    return BatchScheduler(schedule=schedule)


# ---------------------------------------------------------------------------
# Test class: is_trading_day and next_trading_day helpers
# ---------------------------------------------------------------------------

class TestTradingDayHelpers:
    """Unit tests for the trading calendar helper functions."""

    def test_weekday_is_trading_day(self):
        """A regular Monday should be a trading day."""
        monday = date(2026, 2, 16)  # A Monday
        # But 2026-02-16 is Presidents' Day, check a non-holiday Monday
        monday_2 = date(2026, 2, 23)  # Another Monday
        assert _is_trading_day(monday_2) is True

    def test_saturday_is_not_trading_day(self):
        """Saturday should never be a trading day."""
        saturday = date(2026, 2, 21)
        assert _is_trading_day(saturday) is False

    def test_sunday_is_not_trading_day(self):
        """Sunday should never be a trading day."""
        sunday = date(2026, 2, 22)
        assert _is_trading_day(sunday) is False

    def test_nyse_holiday_is_not_trading_day(self):
        """Known NYSE holidays should not be trading days."""
        for holiday in _NYSE_HOLIDAYS:
            assert _is_trading_day(holiday) is False

    def test_next_trading_day_skips_weekend(self):
        """next_trading_day from a Friday should return the following Monday."""
        friday = date(2026, 2, 20)
        next_day = _next_trading_day(friday + timedelta(days=1))  # Saturday
        # Should skip Saturday, Sunday -> Monday
        assert next_day == date(2026, 2, 23)

    def test_next_trading_day_skips_holiday(self):
        """next_trading_day from a holiday should advance to next business day."""
        # New Year's Day 2026
        holiday = date(2026, 1, 1)
        next_day = _next_trading_day(holiday)
        assert next_day not in _NYSE_HOLIDAYS
        assert next_day.weekday() < 5

    def test_next_trading_day_from_trading_day_returns_same(self):
        """next_trading_day from a trading day should return that same day."""
        tuesday = date(2026, 2, 24)  # Regular Tuesday
        result = _next_trading_day(tuesday)
        assert result == tuesday


# ---------------------------------------------------------------------------
# Test class: task registration
# ---------------------------------------------------------------------------

class TestTaskRegistration:
    """Tests for register() and add_schedule_entry()."""

    def test_register_known_task_succeeds(self):
        """Registering a known task_id should not raise an error."""
        scheduler = _make_scheduler()
        scheduler.register(TASK_NIGHTLY_SCAN, _noop)
        assert TASK_NIGHTLY_SCAN in scheduler._tasks

    def test_register_unknown_task_raises(self):
        """Registering an unknown task_id should raise ValueError."""
        scheduler = _make_scheduler()
        with pytest.raises(ValueError, match="not in the scheduler config"):
            scheduler.register("NONEXISTENT_TASK", _noop)

    def test_register_replaces_existing_callback(self):
        """Registering same task_id twice should replace the callback."""
        scheduler = _make_scheduler()
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        scheduler.register(TASK_NIGHTLY_SCAN, callback1)
        scheduler.register(TASK_NIGHTLY_SCAN, callback2)
        assert scheduler._tasks[TASK_NIGHTLY_SCAN].callback is callback2

    def test_add_schedule_entry_allows_custom_task(self):
        """add_schedule_entry() should allow registering custom tasks."""
        scheduler = _make_scheduler()
        scheduler.add_schedule_entry("CUSTOM_TASK", 15, 30, _noop)
        assert "CUSTOM_TASK" in scheduler._tasks
        assert scheduler._tasks["CUSTOM_TASK"].hour == 15
        assert scheduler._tasks["CUSTOM_TASK"].minute == 30

    def test_all_default_task_ids_can_be_registered(self):
        """All default TASK_* constants should be registerable."""
        scheduler = _make_scheduler()
        for task_id in [TASK_NIGHTLY_SCAN, TASK_GAP_FILTER, TASK_MARKET_OPEN,
                        TASK_OPEN_MONITOR, TASK_POST_OPEN]:
            scheduler.register(task_id, _noop)
        assert len(scheduler._tasks) == 5


# ---------------------------------------------------------------------------
# Test class: next event calculation
# ---------------------------------------------------------------------------

class TestNextEventCalculation:
    """Tests for next_event() and _compute_next_run()."""

    def test_next_event_returns_none_with_no_tasks(self):
        """next_event() with no registered tasks should return None."""
        scheduler = _make_scheduler()
        assert scheduler.next_event() is None

    def test_next_event_returns_next_event_info(self):
        """next_event() with a registered task should return NextEventInfo."""
        scheduler = _make_scheduler()
        scheduler.register(TASK_NIGHTLY_SCAN, _noop)
        info = scheduler.next_event()
        assert info is not None
        assert isinstance(info, NextEventInfo)
        assert info.task_id == TASK_NIGHTLY_SCAN

    def test_next_event_seconds_until_is_positive(self):
        """seconds_until should be >= 0."""
        scheduler = _make_scheduler()
        scheduler.register(TASK_NIGHTLY_SCAN, _noop)
        info = scheduler.next_event()
        assert info is not None
        assert info.seconds_until >= 0

    def test_task_status_returns_list(self):
        """task_status() should return a list with task info dicts."""
        scheduler = _make_scheduler()
        scheduler.register(TASK_NIGHTLY_SCAN, _noop)
        statuses = scheduler.task_status()
        assert isinstance(statuses, list)
        assert len(statuses) == 1
        assert statuses[0]["task_id"] == TASK_NIGHTLY_SCAN
        assert statuses[0]["last_status"] == "pending"


# ---------------------------------------------------------------------------
# Test class: retry on failure
# ---------------------------------------------------------------------------

class TestRetryOnFailure:
    """Tests for retry behavior in _execute_with_retry."""

    @pytest.mark.asyncio
    async def test_task_succeeds_on_first_try(self):
        """Successful callback should result in status=success and run_count=1."""
        scheduler = _make_scheduler()
        callback = AsyncMock()
        scheduler.register(TASK_NIGHTLY_SCAN, callback)

        task = scheduler._tasks[TASK_NIGHTLY_SCAN]
        await scheduler._execute_with_retry(task)

        callback.assert_called_once()
        assert task.last_status == "success"
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_task_retried_3_times_on_failure(self):
        """Callback that always fails should be called exactly 3 times."""
        scheduler = _make_scheduler()
        callback = AsyncMock(side_effect=RuntimeError("transient error"))
        scheduler.register(TASK_NIGHTLY_SCAN, callback)

        task = scheduler._tasks[TASK_NIGHTLY_SCAN]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await scheduler._execute_with_retry(task)

        assert callback.call_count == 3
        assert task.last_status == "failed"
        assert task.error_count == 3

    @pytest.mark.asyncio
    async def test_task_succeeds_on_second_try(self):
        """Callback that fails once then succeeds should end with status=success."""
        scheduler = _make_scheduler()
        call_count = {"n": 0}

        async def flaky():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("first attempt fails")

        scheduler.register(TASK_NIGHTLY_SCAN, flaky)
        task = scheduler._tasks[TASK_NIGHTLY_SCAN]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await scheduler._execute_with_retry(task)

        assert call_count["n"] == 2
        assert task.last_status == "success"

    @pytest.mark.asyncio
    async def test_error_count_increments_on_each_failure(self):
        """error_count should increment for each failed attempt."""
        scheduler = _make_scheduler()
        callback = AsyncMock(side_effect=RuntimeError("error"))
        scheduler.register(TASK_NIGHTLY_SCAN, callback)

        task = scheduler._tasks[TASK_NIGHTLY_SCAN]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await scheduler._execute_with_retry(task)

        assert task.error_count == 3


# ---------------------------------------------------------------------------
# Test class: clean shutdown
# ---------------------------------------------------------------------------

class TestCleanShutdown:
    """Tests for stop() behavior."""

    @pytest.mark.asyncio
    async def test_stop_signals_event(self):
        """Calling stop() should set the internal stop event."""
        scheduler = _make_scheduler()
        assert not scheduler._stop_event.is_set()
        scheduler.stop()
        assert scheduler._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_run_forever_exits_after_stop(self):
        """run_forever() should exit promptly after stop() is called."""
        scheduler = _make_scheduler()

        async def run_and_stop():
            run_task = asyncio.create_task(scheduler.run_forever())
            # Immediately stop
            await asyncio.sleep(0.01)
            scheduler.stop()
            await asyncio.wait_for(run_task, timeout=2.0)

        await run_and_stop()
        assert not scheduler._running
