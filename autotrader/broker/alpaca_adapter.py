from __future__ import annotations

import logging
from typing import Callable

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.live import StockDataStream

from autotrader.broker.base import BrokerAdapter
from autotrader.core.types import AccountInfo, Order, OrderResult, Position

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
        self._client = TradingClient(self._api_key, self._secret_key, paper=self._paper)
        self.connected = True
        logger.info("Connected to Alpaca (paper=%s)", self._paper)

    async def disconnect(self) -> None:
        if self._stream:
            self._stream.stop()
        self._client = None
        self.connected = False
        logger.info("Disconnected from Alpaca")

    async def submit_order(self, order: Order) -> OrderResult:
        assert self._client is not None
        side = _SIDE_MAP[order.side]
        tif = _TIF_MAP.get(order.time_in_force, TimeInForce.DAY)

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

        result = self._client.submit_order(req)
        return OrderResult(
            order_id=str(result.id),
            symbol=result.symbol,
            status=str(result.status),
            filled_qty=float(result.filled_qty or 0),
            filled_price=float(result.filled_avg_price or 0),
        )

    async def cancel_order(self, order_id: str) -> bool:
        assert self._client is not None
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        assert self._client is not None
        raw = self._client.get_all_positions()
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
        assert self._client is not None
        a = self._client.get_account()
        return AccountInfo(
            account_id=str(a.id),
            buying_power=float(a.buying_power),
            portfolio_value=float(a.portfolio_value),
            cash=float(a.cash),
            equity=float(a.equity),
        )

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        self._stream = StockDataStream(self._api_key, self._secret_key)
        self._stream.subscribe_bars(callback, *symbols)
