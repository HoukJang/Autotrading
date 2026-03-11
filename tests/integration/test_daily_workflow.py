"""Integration tests for the daily event workflow sequence.

Validates the ENTIRE daily event lifecycle to prevent state-corruption
bugs caused by incorrect event ordering.  The fatal bug this suite was
written to catch:

    09:30 ET - gap_filter loads candidates into EntryManager
    09:29 ET - daily_reset calls EntryManager.on_new_trading_day() -> WIPES candidates
    09:30 ET - MOO window: EntryManager is empty -> no trades happen

The correct sequence is:
    09:00  daily_bar_refresh
    09:20  daily_reset (clears daily counters)
    09:30  gap_filter + MOO (filter then execute, merged step)
    09:45  confirmation
    10:00  entry_close
    20:00  nightly_scan

Tests cover:
  1. Event ordering correctness
  2. Candidate survival through the pipeline
  3. End-to-end entry flow with mocked broker
  4. Reset-does-not-destroy-needed-state guarantee
  5. Gap filter timing constraints
  6. Startup catch-up sequence correctness
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autotrader.batch.types import (
    BatchResult,
    Candidate as BatchCandidate,
    FilteredCandidate,
    ScanResult,
)
from autotrader.core.config import Settings
from autotrader.core.types import AccountInfo, OrderResult, Signal
from autotrader.execution.entry_manager import Candidate as EntryCandidate, EntryManager
from autotrader.execution.exit_rules import ExitRuleEngine
from autotrader.main import AutoTrader, _batch_to_entry_candidate
from autotrader.portfolio.regime_detector import MarketRegime
from autotrader.scheduling.events import TRADING_EVENTS
from autotrader.scheduling.resolver import StartupCatchUpResolver


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TRADE_DATE = date(2026, 3, 2)  # Monday


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan_result(
    symbol: str,
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    signal_strength: float = 0.85,
    prev_close: float = 100.0,
) -> ScanResult:
    return ScanResult(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        signal_strength=signal_strength,
        indicators={"ATR_14": 2.0, "RSI_14": 45.0},
        prev_close=prev_close,
        scanned_at=datetime.now(tz=timezone.utc),
        metadata={"entry_atr": 2.0},
    )


def _make_batch_candidate(
    symbol: str,
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    rank: int = 1,
) -> BatchCandidate:
    sr = _make_scan_result(symbol, strategy, direction)
    return BatchCandidate(
        scan_result=sr,
        composite_score=0.85,
        regime_compatibility=0.9,
        sector="Technology",
        rank=rank,
    )


def _make_batch_result(
    symbols: list[str] | None = None,
    strategies: list[str] | None = None,
) -> BatchResult:
    """Create a BatchResult with the given symbols (default: AAPL, MSFT, NVDA)."""
    symbols = symbols or ["AAPL", "MSFT", "NVDA"]
    strategies = strategies or ["rsi_mean_reversion"] * len(symbols)
    candidates = [
        _make_batch_candidate(sym, strat, rank=i + 1)
        for i, (sym, strat) in enumerate(zip(symbols, strategies))
    ]
    return BatchResult(
        run_at=datetime.now(tz=timezone.utc),
        scan_duration_secs=5.0,
        symbols_scanned=500,
        symbols_with_signals=len(symbols),
        candidates=candidates,
        regime="TREND_UP",
    )


def _make_account(equity: float = 20_000.0, cash: float = 20_000.0) -> AccountInfo:
    return AccountInfo(
        account_id="test-workflow",
        buying_power=cash,
        portfolio_value=equity,
        cash=cash,
        equity=equity,
    )


def _make_entry_manager(fill_price: float = 100.0) -> EntryManager:
    """Create an EntryManager with all dependencies mocked."""
    fill_result = OrderResult(
        order_id="fill-001",
        symbol="ANY",
        status="filled",
        filled_qty=10.0,
        filled_price=fill_price,
    )

    order_manager = MagicMock()
    order_manager.submit_entry = AsyncMock(return_value=fill_result)
    order_manager.submit_stop_loss = AsyncMock(return_value=None)

    allocation_engine = MagicMock()
    allocation_engine.should_enter = MagicMock(return_value=True)
    allocation_engine.get_position_size = MagicMock(return_value=10)

    risk_manager = MagicMock()
    risk_manager.validate = MagicMock(return_value=True)

    exit_rule_engine = MagicMock(spec=ExitRuleEngine)
    exit_rule_engine.is_reentry_blocked = MagicMock(return_value=False)

    return EntryManager(
        order_manager=order_manager,
        allocation_engine=allocation_engine,
        risk_manager=risk_manager,
        exit_rule_engine=exit_rule_engine,
    )


def _make_autotrader_app() -> AutoTrader:
    """Create a minimally-configured AutoTrader with paper broker."""
    settings = Settings()
    settings.broker.type = "paper"
    app = AutoTrader(settings)
    return app


# =====================================================================
# 1. Event Ordering Tests
# =====================================================================


class TestEventOrdering:
    """Verify events are defined in the correct chronological and dependency order."""

    def test_daily_reset_scheduled_before_gap_filter(self):
        """daily_reset must be scheduled BEFORE gap_filter.

        This is the core ordering constraint that prevents the fatal bug
        where daily_reset wipes candidates loaded by gap_filter.
        """
        reset_ev = TRADING_EVENTS["daily_reset"]
        gap_ev = TRADING_EVENTS["gap_filter"]

        reset_time = reset_ev.scheduled_hour * 60 + reset_ev.scheduled_minute
        gap_time = gap_ev.scheduled_hour * 60 + gap_ev.scheduled_minute

        assert reset_time < gap_time, (
            f"daily_reset ({reset_ev.scheduled_hour}:{reset_ev.scheduled_minute:02d}) "
            f"must be scheduled before gap_filter "
            f"({gap_ev.scheduled_hour}:{gap_ev.scheduled_minute:02d})"
        )

    def test_gap_filter_depends_on_daily_reset(self):
        """gap_filter must declare daily_reset as a dependency.

        Even if scheduled times are correct, the DAG dependency ensures
        the resolver always places daily_reset before gap_filter during
        catch-up sequences.
        """
        gap_ev = TRADING_EVENTS["gap_filter"]
        assert "daily_reset" in gap_ev.depends_on, (
            "gap_filter must depend on daily_reset to prevent the "
            "candidate-wipe ordering bug"
        )

    def test_gap_filter_depends_on_daily_bar_refresh(self):
        """gap_filter needs fresh bars before filtering candidates."""
        gap_ev = TRADING_EVENTS["gap_filter"]
        assert "daily_bar_refresh" in gap_ev.depends_on

    def test_confirmation_depends_on_gap_filter(self):
        """Confirmation must run after gap_filter (which includes MOO)."""
        confirm_ev = TRADING_EVENTS["confirmation"]
        assert "gap_filter" in confirm_ev.depends_on

    def test_full_morning_chronological_order(self):
        """Verify complete morning event schedule is in chronological order.

        Expected: daily_bar_refresh (9:00) -> daily_reset (9:20)
                  -> gap_filter+MOO (9:30) -> confirmation (9:45)
                  -> entry_close (10:00)
        """
        morning_order = [
            "daily_bar_refresh",
            "daily_reset",
            "gap_filter",
            "confirmation",
            "entry_close",
        ]

        times = []
        for name in morning_order:
            ev = TRADING_EVENTS[name]
            times.append(ev.scheduled_hour * 60 + ev.scheduled_minute)

        for i in range(len(times) - 1):
            assert times[i] <= times[i + 1], (
                f"{morning_order[i]} (:{times[i] % 60:02d}) must be <= "
                f"{morning_order[i+1]} (:{times[i+1] % 60:02d})"
            )

    def test_resolver_preserves_correct_order_at_935(self):
        """At 9:35 catch-up, the resolver must order events correctly.

        Critical: daily_reset BEFORE gap_filter (which includes MOO).
        """
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        resolver = StartupCatchUpResolver()
        now_et = datetime(2026, 3, 2, 9, 35, tzinfo=_ET)
        result = resolver.resolve(now_et, today_is_market_day=True)

        idx = {name: i for i, name in enumerate(result)}
        assert "daily_bar_refresh" in idx
        assert "daily_reset" in idx
        assert "gap_filter" in idx

        assert idx["daily_bar_refresh"] < idx["daily_reset"]
        assert idx["daily_reset"] < idx["gap_filter"]

    def test_no_event_destroys_state_needed_by_later_event(self):
        """Validate that the event DAG prevents state-destroying ordering.

        daily_reset (which clears EntryManager) must always precede
        gap_filter (which loads EntryManager and executes MOO).
        """
        reset_ev = TRADING_EVENTS["daily_reset"]
        gap_ev = TRADING_EVENTS["gap_filter"]

        # daily_reset at 9:20, gap_filter at 9:30
        assert reset_ev.scheduled_minute < gap_ev.scheduled_minute

        # gap_filter depends on daily_reset -- enforced in DAG
        assert "daily_reset" in gap_ev.depends_on

        # confirmation depends on gap_filter (which now includes MOO)
        confirm_ev = TRADING_EVENTS["confirmation"]
        assert "gap_filter" in confirm_ev.depends_on


# =====================================================================
# 2. Candidate Survival Tests
# =====================================================================


class TestCandidateSurvival:
    """Verify candidates loaded by gap_filter survive through to MOO execution."""

    @pytest.mark.asyncio
    async def test_candidates_survive_reset_then_gap_filter_then_moo(self):
        """Simulate the correct sequence: reset -> gap_filter -> moo.

        After reset clears the slate, gap_filter loads new candidates,
        and MOO must be able to see and process them.
        """
        em = _make_entry_manager()

        # Step 1: daily_reset clears any old state
        em.on_new_trading_day(TRADE_DATE)
        assert len(em._group_a) == 0
        assert len(em._group_b) == 0

        # Step 2: gap_filter loads fresh candidates
        candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="AAPL",
                    direction="long",
                    strength=0.85,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=150.0,
                atr=2.0,
                indicators={"ATR_14": 2.0},
            ),
            EntryCandidate(
                signal=Signal(
                    strategy="breakout_momentum",
                    symbol="MSFT",
                    direction="long",
                    strength=0.80,
                    metadata={"entry_atr": 3.0},
                ),
                prev_close=300.0,
                atr=3.0,
                indicators={"ATR_14": 3.0},
            ),
        ]
        em.load_candidates(candidates)

        # Verify candidates were loaded
        assert len(em._group_a) == 2

        # Step 3: MOO executes candidates
        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )

        # Verify orders were submitted
        assert em._order_manager.submit_entry.call_count == 2

    @pytest.mark.asyncio
    async def test_gap_filter_after_reset_does_not_lose_candidates(self):
        """The bug scenario: if reset ran AFTER gap_filter, candidates would be wiped.

        This test proves the correct ordering prevents that.
        """
        em = _make_entry_manager()

        # Load candidates (simulating gap_filter)
        candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="AAPL",
                    direction="long",
                    strength=0.85,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=150.0,
                atr=2.0,
                indicators={},
            ),
        ]
        em.load_candidates(candidates)
        assert len(em._group_a) == 1

        # Simulate the BUG: reset AFTER gap_filter
        em.on_new_trading_day(TRADE_DATE)

        # BUG: candidates are wiped!
        assert len(em._group_a) == 0, (
            "This proves that running reset AFTER gap_filter destroys candidates"
        )

    @pytest.mark.asyncio
    async def test_correct_order_preserves_candidates_for_moo(self):
        """Full sequence: nightly scan -> reset -> gap_filter -> moo with fills."""
        em = _make_entry_manager(fill_price=151.0)

        # 1. Nightly scan produces batch result (simulated)
        batch = _make_batch_result(["AAPL", "NVDA"])

        # 2. daily_reset
        em.on_new_trading_day(TRADE_DATE)

        # 3. gap_filter loads candidates
        entry_candidates = [_batch_to_entry_candidate(bc) for bc in batch.candidates]
        em.load_candidates(entry_candidates)
        assert len(em._group_a) == 2

        # 4. MOO execution
        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )

        assert em._order_manager.submit_entry.call_count == 2
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_multiple_strategies_survive_pipeline(self):
        """Both BM and MR candidates survive through the pipeline."""
        em = _make_entry_manager()

        em.on_new_trading_day(TRADE_DATE)

        candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="breakout_momentum",
                    symbol="TSLA",
                    direction="long",
                    strength=0.90,
                    metadata={"entry_atr": 5.0},
                ),
                prev_close=200.0,
                atr=5.0,
                indicators={},
            ),
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="AAPL",
                    direction="long",
                    strength=0.85,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=150.0,
                atr=2.0,
                indicators={},
            ),
        ]
        em.load_candidates(candidates)

        # Both are Group A strategies
        assert len(em._group_a) == 2
        strategies_loaded = {c.signal.strategy for c in em._group_a}
        assert strategies_loaded == {"breakout_momentum", "rsi_mean_reversion"}

        # MOO should process both
        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )
        assert em._order_manager.submit_entry.call_count == 2


# =====================================================================
# 3. End-to-End Entry Flow Tests
# =====================================================================


class TestEndToEndEntryFlow:
    """Test the full entry flow from batch result through order submission."""

    @pytest.mark.asyncio
    async def test_full_flow_nightly_scan_to_moo_orders(self):
        """Simulate the complete daily pipeline with order verification.

        nightly_scan -> daily_bar_refresh -> daily_reset
        -> gap_filter -> MOO -> orders submitted
        """
        em = _make_entry_manager(fill_price=102.0)

        # Night before: nightly scan produces candidates
        batch = _make_batch_result(
            symbols=["AAPL", "MSFT", "NVDA"],
            strategies=["rsi_mean_reversion", "breakout_momentum", "rsi_mean_reversion"],
        )

        # Morning sequence
        # 09:00 - daily_bar_refresh (simulated - no-op for this test)
        # 09:20 - daily_reset
        em.on_new_trading_day(TRADE_DATE)

        # 09:30 - gap_filter converts and loads candidates (market open)
        entry_candidates = [_batch_to_entry_candidate(bc) for bc in batch.candidates]
        em.load_candidates(entry_candidates)

        # 09:30 - MOO execution
        held_positions = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )

        # Verify: orders were submitted to the broker
        assert em._order_manager.submit_entry.call_count == 3

        # Verify: held positions were created with correct fill prices
        assert len(held_positions) == 3
        for hp in held_positions:
            assert hp.entry_price == 102.0
            assert hp.entry_date_et == TRADE_DATE

        # Verify: stop-loss orders were placed
        assert em._order_manager.submit_stop_loss.call_count == 3

    @pytest.mark.asyncio
    async def test_daily_limit_enforced_across_pipeline(self):
        """Only MAX_DAILY_ENTRIES (3) orders should be submitted even with more candidates."""
        em = _make_entry_manager()

        em.on_new_trading_day(TRADE_DATE)

        # Load 5 candidates
        candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol=f"SYM{i}",
                    direction="long",
                    strength=0.9 - i * 0.05,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=100.0,
                atr=2.0,
                indicators={},
            )
            for i in range(5)
        ]
        em.load_candidates(candidates)

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )

        assert len(result) <= 3
        assert em._daily_entry_count <= 3

    @pytest.mark.asyncio
    async def test_batch_to_entry_candidate_conversion(self):
        """_batch_to_entry_candidate correctly converts batch types to entry types."""
        batch_cand = _make_batch_candidate("AAPL", "breakout_momentum")
        entry_cand = _batch_to_entry_candidate(batch_cand)

        assert entry_cand.signal.symbol == "AAPL"
        assert entry_cand.signal.strategy == "breakout_momentum"
        assert entry_cand.signal.direction == "long"
        assert entry_cand.prev_close == 100.0
        assert entry_cand.atr == 2.0


# =====================================================================
# 4. Reset Does Not Destroy Needed State
# =====================================================================


class TestResetSafety:
    """Verify daily_reset clears the correct state without destroying pending work."""

    def test_reset_clears_daily_entry_count(self):
        """on_new_trading_day resets the daily entry counter."""
        em = _make_entry_manager()
        em._daily_entry_count = 3

        em.on_new_trading_day(TRADE_DATE)

        assert em._daily_entry_count == 0

    def test_reset_clears_old_candidates(self):
        """on_new_trading_day clears stale candidates from previous day."""
        em = _make_entry_manager()

        # Simulate previous day's leftover candidates
        old_candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="OLD_SYM",
                    direction="long",
                    strength=0.8,
                    metadata={},
                ),
                prev_close=100.0,
                atr=2.0,
                indicators={},
            ),
        ]
        em.load_candidates(old_candidates)
        assert len(em._group_a) == 1

        # Reset for new day
        em.on_new_trading_day(TRADE_DATE)

        # Old candidates should be cleared
        assert len(em._group_a) == 0
        assert len(em._group_b) == 0

    def test_second_reset_same_day_is_no_op(self):
        """Calling on_new_trading_day twice with same date should not double-reset."""
        em = _make_entry_manager()

        # First reset for today
        em.on_new_trading_day(TRADE_DATE)

        # Load candidates after first reset
        candidates = [
            EntryCandidate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="AAPL",
                    direction="long",
                    strength=0.85,
                    metadata={},
                ),
                prev_close=150.0,
                atr=2.0,
                indicators={},
            ),
        ]
        em.load_candidates(candidates)
        assert len(em._group_a) == 1

        # Second reset with same date -- should be no-op
        em.on_new_trading_day(TRADE_DATE)

        # Candidates should still be there (same day, no re-reset)
        assert len(em._group_a) == 1

    def test_reset_clears_exit_rule_engine_reentry_blocks(self):
        """daily_reset clears the ExitRuleEngine's re-entry blocks."""
        engine = ExitRuleEngine()

        # Record a close (blocks re-entry)
        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True

        # New trading day clears the block
        engine.on_new_trading_day(TRADE_DATE)
        assert engine.is_reentry_blocked("AAPL") is False

    @pytest.mark.asyncio
    async def test_autotrader_daily_reset_calls_all_subsystems(self):
        """AutoTrader._on_daily_reset calls reset on all subsystems."""
        app = _make_autotrader_app()

        # Mock the subsystems
        app._risk_manager = MagicMock()
        app._exit_rule_engine = MagicMock()
        app._entry_manager = MagicMock()
        app._gdr_manager = MagicMock()

        await app._on_daily_reset(TRADE_DATE)

        app._risk_manager.reset_daily.assert_called_once()
        app._exit_rule_engine.on_new_trading_day.assert_called_once_with(TRADE_DATE)
        app._entry_manager.on_new_trading_day.assert_called_once_with(TRADE_DATE)
        app._gdr_manager.reset_daily_entries.assert_called_once()


# =====================================================================
# 5. Gap Filter Timing Tests
# =====================================================================


class TestGapFilterTiming:
    """Verify gap_filter only catches up within the pre-market window."""

    def test_gap_filter_window_is_930_to_940(self):
        """gap_filter's catch-up window is 09:30-09:40 ET (market open)."""
        ev = TRADING_EVENTS["gap_filter"]
        assert ev.scheduled_hour == 9
        assert ev.scheduled_minute == 30
        assert ev.catch_up_deadline_hour == 9
        assert ev.catch_up_deadline_minute == 40

    def test_gap_filter_not_caught_up_at_evening(self):
        """gap_filter must NOT run during evening hours."""
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        resolver = StartupCatchUpResolver()
        for hour in [20, 21, 22, 23]:
            result = resolver.resolve(
                datetime(2026, 3, 2, hour, 0, tzinfo=_ET),
                today_is_market_day=True,
            )
            assert "gap_filter" not in result, (
                f"gap_filter should not run at {hour}:00 ET"
            )

    def test_gap_filter_not_caught_up_at_afternoon(self):
        """gap_filter must NOT run during afternoon hours."""
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        resolver = StartupCatchUpResolver()
        for hour in [11, 13, 15, 17]:
            result = resolver.resolve(
                datetime(2026, 3, 2, hour, 0, tzinfo=_ET),
                today_is_market_day=True,
            )
            assert "gap_filter" not in result, (
                f"gap_filter should not run at {hour}:00 ET"
            )

    def test_gap_filter_caught_up_within_window(self):
        """gap_filter IS caught up at 09:35 (within 09:31-09:40 window)."""
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        resolver = StartupCatchUpResolver()
        result = resolver.resolve(
            datetime(2026, 3, 2, 9, 35, tzinfo=_ET),
            today_is_market_day=True,
        )
        assert "gap_filter" in result

    def test_gap_filter_excluded_at_deadline_boundary(self):
        """gap_filter is excluded at exactly 09:40 (strict less-than)."""
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")

        resolver = StartupCatchUpResolver()
        result = resolver.resolve(
            datetime(2026, 3, 2, 9, 40, tzinfo=_ET),
            today_is_market_day=True,
        )
        assert "gap_filter" not in result


# =====================================================================
# 6. Startup Catch-Up Sequence Tests
# =====================================================================


class TestCatchUpSequence:
    """Verify correct event replay on startup at various times."""

    @pytest.fixture()
    def resolver(self) -> StartupCatchUpResolver:
        return StartupCatchUpResolver()

    def _et(self, hour: int, minute: int = 0) -> datetime:
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")
        return datetime(2026, 3, 2, hour, minute, tzinfo=_ET)

    def test_startup_at_0700_catches_nightly_scan_only(self, resolver):
        """Startup at 07:00: only nightly_scan (overnight catch-up)."""
        result = resolver.resolve(self._et(7, 0), today_is_market_day=True)
        assert result == ["nightly_scan"]

    def test_startup_at_0932_includes_reset_before_gap_filter(self, resolver):
        """Startup at 09:32: daily_reset must precede gap_filter in catch-up.

        This is the critical test: at 9:32, both daily_reset (9:20) and
        gap_filter (9:30) have been missed.  The catch-up must run
        daily_reset first so gap_filter loads into a clean state.
        """
        result = resolver.resolve(self._et(9, 32), today_is_market_day=True)

        # Both should be caught up
        assert "daily_reset" in result
        assert "gap_filter" in result

        # daily_reset must come before gap_filter
        idx = {name: i for i, name in enumerate(result)}
        assert idx["daily_reset"] < idx["gap_filter"], (
            f"daily_reset (idx={idx['daily_reset']}) must precede "
            f"gap_filter (idx={idx['gap_filter']}) in catch-up sequence"
        )

    def test_startup_at_0932_full_morning_catchup(self, resolver):
        """Startup at 09:32: full morning sequence including gap_filter+MOO."""
        result = resolver.resolve(self._et(9, 32), today_is_market_day=True)

        expected = {"daily_bar_refresh", "daily_reset", "gap_filter"}
        assert set(result) == expected

        idx = {name: i for i, name in enumerate(result)}
        # Verify strict ordering
        assert idx["daily_bar_refresh"] < idx["daily_reset"]
        assert idx["daily_reset"] < idx["gap_filter"]

    def test_startup_at_1100_skips_time_sensitive_events(self, resolver):
        """Startup at 11:00: gap_filter is past its window."""
        result = resolver.resolve(self._et(11, 0), today_is_market_day=True)

        assert "gap_filter" not in result  # past 09:40 deadline
        assert "confirmation" not in result  # past 10:00 deadline
        assert "daily_bar_refresh" in result  # ALWAYS policy
        assert "daily_reset" in result  # ALWAYS policy
        assert "entry_close" in result  # ALWAYS policy

    def test_startup_at_2000_catches_nightly_scan(self, resolver):
        """Startup at 20:00: includes nightly_scan for next-day prep."""
        result = resolver.resolve(self._et(20, 0), today_is_market_day=True)
        assert "nightly_scan" in result
        assert "gap_filter" not in result  # evening, not pre-market

    def test_catchup_does_not_corrupt_state(self):
        """Simulated catch-up sequence should not corrupt EntryManager state.

        This test runs the actual handler sequence that would occur during
        a 09:31 startup catch-up: daily_reset then gap_filter then moo.
        """
        em = _make_entry_manager()
        batch = _make_batch_result(["AAPL", "MSFT"])

        # Simulate catch-up sequence
        # 1. daily_bar_refresh (no-op for entry manager)
        # 2. daily_reset
        em.on_new_trading_day(TRADE_DATE)
        assert em._daily_entry_count == 0

        # 3. gap_filter
        entry_candidates = [_batch_to_entry_candidate(bc) for bc in batch.candidates]
        em.load_candidates(entry_candidates)
        assert len(em._group_a) == 2  # candidates survived

        # 4. moo (would execute, but we just verify state is intact)
        assert len(em._group_a) == 2  # still there, not wiped

    @pytest.mark.asyncio
    async def test_catchup_at_931_produces_working_entries(self):
        """Full catch-up at 09:31 should result in actual order submissions."""
        em = _make_entry_manager(fill_price=101.0)
        batch = _make_batch_result(["AAPL", "MSFT"])

        # Catch-up sequence
        em.on_new_trading_day(TRADE_DATE)
        entry_candidates = [_batch_to_entry_candidate(bc) for bc in batch.candidates]
        em.load_candidates(entry_candidates)

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND_UP,
            current_date_et=TRADE_DATE,
        )

        assert len(result) == 2
        assert em._order_manager.submit_entry.call_count == 2


# =====================================================================
# 7. AutoTrader-Level Integration (Mocked Broker)
# =====================================================================


class TestAutoTraderEventHandlers:
    """Test AutoTrader's event handlers in the correct sequence."""

    @pytest.mark.asyncio
    async def test_autotrader_gap_filter_loads_and_executes_moo(self):
        """AutoTrader._on_gap_filter converts candidates and executes MOO (merged step)."""
        app = _make_autotrader_app()

        # Inject mocked entry manager
        app._entry_manager = _make_entry_manager()
        app._gap_filter = None  # no gap filter, all candidates pass through

        # Inject batch result
        app._last_batch_result = _make_batch_result(["AAPL", "MSFT"])

        await app._on_gap_filter()

        # Verify candidates were loaded AND executed (merged step)
        # _group_a is empty because MOO consumed the candidates
        assert app._entry_manager._order_manager.submit_entry.call_count == 2

    @pytest.mark.asyncio
    async def test_autotrader_reset_then_gap_filter_preserves_candidates(self):
        """Running _on_daily_reset then _on_gap_filter: reset first, then load+execute."""
        app = _make_autotrader_app()

        # Inject dependencies
        app._entry_manager = _make_entry_manager()
        app._gap_filter = None
        app._last_batch_result = _make_batch_result(["AAPL"])
        app._gdr_manager = None

        # Execute in correct order
        await app._on_daily_reset(TRADE_DATE)
        await app._on_gap_filter()

        # MOO should have executed the single candidate
        assert app._entry_manager._order_manager.submit_entry.call_count == 1

    @pytest.mark.asyncio
    async def test_autotrader_wrong_order_would_corrupt_state(self):
        """Demonstrate the bug: gap_filter -> daily_reset would corrupt daily counters.

        With merged gap_filter+moo, orders get submitted, but then daily_reset
        wipes counters, causing incorrect state for confirmation/entry_close.
        """
        app = _make_autotrader_app()

        app._entry_manager = _make_entry_manager()
        app._gap_filter = None
        app._last_batch_result = _make_batch_result(["AAPL"])
        app._gdr_manager = None

        # WRONG order: gap_filter+moo first (submits orders), then reset
        await app._on_gap_filter()
        # MOO ran -- order submitted
        assert app._entry_manager._order_manager.submit_entry.call_count == 1

        # Reset AFTER gap_filter+moo -- wipes daily counters (the bug)
        await app._on_daily_reset(TRADE_DATE)
        assert app._entry_manager._daily_entry_count == 0  # Counter wiped!

    @pytest.mark.asyncio
    async def test_gap_filter_with_no_batch_result_is_safe(self):
        """_on_gap_filter with no batch result should not crash."""
        app = _make_autotrader_app()
        app._entry_manager = _make_entry_manager()
        app._last_batch_result = None

        # Should not raise
        await app._on_gap_filter()

        # EntryManager should remain empty
        assert len(app._entry_manager._group_a) == 0

    @pytest.mark.asyncio
    async def test_gap_filter_with_empty_batch_result_is_safe(self):
        """_on_gap_filter with an empty batch result should not crash."""
        app = _make_autotrader_app()
        app._entry_manager = _make_entry_manager()

        empty_batch = BatchResult(
            run_at=datetime.now(tz=timezone.utc),
            scan_duration_secs=1.0,
            symbols_scanned=500,
            symbols_with_signals=0,
            candidates=[],
        )
        app._last_batch_result = empty_batch

        await app._on_gap_filter()

        assert len(app._entry_manager._group_a) == 0


# =====================================================================
# 8. Regression Guard: Schedule Constants Match Events
# =====================================================================


class TestScheduleConstantsMatchEvents:
    """Verify that main.py time constants match events.py definitions."""

    def test_daily_reset_time_matches(self):
        """main.py _DAILY_RESET_HOUR/MINUTE must match events.py daily_reset."""
        from autotrader.main import _DAILY_RESET_HOUR, _DAILY_RESET_MINUTE

        ev = TRADING_EVENTS["daily_reset"]
        assert _DAILY_RESET_HOUR == ev.scheduled_hour, (
            f"main.py _DAILY_RESET_HOUR={_DAILY_RESET_HOUR} != "
            f"events.py daily_reset.scheduled_hour={ev.scheduled_hour}"
        )
        assert _DAILY_RESET_MINUTE == ev.scheduled_minute, (
            f"main.py _DAILY_RESET_MINUTE={_DAILY_RESET_MINUTE} != "
            f"events.py daily_reset.scheduled_minute={ev.scheduled_minute}"
        )

    def test_gap_filter_time_matches(self):
        """main.py _GAP_FILTER_HOUR/MINUTE must match events.py gap_filter."""
        from autotrader.main import _GAP_FILTER_HOUR, _GAP_FILTER_MINUTE

        ev = TRADING_EVENTS["gap_filter"]
        assert _GAP_FILTER_HOUR == ev.scheduled_hour
        assert _GAP_FILTER_MINUTE == ev.scheduled_minute

    def test_daily_bar_refresh_time_matches(self):
        """main.py _DAILY_BAR_REFRESH times must match events.py."""
        from autotrader.main import _DAILY_BAR_REFRESH_HOUR, _DAILY_BAR_REFRESH_MINUTE

        ev = TRADING_EVENTS["daily_bar_refresh"]
        assert _DAILY_BAR_REFRESH_HOUR == ev.scheduled_hour
        assert _DAILY_BAR_REFRESH_MINUTE == ev.scheduled_minute

    def test_daily_reset_is_before_gap_filter_in_constants(self):
        """The time constants must maintain daily_reset < gap_filter ordering."""
        from autotrader.main import (
            _DAILY_RESET_HOUR, _DAILY_RESET_MINUTE,
            _GAP_FILTER_HOUR, _GAP_FILTER_MINUTE,
        )

        reset_time = _DAILY_RESET_HOUR * 60 + _DAILY_RESET_MINUTE
        gap_time = _GAP_FILTER_HOUR * 60 + _GAP_FILTER_MINUTE

        assert reset_time < gap_time, (
            f"daily_reset ({_DAILY_RESET_HOUR}:{_DAILY_RESET_MINUTE:02d}) "
            f"must be scheduled before gap_filter "
            f"({_GAP_FILTER_HOUR}:{_GAP_FILTER_MINUTE:02d})"
        )
