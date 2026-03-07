"""Trading event definitions with catch-up policies for startup resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CatchUpPolicy(Enum):
    """Policy determining how a missed event should be handled on late startup.

    ALWAYS  -- always catch up regardless of how late we start.
    WINDOW  -- catch up only if we start before the deadline.
    SKIP    -- never catch up; wait for the next scheduled occurrence.
    CONDITIONAL -- catch up only if the current time is within the allowed
                   catch-up window.  When ``catch_up_deadline_hour/minute``
                   are set, the resolver enforces ``now < deadline`` (same
                   semantics as WINDOW).  When no deadline is set, behaves
                   like ALWAYS.
    """

    ALWAYS = "always"
    WINDOW = "window"
    SKIP = "skip"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class EventDefinition:
    """Immutable specification of a scheduled trading event.

    Parameters
    ----------
    name : str
        Unique identifier for the event (must match its key in TRADING_EVENTS).
    scheduled_hour : int
        Hour (0-23) in US Eastern when the event is nominally scheduled.
    scheduled_minute : int
        Minute (0-59) when the event is nominally scheduled.
    catch_up_policy : CatchUpPolicy
        Governs whether the resolver should include this event on late start.
    catch_up_deadline_hour : int | None
        For WINDOW and CONDITIONAL policies -- hour component of the latest
        allowed catch-up time.  When set, the resolver requires ``now < deadline``
        for catch-up to occur.
    catch_up_deadline_minute : int | None
        For WINDOW and CONDITIONAL policies -- minute component of the latest
        allowed catch-up time.
    depends_on : list[str]
        Names of events that must run *before* this event.
    """

    name: str
    scheduled_hour: int
    scheduled_minute: int
    catch_up_policy: CatchUpPolicy
    catch_up_deadline_hour: int | None = None
    catch_up_deadline_minute: int | None = None
    depends_on: list[str] = field(default_factory=list)
    target_next_day: bool = False  # If True, dedup key uses next calendar date


# ---------------------------------------------------------------------------
# Canonical trading-day event definitions (US Eastern times)
# ---------------------------------------------------------------------------
TRADING_EVENTS: dict[str, EventDefinition] = {
    "daily_bar_refresh": EventDefinition(
        name="daily_bar_refresh",
        scheduled_hour=9,
        scheduled_minute=0,
        catch_up_policy=CatchUpPolicy.ALWAYS,
        depends_on=[],
    ),
    "daily_reset": EventDefinition(
        name="daily_reset",
        scheduled_hour=9,
        scheduled_minute=20,
        catch_up_policy=CatchUpPolicy.ALWAYS,
        depends_on=["daily_bar_refresh"],
    ),
    "gap_filter": EventDefinition(
        name="gap_filter",
        scheduled_hour=9,
        scheduled_minute=25,
        catch_up_policy=CatchUpPolicy.CONDITIONAL,
        catch_up_deadline_hour=9,
        catch_up_deadline_minute=35,
        depends_on=["daily_bar_refresh", "daily_reset"],
    ),
    "moo": EventDefinition(
        name="moo",
        scheduled_hour=9,
        scheduled_minute=30,
        catch_up_policy=CatchUpPolicy.WINDOW,
        catch_up_deadline_hour=9,
        catch_up_deadline_minute=45,
        depends_on=["daily_reset", "gap_filter"],
    ),
    "confirmation": EventDefinition(
        name="confirmation",
        scheduled_hour=9,
        scheduled_minute=45,
        catch_up_policy=CatchUpPolicy.WINDOW,
        catch_up_deadline_hour=10,
        catch_up_deadline_minute=0,
        depends_on=["moo"],
    ),
    "entry_close": EventDefinition(
        name="entry_close",
        scheduled_hour=10,
        scheduled_minute=0,
        catch_up_policy=CatchUpPolicy.ALWAYS,
        depends_on=["confirmation"],
    ),
    "nightly_scan": EventDefinition(
        name="nightly_scan",
        scheduled_hour=20,
        scheduled_minute=0,
        catch_up_policy=CatchUpPolicy.ALWAYS,
        depends_on=[],
        target_next_day=True,
    ),
}
