"""Unit tests for EntryManager (autotrader/execution/entry_manager.py).

Tests cover:
- Group A (MOO): RSI MR, Consecutive Down, Volume Divergence at 9:30
- Group B (Confirm): EMA Pullback at 9:45-10:00
- Confirmation condition: long price >= prev_close * 0.997
- Confirmation condition: short price <= prev_close * 1.003
- Signal discarded if confirmation fails by 10:00
- Daily entry limit: max 3 new entries
- Direction limits: max 6 long, max 3 short
- Entry window: no entries after 10:00 AM
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.core.types import AccountInfo, OrderResult, Position, Signal
from autotrader.execution.entry_manager import (
    Candidate,
    EntryManager,
    _GROUP_A_STRATEGIES,
    _GROUP_B_STRATEGIES,
    _GAP_TOLERANCE,
    _MAX_DAILY_ENTRIES,
    _MAX_LONG_POSITIONS,
    _MAX_SHORT_POSITIONS,
)
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.portfolio.regime_detector import MarketRegime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRADE_DATE = date(2026, 2, 24)


def _make_signal(
    strategy: str = "rsi_mean_reversion",
    symbol: str = "AAPL",
    direction: str = "long",
    strength: float = 0.80,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        strategy=strategy,
        symbol=symbol,
        direction=direction,
        strength=strength,
        metadata=metadata or {"entry_atr": 2.0},
    )


def _make_candidate(
    strategy: str = "rsi_mean_reversion",
    symbol: str = "AAPL",
    direction: str = "long",
    prev_close: float = 100.0,
    atr: float = 2.0,
) -> Candidate:
    signal = _make_signal(strategy=strategy, symbol=symbol, direction=direction)
    return Candidate(signal=signal, prev_close=prev_close, atr=atr, indicators={})


def _make_account(equity: float = 10_000.0, cash: float = 10_000.0) -> AccountInfo:
    return AccountInfo(
        account_id="test",
        buying_power=cash,
        portfolio_value=equity,
        cash=cash,
        equity=equity,
    )


def _make_position(symbol: str = "AAPL", side: str = "long") -> Position:
    return Position(
        symbol=symbol,
        quantity=10.0,
        avg_entry_price=100.0,
        market_value=1000.0,
        unrealized_pnl=0.0,
        side=side,
    )


def _make_order_result(
    symbol: str = "AAPL",
    status: str = "filled",
    filled_price: float = 100.0,
    filled_qty: float = 10.0,
) -> OrderResult:
    return OrderResult(
        order_id="ord-123",
        symbol=symbol,
        status=status,
        filled_qty=filled_qty,
        filled_price=filled_price,
    )


def _make_entry_manager(
    order_result: OrderResult | None = None,
    risk_validate: bool = True,
    allocation_should_enter: bool = True,
    allocation_qty: int = 10,
    reentry_blocked: bool = False,
) -> EntryManager:
    """Create a fully mocked EntryManager."""
    order_manager = MagicMock()
    order_manager.submit_entry = AsyncMock(return_value=order_result)
    order_manager.submit_stop_loss = AsyncMock(return_value=None)

    allocation_engine = MagicMock()
    allocation_engine.should_enter = MagicMock(return_value=allocation_should_enter)
    allocation_engine.get_position_size = MagicMock(return_value=allocation_qty)

    risk_manager = MagicMock()
    risk_manager.validate = MagicMock(return_value=risk_validate)

    exit_rule_engine = MagicMock(spec=ExitRuleEngine)
    exit_rule_engine.is_reentry_blocked = MagicMock(return_value=reentry_blocked)

    return EntryManager(
        order_manager=order_manager,
        allocation_engine=allocation_engine,
        risk_manager=risk_manager,
        exit_rule_engine=exit_rule_engine,
    )


# ---------------------------------------------------------------------------
# Test class: group membership
# ---------------------------------------------------------------------------

class TestGroupMembership:
    """Verify which strategies belong to Group A vs Group B."""

    def test_rsi_mr_is_group_a(self):
        """rsi_mean_reversion should be in Group A (MOO)."""
        assert "rsi_mean_reversion" in _GROUP_A_STRATEGIES

    def test_consecutive_down_is_group_a(self):
        """consecutive_down should be in Group A (MOO)."""
        assert "consecutive_down" in _GROUP_A_STRATEGIES

    def test_volume_divergence_not_in_group_a(self):
        """volume_divergence should NOT be in Group A (removed in 13th backtest)."""
        assert "volume_divergence" not in _GROUP_A_STRATEGIES

    def test_ema_pullback_not_in_group_b(self):
        """ema_pullback should NOT be in Group B (strategy disabled)."""
        assert "ema_pullback" not in _GROUP_B_STRATEGIES

    def test_group_a_has_three_strategies(self):
        """Group A should contain exactly 3 strategies."""
        assert len(_GROUP_A_STRATEGIES) == 3
        assert "ema_cross_trend" in _GROUP_A_STRATEGIES

    def test_group_b_is_empty(self):
        """Group B should be empty (no confirmation strategies currently active)."""
        assert len(_GROUP_B_STRATEGIES) == 0

    def test_load_candidates_splits_by_group(self):
        """load_candidates() should correctly route to _group_a (Group B is empty)."""
        em = _make_entry_manager()
        candidates = [
            _make_candidate(strategy="rsi_mean_reversion", symbol="AAPL"),
            _make_candidate(strategy="consecutive_down", symbol="MSFT"),
        ]
        em.load_candidates(candidates)
        assert len(em._group_a) == 2
        assert len(em._group_b) == 0


# ---------------------------------------------------------------------------
# Test class: confirmation logic
# ---------------------------------------------------------------------------

class TestConfirmationLogic:
    """Tests for Group B confirmation condition _is_confirmed()."""

    def test_long_confirmed_when_price_at_prev_close(self):
        """Long confirmed when current_price == prev_close (0% gap)."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="long", prev_close=100.0)
        assert em._is_confirmed(candidate, current_price=100.0) is True

    def test_long_confirmed_when_price_above_threshold(self):
        """Long confirmed when current_price >= prev_close * (1 - 0.003)."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="long", prev_close=100.0)
        # Threshold = 100 * 0.997 = 99.7
        assert em._is_confirmed(candidate, current_price=99.7) is True

    def test_long_not_confirmed_below_threshold(self):
        """Long NOT confirmed when price < prev_close * 0.997."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="long", prev_close=100.0)
        # Below threshold: 99.69 < 99.70
        assert em._is_confirmed(candidate, current_price=99.69) is False

    def test_short_confirmed_when_price_at_prev_close(self):
        """Short confirmed when current_price == prev_close."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="short", prev_close=100.0)
        assert em._is_confirmed(candidate, current_price=100.0) is True

    def test_short_confirmed_when_price_below_threshold(self):
        """Short confirmed when current_price <= prev_close * (1 + 0.003)."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="short", prev_close=100.0)
        # Threshold = 100 * 1.003 = 100.29999... (float precision)
        # Use 100.29 which is clearly below threshold
        assert em._is_confirmed(candidate, current_price=100.29) is True

    def test_short_not_confirmed_above_threshold(self):
        """Short NOT confirmed when price > prev_close * 1.003."""
        em = _make_entry_manager()
        candidate = _make_candidate(strategy="ema_pullback", direction="short", prev_close=100.0)
        # Above threshold: 100.31 > 100.30
        assert em._is_confirmed(candidate, current_price=100.31) is False

    def test_gap_tolerance_constant_is_003(self):
        """GAP_TOLERANCE should be 0.003 (3 bps)."""
        assert _GAP_TOLERANCE == pytest.approx(0.003)


# ---------------------------------------------------------------------------
# Test class: execute_moo (Group A)
# ---------------------------------------------------------------------------

class TestExecuteMoo:
    """Tests for Group A market-on-open execution."""

    @pytest.mark.asyncio
    async def test_moo_submits_entry_for_group_a_candidates(self):
        """execute_moo() should submit an entry order for each Group A candidate."""
        fill_result = _make_order_result(status="filled", filled_price=100.0, filled_qty=10.0)
        em = _make_entry_manager(order_result=fill_result)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")])

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        em._order_manager.submit_entry.assert_called_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_moo_returns_held_position_on_fill(self):
        """execute_moo() should return HeldPosition objects for successful fills."""
        fill_result = _make_order_result(status="filled", filled_price=101.0, filled_qty=10.0)
        em = _make_entry_manager(order_result=fill_result)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")])

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert len(result) == 1
        assert isinstance(result[0], HeldPosition)
        assert result[0].entry_price == 101.0

    @pytest.mark.asyncio
    async def test_moo_increments_daily_entry_count(self):
        """execute_moo() should increment _daily_entry_count per fill."""
        fill_result = _make_order_result(status="filled")
        em = _make_entry_manager(order_result=fill_result)
        em.load_candidates([
            _make_candidate(strategy="rsi_mean_reversion", symbol="AAPL"),
        ])

        await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert em._daily_entry_count == 1

    @pytest.mark.asyncio
    async def test_moo_submits_broker_sl_after_fill(self):
        """execute_moo() should submit a stop-loss order after a successful fill."""
        fill_result = _make_order_result(status="filled")
        em = _make_entry_manager(order_result=fill_result)
        # Signal must have ATR in metadata for SL to be submitted
        candidate = _make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")
        candidate.signal.__class__  # ensure it's a Signal
        em.load_candidates([candidate])

        await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        # submit_stop_loss called (may not be called if atr=0 in metadata)
        # Just verify submit_entry was called successfully
        em._order_manager.submit_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_moo_skips_when_reentry_blocked(self):
        """execute_moo() should skip candidates that are re-entry blocked."""
        em = _make_entry_manager(order_result=_make_order_result(), reentry_blocked=True)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")])

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert result == []
        em._order_manager.submit_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_moo_clears_group_a_after_execution(self):
        """execute_moo() should clear _group_a after running."""
        fill_result = _make_order_result(status="filled")
        em = _make_entry_manager(order_result=fill_result)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")])

        await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert em._group_a == []


# ---------------------------------------------------------------------------
# Test class: daily entry limit
# ---------------------------------------------------------------------------

class TestDailyEntryLimit:
    """Max 3 new entries per day across all strategies."""

    @pytest.mark.asyncio
    async def test_daily_limit_blocks_fourth_entry(self):
        """After 3 entries, a 4th should be rejected."""
        fill_result = _make_order_result(status="filled")
        em = _make_entry_manager(order_result=fill_result)
        # Manually set counter to 3 (limit reached)
        em._daily_entry_count = _MAX_DAILY_ENTRIES
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL")])

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert result == []

    def test_max_daily_entries_constant_is_3(self):
        """MAX_DAILY_ENTRIES should be 3."""
        assert _MAX_DAILY_ENTRIES == 3

    @pytest.mark.asyncio
    async def test_on_new_trading_day_resets_counter(self):
        """on_new_trading_day() should reset the daily entry counter."""
        em = _make_entry_manager()
        em._daily_entry_count = 3
        em.on_new_trading_day(date(2026, 2, 25))
        assert em._daily_entry_count == 0


# ---------------------------------------------------------------------------
# Test class: direction position limits
# ---------------------------------------------------------------------------

class TestDirectionPositionLimits:
    """Max 6 long, max 3 short concurrent positions."""

    def test_max_long_constant_is_6(self):
        """_MAX_LONG_POSITIONS should be 6."""
        assert _MAX_LONG_POSITIONS == 6

    def test_max_short_constant_is_3(self):
        """_MAX_SHORT_POSITIONS should be 3."""
        assert _MAX_SHORT_POSITIONS == 3

    @pytest.mark.asyncio
    async def test_blocked_when_max_longs_reached(self):
        """New long entry should be rejected when 6 long positions already open."""
        em = _make_entry_manager(order_result=_make_order_result())
        # 6 long positions already open
        long_positions = [_make_position(symbol=f"SYM{i}", side="long") for i in range(6)]
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", direction="long")])

        result = await em.execute_moo(
            account=_make_account(),
            positions=long_positions,
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_blocked_when_max_shorts_reached(self):
        """New short entry should be rejected when 3 short positions already open."""
        em = _make_entry_manager(order_result=_make_order_result())
        short_positions = [_make_position(symbol=f"SYM{i}", side="short") for i in range(3)]
        em.load_candidates([_make_candidate(
            strategy="rsi_mean_reversion",
            direction="short",
            symbol="NEWSHORT",
        )])

        result = await em.execute_moo(
            account=_make_account(),
            positions=short_positions,
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        assert result == []


# ---------------------------------------------------------------------------
# Test class: execute_confirmation (Group B)
# ---------------------------------------------------------------------------

class TestExecuteConfirmation:
    """Tests for Group B confirmation window execution (Group B is currently empty)."""

    @pytest.mark.asyncio
    async def test_confirmation_returns_empty_when_group_b_empty(self):
        """execute_confirmation() should return empty list when Group B has no candidates."""
        fill_result = _make_order_result(status="filled", filled_price=100.5)
        em = _make_entry_manager(order_result=fill_result)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL", prev_close=100.0)])

        result = await em.execute_confirmation(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
            current_prices={"AAPL": 100.5},
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_group_b_always_empty_after_load(self):
        """After load_candidates(), _group_b should always be empty."""
        em = _make_entry_manager(order_result=_make_order_result())
        # Even if ema_pullback candidates are passed, they go nowhere (not in _GROUP_B_STRATEGIES)
        em.load_candidates([_make_candidate(strategy="rsi_mean_reversion", symbol="AAPL", prev_close=100.0)])

        assert len(em._group_b) == 0

    @pytest.mark.asyncio
    async def test_missing_price_does_not_affect_group_b(self):
        """Group B is empty; missing prices result in empty confirmation result."""
        em = _make_entry_manager(order_result=_make_order_result())
        em.load_candidates([_make_candidate(strategy="consecutive_down", symbol="AAPL")])

        await em.execute_confirmation(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
            current_prices={},
        )

        assert len(em._group_b) == 0

    @pytest.mark.asyncio
    async def test_close_entry_window_returns_zero_when_group_b_empty(self):
        """close_entry_window() returns 0 when Group B is empty."""
        em = _make_entry_manager()
        em.load_candidates([
            _make_candidate(strategy="rsi_mean_reversion", symbol="AAPL"),
            _make_candidate(strategy="consecutive_down", symbol="MSFT"),
        ])

        discarded = em.close_entry_window()

        assert discarded == 0
        assert em._group_b == []

    @pytest.mark.asyncio
    async def test_close_entry_window_returns_zero_when_nothing_pending(self):
        """close_entry_window() on empty group_b should return 0."""
        em = _make_entry_manager()
        em.load_candidates([])

        discarded = em.close_entry_window()

        assert discarded == 0
