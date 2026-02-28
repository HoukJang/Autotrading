"""Unit tests for PositionMonitor (autotrader/execution/position_monitor.py).

Tests cover:
- Add/remove position tracking
- Bar processing triggers exit evaluation
- Exit decision triggers order submission
- Sold-today tracking (record_close called on exit)
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autotrader.core.types import Bar, OrderResult, Timeframe
from autotrader.execution.exit_rules import ExitDecision, ExitRuleEngine, HeldPosition
from autotrader.execution.position_monitor import PositionMonitor, MAX_POSITIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENTRY_DATE = date(2026, 2, 24)


def _make_bar(
    symbol: str = "AAPL",
    close: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    timeframe: Timeframe = Timeframe.DAILY,
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        open=99.0,
        high=high,
        low=low,
        close=close,
        volume=500_000,
        timeframe=timeframe,
    )


def _make_held_position(
    symbol: str = "AAPL",
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    entry_price: float = 100.0,
    bars_held: int = 1,
) -> HeldPosition:
    return HeldPosition(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        entry_price=entry_price,
        entry_atr=2.0,
        entry_date_et=ENTRY_DATE,
        bars_held=bars_held,
        qty=10.0,
        highest_price=entry_price,
        lowest_price=entry_price,
    )


def _make_monitor(
    exit_decision: ExitDecision | None = None,
    order_result: OrderResult | None = None,
) -> PositionMonitor:
    """Create a PositionMonitor with all dependencies mocked."""
    adapter = MagicMock()
    adapter.subscribe_bars = AsyncMock()
    adapter.run_stream = MagicMock()

    order_result = order_result or OrderResult(
        order_id="exit-001",
        symbol="AAPL",
        status="filled",
        filled_qty=10.0,
        filled_price=100.0,
    )
    order_manager = MagicMock()
    order_manager.submit_exit = AsyncMock(return_value=order_result)
    order_manager.calculate_pnl = MagicMock(return_value=50.0)

    exit_rule_engine = MagicMock(spec=ExitRuleEngine)
    exit_decision = exit_decision or ExitDecision(action="hold")
    exit_rule_engine.evaluate = MagicMock(return_value=exit_decision)
    exit_rule_engine.record_close = MagicMock()

    indicator_engine = MagicMock()
    indicator_engine.compute = MagicMock(return_value={"ATR_14": 2.0, "RSI_14": 50.0})

    monitor = PositionMonitor(
        adapter=adapter,
        order_manager=order_manager,
        exit_rule_engine=exit_rule_engine,
        indicator_engine=indicator_engine,
    )
    return monitor


# ---------------------------------------------------------------------------
# Test class: add/remove position
# ---------------------------------------------------------------------------

class TestPositionTracking:
    """Tests for add_position() and remove_position()."""

    def test_add_position_registers_symbol(self):
        """add_position() should add the symbol to monitored_symbols."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL")
        monitor.add_position(pos)
        assert "AAPL" in monitor.monitored_symbols

    def test_add_multiple_positions(self):
        """Multiple positions should all be tracked."""
        monitor = _make_monitor()
        for sym in ["AAPL", "MSFT", "NVDA"]:
            monitor.add_position(_make_held_position(sym))
        assert set(monitor.monitored_symbols) == {"AAPL", "MSFT", "NVDA"}

    def test_remove_position_returns_held_position(self):
        """remove_position() should return the HeldPosition and untrack it."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL")
        monitor.add_position(pos)

        removed = monitor.remove_position("AAPL")

        assert removed is pos
        assert "AAPL" not in monitor.monitored_symbols

    def test_remove_nonexistent_symbol_returns_none(self):
        """remove_position() for an untracked symbol should return None."""
        monitor = _make_monitor()
        result = monitor.remove_position("NONEXISTENT")
        assert result is None

    def test_max_positions_limit_enforced(self):
        """Should not track more than MAX_POSITIONS positions."""
        monitor = _make_monitor()
        for i in range(MAX_POSITIONS + 5):
            monitor.add_position(_make_held_position(f"SYM{i}"))

        assert len(monitor.monitored_symbols) <= MAX_POSITIONS

    def test_add_position_creates_bar_history(self):
        """add_position() should initialize bar history for the symbol."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL")
        monitor.add_position(pos)
        assert "AAPL" in monitor._bar_history

    def test_add_position_creates_aggregator(self):
        """add_position() should initialize DailyBarAggregator for the symbol."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL")
        monitor.add_position(pos)
        assert "AAPL" in monitor._aggregators


# ---------------------------------------------------------------------------
# Test class: bar processing
# ---------------------------------------------------------------------------

class TestBarProcessing:
    """Tests for _on_bar() and _on_daily_bar() bar handling."""

    @pytest.mark.asyncio
    async def test_daily_bar_triggers_exit_evaluation(self):
        """Processing a daily bar should call ExitRuleEngine.evaluate()."""
        monitor = _make_monitor(exit_decision=ExitDecision(action="hold"))
        pos = _make_held_position("AAPL", bars_held=1)
        monitor.add_position(pos)

        bar = _make_bar("AAPL", timeframe=Timeframe.DAILY)
        # _on_daily_bar calls datetime.now() internally to get current_date_et;
        # the exit_rule_engine is already mocked to return "hold" regardless of date,
        # so no datetime patching is needed here - we only verify evaluate() is called.
        await monitor._on_daily_bar(bar, pos)

        monitor._exit_rules.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_bar_increments_bars_held(self):
        """Processing a daily bar should increment bars_held by 1."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL", bars_held=2)
        monitor.add_position(pos)

        initial_bars_held = pos.bars_held
        bar = _make_bar("AAPL", timeframe=Timeframe.DAILY)

        await monitor._on_daily_bar(bar, pos)

        assert pos.bars_held == initial_bars_held + 1

    @pytest.mark.asyncio
    async def test_exit_decision_triggers_order_submission(self):
        """When ExitRuleEngine returns action='exit', submit_exit should be called."""
        exit_decision = ExitDecision(action="exit", reason="stop_loss", target_price=95.0)
        monitor = _make_monitor(exit_decision=exit_decision)
        pos = _make_held_position("AAPL", bars_held=2)
        monitor.add_position(pos)

        bar = _make_bar("AAPL", close=95.0, timeframe=Timeframe.DAILY)
        await monitor._on_daily_bar(bar, pos)

        monitor._order_manager.submit_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_hold_decision_does_not_trigger_order(self):
        """When ExitRuleEngine returns action='hold', no order should be submitted."""
        monitor = _make_monitor(exit_decision=ExitDecision(action="hold"))
        pos = _make_held_position("AAPL", bars_held=1)
        monitor.add_position(pos)

        bar = _make_bar("AAPL", timeframe=Timeframe.DAILY)
        await monitor._on_daily_bar(bar, pos)

        monitor._order_manager.submit_exit.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_calls_record_close(self):
        """After exit, record_close should be called to block re-entry."""
        exit_decision = ExitDecision(action="exit", reason="time_exit", target_price=0.0)
        monitor = _make_monitor(exit_decision=exit_decision)
        pos = _make_held_position("AAPL", bars_held=5)
        monitor.add_position(pos)

        bar = _make_bar("AAPL", timeframe=Timeframe.DAILY)
        await monitor._on_daily_bar(bar, pos)

        monitor._exit_rules.record_close.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_exit_removes_position_from_monitoring(self):
        """After exit, symbol should be removed from active monitoring."""
        exit_decision = ExitDecision(action="exit", reason="stop_loss")
        monitor = _make_monitor(exit_decision=exit_decision)
        pos = _make_held_position("AAPL", bars_held=2)
        monitor.add_position(pos)

        assert "AAPL" in monitor.monitored_symbols

        bar = _make_bar("AAPL", timeframe=Timeframe.DAILY)
        await monitor._on_daily_bar(bar, pos)

        assert "AAPL" not in monitor.monitored_symbols

    @pytest.mark.asyncio
    async def test_exit_callback_called_after_exit(self):
        """Registered exit callbacks should be called after a position is closed."""
        exit_decision = ExitDecision(action="exit", reason="stop_loss", target_price=95.0)
        monitor = _make_monitor(exit_decision=exit_decision)
        pos = _make_held_position("AAPL", bars_held=2)
        monitor.add_position(pos)

        callback_received = []

        async def on_exit(symbol, reason, fill_price, pnl):
            callback_received.append((symbol, reason, fill_price, pnl))

        monitor.register_exit_callback(on_exit)

        bar = _make_bar("AAPL", close=95.0, timeframe=Timeframe.DAILY)
        await monitor._on_daily_bar(bar, pos)

        assert len(callback_received) == 1
        assert callback_received[0][0] == "AAPL"
        assert callback_received[0][1] == "stop_loss"

    @pytest.mark.asyncio
    async def test_minute_bar_updates_price_extremes(self):
        """Minute bar should update MFE/MAE tracking via update_price_extremes."""
        monitor = _make_monitor()
        pos = _make_held_position("AAPL")
        pos.highest_price = 100.0
        pos.lowest_price = 100.0
        monitor.add_position(pos)

        # Minute bar with new high/low
        minute_bar = _make_bar("AAPL", high=105.0, low=97.0, timeframe=Timeframe.MINUTE)

        # Mock aggregator to not produce a daily bar
        monitor._aggregators["AAPL"] = MagicMock()
        monitor._aggregators["AAPL"].add = MagicMock(return_value=None)

        await monitor._on_bar(minute_bar)

        assert pos.highest_price >= 105.0
        assert pos.lowest_price <= 97.0

    @pytest.mark.asyncio
    async def test_bar_for_unknown_symbol_is_ignored(self):
        """Bar for a symbol not in positions should be silently ignored."""
        monitor = _make_monitor()
        bar = _make_bar("UNKNOWN_SYM")

        # Should not raise any exception
        await monitor._on_bar(bar)


# ---------------------------------------------------------------------------
# Test class: start and stop
# ---------------------------------------------------------------------------

class TestStartStop:
    """Tests for start() and stop() lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """start() should set _running to True."""
        monitor = _make_monitor()
        await monitor.start()
        assert monitor._running is True
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """stop() should set _running to False."""
        monitor = _make_monitor()
        await monitor.start()
        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_start_twice_does_not_raise(self):
        """Calling start() when already running should be a no-op."""
        monitor = _make_monitor()
        await monitor.start()
        await monitor.start()  # second call should not raise
        await monitor.stop()
