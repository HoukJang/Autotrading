from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from autotrader.core.types import AccountInfo, Order, OrderResult, Position


class BrokerAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_account(self) -> AccountInfo: ...

    @abstractmethod
    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None: ...
