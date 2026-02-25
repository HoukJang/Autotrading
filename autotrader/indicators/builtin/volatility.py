from __future__ import annotations

import math
from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator


class ATR(Indicator):
    def __init__(self, period: int = 14) -> None:
        self.name = "ATR"
        self.warmup_period = period + 1
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.warmup_period:
            return None
        bar_list = list(bars)
        true_ranges = []
        for i in range(1, len(bar_list)):
            high_low = bar_list[i].high - bar_list[i].low
            high_prev_close = abs(bar_list[i].high - bar_list[i - 1].close)
            low_prev_close = abs(bar_list[i].low - bar_list[i - 1].close)
            true_ranges.append(max(high_low, high_prev_close, low_prev_close))

        atr = sum(true_ranges[: self.period]) / self.period
        for tr in true_ranges[self.period :]:
            atr = (atr * (self.period - 1) + tr) / self.period
        return atr


class BollingerBands(Indicator):
    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.name = "BBANDS"
        self.period = period
        self.num_std = num_std
        self.warmup_period = period

    def calculate(self, bars: deque[Bar]) -> dict | None:
        if len(bars) < self.period:
            return None

        closes = [b.close for b in bars]
        window = closes[-self.period :]

        middle = sum(window) / self.period
        variance = sum((c - middle) ** 2 for c in window) / self.period
        stdev = math.sqrt(variance)

        upper = middle + self.num_std * stdev
        lower = middle - self.num_std * stdev

        if middle == 0:
            width = 0.0
        else:
            width = (upper - lower) / middle

        band_range = upper - lower
        if band_range == 0:
            pct_b = 0.5
        else:
            pct_b = (closes[-1] - lower) / band_range

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "width": width,
            "pct_b": pct_b,
        }
