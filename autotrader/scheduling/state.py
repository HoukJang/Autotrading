"""Persistent scheduler state for tracking fired events across restarts.

Solves the restart amnesia problem: without persistent state, the scheduler
has no way to know which events already ran today.  This leads to ghost
positions (catch-up re-executing MOO), stale gap_filter reruns, and other
bugs documented in the design doc.

State is stored as a single JSON file and written atomically (tmp+rename)
to survive mid-write crashes.

Phase 5 enhancement: dual-write to SQLite scheduler_events table via
StateStore, with JSON kept as backup.  SQLite is tried first on load,
falling back to JSON when the database is empty or unavailable.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from autotrader.data.state_store import StateStore

logger = logging.getLogger("autotrader.scheduling.state")

_ET = ZoneInfo("America/New_York")


@dataclass
class EventRecord:
    """Record of a single fired event."""

    fired_at: str  # ISO timestamp (ET)
    result: str  # "success" | "skipped" | "failed"
    target_date: str = ""  # ISO date: which trading day this event serves


@dataclass
class SchedulerState:
    """Persistent state tracking which events have fired today.

    On each event execution, call ``mark_fired`` then ``save``.
    On startup, call ``load`` to restore the last known state.
    If the date has changed, call ``fresh`` to start a clean slate.
    """

    date: str  # ISO date string, e.g. "2026-03-04"
    events: dict[str, EventRecord] = field(default_factory=dict)
    _store: Any = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # StateStore integration
    # ------------------------------------------------------------------

    def set_state_store(self, store: "StateStore") -> None:
        """Attach a StateStore for SQLite dual-write persistence."""
        object.__setattr__(self, "_store", store)

    # ------------------------------------------------------------------
    # Factory / persistence
    # ------------------------------------------------------------------

    @staticmethod
    def fresh(today: str) -> SchedulerState:
        """Create an empty state for a new day."""
        return SchedulerState(date=today, events={})

    @classmethod
    def load(cls, path: Path, store: "StateStore | None" = None) -> SchedulerState:
        """Load state: try SQLite first, fallback to JSON.

        Returns empty state on any failure.
        """
        # --- Try SQLite first ---
        if store is not None:
            try:
                state_date, db_events = store.load_scheduler_state()
                if state_date and db_events:
                    events: dict[str, EventRecord] = {}
                    for name, evt in db_events.items():
                        events[name] = EventRecord(
                            fired_at=evt.get("fired_at", ""),
                            result=evt.get("result", "unknown"),
                            target_date=evt.get("target_date", ""),
                        )
                    logger.info(
                        "Loaded scheduler state from SQLite: date=%s, %d event(s)",
                        state_date,
                        len(events),
                    )
                    instance = cls(date=state_date, events=events)
                    instance.set_state_store(store)
                    return instance
            except Exception:
                logger.exception("Failed to load scheduler state from SQLite")

        # --- Fallback to JSON ---
        try:
            if not path.exists():
                logger.info("No scheduler state file at %s; starting fresh", path)
                instance = cls._fresh_today()
                if store is not None:
                    instance.set_state_store(store)
                return instance

            raw = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)

            state_date_json = data.get("date", "")
            events_raw = data.get("events", {})
            events_json: dict[str, EventRecord] = {}
            for name, rec in events_raw.items():
                events_json[name] = EventRecord(
                    fired_at=rec.get("fired_at", ""),
                    result=rec.get("result", "unknown"),
                    target_date=rec.get("target_date", ""),
                )

            logger.info(
                "Loaded scheduler state from JSON: date=%s, %d event(s)",
                state_date_json,
                len(events_json),
            )
            instance = cls(date=state_date_json, events=events_json)
            if store is not None:
                instance.set_state_store(store)

            # Migrate JSON data to SQLite for future loads
            if store is not None and events_json:
                try:
                    sqlite_events = {
                        name: asdict(rec) for name, rec in events_json.items()
                    }
                    store.save_scheduler_state(state_date_json, sqlite_events)
                    logger.info(
                        "Migrated scheduler state to SQLite: date=%s, %d event(s)",
                        state_date_json,
                        len(sqlite_events),
                    )
                except Exception:
                    logger.exception("Failed to migrate scheduler state to SQLite")

            return instance

        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning("Corrupted scheduler state (%s); starting fresh", exc)
            instance = cls._fresh_today()
            if store is not None:
                instance.set_state_store(store)
            return instance

    def save(self, path: Path) -> None:
        """Dual-write: save to SQLite first, then JSON as backup."""
        events_dict = {
            name: asdict(rec) for name, rec in self.events.items()
        }

        # --- SQLite write (primary) ---
        if self._store is not None:
            try:
                self._store.save_scheduler_state(self.date, events_dict)
                logger.debug(
                    "Scheduler state saved to SQLite: date=%s, %d event(s)",
                    self.date,
                    len(events_dict),
                )
            except Exception:
                logger.exception("Failed to save scheduler state to SQLite")

        # --- JSON write (backup) ---
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        payload = {
            "date": self.date,
            "events": events_dict,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))

    # ------------------------------------------------------------------
    # Query / mutation
    # ------------------------------------------------------------------

    def mark_fired(
        self,
        event: str,
        result: str = "success",
        target_date: str = "",
    ) -> None:
        """Record an event as fired with the current ET timestamp.

        Args:
            event: Event name.
            result: Outcome string ("success", "skipped", "failed").
            target_date: ISO date string indicating which trading day this
                event serves.  For events with ``target_next_day=True``
                (e.g. nightly_scan), this is the *next* calendar day when
                run in the evening, or *today* when caught up in the morning.
        """
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        self.events[event] = EventRecord(
            fired_at=now_et.isoformat(),
            result=result,
            target_date=target_date,
        )

    def is_fired(self, event: str) -> bool:
        """Check whether an event has been recorded today."""
        return event in self.events

    def is_fired_for_date(self, event_name: str, target: str) -> bool:
        """Check if event was already fired for a specific target date.

        For events that use target_date-based dedup (e.g. nightly_scan),
        this checks whether the recorded target_date matches *target*.
        If the event has no target_date recorded (legacy state or non-
        target_next_day events), assume it was fired for state.date
        (the current scheduler day).  This means a legacy record blocks
        same-day targets but does NOT block a different-date target
        (e.g. morning catch-up for today does not block the evening run
        targeting tomorrow).

        Args:
            event_name: Name of the event to check.
            target: ISO date string to compare against.

        Returns:
            True if the event was already fired for this target date.
        """
        rec = self.events.get(event_name)
        if rec is None:
            return False
        if rec.target_date:
            return rec.target_date == target
        # Legacy: no target_date recorded -> assume fired for state.date.
        # Blocks same-day target, but not a different-date target.
        return target == self.date

    def fired_event_names(self) -> set[str]:
        """Return the set of event names that have fired."""
        return set(self.events.keys())

    def to_fired_dict(self) -> dict[str, date | None]:
        """Convert to the legacy ``_fired`` dict format for backward compat.

        Fired events get today's date; unfired events are not included
        (callers should initialise their dict with None values first).
        """
        today = date.fromisoformat(self.date)
        return {name: today for name in self.events}

    # ------------------------------------------------------------------
    # Snapshottable protocol (for RuntimeState periodic saves)
    # ------------------------------------------------------------------

    def to_snapshot(self) -> dict:
        """Serialize state for RuntimeState persistence."""
        return {
            "date": self.date,
            "events": {
                name: asdict(rec) for name, rec in self.events.items()
            },
        }

    def from_snapshot(self, data: dict) -> None:
        """Restore state from RuntimeState snapshot."""
        self.date = data.get("date", "")
        events_raw = data.get("events", {})
        self.events = {}
        for name, rec in events_raw.items():
            self.events[name] = EventRecord(
                fired_at=rec.get("fired_at", ""),
                result=rec.get("result", "unknown"),
                target_date=rec.get("target_date", ""),
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _fresh_today(cls) -> SchedulerState:
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        return cls.fresh(now_et.date().isoformat())
