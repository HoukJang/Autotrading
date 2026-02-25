from __future__ import annotations

from autotrader.strategy.base import Strategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        if strategy.name in self._strategies:
            raise ValueError(f"Strategy already registered: {strategy.name}")
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Strategy | None:
        return self._strategies.get(name)

    def all(self) -> list[Strategy]:
        return list(self._strategies.values())
