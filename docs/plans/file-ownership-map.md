# AutoTrader v3 - File Ownership Map

> Prevents merge conflicts by assigning clear file ownership per agent.
> Author: Dev-1 (System Architect) | Date: 2026-02-27

---

## Ownership Rules

1. **Only the owner may create or modify a file.**
2. **Shared files** (marked with multiple owners) require sequential edits -- never parallel.
3. **Read-only access** is unrestricted -- any agent can read any file.
4. **New files** in an owned directory must be created by the directory owner.
5. **If conflict is detected**, the Orchestrator resolves by determining which agent's changes take precedence.

---

## File Ownership Table

### New Batch Modules (autotrader/batch/)

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/batch/__init__.py` | Dev-1 (Architect) | Phase 1 | Created with ABC exports |
| `autotrader/batch/scanner.py` | Dev-2 (Pipeline) | Phase 2 | Implements NightlyScanner |
| `autotrader/batch/scheduler.py` | Dev-2 (Pipeline) | Phase 2 | Implements BatchScheduler |
| `autotrader/batch/ranking.py` | Dev-2 (Pipeline) | Phase 2 | Implements SignalRanker |
| `autotrader/batch/gap_filter.py` | Dev-2 (Pipeline) | Phase 2 | Implements GapFilter |

### New Execution Modules (autotrader/execution/)

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/execution/__init__.py` | Dev-1 (Architect) | Phase 1 | Created with ABC exports |
| `autotrader/execution/entry_manager.py` | Dev-3 (Execution) | Phase 2 | Implements EntryManager |
| `autotrader/execution/exit_rules.py` | Dev-3 (Execution) | Phase 2 | Implements ExitRuleEngine |
| `autotrader/execution/position_monitor.py` | Dev-3 (Execution) | Phase 2 | Implements PositionMonitor |
| `autotrader/execution/order_manager.py` | Dev-3 (Execution) | Phase 2 | Implements OrderManager |

### New Data Modules

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/data/batch_fetcher.py` | Dev-2 (Pipeline) | Phase 2 | Implements BatchFetcher |

### Main Application

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/main.py` | Dev-3 (Execution) | Phase 2 | Complete rewrite |

### Shared Core Types (Sequential Access)

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/core/types.py` | Dev-1 (Architect) | Phase 1 | Add new batch types |
| `autotrader/core/config.py` | Dev-1 (Architect) | Phase 1 | Add BatchConfig model |

**IMPORTANT**: After Phase 1, if Dev-2 or Dev-3 need to add types, they must coordinate through the Orchestrator. Dev-1 defines the initial set; subsequent additions are handled sequentially.

### Configuration Files

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `config/default.yaml` | Dev-1 (Architect) | Phase 1 | Extend with batch section (if needed) |
| `config/strategy_params.yaml` | Strat-2 (Quant) | Phase 1 | Strategy team defines values |

### Dashboard

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `autotrader/dashboard/live_app.py` | Dev-5 (Frontend) | Phase 2 | Dashboard rewrite |
| `autotrader/dashboard/data_loader.py` | Dev-5 (Frontend) | Phase 2 | New batch data loader |
| `autotrader/dashboard/components/*.py` | Dev-5 (Frontend) | Phase 2 | All dashboard components |
| `autotrader/dashboard/theme.py` | Dev-5 (Frontend) | Phase 2 | Theme and styling |
| `autotrader/dashboard/utils/*.py` | Dev-5 (Frontend) | Phase 2 | Dashboard utilities |

### DevOps and Scripts

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `scripts/watchdog.py` | Dev-4 (DevOps) | Phase 3 | Process supervision |
| `scripts/health_check.py` | Dev-4 (DevOps) | Phase 3 | Health monitoring |
| `start_trading.bat` | Dev-4 (DevOps) | Phase 3 | Startup script update |
| `stop_trading.bat` | Dev-4 (DevOps) | Phase 3 | Shutdown script update |

### Tests

| File/Directory | Owner | Phase | Notes |
|---------------|-------|-------|-------|
| `tests/unit/batch/` | Test-1 (QA) | Phase 3 | Batch module tests |
| `tests/unit/execution/` | Test-1 (QA) | Phase 3 | Execution module tests |
| `tests/integration/` | Test-1 (QA) | Phase 3 | Integration tests |
| `tests/e2e/` | Test-1 (QA) | Phase 4 | End-to-end tests |
| `tests/` (existing files) | Test-1 (QA) | Phase 1 | Audit and update |

### Strategy Documentation

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `docs/strategies/entry-rules-spec.md` | Strat-1 (Swing) | Phase 1 | Entry rules specification |
| `docs/strategies/exit-rules-spec.md` | Strat-1 (Swing) | Phase 1 | Exit rules specification |
| `docs/strategies/stock-selection-criteria.md` | Strat-1 (Swing) | Phase 1 | Selection criteria |
| `docs/strategies/sltp-statistical-basis.md` | Strat-2 (Quant) | Phase 1 | Statistical analysis |
| `docs/strategies/ranking-algorithm-spec.md` | Strat-2 (Quant) | Phase 1 | Ranking specification |
| `docs/strategies/risk-management-spec.md` | Strat-3 (Risk) | Phase 1 | Risk rules |
| `docs/strategies/regime-exposure-rules.md` | Strat-3 (Risk) | Phase 1 | Regime-based exposure |

### Analysis Reports

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `docs/analysis/backtest-results.md` | Test-2 (Backtest) | Phase 3 | Backtest report |
| `docs/analysis/parameter-validation.md` | Test-2 (Backtest) | Phase 3 | Param validation |
| `docs/analysis/mfe-mae-analysis.md` | Test-2 (Backtest) | Phase 3 | MFE/MAE analysis |
| `docs/analysis/strategy-performance-review.md` | Strat-4 (Analyst) | Phase 4 | Performance review |

### Architecture Documentation

| File | Owner | Phase | Notes |
|------|-------|-------|-------|
| `docs/plans/batch-architecture.md` | Dev-1 (Architect) | Phase 1 | This document |
| `docs/plans/interface-contracts.md` | Dev-1 (Architect) | Phase 1 | Interface specs |
| `docs/plans/file-ownership-map.md` | Dev-1 (Architect) | Phase 1 | This map |

---

## Existing Modules - DO NOT MODIFY

These modules are proven, tested, and working. No agent should modify them without explicit Orchestrator approval.

| File/Directory | Status | Protected By |
|---------------|--------|-------------|
| `autotrader/strategy/rsi_mean_reversion.py` | FROZEN | 903 existing tests |
| `autotrader/strategy/bb_squeeze.py` | FROZEN | 903 existing tests |
| `autotrader/strategy/adx_pullback.py` | FROZEN | 903 existing tests |
| `autotrader/strategy/overbought_short.py` | FROZEN | 903 existing tests |
| `autotrader/strategy/regime_momentum.py` | FROZEN | 903 existing tests |
| `autotrader/strategy/base.py` | FROZEN | ABC contract |
| `autotrader/strategy/engine.py` | FROZEN | Strategy orchestration |
| `autotrader/indicators/` (all files) | FROZEN | 903 existing tests |
| `autotrader/core/aggregator.py` | FROZEN | Aggregator logic |
| `autotrader/portfolio/regime_detector.py` | FROZEN | Regime detection |
| `autotrader/portfolio/allocation_engine.py` | FROZEN | Position sizing |
| `autotrader/portfolio/position_tracker.py` | FROZEN | MFE/MAE tracking |
| `autotrader/portfolio/trade_logger.py` | FROZEN | Trade logging |
| `autotrader/risk/manager.py` | FROZEN | Risk validation |
| `autotrader/risk/position_sizer.py` | FROZEN | Position sizing |
| `autotrader/broker/base.py` | FROZEN | Broker ABC |
| `autotrader/broker/paper.py` | FROZEN | Paper broker |
| `autotrader/universe/provider.py` | FROZEN | S&P 500 provider |

### Modules With Allowed Extension

| File | Allowed Changes | By Whom |
|------|----------------|---------|
| `autotrader/broker/alpaca_adapter.py` | Add `get_latest_quotes()` method | Dev-2 (Pipeline) |
| `autotrader/core/types.py` | Add new dataclasses (additive only) | Dev-1 (Architect) |
| `autotrader/core/config.py` | Add new config models (additive only) | Dev-1 (Architect) |

---

## Conflict Resolution Matrix

| Scenario | Resolution |
|----------|------------|
| Two agents need to modify `core/types.py` | Dev-1 makes all changes; others request through Orchestrator |
| Dev-2 and Dev-3 both need a new helper | Each creates in their own module directory |
| Dashboard needs new data format | Dev-5 requests through Orchestrator; Dev-2 updates JSON schema |
| Test finds bug in implementation | Test-1 reports; owning Dev agent fixes |
| Strategy team wants parameter change | Updates `config/strategy_params.yaml`; no code changes needed |

---

## Phase-Based Access Control

### Phase 1 (Design)
- **Active**: Dev-1, Strat-1/2/3, Test-1
- **Write access**: Dev-1 creates all skeleton files and types
- **Strat team**: Creates docs and YAML config only
- **Test-1**: Audit existing tests (read-only on code)

### Phase 2 (Implementation)
- **Active**: Dev-2, Dev-3, Dev-5
- **Dev-2**: Writes only in `autotrader/batch/`, `autotrader/data/batch_fetcher.py`
- **Dev-3**: Writes only in `autotrader/execution/`, `autotrader/main.py`
- **Dev-5**: Writes only in `autotrader/dashboard/`
- **No cross-directory writes allowed**

### Phase 3 (Integration)
- **Active**: Orchestrator (merge), Test-1, Test-2, Dev-4
- **Orchestrator**: Merges worktrees, resolves conflicts
- **Test-1**: Creates tests in `tests/`
- **Test-2**: Creates backtests in `autotrader/backtest/`
- **Dev-4**: Creates scripts in `scripts/`

### Phase 4 (Review)
- **Active**: Strat-4, Strat-3, Dev-3, Test-2
- **Parameter adjustments only** -- no structural code changes
- **Config changes**: `config/strategy_params.yaml` only
