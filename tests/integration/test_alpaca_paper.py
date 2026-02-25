"""Integration tests for Alpaca paper trading connection.

These tests connect to the real Alpaca paper trading API to verify
that the AlpacaAdapter correctly interfaces with the Alpaca service.

Tests are skipped when ALPACA_API_KEY / ALPACA_SECRET_KEY are not set.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autotrader.broker.alpaca_adapter import AlpacaAdapter
from autotrader.core.types import AccountInfo, Bar, Order, Position

from tests.integration.conftest import skip_no_creds


@skip_no_creds
class TestAlpacaConnection:
    """Tests that verify basic Alpaca paper API connectivity."""

    async def test_connect_and_get_account(self, alpaca_adapter: AlpacaAdapter):
        """Connect to Alpaca paper and verify account info fields."""
        account = await alpaca_adapter.get_account()

        assert isinstance(account, AccountInfo)
        assert account.account_id != ""
        assert account.equity > 0
        assert account.cash >= 0
        assert account.buying_power >= 0
        assert account.portfolio_value >= 0

    async def test_get_positions(self, alpaca_adapter: AlpacaAdapter):
        """Verify get_positions returns a list (may be empty on paper account)."""
        positions = await alpaca_adapter.get_positions()

        assert isinstance(positions, list)
        for pos in positions:
            assert isinstance(pos, Position)
            assert pos.symbol != ""
            assert pos.quantity != 0
            assert pos.side in ("long", "short")


@skip_no_creds
class TestAlpacaOrderLifecycle:
    """Tests that submit and cancel orders on the Alpaca paper account."""

    async def test_submit_and_cancel_limit_order(self, alpaca_adapter: AlpacaAdapter):
        """Submit a far-from-market limit order and cancel it immediately.

        Uses a buy limit at $1.00 for AAPL so it will never fill,
        then cancels to leave no stale orders.
        """
        order = Order(
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=1.00,
            time_in_force="day",
        )

        result = await alpaca_adapter.submit_order(order)
        assert result.order_id != ""
        assert result.symbol == "AAPL"
        # alpaca-py str(OrderStatus.ACCEPTED) -> "OrderStatus.ACCEPTED"
        # so check that 'accepted' or 'new' appears in the lowered status
        status_lower = result.status.lower()
        assert any(
            s in status_lower for s in ("accepted", "new")
        ), f"Unexpected order status: {result.status}"

        # Small delay to let Alpaca register the order
        await asyncio.sleep(1)

        cancelled = await alpaca_adapter.cancel_order(result.order_id)
        assert cancelled is True


class TestBarConversion:
    """Tests for AlpacaAdapter._convert_bar (no API connection needed)."""

    def test_convert_bar_with_timezone(self):
        """Verify _convert_bar produces a correct Bar from an Alpaca-like object."""
        mock_bar = SimpleNamespace(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            open=150.0,
            high=155.0,
            low=149.0,
            close=153.0,
            volume=1_000_000,
        )

        adapter = AlpacaAdapter(api_key="fake", secret_key="fake", paper=True)
        bar = adapter._convert_bar(mock_bar)

        assert isinstance(bar, Bar)
        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.high == 155.0
        assert bar.low == 149.0
        assert bar.close == 153.0
        assert bar.volume == 1_000_000
        assert bar.timestamp.tzinfo is not None

    def test_convert_bar_naive_timestamp_gets_utc(self):
        """Verify naive timestamps are converted to UTC."""
        mock_bar = SimpleNamespace(
            symbol="MSFT",
            timestamp=datetime(2026, 1, 15, 14, 30, 0),  # naive
            open=300.0,
            high=305.0,
            low=298.0,
            close=302.0,
            volume=500_000,
        )

        adapter = AlpacaAdapter(api_key="fake", secret_key="fake", paper=True)
        bar = adapter._convert_bar(mock_bar)

        assert bar.timestamp.tzinfo == timezone.utc
        assert bar.symbol == "MSFT"
