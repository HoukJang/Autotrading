"""SMA Crossover strategy using dual moving average signals."""
from __future__ import annotations

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


class SmaCrossover(Strategy):
    """Dual SMA crossover strategy.

    Generates long signals on golden cross (fast SMA crosses above slow SMA)
    and close signals on death cross (fast SMA crosses below slow SMA).
    """

    name = "sma_crossover"

    def __init__(self, fast_period: int = 10, slow_period: int = 30) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.required_indicators = [
            IndicatorSpec(name="SMA", params={"period": fast_period}),
            IndicatorSpec(name="SMA", params={"period": slow_period}),
        ]
        self._prev_fast_above: dict[str, bool] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        fast_key = f"SMA_{self.fast_period}"
        slow_key = f"SMA_{self.slow_period}"

        fast_val = ctx.indicators.get(fast_key)
        slow_val = ctx.indicators.get(slow_key)

        if fast_val is None or slow_val is None:
            return None

        fast_above = float(fast_val) > float(slow_val)
        symbol = ctx.symbol

        if symbol not in self._prev_fast_above:
            self._prev_fast_above[symbol] = fast_above
            return None

        prev_above = self._prev_fast_above[symbol]
        self._prev_fast_above[symbol] = fast_above

        if fast_above and not prev_above:
            spread = abs(float(fast_val) - float(slow_val))
            price = float(ctx.bar.close) if ctx.bar.close else 1.0
            strength = min(spread / price, 1.0)
            return Signal(
                strategy=self.name,
                symbol=symbol,
                direction="long",
                strength=strength,
            )

        if not fast_above and prev_above:
            spread = abs(float(fast_val) - float(slow_val))
            price = float(ctx.bar.close) if ctx.bar.close else 1.0
            strength = min(spread / price, 1.0)
            return Signal(
                strategy=self.name,
                symbol=symbol,
                direction="close",
                strength=strength,
            )

        return None
