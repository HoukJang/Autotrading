"""Unit tests for limit order support in Signal and AutoTrader._signal_to_order.

Validates that:
- Signal accepts an optional limit_price field
- Entry signals with limit_price produce limit orders
- Entry signals without limit_price produce market orders
- Close signals always produce market orders regardless of limit_price
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from autotrader.main import AutoTrader
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


class TestSignalLimitPrice:
    """Tests for the limit_price field on Signal."""

    def test_signal_with_limit_price(self):
        """Signal can be created with an explicit limit_price."""
        sig = Signal(
            strategy="test_strat",
            symbol="AAPL",
            direction="long",
            strength=0.8,
            limit_price=145.50,
        )
        assert sig.limit_price == 145.50

    def test_signal_default_no_limit(self):
        """Signal without limit_price defaults to None."""
        sig = Signal(
            strategy="test_strat",
            symbol="AAPL",
            direction="long",
            strength=0.8,
        )
        assert sig.limit_price is None


class TestLimitOrderFlow:
    """Tests for limit order creation in _signal_to_order."""

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.type = "paper"
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_order_with_limit_creates_limit_type(self, app):
        """When signal has limit_price, the resulting order has order_type='limit'."""
        await app._broker.connect()
        account = await app._broker.get_account()

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="adx_pullback",
            symbol="AAPL",
            direction="long",
            strength=0.8,
            limit_price=148.00,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.order_type == "limit"
        assert order.limit_price == 148.00
        assert order.side == "buy"

    @pytest.mark.asyncio
    async def test_order_without_limit_creates_market_type(self, app):
        """When signal has no limit_price, the resulting order has order_type='market'."""
        await app._broker.connect()
        account = await app._broker.get_account()

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="adx_pullback",
            symbol="AAPL",
            direction="long",
            strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.order_type == "market"
        assert order.limit_price is None

    @pytest.mark.asyncio
    async def test_close_signal_always_market(self, app):
        """Close signals always create market orders regardless of limit_price on signal."""
        await app._broker.connect()
        account = await app._broker.get_account()

        positions = [
            Position(
                symbol="AAPL",
                quantity=10,
                avg_entry_price=150.0,
                market_value=1500.0,
                unrealized_pnl=0.0,
                side="long",
            ),
        ]

        signal = Signal(
            strategy="rsi_mean_reversion",
            symbol="AAPL",
            direction="close",
            strength=1.0,
            limit_price=155.00,  # should be ignored for close signals
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None
        assert order.order_type == "market"
        assert order.limit_price is None
        assert order.side == "sell"
        assert order.quantity == 10

    @pytest.mark.asyncio
    async def test_short_signal_with_limit(self, app):
        """Short signal with limit_price produces a limit sell order."""
        await app._broker.connect()
        account = await app._broker.get_account()

        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)

        signal = Signal(
            strategy="overbought_short",
            symbol="AAPL",
            direction="short",
            strength=0.9,
            limit_price=152.00,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.order_type == "limit"
        assert order.limit_price == 152.00
        assert order.side == "sell"
