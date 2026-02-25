from __future__ import annotations

from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator


class RSI(Indicator):
    def __init__(self, period: int = 14) -> None:
        self.name = "RSI"
        self.warmup_period = period + 1
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.warmup_period:
            return None
        closes = [b.close for b in bars]
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        avg_gain = sum(gains[: self.period]) / self.period
        avg_loss = sum(losses[: self.period]) / self.period

        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
