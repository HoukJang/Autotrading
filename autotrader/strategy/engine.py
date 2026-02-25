from __future__ import annotations

import logging

from autotrader.core.types import MarketContext, Signal
from autotrader.strategy.base import Strategy

logger = logging.getLogger(__name__)


class StrategyEngine:
    def __init__(self) -> None:
        self._strategies: list[Strategy] = []

    def add_strategy(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)

    async def process(self, ctx: MarketContext) -> list[Signal]:
        signals = []
        for strat in self._strategies:
            try:
                sig = strat.on_context(ctx)
                if sig is not None:
                    signals.append(sig)
            except Exception:
                logger.exception("Strategy %s failed", strat.name)
        return signals
