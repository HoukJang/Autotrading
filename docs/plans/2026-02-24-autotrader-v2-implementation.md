# AutoTrader v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete autotrading system for US equities via Alpaca API with plugin-based strategies and hybrid indicator system.

**Architecture:** Monolithic event-driven Python application. Async EventBus decouples modules. BrokerAdapter ABC enables broker swapping. Hybrid IndicatorEngine computes shared indicators; strategies add custom logic. Same code runs live and backtest by swapping broker.

**Tech Stack:** Python 3.11+, alpaca-py, asyncio, aiosqlite, pydantic v2, pyyaml, python-dotenv, pytest, pytest-asyncio

---

## Task 1: Project Scaffolding

**Files:**
- Create: `autotrader/__init__.py`
- Create: `autotrader/core/__init__.py`
- Create: `autotrader/broker/__init__.py`
- Create: `autotrader/data/__init__.py`
- Create: `autotrader/indicators/__init__.py`
- Create: `autotrader/indicators/builtin/__init__.py`
- Create: `autotrader/strategy/__init__.py`
- Create: `autotrader/risk/__init__.py`
- Create: `autotrader/portfolio/__init__.py`
- Create: `autotrader/backtest/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `pyproject.toml`
- Create: `config/default.yaml`
- Create: `config/.env.example`
- Create: `.gitignore`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "autotrader"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "alpaca-py>=0.33.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
    "aiosqlite>=0.19.0",
    "numpy>=1.24.0",
    "pandas>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests",
    "integration: Integration tests (require external services)",
]

[tool.ruff]
target-version = "py311"
line-length = 100
```

**Step 2: Create config/default.yaml**

```yaml
system:
  name: "AutoTrader v2"
  log_level: "INFO"
  log_dir: "logs"

broker:
  type: "paper"  # paper | alpaca
  paper_balance: 100000.0

alpaca:
  feed: "iex"  # iex (free) | sip (paid)
  paper: true

data:
  bar_history_size: 500
  store_type: "sqlite"  # sqlite | postgres
  sqlite_path: "data/autotrader.db"

risk:
  max_position_pct: 0.10       # 10% of account per symbol
  daily_loss_limit_pct: 0.02   # 2% of account
  max_drawdown_pct: 0.05       # 5% of account
  max_open_positions: 5

symbols:
  - "AAPL"
  - "MSFT"
  - "GOOGL"
```

**Step 3: Create config/.env.example**

```
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
```

**Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
config/.env
data/*.db
logs/
*.log
.ruff_cache/
```

**Step 5: Create all __init__.py files and directory structure**

All `__init__.py` files are empty initially.

**Step 6: Create virtual environment and install dependencies**

Run:
```bash
cd /c/Users/linep/Autotrading
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
```

**Step 7: Verify pytest runs**

Run: `pytest --co -q`
Expected: `no tests ran` (clean setup)

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with pyproject.toml and config"
```

---

## Task 2: Core Types

**Files:**
- Create: `autotrader/core/types.py`
- Create: `tests/unit/test_types.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_types.py
import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar, Signal, Order, MarketContext, OrderResult, Position, AccountInfo


class TestBar:
    def test_create_bar(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
        )
        assert bar.symbol == "AAPL"
        assert bar.close == 151.0

    def test_bar_midpoint(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=148.0, close=151.0, volume=1000.0,
        )
        assert bar.midpoint == 150.0  # (high + low) / 2


class TestSignal:
    def test_create_long_signal(self):
        sig = Signal(strategy="momentum", symbol="AAPL", direction="long", strength=0.8)
        assert sig.direction == "long"
        assert 0.0 <= sig.strength <= 1.0

    def test_signal_strength_clamped(self):
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=1.5)
        assert sig.strength == 1.0


class TestOrder:
    def test_market_order(self):
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        assert order.limit_price is None
        assert order.stop_price is None

    def test_limit_order(self):
        order = Order(symbol="AAPL", side="buy", quantity=5, order_type="limit", limit_price=150.0)
        assert order.limit_price == 150.0


class TestMarketContext:
    def test_create_context(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            open=150.0, high=152.0, low=149.0, close=151.0, volume=1000.0,
        )
        ctx = MarketContext(symbol="AAPL", bar=bar, indicators={"SMA_20": 149.5}, history=deque([bar]))
        assert ctx.indicators["SMA_20"] == 149.5
        assert len(ctx.history) == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_types.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement core types**

```python
# autotrader/core/types.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


@dataclass(frozen=True, slots=True)
class Signal:
    strategy: str
    symbol: str
    direction: Literal["long", "short", "close"]
    strength: float
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "strength", max(0.0, min(1.0, self.strength)))


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: Literal["day", "gtc", "ioc"] = "day"


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str
    symbol: str
    status: Literal["accepted", "filled", "partially_filled", "cancelled", "rejected"]
    filled_qty: float = 0.0
    filled_price: float = 0.0


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    market_value: float
    unrealized_pnl: float
    side: Literal["long", "short"]


@dataclass(frozen=True, slots=True)
class AccountInfo:
    account_id: str
    buying_power: float
    portfolio_value: float
    cash: float
    equity: float


@dataclass(slots=True)
class MarketContext:
    symbol: str
    bar: Bar
    indicators: dict[str, float | dict]
    history: deque[Bar]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_types.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/core/types.py tests/unit/test_types.py
git commit -m "feat: core data types (Bar, Signal, Order, MarketContext)"
```

---

## Task 3: Core Exceptions

**Files:**
- Create: `autotrader/core/exceptions.py`
- Create: `tests/unit/test_exceptions.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_exceptions.py
from autotrader.core.exceptions import (
    AutoTraderError,
    ConfigError,
    BrokerError,
    ConnectionError,
    OrderError,
    RiskLimitError,
    DataError,
    StrategyError,
)


def test_exception_hierarchy():
    assert issubclass(ConfigError, AutoTraderError)
    assert issubclass(BrokerError, AutoTraderError)
    assert issubclass(ConnectionError, BrokerError)
    assert issubclass(OrderError, BrokerError)
    assert issubclass(RiskLimitError, AutoTraderError)
    assert issubclass(DataError, AutoTraderError)
    assert issubclass(StrategyError, AutoTraderError)


def test_exception_message():
    err = OrderError("AAPL", "insufficient buying power")
    assert "AAPL" in str(err)
    assert "insufficient buying power" in str(err)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: FAIL

**Step 3: Implement exceptions**

```python
# autotrader/core/exceptions.py
class AutoTraderError(Exception):
    """Base exception for all AutoTrader errors."""


class ConfigError(AutoTraderError):
    """Configuration-related errors."""


class BrokerError(AutoTraderError):
    """Broker communication and operation errors."""


class ConnectionError(BrokerError):
    """Broker connection failures."""

    def __init__(self, broker: str, reason: str):
        super().__init__(f"[{broker}] Connection failed: {reason}")
        self.broker = broker
        self.reason = reason


class OrderError(BrokerError):
    """Order submission/execution errors."""

    def __init__(self, symbol: str, reason: str):
        super().__init__(f"[{symbol}] Order error: {reason}")
        self.symbol = symbol
        self.reason = reason


class RiskLimitError(AutoTraderError):
    """Risk limit exceeded."""

    def __init__(self, rule: str, detail: str):
        super().__init__(f"Risk limit [{rule}]: {detail}")
        self.rule = rule
        self.detail = detail


class DataError(AutoTraderError):
    """Data pipeline errors."""


class StrategyError(AutoTraderError):
    """Strategy execution errors."""
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/core/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat: custom exception hierarchy"
```

---

## Task 4: Core Config

**Files:**
- Create: `autotrader/core/config.py`
- Create: `tests/unit/test_config.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_config.py
import pytest
from pathlib import Path

from autotrader.core.config import Settings, load_settings


def test_load_default_config(tmp_path):
    yaml_content = """
system:
  name: "TestTrader"
  log_level: "DEBUG"
  log_dir: "logs"
broker:
  type: "paper"
  paper_balance: 50000.0
alpaca:
  feed: "iex"
  paper: true
data:
  bar_history_size: 200
  store_type: "sqlite"
  sqlite_path: "data/test.db"
risk:
  max_position_pct: 0.10
  daily_loss_limit_pct: 0.02
  max_drawdown_pct: 0.05
  max_open_positions: 5
symbols:
  - "AAPL"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    settings = load_settings(config_file)
    assert settings.system.name == "TestTrader"
    assert settings.broker.type == "paper"
    assert settings.broker.paper_balance == 50000.0
    assert settings.risk.max_position_pct == 0.10
    assert settings.symbols == ["AAPL"]


def test_settings_defaults():
    settings = Settings()
    assert settings.system.log_level == "INFO"
    assert settings.broker.type == "paper"
    assert settings.risk.max_open_positions == 5
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL

**Step 3: Implement config**

```python
# autotrader/core/config.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class SystemConfig(BaseModel):
    name: str = "AutoTrader v2"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_dir: str = "logs"


class BrokerConfig(BaseModel):
    type: Literal["paper", "alpaca"] = "paper"
    paper_balance: float = 100_000.0


class AlpacaConfig(BaseModel):
    feed: Literal["iex", "sip"] = "iex"
    paper: bool = True


class DataConfig(BaseModel):
    bar_history_size: int = 500
    store_type: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "data/autotrader.db"


class RiskConfig(BaseModel):
    max_position_pct: float = 0.10
    daily_loss_limit_pct: float = 0.02
    max_drawdown_pct: float = 0.05
    max_open_positions: int = 5


class Settings(BaseModel):
    system: SystemConfig = SystemConfig()
    broker: BrokerConfig = BrokerConfig()
    alpaca: AlpacaConfig = AlpacaConfig()
    data: DataConfig = DataConfig()
    risk: RiskConfig = RiskConfig()
    symbols: list[str] = ["AAPL", "MSFT", "GOOGL"]


def load_settings(path: Path) -> Settings:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Settings.model_validate(raw)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/core/config.py tests/unit/test_config.py
git commit -m "feat: pydantic-based config with YAML loading"
```

---

## Task 5: Core EventBus

**Files:**
- Create: `autotrader/core/event_bus.py`
- Create: `tests/unit/test_event_bus.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_event_bus.py
import pytest
from autotrader.core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


class TestEventBus:
    async def test_subscribe_and_emit(self, bus):
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("test_event", handler)
        await bus.emit("test_event", {"value": 42})
        assert received == [{"value": 42}]

    async def test_multiple_subscribers(self, bus):
        results_a, results_b = [], []

        async def handler_a(data):
            results_a.append(data)

        async def handler_b(data):
            results_b.append(data)

        bus.subscribe("tick", handler_a)
        bus.subscribe("tick", handler_b)
        await bus.emit("tick", "AAPL")
        assert results_a == ["AAPL"]
        assert results_b == ["AAPL"]

    async def test_unsubscribe(self, bus):
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        bus.unsubscribe("event", handler)
        await bus.emit("event", "ignored")
        assert received == []

    async def test_emit_no_subscribers(self, bus):
        # Should not raise
        await bus.emit("nobody_listens", "data")

    async def test_handler_error_does_not_block_others(self, bus):
        results = []

        async def bad_handler(data):
            raise ValueError("boom")

        async def good_handler(data):
            results.append(data)

        bus.subscribe("event", bad_handler)
        bus.subscribe("event", good_handler)
        await bus.emit("event", "ok")
        assert results == ["ok"]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_event_bus.py -v`
Expected: FAIL

**Step 3: Implement EventBus**

```python
# autotrader/core/event_bus.py
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: str, data: Any = None) -> None:
        for handler in self._handlers.get(event, []):
            try:
                await handler(data)
            except Exception:
                logger.exception("Handler %s failed for event %s", handler.__name__, event)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_event_bus.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/core/event_bus.py tests/unit/test_event_bus.py
git commit -m "feat: async EventBus with error isolation"
```

---

## Task 6: Core Logger

**Files:**
- Create: `autotrader/core/logger.py`
- Create: `tests/unit/test_logger.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_logger.py
import logging
from autotrader.core.logger import setup_logging


def test_setup_logging_returns_logger():
    log = setup_logging("TEST", level="DEBUG")
    assert isinstance(log, logging.Logger)
    assert log.level == logging.DEBUG


def test_setup_logging_default_level():
    log = setup_logging("DEFAULT")
    assert log.level == logging.INFO
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_logger.py -v`
Expected: FAIL

**Step 3: Implement logger**

```python
# autotrader/core/logger.py
from __future__ import annotations

import logging
import sys


def setup_logging(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)

    return logger
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_logger.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/core/logger.py tests/unit/test_logger.py
git commit -m "feat: structured logging setup"
```

---

## Task 7: Broker ABC + Paper Adapter

**Files:**
- Create: `autotrader/broker/base.py`
- Create: `autotrader/broker/paper.py`
- Create: `tests/unit/test_paper_broker.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_paper_broker.py
import pytest
from autotrader.core.types import Order
from autotrader.broker.paper import PaperBroker


@pytest.fixture
def broker():
    return PaperBroker(initial_balance=100_000.0)


class TestPaperBroker:
    async def test_connect_disconnect(self, broker):
        await broker.connect()
        assert broker.connected
        await broker.disconnect()
        assert not broker.connected

    async def test_get_account(self, broker):
        await broker.connect()
        account = await broker.get_account()
        assert account.cash == 100_000.0
        assert account.equity == 100_000.0

    async def test_submit_market_buy(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await broker.submit_order(order)
        assert result.status == "filled"
        assert result.filled_qty == 10
        assert result.filled_price == 150.0

    async def test_positions_after_buy(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(order)
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

    async def test_submit_market_sell(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await broker.submit_order(buy)

        broker.set_price("AAPL", 155.0)
        sell = Order(symbol="AAPL", side="sell", quantity=10, order_type="market")
        result = await broker.submit_order(sell)
        assert result.status == "filled"

        account = await broker.get_account()
        assert account.cash == 100_000.0 + (155.0 - 150.0) * 10

    async def test_cancel_order(self, broker):
        await broker.connect()
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=100.0)
        result = await broker.submit_order(order)
        cancelled = await broker.cancel_order(result.order_id)
        assert cancelled is True

    async def test_insufficient_buying_power(self, broker):
        await broker.connect()
        broker.set_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side="buy", quantity=10_000, order_type="market")
        result = await broker.submit_order(order)
        assert result.status == "rejected"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_paper_broker.py -v`
Expected: FAIL

**Step 3: Implement broker ABC**

```python
# autotrader/broker/base.py
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
```

**Step 4: Implement PaperBroker**

```python
# autotrader/broker/paper.py
from __future__ import annotations

import uuid
from typing import Callable

from autotrader.broker.base import BrokerAdapter
from autotrader.core.types import AccountInfo, Order, OrderResult, Position


class PaperBroker(BrokerAdapter):
    def __init__(self, initial_balance: float = 100_000.0) -> None:
        self._initial_balance = initial_balance
        self._cash = initial_balance
        self._positions: dict[str, _PaperPosition] = {}
        self._pending_orders: dict[str, Order] = {}
        self._prices: dict[str, float] = {}
        self.connected = False

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def submit_order(self, order: Order) -> OrderResult:
        order_id = str(uuid.uuid4())

        if order.order_type == "market":
            return self._execute_market(order_id, order)

        # Limit/stop orders go to pending
        self._pending_orders[order_id] = order
        return OrderResult(
            order_id=order_id, symbol=order.symbol, status="accepted",
        )

    def _execute_market(self, order_id: str, order: Order) -> OrderResult:
        price = self._prices.get(order.symbol, 0.0)
        cost = price * order.quantity

        if order.side == "buy":
            if cost > self._cash:
                return OrderResult(order_id=order_id, symbol=order.symbol, status="rejected")
            self._cash -= cost
            pos = self._positions.get(order.symbol)
            if pos:
                pos.add(order.quantity, price)
            else:
                self._positions[order.symbol] = _PaperPosition(order.symbol, order.quantity, price)
        else:  # sell
            pos = self._positions.get(order.symbol)
            if not pos or pos.quantity < order.quantity:
                return OrderResult(order_id=order_id, symbol=order.symbol, status="rejected")
            self._cash += cost
            pos.reduce(order.quantity)
            if pos.quantity == 0:
                del self._positions[order.symbol]

        return OrderResult(
            order_id=order_id, symbol=order.symbol, status="filled",
            filled_qty=order.quantity, filled_price=price,
        )

    async def cancel_order(self, order_id: str) -> bool:
        return self._pending_orders.pop(order_id, None) is not None

    async def get_positions(self) -> list[Position]:
        result = []
        for sym, pos in self._positions.items():
            price = self._prices.get(sym, pos.avg_price)
            mv = price * pos.quantity
            pnl = (price - pos.avg_price) * pos.quantity
            result.append(Position(
                symbol=sym, quantity=pos.quantity, avg_entry_price=pos.avg_price,
                market_value=mv, unrealized_pnl=pnl, side="long",
            ))
        return result

    async def get_account(self) -> AccountInfo:
        equity = self._cash + sum(
            self._prices.get(s, p.avg_price) * p.quantity
            for s, p in self._positions.items()
        )
        return AccountInfo(
            account_id="paper", buying_power=self._cash,
            portfolio_value=equity, cash=self._cash, equity=equity,
        )

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        pass  # Paper broker does not produce bars


class _PaperPosition:
    def __init__(self, symbol: str, quantity: float, avg_price: float) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price

    def add(self, qty: float, price: float) -> None:
        total_cost = self.avg_price * self.quantity + price * qty
        self.quantity += qty
        self.avg_price = total_cost / self.quantity

    def reduce(self, qty: float) -> None:
        self.quantity -= qty
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_paper_broker.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add autotrader/broker/base.py autotrader/broker/paper.py tests/unit/test_paper_broker.py
git commit -m "feat: BrokerAdapter ABC and PaperBroker implementation"
```

---

## Task 8: Indicator System

**Files:**
- Create: `autotrader/indicators/base.py`
- Create: `autotrader/indicators/engine.py`
- Create: `autotrader/indicators/builtin/moving_average.py`
- Create: `autotrader/indicators/builtin/momentum.py`
- Create: `autotrader/indicators/builtin/volatility.py`
- Create: `tests/unit/test_indicators.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_indicators.py
import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator, IndicatorSpec
from autotrader.indicators.engine import IndicatorEngine
from autotrader.indicators.builtin.moving_average import SMA, EMA
from autotrader.indicators.builtin.momentum import RSI
from autotrader.indicators.builtin.volatility import ATR


def _make_bars(closes: list[float], symbol: str = "AAPL") -> deque[Bar]:
    bars = deque()
    for i, c in enumerate(closes):
        bars.append(Bar(
            symbol=symbol,
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=c, high=c + 1, low=c - 1, close=c, volume=100.0,
        ))
    return bars


class TestSMA:
    def test_sma_basic(self):
        sma = SMA(period=3)
        bars = _make_bars([10.0, 20.0, 30.0])
        result = sma.calculate(bars)
        assert result == pytest.approx(20.0)

    def test_sma_warmup(self):
        sma = SMA(period=5)
        assert sma.warmup_period == 5
        bars = _make_bars([10.0, 20.0])  # not enough
        result = sma.calculate(bars)
        assert result is None


class TestEMA:
    def test_ema_basic(self):
        ema = EMA(period=3)
        bars = _make_bars([10.0, 20.0, 30.0, 40.0, 50.0])
        result = ema.calculate(bars)
        assert isinstance(result, float)
        assert result > 30.0  # EMA weights recent values more


class TestRSI:
    def test_rsi_all_gains(self):
        rsi = RSI(period=14)
        bars = _make_bars([float(i) for i in range(1, 20)])
        result = rsi.calculate(bars)
        assert result is not None
        assert result > 90.0  # all upward movement

    def test_rsi_warmup(self):
        rsi = RSI(period=14)
        assert rsi.warmup_period == 15  # period + 1
        bars = _make_bars([10.0, 20.0])
        assert rsi.calculate(bars) is None


class TestATR:
    def test_atr_basic(self):
        atr = ATR(period=3)
        bars = _make_bars([10.0, 12.0, 11.0, 13.0, 12.0])
        result = atr.calculate(bars)
        assert result is not None
        assert result > 0


class TestIndicatorEngine:
    def test_register_and_compute(self):
        engine = IndicatorEngine()
        engine.register(IndicatorSpec("SMA", {"period": 3}))
        bars = _make_bars([10.0, 20.0, 30.0])
        results = engine.compute(bars)
        assert "SMA_3" in results
        assert results["SMA_3"] == pytest.approx(20.0)

    def test_compute_multiple(self):
        engine = IndicatorEngine()
        engine.register(IndicatorSpec("SMA", {"period": 3}))
        engine.register(IndicatorSpec("RSI", {"period": 14}))
        bars = _make_bars([float(i) for i in range(1, 20)])
        results = engine.compute(bars)
        assert "SMA_3" in results
        assert "RSI_14" in results
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_indicators.py -v`
Expected: FAIL

**Step 3: Implement indicator base**

```python
# autotrader/indicators/base.py
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
```

**Step 4: Implement built-in indicators**

```python
# autotrader/indicators/builtin/moving_average.py
from __future__ import annotations

from collections import deque

from autotrader.core.types import Bar
from autotrader.indicators.base import Indicator


class SMA(Indicator):
    def __init__(self, period: int) -> None:
        self.name = "SMA"
        self.warmup_period = period
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.period:
            return None
        closes = [b.close for b in list(bars)[-self.period :]]
        return sum(closes) / self.period


class EMA(Indicator):
    def __init__(self, period: int) -> None:
        self.name = "EMA"
        self.warmup_period = period
        self.period = period

    def calculate(self, bars: deque[Bar]) -> float | None:
        if len(bars) < self.period:
            return None
        closes = [b.close for b in bars]
        multiplier = 2 / (self.period + 1)
        ema = sum(closes[: self.period]) / self.period
        for close in closes[self.period :]:
            ema = (close - ema) * multiplier + ema
        return ema
```

```python
# autotrader/indicators/builtin/momentum.py
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
```

```python
# autotrader/indicators/builtin/volatility.py
from __future__ import annotations

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
```

**Step 5: Implement IndicatorEngine**

```python
# autotrader/indicators/engine.py
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
```

**Step 6: Run tests**

Run: `pytest tests/unit/test_indicators.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add autotrader/indicators/ tests/unit/test_indicators.py
git commit -m "feat: hybrid indicator system with SMA, EMA, RSI, ATR"
```

---

## Task 9: Strategy ABC + Registry + Engine

**Files:**
- Create: `autotrader/strategy/base.py`
- Create: `autotrader/strategy/registry.py`
- Create: `autotrader/strategy/engine.py`
- Create: `tests/unit/test_strategy.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_strategy.py
import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy
from autotrader.strategy.registry import StrategyRegistry
from autotrader.strategy.engine import StrategyEngine


class DummyStrategy(Strategy):
    name = "dummy"
    required_indicators = [IndicatorSpec("SMA", {"period": 3})]

    def on_context(self, ctx: MarketContext) -> Signal | None:
        sma = ctx.indicators.get("SMA_3")
        if sma and ctx.bar.close > sma:
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="long", strength=0.5)
        return None


def _make_context(close: float, sma: float) -> MarketContext:
    bar = Bar("AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc), close, close + 1, close - 1, close, 100)
    return MarketContext(symbol="AAPL", bar=bar, indicators={"SMA_3": sma}, history=deque([bar]))


class TestStrategy:
    def test_strategy_generates_signal(self):
        strat = DummyStrategy()
        ctx = _make_context(close=105.0, sma=100.0)
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "long"

    def test_strategy_no_signal(self):
        strat = DummyStrategy()
        ctx = _make_context(close=95.0, sma=100.0)
        sig = strat.on_context(ctx)
        assert sig is None


class TestRegistry:
    def test_register_and_get(self):
        reg = StrategyRegistry()
        strat = DummyStrategy()
        reg.register(strat)
        assert reg.get("dummy") is strat
        assert len(reg.all()) == 1

    def test_duplicate_raises(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy())
        with pytest.raises(ValueError):
            reg.register(DummyStrategy())


class TestStrategyEngine:
    async def test_process_context(self):
        engine = StrategyEngine()
        engine.add_strategy(DummyStrategy())
        ctx = _make_context(close=105.0, sma=100.0)
        signals = await engine.process(ctx)
        assert len(signals) == 1
        assert signals[0].direction == "long"

    async def test_no_signals(self):
        engine = StrategyEngine()
        engine.add_strategy(DummyStrategy())
        ctx = _make_context(close=95.0, sma=100.0)
        signals = await engine.process(ctx)
        assert signals == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_strategy.py -v`
Expected: FAIL

**Step 3: Implement strategy base, registry, engine**

```python
# autotrader/strategy/base.py
from __future__ import annotations

from abc import ABC, abstractmethod

from autotrader.core.types import MarketContext, Signal, OrderResult, Position
from autotrader.indicators.base import IndicatorSpec


class Strategy(ABC):
    name: str
    required_indicators: list[IndicatorSpec] = []

    @abstractmethod
    def on_context(self, ctx: MarketContext) -> Signal | None: ...

    def on_order_filled(self, fill: OrderResult) -> None:
        pass

    def on_position_update(self, pos: Position) -> None:
        pass
```

```python
# autotrader/strategy/registry.py
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
```

```python
# autotrader/strategy/engine.py
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
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_strategy.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/strategy/ tests/unit/test_strategy.py
git commit -m "feat: Strategy ABC, registry, and execution engine"
```

---

## Task 10: Risk Manager

**Files:**
- Create: `autotrader/risk/manager.py`
- Create: `autotrader/risk/position_sizer.py`
- Create: `tests/unit/test_risk.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_risk.py
import pytest
from autotrader.core.types import Signal, AccountInfo, Position
from autotrader.core.config import RiskConfig
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer


@pytest.fixture
def config():
    return RiskConfig(
        max_position_pct=0.10,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.05,
        max_open_positions=3,
    )


@pytest.fixture
def account():
    return AccountInfo(
        account_id="test", buying_power=100_000.0,
        portfolio_value=100_000.0, cash=100_000.0, equity=100_000.0,
    )


class TestRiskManager:
    def test_approve_valid_signal(self, config, account):
        rm = RiskManager(config)
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=0.8)
        assert rm.validate(sig, account, positions=[]) is True

    def test_reject_too_many_positions(self, config, account):
        rm = RiskManager(config)
        existing = [
            Position(symbol=s, quantity=10, avg_entry_price=100, market_value=1000, unrealized_pnl=0, side="long")
            for s in ["AAPL", "MSFT", "GOOGL"]
        ]
        sig = Signal(strategy="test", symbol="TSLA", direction="long", strength=0.8)
        assert rm.validate(sig, account, positions=existing) is False

    def test_allow_close_even_at_limit(self, config, account):
        rm = RiskManager(config)
        existing = [
            Position(symbol=s, quantity=10, avg_entry_price=100, market_value=1000, unrealized_pnl=0, side="long")
            for s in ["AAPL", "MSFT", "GOOGL"]
        ]
        sig = Signal(strategy="test", symbol="AAPL", direction="close", strength=1.0)
        assert rm.validate(sig, account, positions=existing) is True

    def test_reject_daily_loss_exceeded(self, config):
        rm = RiskManager(config)
        rm.record_pnl(-2500.0)  # > 2% of 100k
        account = AccountInfo("test", 97_500, 97_500, 97_500, 97_500)
        sig = Signal(strategy="test", symbol="AAPL", direction="long", strength=0.5)
        assert rm.validate(sig, account, positions=[]) is False


class TestPositionSizer:
    def test_size_by_risk_pct(self, config, account):
        sizer = PositionSizer(config)
        qty = sizer.calculate(price=150.0, account=account)
        max_value = account.equity * config.max_position_pct  # 10000
        expected_qty = int(max_value / 150.0)  # 66
        assert qty == expected_qty

    def test_zero_price(self, config, account):
        sizer = PositionSizer(config)
        assert sizer.calculate(price=0.0, account=account) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_risk.py -v`
Expected: FAIL

**Step 3: Implement RiskManager and PositionSizer**

```python
# autotrader/risk/manager.py
from __future__ import annotations

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo, Position, Signal


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._daily_pnl: float = 0.0
        self._peak_equity: float = 0.0

    def validate(self, signal: Signal, account: AccountInfo, positions: list[Position]) -> bool:
        if signal.direction == "close":
            return True
        return all([
            self._check_max_positions(positions),
            self._check_daily_loss(account),
            self._check_drawdown(account),
        ])

    def record_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    def update_peak(self, equity: float) -> None:
        if equity > self._peak_equity:
            self._peak_equity = equity

    def _check_max_positions(self, positions: list[Position]) -> bool:
        return len(positions) < self._config.max_open_positions

    def _check_daily_loss(self, account: AccountInfo) -> bool:
        limit = account.equity * self._config.daily_loss_limit_pct
        return abs(self._daily_pnl) < limit or self._daily_pnl >= 0

    def _check_drawdown(self, account: AccountInfo) -> bool:
        if self._peak_equity == 0:
            self._peak_equity = account.equity
            return True
        drawdown = (self._peak_equity - account.equity) / self._peak_equity
        return drawdown < self._config.max_drawdown_pct
```

```python
# autotrader/risk/position_sizer.py
from __future__ import annotations

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo


class PositionSizer:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def calculate(self, price: float, account: AccountInfo) -> int:
        if price <= 0:
            return 0
        max_value = account.equity * self._config.max_position_pct
        return int(max_value / price)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_risk.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/risk/ tests/unit/test_risk.py
git commit -m "feat: RiskManager and PositionSizer with config-driven rules"
```

---

## Task 11: Portfolio Tracker

**Files:**
- Create: `autotrader/portfolio/tracker.py`
- Create: `autotrader/portfolio/performance.py`
- Create: `tests/unit/test_portfolio.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_portfolio.py
import pytest
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.portfolio.performance import calculate_metrics


class TestPortfolioTracker:
    def test_record_trade(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade(symbol="AAPL", side="buy", qty=10, price=150.0, pnl=0.0)
        assert len(tracker.trades) == 1

    def test_equity_curve(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade("AAPL", "sell", 10, 155.0, pnl=50.0)
        tracker.update_equity(100_050.0)
        assert tracker.equity_curve[-1] == 100_050.0

    def test_daily_pnl(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade("AAPL", "sell", 10, 155.0, pnl=50.0)
        tracker.record_trade("MSFT", "sell", 5, 300.0, pnl=-30.0)
        assert tracker.total_pnl == pytest.approx(20.0)


class TestPerformanceMetrics:
    def test_win_rate(self):
        trades = [100.0, -50.0, 75.0, -25.0, 200.0]
        metrics = calculate_metrics(trades, initial_equity=100_000.0)
        assert metrics["win_rate"] == pytest.approx(0.6)  # 3/5

    def test_profit_factor(self):
        trades = [100.0, -50.0, 200.0]
        metrics = calculate_metrics(trades, initial_equity=100_000.0)
        assert metrics["profit_factor"] == pytest.approx(6.0)  # 300/50

    def test_empty_trades(self):
        metrics = calculate_metrics([], initial_equity=100_000.0)
        assert metrics["win_rate"] == 0.0
        assert metrics["total_trades"] == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_portfolio.py -v`
Expected: FAIL

**Step 3: Implement portfolio tracker and performance**

```python
# autotrader/portfolio/tracker.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    symbol: str
    side: str
    qty: float
    price: float
    pnl: float


class PortfolioTracker:
    def __init__(self, initial_equity: float) -> None:
        self.initial_equity = initial_equity
        self.trades: list[TradeRecord] = []
        self.equity_curve: list[float] = [initial_equity]
        self.total_pnl: float = 0.0

    def record_trade(self, symbol: str, side: str, qty: float, price: float, pnl: float) -> None:
        self.trades.append(TradeRecord(symbol=symbol, side=side, qty=qty, price=price, pnl=pnl))
        self.total_pnl += pnl

    def update_equity(self, equity: float) -> None:
        self.equity_curve.append(equity)
```

```python
# autotrader/portfolio/performance.py
from __future__ import annotations


def calculate_metrics(trade_pnls: list[float], initial_equity: float) -> dict:
    if not trade_pnls:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_pnl": 0.0, "max_drawdown": 0.0,
        }

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]

    total_wins = sum(wins)
    total_losses = abs(sum(losses))

    # Equity curve for drawdown
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for pnl in trade_pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "total_trades": len(trade_pnls),
        "win_rate": len(wins) / len(trade_pnls),
        "profit_factor": total_wins / total_losses if total_losses > 0 else float("inf"),
        "total_pnl": sum(trade_pnls),
        "max_drawdown": max_dd,
    }
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_portfolio.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/portfolio/ tests/unit/test_portfolio.py
git commit -m "feat: PortfolioTracker and performance metrics"
```

---

## Task 12: Data Store (SQLite)

**Files:**
- Create: `autotrader/data/store.py`
- Create: `autotrader/data/sqlite_store.py`
- Create: `tests/unit/test_data_store.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_data_store.py
import pytest
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.data.sqlite_store import SQLiteStore


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = SQLiteStore(db_path)
    await s.initialize()
    yield s
    await s.close()


class TestSQLiteStore:
    async def test_save_and_load_bars(self, store):
        bars = [
            Bar("AAPL", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), 150, 152, 149, 151, 1000),
            Bar("AAPL", datetime(2026, 1, 15, 10, 1, tzinfo=timezone.utc), 151, 153, 150, 152, 1100),
        ]
        await store.save_bars(bars)
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc),
        )
        assert len(loaded) == 2
        assert loaded[0].close == 151

    async def test_load_empty(self, store):
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        assert loaded == []

    async def test_no_duplicates(self, store):
        bar = Bar("AAPL", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), 150, 152, 149, 151, 1000)
        await store.save_bars([bar])
        await store.save_bars([bar])  # duplicate
        loaded = await store.load_bars(
            "AAPL",
            datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc),
        )
        assert len(loaded) == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_data_store.py -v`
Expected: FAIL

**Step 3: Implement data store**

```python
# autotrader/data/store.py
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
```

```python
# autotrader/data/sqlite_store.py
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from autotrader.core.types import Bar
from autotrader.data.store import DataStore


class SQLiteStore(DataStore):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save_bars(self, bars: list[Bar]) -> None:
        assert self._db is not None
        await self._db.executemany(
            "INSERT OR IGNORE INTO bars (symbol, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(b.symbol, b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume) for b in bars],
        )
        await self._db.commit()

    async def load_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT symbol, timestamp, open, high, low, close, volume FROM bars WHERE symbol = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (symbol, start.isoformat(), end.isoformat()),
        )
        rows = await cursor.fetchall()
        return [
            Bar(
                symbol=r[0],
                timestamp=datetime.fromisoformat(r[1]),
                open=r[2], high=r[3], low=r[4], close=r[5], volume=r[6],
            )
            for r in rows
        ]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_data_store.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/data/ tests/unit/test_data_store.py
git commit -m "feat: DataStore ABC and SQLite implementation"
```

---

## Task 13: Backtest Engine

**Files:**
- Create: `autotrader/backtest/engine.py`
- Create: `autotrader/backtest/simulator.py`
- Create: `tests/unit/test_backtest.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_backtest.py
import pytest
from collections import deque
from datetime import datetime, timezone, timedelta

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.core.config import RiskConfig
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy
from autotrader.backtest.engine import BacktestEngine


class BuyAndHold(Strategy):
    name = "buy_and_hold"
    required_indicators = []
    _bought = False

    def on_context(self, ctx: MarketContext) -> Signal | None:
        if not self._bought:
            self._bought = True
            return Signal(strategy=self.name, symbol=ctx.symbol, direction="long", strength=1.0)
        return None


def _make_bars(n: int, start_price: float = 100.0, trend: float = 1.0) -> list[Bar]:
    bars = []
    price = start_price
    for i in range(n):
        bars.append(Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=price, high=price + 1, low=price - 1, close=price + trend, volume=1000,
        ))
        price += trend
    return bars


class TestBacktestEngine:
    async def test_run_backtest(self):
        bars = _make_bars(20, start_price=100.0, trend=0.5)
        engine = BacktestEngine(
            initial_balance=100_000.0,
            risk_config=RiskConfig(),
        )
        engine.add_strategy(BuyAndHold())
        result = engine.run(bars)
        assert result.total_trades >= 1
        assert result.final_equity > 100_000.0  # price went up

    async def test_backtest_metrics(self):
        bars = _make_bars(50, start_price=100.0, trend=0.5)
        engine = BacktestEngine(initial_balance=100_000.0, risk_config=RiskConfig())
        engine.add_strategy(BuyAndHold())
        result = engine.run(bars)
        assert "win_rate" in result.metrics
        assert "profit_factor" in result.metrics
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_backtest.py -v`
Expected: FAIL

**Step 3: Implement BacktestEngine**

```python
# autotrader/backtest/simulator.py
from __future__ import annotations

from autotrader.core.types import Order, OrderResult, Signal
from autotrader.risk.position_sizer import PositionSizer
from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo

import uuid


class BacktestSimulator:
    def __init__(self, initial_balance: float, risk_config: RiskConfig) -> None:
        self._cash = initial_balance
        self._positions: dict[str, _SimPosition] = {}
        self._sizer = PositionSizer(risk_config)

    def execute_signal(self, signal: Signal, price: float) -> OrderResult | None:
        account = self._get_account()

        if signal.direction == "long":
            qty = self._sizer.calculate(price, account)
            if qty <= 0:
                return None
            cost = qty * price
            if cost > self._cash:
                return None
            self._cash -= cost
            self._positions[signal.symbol] = _SimPosition(signal.symbol, qty, price)
            return OrderResult(str(uuid.uuid4()), signal.symbol, "filled", qty, price)

        elif signal.direction == "close":
            pos = self._positions.pop(signal.symbol, None)
            if pos is None:
                return None
            proceeds = pos.quantity * price
            self._cash += proceeds
            pnl = (price - pos.avg_price) * pos.quantity
            return OrderResult(str(uuid.uuid4()), signal.symbol, "filled", pos.quantity, price)

        return None

    def get_pnl(self, symbol: str, current_price: float) -> float:
        pos = self._positions.get(symbol)
        if not pos:
            return 0.0
        return (current_price - pos.avg_price) * pos.quantity

    def _get_account(self) -> AccountInfo:
        equity = self._cash + sum(p.quantity * p.avg_price for p in self._positions.values())
        return AccountInfo("backtest", self._cash, equity, self._cash, equity)

    @property
    def equity(self) -> float:
        return self._cash + sum(p.quantity * p.avg_price for p in self._positions.values())

    def get_equity_with_prices(self, prices: dict[str, float]) -> float:
        market_value = sum(
            p.quantity * prices.get(p.symbol, p.avg_price)
            for p in self._positions.values()
        )
        return self._cash + market_value

    @property
    def has_positions(self) -> bool:
        return len(self._positions) > 0


class _SimPosition:
    def __init__(self, symbol: str, quantity: float, avg_price: float) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
```

```python
# autotrader/backtest/engine.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import Bar, MarketContext
from autotrader.core.config import RiskConfig
from autotrader.indicators.base import IndicatorSpec
from autotrader.indicators.engine import IndicatorEngine
from autotrader.strategy.base import Strategy
from autotrader.risk.manager import RiskManager
from autotrader.backtest.simulator import BacktestSimulator
from autotrader.portfolio.performance import calculate_metrics


@dataclass
class BacktestResult:
    total_trades: int
    final_equity: float
    metrics: dict
    equity_curve: list[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, initial_balance: float, risk_config: RiskConfig) -> None:
        self._initial_balance = initial_balance
        self._risk_config = risk_config
        self._strategies: list[Strategy] = []
        self._indicator_engine = IndicatorEngine()

    def add_strategy(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)
        for spec in strategy.required_indicators:
            self._indicator_engine.register(spec)

    def run(self, bars: list[Bar]) -> BacktestResult:
        simulator = BacktestSimulator(self._initial_balance, self._risk_config)
        risk_mgr = RiskManager(self._risk_config)
        history: deque[Bar] = deque(maxlen=500)
        trade_pnls: list[float] = []
        equity_curve: list[float] = [self._initial_balance]

        for bar in bars:
            history.append(bar)
            indicators = self._indicator_engine.compute(history)
            ctx = MarketContext(symbol=bar.symbol, bar=bar, indicators=indicators, history=history)

            for strat in self._strategies:
                try:
                    signal = strat.on_context(ctx)
                except Exception:
                    continue

                if signal is None:
                    continue

                account = simulator._get_account()
                if not risk_mgr.validate(signal, account, positions=[]):
                    continue

                result = simulator.execute_signal(signal, bar.close)
                if result and result.status == "filled":
                    if signal.direction == "close":
                        pnl = simulator.get_pnl(signal.symbol, bar.close)
                        trade_pnls.append(pnl)

            equity = simulator.get_equity_with_prices({bar.symbol: bar.close})
            equity_curve.append(equity)

        metrics = calculate_metrics(trade_pnls, self._initial_balance)
        return BacktestResult(
            total_trades=len(trade_pnls),
            final_equity=equity_curve[-1],
            metrics=metrics,
            equity_curve=equity_curve,
        )
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_backtest.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/backtest/ tests/unit/test_backtest.py
git commit -m "feat: BacktestEngine with simulator and performance reporting"
```

---

## Task 14: Alpaca Broker Adapter

**Files:**
- Create: `autotrader/broker/alpaca_adapter.py`
- Create: `tests/unit/test_alpaca_adapter.py`

**Step 1: Write failing tests (unit tests with mock)**

```python
# tests/unit/test_alpaca_adapter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autotrader.core.types import Order
from autotrader.broker.alpaca_adapter import AlpacaAdapter


@pytest.fixture
def adapter():
    return AlpacaAdapter(api_key="test_key", secret_key="test_secret", paper=True)


class TestAlpacaAdapter:
    def test_init_paper_mode(self, adapter):
        assert adapter._paper is True

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_connect(self, mock_client_cls, adapter):
        await adapter.connect()
        mock_client_cls.assert_called_once_with("test_key", "test_secret", paper=True)
        assert adapter.connected

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_get_account(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_account = MagicMock()
        mock_account.id = "test-id"
        mock_account.buying_power = "100000.0"
        mock_account.portfolio_value = "100000.0"
        mock_account.cash = "100000.0"
        mock_account.equity = "100000.0"
        mock_client.get_account.return_value = mock_account
        mock_client_cls.return_value = mock_client

        await adapter.connect()
        account = await adapter.get_account()
        assert account.buying_power == 100_000.0

    @patch("autotrader.broker.alpaca_adapter.TradingClient")
    async def test_submit_market_order(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "AAPL"
        mock_order.status = "accepted"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order
        mock_client_cls.return_value = mock_client

        await adapter.connect()
        order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        result = await adapter.submit_order(order)
        assert result.order_id == "order-123"
        assert result.status == "accepted"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_alpaca_adapter.py -v`
Expected: FAIL

**Step 3: Implement AlpacaAdapter**

```python
# autotrader/broker/alpaca_adapter.py
from __future__ import annotations

import logging
from typing import Callable

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.live import StockDataStream

from autotrader.broker.base import BrokerAdapter
from autotrader.core.types import AccountInfo, Order, OrderResult, Position

logger = logging.getLogger(__name__)

_SIDE_MAP = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
_TIF_MAP = {"day": TimeInForce.DAY, "gtc": TimeInForce.GTC, "ioc": TimeInForce.IOC}


class AlpacaAdapter(BrokerAdapter):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True, feed: str = "iex") -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._feed = feed
        self._client: TradingClient | None = None
        self._stream: StockDataStream | None = None
        self.connected = False

    async def connect(self) -> None:
        self._client = TradingClient(self._api_key, self._secret_key, paper=self._paper)
        self.connected = True
        logger.info("Connected to Alpaca (paper=%s)", self._paper)

    async def disconnect(self) -> None:
        if self._stream:
            self._stream.stop()
        self._client = None
        self.connected = False
        logger.info("Disconnected from Alpaca")

    async def submit_order(self, order: Order) -> OrderResult:
        assert self._client is not None
        side = _SIDE_MAP[order.side]
        tif = _TIF_MAP.get(order.time_in_force, TimeInForce.DAY)

        if order.order_type == "market":
            req = MarketOrderRequest(symbol=order.symbol, qty=order.quantity, side=side, time_in_force=tif)
        elif order.order_type == "limit":
            req = LimitOrderRequest(
                symbol=order.symbol, qty=order.quantity, side=side,
                time_in_force=tif, limit_price=order.limit_price,
            )
        elif order.order_type == "stop":
            req = StopOrderRequest(
                symbol=order.symbol, qty=order.quantity, side=side,
                time_in_force=tif, stop_price=order.stop_price,
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

        result = self._client.submit_order(req)
        return OrderResult(
            order_id=str(result.id),
            symbol=result.symbol,
            status=str(result.status),
            filled_qty=float(result.filled_qty or 0),
            filled_price=float(result.filled_avg_price or 0),
        )

    async def cancel_order(self, order_id: str) -> bool:
        assert self._client is not None
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        assert self._client is not None
        raw = self._client.get_all_positions()
        return [
            Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pnl=float(p.unrealized_pl),
                side="long" if float(p.qty) > 0 else "short",
            )
            for p in raw
        ]

    async def get_account(self) -> AccountInfo:
        assert self._client is not None
        a = self._client.get_account()
        return AccountInfo(
            account_id=str(a.id),
            buying_power=float(a.buying_power),
            portfolio_value=float(a.portfolio_value),
            cash=float(a.cash),
            equity=float(a.equity),
        )

    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None:
        self._stream = StockDataStream(self._api_key, self._secret_key)
        self._stream.subscribe_bars(callback, *symbols)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_alpaca_adapter.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/broker/alpaca_adapter.py tests/unit/test_alpaca_adapter.py
git commit -m "feat: AlpacaAdapter with trading, positions, and streaming"
```

---

## Task 15: Main Entry Point

**Files:**
- Create: `autotrader/main.py`
- Create: `tests/unit/test_main.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_main.py
import pytest
from unittest.mock import patch, AsyncMock

from autotrader.main import AutoTrader
from autotrader.core.config import Settings


class TestAutoTrader:
    def test_create_with_defaults(self):
        app = AutoTrader(Settings())
        assert app is not None

    def test_create_paper_broker(self):
        settings = Settings()
        settings.broker.type = "paper"
        app = AutoTrader(settings)
        from autotrader.broker.paper import PaperBroker
        assert isinstance(app._broker, PaperBroker)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_main.py -v`
Expected: FAIL

**Step 3: Implement main**

```python
# autotrader/main.py
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from autotrader.core.config import Settings, load_settings
from autotrader.core.event_bus import EventBus
from autotrader.core.logger import setup_logging
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.indicators.engine import IndicatorEngine
from autotrader.strategy.engine import StrategyEngine
from autotrader.risk.manager import RiskManager

logger = logging.getLogger(__name__)


class AutoTrader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bus = EventBus()
        self._broker = self._create_broker()
        self._indicator_engine = IndicatorEngine()
        self._strategy_engine = StrategyEngine()
        self._risk_manager = RiskManager(settings.risk)

    def _create_broker(self) -> BrokerAdapter:
        if self._settings.broker.type == "paper":
            return PaperBroker(self._settings.broker.paper_balance)
        elif self._settings.broker.type == "alpaca":
            from autotrader.broker.alpaca_adapter import AlpacaAdapter
            load_dotenv()
            return AlpacaAdapter(
                api_key=os.environ["ALPACA_API_KEY"],
                secret_key=os.environ["ALPACA_SECRET_KEY"],
                paper=self._settings.alpaca.paper,
                feed=self._settings.alpaca.feed,
            )
        raise ValueError(f"Unknown broker type: {self._settings.broker.type}")

    async def start(self) -> None:
        logger.info("Starting %s", self._settings.system.name)
        await self._broker.connect()
        account = await self._broker.get_account()
        logger.info("Account equity: %.2f", account.equity)

    async def stop(self) -> None:
        logger.info("Stopping %s", self._settings.system.name)
        await self._broker.disconnect()


def main() -> None:
    config_path = Path("config/default.yaml")
    if config_path.exists():
        settings = load_settings(config_path)
    else:
        settings = Settings()

    setup_logging("autotrader", level=settings.system.log_level)
    app = AutoTrader(settings)

    async def run():
        await app.start()
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await app.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_main.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/main.py tests/unit/test_main.py
git commit -m "feat: AutoTrader main entry point with broker selection"
```

---

## Task 16: Run Full Test Suite

**Step 1: Run all tests with coverage**

Run: `pytest tests/ -v --cov=autotrader --cov-report=term-missing`
Expected: All tests PASS, coverage report displayed

**Step 2: Fix any failures**

Address any test failures or import issues.

**Step 3: Commit**

```bash
git commit --allow-empty -m "chore: verify full test suite passes"
```

---

## Task 17: Core Module Exports

**Files:**
- Modify: `autotrader/core/__init__.py`
- Modify: `autotrader/broker/__init__.py`
- Modify: `autotrader/strategy/__init__.py`
- Modify: `autotrader/indicators/__init__.py`

**Step 1: Add clean public API exports**

```python
# autotrader/core/__init__.py
from autotrader.core.types import Bar, Signal, Order, OrderResult, Position, AccountInfo, MarketContext
from autotrader.core.event_bus import EventBus
from autotrader.core.config import Settings, load_settings
from autotrader.core.exceptions import AutoTraderError
```

```python
# autotrader/broker/__init__.py
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
```

```python
# autotrader/strategy/__init__.py
from autotrader.strategy.base import Strategy
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.registry import StrategyRegistry
```

```python
# autotrader/indicators/__init__.py
from autotrader.indicators.base import Indicator, IndicatorSpec
from autotrader.indicators.engine import IndicatorEngine
```

**Step 2: Run tests to verify nothing broke**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add autotrader/core/__init__.py autotrader/broker/__init__.py autotrader/strategy/__init__.py autotrader/indicators/__init__.py
git commit -m "feat: clean public API exports for all modules"
```

---

## Summary

| Task | Module | Tests |
|------|--------|-------|
| 1 | Project scaffolding | - |
| 2 | Core types | 6 |
| 3 | Exceptions | 2 |
| 4 | Config | 2 |
| 5 | EventBus | 5 |
| 6 | Logger | 2 |
| 7 | Broker ABC + Paper | 7 |
| 8 | Indicators | 9 |
| 9 | Strategy | 5 |
| 10 | Risk | 6 |
| 11 | Portfolio | 5 |
| 12 | Data Store | 3 |
| 13 | Backtest | 2 |
| 14 | Alpaca Adapter | 4 |
| 15 | Main entry point | 2 |
| 16 | Full test suite | - |
| 17 | Module exports | - |
| **Total** | **10 modules** | **~60 tests** |
