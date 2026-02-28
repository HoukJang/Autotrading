# AutoTrader v3 - Nightly Batch Architecture

> System architecture for the nightly batch swing trading rebuild.
> Author: Dev-1 (System Architect) | Date: 2026-02-27

---

## 1. Architecture Overview

### 1.1 Current vs Target

```
[Current v2]
  Real-time streaming 10 symbols
  -> DailyBarAggregator (minute -> daily)
  -> IndicatorEngine
  -> StrategyEngine (sequential, per-bar)
  -> RiskManager + AllocationEngine
  -> Broker order

[Target v3]
  Nightly batch scan 503 S&P 500 symbols (8 PM ET)
  -> Indicator computation (bulk, all symbols)
  -> Strategy execution (bulk, all symbols)
  -> Composite ranking -> top 12 candidates
  -> Pre-market gap filter (9:25 AM ET)
  -> Entry execution: MOO + Confirmation groups (9:30-10:00 AM ET)
  -> Position monitoring: streaming held positions only (max 8)
  -> Exit rule engine: day skip, ATR SL/TP, time exit, emergency stop
```

### 1.2 Design Principles

1. **Batch-First, Stream-Second**: The primary signal generation happens in a nightly batch scan. Intraday streaming is only for position monitoring (exit rules).
2. **Separation of Concerns**: Scanning, ranking, filtering, entry, and exit are distinct modules with clear interfaces.
3. **Reuse Existing Modules**: Strategies, indicators, and broker adapter are reused. New modules wrap and extend, never rewrite.
4. **File-Based IPC**: Batch results are persisted to JSON files. Downstream stages read from files, not in-memory state. This enables crash recovery and dashboard consumption.
5. **Idempotent Operations**: Each stage can be re-run independently. Re-running the scanner overwrites the previous result. Re-running the gap filter reads the latest scan result.
6. **Time-Zone Awareness**: All scheduled events use US Eastern time via `zoneinfo.ZoneInfo("US/Eastern")`.

---

## 2. Module Structure

```
autotrader/
    batch/
        __init__.py
        scanner.py          # NightlyScanner ABC + implementation
        scheduler.py         # BatchScheduler: asyncio time-based triggers
        ranking.py           # SignalRanker: composite score, sector diversification
        gap_filter.py        # GapFilter: pre-market price check, gap threshold

    execution/
        __init__.py
        entry_manager.py     # EntryManager: MOO (Group A) + Confirmation (Group B)
        exit_rules.py        # ExitRuleEngine: day skip, SL/TP, time exit, emergency
        position_monitor.py  # PositionMonitor: stream held positions, MFE/MAE
        order_manager.py     # OrderManager: Alpaca order lifecycle

    data/
        batch_fetcher.py     # BatchFetcher: fetch daily bars for 503 symbols (IEX)

    core/
        types.py             # EXTEND with new batch data types (additive only)
```

### 2.1 Module Dependency Graph

```
BatchScheduler
    |
    +-- triggers --> NightlyScanner
    |                   |
    |                   +-- uses --> BatchFetcher (daily bars, Alpaca REST)
    |                   +-- uses --> IndicatorEngine (existing)
    |                   +-- uses --> Strategy instances (existing)
    |                   +-- outputs --> list[ScanResult]
    |                   |
    |                   +-- feeds --> SignalRanker
    |                                   |
    |                                   +-- outputs --> BatchResult (saved to JSON)
    |
    +-- triggers --> GapFilter
    |                   |
    |                   +-- reads --> BatchResult (from JSON)
    |                   +-- fetches --> pre-market prices (Alpaca REST)
    |                   +-- outputs --> list[Candidate]
    |
    +-- triggers --> EntryManager
    |                   |
    |                   +-- reads --> list[Candidate]
    |                   +-- Group A (MOO) --> OrderManager --> Alpaca
    |                   +-- Group B (Confirm) --> price check --> OrderManager
    |
    +-- starts --> PositionMonitor
                    |
                    +-- streams --> Alpaca bar stream (held positions only)
                    +-- evaluates --> ExitRuleEngine (per bar)
                    +-- executes exits --> OrderManager --> Alpaca
```

---

## 3. Data Flow

### 3.1 Nightly Batch Scan (8:00 PM ET)

```
Input:  503 S&P 500 symbols (from SP500Provider)
        120 days of daily bars per symbol (from BatchFetcher via Alpaca REST)
        Current market regime (from RegimeDetector)

Process:
  1. BatchFetcher.fetch_daily_bars(symbols, days=120)
     -> dict[str, list[Bar]]  (batched in groups of 50, IEX feed)

  2. For each symbol with sufficient bars (>= 60):
     a. IndicatorEngine.compute(bars) -> indicators dict
     b. Build MarketContext(symbol, bar, indicators, history)
     c. For each strategy:
        strategy.on_context(ctx) -> Signal | None
     d. If signal generated, create ScanResult with indicators + score

  3. SignalRanker.rank(scan_results)
     -> Apply composite scoring (signal strength, ATR ratio, regime weight)
     -> Sector diversification (max 3 per sector)
     -> Select top 12 candidates

  4. Save BatchResult to data/batch_results/{date}.json

Output: BatchResult JSON file containing:
  - timestamp, regime, scan statistics
  - top 12 candidates with scores, strategies, indicators
  - full scan summary (503 scanned, N signals, top 12 selected)
```

### 3.2 Pre-Market Gap Filter (9:25 AM ET)

```
Input:  BatchResult from previous night's scan
        Pre-market prices for 12 candidates (Alpaca REST snapshot)

Process:
  1. Load BatchResult from data/batch_results/{date}.json
  2. Fetch latest quotes/snapshots for candidate symbols
  3. For each candidate:
     gap_pct = (pre_market_price - prev_close) / prev_close
     if abs(gap_pct) > 0.03:  # 3% threshold
         discard candidate (reason: "gap_too_large")
  4. Save filtered candidates to data/batch_results/{date}_filtered.json

Output: Filtered list[Candidate] (typically 8-12 symbols)
```

### 3.3 Entry Execution (9:30-10:00 AM ET)

```
Group A - Market-on-Open (9:30 AM):
  Strategies: Defined by entry.groups.moo in config/strategy_params.yaml
  Action: Submit market orders immediately at open
  SL/TP: Calculated from actual fill price + strategy ATR multiplier

Group B - Confirmation (9:45 AM):
  Strategies: Defined by entry.groups.confirmation in config/strategy_params.yaml
  Confirmation window: 9:30-9:45 AM
  Condition:
    long  -> current_price >= prev_close (direction confirmed)
    short -> current_price <= prev_close (direction confirmed)
  Action: Submit market order if confirmed, discard if not

10:00 AM: Entry window closes. No new entries after this point.
```

### 3.4 Position Monitoring (Intraday)

```
Input:  Held positions (max 8)
        Minute bar stream for held symbols only

Process (per bar):
  1. Update MFE/MAE tracking
  2. ExitRuleEngine.evaluate(position, bar) -> ExitDecision
     Rules evaluated in priority order:
       a. Emergency stop: unrealized loss >= emergency_stop_pct (any day, overrides all)
       b. Day 1 skip: if entry_date == today, skip SL/TP checks
       c. ATR-based stop loss: close <= entry - SL_ATR_MULT * ATR (Day 2+)
       d. ATR-based take profit: close >= entry + TP_ATR_MULT * ATR (Day 2+)
       e. Time exit: days_held >= max_hold_days (strategy-dependent)
       f. Re-entry block: no re-entry for same symbol same day after exit
  3. If ExitDecision.action == "exit":
     OrderManager.submit_exit_order(position)

Output: Trade records (LiveTradeRecord) with exit_reason, MFE/MAE
```

---

## 4. New Data Types

All new types are defined in `autotrader/core/types.py` (additive extension).

### 4.1 ScanResult

```python
@dataclass(frozen=True, slots=True)
class ScanResult:
    """Result of nightly scan for a single symbol."""
    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    strength: float              # Signal strength [0.0, 1.0]
    prev_close: float            # Previous day close (for gap filter)
    atr: float                   # ATR(14) value
    indicators: dict             # Full indicator snapshot
    metadata: dict               # Strategy-specific metadata (e.g., stop_loss)
    score: float = 0.0           # Composite score (set by SignalRanker)
```

### 4.2 EntryGroup

```python
class EntryGroup(str, Enum):
    """Entry execution group classification."""
    MOO = "MOO"           # Market-on-Open (Group A)
    CONFIRM = "CONFIRM"   # Confirmation required (Group B)
```

### 4.3 Candidate

```python
@dataclass(frozen=True, slots=True)
class Candidate:
    """Entry candidate after ranking and optional gap filtering."""
    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_group: EntryGroup
    prev_close: float
    atr: float
    sl_atr_mult: float     # Strategy-specific SL ATR multiplier
    tp_atr_mult: float     # Strategy-specific TP ATR multiplier
    score: float
    max_hold_days: int     # Strategy-specific max holding period
    metadata: dict = field(default_factory=dict)
```

### 4.4 ExitAction

```python
class ExitAction(str, Enum):
    """Exit decision action type."""
    HOLD = "HOLD"
    EXIT = "EXIT"
```

### 4.5 ExitDecision

```python
@dataclass(frozen=True, slots=True)
class ExitDecision:
    """Result of exit rule evaluation for a position."""
    action: ExitAction
    reason: str              # "stop_loss", "take_profit", "time_exit",
                             # "emergency_stop", "day_skip", "hold"
    target_price: float | None = None  # Price at which exit was triggered
```

### 4.6 RankedSignal

```python
@dataclass(frozen=True, slots=True)
class RankedSignal:
    """Signal with composite score from ranking engine."""
    scan_result: ScanResult
    composite_score: float
    rank: int
    sector: str
```

### 4.7 BatchResult

```python
@dataclass(frozen=True, slots=True)
class BatchResult:
    """Full output of a nightly batch scan."""
    timestamp: str                    # ISO format, UTC
    scan_date: str                    # YYYY-MM-DD
    regime: str                       # Current market regime
    total_symbols_scanned: int
    total_signals_generated: int
    candidates: list[Candidate]       # Top N ranked candidates
    scan_results: list[ScanResult]    # All signals (for analysis/dashboard)
    metadata: dict                    # Scan duration, errors, etc.
```

### 4.8 HeldPosition

```python
@dataclass(slots=True)
class HeldPosition:
    """Extended position info for intraday monitoring."""
    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_price: float
    entry_date: date                 # US Eastern date
    quantity: float
    sl_price: float                  # Stop loss price
    tp_price: float                  # Take profit price
    sl_atr_mult: float
    tp_atr_mult: float
    atr_at_entry: float
    max_hold_days: int
    bars_held: int = 0
    highest_price: float = 0.0
    lowest_price: float = float("inf")
    is_entry_day: bool = True
```

---

## 5. Strategy-to-Entry-Group Mapping

**IMPORTANT**: `config/strategy_params.yaml` is the sole source of truth for all strategy parameters. The table below is provided for quick reference. If there is any discrepancy between this table and the YAML file, the YAML file wins. Implementers (Dev-2, Dev-3) MUST read parameters from the YAML file, never hardcode them.

The Strategy team has provided the authoritative parameters in `config/strategy_params.yaml`. Key mappings from that file:

| Strategy            | Entry Group | SL (ATR mult) | TP (ATR mult) | Max Hold | Trailing Stop |
|---------------------|-------------|---------------|---------------|----------|---------------|
| rsi_mean_reversion  | MOO         | 2.5           | 3.0           | 5 days   | No            |
| bb_squeeze          | CONFIRM     | 2.0           | 3.0           | 5 days   | No            |
| adx_pullback        | CONFIRM     | 1.5           | 2.5           | 7 days   | Yes (2.0 ATR) |
| overbought_short    | MOO         | 2.5           | (RSI-based)   | 5 days   | No            |
| regime_momentum     | CONFIRM     | 1.5           | 3.0           | 7 days   | Yes (2.0 ATR) |

Note: The Strategy team's exit rules also include RSI-based take-profit targets and an emergency immediate threshold (10%) in addition to the emergency stop (7%). Dev-3 should consult `config/strategy_params.yaml` directly for the full exit rule specification.

---

## 6. Scheduling Architecture

### 6.1 BatchScheduler Design

The `BatchScheduler` is an asyncio-based scheduler that triggers tasks at specific US Eastern times. It runs as a long-lived coroutine.

```
Schedule (daily):
  20:00 ET  -> NightlyScanner.scan_with_ranking()
  09:25 ET  -> GapFilter.filter()
  09:30 ET  -> EntryManager.execute_moo()
  09:45 ET  -> EntryManager.execute_confirmation()
  10:00 ET  -> EntryManager.close_entry_window()

Schedule (continuous during market hours 09:30-16:00 ET):
  PositionMonitor.start()  -> runs until market close
  PositionMonitor.stop()   -> at 16:00 ET
```

### 6.2 Time Calculation

```python
def _next_trigger(hour: int, minute: int) -> datetime:
    """Calculate next trigger time in US Eastern, accounting for weekends."""
    now = datetime.now(ZoneInfo("US/Eastern"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target
```

### 6.3 Retry Policy

| Stage | Max Retries | Backoff | Fallback |
|-------|-------------|---------|----------|
| Nightly scan | 3 | 60s, 120s, 300s | Use previous day's BatchResult |
| Gap filter | 2 | 30s, 60s | Skip filter, use all candidates |
| Entry orders | 3 per order | 5s, 10s, 30s | Log and skip symbol |
| Position monitor stream | Unlimited | 5s reconnect | Auto-reconnect |

---

## 7. Configuration Design

### 7.1 config/strategy_params.yaml (Created by Strategy Team)

This file already exists and contains the authoritative strategy parameters defined by the Strategy team. It is organized into these top-level sections:

- `entry`: Gap filter, entry window times, entry groups (MOO/CONFIRM assignments), confirmation rules
- `strategies`: Per-strategy SL/TP multipliers, trailing stop, RSI targets, max hold days
- `exit`: Entry day skip, emergency stop thresholds, re-entry block
- `risk`: Position sizing, direction limits, sector concentration
- `batch`: Scan time, universe, candidate count, gap filter time

See `config/strategy_params.yaml` for the full specification. Implementers should load this file at startup and use it to configure all batch/execution behavior.

### 7.2 Integration with Existing config/default.yaml

The existing `config/default.yaml` continues to hold system-level settings (broker, risk, performance logging). The `config/strategy_params.yaml` holds all trading-logic parameters. Both are loaded at startup.

A new Pydantic model should be added to `autotrader/core/config.py` to parse `strategy_params.yaml`:

```python
class StrategyParamsConfig(BaseModel):
    sl_atr_mult: float
    tp_atr_mult: float
    max_hold_days: int
    trailing_stop: bool = False
    trailing_atr_mult: float | None = None
    # Additional RSI-based targets are strategy-specific

class BatchScheduleConfig(BaseModel):
    scan_time: str = "20:00"
    gap_filter_time: str = "09:25"
    top_candidates: int = 12
    scan_universe: str = "sp500"

class ExitRulesConfig(BaseModel):
    entry_day_skip: bool = True
    emergency_stop_pct: float = 0.07
    emergency_immediate_pct: float = 0.10
    no_same_day_reentry: bool = True
```

---

## 8. JSON File Format (Dashboard Integration)

### 8.1 BatchResult JSON Schema

File location: `data/batch_results/YYYY-MM-DD.json`

```json
{
  "timestamp": "2026-02-27T01:00:00Z",
  "scan_date": "2026-02-27",
  "regime": "TREND",
  "total_symbols_scanned": 503,
  "total_signals_generated": 47,
  "candidates": [
    {
      "symbol": "AAPL",
      "strategy": "adx_pullback",
      "direction": "long",
      "entry_group": "CONFIRM",
      "prev_close": 185.50,
      "atr": 3.25,
      "sl_atr_mult": 1.5,
      "tp_atr_mult": 2.5,
      "score": 0.87,
      "max_hold_days": 7,
      "metadata": {"adx": 32.1, "rsi": 38.5, "ema_fast": 184.2, "ema_slow": 182.8}
    }
  ],
  "scan_summary": {
    "signals_by_strategy": {
      "rsi_mean_reversion": 8,
      "bb_squeeze": 5,
      "adx_pullback": 12,
      "overbought_short": 7,
      "regime_momentum": 15
    },
    "sectors_represented": ["Technology", "Healthcare", "Finance", "Consumer"],
    "scan_duration_seconds": 95.3
  },
  "all_signals": [
    {"symbol": "AAPL", "strategy": "adx_pullback", "direction": "long", "strength": 0.72, "score": 0.87}
  ]
}
```

### 8.2 Filtered Candidates JSON

File location: `data/batch_results/YYYY-MM-DD_filtered.json`

```json
{
  "timestamp": "2026-02-27T14:25:00Z",
  "filter_date": "2026-02-27",
  "gap_threshold_pct": 0.03,
  "candidates_before": 12,
  "candidates_after": 10,
  "filtered": [
    {
      "symbol": "AAPL",
      "strategy": "adx_pullback",
      "direction": "long",
      "entry_group": "CONFIRM",
      "prev_close": 185.50,
      "pre_market_price": 186.20,
      "gap_pct": 0.0038,
      "status": "passed"
    }
  ],
  "rejected": [
    {
      "symbol": "TSLA",
      "reason": "gap_too_large",
      "gap_pct": 0.045
    }
  ]
}
```

---

## 9. Error Handling and Recovery

### 9.1 Failure Scenarios

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Alpaca API timeout during batch fetch | `asyncio.TimeoutError` | Retry batch (3x backoff), skip failed symbols |
| Nightly scan total failure | No JSON file created | Use previous day's BatchResult if exists |
| Pre-market data unavailable | Empty snapshot response | Skip gap filter, use all candidates |
| Order submission failure | `OrderResult.status == "rejected"` | Retry 3x with backoff, then skip symbol |
| Streaming disconnect | `StockDataStream` error callback | Auto-reconnect with 5s backoff, restore state |
| Partial fill on market order | `filled_qty < requested_qty` | Accept partial fill, adjust SL/TP for actual qty |
| Emergency stop triggered | Position loss >= emergency_stop_pct | Immediate market sell, override all other rules |
| Emergency immediate triggered | Position loss >= emergency_immediate_pct | Single-bar confirm, immediate market sell |
| Scheduler missed trigger | Time check: now > trigger + tolerance | Run immediately on detection |

### 9.2 State Recovery

On system restart, the `BatchScheduler` should:
1. Check if today's batch scan exists (`data/batch_results/{today}.json`)
2. If yes, skip scan and proceed to next pending stage
3. If no, and current time is past 8 PM ET, run scan immediately
4. Check position state from broker (Alpaca positions API)
5. Rebuild `HeldPosition` tracking from broker + trade log data

---

## 10. Performance Requirements

| Operation | Target | Approach |
|-----------|--------|----------|
| Fetch 503 symbols (120 days each) | < 60s | Batched requests (50 symbols per batch), IEX feed |
| Compute indicators for 503 symbols | < 30s | Sequential (IndicatorEngine is lightweight) |
| Run 5 strategies on 503 symbols | < 30s | Sequential (each strategy is O(1) per symbol) |
| Ranking + selection | < 1s | In-memory sort and filter |
| Total nightly scan | < 2 min | Sum of above |
| Gap filter | < 5s | Single batch quote request |
| Order submission | < 2s per order | Alpaca REST, max 12 orders |

---

## 11. Integration Points with Existing Modules

### 11.1 Modules Reused As-Is

| Module | Path | Usage |
|--------|------|-------|
| IndicatorEngine | `autotrader/indicators/engine.py` | Compute RSI, BB, ADX, ATR per symbol |
| Strategy classes | `autotrader/strategy/*.py` | Generate signals via `on_context()` |
| RegimeDetector | `autotrader/portfolio/regime_detector.py` | Classify market regime |
| AllocationEngine | `autotrader/portfolio/allocation_engine.py` | Position sizing |
| RiskManager | `autotrader/risk/manager.py` | Risk validation |
| TradeLogger | `autotrader/portfolio/trade_logger.py` | Trade/equity logging |
| OpenPositionTracker | `autotrader/portfolio/position_tracker.py` | MFE/MAE tracking |
| SP500Provider | `autotrader/universe/provider.py` | Fetch S&P 500 constituent list |

### 11.2 Modules Extended

| Module | Path | Extension |
|--------|------|-----------|
| AlpacaAdapter | `autotrader/broker/alpaca_adapter.py` | Add `get_latest_quotes()` method for gap filter |
| core/types.py | `autotrader/core/types.py` | Add ScanResult, Candidate, etc. (additive) |
| core/config.py | `autotrader/core/config.py` | Add batch config Pydantic models (additive) |

### 11.3 Module Replaced

| Module | Path | Replacement |
|--------|------|-------------|
| AutoTrader (main.py) | `autotrader/main.py` | Complete rewrite by Dev-3. New main orchestrates BatchScheduler + PositionMonitor instead of real-time streaming loop |

---

## 12. Concurrency Model

The system uses `asyncio` for all concurrency. No threads except where Alpaca SDK requires them.

```
Main Event Loop (asyncio)
  |
  +-- BatchScheduler coroutine (long-lived, triggers tasks at scheduled times)
  |     |
  |     +-- NightlyScanner.scan_with_ranking() (awaitable, runs at 8 PM)
  |     +-- GapFilter.filter() (awaitable, runs at 9:25 AM)
  |     +-- EntryManager.execute_moo() (awaitable, runs at 9:30 AM)
  |     +-- EntryManager.execute_confirmation() (awaitable, runs at 9:45 AM)
  |
  +-- PositionMonitor coroutine (long-lived during market hours)
  |     |
  |     +-- Alpaca StockDataStream (runs in thread via asyncio.to_thread)
  |     +-- on_bar callback -> ExitRuleEngine.evaluate() -> OrderManager
  |
  +-- Cleanup / shutdown handler
```

---

## 13. Security and Operational Considerations

1. **API Keys**: Loaded from `config/.env` (gitignored), never hardcoded.
2. **Rate Limits**: Alpaca free tier allows 200 requests/minute. BatchFetcher uses batches of 50 symbols and includes rate-limit-aware delays.
3. **Paper Mode**: All development and testing uses `paper=True`. Production switch is a config change only.
4. **Logging**: All modules use `logging.getLogger("autotrader.{module}")`. File rotation with 30-day retention (existing infrastructure).
5. **Data Retention**: Batch result files accumulate in `data/batch_results/`. A cleanup job (Dev-4 scope) will purge files older than 90 days.
