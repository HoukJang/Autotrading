"""Trade detail collection for backtest analysis.

Captures per-trade metadata (strategy, sub-strategy, entry/exit info)
during backtest execution for downstream dashboard consumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TradeDetail:
    trade_id: int
    symbol: str
    strategy: str
    sub_strategy: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    bars_held: int
    exit_reason: str
    entry_indicators: dict = field(default_factory=dict)


@dataclass
class _PendingTrade:
    symbol: str
    strategy: str
    sub_strategy: str
    direction: str
    entry_time: datetime
    entry_price: float
    quantity: float
    entry_indicators: dict = field(default_factory=dict)


class TradeCollector:
    def __init__(self) -> None:
        self._pending: dict[str, _PendingTrade] = {}
        self._trades: list[TradeDetail] = []
        self._next_id: int = 1

    def on_entry(self, signal, bar, quantity: float) -> None:
        meta = signal.metadata or {}
        self._pending[signal.symbol] = _PendingTrade(
            symbol=signal.symbol,
            strategy=signal.strategy,
            sub_strategy=meta.get("sub_strategy", "unknown"),
            direction=signal.direction,
            entry_time=bar.timestamp,
            entry_price=bar.close,
            quantity=quantity,
            entry_indicators={
                k: v for k, v in meta.items()
                if k not in ("sub_strategy", "exit_reason", "bars_held", "entry_price", "exit_price", "pnl_pct")
            },
        )

    def on_exit(self, signal, bar, pnl: float) -> TradeDetail | None:
        pending = self._pending.pop(signal.symbol, None)
        if pending is None:
            return None

        meta = signal.metadata or {}
        entry_price = pending.entry_price
        exit_price = bar.close
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0

        detail = TradeDetail(
            trade_id=self._next_id,
            symbol=pending.symbol,
            strategy=pending.strategy,
            sub_strategy=pending.sub_strategy,
            direction=pending.direction,
            entry_time=pending.entry_time,
            exit_time=bar.timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=pending.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            bars_held=meta.get("bars_held", 0),
            exit_reason=meta.get("exit_reason", "unknown"),
            entry_indicators=pending.entry_indicators,
        )
        self._next_id += 1
        self._trades.append(detail)
        return detail

    @property
    def trades(self) -> list[TradeDetail]:
        return list(self._trades)
