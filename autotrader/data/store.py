from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from autotrader.core.types import Bar


class DataStore(ABC):
    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def save_bars(self, bars: list[Bar]) -> None: ...

    @abstractmethod
    async def load_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]: ...
