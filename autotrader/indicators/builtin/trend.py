from __future__ import annotations

from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator


class ADX(Indicator):
    def __init__(self, period: int = 14) -> None:
        self.name = "ADX"
        self.period = period
        self.warmup_period = 2 * period + 1

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.warmup_period:
            return None

        bar_list = list(bars)
        period = self.period

        # Step 1: Calculate +DM, -DM, TR for each bar pair
        plus_dm: list[float] = []
        minus_dm: list[float] = []
        true_ranges: list[float] = []

        for i in range(1, len(bar_list)):
            high_diff = bar_list[i].high - bar_list[i - 1].high
            low_diff = bar_list[i - 1].low - bar_list[i].low

            if high_diff > low_diff and high_diff > 0:
                plus_dm.append(high_diff)
            else:
                plus_dm.append(0.0)

            if low_diff > high_diff and low_diff > 0:
                minus_dm.append(low_diff)
            else:
                minus_dm.append(0.0)

            high_low = bar_list[i].high - bar_list[i].low
            high_prev_close = abs(bar_list[i].high - bar_list[i - 1].close)
            low_prev_close = abs(bar_list[i].low - bar_list[i - 1].close)
            true_ranges.append(max(high_low, high_prev_close, low_prev_close))

        # Step 2: Wilder smoothing for +DM, -DM, TR
        smoothed_plus_dm = sum(plus_dm[:period])
        smoothed_minus_dm = sum(minus_dm[:period])
        smoothed_tr = sum(true_ranges[:period])

        # Step 3: Calculate DX values
        dx_values: list[float] = []

        # First DI/DX from initial sums
        if smoothed_tr == 0:
            plus_di = 0.0
            minus_di = 0.0
        else:
            plus_di = 100.0 * smoothed_plus_dm / smoothed_tr
            minus_di = 100.0 * smoothed_minus_dm / smoothed_tr

        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_values.append(0.0)
        else:
            dx_values.append(100.0 * abs(plus_di - minus_di) / di_sum)

        # Continue Wilder smoothing and compute subsequent DX values
        for i in range(period, len(plus_dm)):
            smoothed_plus_dm = smoothed_plus_dm - smoothed_plus_dm / period + plus_dm[i]
            smoothed_minus_dm = smoothed_minus_dm - smoothed_minus_dm / period + minus_dm[i]
            smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[i]

            if smoothed_tr == 0:
                plus_di = 0.0
                minus_di = 0.0
            else:
                plus_di = 100.0 * smoothed_plus_dm / smoothed_tr
                minus_di = 100.0 * smoothed_minus_dm / smoothed_tr

            di_sum = plus_di + minus_di
            if di_sum == 0:
                dx_values.append(0.0)
            else:
                dx_values.append(100.0 * abs(plus_di - minus_di) / di_sum)

        # Step 4: First ADX = average of first period DX values, then Wilder smooth
        if len(dx_values) < period:
            return None

        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period

        return adx
