from __future__ import annotations

from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator, IndicatorSpec
from autotrader.indicators.builtin.moving_average import SMA, EMA
from autotrader.indicators.builtin.momentum import RSI
from autotrader.indicators.builtin.volatility import ATR

_INDICATOR_REGISTRY: dict[str, type[Indicator]] = {
    "SMA": SMA,
    "EMA": EMA,
    "RSI": RSI,
    "ATR": ATR,
}


class IndicatorEngine:
    def __init__(self) -> None:
        self._indicators: dict[str, Indicator] = {}

    def register(self, spec: IndicatorSpec) -> None:
        cls = _INDICATOR_REGISTRY.get(spec.name)
        if cls is None:
            raise ValueError(f"Unknown indicator: {spec.name}")
        self._indicators[spec.key] = cls(**spec.params)

    def compute(self, bars: deque[Bar]) -> dict[str, float | dict | None]:
        return {key: ind.calculate(bars) for key, ind in self._indicators.items()}

    @property
    def max_warmup(self) -> int:
        if not self._indicators:
            return 0
        return max(ind.warmup_period for ind in self._indicators.values())
