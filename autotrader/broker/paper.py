from __future__ import annotations

import uuid
from typing import Callable

from autotrader.broker.base import BrokerAdapter
from autotrader.core.types import AccountInfo, Order, OrderResult, Position


class PaperBroker(BrokerAdapter):
    def __init__(self, initial_balance: float = 100_000.0) -> None:
        self._initial_balance = initial_balance
        self._cash = initial_balance
        self._positions: dict[str, _PaperPosition] = {}
        self._pending_orders: dict[str, Order] = {}
        self._prices: dict[str, float] = {}
        self.connected = False

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def submit_order(self, order: Order) -> OrderResult:
        order_id = str(uuid.uuid4())

        if order.order_type == "market":
            return self._execute_market(order_id, order)

        # Limit/stop orders go to pending
        self._pending_orders[order_id] = order
        return OrderResult(
            order_id=order_id, symbol=order.symbol, status="accepted",
        )

    def _execute_market(self, order_id: str, order: Order) -> OrderResult:
        price = self._prices.get(order.symbol, 0.0)
        cost = price * order.quantity

        if order.side == "buy":
            if cost > self._cash:
                return OrderResult(order_id=order_id, symbol=order.symbol, status="rejected")
            self._cash -= cost
            pos = self._positions.get(order.symbol)
            if pos:
                pos.add(order.quantity, price)
            else:
                self._positions[order.symbol] = _PaperPosition(order.symbol, order.quantity, price)
        else:  # sell
            pos = self._positions.get(order.symbol)
            if not pos or pos.quantity < order.quantity:
                return OrderResult(order_id=order_id, symbol=order.symbol, status="rejected")
            self._cash += cost
            pos.reduce(order.quantity)
            if pos.quantity == 0:
                del self._positions[order.symbol]

        return OrderResult(
            order_id=order_id, symbol=order.symbol, status="filled",
            filled_qty=order.quantity, filled_price=price,
        )

    async def cancel_order(self, order_id: str) -> bool:
        return self._pending_orders.pop(order_id, None) is not None

    async def get_positions(self) -> list[Position]:
        result = []
        for sym, pos in self._positions.items():
            price = self._prices.get(sym, pos.avg_price)
            mv = price * pos.quantity
            pnl = (price - pos.avg_price) * pos.quantity
            result.append(Position(
                symbol=sym, quantity=pos.quantity, avg_entry_price=pos.avg_price,
                market_value=mv, unrealized_pnl=pnl, side="long",
            ))
        return result

    async def get_account(self) -> AccountInfo:
        equity = self._cash + sum(
            self._prices.get(s, p.avg_price) * p.quantity
            for s, p in self._positions.items()
        )
        return AccountInfo(
            account_id="paper", buying_power=self._cash,
            portfolio_value=equity, cash=self._cash, equity=equity,
        )

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        pass  # Paper broker does not produce bars


class _PaperPosition:
    def __init__(self, symbol: str, quantity: float, avg_price: float) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price

    def add(self, qty: float, price: float) -> None:
        total_cost = self.avg_price * self.quantity + price * qty
        self.quantity += qty
        self.avg_price = total_cost / self.quantity

    def reduce(self, qty: float) -> None:
        self.quantity -= qty
