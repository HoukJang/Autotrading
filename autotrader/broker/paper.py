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
        self._short_positions: dict[str, _PaperPosition] = {}
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
            # If short exists, cover short first
            short_pos = self._short_positions.get(order.symbol)
            if short_pos:
                cover_qty = min(order.quantity, short_pos.quantity)
                cover_cost = price * cover_qty
                if cover_cost > self._cash:
                    return OrderResult(
                        order_id=order_id, symbol=order.symbol, status="rejected",
                    )
                self._cash -= cover_cost
                short_pos.reduce(cover_qty)
                if short_pos.quantity == 0:
                    del self._short_positions[order.symbol]
                remaining = order.quantity - cover_qty
                if remaining > 0:
                    # Open long with remainder
                    long_cost = price * remaining
                    if long_cost > self._cash:
                        # Already covered short portion, but can't open long
                        return OrderResult(
                            order_id=order_id, symbol=order.symbol, status="filled",
                            filled_qty=cover_qty, filled_price=price,
                        )
                    self._cash -= long_cost
                    pos = self._positions.get(order.symbol)
                    if pos:
                        pos.add(remaining, price)
                    else:
                        self._positions[order.symbol] = _PaperPosition(
                            order.symbol, remaining, price,
                        )
            else:
                # Normal long buy
                if cost > self._cash:
                    return OrderResult(
                        order_id=order_id, symbol=order.symbol, status="rejected",
                    )
                self._cash -= cost
                pos = self._positions.get(order.symbol)
                if pos:
                    pos.add(order.quantity, price)
                else:
                    self._positions[order.symbol] = _PaperPosition(
                        order.symbol, order.quantity, price,
                    )

        else:  # sell
            long_pos = self._positions.get(order.symbol)
            if long_pos and long_pos.quantity >= order.quantity:
                # Close/reduce long
                self._cash += cost
                long_pos.reduce(order.quantity)
                if long_pos.quantity == 0:
                    del self._positions[order.symbol]
            elif long_pos:
                # Close all long, do NOT short the excess
                close_qty = long_pos.quantity
                self._cash += price * close_qty
                del self._positions[order.symbol]
                return OrderResult(
                    order_id=order_id, symbol=order.symbol, status="filled",
                    filled_qty=close_qty, filled_price=price,
                )
            else:
                # No long position -> open short
                self._cash += cost  # short proceeds
                short_pos = self._short_positions.get(order.symbol)
                if short_pos:
                    short_pos.add(order.quantity, price)
                else:
                    self._short_positions[order.symbol] = _PaperPosition(
                        order.symbol, order.quantity, price,
                    )

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
        for sym, pos in self._short_positions.items():
            price = self._prices.get(sym, pos.avg_price)
            mv = price * pos.quantity
            pnl = (pos.avg_price - price) * pos.quantity  # Short PnL is inverted
            result.append(Position(
                symbol=sym, quantity=pos.quantity, avg_entry_price=pos.avg_price,
                market_value=mv, unrealized_pnl=pnl, side="short",
            ))
        return result

    async def get_account(self) -> AccountInfo:
        long_value = sum(
            self._prices.get(s, p.avg_price) * p.quantity
            for s, p in self._positions.items()
        )
        short_liability = sum(
            self._prices.get(s, p.avg_price) * p.quantity
            for s, p in self._short_positions.items()
        )
        equity = self._cash + long_value - short_liability
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
