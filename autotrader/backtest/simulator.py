from __future__ import annotations

from autotrader.core.types import Order, OrderResult, Signal
from autotrader.risk.position_sizer import PositionSizer
from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo

import uuid


class BacktestSimulator:
    def __init__(self, initial_balance: float, risk_config: RiskConfig) -> None:
        self._cash = initial_balance
        self._positions: dict[str, _SimPosition] = {}
        self._sizer = PositionSizer(risk_config)

    def execute_signal(self, signal: Signal, price: float) -> OrderResult | None:
        account = self._get_account()

        if signal.direction == "long":
            qty = self._sizer.calculate(price, account)
            if qty <= 0:
                return None
            cost = qty * price
            if cost > self._cash:
                return None
            self._cash -= cost
            self._positions[signal.symbol] = _SimPosition(signal.symbol, qty, price)
            return OrderResult(str(uuid.uuid4()), signal.symbol, "filled", qty, price)

        elif signal.direction == "close":
            pos = self._positions.pop(signal.symbol, None)
            if pos is None:
                return None
            proceeds = pos.quantity * price
            self._cash += proceeds
            return OrderResult(str(uuid.uuid4()), signal.symbol, "filled", pos.quantity, price)

        return None

    def get_pnl(self, symbol: str, current_price: float) -> float:
        pos = self._positions.get(symbol)
        if not pos:
            return 0.0
        return (current_price - pos.avg_price) * pos.quantity

    def _get_account(self) -> AccountInfo:
        equity = self._cash + sum(p.quantity * p.avg_price for p in self._positions.values())
        return AccountInfo("backtest", self._cash, equity, self._cash, equity)

    @property
    def equity(self) -> float:
        return self._cash + sum(p.quantity * p.avg_price for p in self._positions.values())

    def get_equity_with_prices(self, prices: dict[str, float]) -> float:
        market_value = sum(
            p.quantity * prices.get(p.symbol, p.avg_price)
            for p in self._positions.values()
        )
        return self._cash + market_value

    @property
    def has_positions(self) -> bool:
        return len(self._positions) > 0


class _SimPosition:
    def __init__(self, symbol: str, quantity: float, avg_price: float) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
