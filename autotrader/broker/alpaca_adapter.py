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
from autotrader.core.types import AccountInfo, Bar, Order, OrderResult, Position

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

        result: Any = self._client.submit_order(req)
        return OrderResult(
            order_id=str(result.id),
            symbol=str(result.symbol),
            status=str(result.status),  # type: ignore[arg-type]
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
        raw: Any = self._client.get_all_positions()
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
        a: Any = self._client.get_account()
        return AccountInfo(
            account_id=str(a.id),
            buying_power=float(a.buying_power),
            portfolio_value=float(a.portfolio_value),
            cash=float(a.cash),
            equity=float(a.equity),
        )

    def _convert_bar(self, alpaca_bar: Any) -> Bar:
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
        )

    async def get_historical_bars(
        self, symbols: list[str], days: int = 120,
    ) -> dict[str, list[Bar]]:
        end_date = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        start_date = end_date - timedelta(days=days)
        client = StockHistoricalDataClient(self._api_key, self._secret_key)

        result: dict[str, list[Bar]] = {}
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start_date,
                    end=end_date,
                )
                raw = client.get_stock_bars(request)
                for sym in batch:
                    try:
                        alpaca_bars = raw[sym]
                    except (KeyError, IndexError):
                        continue
                    if not alpaca_bars:
                        continue
                    result[sym] = [self._convert_bar(ab) for ab in alpaca_bars]
            except Exception:
                logger.exception("Historical bars batch fetch failed")
        return result

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        feed_enum = DataFeed.IEX if self._feed == "iex" else DataFeed.SIP
        self._stream = StockDataStream(self._api_key, self._secret_key, feed=feed_enum)
        self._loop = asyncio.get_running_loop()

        async def _bridge(alpaca_bar: Any) -> None:
            bar = self._convert_bar(alpaca_bar)
            asyncio.run_coroutine_threadsafe(callback(bar), self._loop)

        self._stream.subscribe_bars(_bridge, *symbols)

    def run_stream(self) -> None:
        assert self._stream is not None
        self._stream.run()
