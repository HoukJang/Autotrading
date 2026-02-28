"""OrderManager: concrete order lifecycle management wrapping AlpacaAdapter.

Responsible for:
- Submitting market and limit entry orders
- Submitting stop-loss orders as Alpaca-side safety nets
- Polling for fill prices with retries
- Cancelling stale/pending orders
- Calculating realised PnL on position close
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from autotrader.broker.alpaca_adapter import AlpacaAdapter
from autotrader.core.types import Order, OrderResult

logger = logging.getLogger("autotrader.execution.order_manager")

# Maximum number of submission retries on transient failures.
_MAX_RETRIES: int = 3
# Seconds to wait between retry attempts.
_RETRY_DELAY: float = 1.0


@dataclass
class ActiveOrder:
    """Tracks an order that has been submitted but not yet fully resolved."""

    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: str
    submitted_qty: float
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fill_price: float = 0.0
    filled_qty: float = 0.0
    status: str = "pending"
    sl_order_id: str | None = None


class OrderManager:
    """Manages the full order lifecycle via AlpacaAdapter.

    This class provides a higher-level interface above the raw AlpacaAdapter
    for the execution engine.  It handles:
    - Entry order submission (market / limit)
    - Stop-loss order submission after fill confirmation
    - Order cancellation
    - PnL computation at close
    - Retry logic on transient errors

    Args:
        adapter: Initialised and connected AlpacaAdapter instance.
    """

    def __init__(self, adapter: AlpacaAdapter) -> None:
        self._adapter = adapter
        # Keyed by Alpaca order_id -> ActiveOrder
        self._active_orders: dict[str, ActiveOrder] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def submit_entry(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        order_type: Literal["market", "limit"] = "market",
        limit_price: float | None = None,
        time_in_force: Literal["day", "gtc", "ioc"] = "day",
    ) -> OrderResult | None:
        """Submit an entry order with retry logic.

        Args:
            symbol: Ticker symbol to trade.
            side: "buy" for long entries, "sell" for short entries.
            qty: Number of shares.
            order_type: "market" or "limit".
            limit_price: Required when order_type is "limit".
            time_in_force: Order validity period.

        Returns:
            OrderResult if submission succeeded and order reached a terminal
            state, or None if all retries were exhausted.
        """
        if qty <= 0:
            logger.warning("submit_entry: qty must be positive, got %s for %s", qty, symbol)
            return None

        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
        )

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = await self._adapter.submit_order(order)
                if result.status in ("filled", "accepted", "partially_filled"):
                    active = ActiveOrder(
                        order_id=result.order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        submitted_qty=qty,
                        fill_price=result.filled_price,
                        filled_qty=result.filled_qty,
                        status=result.status,
                    )
                    self._active_orders[result.order_id] = active
                    logger.info(
                        "Entry submitted: %s %s %s %.0f @ %.2f (attempt %d)",
                        side, symbol, order_type, result.filled_qty,
                        result.filled_price, attempt,
                    )
                    return result
                else:
                    logger.warning(
                        "Entry order %s status: %s (attempt %d)",
                        result.order_id, result.status, attempt,
                    )
                    return result
            except Exception:
                logger.exception(
                    "Entry order submission failed for %s (attempt %d/%d)",
                    symbol, attempt, _MAX_RETRIES,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY * attempt)

        logger.error("All %d entry retries exhausted for %s", _MAX_RETRIES, symbol)
        return None

    async def submit_stop_loss(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        stop_price: float,
        parent_order_id: str | None = None,
    ) -> OrderResult | None:
        """Submit a stop-loss order as a broker-side safety net.

        Stop orders are submitted with GTC (good-til-canceled) so they persist
        through market sessions until triggered or manually cancelled.

        Args:
            symbol: Ticker symbol.
            side: "sell" for long SL, "buy" for short SL.
            qty: Number of shares to close on stop trigger.
            stop_price: Stop trigger price.
            parent_order_id: Alpaca order_id of the entry fill for tracking.

        Returns:
            OrderResult from the stop order submission, or None on failure.
        """
        if stop_price <= 0 or qty <= 0:
            logger.warning(
                "Invalid stop_loss params for %s: stop=%.2f, qty=%.0f",
                symbol, stop_price, qty,
            )
            return None

        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type="stop",
            stop_price=stop_price,
            time_in_force="gtc",
        )

        try:
            result = await self._adapter.submit_order(order)
            logger.info(
                "Stop-loss submitted: %s %s %.0f @ stop=%.2f (status=%s)",
                side, symbol, qty, stop_price, result.status,
            )
            # Link stop order to its parent entry
            if parent_order_id and parent_order_id in self._active_orders:
                self._active_orders[parent_order_id].sl_order_id = result.order_id
            return result
        except Exception:
            logger.exception("Stop-loss submission failed for %s @ %.2f", symbol, stop_price)
            return None

    async def submit_exit(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        order_type: Literal["market", "limit"] = "market",
        limit_price: float | None = None,
    ) -> OrderResult | None:
        """Submit a closing order for an existing position.

        If a pending stop-loss order exists for this symbol, it is cancelled
        before submitting the exit to avoid double-close.

        Args:
            symbol: Ticker to close.
            side: "sell" to close long, "buy" to close short.
            qty: Number of shares to close.
            order_type: "market" or "limit".
            limit_price: Required for limit exits.

        Returns:
            OrderResult or None on failure.
        """
        if qty <= 0:
            logger.warning("submit_exit: qty must be positive, got %s for %s", qty, symbol)
            return None

        # Cancel any outstanding stop-loss for this symbol before exiting
        await self._cancel_sl_for_symbol(symbol)

        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force="day",
        )

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = await self._adapter.submit_order(order)
                logger.info(
                    "Exit submitted: %s %s %.0f @ %.2f (status=%s, attempt %d)",
                    side, symbol, result.filled_qty, result.filled_price,
                    result.status, attempt,
                )
                # Remove from active orders tracking
                self._evict_symbol(symbol)
                return result
            except Exception:
                logger.exception(
                    "Exit order submission failed for %s (attempt %d/%d)",
                    symbol, attempt, _MAX_RETRIES,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY * attempt)

        logger.error("All %d exit retries exhausted for %s", _MAX_RETRIES, symbol)
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by its Alpaca order_id.

        Args:
            order_id: Alpaca-assigned order ID.

        Returns:
            True if the cancel request was acknowledged, False otherwise.
        """
        success = await self._adapter.cancel_order(order_id)
        if success:
            if order_id in self._active_orders:
                self._active_orders[order_id].status = "cancelled"
            logger.info("Order %s cancelled", order_id)
        else:
            logger.warning("Failed to cancel order %s", order_id)
        return success

    def calculate_pnl(
        self,
        entry_price: float,
        exit_price: float,
        qty: float,
        direction: Literal["long", "short"],
    ) -> float:
        """Calculate realised PnL for a closed position.

        Args:
            entry_price: Average fill price at entry.
            exit_price: Average fill price at exit.
            qty: Number of shares traded.
            direction: "long" or "short".

        Returns:
            Signed PnL in dollars.
        """
        if direction == "long":
            return (exit_price - entry_price) * qty
        else:  # short
            return (entry_price - exit_price) * qty

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _cancel_sl_for_symbol(self, symbol: str) -> None:
        """Cancel any live stop-loss order tracked for this symbol."""
        for active in list(self._active_orders.values()):
            if active.symbol == symbol and active.sl_order_id:
                await self.cancel_order(active.sl_order_id)
                active.sl_order_id = None

    def _evict_symbol(self, symbol: str) -> None:
        """Remove all active order entries for a symbol after exit."""
        to_remove = [oid for oid, o in self._active_orders.items() if o.symbol == symbol]
        for oid in to_remove:
            del self._active_orders[oid]

    @property
    def active_order_count(self) -> int:
        """Number of currently tracked active orders."""
        return len(self._active_orders)
