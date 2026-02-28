"""Unit tests for OrderManager (autotrader/execution/order_manager.py).

Tests cover:
- Market order submission
- Stop-loss order submission
- Exit order submission (cancels existing SL first)
- Retry on failure
- PnL calculation (long and short)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.core.types import OrderResult
from autotrader.execution.order_manager import OrderManager, ActiveOrder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order_result(
    order_id: str = "ord-001",
    symbol: str = "AAPL",
    status: str = "filled",
    filled_qty: float = 10.0,
    filled_price: float = 100.0,
) -> OrderResult:
    return OrderResult(
        order_id=order_id,
        symbol=symbol,
        status=status,
        filled_qty=filled_qty,
        filled_price=filled_price,
    )


def _make_adapter(order_result: OrderResult | None = None, cancel_success: bool = True) -> MagicMock:
    adapter = MagicMock()
    adapter.submit_order = AsyncMock(return_value=order_result or _make_order_result())
    adapter.cancel_order = AsyncMock(return_value=cancel_success)
    return adapter


def _make_order_manager(
    order_result: OrderResult | None = None,
    cancel_success: bool = True,
) -> OrderManager:
    adapter = _make_adapter(order_result=order_result, cancel_success=cancel_success)
    return OrderManager(adapter=adapter)


# ---------------------------------------------------------------------------
# Test class: submit_entry
# ---------------------------------------------------------------------------

class TestSubmitEntry:
    """Tests for market and limit entry order submission."""

    @pytest.mark.asyncio
    async def test_submit_market_entry_returns_order_result(self):
        """submit_entry() should return an OrderResult on success."""
        result = _make_order_result(status="filled", filled_price=100.0)
        om = _make_order_manager(order_result=result)

        response = await om.submit_entry("AAPL", "buy", 10.0, "market")

        assert response is not None
        assert response.status == "filled"
        assert response.filled_price == 100.0

    @pytest.mark.asyncio
    async def test_submit_entry_tracks_active_order(self):
        """Successful fill should add entry to active_orders tracking."""
        result = _make_order_result(order_id="ord-123", status="filled")
        om = _make_order_manager(order_result=result)

        await om.submit_entry("AAPL", "buy", 10.0, "market")

        assert "ord-123" in om._active_orders
        assert om.active_order_count == 1

    @pytest.mark.asyncio
    async def test_submit_entry_zero_qty_returns_none(self):
        """submit_entry() with qty=0 should return None without calling adapter."""
        om = _make_order_manager()

        result = await om.submit_entry("AAPL", "buy", 0.0, "market")

        assert result is None
        om._adapter.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_entry_negative_qty_returns_none(self):
        """submit_entry() with negative qty should return None."""
        om = _make_order_manager()

        result = await om.submit_entry("AAPL", "buy", -5.0, "market")

        assert result is None
        om._adapter.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_entry_retries_on_exception(self):
        """submit_entry() should retry up to 3 times on exception."""
        call_count = {"n": 0}

        async def flaky_submit(order):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("transient error")
            return _make_order_result()

        adapter = MagicMock()
        adapter.submit_order = AsyncMock(side_effect=flaky_submit)
        om = OrderManager(adapter=adapter)

        from unittest.mock import patch
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await om.submit_entry("AAPL", "buy", 10.0, "market")

        assert result is not None
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_submit_entry_returns_none_after_all_retries_exhausted(self):
        """submit_entry() should return None after 3 failed attempts."""
        adapter = MagicMock()
        adapter.submit_order = AsyncMock(side_effect=RuntimeError("persistent error"))
        om = OrderManager(adapter=adapter)

        from unittest.mock import patch
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await om.submit_entry("AAPL", "buy", 10.0, "market")

        assert result is None
        assert adapter.submit_order.call_count == 3

    @pytest.mark.asyncio
    async def test_submit_limit_entry_passes_limit_price(self):
        """submit_entry() with limit order should pass limit_price to adapter."""
        result = _make_order_result(status="accepted")
        om = _make_order_manager(order_result=result)

        from autotrader.core.types import Order
        submitted_orders = []
        om._adapter.submit_order = AsyncMock(side_effect=lambda o: (
            submitted_orders.append(o) or result
        ))

        await om.submit_entry("AAPL", "buy", 10.0, "limit", limit_price=99.50)

        assert len(submitted_orders) == 1
        assert submitted_orders[0].limit_price == 99.50
        assert submitted_orders[0].order_type == "limit"


# ---------------------------------------------------------------------------
# Test class: submit_stop_loss
# ---------------------------------------------------------------------------

class TestSubmitStopLoss:
    """Tests for stop-loss order submission."""

    @pytest.mark.asyncio
    async def test_submit_stop_loss_succeeds(self):
        """submit_stop_loss() should submit a stop order and return result."""
        sl_result = _make_order_result(order_id="sl-001", status="accepted")
        om = _make_order_manager(order_result=sl_result)

        response = await om.submit_stop_loss(
            symbol="AAPL",
            side="sell",
            qty=10.0,
            stop_price=95.0,
        )

        assert response is not None
        om._adapter.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_stop_loss_invalid_stop_price_returns_none(self):
        """submit_stop_loss() with stop_price=0 should return None."""
        om = _make_order_manager()

        result = await om.submit_stop_loss("AAPL", "sell", 10.0, stop_price=0.0)

        assert result is None
        om._adapter.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_stop_loss_links_to_parent_order(self):
        """Stop order should be linked to parent entry in active_orders."""
        # First submit entry
        entry_result = _make_order_result(order_id="entry-001", status="filled")
        sl_result = _make_order_result(order_id="sl-001", status="accepted")

        adapter = MagicMock()
        call_count = {"n": 0}

        async def submit_in_sequence(order):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return entry_result
            return sl_result

        adapter.submit_order = AsyncMock(side_effect=submit_in_sequence)
        om = OrderManager(adapter=adapter)

        # Submit entry first
        await om.submit_entry("AAPL", "buy", 10.0, "market")
        # Submit SL linked to that entry
        await om.submit_stop_loss("AAPL", "sell", 10.0, stop_price=95.0, parent_order_id="entry-001")

        assert om._active_orders["entry-001"].sl_order_id == "sl-001"

    @pytest.mark.asyncio
    async def test_submit_stop_loss_uses_gtc_time_in_force(self):
        """Stop-loss should use GTC time_in_force for persistence."""
        from autotrader.core.types import Order
        submitted_orders = []
        result = _make_order_result(status="accepted")

        adapter = MagicMock()
        adapter.submit_order = AsyncMock(side_effect=lambda o: (
            submitted_orders.append(o) or result
        ))
        om = OrderManager(adapter=adapter)

        await om.submit_stop_loss("AAPL", "sell", 10.0, stop_price=95.0)

        assert len(submitted_orders) == 1
        assert submitted_orders[0].time_in_force == "gtc"
        assert submitted_orders[0].order_type == "stop"


# ---------------------------------------------------------------------------
# Test class: submit_exit
# ---------------------------------------------------------------------------

class TestSubmitExit:
    """Tests for exit order submission."""

    @pytest.mark.asyncio
    async def test_submit_exit_succeeds(self):
        """submit_exit() should return an OrderResult on success."""
        result = _make_order_result(status="filled")
        om = _make_order_manager(order_result=result)

        response = await om.submit_exit("AAPL", "sell", 10.0)

        assert response is not None
        assert response.status == "filled"

    @pytest.mark.asyncio
    async def test_submit_exit_cancels_pending_sl_first(self):
        """submit_exit() should cancel any pending SL order before exiting."""
        entry_result = _make_order_result(order_id="entry-001", status="filled")
        sl_result = _make_order_result(order_id="sl-001", status="accepted")
        exit_result = _make_order_result(order_id="exit-001", status="filled")

        adapter = MagicMock()
        call_count = {"n": 0}

        async def submit_sequence(order):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return entry_result
            elif call_count["n"] == 2:
                return sl_result
            else:
                return exit_result

        adapter.submit_order = AsyncMock(side_effect=submit_sequence)
        adapter.cancel_order = AsyncMock(return_value=True)
        om = OrderManager(adapter=adapter)

        # Submit entry and SL
        await om.submit_entry("AAPL", "buy", 10.0, "market")
        await om.submit_stop_loss("AAPL", "sell", 10.0, stop_price=95.0, parent_order_id="entry-001")

        # Now exit
        await om.submit_exit("AAPL", "sell", 10.0)

        # cancel_order should have been called to cancel the SL
        adapter.cancel_order.assert_called_once_with("sl-001")

    @pytest.mark.asyncio
    async def test_submit_exit_zero_qty_returns_none(self):
        """submit_exit() with qty=0 should return None."""
        om = _make_order_manager()

        result = await om.submit_exit("AAPL", "sell", 0.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_submit_exit_evicts_from_active_orders(self):
        """submit_exit() should remove the symbol from active_orders tracking."""
        entry_result = _make_order_result(order_id="entry-001", status="filled")
        exit_result = _make_order_result(order_id="exit-001", status="filled")

        adapter = MagicMock()
        call_count = {"n": 0}

        async def submit_sequence(order):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return entry_result
            return exit_result

        adapter.submit_order = AsyncMock(side_effect=submit_sequence)
        adapter.cancel_order = AsyncMock(return_value=True)
        om = OrderManager(adapter=adapter)

        await om.submit_entry("AAPL", "buy", 10.0, "market")
        assert om.active_order_count == 1

        await om.submit_exit("AAPL", "sell", 10.0)
        assert om.active_order_count == 0

    @pytest.mark.asyncio
    async def test_submit_exit_retries_on_failure(self):
        """submit_exit() should retry on exception."""
        call_count = {"n": 0}

        async def flaky_submit(order):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("error")
            return _make_order_result(status="filled")

        adapter = MagicMock()
        adapter.submit_order = AsyncMock(side_effect=flaky_submit)
        adapter.cancel_order = AsyncMock(return_value=True)
        om = OrderManager(adapter=adapter)

        from unittest.mock import patch
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await om.submit_exit("AAPL", "sell", 10.0)

        assert result is not None
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Test class: cancel_order
# ---------------------------------------------------------------------------

class TestCancelOrder:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order_returns_true_on_success(self):
        """cancel_order() should return True when adapter cancels successfully."""
        om = _make_order_manager(cancel_success=True)

        result = await om.cancel_order("ord-001")

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false_on_failure(self):
        """cancel_order() should return False when adapter cancellation fails."""
        om = _make_order_manager(cancel_success=False)

        result = await om.cancel_order("ord-001")

        assert result is False


# ---------------------------------------------------------------------------
# Test class: PnL calculation
# ---------------------------------------------------------------------------

class TestPnlCalculation:
    """Tests for calculate_pnl method."""

    def test_long_pnl_profit(self):
        """Long position profit: (exit - entry) * qty."""
        om = _make_order_manager()
        pnl = om.calculate_pnl(
            entry_price=100.0,
            exit_price=110.0,
            qty=10.0,
            direction="long",
        )
        assert pnl == pytest.approx(100.0)  # (110 - 100) * 10

    def test_long_pnl_loss(self):
        """Long position loss should be negative."""
        om = _make_order_manager()
        pnl = om.calculate_pnl(
            entry_price=100.0,
            exit_price=90.0,
            qty=10.0,
            direction="long",
        )
        assert pnl == pytest.approx(-100.0)  # (90 - 100) * 10

    def test_short_pnl_profit(self):
        """Short position profit: (entry - exit) * qty."""
        om = _make_order_manager()
        pnl = om.calculate_pnl(
            entry_price=100.0,
            exit_price=90.0,
            qty=10.0,
            direction="short",
        )
        assert pnl == pytest.approx(100.0)  # (100 - 90) * 10

    def test_short_pnl_loss(self):
        """Short position that moves against (price rises) should show loss."""
        om = _make_order_manager()
        pnl = om.calculate_pnl(
            entry_price=100.0,
            exit_price=115.0,
            qty=10.0,
            direction="short",
        )
        assert pnl == pytest.approx(-150.0)  # (100 - 115) * 10

    def test_breakeven_pnl_is_zero(self):
        """Entry and exit at same price should produce PnL of 0."""
        om = _make_order_manager()
        pnl = om.calculate_pnl(
            entry_price=100.0,
            exit_price=100.0,
            qty=5.0,
            direction="long",
        )
        assert pnl == pytest.approx(0.0)

    def test_pnl_scales_with_qty(self):
        """PnL should scale linearly with quantity."""
        om = _make_order_manager()
        pnl_1 = om.calculate_pnl(100.0, 110.0, 1.0, "long")
        pnl_100 = om.calculate_pnl(100.0, 110.0, 100.0, "long")
        assert pnl_100 == pytest.approx(pnl_1 * 100)

    def test_active_order_count_property(self):
        """active_order_count should reflect tracked orders."""
        om = _make_order_manager()
        assert om.active_order_count == 0
