from __future__ import annotations

from abc import ABC, abstractmethod

from autotrader.core.types import MarketContext, Signal, OrderResult, Position, Timeframe
from autotrader.indicators.base import IndicatorSpec


class Strategy(ABC):
    name: str
    required_indicators: list[IndicatorSpec] = []
    timeframe: Timeframe = Timeframe.DAILY

    @abstractmethod
    def on_context(self, ctx: MarketContext) -> Signal | None: ...

    def on_order_filled(self, fill: OrderResult) -> None:
        pass

    def on_position_update(self, pos: Position) -> None:
        pass
