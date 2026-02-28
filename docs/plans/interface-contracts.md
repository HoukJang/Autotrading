# AutoTrader v3 - Interface Contracts

> Defines the exact interfaces between modules and teams.
> Author: Dev-1 (System Architect) | Date: 2026-02-27

---

## 1. Overview

This document defines the contracts between all modules in the v3 batch architecture. Every implementer (Dev-2, Dev-3, Dev-5) must conform to these interfaces. The Strategy team defines parameter values; the Dev team implements the logic.

---

## 2. ABC Contracts

### 2.1 NightlyScanner (Dev-2 implements)

```python
class NightlyScanner(ABC):
    """Scans all S&P 500 symbols, computes indicators, runs strategies."""

    @abstractmethod
    async def scan(self, symbols: list[str]) -> list[ScanResult]:
        """Run nightly batch scan on given symbols.

        Args:
            symbols: List of ticker symbols to scan (e.g., 503 S&P 500 stocks).

        Returns:
            List of ScanResult for every symbol that generated a signal.
            Empty list if no signals or scan failure after retries.

        Raises:
            ScanError: If scan fails after all retry attempts.
        """

    @abstractmethod
    async def scan_with_ranking(self, symbols: list[str]) -> BatchResult:
        """Run scan and produce ranked BatchResult.

        Combines scan() + SignalRanker.rank() + file persistence.

        Returns:
            BatchResult with top candidates and full scan summary.
        """
```

**Contract obligations:**
- Must use `IndicatorEngine` for indicator computation (do not re-implement).
- Must instantiate all 5 strategies and call `strategy.on_context(ctx)`.
- Must use `BatchFetcher` for data retrieval (IEX feed, batched).
- Must handle partial failures (some symbols fail to fetch) gracefully.
- Must produce ScanResult with `prev_close` field populated for gap filter.
- Must complete scan within 2 minutes for 503 symbols.

---

### 2.2 SignalRanker (Dev-2 implements)

```python
class SignalRanker(ABC):
    """Ranks signals and selects top candidates with sector diversification."""

    @abstractmethod
    def rank(
        self,
        scan_results: list[ScanResult],
        regime: str,
        top_n: int = 12,
        max_per_sector: int = 3,
    ) -> list[Candidate]:
        """Rank scan results and select top N candidates.

        Args:
            scan_results: Raw scan results from NightlyScanner.
            regime: Current market regime string (e.g., "TREND").
            top_n: Maximum number of candidates to select.
            max_per_sector: Maximum candidates from same GICS sector.

        Returns:
            Ranked list of Candidate objects, length <= top_n.
            Candidates include strategy-specific SL/TP multipliers and
            entry group classification (MOO or CONFIRM).
        """
```

**Contract obligations:**
- Must apply composite scoring: signal_strength * w1 + atr_ratio * w2 + regime_weight * w3 + volume * w4
- Must enforce sector diversification (max 3 per sector).
- Must map each signal's strategy to the correct EntryGroup (MOO or CONFIRM).
- Must populate sl_atr_mult, tp_atr_mult, max_hold_days from `config/strategy_params.yaml`.
- Weights are loaded from config, not hardcoded.

---

### 2.3 GapFilter (Dev-2 implements)

```python
class GapFilter(ABC):
    """Filters candidates based on pre-market price gap."""

    @abstractmethod
    async def filter(
        self,
        candidates: list[Candidate],
        gap_threshold_pct: float = 0.03,
    ) -> list[Candidate]:
        """Filter candidates by pre-market gap.

        Args:
            candidates: Candidates from ranking stage.
            gap_threshold_pct: Maximum allowed absolute gap percentage.
                Default 0.03 (3%).

        Returns:
            Filtered list of candidates that passed the gap check.
            Candidates with unavailable pre-market data are kept (fail-open).
        """
```

**Contract obligations:**
- Must fetch pre-market prices via `AlpacaAdapter.get_latest_quotes()` (to be added by Dev-2).
- If pre-market data is unavailable for a symbol, KEEP the candidate (fail-open).
- Must log rejected candidates with gap percentage and reason.
- Must save filtered results to `data/batch_results/{date}_filtered.json`.

---

### 2.4 EntryManager (Dev-3 implements)

```python
class EntryManager(ABC):
    """Manages entry execution for MOO and Confirmation groups."""

    @abstractmethod
    async def execute_moo(self, candidates: list[Candidate]) -> list[OrderResult]:
        """Execute Market-on-Open entries for Group A candidates.

        Called at 9:30 AM ET. Submits market orders for all MOO candidates
        that pass risk validation.

        Args:
            candidates: Filtered candidates with entry_group == EntryGroup.MOO.

        Returns:
            List of OrderResult for submitted orders.
        """

    @abstractmethod
    async def execute_confirmation(
        self,
        candidates: list[Candidate],
    ) -> list[OrderResult]:
        """Execute confirmation-based entries for Group B candidates.

        Called at 9:45 AM ET. Checks current price against prev_close
        to confirm direction. Enters confirmed candidates, discards rest.

        Confirmation logic:
          long  -> current_price >= prev_close
          short -> current_price <= prev_close

        Args:
            candidates: Filtered candidates with entry_group == EntryGroup.CONFIRM.

        Returns:
            List of OrderResult for confirmed and submitted orders.
        """

    @abstractmethod
    def is_entry_window_open(self) -> bool:
        """Check if entry window is still open (before 10:00 AM ET)."""
```

**Contract obligations:**
- Must validate each candidate through `RiskManager.validate()` before ordering.
- Must use `AllocationEngine.get_position_size()` for sizing.
- Must calculate SL/TP prices from actual fill price (not signal price).
- Must register filled positions with `PositionMonitor` for intraday tracking.
- Must record each entry via `TradeLogger.log_trade()`.
- Must respect max_open_positions limit (8).
- Must NOT submit any order after 10:00 AM ET.

---

### 2.5 ExitRuleEngine (Dev-3 implements)

```python
class ExitRuleEngine(ABC):
    """Evaluates exit rules for held positions."""

    @abstractmethod
    def evaluate(self, position: HeldPosition, current_bar: Bar) -> ExitDecision:
        """Evaluate all exit rules for a position against current bar.

        Rules are evaluated in strict priority order:
          1. Emergency stop: unrealized_pnl_pct <= -7% (any day)
          2. Day 1 skip: if entry_date == today (US Eastern), return HOLD
          3. Stop loss: ATR-based, strategy-specific multiplier (Day 2+)
          4. Take profit: ATR-based, strategy-specific multiplier (Day 2+)
          5. Time exit: bars_held >= max_hold_days (Day 2+)

        Args:
            position: HeldPosition with entry info and SL/TP levels.
            current_bar: Latest bar data for the position's symbol.

        Returns:
            ExitDecision with action (HOLD or EXIT) and reason string.
        """
```

**Contract obligations:**
- Rule priority is ABSOLUTE. Emergency stop always fires, regardless of day skip.
- Day 1 skip means: if position was entered TODAY (US Eastern calendar date), only emergency stop is checked. All other rules are skipped.
- SL/TP prices are pre-calculated at entry from fill_price +/- ATR * multiplier. They are stored in `HeldPosition` and do not change.
- Time exit uses calendar days held, not bar count (weekends count).
- Must return `ExitDecision(action=ExitAction.HOLD, reason="day_skip")` on entry day (unless emergency).
- Must return `ExitDecision(action=ExitAction.HOLD, reason="hold")` when no rule triggers.

---

### 2.6 PositionMonitor (Dev-3 implements)

```python
class PositionMonitor(ABC):
    """Monitors held positions via real-time bar streaming."""

    @abstractmethod
    async def start(self, positions: list[HeldPosition]) -> None:
        """Start monitoring held positions.

        Subscribes to minute bar stream for position symbols only.
        On each bar, evaluates exit rules and executes exits as needed.

        Args:
            positions: List of currently held positions to monitor.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop monitoring and clean up stream subscriptions."""

    @abstractmethod
    def add_position(self, position: HeldPosition) -> None:
        """Add a newly entered position to monitoring."""

    @abstractmethod
    def remove_position(self, symbol: str) -> None:
        """Remove a position from monitoring (after exit)."""

    @abstractmethod
    def get_held_positions(self) -> list[HeldPosition]:
        """Return list of currently monitored positions."""
```

**Contract obligations:**
- Must only stream symbols that have active positions (not all 503).
- Must update MFE/MAE tracking on every bar via `OpenPositionTracker`.
- Must call `ExitRuleEngine.evaluate()` on every bar.
- Must use `OrderManager` to execute exits.
- Must enforce re-entry block: after selling a symbol, block same-day re-entry.
- Must handle stream disconnections with auto-reconnect.
- Must log equity snapshots periodically.

---

### 2.7 OrderManager (Dev-3 implements)

```python
class OrderManager(ABC):
    """Manages order lifecycle with Alpaca broker."""

    @abstractmethod
    async def submit_entry_order(
        self,
        candidate: Candidate,
        quantity: int,
        order_type: str = "market",
    ) -> OrderResult:
        """Submit an entry order for a candidate.

        Args:
            candidate: Entry candidate with symbol, direction, etc.
            quantity: Number of shares to trade.
            order_type: Order type ("market" for MOO, "market" for confirm).

        Returns:
            OrderResult with fill information.
        """

    @abstractmethod
    async def submit_exit_order(
        self,
        position: HeldPosition,
        reason: str,
    ) -> OrderResult:
        """Submit an exit order for a held position.

        Args:
            position: Position to close.
            reason: Exit reason for logging (e.g., "stop_loss", "take_profit").

        Returns:
            OrderResult with fill information.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
```

**Contract obligations:**
- Must delegate to `AlpacaAdapter.submit_order()` for actual order placement.
- Must implement retry logic (3x with exponential backoff) on submission failure.
- Must wait for fill confirmation via `AlpacaAdapter._wait_for_fill()`.
- Must calculate and log PnL for exit orders.
- Must handle partial fills appropriately.

---

### 2.8 BatchScheduler (Dev-2 implements)

```python
class BatchScheduler(ABC):
    """Asyncio-based scheduler for batch trading events."""

    @abstractmethod
    async def start(self) -> None:
        """Start the scheduler. Runs until stop() is called."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the scheduler and cancel pending tasks."""

    @abstractmethod
    def register_task(
        self,
        name: str,
        hour: int,
        minute: int,
        callback: Callable[[], Awaitable[None]],
    ) -> None:
        """Register a task to run at a specific US Eastern time daily.

        Args:
            name: Human-readable task name for logging.
            hour: Hour in US Eastern time (0-23).
            minute: Minute (0-59).
            callback: Async callable to execute at scheduled time.
        """
```

**Contract obligations:**
- Must use `zoneinfo.ZoneInfo("US/Eastern")` for all time calculations.
- Must skip weekends and US market holidays.
- Must handle daylight saving time transitions correctly.
- Must log each task execution with timing information.
- Must implement missed-trigger detection: if system starts after a trigger time, run immediately.
- Must be idempotent: re-triggering a task should not cause duplicate operations.

---

### 2.9 BatchFetcher (Dev-2 implements)

```python
class BatchFetcher(ABC):
    """Fetches daily bars for large symbol lists from Alpaca."""

    @abstractmethod
    async def fetch_daily_bars(
        self,
        symbols: list[str],
        days: int = 120,
    ) -> dict[str, list[Bar]]:
        """Fetch daily bars for all symbols.

        Args:
            symbols: List of ticker symbols (up to 503).
            days: Number of historical days to fetch.

        Returns:
            Dict mapping symbol to list of Bar objects.
            Symbols that fail to fetch are omitted (not raised).
        """

    @abstractmethod
    async def fetch_latest_quotes(
        self,
        symbols: list[str],
    ) -> dict[str, float]:
        """Fetch latest/pre-market prices for symbols.

        Args:
            symbols: List of ticker symbols.

        Returns:
            Dict mapping symbol to latest price.
            Symbols without available quotes are omitted.
        """
```

**Contract obligations:**
- Must use IEX feed (`feed="iex"`), not SIP.
- Must batch requests in groups of 50 symbols (Alpaca limit).
- Must include rate-limit-aware delays between batches.
- Must handle partial failures: if batch N fails, continue with batch N+1.
- Must use existing `AlpacaAdapter._convert_bar()` for bar conversion.
- Must complete 503-symbol fetch within 60 seconds.

---

## 3. Inter-Team Data Contracts

### 3.1 Strategy Team -> Dev Team

The Strategy team produces specification documents and YAML configuration. The Dev team consumes these as implementation requirements.

| Data | Format | Producer | Consumer | Validation |
|------|--------|----------|----------|------------|
| SL/TP multipliers per strategy | `config/strategy_params.yaml` | Strat-2 | Dev-2 (ranking), Dev-3 (exit rules) | Must be float > 0 |
| Entry group classification | `config/strategy_params.yaml` | Strat-1 | Dev-2 (ranking), Dev-3 (entry) | Must be "MOO" or "CONFIRM" |
| Max hold days per strategy | `config/strategy_params.yaml` | Strat-1 | Dev-3 (exit rules) | Must be int 1-10 |
| Gap filter threshold | `config/strategy_params.yaml` | Strat-2 | Dev-2 (gap filter) | Must be float 0.01-0.10 |
| Ranking weights | `config/strategy_params.yaml` | Strat-2 | Dev-2 (ranking) | Must sum to ~1.0 |
| Emergency stop threshold | `config/strategy_params.yaml` | Strat-3 | Dev-3 (exit rules) | Must be float -0.01 to -0.20 |
| Regime exposure rules | `docs/strategies/regime-exposure-rules.md` | Strat-3 | Dev-2 (ranking) | Markdown spec |
| Confirmation logic | `docs/strategies/entry-rules-spec.md` | Strat-1 | Dev-3 (entry) | Markdown spec |

### 3.2 Dev Team -> Dashboard (Dev-5)

| Data | Format | Location | Producer | Consumer |
|------|--------|----------|----------|----------|
| Batch scan results | JSON | `data/batch_results/{date}.json` | Dev-2 | Dev-5 |
| Filtered candidates | JSON | `data/batch_results/{date}_filtered.json` | Dev-2 | Dev-5 |
| Trade log | JSONL | `data/live_trades.jsonl` | Dev-3 | Dev-5 |
| Equity snapshots | JSONL | `data/equity_snapshots.jsonl` | Dev-3 | Dev-5 |

Dev-5 must read these files without modifying them. Dashboard is read-only with respect to data files.

### 3.3 Dev Team -> Test Team

| Artifact | Description | Consumer |
|----------|-------------|----------|
| ABC skeleton code | ABCs in `autotrader/batch/` and `autotrader/execution/` | Test-1 writes tests against ABCs |
| Batch result JSON schema | Documented in `batch-architecture.md` section 8 | Test-1 validates output format |
| Strategy params schema | Documented in `interface-contracts.md` section 3.1 | Test-1 validates config loading |

---

## 4. Shared Type Contracts

### 4.1 Types Shared Across Teams

These types are defined in `autotrader/core/types.py` and used by all modules:

| Type | Used By | Immutable |
|------|---------|-----------|
| `Bar` | Scanner, Monitor, Exit Rules | Yes (frozen) |
| `Signal` | Scanner, Strategies | Yes (frozen) |
| `Order` | OrderManager, Broker | Yes (frozen) |
| `OrderResult` | OrderManager, EntryManager | Yes (frozen) |
| `Position` | OrderManager, EntryManager | Yes (frozen) |
| `AccountInfo` | EntryManager, RiskManager | Yes (frozen) |
| `ScanResult` | Scanner, Ranker | Yes (frozen) |
| `Candidate` | Ranker, GapFilter, EntryManager | Yes (frozen) |
| `ExitDecision` | ExitRuleEngine, PositionMonitor | Yes (frozen) |
| `BatchResult` | Scanner, Dashboard | Yes (frozen) |
| `HeldPosition` | PositionMonitor, ExitRuleEngine | No (mutable: bars_held, prices) |
| `EntryGroup` | Ranker, EntryManager | Yes (enum) |
| `ExitAction` | ExitRuleEngine | Yes (enum) |

### 4.2 Serialization Contract

All frozen dataclass types must be serializable via `dataclasses.asdict()` for JSON persistence. Enum values serialize as their string value. `datetime` fields serialize as ISO 8601 strings. `date` fields serialize as `YYYY-MM-DD` strings.

---

## 5. Error Contracts

### 5.1 Custom Exceptions

```python
class ScanError(Exception):
    """Raised when nightly scan fails after all retry attempts."""

class EntryWindowClosedError(Exception):
    """Raised when entry is attempted after 10:00 AM ET."""

class InsufficientDataError(Exception):
    """Raised when symbol has insufficient bars for indicator computation."""
```

### 5.2 Error Propagation Rules

1. **Scanner errors**: Log and continue. Failed symbols are omitted from results, not raised.
2. **Ranking errors**: If ranking fails entirely, raise `ScanError`. Partial failures in scoring are logged and the symbol is scored at 0.
3. **Gap filter errors**: If pre-market data is unavailable, KEEP all candidates (fail-open). Log warning.
4. **Entry errors**: Each order failure is independent. Failed orders are logged. Other candidates proceed.
5. **Exit errors**: Exit order failure triggers immediate retry (3x). If all retries fail, log CRITICAL and alert.
6. **Monitor errors**: Stream disconnect triggers auto-reconnect. Position state is preserved in memory.
