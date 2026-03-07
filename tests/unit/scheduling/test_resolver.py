"""Unit tests for StartupCatchUpResolver.

Validates the catch-up resolution logic including:
- CatchUpPolicy enum completeness
- EventDefinition data integrity and dependency validity
- Resolver behavior across various startup times and market-day conditions
- WINDOW policy deadline boundary enforcement
- Topological sort preserving dependency order
- Nightly scan cross-day catch-up logic
- Custom event override support
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from autotrader.scheduling.events import CatchUpPolicy, EventDefinition, TRADING_EVENTS
from autotrader.scheduling.resolver import StartupCatchUpResolver

_ET = ZoneInfo("America/New_York")


def _et(
    hour: int,
    minute: int = 0,
    year: int = 2026,
    month: int = 3,
    day: int = 2,
) -> datetime:
    """Create a US Eastern datetime for testing.

    Default date is Monday 2026-03-02 (a regular trading day).
    """
    return datetime(year, month, day, hour, minute, tzinfo=_ET)


# ======================================================================
# CatchUpPolicy enum tests
# ======================================================================


class TestCatchUpPolicyEnum:
    """Verify CatchUpPolicy enum completeness and values."""

    def test_always_member_exists(self) -> None:
        """ALWAYS policy must be a valid enum member."""
        assert CatchUpPolicy.ALWAYS.value == "always"

    def test_window_member_exists(self) -> None:
        """WINDOW policy must be a valid enum member."""
        assert CatchUpPolicy.WINDOW.value == "window"

    def test_skip_member_exists(self) -> None:
        """SKIP policy must be a valid enum member."""
        assert CatchUpPolicy.SKIP.value == "skip"

    def test_conditional_member_exists(self) -> None:
        """CONDITIONAL policy must be a valid enum member."""
        assert CatchUpPolicy.CONDITIONAL.value == "conditional"

    def test_exactly_four_members(self) -> None:
        """Enum should contain exactly 4 policies -- no more, no less."""
        assert len(CatchUpPolicy) == 4

    def test_all_members_unique(self) -> None:
        """All enum values must be distinct strings."""
        values = [p.value for p in CatchUpPolicy]
        assert len(values) == len(set(values))


# ======================================================================
# EventDefinition and TRADING_EVENTS integrity tests
# ======================================================================


class TestEventDefinitions:
    """Validate TRADING_EVENTS registry and individual EventDefinition fields."""

    def test_trading_events_has_exactly_seven_events(self) -> None:
        """Registry must contain exactly 7 canonical events."""
        assert len(TRADING_EVENTS) == 7

    def test_all_event_names_match_dict_keys(self) -> None:
        """Each EventDefinition.name must equal its dictionary key."""
        for key, ev in TRADING_EVENTS.items():
            assert ev.name == key, (
                f"Key '{key}' does not match event name '{ev.name}'"
            )

    @pytest.mark.parametrize(
        "event_name, expected_policy",
        [
            ("daily_bar_refresh", CatchUpPolicy.ALWAYS),
            ("daily_reset", CatchUpPolicy.ALWAYS),
            ("gap_filter", CatchUpPolicy.CONDITIONAL),
            ("moo", CatchUpPolicy.WINDOW),
            ("confirmation", CatchUpPolicy.WINDOW),
            ("entry_close", CatchUpPolicy.ALWAYS),
            ("nightly_scan", CatchUpPolicy.ALWAYS),
        ],
    )
    def test_event_has_correct_policy(
        self, event_name: str, expected_policy: CatchUpPolicy
    ) -> None:
        """Each event must have its documented catch-up policy."""
        assert TRADING_EVENTS[event_name].catch_up_policy == expected_policy

    def test_no_circular_dependencies(self) -> None:
        """Dependency graph must be a DAG -- no cycles allowed."""
        visited: set[str] = set()
        path: set[str] = set()

        def _has_cycle(name: str) -> bool:
            if name in path:
                return True
            if name in visited:
                return False
            visited.add(name)
            path.add(name)
            ev = TRADING_EVENTS.get(name)
            if ev is not None:
                for dep in ev.depends_on:
                    if _has_cycle(dep):
                        return True
            path.discard(name)
            return False

        for event_name in TRADING_EVENTS:
            assert not _has_cycle(event_name), (
                f"Circular dependency detected involving '{event_name}'"
            )

    def test_all_dependencies_reference_existing_events(self) -> None:
        """Every depends_on entry must point to a valid TRADING_EVENTS key."""
        for name, ev in TRADING_EVENTS.items():
            for dep in ev.depends_on:
                assert dep in TRADING_EVENTS, (
                    f"Event '{name}' depends on '{dep}' "
                    "which is not in TRADING_EVENTS"
                )

    def test_window_events_have_deadline_fields(self) -> None:
        """WINDOW-policy events must specify catch_up_deadline_hour/minute."""
        for name, ev in TRADING_EVENTS.items():
            if ev.catch_up_policy == CatchUpPolicy.WINDOW:
                assert ev.catch_up_deadline_hour is not None, (
                    f"WINDOW event '{name}' missing catch_up_deadline_hour"
                )
                assert ev.catch_up_deadline_minute is not None, (
                    f"WINDOW event '{name}' missing catch_up_deadline_minute"
                )

    def test_nightly_scan_has_target_next_day(self) -> None:
        """nightly_scan must have target_next_day=True."""
        assert TRADING_EVENTS["nightly_scan"].target_next_day is True

    def test_non_nightly_events_have_target_next_day_false(self) -> None:
        """All events except nightly_scan should have target_next_day=False."""
        for name, ev in TRADING_EVENTS.items():
            if name != "nightly_scan":
                assert ev.target_next_day is False, (
                    f"Event '{name}' has unexpected target_next_day=True"
                )

    def test_non_window_non_conditional_events_have_no_deadline(self) -> None:
        """Events that are neither WINDOW nor CONDITIONAL should not specify deadline fields."""
        for name, ev in TRADING_EVENTS.items():
            if ev.catch_up_policy not in (CatchUpPolicy.WINDOW, CatchUpPolicy.CONDITIONAL):
                assert ev.catch_up_deadline_hour is None, (
                    f"Non-WINDOW/CONDITIONAL event '{name}' has unexpected "
                    "catch_up_deadline_hour"
                )
                assert ev.catch_up_deadline_minute is None, (
                    f"Non-WINDOW/CONDITIONAL event '{name}' has unexpected "
                    "catch_up_deadline_minute"
                )

    def test_conditional_events_with_deadline_have_valid_fields(self) -> None:
        """CONDITIONAL events with deadlines must have valid hour/minute values."""
        for name, ev in TRADING_EVENTS.items():
            if ev.catch_up_policy == CatchUpPolicy.CONDITIONAL and ev.catch_up_deadline_hour is not None:
                assert 0 <= ev.catch_up_deadline_hour <= 23, (
                    f"CONDITIONAL event '{name}' has invalid "
                    f"catch_up_deadline_hour={ev.catch_up_deadline_hour}"
                )
                assert ev.catch_up_deadline_minute is not None, (
                    f"CONDITIONAL event '{name}' has deadline_hour but missing "
                    "catch_up_deadline_minute"
                )
                assert 0 <= ev.catch_up_deadline_minute <= 59, (
                    f"CONDITIONAL event '{name}' has invalid "
                    f"catch_up_deadline_minute={ev.catch_up_deadline_minute}"
                )

    def test_event_definition_is_frozen(self) -> None:
        """EventDefinition instances must be immutable (frozen dataclass)."""
        ev = TRADING_EVENTS["daily_bar_refresh"]
        with pytest.raises(AttributeError):
            ev.name = "should_fail"  # type: ignore[misc]

    def test_scheduled_hours_within_range(self) -> None:
        """All scheduled hours must be in [0, 23]."""
        for name, ev in TRADING_EVENTS.items():
            assert 0 <= ev.scheduled_hour <= 23, (
                f"Event '{name}' has invalid "
                f"scheduled_hour={ev.scheduled_hour}"
            )

    def test_scheduled_minutes_within_range(self) -> None:
        """All scheduled minutes must be in [0, 59]."""
        for name, ev in TRADING_EVENTS.items():
            assert 0 <= ev.scheduled_minute <= 59, (
                f"Event '{name}' has invalid "
                f"scheduled_minute={ev.scheduled_minute}"
            )


# ======================================================================
# StartupCatchUpResolver core tests
# ======================================================================


class TestStartupCatchUpResolver:
    """Test the resolve() method across different startup times and scenarios."""

    @pytest.fixture()
    def resolver(self) -> StartupCatchUpResolver:
        """Fresh resolver using the canonical TRADING_EVENTS."""
        return StartupCatchUpResolver()

    # ------------------------------------------------------------------
    # Basic startup-time scenarios
    # ------------------------------------------------------------------

    def test_start_before_all_events_catches_nightly_scan(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 8:00 AM on a market day.

        The nightly_scan uses cross-day logic: if the system starts before
        9:00 AM, it assumes the scan was not run overnight and includes it
        for catch-up. All other morning events are still in the future.
        """
        result = resolver.resolve(_et(8, 0), today_is_market_day=True)
        assert result == ["nightly_scan"]

    def test_start_at_930_catches_up_daily_refresh_reset_gap_moo(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 9:30 AM on a market day.

        Missed events whose scheduled time <= 9:30:
        - daily_bar_refresh (9:00, ALWAYS) -> included
        - gap_filter (9:25, CONDITIONAL, deadline 9:35, 9:30 < 9:35) -> included
        - daily_reset (9:20, ALWAYS) -> included
        - moo (9:30, WINDOW deadline 9:45, 9:30 < 9:45) -> included
        - confirmation (9:45, scheduled > 9:30) -> NOT missed yet
        - entry_close (10:00, scheduled > 9:30) -> NOT missed yet
        - nightly_scan: 9:30 is past 9:00 and before 20:00 -> NOT included
        """
        result = resolver.resolve(_et(9, 30), today_is_market_day=True)
        assert set(result) == {
            "daily_bar_refresh",
            "daily_reset",
            "gap_filter",
            "moo",
        }

    def test_start_at_935_catches_up_without_gap_filter(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 9:35 AM on a market day.

        gap_filter (CONDITIONAL, deadline 9:35) is excluded because
        9:35 is NOT strictly less than the 9:35 deadline (pre-market
        data is stale by this time).  moo still runs because the
        topological sort treats absent dependencies as satisfied.
        """
        result = resolver.resolve(_et(9, 35), today_is_market_day=True)
        assert set(result) == {
            "daily_bar_refresh",
            "daily_reset",
            "moo",
        }
        assert "gap_filter" not in result

    def test_start_at_1100_skips_moo_confirmation_and_gap_filter(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 11:00 AM on a market day.

        - daily_bar_refresh (ALWAYS) -> included
        - gap_filter (CONDITIONAL, deadline 9:35, 11:00 >= 9:35) -> EXCLUDED
        - daily_reset (ALWAYS) -> included
        - moo (WINDOW, deadline 9:45, 11:00 >= 9:45) -> EXCLUDED
        - confirmation (WINDOW, deadline 10:00, 11:00 >= 10:00) -> EXCLUDED
        - entry_close (10:00, ALWAYS) -> included
        - nightly_scan: 11:00 is between 9:00 and 20:00 -> NOT included
        """
        result = resolver.resolve(_et(11, 0), today_is_market_day=True)
        assert set(result) == {
            "daily_bar_refresh",
            "daily_reset",
            "entry_close",
        }
        assert "gap_filter" not in result
        assert "moo" not in result
        assert "confirmation" not in result

    def test_start_at_1500_catches_always_events_only(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 3:00 PM on a market day.

        ALWAYS events included. gap_filter (CONDITIONAL, deadline 9:35)
        excluded -- pre-market window long past.
        WINDOW events (moo, confirmation) excluded -- past deadlines.
        nightly_scan: 15:00 is between 9:00 and 20:00 -> NOT included.
        """
        result = resolver.resolve(_et(15, 0), today_is_market_day=True)
        assert set(result) == {
            "daily_bar_refresh",
            "daily_reset",
            "entry_close",
        }
        assert "gap_filter" not in result
        assert "nightly_scan" not in result

    def test_start_at_2200_catches_always_and_nightly_only(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 10:00 PM on a market day.

        All events past their scheduled time. ALWAYS events included.
        gap_filter (CONDITIONAL, deadline 9:35) excluded -- evening start.
        WINDOW events (moo, confirmation) excluded -- past deadlines.
        nightly_scan (20:00) included via evening window (>= 20:00).
        """
        result = resolver.resolve(_et(22, 0), today_is_market_day=True)
        assert set(result) == {
            "daily_bar_refresh",
            "daily_reset",
            "entry_close",
            "nightly_scan",
        }
        assert "gap_filter" not in result
        assert "moo" not in result
        assert "confirmation" not in result

    # ------------------------------------------------------------------
    # Non-market-day scenarios
    # ------------------------------------------------------------------

    def test_sunday_evening_catches_nightly_scan_only(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Sunday 10 PM (not a market day).

        nightly_scan is special: runs on any day for next-day prep.
        All other events require a market day.
        """
        sunday_10pm = _et(22, 0, year=2026, month=3, day=1)
        result = resolver.resolve(sunday_10pm, today_is_market_day=False)
        assert result == ["nightly_scan"]

    def test_non_market_day_morning_returns_empty(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Saturday 10 AM (not a market day).

        nightly_scan: 10:00 is between 9:00 and 20:00, so NOT in catch-up
        window. All other events gated by market-day check.
        """
        saturday_10am = _et(10, 0, year=2026, month=2, day=28)
        result = resolver.resolve(saturday_10am, today_is_market_day=False)
        assert result == []

    def test_non_market_day_early_morning_catches_nightly_scan(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Saturday 7 AM (not a market day).

        nightly_scan uses cross-day logic: before 9:00 AM catches up
        the previous night's scan even on non-market days.
        """
        saturday_7am = _et(7, 0, year=2026, month=2, day=28)
        result = resolver.resolve(saturday_7am, today_is_market_day=False)
        assert result == ["nightly_scan"]

    # ------------------------------------------------------------------
    # Dependency ordering
    # ------------------------------------------------------------------

    def test_dependency_order_preserved(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Topological sort must ensure dependencies precede dependents.

        At 9:30, gap_filter is still within its catch-up window (< 9:35).
        Known dependency chains:
        - daily_bar_refresh -> daily_reset
        - daily_bar_refresh -> daily_reset -> gap_filter
        - daily_reset + gap_filter -> moo
        """
        result = resolver.resolve(_et(9, 30), today_is_market_day=True)
        idx = {name: i for i, name in enumerate(result)}

        assert idx["daily_bar_refresh"] < idx["daily_reset"]
        assert idx["daily_bar_refresh"] < idx["gap_filter"]
        assert idx["daily_reset"] < idx["gap_filter"]
        assert idx["daily_reset"] < idx["moo"]
        assert idx["gap_filter"] < idx["moo"]

    def test_dependency_order_with_entry_close(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """At 11:00 AM, entry_close is included but confirmation and gap_filter are not.

        Verify entry_close still appears after its available dependencies.
        gap_filter excluded (CONDITIONAL deadline 9:35 passed).
        """
        result = resolver.resolve(_et(11, 0), today_is_market_day=True)
        idx = {name: i for i, name in enumerate(result)}

        assert idx["daily_bar_refresh"] < idx["entry_close"]
        assert idx["daily_reset"] < idx["entry_close"]
        assert "gap_filter" not in idx

    # ------------------------------------------------------------------
    # WINDOW policy boundary tests
    # ------------------------------------------------------------------

    def test_window_policy_before_deadline_includes_event(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 9:40 AM: moo (deadline 9:45) should be included.

        9:40 < 9:45 -> within the catch-up window.
        """
        result = resolver.resolve(_et(9, 40), today_is_market_day=True)
        assert "moo" in result

    def test_window_policy_after_deadline_excludes_event(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 9:50 AM: moo (deadline 9:45) should be excluded.

        9:50 >= 9:45 -> past the catch-up window.
        """
        result = resolver.resolve(_et(9, 50), today_is_market_day=True)
        assert "moo" not in result

    @pytest.mark.parametrize(
        "minute, moo_included",
        [
            (31, True),
            (44, True),
            (45, False),
            (46, False),
        ],
        ids=[
            "9:31-within-window",
            "9:44-one-minute-before-deadline",
            "9:45-exactly-at-deadline-excluded",
            "9:46-one-minute-after-deadline",
        ],
    )
    def test_moo_window_boundary(
        self,
        resolver: StartupCatchUpResolver,
        minute: int,
        moo_included: bool,
    ) -> None:
        """Parametrized boundary test for moo WINDOW deadline at 9:45.

        The WINDOW policy uses strict less-than (current < deadline),
        so 9:45 exactly is NOT within the window.
        """
        result = resolver.resolve(_et(9, minute), today_is_market_day=True)
        if moo_included:
            assert "moo" in result
        else:
            assert "moo" not in result

    def test_confirmation_window_at_959_included(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 9:59 AM: confirmation (deadline 10:00) included.

        9:59 < 10:00 -> within window.
        moo deadline is 9:45, so moo is EXCLUDED at 9:59.
        """
        result = resolver.resolve(_et(9, 59), today_is_market_day=True)
        assert "confirmation" in result
        assert "moo" not in result

    def test_confirmation_window_at_1001_excluded(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 10:01 AM: confirmation (deadline 10:00) excluded.

        10:01 >= 10:00 -> past the catch-up window.
        """
        result = resolver.resolve(_et(10, 1), today_is_market_day=True)
        assert "confirmation" not in result

    @pytest.mark.parametrize(
        "hour, minute, confirmation_included",
        [
            (9, 46, True),
            (9, 59, True),
            (10, 0, False),
        ],
        ids=[
            "9:46-within-confirmation-window",
            "9:59-one-minute-before-deadline",
            "10:00-exactly-at-deadline-excluded",
        ],
    )
    def test_confirmation_window_boundary(
        self,
        resolver: StartupCatchUpResolver,
        hour: int,
        minute: int,
        confirmation_included: bool,
    ) -> None:
        """Parametrized boundary test for confirmation WINDOW deadline at 10:00.

        The WINDOW policy uses strict less-than, so 10:00 is NOT within.
        """
        result = resolver.resolve(_et(hour, minute), today_is_market_day=True)
        if confirmation_included:
            assert "confirmation" in result
        else:
            assert "confirmation" not in result

    # ------------------------------------------------------------------
    # Custom events override
    # ------------------------------------------------------------------

    def test_custom_events_override(self) -> None:
        """Resolver should use custom event dict when provided."""
        custom_events = {
            "alpha": EventDefinition(
                name="alpha",
                scheduled_hour=8,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=[],
            ),
            "beta": EventDefinition(
                name="beta",
                scheduled_hour=9,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=["alpha"],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(10, 0), today_is_market_day=True)
        assert result == ["alpha", "beta"]

    def test_custom_events_ignores_default_events(self) -> None:
        """When custom events are given, default TRADING_EVENTS are not used."""
        custom_events = {
            "only_event": EventDefinition(
                name="only_event",
                scheduled_hour=8,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=[],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(10, 0), today_is_market_day=True)
        assert result == ["only_event"]
        assert "daily_bar_refresh" not in result

    # ------------------------------------------------------------------
    # Return type validation
    # ------------------------------------------------------------------

    def test_resolve_returns_list_of_strings(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """resolve() must return a list whose elements are all strings."""
        result = resolver.resolve(_et(9, 30), today_is_market_day=True)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str), (
                f"Expected str, got {type(item).__name__}"
            )

    def test_resolve_returns_empty_list_not_none(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """resolve() must return an empty list, not None, when nothing qualifies.

        At 9:00 AM exactly, nightly_scan is NOT caught up (past 9:00 boundary)
        and no morning events have been missed yet (scheduled at 9:00 means
        minutes-from-midnight equal, so not strictly less-than).
        """
        result = resolver.resolve(_et(9, 0), today_is_market_day=True)
        assert isinstance(result, list)
        # daily_bar_refresh is scheduled at 9:00 and ALWAYS policy,
        # 540 >= 540 so it IS included. Use Saturday 10AM non-market instead.
        saturday_10am = _et(10, 0, year=2026, month=2, day=28)
        result2 = resolver.resolve(saturday_10am, today_is_market_day=False)
        assert isinstance(result2, list)
        assert len(result2) == 0

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_midnight_catches_nightly_scan_on_market_day(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at midnight on a market day.

        The nightly_scan cross-day logic catches up before 9:00 AM
        (assumes the scan was not run overnight). All other events are
        in the future.
        """
        result = resolver.resolve(_et(0, 0), today_is_market_day=True)
        assert result == ["nightly_scan"]

    def test_end_of_day_2359_on_market_day(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Starting at 23:59 on a market day catches ALWAYS events + nightly_scan.

        gap_filter (CONDITIONAL, deadline 9:35) excluded.
        WINDOW events (moo, confirmation) excluded.
        """
        result = resolver.resolve(_et(23, 59), today_is_market_day=True)
        expected = {
            "daily_bar_refresh",
            "daily_reset",
            "entry_close",
            "nightly_scan",
        }
        assert set(result) == expected
        assert "gap_filter" not in result

    def test_skip_policy_event_never_included(self) -> None:
        """An event with SKIP policy should never be caught up."""
        custom_events = {
            "skippable": EventDefinition(
                name="skippable",
                scheduled_hour=9,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.SKIP,
                depends_on=[],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(12, 0), today_is_market_day=True)
        assert result == []

    def test_window_event_without_deadline_catches_up_as_always(self) -> None:
        """A WINDOW event with None deadline is treated as ALWAYS by resolver.

        When catch_up_deadline_hour is None, the resolver falls through
        to return True (catch up unconditionally).
        """
        custom_events = {
            "open_window": EventDefinition(
                name="open_window",
                scheduled_hour=9,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.WINDOW,
                catch_up_deadline_hour=None,
                catch_up_deadline_minute=None,
                depends_on=[],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(9, 10), today_is_market_day=True)
        assert result == ["open_window"]

    def test_nightly_scan_not_caught_up_between_9am_and_8pm(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """nightly_scan should NOT be caught up between 9:00 AM and 7:59 PM.

        The cross-day logic only catches up before 9:00 AM or at/after 8:00 PM.
        """
        result = resolver.resolve(_et(19, 59), today_is_market_day=True)
        assert "nightly_scan" not in result

    def test_nightly_scan_caught_up_at_8pm(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """nightly_scan scheduled at 20:00 should appear at exactly 20:00."""
        result = resolver.resolve(_et(20, 0), today_is_market_day=True)
        assert "nightly_scan" in result

    def test_nightly_scan_on_non_market_day_evening(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """nightly_scan runs even on non-market days (next-day prep)."""
        result = resolver.resolve(_et(21, 0), today_is_market_day=False)
        assert result == ["nightly_scan"]

    def test_nightly_scan_early_morning_catch_up(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """nightly_scan is caught up before 9:00 AM (overnight gap logic).

        If the system starts between midnight and 8:59 AM, it assumes
        the nightly scan was not run and catches up.
        """
        result = resolver.resolve(_et(6, 30), today_is_market_day=True)
        assert "nightly_scan" in result

    @pytest.mark.parametrize(
        "hour, minute, nightly_included",
        [
            (0, 0, True),     # midnight -- early morning window
            (5, 0, True),     # 5:00 AM -- early morning window
            (8, 59, True),    # 8:59 AM -- last minute of early morning window
            (9, 0, False),    # 9:00 AM -- boundary: NOT in early morning window
            (12, 0, False),   # noon -- mid-day gap
            (19, 59, False),  # 7:59 PM -- just before evening window
            (20, 0, True),    # 8:00 PM -- evening window starts
            (23, 59, True),   # 11:59 PM -- evening window
        ],
        ids=[
            "midnight-early-morning",
            "5am-early-morning",
            "859am-boundary-included",
            "9am-boundary-excluded",
            "noon-gap",
            "759pm-just-before-evening",
            "8pm-evening-start",
            "1159pm-evening",
        ],
    )
    def test_nightly_scan_cross_day_windows(
        self,
        resolver: StartupCatchUpResolver,
        hour: int,
        minute: int,
        nightly_included: bool,
    ) -> None:
        """Parametrized test for nightly_scan cross-day catch-up windows.

        Catch-up windows: [00:00, 09:00) and [20:00, 24:00).
        Gap (no catch-up): [09:00, 20:00).
        """
        result = resolver.resolve(_et(hour, minute), today_is_market_day=True)
        if nightly_included:
            assert "nightly_scan" in result
        else:
            assert "nightly_scan" not in result

    def test_no_duplicates_in_result(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """The result list must never contain duplicate event names."""
        result = resolver.resolve(_et(22, 0), today_is_market_day=True)
        assert len(result) == len(set(result))

    def test_default_resolver_uses_trading_events(self) -> None:
        """A resolver created without arguments should use TRADING_EVENTS."""
        resolver = StartupCatchUpResolver()
        result = resolver.resolve(_et(9, 30), today_is_market_day=True)
        assert "daily_bar_refresh" in result

    def test_topological_sort_handles_independent_events(self) -> None:
        """Independent events (no deps) should be sorted by scheduled time."""
        custom_events = {
            "late": EventDefinition(
                name="late",
                scheduled_hour=11,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=[],
            ),
            "early": EventDefinition(
                name="early",
                scheduled_hour=9,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=[],
            ),
            "mid": EventDefinition(
                name="mid",
                scheduled_hour=10,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=[],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(12, 0), today_is_market_day=True)
        assert result == ["early", "mid", "late"]

    def test_topological_sort_with_diamond_dependency(self) -> None:
        """Diamond dependency: A -> B, A -> C, B -> D, C -> D.

        D must come after both B and C; B and C must come after A.
        """
        custom_events = {
            "A": EventDefinition(
                name="A", scheduled_hour=9, scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS, depends_on=[],
            ),
            "B": EventDefinition(
                name="B", scheduled_hour=9, scheduled_minute=10,
                catch_up_policy=CatchUpPolicy.ALWAYS, depends_on=["A"],
            ),
            "C": EventDefinition(
                name="C", scheduled_hour=9, scheduled_minute=20,
                catch_up_policy=CatchUpPolicy.ALWAYS, depends_on=["A"],
            ),
            "D": EventDefinition(
                name="D", scheduled_hour=9, scheduled_minute=30,
                catch_up_policy=CatchUpPolicy.ALWAYS,
                depends_on=["B", "C"],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(10, 0), today_is_market_day=True)
        idx = {name: i for i, name in enumerate(result)}

        assert idx["A"] < idx["B"]
        assert idx["A"] < idx["C"]
        assert idx["B"] < idx["D"]
        assert idx["C"] < idx["D"]

    def test_topological_sort_detects_cycle(self) -> None:
        """Topological sort should raise ValueError on circular dependencies."""
        custom_events = {
            "x": EventDefinition(
                name="x", scheduled_hour=9, scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.ALWAYS, depends_on=["y"],
            ),
            "y": EventDefinition(
                name="y", scheduled_hour=9, scheduled_minute=10,
                catch_up_policy=CatchUpPolicy.ALWAYS, depends_on=["x"],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        with pytest.raises(ValueError, match="cycle"):
            resolver.resolve(_et(10, 0), today_is_market_day=True)


# ======================================================================
# Gap filter CONDITIONAL deadline tests
# ======================================================================


class TestGapFilterConditionalDeadline:
    """Test that gap_filter only catches up within the pre-market window.

    The gap_filter is scheduled at 09:25 ET with a CONDITIONAL policy and
    a catch-up deadline of 09:35 ET.  It should only be caught up when
    the system starts between 09:25 and 09:35 (exclusive).  Outside this
    window, pre-market price data is either unavailable or stale.
    """

    @pytest.fixture()
    def resolver(self) -> StartupCatchUpResolver:
        return StartupCatchUpResolver()

    def test_gap_filter_caught_up_at_926(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:26 AM -- one minute after scheduled time.

        Within pre-market window (9:26 < 9:35), gap_filter included.
        """
        result = resolver.resolve(_et(9, 26), today_is_market_day=True)
        assert "gap_filter" in result

    def test_gap_filter_caught_up_at_930(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:30 AM -- still within pre-market window."""
        result = resolver.resolve(_et(9, 30), today_is_market_day=True)
        assert "gap_filter" in result

    def test_gap_filter_caught_up_at_934(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:34 AM -- last minute before deadline."""
        result = resolver.resolve(_et(9, 34), today_is_market_day=True)
        assert "gap_filter" in result

    def test_gap_filter_excluded_at_935(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:35 AM -- exactly at deadline (strict less-than)."""
        result = resolver.resolve(_et(9, 35), today_is_market_day=True)
        assert "gap_filter" not in result

    def test_gap_filter_excluded_at_936(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:36 AM -- one minute past deadline."""
        result = resolver.resolve(_et(9, 36), today_is_market_day=True)
        assert "gap_filter" not in result

    def test_gap_filter_excluded_at_1000(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 10:00 AM -- well past pre-market window."""
        result = resolver.resolve(_et(10, 0), today_is_market_day=True)
        assert "gap_filter" not in result

    def test_gap_filter_excluded_at_2037_evening_start(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 8:37 PM -- the specific bug scenario.

        When AutoTrader starts at 20:37 ET with catch-up logic,
        the gap_filter must NOT run because pre-market data is
        meaningless at this time.
        """
        result = resolver.resolve(_et(20, 37), today_is_market_day=True)
        assert "gap_filter" not in result
        # nightly_scan SHOULD be caught up at 20:37
        assert "nightly_scan" in result

    def test_gap_filter_not_caught_up_before_scheduled_time(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """System starts at 9:20 AM -- before gap_filter is scheduled."""
        result = resolver.resolve(_et(9, 20), today_is_market_day=True)
        assert "gap_filter" not in result

    @pytest.mark.parametrize(
        "hour, minute, gap_included",
        [
            (9, 24, False),   # before scheduled time
            (9, 25, True),    # exactly at scheduled time
            (9, 30, True),    # within window
            (9, 34, True),    # last minute in window
            (9, 35, False),   # at deadline (excluded)
            (9, 40, False),   # past deadline
            (11, 0, False),   # late morning
            (15, 0, False),   # afternoon
            (20, 37, False),  # evening (reported bug scenario)
            (23, 59, False),  # end of day
        ],
        ids=[
            "924-before-scheduled",
            "925-at-scheduled",
            "930-within-window",
            "934-last-minute",
            "935-at-deadline-excluded",
            "940-past-deadline",
            "1100-late-morning",
            "1500-afternoon",
            "2037-evening-bug-scenario",
            "2359-end-of-day",
        ],
    )
    def test_gap_filter_conditional_window_boundary(
        self,
        resolver: StartupCatchUpResolver,
        hour: int,
        minute: int,
        gap_included: bool,
    ) -> None:
        """Parametrized boundary test for gap_filter CONDITIONAL deadline.

        Catch-up window: [09:25, 09:35) -- scheduled time to deadline.
        """
        result = resolver.resolve(_et(hour, minute), today_is_market_day=True)
        if gap_included:
            assert "gap_filter" in result
        else:
            assert "gap_filter" not in result

    def test_conditional_without_deadline_behaves_as_always(self) -> None:
        """A CONDITIONAL event without deadline fields falls back to ALWAYS."""
        custom_events = {
            "cond_no_deadline": EventDefinition(
                name="cond_no_deadline",
                scheduled_hour=9,
                scheduled_minute=0,
                catch_up_policy=CatchUpPolicy.CONDITIONAL,
                depends_on=[],
            ),
        }
        resolver = StartupCatchUpResolver(events=custom_events)
        result = resolver.resolve(_et(15, 0), today_is_market_day=True)
        assert "cond_no_deadline" in result


# ======================================================================
# already_fired parameter tests
# ======================================================================


class TestAlreadyFiredFiltering:
    """Test the already_fired parameter for persistent state integration."""

    @pytest.fixture()
    def resolver(self) -> StartupCatchUpResolver:
        return StartupCatchUpResolver()

    def test_resolve_filters_already_fired(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Events in already_fired should be excluded from catch-up results."""
        already = {"daily_bar_refresh", "daily_reset", "gap_filter", "moo"}
        result = resolver.resolve(
            _et(9, 30), today_is_market_day=True, already_fired=already
        )
        assert "daily_bar_refresh" not in result
        assert "daily_reset" not in result
        assert "gap_filter" not in result
        assert "moo" not in result
        assert result == []

    def test_resolve_already_fired_none_backward_compat(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """When already_fired is None, behavior is unchanged (no filtering)."""
        result_default = resolver.resolve(
            _et(9, 30), today_is_market_day=True
        )
        result_none = resolver.resolve(
            _et(9, 30), today_is_market_day=True, already_fired=None
        )
        assert result_default == result_none

    def test_resolve_partial_already_fired(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """Only fired events are excluded; remaining events still caught up."""
        already = {"daily_bar_refresh"}
        result = resolver.resolve(
            _et(9, 30), today_is_market_day=True, already_fired=already
        )
        assert "daily_bar_refresh" not in result
        assert "daily_reset" in result
        assert "gap_filter" in result
        assert "moo" in result


# ======================================================================
# Nightly scan target_date dedup tests
# ======================================================================


class TestNightlyScanTargetDateDedup:
    """Test that nightly_scan dedup works with target_date semantics.

    The core scenario: morning catch-up targets today, evening run targets
    tomorrow.  These are different target_dates, so a morning catch-up
    must NOT block the 20:00 evening run (and vice versa).
    """

    @pytest.fixture()
    def resolver(self) -> StartupCatchUpResolver:
        return StartupCatchUpResolver()

    def test_morning_catchup_does_not_block_evening_via_already_fired(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """If nightly_scan is NOT in already_fired, resolver includes it
        in the morning catch-up window (before 9:00).
        """
        # Morning: nightly_scan should be caught up
        result = resolver.resolve(
            _et(5, 21), today_is_market_day=True, already_fired=set()
        )
        assert "nightly_scan" in result

    def test_nightly_scan_in_already_fired_blocks_catchup(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """If nightly_scan IS in already_fired, resolver excludes it."""
        result = resolver.resolve(
            _et(5, 21),
            today_is_market_day=True,
            already_fired={"nightly_scan"},
        )
        assert "nightly_scan" not in result

    def test_evening_resolver_includes_nightly_when_not_fired(
        self, resolver: StartupCatchUpResolver
    ) -> None:
        """At 20:00+, nightly_scan should be included when not in already_fired."""
        result = resolver.resolve(
            _et(20, 0), today_is_market_day=True, already_fired=set()
        )
        assert "nightly_scan" in result
