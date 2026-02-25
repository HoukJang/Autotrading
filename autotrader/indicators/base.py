from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any

from autotrader.core.types import Bar


class Indicator(ABC):
    name: str
    warmup_period: int

    @abstractmethod
    def calculate(self, bars: deque[Bar]) -> float | dict | None: ...

    def reset(self) -> None:
        pass


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    params: dict[str, Any]

    @property
    def key(self) -> str:
        main_param = next(iter(self.params.values()), "")
        return f"{self.name}_{main_param}"
