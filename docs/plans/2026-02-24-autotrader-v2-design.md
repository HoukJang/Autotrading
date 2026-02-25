# AutoTrader v2 - System Design

## Overview

Complete rebuild of the autotrading system targeting US equities via Alpaca API.
Monolithic event-driven architecture with plugin-based strategy system.

## Decisions

| Item | Decision |
|------|----------|
| Language | Python 3.11+ |
| Architecture | Monolithic event-driven (gradual separation possible) |
| Broker | Alpaca API (abstracted via BrokerAdapter ABC) |
| Market | US Equities |
| Strategy | Plugin system, added later |
| Indicators | Hybrid (shared IndicatorEngine + strategy-internal custom) |
| Database | SQLite (dev) / PostgreSQL (production) |
| Backtest | Same code as live, broker swap only |
| Risk | Config-driven rule engine |
| Legacy code | None, clean slate |

## Module Structure

```
autotrader/
  core/          # Event bus, config, logging, types, exceptions
  broker/        # BrokerAdapter ABC + Alpaca/Paper implementations
  data/          # Real-time feed, bar builder, history, data store
  indicators/    # Indicator ABC + built-in indicators (MA, RSI, ATR, etc.)
  strategy/      # Strategy ABC + registry + execution engine
  risk/          # Risk manager, position sizer
  portfolio/     # Portfolio tracker, performance metrics
  backtest/      # Backtest engine, simulator, reports
tests/
  unit/
  integration/
config/
  default.yaml
  .env.example
docs/plans/
```

## Data Flow

```
Alpaca WebSocket
      |
  [DataFeed] --bar--> [EventBus]
                          |
                    [IndicatorEngine] -- compute shared indicators
                          |
                    [MarketContext] -- { bar + indicators + history }
                          |
                    [StrategyEngine] --broadcast--> [Strategy A]
                                                    [Strategy B]
                                                    [Strategy N]
                                                        |
                                                   Signal generation
                                                        |
                                                   [RiskManager] -- validate
                                                        |
                                                   [BrokerAdapter] -- execute order
                                                        |
                                                   [PortfolioTracker] -- update state
```

## Core Interfaces

### BrokerAdapter (ABC)

```python
class BrokerAdapter(ABC):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def submit_order(self, order: Order) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_account(self) -> AccountInfo: ...
    async def subscribe_bars(self, symbols: list[str], callback: Callable) -> None: ...
```

### Strategy (ABC)

```python
class Strategy(ABC):
    name: str
    required_indicators: list[IndicatorSpec]

    def on_context(self, ctx: MarketContext) -> Signal | None: ...
    def on_order_filled(self, fill: OrderFill) -> None: ...     # optional
    def on_position_update(self, pos: Position) -> None: ...    # optional
```

### Indicator (ABC)

```python
class Indicator(ABC):
    name: str
    warmup_period: int

    def calculate(self, bars: deque[Bar]) -> float | dict: ...
    def reset(self) -> None: ...
```

### Core Data Types

```python
@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Signal:
    strategy: str
    symbol: str
    direction: Literal["long", "short", "close"]
    strength: float          # 0.0 ~ 1.0
    metadata: dict = field(default_factory=dict)

@dataclass
class Order:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    order_type: Literal["market", "limit", "stop"]
    limit_price: float | None = None
    stop_price: float | None = None

@dataclass
class MarketContext:
    symbol: str
    bar: Bar
    indicators: dict[str, float | dict]
    history: deque[Bar]
```

## Indicator System (Hybrid)

- **Shared indicators**: Computed once by IndicatorEngine, shared across all strategies
- **Strategy-specific**: Each strategy computes its own custom logic internally
- Strategies declare `required_indicators` to request shared indicators
- IndicatorEngine aggregates requirements and computes only what's needed

## Risk Management

Config-driven validation pipeline:
- Per-symbol max position ratio (e.g., 10% of account)
- Daily loss limit (e.g., 2% of account)
- Max drawdown limit (e.g., 5% of account)
- Max concurrent open positions
- All values configurable via `config/default.yaml`

## Backtest Engine

- Uses identical Strategy, IndicatorEngine, RiskManager code as live
- Swaps `AlpacaAdapter` with `SimulatedBroker` (implements BrokerAdapter)
- Performance report: Sharpe, Sortino, Max DD, Win rate, Profit factor
- Point-in-Time data access guarantee

## Database

- `DataStore` ABC with `SQLiteStore` (dev) and `PostgreSQLStore` (production)
- Stores: bars, trades, performance metrics, system events
