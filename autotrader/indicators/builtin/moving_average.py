from __future__ import annotations

from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator


class SMA(Indicator):
    def __init__(self, period: int) -> None:
        self.name = "SMA"
        self.warmup_period = period
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.period:
            return None
        closes = [b.close for b in list(bars)[-self.period :]]
        return sum(closes) / self.period


class EMA(Indicator):
    def __init__(self, period: int) -> None:
        self.name = "EMA"
        self.warmup_period = period
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.period:
            return None
        closes = [b.close for b in bars]
        multiplier = 2 / (self.period + 1)
        ema = sum(closes[: self.period]) / self.period
        for close in closes[self.period :]:
            ema = (close - ema) * multiplier + ema
        return ema
