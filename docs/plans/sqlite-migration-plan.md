# SQLite State Migration Plan

**Date**: 2026-03-11
**Author**: Dev-1 (system-architect) + Dev-6 (database-expert)
**Status**: DRAFT

## 1. Problem Statement

The system uses 6+ JSON/JSONL files for runtime state persistence. This causes:

1. **MFE/MAE data loss**: `open_positions.json` is written every ~60s via atomic tmp+rename. If the process crashes between writes, up to 60 seconds of MFE/MAE tracking is lost. `runtime_state.json` saves every 5 minutes -- even worse.
2. **Split-brain reads**: Dashboard reads JSON files while autotrader writes them. No locking, no transaction isolation. Partial reads are possible.
3. **No cross-file consistency**: A position entry writes to `order_ledger.jsonl`, `live_trades.jsonl`, `open_positions.json`, and `runtime_state.json` in separate I/O operations. A crash between any two leaves the system in an inconsistent state.
4. **Append-only file growth**: `order_ledger.jsonl` and `live_trades.jsonl` grow without bound. The `compact()` method is a workaround, not a solution.

## 2. Solution: Single SQLite DB with WAL Mode

**Target**: `data/autotrader.db` (single file, WAL mode)

WAL mode provides:
- Concurrent readers (dashboard) + single writer (autotrader) without blocking
- Crash-safe commits (no partial writes, no torn pages)
- IMMEDIATE transaction mode for instant MFE/MAE persistence
- SQL query capability for dashboard analytics

## 3. StateStore Facade Design

### 3.1 Class Structure

```python
# autotrader/data/state_store.py

class StateStore:
    """Single facade for all runtime state persistence.

    Replaces:
    - open_positions.json       -> positions table
    - order_ledger.jsonl        -> orders table
    - live_trades.jsonl         -> trades table
    - equity_snapshots.jsonl    -> equity_snapshots table
    - runtime_state.json        -> component_state table
    - scheduler_state.json      -> scheduler_events table

    Usage:
        store = StateStore("data/autotrader.db")
        store.upsert_position(symbol, data_dict)
        store.close()
    """

    def __init__(self, db_path: str = "data/autotrader.db") -> None:
        ...

    def close(self) -> None:
        ...

    # --- Context Manager ---
    def __enter__(self) -> StateStore: ...
    def __exit__(self, *args) -> None: ...
```

### 3.2 Initialization

```python
def __init__(self, db_path: str = "data/autotrader.db") -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(db_path)
    self._conn.execute("PRAGMA journal_mode=WAL")
    self._conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL
    self._conn.execute("PRAGMA busy_timeout=5000")    # 5s retry on lock
    self._conn.row_factory = sqlite3.Row
    self._create_tables()
    self._conn.commit()
```

Key PRAGMA choices:
- `journal_mode=WAL`: Enables concurrent reads during writes
- `synchronous=NORMAL`: Safe with WAL (fsync on checkpoint, not every commit). Trades sub-millisecond crash window for 10x write performance.
- `busy_timeout=5000`: Dashboard reads will retry for 5 seconds instead of failing immediately

### 3.3 Position Methods (replaces open_positions.json + position_book snapshot)

```python
# --- Positions ---
def upsert_position(self, symbol: str, position: dict) -> None:
    """Insert or update a position. Commits immediately."""

def update_mfe_mae(self, symbol: str, highest_price: float, lowest_price: float) -> None:
    """Update MFE/MAE tracking fields ONLY. Immediate commit.
    This is the hot path -- called on every minute bar."""

def remove_position(self, symbol: str) -> None:
    """Delete a position row on exit."""

def load_positions(self) -> dict[str, dict]:
    """Load all positions. Used on startup and by dashboard."""

def load_position(self, symbol: str) -> dict | None:
    """Load a single position by symbol."""
```

### 3.4 Order Methods (replaces order_ledger.jsonl)

```python
# --- Orders ---
def insert_order(self, record: dict) -> None:
    """Insert a new order record."""

def update_order_state(self, order_id: str, state: str,
                        qty_filled: float = 0.0, fill_price: float = 0.0,
                        **kwargs) -> None:
    """Update order state on fill/cancel/expire."""

def load_orders(self, pending_only: bool = False) -> dict[str, dict]:
    """Load orders. If pending_only=True, only non-terminal states."""

def load_order(self, order_id: str) -> dict | None:
    """Load a single order by ID."""

def compact_orders(self, keep_hours: int = 72) -> int:
    """Delete terminal orders older than keep_hours. Returns count deleted."""
```

### 3.5 Trade Methods (replaces live_trades.jsonl)

```python
# --- Trades ---
def insert_trade(self, record: dict) -> None:
    """Insert a completed trade record."""

def load_trades(self, strategy: str | None = None,
                symbol: str | None = None) -> list[dict]:
    """Load trades with optional filters."""

def load_trades_since(self, since_iso: str) -> list[dict]:
    """Load trades since a given ISO timestamp."""
```

### 3.6 Equity Snapshot Methods (replaces equity_snapshots.jsonl)

```python
# --- Equity Snapshots ---
def insert_equity_snapshot(self, snapshot: dict) -> None:
    """Append an equity snapshot."""

def load_equity_snapshots(self) -> list[dict]:
    """Load all equity snapshots ordered by timestamp."""
```

### 3.7 Component State Methods (replaces runtime_state.json)

```python
# --- Component State ---
def save_component_state(self, component_name: str, snapshot: dict) -> None:
    """Upsert a component's snapshot blob."""

def load_component_states(self) -> dict[str, dict]:
    """Load all component states. Returns {name: snapshot_dict}."""

def save_all_component_states(self, components: dict[str, dict]) -> None:
    """Save multiple component states in a single transaction."""
```

### 3.8 Scheduler Event Methods (replaces scheduler_state.json)

```python
# --- Scheduler Events ---
def save_scheduler_state(self, state_date: str, events: dict[str, dict]) -> None:
    """Replace all scheduler events for a given date."""

def load_scheduler_state(self) -> tuple[str, dict[str, dict]]:
    """Load scheduler state. Returns (date_str, {event_name: event_dict})."""
```

### 3.9 Transaction Support

```python
# --- Transactions ---
def begin_transaction(self) -> None:
    """Begin an IMMEDIATE transaction for cross-table consistency."""
    self._conn.execute("BEGIN IMMEDIATE")

def commit(self) -> None:
    self._conn.commit()

def rollback(self) -> None:
    self._conn.rollback()
```

Usage example for atomic position entry:
```python
store.begin_transaction()
try:
    store.insert_order(order_record)
    store.upsert_position(symbol, position_data)
    store.commit()
except Exception:
    store.rollback()
    raise
```

## 4. Complete Schema

```sql
-- =================================================================
-- Table 1: positions
-- Replaces: open_positions.json + runtime_state.json[position_book]
-- Write frequency: every minute bar (MFE/MAE update)
-- =================================================================
CREATE TABLE IF NOT EXISTS positions (
    symbol          TEXT PRIMARY KEY,
    strategy        TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    entry_price     REAL NOT NULL,
    entry_atr       REAL NOT NULL DEFAULT 1.0,
    entry_date_et   TEXT NOT NULL,           -- ISO date, e.g. "2026-03-11"
    qty             REAL NOT NULL,
    bars_held       INTEGER NOT NULL DEFAULT 0,
    highest_price   REAL NOT NULL,           -- MFE tracking
    lowest_price    REAL NOT NULL,           -- MAE tracking
    consecutive_loss_bars INTEGER NOT NULL DEFAULT 0,
    entry_adx       REAL NOT NULL DEFAULT 0.0,
    entry_time      TEXT,                    -- ISO datetime, nullable
    current_price   REAL,                    -- latest known price
    unrealized_pnl  REAL,                    -- cached for dashboard
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy);


-- =================================================================
-- Table 2: orders
-- Replaces: order_ledger.jsonl
-- Write frequency: per order state transition (~5-10/day)
-- =================================================================
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    direction       TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    order_type      TEXT NOT NULL,            -- "market" / "limit" / "stop"
    order_role      TEXT NOT NULL,            -- "entry" / "exit" / "stop_loss"
    strategy        TEXT NOT NULL,
    qty_requested   REAL NOT NULL,
    qty_filled      REAL NOT NULL DEFAULT 0.0,
    fill_price      REAL NOT NULL DEFAULT 0.0,
    state           TEXT NOT NULL DEFAULT 'submitted',
    submitted_at    TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    entry_atr       REAL NOT NULL DEFAULT 0.0,
    limit_price     REAL,
    stop_price      REAL,
    sl_order_id     TEXT,
    parent_order_id TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}'   -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);


-- =================================================================
-- Table 3: trades
-- Replaces: live_trades.jsonl
-- Write frequency: per trade completion (~2-5/day)
-- =================================================================
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    direction       TEXT NOT NULL,
    side            TEXT NOT NULL,            -- "entry" / "exit" / "reconciliation_entry"
    quantity        REAL NOT NULL,
    price           REAL NOT NULL,
    pnl             REAL NOT NULL DEFAULT 0.0,
    regime          TEXT NOT NULL DEFAULT 'UNKNOWN',
    equity_after    REAL NOT NULL DEFAULT 0.0,
    metadata        TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    exit_reason     TEXT NOT NULL DEFAULT '',
    mfe             REAL NOT NULL DEFAULT 0.0,
    mae             REAL NOT NULL DEFAULT 0.0,
    bars_held       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_side ON trades(side);


-- =================================================================
-- Table 4: equity_snapshots
-- Replaces: equity_snapshots.jsonl
-- Write frequency: once per daily bar (~1/day)
-- =================================================================
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    regime          TEXT NOT NULL DEFAULT 'UNKNOWN',
    position_count  INTEGER NOT NULL DEFAULT 0,
    open_positions  TEXT NOT NULL DEFAULT '[]'   -- JSON array of symbols
);

CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_snapshots(timestamp);


-- =================================================================
-- Table 5: component_state
-- Replaces: runtime_state.json (non-position components)
-- Write frequency: every 5 minutes + on state changes
-- =================================================================
CREATE TABLE IF NOT EXISTS component_state (
    component_name  TEXT PRIMARY KEY,
    snapshot        TEXT NOT NULL,            -- JSON blob of component state
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =================================================================
-- Table 6: scheduler_events
-- Replaces: scheduler_state.json
-- Write frequency: per scheduler event (~6-8/day)
-- =================================================================
CREATE TABLE IF NOT EXISTS scheduler_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    state_date      TEXT NOT NULL,            -- ISO date this state belongs to
    event_name      TEXT NOT NULL,
    fired_at        TEXT NOT NULL,
    result          TEXT NOT NULL DEFAULT 'success',
    target_date     TEXT NOT NULL DEFAULT '',
    UNIQUE(state_date, event_name)
);

CREATE INDEX IF NOT EXISTS idx_scheduler_date ON scheduler_events(state_date);
```

### 4.1 Schema Design Rationale

**positions table**:
- `symbol` is PRIMARY KEY (only one position per symbol at a time, enforced by PositionBook)
- `highest_price`/`lowest_price` are NOT NULL -- the hot path for MFE/MAE updates
- `current_price` and `unrealized_pnl` are cached fields for dashboard reads (eliminates the need for `_dump_open_positions` to recompute)
- `updated_at` auto-stamps on every write

**orders table**:
- `order_id` is PRIMARY KEY (Alpaca order IDs are unique)
- Uses UPDATE instead of append-only JSONL -- each order has exactly one row
- `state` index supports fast `WHERE state IN ('submitted','pending_fill','partially_filled')` queries

**trades table**:
- AUTOINCREMENT preserves insertion order (matches JSONL append behavior)
- Timestamp index enables efficient "today's trades" queries for daily PnL
- `side` index supports filtering entry vs exit records

**component_state table**:
- Key-value design: each component gets one row with its JSON blob
- Replaces the monolithic `runtime_state.json` -- individual components can be updated independently
- Components: `gdr_manager`, `risk_manager`, `entry_manager`, `exit_rules`

**scheduler_events table**:
- UNIQUE constraint on `(state_date, event_name)` prevents duplicate firing
- Replaces the nested JSON structure with flat rows for simpler queries

## 5. Migration Phases

### Phase 1: StateStore Foundation (no callers changed)

**Goal**: Create `StateStore` class with full schema and API. No existing code is modified.

**Files to create**:
- `autotrader/data/state_store.py` -- StateStore class
- `tests/unit/test_state_store.py` -- Unit tests for all StateStore methods

**Acceptance criteria**:
- All 6 tables are created correctly
- WAL mode is verified
- CRUD operations work for each table
- Transaction support (begin/commit/rollback) works
- Concurrent reader test passes (one connection writes, another reads)
- All existing tests still pass (no changes to existing code)

### Phase 2: Position Persistence (highest value, biggest risk reduction)

**Goal**: Replace `open_positions.json` and `position_book` snapshot in `runtime_state.json` with `positions` table.

**Files to modify**:
- `autotrader/main.py`:
  - `_setup_components()`: Initialize `StateStore` instance
  - `_dump_open_positions()`: Write to `positions` table instead of JSON
  - `_load_existing_positions()`: Read from `positions` table (fallback to JSON)
  - `_on_bar()`: Call `store.update_mfe_mae()` on every minute bar (IMMEDIATE commit)
  - `_reconcile_positions()`: Update positions table on add/remove
  - All `_position_book.add()` / `_position_book.remove()` call sites: Also update positions table
- `autotrader/trading/position_book.py`:
  - Add optional `StateStore` dependency injection
  - `add()`: Also calls `store.upsert_position()` if store is set
  - `remove()`: Also calls `store.remove_position()` if store is set
  - `update_prices()`: Also calls `store.update_mfe_mae()` if store is set
  - `to_snapshot()` / `from_snapshot()`: Continue working for backward compat

**Migration strategy**:
- On startup: Try `positions` table first. If empty, fall back to `open_positions.json` + `runtime_state.json` and migrate data into the table.
- Dual-write during Phase 2: Write to both DB and JSON for 1 week of paper trading
- After validation: Remove JSON writes (Phase 2b)

**Key change -- MFE/MAE hot path**:
```python
# BEFORE (in _on_bar, called every minute):
self._position_book.update_prices(symbol, bar.high, bar.low, bar.close)
# (MFE/MAE only persisted when _dump_open_positions runs every ~60s)

# AFTER:
self._position_book.update_prices(symbol, bar.high, bar.low, bar.close)
self._state_store.update_mfe_mae(symbol, held.highest_price, held.lowest_price)
# (committed to SQLite immediately -- sub-millisecond)
```

### Phase 3: Order Ledger Migration

**Goal**: Replace `order_ledger.jsonl` with `orders` table.

**Files to modify**:
- `autotrader/execution/order_ledger.py`:
  - Add `StateStore` as optional backend
  - `_append()`: Write to DB instead of JSONL append
  - `load()`: Read from DB instead of replaying JSONL
  - `compact()`: Use `DELETE WHERE` instead of file rewrite
  - Keep in-memory `_orders` dict for fast lookups (SQLite is the persistence layer, dict is the cache)

**Migration strategy**:
- On startup: If `orders` table is empty but `order_ledger.jsonl` exists, bulk-import all records
- Dual-write for 1 week, then remove JSONL writes

### Phase 4: Trade Log + Equity Snapshots

**Goal**: Replace `live_trades.jsonl` and `equity_snapshots.jsonl`.

**Files to modify**:
- `autotrader/portfolio/trade_logger.py`:
  - `log_trade()`: Insert into `trades` table
  - `log_equity()`: Insert into `equity_snapshots` table
  - `read_trades()`: Query from DB
  - `read_equity()`: Query from DB
- `autotrader/data/live_store.py`:
  - **Consolidate into StateStore**: The existing `LiveDataStore` already has `trades` and `equity_snapshots` tables. Merge its schema into StateStore and deprecate `LiveDataStore`.
  - Keep `regime_history` and `rotation_events` tables in StateStore (add to schema)

**Migration strategy**:
- Bulk-import existing JSONL data on first startup with new code
- Dual-write for 1 week

### Phase 5: Component State + Scheduler

**Goal**: Replace `runtime_state.json` and `scheduler_state.json`.

**Files to modify**:
- `autotrader/state/runtime_state.py`:
  - `save()`: Write each component to `component_state` table
  - `load()`: Read from `component_state` table
  - Keep atomic JSON fallback for 1 release cycle
- `autotrader/scheduling/state.py`:
  - `save()`: Write to `scheduler_events` table
  - `load()`: Read from `scheduler_events` table
  - `mark_fired()`: INSERT OR REPLACE into `scheduler_events`

**Migration strategy**:
- These are low-risk (small data, infrequent writes)
- Direct cutover with JSON fallback on read

### Phase 6: Dashboard Integration + File Removal

**Goal**: Dashboard reads exclusively from SQLite. Remove all JSON file I/O.

**Files to modify**:
- `autotrader/dashboard/data_loader.py`:
  - `load_trades()`: Query `trades` table
  - `load_equity()`: Query `equity_snapshots` table
  - `load_open_positions()`: Query `positions` table
  - `compute_risk_metrics()`: Use SQL aggregates where beneficial
  - Remove all JSONL parsing code
- `autotrader/main.py`:
  - Remove `_dump_open_positions()` entirely
  - Remove `open_positions.json` supplementation logic in `_load_existing_positions()`
  - Remove dual-write code added in Phases 2-5

**Files to delete** (after 2-week validation):
- `data/open_positions.json`
- `data/state/runtime_state.json`
- `data/order_ledger.jsonl`
- `data/live_trades.jsonl`
- `data/equity_snapshots.jsonl`
- `data/scheduler_state.json`

## 6. Dashboard Integration Details

### 6.1 Current Flow (JSON-based)

```
AutoTrader writes JSON files -> Dashboard reads JSON files (with st.cache_data TTL=30s)
```

Problems:
- Dashboard can read a half-written file (atomic rename helps but not guaranteed on Windows)
- Streamlit's `st.cache_data` re-parses the entire JSONL file every 30 seconds
- No query capability -- everything loaded into memory

### 6.2 New Flow (SQLite-based)

```
AutoTrader writes to autotrader.db -> Dashboard reads from autotrader.db (WAL mode)
```

The dashboard opens its own `sqlite3.connect("data/autotrader.db")` connection with read-only intent.

**data_loader.py changes**:

```python
# New helper: get a read-only connection
def _get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect("data/autotrader.db", timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")  # ensures WAL if not yet set
    conn.row_factory = sqlite3.Row
    return conn

# Replace load_trades():
@st.cache_data(ttl=30)
def load_trades(db_path: str = "data/autotrader.db") -> pd.DataFrame:
    conn = _get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY id", conn)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
        return df if not df.empty else pd.DataFrame(columns=_TRADE_COLUMNS)
    finally:
        conn.close()

# Replace load_equity():
@st.cache_data(ttl=30)
def load_equity(db_path: str = "data/autotrader.db") -> pd.DataFrame:
    conn = _get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM equity_snapshots ORDER BY id", conn)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
        return df if not df.empty else pd.DataFrame(columns=_EQUITY_COLUMNS)
    finally:
        conn.close()

# Replace load_open_positions():
@st.cache_data(ttl=15)
def load_open_positions(db_path: str = "data/autotrader.db") -> dict[str, dict]:
    conn = _get_db_connection()
    try:
        cursor = conn.execute("SELECT * FROM positions")
        return {row["symbol"]: dict(row) for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return {}  # Table doesn't exist yet (pre-migration)
    finally:
        conn.close()
```

### 6.3 Backward Compatibility During Migration

During Phases 2-5 (dual-write period), `data_loader.py` uses a fallback pattern:

```python
def load_trades(...) -> pd.DataFrame:
    # Try SQLite first
    db_path = Path("data/autotrader.db")
    if db_path.exists():
        try:
            return _load_trades_from_db(db_path)
        except Exception:
            logger.warning("DB read failed, falling back to JSONL")
    # Fallback to JSONL
    return _load_trades_from_jsonl(jsonl_path)
```

## 7. Relationship to Existing LiveDataStore

`autotrader/data/live_store.py` already has a `trades` and `equity_snapshots` table but is NOT used by `main.py`. It was built as a parallel analytics store.

**Decision**: Absorb `LiveDataStore`'s tables (`trades`, `equity_snapshots`, `regime_history`, `rotation_events`) into `StateStore`. `LiveDataStore` becomes deprecated.

The `regime_history` and `rotation_events` tables will be added to the StateStore schema as-is (they are already well-designed). Their methods from `LiveDataStore` are moved to `StateStore`.

## 8. Rollback Plan

### Per-Phase Rollback

Each phase maintains backward compatibility:

1. **Phase 1**: No callers changed. Rollback = delete `state_store.py`.
2. **Phase 2-5**: Dual-write mode means JSON files are always current. Rollback = revert the modified files. JSON data is intact.
3. **Phase 6**: This is the point of no return. Before entering Phase 6:
   - Paper trade for 2+ weeks with dual-write
   - Verify DB data matches JSON data (automated comparison test)
   - Take a manual backup of all JSON files

### Emergency Rollback Procedure

If a crash or data corruption is discovered after Phase 6:

1. Stop autotrader
2. `git revert` the Phase 6 commit (restores JSON read paths)
3. If DB is corrupted: `sqlite3 data/autotrader.db ".recover" | sqlite3 data/autotrader_recovered.db`
4. Export DB data to JSON files using a recovery script (to be written in Phase 1)
5. Restart autotrader

### Data Backup

Add to the nightly scheduler (post-nightly_scan):
```python
import shutil
shutil.copy2("data/autotrader.db", f"data/backups/autotrader_{date}.db")
```

WAL checkpoint before backup:
```python
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

## 9. Testing Strategy

### 9.1 Unit Tests (Phase 1)

File: `tests/unit/test_state_store.py`

```
TestStateStoreInit
    test_creates_db_file
    test_wal_mode_enabled
    test_tables_created
    test_idempotent_init (call __init__ twice on same file)

TestPositions
    test_upsert_position
    test_update_mfe_mae
    test_remove_position
    test_load_positions_empty
    test_load_positions_with_data
    test_load_single_position
    test_upsert_overwrites_existing
    test_updated_at_changes_on_write

TestOrders
    test_insert_order
    test_update_order_state
    test_load_pending_orders
    test_load_all_orders
    test_compact_orders
    test_duplicate_order_id_rejected

TestTrades
    test_insert_trade
    test_load_trades_filtered
    test_load_trades_since
    test_trades_ordered_by_insertion

TestEquitySnapshots
    test_insert_snapshot
    test_load_snapshots_ordered

TestComponentState
    test_save_and_load_component
    test_save_all_components_transactional
    test_upsert_overwrites

TestSchedulerEvents
    test_save_and_load_scheduler_state
    test_unique_constraint_per_date_event

TestTransactions
    test_commit_persists
    test_rollback_reverts
    test_cross_table_transaction

TestConcurrency
    test_reader_during_write (WAL concurrent read)
    test_busy_timeout
```

### 9.2 Integration Tests (Phase 2+)

File: `tests/integration/test_state_store_migration.py`

```
TestJSONToDBMigration
    test_positions_json_imported_to_db
    test_order_ledger_jsonl_imported_to_db
    test_trades_jsonl_imported_to_db
    test_equity_snapshots_imported_to_db
    test_runtime_state_components_imported
    test_scheduler_state_imported

TestDualWrite
    test_position_written_to_both_db_and_json
    test_data_matches_between_db_and_json

TestDashboardReads
    test_dashboard_reads_from_db
    test_dashboard_fallback_to_json_when_no_db
```

### 9.3 MFE/MAE Specific Tests

File: `tests/unit/test_mfe_mae_persistence.py`

```
TestMFEMAEPersistence
    test_mfe_survives_simulated_crash
    test_mae_survives_simulated_crash
    test_mfe_mae_updated_on_every_bar
    test_mfe_mae_values_match_position_book
    test_position_restored_with_correct_mfe_mae
```

### 9.4 Existing Test Compatibility

All 1865 existing tests must continue passing. The StateStore is additive in Phases 1-5. Phase 6 modifies `data_loader.py` which has dashboard tests that will need updating.

## 10. Performance Considerations

### Write Performance

| Operation | JSON (current) | SQLite WAL |
|-----------|----------------|------------|
| MFE/MAE update | ~2ms (full file rewrite) | ~0.1ms (single row UPDATE) |
| Position dump (5 positions) | ~5ms (serialize + fsync) | ~0.5ms (5 UPDATEs) |
| Order state transition | ~1ms (append + fsync) | ~0.1ms (UPDATE) |
| Trade log | ~1ms (append + fsync) | ~0.1ms (INSERT) |

### Read Performance

| Operation | JSON (current) | SQLite WAL |
|-----------|----------------|------------|
| Load all positions | ~2ms (parse JSON) | ~0.1ms (SELECT *) |
| Load today's trades | ~50ms (parse all JSONL + filter) | ~0.1ms (indexed query) |
| Dashboard full refresh | ~100ms (parse 3 files) | ~1ms (3 queries) |

### DB Size Estimate

After 1 year of trading (~250 trading days):
- positions: ~10 rows (current positions, transient)
- orders: ~2500 rows (after compaction) = ~500 KB
- trades: ~1500 rows = ~200 KB
- equity_snapshots: ~250 rows = ~50 KB
- component_state: ~5 rows = ~5 KB
- scheduler_events: ~1500 rows = ~100 KB
- Total: < 1 MB (trivial)

## 11. Implementation Notes

### Thread Safety

The autotrader runs in a single asyncio event loop, but `TradeLogger` uses a threading lock for cross-thread writes. StateStore should also use a threading lock for write operations:

```python
self._write_lock = threading.Lock()

def upsert_position(self, symbol: str, position: dict) -> None:
    with self._write_lock:
        self._conn.execute(...)
        self._conn.commit()
```

Dashboard reads use separate connections (each `sqlite3.connect()` call creates a new connection), so they don't need the lock.

### Windows-Specific Concerns

- SQLite WAL mode works on Windows but WAL file deletion on close requires all connections to be closed first
- `os.replace()` (used by current JSON atomic writes) has edge cases on Windows with open file handles. SQLite handles this internally.
- Ensure `busy_timeout` is set on dashboard connections too, in case the autotrader is doing a long write

### Migration Data Import

When the autotrader starts and finds an empty DB but existing JSON files:

```python
def _migrate_from_json(self) -> None:
    """One-time migration: import JSON/JSONL data into SQLite tables."""
    # Only runs if positions table is empty AND open_positions.json exists
    # Each file migration is wrapped in its own transaction
    # A migration_complete flag is set in component_state to prevent re-running
```

This runs once, automatically, on the first startup after the code is deployed.

## 12. File Summary

### New Files
| File | Phase | Description |
|------|-------|-------------|
| `autotrader/data/state_store.py` | 1 | StateStore facade class |
| `tests/unit/test_state_store.py` | 1 | Unit tests |
| `tests/unit/test_mfe_mae_persistence.py` | 2 | MFE/MAE crash safety tests |
| `tests/integration/test_state_store_migration.py` | 2 | Migration tests |

### Modified Files
| File | Phase | Changes |
|------|-------|---------|
| `autotrader/main.py` | 2, 6 | Init StateStore, wire MFE/MAE hot path, remove `_dump_open_positions` |
| `autotrader/trading/position_book.py` | 2 | Optional StateStore injection for write-through |
| `autotrader/execution/order_ledger.py` | 3 | StateStore backend for orders |
| `autotrader/portfolio/trade_logger.py` | 4 | StateStore backend for trades + equity |
| `autotrader/state/runtime_state.py` | 5 | StateStore backend for component state |
| `autotrader/scheduling/state.py` | 5 | StateStore backend for scheduler events |
| `autotrader/dashboard/data_loader.py` | 6 | SQL queries instead of JSON parsing |
| `autotrader/data/live_store.py` | 4 | Deprecated (absorbed into StateStore) |

### Deleted Files (Phase 6, after validation)
| File | Replaced By |
|------|-------------|
| `data/open_positions.json` | `positions` table |
| `data/state/runtime_state.json` | `component_state` table |
| `data/order_ledger.jsonl` | `orders` table |
| `data/live_trades.jsonl` | `trades` table |
| `data/equity_snapshots.jsonl` | `equity_snapshots` table |
| `data/scheduler_state.json` | `scheduler_events` table |

## 13. Phase Execution Timeline

| Phase | Scope | Estimated Effort | Risk |
|-------|-------|-----------------|------|
| Phase 1 | StateStore class + tests | 1 session | None (additive) |
| Phase 2 | Positions (MFE/MAE fix) | 1-2 sessions | Medium (hot path change) |
| Phase 3 | Order ledger | 1 session | Low |
| Phase 4 | Trades + equity + LiveDataStore merge | 1 session | Low |
| Phase 5 | Component state + scheduler | 1 session | Low |
| Phase 6 | Dashboard + cleanup | 1 session | Medium (removes fallbacks) |

**Total**: 6-8 sessions, spread across 2-3 weeks of paper trading validation.

Phase 2 should be deployed first and run in dual-write mode during live paper trading. This immediately fixes the MFE/MAE persistence gap (the primary motivation). Phases 3-5 can follow at any pace. Phase 6 is the final cutover after validating data consistency.
