"""Integration tests for the Entry-to-Exit pipeline.

Tests the complete flow:
  Entry fills -> PositionMonitor tracks -> ExitRuleEngine evaluates
  -> OrderManager exits

Uses real ExitRuleEngine logic but mocked Alpaca adapter and order manager.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.core.types import Bar, OrderResult, Timeframe
from autotrader.execution.exit_rules import ExitDecision, ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.execution.position_monitor import PositionMonitor
from autotrader.indicators.engine import IndicatorEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENTRY_DATE = date(2026, 2, 24)   # Monday
NEXT_DAY = date(2026, 2, 25)     # Tuesday


def _make_bar(
    symbol: str = "AAPL",
    close: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    open_: float = 99.0,
    timeframe: Timeframe = Timeframe.DAILY,
    dt: datetime | None = None,
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=dt or datetime.now(timezone.utc),
        open=open_,
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
    entry_atr: float = 2.0,
    bars_held: int = 0,
    entry_date_et: date = ENTRY_DATE,
) -> HeldPosition:
    return HeldPosition(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        entry_price=entry_price,
        entry_atr=entry_atr,
        entry_date_et=entry_date_et,
        bars_held=bars_held,
        qty=10.0,
        highest_price=entry_price,
        lowest_price=entry_price,
    )


def _make_monitor_with_real_exit_engine(
    exit_result: OrderResult | None = None,
) -> tuple[PositionMonitor, ExitRuleEngine]:
    """Create PositionMonitor with a real ExitRuleEngine but mocked adapter/orders."""
    adapter = MagicMock()
    adapter.subscribe_bars = AsyncMock()

    exit_result = exit_result or OrderResult(
        order_id="exit-001",
        symbol="AAPL",
        status="filled",
        filled_qty=10.0,
        filled_price=95.0,
    )

    order_manager = MagicMock(spec=OrderManager)
    order_manager.submit_exit = AsyncMock(return_value=exit_result)
    order_manager.calculate_pnl = MagicMock(return_value=-50.0)

    exit_rule_engine = ExitRuleEngine()

    indicator_engine = MagicMock(spec=IndicatorEngine)
    indicator_engine.compute = MagicMock(return_value={"ATR_14": 2.0, "RSI_14": 45.0})

    monitor = PositionMonitor(
        adapter=adapter,
        order_manager=order_manager,
        exit_rule_engine=exit_rule_engine,
        indicator_engine=indicator_engine,
    )
    return monitor, exit_rule_engine


# ---------------------------------------------------------------------------
# Test class: Day 1 -> Day 2 transition
# ---------------------------------------------------------------------------

class TestDay1ToDay2Transition:
    """Verifies that Day 1 skips SL/TP and Day 2 applies them."""

    @pytest.mark.asyncio
    async def test_day1_no_sl_triggers_even_on_large_loss(self):
        """On entry day, normal SL should not trigger even with -5% loss."""
        monitor, engine = _make_monitor_with_real_exit_engine()

        pos = _make_held_position(
            symbol="AAPL",
            entry_price=100.0,
            entry_atr=2.0,
            bars_held=0,
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        # -5% loss on Day 1 (entry_date_et = ENTRY_DATE)
        bar = _make_bar(symbol="AAPL", close=95.0, high=97.0, low=94.0)

        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = ENTRY_DATE

            await monitor._on_daily_bar(bar, pos)

        # Position should still be tracked (no exit)
        assert "AAPL" in monitor.monitored_symbols
        monitor._order_manager.submit_exit.assert_not_called()

    @pytest.mark.asyncio
    async def test_day2_sl_triggers_for_rsi_mr(self):
        """On Day 2, RSI MR long SL should trigger at the correct level."""
        monitor, engine = _make_monitor_with_real_exit_engine()

        # RSI MR long: SL at 2.0x ATR (from code)
        entry_price = 100.0
        atr = 2.0
        from autotrader.execution.exit_rules import _SL_ATR_MULT
        sl_mult = _SL_ATR_MULT["rsi_mean_reversion"]["long"]  # 2.0
        sl_price = entry_price - sl_mult * atr  # 100 - 4 = 96

        pos = _make_held_position(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            entry_price=entry_price,
            entry_atr=atr,
            bars_held=1,  # Day 2+
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        # Close just below SL
        bar = _make_bar(symbol="AAPL", close=sl_price - 0.10, high=97.0, low=sl_price - 0.5)

        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = NEXT_DAY

            await monitor._on_daily_bar(bar, pos)

        monitor._order_manager.submit_exit.assert_called_once()


# ---------------------------------------------------------------------------
# Test class: re-entry blocking end-to-end
# ---------------------------------------------------------------------------

class TestReEntryBlockingEndToEnd:
    """Tests re-entry blocking through the full PositionMonitor -> ExitRuleEngine chain."""

    @pytest.mark.asyncio
    async def test_exit_blocks_symbol_for_remainder_of_day(self):
        """After exit, ExitRuleEngine should block the symbol from re-entry."""
        exit_decision = ExitDecision(action="exit", reason="stop_loss", target_price=95.0)

        adapter = MagicMock()
        adapter.subscribe_bars = AsyncMock()

        order_manager = MagicMock(spec=OrderManager)
        order_manager.submit_exit = AsyncMock(return_value=OrderResult(
            order_id="exit-001", symbol="AAPL", status="filled",
            filled_qty=10.0, filled_price=95.0,
        ))
        order_manager.calculate_pnl = MagicMock(return_value=-50.0)

        exit_rule_engine = ExitRuleEngine()

        mock_indicator_engine = MagicMock(spec=IndicatorEngine)
        mock_indicator_engine.compute = MagicMock(return_value={"ATR_14": 2.0, "RSI_14": 50.0})
        mock_indicator_engine.evaluate = MagicMock(return_value=exit_decision)

        # Override evaluate to force exit on second daily bar
        original_evaluate = exit_rule_engine.evaluate
        call_count = {"n": 0}

        def forced_exit(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                return ExitDecision(action="exit", reason="stop_loss", target_price=95.0)
            return ExitDecision(action="hold")

        exit_rule_engine.evaluate = forced_exit

        monitor = PositionMonitor(
            adapter=adapter,
            order_manager=order_manager,
            exit_rule_engine=exit_rule_engine,
            indicator_engine=mock_indicator_engine,
        )

        pos = _make_held_position("AAPL", bars_held=2, entry_date_et=ENTRY_DATE)
        monitor.add_position(pos)

        bar = _make_bar("AAPL", close=95.0, high=97.0, low=94.0)
        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = NEXT_DAY

            await monitor._on_daily_bar(bar, pos)

        # After exit, re-entry should be blocked
        assert exit_rule_engine.is_reentry_blocked("AAPL") is True

    @pytest.mark.asyncio
    async def test_reentry_block_cleared_on_new_trading_day(self):
        """After calling on_new_trading_day(), the block should be lifted."""
        _, engine = _make_monitor_with_real_exit_engine()

        engine.record_close("AAPL")
        assert engine.is_reentry_blocked("AAPL") is True

        # New trading day clears the block
        engine.on_new_trading_day(NEXT_DAY)
        assert engine.is_reentry_blocked("AAPL") is False


# ---------------------------------------------------------------------------
# Test class: emergency stop end-to-end
# ---------------------------------------------------------------------------

class TestEmergencyStopEndToEnd:
    """Full pipeline test for Day 1 emergency stops."""

    @pytest.mark.asyncio
    async def test_10pct_loss_triggers_immediate_emergency_exit(self):
        """Day 1: -10% loss should trigger emergency exit via PositionMonitor."""
        monitor, engine = _make_monitor_with_real_exit_engine()

        entry_price = 100.0
        pos = _make_held_position(
            symbol="AAPL",
            entry_price=entry_price,
            entry_atr=2.0,
            bars_held=0,  # Still Day 1
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        # -10% loss bar (entry_price=100, close=90)
        bar = _make_bar(symbol="AAPL", close=90.0, high=92.0, low=89.0)

        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = ENTRY_DATE

            await monitor._on_daily_bar(bar, pos)

        # Emergency exit should have been triggered
        monitor._order_manager.submit_exit.assert_called_once()
        assert "AAPL" not in monitor.monitored_symbols

    @pytest.mark.asyncio
    async def test_7pct_loss_two_bars_triggers_confirmed_emergency(self):
        """Day 1: -7% over 2 bars should trigger confirmed emergency stop."""
        monitor, engine = _make_monitor_with_real_exit_engine()

        entry_price = 100.0
        pos = _make_held_position(
            symbol="AAPL",
            entry_price=entry_price,
            entry_atr=2.0,
            bars_held=0,
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        # First bar: -7% (no exit, just counter increments)
        bar1 = _make_bar(symbol="AAPL", close=93.0, high=95.0, low=92.0)
        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = ENTRY_DATE

            await monitor._on_daily_bar(bar1, pos)

        monitor._order_manager.submit_exit.assert_not_called()
        assert "AAPL" in monitor.monitored_symbols

        # Second bar: -7% (triggers exit)
        bar2 = _make_bar(symbol="AAPL", close=93.0, high=94.0, low=92.5)
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = ENTRY_DATE

            await monitor._on_daily_bar(bar2, pos)

        monitor._order_manager.submit_exit.assert_called_once()


# ---------------------------------------------------------------------------
# Test class: time-based exit end-to-end
# ---------------------------------------------------------------------------

class TestTimeBasedExitEndToEnd:
    """Full pipeline for time-based forced exits."""

    @pytest.mark.asyncio
    async def test_rsi_mr_time_exit_at_5_days(self):
        """RSI MR position held for 5 bars should trigger time exit."""
        monitor, engine = _make_monitor_with_real_exit_engine()

        pos = _make_held_position(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            entry_price=100.0,
            entry_atr=2.0,
            bars_held=4,  # Will be incremented to 5 in _on_daily_bar
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        # Neutral bar (no SL or TP trigger)
        bar = _make_bar(symbol="AAPL", close=100.5, high=101.0, low=99.5)

        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = NEXT_DAY

            # Set indicator to return RSI below TP threshold
            monitor._indicator_engine.compute = MagicMock(
                return_value={"ATR_14": 2.0, "RSI_14": 49.0, "BBANDS_20": {"pct_b": 0.45}}
            )

            await monitor._on_daily_bar(bar, pos)

        monitor._order_manager.submit_exit.assert_called_once()
        assert "AAPL" not in monitor.monitored_symbols

    @pytest.mark.asyncio
    async def test_exit_callback_invoked_on_time_exit(self):
        """Exit callbacks should be called with correct arguments on time exit."""
        monitor, engine = _make_monitor_with_real_exit_engine()
        monitor._order_manager.calculate_pnl = MagicMock(return_value=25.0)

        pos = _make_held_position(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            bars_held=4,
            entry_date_et=ENTRY_DATE,
        )
        monitor.add_position(pos)

        received_callbacks = []

        async def on_exit(symbol, reason, fill_price, pnl):
            received_callbacks.append({
                "symbol": symbol,
                "reason": reason,
                "fill_price": fill_price,
                "pnl": pnl,
            })

        monitor.register_exit_callback(on_exit)

        bar = _make_bar("AAPL", close=100.0, high=101.0, low=99.0)
        from unittest.mock import patch
        with patch(
            "autotrader.execution.position_monitor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.astimezone.return_value.date.return_value = NEXT_DAY

            monitor._indicator_engine.compute = MagicMock(
                return_value={"ATR_14": 2.0, "RSI_14": 49.0, "BBANDS_20": {"pct_b": 0.45}}
            )

            await monitor._on_daily_bar(bar, pos)

        assert len(received_callbacks) == 1
        assert received_callbacks[0]["symbol"] == "AAPL"
        assert received_callbacks[0]["reason"] == "time_exit"
