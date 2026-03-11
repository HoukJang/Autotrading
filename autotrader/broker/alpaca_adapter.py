from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Union

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from autotrader.broker.base import BrokerAdapter
from autotrader.core.exceptions import BrokerError
from autotrader.core.exceptions import ConnectionError as BrokerConnectionError
from autotrader.core.types import AccountInfo, Bar, Order, OrderResult, Position, Timeframe

logger = logging.getLogger(__name__)

_SIDE_MAP = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
_TIF_MAP = {"day": TimeInForce.DAY, "gtc": TimeInForce.GTC, "ioc": TimeInForce.IOC}


class AlpacaAdapter(BrokerAdapter):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True, feed: str = "iex") -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._feed = feed
        self._client: TradingClient | None = None
        self._stream: StockDataStream | None = None
        self.connected = False

    async def connect(self) -> None:
        try:
            self._client = TradingClient(self._api_key, self._secret_key, paper=self._paper)
            self.connected = True
            logger.info("Connected to Alpaca (paper=%s)", self._paper)
        except Exception as exc:
            raise BrokerConnectionError("Alpaca", str(exc)) from exc

    async def disconnect(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream = None
        self._client = None
        self.connected = False
        logger.info("Disconnected from Alpaca")

    async def submit_order(self, order: Order) -> OrderResult:
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        side = _SIDE_MAP[order.side]
        tif = _TIF_MAP.get(order.time_in_force, TimeInForce.DAY)

        req: Union[MarketOrderRequest, LimitOrderRequest, StopOrderRequest]
        if order.order_type == "market":
            req = MarketOrderRequest(symbol=order.symbol, qty=order.quantity, side=side, time_in_force=tif)
        elif order.order_type == "limit":
            req = LimitOrderRequest(
                symbol=order.symbol, qty=order.quantity, side=side,
                time_in_force=tif, limit_price=order.limit_price,
            )
        elif order.order_type == "stop":
            req = StopOrderRequest(
                symbol=order.symbol, qty=order.quantity, side=side,
                time_in_force=tif, stop_price=order.stop_price,
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

        try:
            result: Any = self._client.submit_order(req)
        except Exception as exc:
            raise BrokerError(f"Failed to submit order for {order.symbol}: {exc}") from exc
        result = await self._wait_for_fill(result, order.order_type)
        return OrderResult(
            order_id=str(result.id),
            symbol=str(result.symbol),
            status=result.status.value,  # type: ignore[arg-type]
            filled_qty=float(result.filled_qty or 0),
            filled_price=float(result.filled_avg_price or 0),
        )

    async def _wait_for_fill(
        self, order_response: Any, order_type: str,
        max_wait: float = 30.0, poll_interval: float = 0.5,
    ) -> Any:
        """Poll Alpaca until the order reaches a terminal state."""
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        terminal = {"filled", "cancelled", "canceled", "expired", "rejected"}
        status = str(order_response.status).lower().replace("orderstatus.", "")
        if status in terminal:
            return order_response

        # Market orders fill fast; limit/stop may take longer.
        # Use 30s for market orders to handle MOO congestion at market open.
        deadline = max_wait if order_type != "market" else 30.0
        elapsed = 0.0
        order_id = str(order_response.id)
        while elapsed < deadline:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                updated = self._client.get_order_by_id(order_id)
            except Exception:
                logger.warning("Failed to poll order %s", order_id)
                continue
            status = str(updated.status).lower().replace("orderstatus.", "")
            if status in terminal:
                logger.info("Order %s reached terminal status: %s (%.1fs)", order_id, status, elapsed)
                return updated

        logger.warning("Order %s still pending after %.1fs (status=%s)", order_id, elapsed, status)
        return self._client.get_order_by_id(order_id)

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count of cancelled orders."""
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        try:
            statuses = self._client.cancel_orders()
            cancelled = len(statuses) if statuses else 0
            return cancelled
        except Exception as exc:
            raise BrokerError(f"Failed to cancel all orders: {exc}") from exc

    async def cancel_order(self, order_id: str) -> bool:
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            return False

    async def get_order_status(self, order_id: str) -> OrderResult | None:
        """Re-fetch current order state from Alpaca by order_id."""
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        try:
            raw = self._client.get_order_by_id(order_id)
            return OrderResult(
                order_id=str(raw.id),
                symbol=str(raw.symbol),
                status=raw.status.value,  # type: ignore[arg-type]
                filled_qty=float(raw.filled_qty or 0),
                filled_price=float(raw.filled_avg_price or 0),
            )
        except Exception:
            logger.exception("Failed to get order status for %s", order_id)
            return None

    async def get_positions(self) -> list[Position]:
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        try:
            raw: Any = self._client.get_all_positions()
        except Exception as exc:
            raise BrokerError(f"Failed to get positions: {exc}") from exc
        return [
            Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pnl=float(p.unrealized_pl),
                side="long" if float(p.qty) > 0 else "short",
            )
            for p in raw
        ]

    async def get_account(self) -> AccountInfo:
        if self._client is None:
            raise BrokerError("AlpacaAdapter not connected. Call connect() first.")
        try:
            a: Any = self._client.get_account()
        except Exception as exc:
            raise BrokerError(f"Failed to get account info: {exc}") from exc
        return AccountInfo(
            account_id=str(a.id),
            buying_power=float(a.buying_power),
            portfolio_value=float(a.portfolio_value),
            cash=float(a.cash),
            equity=float(a.equity),
        )

    def _convert_bar(self, alpaca_bar: Any, timeframe: Timeframe = Timeframe.DAILY) -> Bar:
        ts = alpaca_bar.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return Bar(
            symbol=str(alpaca_bar.symbol),
            timestamp=ts,
            open=float(alpaca_bar.open),
            high=float(alpaca_bar.high),
            low=float(alpaca_bar.low),
            close=float(alpaca_bar.close),
            volume=float(alpaca_bar.volume),
            timeframe=timeframe,
        )

    async def get_historical_bars(
        self, symbols: list[str], days: int = 120,
    ) -> dict[str, list[Bar]]:
        end_date = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        start_date = end_date - timedelta(days=days)
        client = StockHistoricalDataClient(self._api_key, self._secret_key)

        # Alpaca uses '.' for share class indicators (e.g., BRK.B not BRK-B)
        # Build mapping to convert keys back to caller's original format
        original_to_converted = {s: s.replace("-", ".") for s in symbols}
        converted_to_original = {v: k for k, v in original_to_converted.items()}
        api_symbols = list(original_to_converted.values())

        result: dict[str, list[Bar]] = {}
        batch_size = 50
        for i in range(0, len(api_symbols), batch_size):
            batch = api_symbols[i : i + batch_size]
            try:
                feed_enum = DataFeed.IEX if self._feed == "iex" else DataFeed.SIP
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start_date,
                    end=end_date,
                    feed=feed_enum,
                )
                raw = client.get_stock_bars(request)
                for sym in batch:
                    try:
                        alpaca_bars = raw[sym]
                    except (KeyError, IndexError):
                        continue
                    if not alpaca_bars:
                        continue
                    original_sym = converted_to_original.get(sym, sym)
                    result[original_sym] = [self._convert_bar(ab, timeframe=Timeframe.DAILY) for ab in alpaca_bars]
            except Exception:
                logger.exception("Historical bars batch fetch failed")
        return result

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        # Clean up existing stream to prevent orphan WebSocket connections
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        feed_enum = DataFeed.IEX if self._feed == "iex" else DataFeed.SIP
        self._stream = StockDataStream(self._api_key, self._secret_key, feed=feed_enum)
        self._loop = asyncio.get_running_loop()

        async def _bridge(alpaca_bar: Any) -> None:
            try:
                bar = self._convert_bar(alpaca_bar, timeframe=Timeframe.MINUTE)
                await callback(bar)
            except Exception:
                logger.exception(
                    "Bar callback failed for %s",
                    getattr(alpaca_bar, "symbol", "unknown"),
                )

        self._stream.subscribe_bars(_bridge, *symbols)

    async def add_bar_subscription(self, symbols: list[str], callback: Callable) -> None:
        if not self._stream:
            logger.warning("Cannot add subscription: stream not initialized")
            return
        if not symbols:
            return

        async def _bridge(alpaca_bar: Any) -> None:
            try:
                bar = self._convert_bar(alpaca_bar, timeframe=Timeframe.MINUTE)
                await callback(bar)
            except Exception:
                logger.exception(
                    "Bar callback failed for %s",
                    getattr(alpaca_bar, "symbol", "unknown"),
                )

        self._stream.subscribe_bars(_bridge, *symbols)
        logger.info("Added bar subscription for %d symbols: %s", len(symbols), symbols)

    async def remove_bar_subscription(self, symbols: list[str]) -> None:
        if not self._stream:
            logger.warning("Cannot remove subscription: stream not initialized")
            return
        if not symbols:
            return
        self._stream.unsubscribe_bars(*symbols)
        logger.info("Removed bar subscription for %d symbols: %s", len(symbols), symbols)

    def run_stream(self) -> None:
        if self._stream is None:
            raise RuntimeError("AlpacaAdapter stream not initialized. Call connect() first.")
        self._stream.run()
