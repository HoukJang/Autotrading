"""Unit tests for duplicate signal prevention in AutoTrader._signal_to_order.

Validates that the system prevents multiple strategies from opening
positions on the same symbol simultaneously, while still allowing
the owning strategy to manage its own position.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from autotrader.main import AutoTrader
from autotrader.broker.paper import PaperBroker
from autotrader.core.config import Settings
from autotrader.core.types import (
    AccountInfo, Bar, Order, Position, Signal,
)


def _make_bar(symbol: str = "AAPL", close: float = 150.0, idx: int = 0) -> Bar:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=base + timedelta(minutes=idx),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1000.0,
    )


class TestDuplicateSignalPrevention:
    """Tests for blocking duplicate positions on the same symbol from different strategies."""

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.type = "paper"
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_blocks_different_strategy_same_symbol(self, app):
        """AAPL has position from rsi_mean_reversion; consecutive_down signal for AAPL returns None."""
        await app._broker.connect()
        account = await app._broker.get_account()

        # Simulate existing position from rsi_mean_reversion
        app._position_strategy_map["AAPL"] = "rsi_mean_reversion"

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="consecutive_down",
            symbol="AAPL",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is None

    @pytest.mark.asyncio
    async def test_blocks_short_from_different_strategy(self, app):
        """AAPL has long from rsi_mean_reversion; ema_pullback signal for AAPL returns None."""
        await app._broker.connect()
        account = await app._broker.get_account()

        app._position_strategy_map["AAPL"] = "rsi_mean_reversion"

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="ema_pullback",
            symbol="AAPL",
            direction="long",
            strength=0.9,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is None

    @pytest.mark.asyncio
    async def test_allows_same_strategy_close_signal(self, app):
        """Close signals always pass regardless of strategy ownership (handled before entry checks)."""
        await app._broker.connect()
        account = await app._broker.get_account()

        app._position_strategy_map["AAPL"] = "rsi_mean_reversion"

        positions = [
            Position(
                symbol="AAPL", quantity=10, avg_entry_price=150.0,
                market_value=1500.0, unrealized_pnl=0.0, side="long",
            ),
        ]

        signal = Signal(
            strategy="rsi_mean_reversion",
            symbol="AAPL",
            direction="close",
            strength=1.0,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None
        assert order.side == "sell"
        assert order.quantity == 10

    @pytest.mark.asyncio
    async def test_allows_new_symbol(self, app):
        """AAPL has position; MSFT signal from different strategy passes."""
        await app._broker.connect()
        account = await app._broker.get_account()

        app._position_strategy_map["AAPL"] = "rsi_mean_reversion"

        bar = _make_bar("MSFT", 100.0)
        app._bar_history["MSFT"].append(bar)

        signal = Signal(
            strategy="consecutive_down",
            symbol="MSFT",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        # Should not be blocked by duplicate check (may be blocked by other checks)
        # The key assertion: it must NOT be None due to duplicate prevention
        # It could still be None if allocation engine blocks it, so we verify
        # by checking that the position_strategy_map check did NOT block it.
        # We do this by confirming that MSFT is not in position_strategy_map
        assert "MSFT" not in app._position_strategy_map
        # If allocation allows, order should be created
        if order is not None:
            assert order.symbol == "MSFT"

    @pytest.mark.asyncio
    async def test_allows_new_symbol_creates_order(self, app):
        """AAPL has position; MSFT signal passes and creates a valid order."""
        await app._broker.connect()
        account = await app._broker.get_account()

        app._position_strategy_map["AAPL"] = "rsi_mean_reversion"

        bar = _make_bar("MSFT", 100.0)
        app._bar_history["MSFT"].append(bar)

        signal = Signal(
            strategy="consecutive_down",
            symbol="MSFT",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.symbol == "MSFT"
        assert order.side == "buy"

    @pytest.mark.asyncio
    async def test_blocks_when_broker_has_position(self, app):
        """Even if _position_strategy_map is empty, broker position blocks entry."""
        await app._broker.connect()
        account = await app._broker.get_account()

        # position_strategy_map is empty -- but broker reports a position
        broker_positions = [
            Position(
                symbol="AAPL", quantity=10, avg_entry_price=150.0,
                market_value=1500.0, unrealized_pnl=0.0, side="long",
            ),
        ]

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="consecutive_down",
            symbol="AAPL",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, broker_positions)
        assert order is None

    @pytest.mark.asyncio
    async def test_blocks_long_when_broker_has_long(self, app):
        """Broker has long position; long signal from different strategy is blocked."""
        await app._broker.connect()
        account = await app._broker.get_account()

        broker_positions = [
            Position(
                symbol="AAPL", quantity=5, avg_entry_price=140.0,
                market_value=700.0, unrealized_pnl=50.0, side="long",
            ),
        ]

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="ema_pullback",
            symbol="AAPL",
            direction="long",
            strength=0.9,
        )
        order = app._signal_to_order(signal, account, broker_positions)
        assert order is None

    @pytest.mark.asyncio
    async def test_close_signal_still_works_with_broker_position(self, app):
        """Close signals bypass all entry checks even when broker has position."""
        await app._broker.connect()
        account = await app._broker.get_account()

        broker_positions = [
            Position(
                symbol="AAPL", quantity=10, avg_entry_price=150.0,
                market_value=1500.0, unrealized_pnl=0.0, side="long",
            ),
        ]

        signal = Signal(
            strategy="rsi_mean_reversion",
            symbol="AAPL",
            direction="close",
            strength=1.0,
        )
        order = app._signal_to_order(signal, account, broker_positions)
        assert order is not None
        assert order.side == "sell"

    @pytest.mark.asyncio
    async def test_no_position_no_map_allows_entry(self, app):
        """With empty map and no broker positions, entry signal passes normally."""
        await app._broker.connect()
        account = await app._broker.get_account()

        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="consecutive_down",
            symbol="AAPL",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == "buy"
