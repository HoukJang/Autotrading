from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    symbol: str
    side: str
    qty: float
    price: float
    pnl: float


class PortfolioTracker:
    def __init__(self, initial_equity: float) -> None:
        self.initial_equity = initial_equity
        self.trades: list[TradeRecord] = []
        self.equity_curve: list[float] = [initial_equity]
        self.total_pnl: float = 0.0

    def record_trade(self, symbol: str, side: str, qty: float, price: float, pnl: float) -> None:
        self.trades.append(TradeRecord(symbol=symbol, side=side, qty=qty, price=price, pnl=pnl))
        self.total_pnl += pnl

    def update_equity(self, equity: float) -> None:
        self.equity_curve.append(equity)
