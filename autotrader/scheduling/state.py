"""Persistent scheduler state for tracking fired events across restarts.

Solves the restart amnesia problem: without persistent state, the scheduler
has no way to know which events already ran today.  This leads to ghost
positions (catch-up re-executing MOO), stale gap_filter reruns, and other
bugs documented in the design doc.

State is stored as a single JSON file and written atomically (tmp+rename)
to survive mid-write crashes.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

logger = logging.getLogger("autotrader.scheduling.state")

_ET = ZoneInfo("America/New_York")


@dataclass
class EventRecord:
    """Record of a single fired event."""

    fired_at: str  # ISO timestamp (ET)
    result: str  # "success" | "skipped" | "failed"


@dataclass
class SchedulerState:
    """Persistent state tracking which events have fired today.

    On each event execution, call ``mark_fired`` then ``save``.
    On startup, call ``load`` to restore the last known state.
    If the date has changed, call ``fresh`` to start a clean slate.
    """

    date: str  # ISO date string, e.g. "2026-03-04"
    events: dict[str, EventRecord] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory / persistence
    # ------------------------------------------------------------------

    @staticmethod
    def fresh(today: str) -> SchedulerState:
        """Create an empty state for a new day."""
        return SchedulerState(date=today, events={})

    @classmethod
    def load(cls, path: Path) -> SchedulerState:
        """Load state from disk.  Returns empty state on any failure."""
        try:
            if not path.exists():
                logger.info("No scheduler state file at %s; starting fresh", path)
                return cls._fresh_today()

            raw = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)

            state_date = data.get("date", "")
            events_raw = data.get("events", {})
            events: dict[str, EventRecord] = {}
            for name, rec in events_raw.items():
                events[name] = EventRecord(
                    fired_at=rec.get("fired_at", ""),
                    result=rec.get("result", "unknown"),
                )

            logger.info(
                "Loaded scheduler state: date=%s, %d event(s)",
                state_date,
                len(events),
            )
            return cls(date=state_date, events=events)

        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning("Corrupted scheduler state (%s); starting fresh", exc)
            return cls._fresh_today()

    def save(self, path: Path) -> None:
        """Atomic write: write to .tmp then rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        payload = {
            "date": self.date,
            "events": {
                name: asdict(rec) for name, rec in self.events.items()
            },
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))

    # ------------------------------------------------------------------
    # Query / mutation
    # ------------------------------------------------------------------

    def mark_fired(self, event: str, result: str = "success") -> None:
        """Record an event as fired with the current ET timestamp."""
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        self.events[event] = EventRecord(
            fired_at=now_et.isoformat(),
            result=result,
        )

    def is_fired(self, event: str) -> bool:
        """Check whether an event has been recorded today."""
        return event in self.events

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
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _fresh_today(cls) -> SchedulerState:
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        return cls.fresh(now_et.date().isoformat())
