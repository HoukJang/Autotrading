# AutoTrader v3 - Nightly Batch Architecture Team Design

> Nightly batch swing trading system rebuild with 3-team structure.

## Architecture Overview

```
[Current] Real-time streaming 10 symbols -> Aggregator -> Daily bar -> Strategy
[Target]  Nightly batch 503 symbols -> Rank top 12 -> Gap filter -> Entry -> Position management
```

### Target System Flow

```
8:00 PM ET   Nightly Batch Scanner
             - Fetch confirmed daily bars for 503 S&P 500 stocks (Alpaca REST API)
             - Compute indicators (RSI, BB, ADX, ATR)
             - Run 5 strategies against all 503
             - Composite score ranking -> select top 12 candidates
             - Save results to file (JSON)

9:25 AM ET   Pre-Market Gap Filter
             - Fetch pre-market prices for 12 candidates
             - Skip if gap > +-3% from previous close
             - Output: filtered candidate list

9:30 AM ET   Entry Execution (Group A - MOO)
             - RSI mean reversion, BB squeeze -> market order at open
             - SL/TP calculated from actual fill price

9:50 AM ET   Entry Execution (Group B - Confirmation)
             - ADX pullback, regime momentum, overbought short
             - Confirm: long -> price >= open * 0.997 | short -> price <= open * 1.003
             - Enter confirmed, discard unconfirmed

10:00 AM ET  Entry window closes. No new entries after this.

Intraday     Position Monitoring
             - Stream held positions only (max 8)
             - Day 1: NO SL/TP check (entry day skip), emergency -7% only
             - Day 2+: ATR-based SL/TP monitoring
             - Day 5: time-based forced exit
             - After sell: no re-entry same stock same day
             - MFE/MAE tracking per position
```

### Strategy-Specific Parameters

| Strategy | Entry Type | SL (ATR mult) | TP (ATR mult) | R:R |
|----------|-----------|---------------|---------------|-----|
| RSI Mean Reversion | MOO (9:31) | 1.5 | 2.0 | 1:1.33 |
| BB Squeeze | MOO (9:31) | 2.5 | 4.0 | 1:1.6 |
| ADX Pullback | Confirm (9:50) | 2.0 | 3.0 | 1:1.5 |
| Overbought Short | Confirm (9:50) | 2.0 | 2.5 | 1:1.25 |
| Regime Momentum | Confirm (9:50) | 2.0 | 3.5 | 1:1.75 |

---

## Team Structure

```
[Orchestrator] (Main conversation = Project Manager)
     |
     +-- [Development Team] -- 5 agents (system design + implementation + dashboard)
     |
     +-- [Strategy Team]    -- 4 agents (trading domain experts, advisory)
     |
     +-- [Test Team]        -- 2 agents (QA + backtesting)
```

### Team Boundaries

| Domain | Owner | Other teams MUST NOT |
|--------|-------|---------------------|
| `autotrader/batch/` | Development | Strategy/Test: no code changes |
| `autotrader/execution/` | Development | Strategy/Test: no code changes |
| `autotrader/main.py` | Development | Strategy/Test: no code changes |
| `autotrader/strategy/*.py` | Development (impl) + Strategy (spec) | Test: no code changes |
| `autotrader/dashboard/` | Development (Dev-5) | Strategy/Test: no code changes |
| `config/strategy_params.yaml` | Strategy (defines) -> Dev (implements) | Test: no changes |
| `tests/` | Test | Dev/Strategy: no test changes |
| `docs/strategies/` | Strategy | Dev/Test: no changes |
| `docs/analysis/` | Test (backtest reports) | Dev/Strategy: no changes |

---

## Development Team (5 agents)

### Dev-1: System Architect

| Property | Value |
|----------|-------|
| Agent type | `system-architect` |
| Phase | Phase 1 (first, solo) |
| Isolation | Main branch |

**Responsibilities:**
- Design overall batch architecture (modules, data flow, scheduling)
- Define ABCs/protocols: `NightlyScanner`, `PreMarketFilter`, `ExecutionManager`, `PositionMonitor`, `ExitRuleEngine`
- Create file/directory structure for new modules
- Write interface contracts between teams (what Strategy team specifies vs what Dev team implements)
- Create file ownership map to prevent agent conflicts
- Review Strategy team's specs for implementability

**Outputs:**
- `docs/plans/batch-architecture.md`
- `docs/plans/interface-contracts.md`
- `docs/plans/file-ownership-map.md`
- ABC skeleton code in `autotrader/batch/` and `autotrader/execution/`

### Dev-2: Pipeline Engineer

| Property | Value |
|----------|-------|
| Agent type | `backend-architect` |
| Phase | Phase 2 (parallel, after Architect) |
| Isolation | Worktree |

**Responsibilities:**
- Implement 8 PM nightly batch scanner (503 symbols fetch, indicator compute, strategy execution)
- Implement signal ranking engine (composite score, sector diversification, top 12 selection)
- Implement batch scheduler (asyncio-based, 8 PM ET trigger, retry on failure)
- Implement 9:25 AM pre-market gap filter (fetch pre-market prices, apply Strategy team's gap spec)
- Batch result persistence (JSON file for dashboard + next-stage consumption)
- Failure recovery: retry policy, partial failure handling, fallback to previous day's scan

**Owns:**
- `autotrader/batch/scanner.py`
- `autotrader/batch/scheduler.py`
- `autotrader/batch/ranking.py`
- `autotrader/batch/gap_filter.py`
- `autotrader/data/batch_fetcher.py`

### Dev-3: Execution Engineer

| Property | Value |
|----------|-------|
| Agent type | `python-expert` |
| Phase | Phase 2 (parallel, after Architect) |
| Isolation | Worktree |

**Responsibilities:**
- Implement entry execution engine:
  - Group A (MOO): submit market orders at 9:31 AM for mean reversion strategies
  - Group B (Confirmation): monitor 9:30-9:50 AM, confirm direction, enter or discard
- Implement exit rule engine:
  - Day 1: entry day skip (no SL/TP), emergency stop -7% only (overrides PDT guard)
  - Day 2+: ATR-based SL/TP monitoring via real-time streaming
  - Day 5: time-based forced exit
  - Same-day re-entry block after sell
- Implement position monitor: stream held positions, MFE/MAE tracking
- Rewrite `autotrader/main.py` for new batch + intraday hybrid architecture
- Alpaca order management: stop orders + real-time monitoring hybrid

**Owns:**
- `autotrader/execution/entry_manager.py`
- `autotrader/execution/exit_rules.py`
- `autotrader/execution/position_monitor.py`
- `autotrader/execution/order_manager.py`
- `autotrader/main.py` (rewrite)

### Dev-4: DevOps Engineer

| Property | Value |
|----------|-------|
| Agent type | `devops-architect` |
| Phase | Phase 3 (after implementation) |
| Isolation | Main branch |

**Responsibilities:**
- Process supervision: watchdog for batch scheduler, auto-restart on crash
- Log monitoring: structured logging, error detection, daily summary
- Startup/shutdown scripts: update `start_trading.bat`, `stop_trading.bat`
- Health checks: verify 8 PM batch ran, verify 9:30 AM entries executed
- Alert system foundation: log-based error detection (future: Telegram/Discord)

**Owns:**
- `scripts/watchdog.py`
- `start_trading.bat`, `stop_trading.bat`
- `scripts/health_check.py`

### Dev-5: Frontend Engineer

| Property | Value |
|----------|-------|
| Agent type | `frontend-architect` |
| Phase | Phase 2 (parallel with Pipeline/Execution) + Phase 3 (integration) |
| Isolation | Worktree |

**Responsibilities:**
- Redesign Streamlit dashboard for nightly batch architecture:
  - Nightly scan results view: 503 stocks scanned, top 12 candidates with scores
  - Entry candidates panel: gap filter results, entry group (MOO/Confirm), status
  - Position monitor: live SL/TP levels, MFE/MAE, days held, entry day skip indicator
  - Exit log: exit reason (SL/TP/time/emergency), actual vs target prices
- Fix existing dashboard bugs (timestamp parsing, empty data guards)
- New data loader for batch results (JSON from nightly scanner)
- Strategy performance dashboard: per-strategy win rate, PnL, R:R ratio
- Regime display: current regime, regime history, regime-strategy compatibility view
- Real-time status bar: next scheduled event (batch scan, gap filter, entry window)

**Owns:**
- `autotrader/dashboard/live_app.py` (rewrite)
- `autotrader/dashboard/data_loader.py` (update for batch data)
- `autotrader/dashboard/components/*.py` (all components)
- `autotrader/dashboard/theme.py`
- `autotrader/dashboard/utils/*.py`

---

## Strategy Team (5 agents - Domain Experts)

Strategy team agents are domain experts who provide trading knowledge through panel discussions.
They produce specification documents and parameter configurations, NOT code.

> **Roster Change Log (11th backtest):**
> - Removed: Strat-1 (Swing Trade Expert) -- SL/TP 역할이 Strat-4/5와 중복
> - Removed: Strat-3 (Market Microstructure Expert) -- daily bar 시스템에서 활용도 낮음
> - Added: Strat-6 (Trading System Architect) -- 시스템 구조 변경 아이디어 전문
> - Added: Strat-7 (Root Cause / Structure Analyst) -- 데이터 기반 근본원인 진단 전문

### Strat-2: Portfolio Risk Manager

| Property | Value |
|----------|-------|
| Agent type | `business-panel-experts` |
| Phase | Phase 1 + Phase 4 (initial rules + ongoing review) |
| Invocation | Panel discussions on risk-related decisions |

**Responsibilities:**
- Position sizing rules: max % per position, account risk limits
- Drawdown management: GDR thresholds, risk tiers, portfolio safety nets
- Regime-based exposure: how many positions in TREND vs HIGH_VOL vs RANGING
- Correlation risk: max same-sector positions, max same-direction positions
- Emergency procedures: what to do in flash crash, circuit breaker halt
- Daily/weekly risk budget limits

**Outputs:**
- `docs/strategies/risk-management-spec.md`
- `docs/strategies/regime-exposure-rules.md`
- Risk parameters in `config/strategy_params.yaml`

### Strat-4: Trade Analyst

| Property | Value |
|----------|-------|
| Agent type | `business-panel-experts` |
| Phase | Phase 4 (after backtests and live data) |
| Invocation | When trade data needs interpretation |

**Responsibilities:**
- Analyze backtest results: is each strategy performing as expected?
- Win rate trends: improving or degrading over time?
- Strategy comparison: which strategies contribute most to PnL?
- MFE/MAE analysis: are SL/TP levels optimal based on actual data?
- Identify systematic patterns: time-of-day effects, day-of-week effects
- Recommend parameter adjustments based on evidence

**Outputs:**
- `docs/analysis/strategy-performance-review.md`
- `docs/analysis/sltp-optimization-recommendations.md`

### Strat-5: Quant Algorithm Expert

| Property | Value |
|----------|-------|
| Agent type | `business-panel-experts` |
| Phase | Phase 4 (after backtests, alongside Strat-4) |
| Invocation | Panel discussions requiring mathematical/statistical rigor |

**Role Model:** Renaissance Technologies style quantitative algorithm specialist

**Responsibilities:**
- Portfolio-level mathematical analysis: correlation matrices, covariance structure
- Position sizing optimization: Kelly criterion, fractional Kelly, risk parity
- Drawdown decomposition: mathematical attribution of DD to strategy correlation, sizing, timing
- Monte Carlo simulation for risk estimation and tail risk quantification
- Walk-forward validation design: train/test splits, regime-aware cross-validation
- Signal decay modeling: edge half-life estimation per strategy
- Portfolio construction optimization: mean-variance, risk budgeting, strategy weight allocation

**Outputs:**
- `docs/analysis/portfolio-math-analysis.md`
- `docs/analysis/position-sizing-optimization.md`
- `docs/analysis/drawdown-decomposition.md`

### Strat-6: Trading System Architect

| Property | Value |
|----------|-------|
| Agent type | `business-panel-experts` |
| Phase | Phase 4 (after backtests, proactive structural proposals) |
| Invocation | Panel discussions, especially after backtest failures or plateaus |

**Role Model:** Two Sigma / DE Shaw style trading system designer

**Responsibilities:**
- Trading system structural design: component separation, strategy isolation, capital allocation architecture
- Propose structural changes (e.g., per-strategy GDR, independent capital pools, strategy-level risk budgets)
- Identify when parameter tuning is insufficient and architectural change is needed
- Design feedback loops: how backtest results should inform system structure
- Cross-strategy interaction analysis: how strategies interfere with each other in portfolio context
- Scalability analysis: will current architecture support 5, 10, 20 strategies?

**Key Question:** "Is this a parameter problem or an architecture problem?"

**Outputs:**
- `docs/analysis/system-architecture-proposals.md`
- `docs/analysis/structural-change-specs.md`

### Strat-7: Root Cause / Structure Analyst

| Property | Value |
|----------|-------|
| Agent type | `business-panel-experts` |
| Phase | Phase 4 (after backtests, diagnostic-first approach) |
| Invocation | Panel discussions, especially when results are unexpected or degrading |

**Role Model:** Bridgewater Associates style systematic diagnostician

**Responsibilities:**
- Root cause analysis: trace unexpected results to their structural origin
- Circular dependency detection: identify feedback loops that amplify problems (e.g., DD -> GDR -> reduced recovery -> prolonged DD)
- Counterfactual analysis: "what would have happened if X were different?"
- Metric decomposition: break aggregate metrics into contributing factors
- Hypothesis generation: propose testable explanations for observed phenomena
- Anti-pattern identification: detect when optimization is making things worse (overfitting, death spirals)

**Key Question:** "Why did this happen, and what structural assumption is wrong?"

**Outputs:**
- `docs/analysis/root-cause-reports.md`
- `docs/analysis/counterfactual-analysis.md`

---

## Test Team (2 agents)

### Test-1: Quality Engineer

| Property | Value |
|----------|-------|
| Agent type | `quality-engineer` |
| Phase | Phase 1 (test audit) + Phase 3 (new tests) + Phase 4 (E2E) |
| Isolation | Main branch |

**Responsibilities:**
- Phase 1: Audit existing 903 tests - classify as valid/invalid/needs-update
- Phase 3: Write unit tests for new batch/execution modules
- Phase 3: Write integration tests (batch -> gap filter -> entry -> monitoring)
- Phase 4: Write E2E tests (full day simulation: 8 PM scan -> next day entries -> exits)
- Code review: verify Dev team's implementation matches Strategy team's specs
- Regression testing: ensure existing working modules (indicators, strategies, risk) not broken

**Owns:**
- `tests/unit/batch/`
- `tests/unit/execution/`
- `tests/integration/`
- `tests/e2e/`

### Test-2: Backtest Engineer

| Property | Value |
|----------|-------|
| Agent type | `performance-engineer` |
| Phase | Phase 3 (after Dev implementation) |
| Isolation | Worktree |

**Responsibilities:**
- Adapt backtest engine for new batch architecture (nightly scan simulation)
- Run backtest scenarios:
  - Each strategy individually with ATR SL/TP
  - Combined portfolio with ranking + position limits
  - Entry day skip vs no skip comparison
  - Day 3 vs Day 5 vs Day 7 time exit comparison
  - Gap filter 2% vs 3% vs 5% comparison
- MFE/MAE distribution analysis per strategy
- Generate performance reports: Sharpe, Sortino, Max DD, Win Rate, Profit Factor
- Validate Strategy team's parameter recommendations against historical data

**Owns:**
- `autotrader/backtest/` (modifications for batch simulation)
- `docs/analysis/backtest-results.md`
- `docs/analysis/parameter-validation.md`
- `docs/analysis/mfe-mae-analysis.md`

---

## Execution Phases

```
Phase 1: Design & Specification (parallel)
  +-- [Dev-1: System Architect]   -> architecture + ABCs + interface contracts
  +-- [Strat-1 + 2 + 3: Panel]   -> strategy specs + risk rules + parameters
  +-- [Test-1: Quality Engineer]  -> existing test audit report

  Duration: ~1 session
  Gate: Architecture doc + Strategy specs + Test audit reviewed by Orchestrator

Phase 2: Core Implementation (parallel, worktree isolated)
  +-- [Dev-2: Pipeline Engineer]   -> batch scanner, scheduler, gap filter, ranking
  +-- [Dev-3: Execution Engineer]  -> entry/exit engine, position monitor, main.py
  +-- [Dev-5: Frontend Engineer]   -> dashboard rewrite for batch architecture

  Duration: ~2-3 sessions
  Gate: All unit tests pass, no file conflicts

Phase 3: Integration & Validation (parallel)
  +-- [Orchestrator]              -> merge Phase 2 worktrees
  +-- [Test-1: Quality Engineer]  -> integration tests + E2E tests
  +-- [Test-2: Backtest Engineer] -> backtest scenarios + performance reports
  +-- [Dev-4: DevOps Engineer]    -> monitoring, scripts, health checks

  Duration: ~1-2 sessions
  Gate: All tests pass, backtest results acceptable

Phase 4: Review & Optimization (iterative)
  +-- [Strat-4: Trade Analyst]    -> backtest result analysis + recommendations
  +-- [Strat-3: Risk Manager]     -> risk parameter review
  +-- [Dev-3: Execution Engineer] -> parameter adjustments based on analysis
  +-- [Test-2: Backtest Engineer] -> re-validate adjusted parameters

  Duration: iterative cycle
  Gate: Strategy team signs off on performance
```

---

## Inter-Team Communication Protocol

### Strategy -> Development (specs flow down)

Strategy team produces specification documents. Dev team implements them.

| Spec Document | Author | Consumer | Format |
|--------------|--------|----------|--------|
| Entry rules (MOO vs confirm, timing) | Strat-1 | Dev-3 | Markdown spec |
| Exit rules (SL/TP, day skip, time exit) | Strat-1 | Dev-3 | Markdown spec |
| ATR multipliers per strategy | Strat-2 | Dev-3 | YAML config |
| Gap filter conditions | Strat-1 + Strat-2 | Dev-2 | YAML config |
| Ranking weights | Strat-2 | Dev-2 | YAML config |
| Risk limits (position size, drawdown) | Strat-3 | Dev-2 + Dev-3 | YAML config |
| Regime exposure rules | Strat-3 | Dev-2 | YAML config |

### Development -> Test (implementation flows to validation)

| Artifact | Author | Consumer |
|----------|--------|----------|
| New module code | Dev-2, Dev-3 | Test-1 (unit/integration tests) |
| Batch result format (JSON) | Dev-2 | Dev-5 (dashboard display) + Test-2 (backtest) |
| Dashboard components | Dev-5 | Test-1 (UI integration tests) |
| Strategy specs (from Strategy team) | Dev pass-through | Test-1 (spec compliance testing) |

### Test -> Strategy (results flow up for review)

| Report | Author | Consumer |
|--------|--------|----------|
| Backtest performance report | Test-2 | Strat-4 (analysis) |
| MFE/MAE distribution | Test-2 | Strat-2 (parameter tuning) |
| Risk metric summary | Test-2 | Strat-3 (risk review) |
| Parameter validation results | Test-2 | Strat-1 + Strat-2 (approval) |

---

## Model Selection

| Agent | Model | Rationale |
|-------|-------|-----------|
| Orchestrator | opus | Complex coordination, merge decisions |
| Dev-1: System Architect | opus | Architecture requires deep reasoning |
| Dev-2: Pipeline Engineer | sonnet | Implementation with clear specs |
| Dev-3: Execution Engineer | sonnet | Implementation with clear specs |
| Dev-4: DevOps Engineer | sonnet | Infrastructure scripting |
| Dev-5: Frontend Engineer | sonnet | Dashboard implementation |
| Strat-1~4: Strategy Panel | opus | Domain expertise, nuanced analysis |
| Test-1: Quality Engineer | sonnet | Test writing, code review |
| Test-2: Backtest Engineer | sonnet | Analysis + implementation |

---

## Risk Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| Phase 2 interface mismatch | High | Phase 1 Architect provides compilable ABC skeletons |
| Team boundary violation | Medium | File ownership map enforced in agent prompts |
| 503-symbol batch performance | Medium | Pipeline Engineer must benchmark (target: < 2 min) |
| Existing test mass failure | Low | Test audit in Phase 1 identifies affected tests |
| Merge conflicts | Medium | File ownership map prevents overlap; shared files handled sequentially |
| Strategy specs too vague | Medium | Orchestrator reviews specs before Phase 2 starts |
