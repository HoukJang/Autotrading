# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🏷️ Quick Reference Tags

| Tag | Description | Section |
|-----|-------------|---------|
| `#policy` | Project governance and development policies | [Project Policies](#project-policies) |
| `#security` | Security guidelines and sensitive data handling | [Security Guidelines](#security-guidelines) |
| `#workflow` | Development workflow and file management | [Development Workflow](#development-workflow) |
| `#architecture` | System architecture and component overview | [Architecture Overview](#architecture-overview) |
| `#commands` | Development commands and tooling | [Development Commands](#development-commands) |
| `#database` | Database schema and data handling | [Database Schema](#database-schema) |
| `#tables` | Table structures and relationships | [Table Definitions](#table-definitions) |
| `#indexes` | Performance indexes and constraints | [Performance Optimization](#performance-optimization) |
| `#queries` | Common database operations and examples | [Common Operations](#common-operations) |
| `#monitoring` | Database monitoring and status tracking | [System Monitoring](#system-monitoring) |

---

## 📋 Project Policies

### Communication Policy `#policy`
- **Korean for dialogue**: All conversations with user in Korean
- **English for documentation**: All documentation, comments, and internal thoughts in English
- **Code comments**: Korean docstrings and comments for better understanding

### File Management Policy `#policy` `#workflow`
- **Minimize file count**: Always prefer updating existing files over creating new ones
- **Update-only approach**: Avoid file proliferation, consolidate functionality
- **File organization**: Use existing directory structure, avoid deep nesting

### Incremental Work Policy `#policy` `#workflow`
- **Small units**: Break down work into clear, manageable steps
- **Step-by-step progression**: Complete one unit before moving to next
- **Validation after each step**: Ensure each increment works before proceeding

### Tool Usage Restrictions `#policy` `#workflow`
- **Explain Only Mode**: `/sc:explain`, `explain` 키워드 사용 시 **절대 코드 생성 금지**
- **Analysis Tools Only**: Read, Grep, Glob만 사용하여 현황 파악
- **No Creation**: Write, Edit, MultiEdit, TodoWrite 등 파일 변경 도구 사용 금지
- **Description Focus**: 문제 원인, 해결 방법, 개념 설명에만 집중

### Command Type Detection `#workflow`
```yaml
explain_triggers:
  - "/sc:explain"
  - "explain", "설명", "어떻게", "왜", "원인"
  - "what is", "how does", "why"

implement_triggers:
  - "만들어", "생성", "구현", "추가"
  - "create", "implement", "add", "build"
  - "fix", "solve", "해결"
```

### Violation Prevention `#policy`
- **Stop and Ask**: 설명 요청에서 구현 충동 느끼면 명시적으로 구현 여부 확인
- **Read-Only Mode**: 설명 모드에서는 현황 분석만, 수정 작업 절대 금지
- **Clear Boundaries**: "설명만 원하시나요? 구현도 필요하신가요?" 같은 확인 질문

### Response Examples `#workflow`
```
❌ Wrong (설명 요청인데 코드 생성):
"이 오류를 해결하기 위해 파일을 만들겠습니다..."

✅ Right (설명만):
"이 오류는 모듈이 없어서 발생합니다. 해결하려면:
1) autotrading/database/ 디렉토리 생성
2) __init__.py 생성
3) connection.py 모듈 파일 생성이 필요합니다."
```

### Documentation Structure Policy `#policy`
- **Central reference document**: This CLAUDE.md serves as main entry point
- **Linked documentation**: Other documents referenced through tags and links
- **Easy content discovery**: Tag system for quick navigation
- **Living documentation**: Regular updates as project evolves

---

## 🔒 Security Guidelines `#security`

### Sensitive Data Handling
- **Never commit**: API keys, tokens, passwords, connection strings
- **Environment variables**: Use `.env` files (gitignored) for sensitive config
- **Placeholder patterns**: Use `YOUR_API_KEY_HERE` in documentation
- **Security checks**: Always review code for hardcoded credentials before commits

### API Security
- **Schwab API**: OAuth tokens and refresh tokens must be environment-based
- **Database**: Connection strings and credentials in environment variables
- **Logging**: Never log sensitive authentication data

---

## 🔄 Development Workflow `#workflow`

### Testing Strategy `#commands`
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_core.py

# Run with coverage
pytest --cov=autotrading tests/
```

### Code Quality `#commands`
```bash
# Format code (line length 100)
black autotrading/ tests/

# Lint code
ruff check autotrading/ tests/

# Fix auto-fixable issues
ruff check --fix autotrading/ tests/
```

### Development Setup `#commands`
```bash
# Install development dependencies
pip install -e ".[dev]"

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

### Development Guidelines `#policy` `#workflow`

#### Incremental Development Policy `#policy`
- **Create Before Import**: 임포트하는 모듈을 먼저 생성한 후 사용하는 코드 작성
- **Module Dependency Check**: 새 파일 생성 시 모든 임포트가 존재하는지 확인
- **Runnable State Maintenance**: 각 단계에서 실행 가능한 상태 유지
- **Missing Module Detection**: 실행 전 `python -m py_compile` 로 문법/임포트 오류 사전 확인

#### File Creation Order `#workflow`
```
1. 디렉토리 구조 생성
2. __init__.py 파일 생성
3. 종속성이 없는 하위 모듈부터 생성
4. 상위 모듈에서 하위 모듈 임포트
5. 실행 테스트 후 다음 단계
```

#### Import Validation `#workflow`
- **Before Creation**: 새 파일에서 임포트할 모듈들이 존재하는지 확인
- **After Creation**: `python -c "import autotrading.module.name"` 으로 임포트 테스트
- **Dependency Mapping**: 복잡한 의존성의 경우 종속성 그래프 작성

#### Error Prevention Commands `#commands`
```bash
# 임포트 오류 사전 확인
python -m py_compile autotrading/core/context.py

# 모듈 임포트 테스트
python -c "from autotrading.core.context import create_shared_context"

# 전체 패키지 문법 검사
python -m compileall autotrading/
```

---

## 🏗️ Architecture Overview `#architecture`

### System Design Philosophy
- **Live trading focus**: Real trading without paper simulation
- **UTC standardization**: All timestamps in UTC, 1-minute intervals
- **Dependency injection**: SharedContext pattern for resource management
- **Modular components**: Loosely coupled, testable components

### Core Components `#architecture`
```
SharedContext (Protocol)
├── Database connection pool
├── Schwab API client
├── Configuration dictionary
└── Logger instance

DataCollector → Market data ingestion and storage
Analyzer → Technical analysis and signal generation
Trader → Order execution and portfolio management
Backtester → Historical strategy validation
```

### Data Flow `#architecture` `#database`
1. User provides symbol list → DataCollector fetches latest bars
2. Data validation via `validate_minute_bars()` (UTC, no gaps, no NaN)
3. Storage with UPSERT conflict resolution (symbol, timestamp)
4. Analyzer computes signals from stored data
5. Trader executes orders based on signals
6. Status tracking in database for monitoring

---

## 🗄️ Database Schema `#database`

The Autotrading system uses PostgreSQL 17.4 with a focus on time-series data optimization and real-time trading operations. The schema is designed for high-frequency data ingestion and efficient querying of market data.

### Recent Schema Improvements `#database`
- **Timestamp Column Clarity**: Renamed confusing timestamp columns for better developer experience
  - `updated_at` → `record_modified_at` (database record changes)
  - `last_updated` → `market_data_refreshed_at` (external API data sync)
- **Enhanced Indexing**: Added optimized indexes for data freshness queries

### Database Design Principles `#database`
- **UTC standardization**: All timestamps stored in UTC timezone with 1-minute precision
- **UPSERT strategy**: Conflict resolution for duplicate data ingestion
- **Time-series optimization**: Indexes optimized for time-range queries
- **JSONB flexibility**: Extensible metadata storage for system components
- **Data integrity**: Constraints ensure data quality and consistency

### tickers Table - Stock Symbol Management `#tables`

**Purpose**: Manages stock symbols with intelligent lifecycle tracking and market data freshness

```sql
CREATE TABLE tickers (
    symbol TEXT NOT NULL,                            -- Stock symbol (e.g., 'AAPL', 'MSFT')
    is_active BOOLEAN DEFAULT true,                  -- Active status (delisting detection)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Initial creation timestamp
    record_modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Database record changes
    market_data_refreshed_at TIMESTAMPTZ,           -- Last successful API data sync
    exchange TEXT,                                   -- Trading exchange

    -- Market Data Fields
    last_price NUMERIC(18,8),                       -- Most recent price
    market_cap NUMERIC(28,8),                       -- Market capitalization
    pe_ratio NUMERIC(10,4),                         -- Price-to-earnings ratio
    dividend_yield NUMERIC(8,4),                    -- Dividend yield percentage
    beta NUMERIC(8,4),                              -- Beta coefficient
    avg_volume_30d NUMERIC(28,8),                   -- 30-day average volume

    PRIMARY KEY (symbol)
);
```

**Key Features**:
- **Intelligent Timestamp Tracking**: Clear distinction between record changes and data freshness
- **Delisting Detection**: Automated lifecycle management via `is_active` flag
- **Data Quality Validation**: Built-in constraints and monitoring for market data integrity
- **Batch Processing Optimization**: Indexes optimized for API rate-limited operations

---

## 📊 Table Definitions `#tables`

### candles Table - OHLCV Market Data `#tables`

**Purpose**: Stores 1-minute candlestick data for all traded symbols

```sql
CREATE TABLE candles (
    symbol TEXT NOT NULL,                    -- Stock symbol (e.g., 'AAPL', 'MSFT')
    ts TIMESTAMPTZ NOT NULL,                -- UTC timestamp (minute precision)
    open NUMERIC(18,8) NOT NULL,            -- Opening price
    high NUMERIC(18,8) NOT NULL,            -- Highest price during period
    low NUMERIC(18,8) NOT NULL,             -- Lowest price during period
    close NUMERIC(18,8) NOT NULL,           -- Closing price
    volume NUMERIC(28,8) NOT NULL,          -- Trading volume
    source TEXT NOT NULL DEFAULT 'schwab',  -- Data source identifier
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Record creation timestamp

    PRIMARY KEY (symbol, ts),
    CONSTRAINT check_minute_alignment
        CHECK (date_trunc('minute', ts) = ts)
);
```

**Key Features**:
- **Composite Primary Key**: `(symbol, ts)` ensures unique data points
- **High Precision**: `NUMERIC(18,8)` for prices, `NUMERIC(28,8)` for volume
- **Time Alignment**: Check constraint ensures 1-minute boundary alignment
- **Source Tracking**: Default 'schwab' with flexibility for multiple data sources
- **Audit Trail**: `created_at` timestamp for data ingestion tracking

**Data Validation**:
- No NULL values allowed in price/volume columns
- Timestamp must align to minute boundaries (seconds = 0)
- Volume must be non-negative
- Symbol format follows standard ticker conventions

### status Table - System Component Monitoring `#tables`

**Purpose**: Tracks the operational state of system components in real-time

```sql
CREATE TABLE status (
    name TEXT PRIMARY KEY,                   -- Component identifier
    state TEXT NOT NULL,                     -- Current operational state
    record_modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Last state change
    details JSONB NOT NULL DEFAULT '{}',    -- Flexible metadata storage
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- Initial creation time
);
```

**Key Features**:
- **Component Tracking**: Unique identifier for each system component
- **State Management**: Text-based state for human readability
- **Flexible Metadata**: JSONB for extensible component-specific data
- **Temporal Tracking**: Both creation and update timestamps

**Standard States**:
- `initialized`: Component created but not active
- `running`: Actively processing data or executing trades
- `stopped`: Gracefully halted, can be restarted
- `error`: Error state requiring intervention
- `healthy`: Normal operational status

**Current System Components**:
```sql
-- Example current status data
INSERT INTO status (name, state, details) VALUES
('data_collector', 'initialized', '{"symbols": ["AAPL", "MSFT"], "last_fetch": null}'),
('analyzer', 'initialized', '{"strategy": "momentum", "signals_generated": 0}'),
('trader', 'initialized', '{"portfolio_value": 0, "positions": 0}'),
('system', 'healthy', '{"uptime": "00:05:32", "memory_usage": "142MB"}');
```

---

## ⚡ Performance Optimization `#indexes`

### Index Strategy `#indexes`

The database uses strategically placed indexes to optimize common query patterns in trading operations:

```sql
-- Time-series queries (most recent data first)
CREATE INDEX idx_candles_ts_desc ON candles (ts DESC);

-- Symbol-specific queries
CREATE INDEX idx_candles_symbol ON candles (symbol);

-- Combined symbol and time queries (most common pattern)
CREATE INDEX idx_candles_symbol_ts ON candles (symbol, ts DESC);

-- Status monitoring and alerting
CREATE INDEX idx_status_record_modified_at ON status (record_modified_at DESC);
```

**Index Usage Patterns**:
- `idx_candles_ts_desc`: Latest market data across all symbols
- `idx_candles_symbol`: All historical data for specific symbol
- `idx_candles_symbol_ts`: Time-range queries for specific symbol (primary pattern)
- `idx_status_record_modified_at`: Recent component status changes

### Query Performance Guidelines `#indexes`

**Optimal Query Patterns**:
```sql
-- ✅ GOOD: Uses idx_candles_symbol_ts
SELECT * FROM candles
WHERE symbol = 'AAPL' AND ts >= '2025-01-01'
ORDER BY ts DESC LIMIT 100;

-- ✅ GOOD: Uses idx_candles_ts_desc
SELECT DISTINCT symbol FROM candles
WHERE ts >= NOW() - INTERVAL '1 hour';

-- ❌ AVOID: Full table scan
SELECT * FROM candles WHERE open > close;
```

**Performance Considerations**:
- **Time-range queries**: Always include timestamp filters
- **Symbol filtering**: Combine with time ranges for optimal performance
- **Sorting**: Use DESC order to leverage index optimization
- **Limit clauses**: Reduce result set size for recent data queries

---

## 🔧 Common Operations `#queries`

### Data Ingestion Patterns `#queries`

**UPSERT for Market Data**:
```sql
-- Insert new candle data with conflict resolution
INSERT INTO candles (symbol, ts, open, high, low, close, volume, source)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (symbol, ts)
DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    source = EXCLUDED.source;
```

**Batch Data Validation**:
```sql
-- Verify data integrity after ingestion
SELECT
    symbol,
    COUNT(*) as total_records,
    MIN(ts) as earliest_data,
    MAX(ts) as latest_data,
    COUNT(CASE WHEN high < low THEN 1 END) as invalid_ohlc,
    COUNT(CASE WHEN volume < 0 THEN 1 END) as invalid_volume
FROM candles
WHERE symbol = $1
GROUP BY symbol;
```

### Analysis Queries `#queries`

**Latest Market Data**:
```sql
-- Get most recent candle for each symbol
SELECT DISTINCT ON (symbol)
    symbol, ts, open, high, low, close, volume
FROM candles
ORDER BY symbol, ts DESC;
```

**Time-series Analysis**:
```sql
-- Calculate moving averages and volatility
SELECT
    symbol,
    ts,
    close,
    AVG(close) OVER (
        PARTITION BY symbol
        ORDER BY ts
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) as sma_20,
    STDDEV(close) OVER (
        PARTITION BY symbol
        ORDER BY ts
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) as volatility_20
FROM candles
WHERE symbol = $1
    AND ts >= $2
ORDER BY ts DESC;
```

**Gap Detection**:
```sql
-- Find missing data periods (gaps in time-series)
SELECT
    symbol,
    ts as gap_start,
    LEAD(ts) OVER (PARTITION BY symbol ORDER BY ts) as gap_end,
    EXTRACT(EPOCH FROM (
        LEAD(ts) OVER (PARTITION BY symbol ORDER BY ts) - ts
    ))/60 as gap_minutes
FROM candles
WHERE symbol = $1
    AND EXTRACT(EPOCH FROM (
        LEAD(ts) OVER (PARTITION BY symbol ORDER BY ts) - ts
    ))/60 > 1;
```

### System Monitoring Queries `#queries` `#monitoring`

**Component Health Check**:
```sql
-- Check all system components status
SELECT
    name,
    state,
    record_modified_at,
    NOW() - record_modified_at as time_since_update,
    details->>'last_action' as last_action
FROM status
ORDER BY record_modified_at DESC;
```

**Data Freshness Monitoring**:
```sql
-- Check data freshness for trading decisions
SELECT
    symbol,
    MAX(ts) as latest_data,
    NOW() - MAX(ts) as data_age_minutes,
    COUNT(*) as total_candles,
    CASE
        WHEN NOW() - MAX(ts) < INTERVAL '5 minutes' THEN 'FRESH'
        WHEN NOW() - MAX(ts) < INTERVAL '15 minutes' THEN 'STALE'
        ELSE 'EXPIRED'
    END as data_status
FROM candles
GROUP BY symbol
ORDER BY latest_data DESC;
```

**Performance Monitoring**:
```sql
-- Database performance metrics
SELECT
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    seq_scan as sequential_scans,
    idx_scan as index_scans
FROM pg_stat_user_tables
WHERE tablename IN ('candles', 'status');
```

---

## 📊 System Monitoring `#monitoring`

### Component Status Tracking `#monitoring`

The status table provides real-time visibility into system component health:

**Status Update Pattern**:
```sql
-- Update component status with details
UPDATE status
SET
    state = $1,
    record_modified_at = NOW(),
    details = details || $2::jsonb
WHERE name = $3;
```

**Health Dashboard Query**:
```sql
-- Complete system health overview
SELECT
    s.name,
    s.state,
    s.record_modified_at,
    EXTRACT(EPOCH FROM (NOW() - s.record_modified_at))/60 as minutes_since_update,
    s.details,
    CASE
        WHEN s.state = 'error' THEN 'CRITICAL'
        WHEN s.state IN ('stopped', 'initialized') THEN 'WARNING'
        WHEN EXTRACT(EPOCH FROM (NOW() - s.record_modified_at))/60 > 30 THEN 'STALE'
        ELSE 'OK'
    END as health_status
FROM status s
ORDER BY
    CASE s.state
        WHEN 'error' THEN 1
        WHEN 'stopped' THEN 2
        WHEN 'initialized' THEN 3
        ELSE 4
    END,
    s.record_modified_at DESC;
```

### Data Quality Monitoring `#monitoring`

**Daily Data Quality Report**:
```sql
-- Comprehensive data quality metrics
WITH daily_stats AS (
    SELECT
        symbol,
        DATE(ts) as trade_date,
        COUNT(*) as candle_count,
        MIN(ts) as first_candle,
        MAX(ts) as last_candle,
        AVG(volume) as avg_volume,
        COUNT(CASE WHEN high < low THEN 1 END) as ohlc_errors,
        COUNT(CASE WHEN volume = 0 THEN 1 END) as zero_volume_count
    FROM candles
    WHERE ts >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY symbol, DATE(ts)
)
SELECT
    symbol,
    trade_date,
    candle_count,
    CASE
        WHEN candle_count = 390 THEN 'COMPLETE'  -- Full trading day
        WHEN candle_count > 350 THEN 'GOOD'
        WHEN candle_count > 200 THEN 'PARTIAL'
        ELSE 'POOR'
    END as data_completeness,
    ohlc_errors,
    zero_volume_count,
    ROUND(avg_volume::numeric, 2) as avg_volume
FROM daily_stats
ORDER BY trade_date DESC, symbol;
```

### Alerting Conditions `#monitoring`

**Critical Alert Triggers**:
- Component in 'error' state for > 5 minutes
- Data freshness > 15 minutes during market hours
- OHLC validation errors in recent data
- System component not updated for > 30 minutes

**Warning Alert Triggers**:
- Data completeness < 80% for trading day
- Volume anomalies (0 volume or extreme spikes)
- Component state changes from 'running' to 'stopped'

### Database Maintenance `#database`

**Cleanup Operations**:
```sql
-- Archive old candle data (keep 1 year)
DELETE FROM candles
WHERE ts < NOW() - INTERVAL '1 year';

-- Clean up old status history (if implementing status history)
DELETE FROM status_history
WHERE created_at < NOW() - INTERVAL '30 days';
```

**Statistics Update**:
```sql
-- Update table statistics for query optimization
ANALYZE candles;
ANALYZE status;
```

---

## 🔄 Schema Evolution `#database`

### Migration Strategy `#database`
- **Backward compatibility**: New columns with defaults, avoid breaking changes
- **Index maintenance**: Monitor query performance after schema changes
- **Data validation**: Verify integrity after migrations
- **Rollback plan**: Always prepare rollback scripts for schema changes

### Future Enhancements `#database`
- **Partitioning**: Consider time-based partitioning for candles table as data grows
- **TimescaleDB**: Potential migration for enhanced time-series capabilities
- **Additional tables**: Orders, trades, portfolio positions for full trading system
- **Data retention**: Automated archival policies for historical data management

---

## 📚 External Dependencies

### Core Dependencies
- **schwab-py**: Official Schwab API client for authentication and trading
- **PostgreSQL**: Primary data store (TimescaleDB optional for optimization)
- **pandas**: Data manipulation and validation
- **numpy**: Numerical computations

### Development Tools
- **pytest**: Testing framework
- **black**: Code formatting (line length 100)
- **ruff**: Linting and code quality

---

## 🔄 Project Evolution `#policy`

This document is actively maintained and updated as the project evolves. When making changes:

1. Update relevant tags and cross-references
2. Maintain backward compatibility in documentation
3. Add new sections with appropriate tags
4. Update Quick Reference Tags table when adding new content

**Last Updated**: Database schema documentation (2025-09-27)
**Next Review**: After core component implementation and first data ingestion