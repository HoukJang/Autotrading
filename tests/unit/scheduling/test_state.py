"""Unit tests for SchedulerState persistent state.

Validates:
- Fresh state creation
- Event recording and querying
- JSON save/load roundtrip with atomic write
- Corrupted/missing file recovery
- Day boundary reset
- Legacy _fired dict compatibility
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from autotrader.scheduling.state import EventRecord, SchedulerState


class TestFreshState:
    """Test SchedulerState.fresh() factory."""

    def test_fresh_state_empty(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        assert state.date == "2026-03-04"
        assert state.events == {}

    def test_fresh_state_has_no_fired_events(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        assert state.fired_event_names() == set()

    def test_fresh_state_is_fired_false(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        assert state.is_fired("gap_filter") is False


class TestMarkFired:
    """Test mark_fired() and query methods."""

    def test_mark_fired_records_event(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter", result="success")
        assert state.is_fired("gap_filter") is True
        assert state.events["gap_filter"].result == "success"

    def test_mark_fired_default_result_is_success(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("moo")
        assert state.events["moo"].result == "success"

    def test_mark_fired_records_timestamp(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        assert state.events["gap_filter"].fired_at != ""
        assert "2026" in state.events["gap_filter"].fired_at

    def test_is_fired_true(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("daily_bar_refresh")
        assert state.is_fired("daily_bar_refresh") is True

    def test_is_fired_false(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        assert state.is_fired("nightly_scan") is False

    def test_mark_fired_skipped_result(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("moo", result="skipped")
        assert state.events["moo"].result == "skipped"

    def test_mark_fired_failed_result(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter", result="failed")
        assert state.events["gap_filter"].result == "failed"


class TestFiredEventNames:
    """Test fired_event_names() set."""

    def test_fired_event_names_empty(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        assert state.fired_event_names() == set()

    def test_fired_event_names_single(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        assert state.fired_event_names() == {"gap_filter"}

    def test_fired_event_names_multiple(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        state.mark_fired("moo")
        state.mark_fired("daily_bar_refresh")
        assert state.fired_event_names() == {"gap_filter", "moo", "daily_bar_refresh"}


class TestSaveAndLoad:
    """Test save/load roundtrip and edge cases."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter", result="success")
        state.mark_fired("moo", result="skipped")
        state.save(path)

        loaded = SchedulerState.load(path)
        assert loaded.date == "2026-03-04"
        assert loaded.is_fired("gap_filter")
        assert loaded.events["gap_filter"].result == "success"
        assert loaded.is_fired("moo")
        assert loaded.events["moo"].result == "skipped"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        state = SchedulerState.load(path)
        assert state.events == {}

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("not valid json {{{", encoding="utf-8")
        state = SchedulerState.load(path)
        assert state.events == {}

    def test_load_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("", encoding="utf-8")
        state = SchedulerState.load(path)
        assert state.events == {}

    def test_atomic_write_uses_tmp_rename(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        state.save(path)

        # .tmp should not exist after atomic write
        assert not path.with_suffix(".tmp").exists()
        # Main file should exist and be valid JSON
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["date"] == "2026-03-04"
        assert "gap_filter" in data["events"]

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "state.json"
        state = SchedulerState.fresh("2026-03-04")
        state.save(path)
        assert path.exists()

    def test_save_overwrites_previous(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        state1 = SchedulerState.fresh("2026-03-04")
        state1.mark_fired("gap_filter")
        state1.save(path)

        state2 = SchedulerState.fresh("2026-03-05")
        state2.mark_fired("moo")
        state2.save(path)

        loaded = SchedulerState.load(path)
        assert loaded.date == "2026-03-05"
        assert loaded.is_fired("moo")
        assert not loaded.is_fired("gap_filter")


class TestToFiredDict:
    """Test backward-compatible _fired dict conversion."""

    def test_to_fired_dict_empty(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        result = state.to_fired_dict()
        assert result == {}

    def test_to_fired_dict_maps_to_today_date(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        state.mark_fired("moo")
        result = state.to_fired_dict()
        assert result == {
            "gap_filter": date(2026, 3, 4),
            "moo": date(2026, 3, 4),
        }

    def test_to_fired_dict_compat_with_polling_loop(self) -> None:
        """The polling loop checks `_fired[evt] != today_et`.
        Fired events should match today's date.
        """
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("daily_bar_refresh")
        fired_dict = state.to_fired_dict()
        today_et = date(2026, 3, 4)
        assert fired_dict["daily_bar_refresh"] == today_et


class TestDayReset:
    """Test day boundary handling."""

    def test_different_day_resets(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        assert state.is_fired("gap_filter")

        # New day -> fresh state
        new_state = SchedulerState.fresh("2026-03-05")
        assert not new_state.is_fired("gap_filter")
        assert new_state.date == "2026-03-05"

    def test_same_day_preserves(self) -> None:
        state = SchedulerState.fresh("2026-03-04")
        state.mark_fired("gap_filter")
        # Simulating a reload on the same day
        assert state.date == "2026-03-04"
        assert state.is_fired("gap_filter")


class TestEventRecord:
    """Test EventRecord dataclass."""

    def test_event_record_fields(self) -> None:
        rec = EventRecord(fired_at="2026-03-04T09:25:00-05:00", result="success")
        assert rec.fired_at == "2026-03-04T09:25:00-05:00"
        assert rec.result == "success"
