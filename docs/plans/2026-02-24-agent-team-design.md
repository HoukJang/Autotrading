# AutoTrader v2 - Agent Team Design

> Hierarchical agent team for parallel implementation with context optimization.

## Team Structure

```
[Orchestrator] (Main conversation = Project Manager)
     |
     +-- [Foundation Lead] -- Worker: scaffolding
     |                     -- Worker: types + exceptions
     |                     -- Worker: config + eventbus + logger
     |
     +-- [Broker Lead]    -- Worker: broker ABC + paper
     |                    -- Worker: alpaca adapter
     |
     +-- [Data Lead]      -- Worker: indicator engine + builtins
     |                    -- Worker: sqlite store
     |
     +-- [Business Lead]  -- Worker: strategy system
     |                    -- Worker: risk + portfolio
     |
     +-- [Integration Lead] -- Worker: backtest engine
     |                      -- Worker: main entry
     |
     +-- [Quality Lead]   -- Worker: test suite
                           -- Worker: exports + review
```

## Execution Phases

```
Phase 1: [Foundation Lead] --> Workers 1-3 (sequential)
                           --> review + test + commit

Phase 2: [Broker Lead]  --|
         [Data Lead]    --|-- 3 agents in parallel (worktree isolation)
         [Business Lead] --|
         Each Lead --> dispatches own workers + review

         (Orchestrator: wait for all 3 Leads --> merge)

Phase 3: [Integration Lead] --> Workers 1-2
                             --> integration test + commit

Phase 4: [Quality Lead] --> full verification + code review
```

## Agent Definitions

### Orchestrator (Main Conversation)

- **Role:** Project Manager
- **Responsibilities:** Phase transitions, Lead dispatch, merge coordination
- **Context:** Design doc + Lead completion status only (~5K tokens)

### Foundation Lead

| Property | Value |
|----------|-------|
| Subagent type | `general-purpose` |
| Worker count | 3 (`python-expert`, haiku model for cost) |
| Phase | 1 (first, sequential) |
| Isolation | Main branch |
| Tasks | 1-6 + indicators/base.py |

**Lead responsibilities:**
- Receive Task 1-6 specs from implementation plan
- Craft minimal prompts per worker (only required type definitions + tests)
- Review worker output + run tests
- Commit

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | scaffolding (pyproject.toml, dirs, config) | Project structure spec only |
| Worker 2 | types.py + exceptions.py | Type specs + test code |
| Worker 3 | config.py + event_bus.py + logger.py | Interface specs + test code |

### Broker Lead

| Property | Value |
|----------|-------|
| Subagent type | `backend-architect` |
| Worker count | 2 (`python-expert`) |
| Phase | 2 (parallel) |
| Isolation | worktree |
| Tasks | 7, 14 |

**Lead responsibilities:**
- Extract `core/types.py` and `broker/base.py` specs from Foundation output
- Give workers minimal context (BrokerAdapter ABC + relevant types only)
- Provide Alpaca SDK usage guide
- Review + test

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | BrokerAdapter ABC + PaperBroker | types.py + test code |
| Worker 2 | AlpacaAdapter | ABC definition + Alpaca SDK examples |

### Data Lead

| Property | Value |
|----------|-------|
| Subagent type | `python-expert` |
| Worker count | 2 (`python-expert`, haiku) |
| Phase | 2 (parallel) |
| Isolation | worktree |
| Tasks | 8, 12 |

**Lead responsibilities:**
- Use indicators/base.py (from Foundation) as base for indicator implementation
- Give workers Indicator ABC + Bar type only
- Review mathematical correctness of indicator implementations

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | IndicatorEngine + SMA/EMA/RSI/ATR | Indicator ABC + Bar type + tests |
| Worker 2 | DataStore ABC + SQLiteStore | Bar type + test code |

### Business Lead

| Property | Value |
|----------|-------|
| Subagent type | `python-expert` |
| Worker count | 2 (`python-expert`, haiku) |
| Phase | 2 (parallel) |
| Isolation | worktree |
| Tasks | 9, 10, 11 |

**Lead responsibilities:**
- Coordinate Strategy ABC, RiskManager, Portfolio implementation
- Give workers only needed types + IndicatorSpec
- Review business logic correctness

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | Strategy ABC + Registry + Engine | types + IndicatorSpec + tests |
| Worker 2 | RiskManager + PositionSizer + PortfolioTracker | types + RiskConfig + tests |

### Integration Lead

| Property | Value |
|----------|-------|
| Subagent type | `backend-architect` |
| Worker count | 2 (`python-expert`) |
| Phase | 3 (after merge) |
| Isolation | Main branch |
| Tasks | 13, 15 |

**Lead responsibilities:**
- Verify all Phase 2 outputs are merged
- Resolve cross-module integration issues
- Give workers interface summaries only

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | BacktestEngine + Simulator | All ABC definitions + tests |
| Worker 2 | AutoTrader main.py | All module import list + settings |

### Quality Lead

| Property | Value |
|----------|-------|
| Subagent type | `quality-engineer` |
| Worker count | 2 (`python-expert` + `superpowers:code-reviewer`) |
| Phase | 4 (final) |
| Isolation | Main branch |
| Tasks | 16, 17 |

**Lead responsibilities:**
- Run full test suite
- Coverage analysis
- Delegate code review

**Workers:**

| Worker | Tasks | Context given |
|--------|-------|---------------|
| Worker 1 | Full tests + __init__.py cleanup | Full codebase |
| Worker 2 | Code review | Full codebase + design doc |

## Context Optimization Strategy

| Level | Context held | Token cost |
|-------|-------------|------------|
| Orchestrator | Design doc + Lead status | ~5K |
| Lead | Domain spec + worker results | ~10-15K |
| Worker | Task spec + required types only | ~3-5K |

**Core principles:**
- Workers receive **only types/interfaces needed for their task**
- Leads act as **context gatekeepers** (filter unnecessary information)
- Workers can use **haiku model** for simple implementation tasks (cost savings)
- Leads use **sonnet/opus** for review quality

## Model Selection

| Agent | Model | Rationale |
|-------|-------|-----------|
| Orchestrator | opus | Complex coordination decisions |
| Leads | sonnet | Good balance of capability and speed for review |
| Workers (simple) | haiku | Cost-efficient for focused implementation |
| Workers (complex) | sonnet | Alpaca adapter, backtest engine need more capability |
| Quality workers | sonnet | Review requires deep understanding |

## Merge Strategy

After Phase 2 parallel execution:

1. Each Lead works in isolated worktree with its own branch
2. Orchestrator merges branches in order: Data -> Business -> Broker
3. Integration Lead resolves any conflicts
4. Quality Lead validates the final merged state
