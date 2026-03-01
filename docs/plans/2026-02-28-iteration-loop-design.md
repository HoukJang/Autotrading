# Strategy Iteration Loop Design

## Goal

Beat S&P 500 buy-and-hold across multiple time periods using team-driven sequential optimization.

## Benchmark

| Period | S&P 500 Return | S&P 500 MaxDD |
|--------|---------------|---------------|
| Period 1 (2024-03 ~ 2025-02) | TBD (download) | TBD |
| Period 2 (2025-03 ~ 2026-02) | +15.5% | -16.3% |

## Current State

| Metric | 18A (P0 best) | 19A (P1) | Target |
|--------|--------------|----------|--------|
| Return | +10.9% | +9.1% | - |
| MaxDD | -29.2% | -16.8% | - |
| Sharpe | ~0.5 | ~0.5 | >= 1.0 |
| Calmar | 0.37 | 0.54 | >= 1.0 |

## Success Criteria

- Sharpe >= 1.0 OR Calmar >= 1.0
- Must pass on BOTH periods (Period 1 + Period 2)

## Architecture: Sequential Iteration Loop

```
┌─────────────────────────────────────────────────┐
│              ITERATION LOOP (max 15)             │
│                                                  │
│  Step 1: Strategy Team Analysis                  │
│    Input: previous backtest JSON                 │
│    Output: change proposal (PARAM_TUNE or        │
│            NEW_STRATEGY)                         │
│                                                  │
│  Step 2: Dev Team Implementation                 │
│    Input: change proposal                        │
│    Output: code changes (file ownership enforced)│
│                                                  │
│  Step 3: Test Team - Unit Tests                  │
│    Input: code changes                           │
│    Output: all tests passing                     │
│                                                  │
│  Step 4: Test Team - Backtest (Period 2)         │
│    Input: updated codebase                       │
│    Output: backtest result JSON + metrics        │
│                                                  │
│  Step 5: Result Evaluation                       │
│    Sharpe >= 1.0 OR Calmar >= 1.0?               │
│    YES → Multi-period validation                 │
│    NO  → Back to Step 1                          │
│                                                  │
│  Safety: 3 consecutive no-improvement →          │
│          strategy team direction change           │
│  Safety: 15 iterations → stop, user decision     │
└─────────────────────────────────────────────────┘

Multi-period Validation:
  Run backtest on Period 1 (2024-03 ~ 2025-02)
  BOTH periods pass? → Commit + version bump + merge to beta
  Only 1 passes? → Back to iteration loop
```

## Team Roles

### Strategy Team (Strat-1~4, business-panel-experts)

Analyze backtest results and produce change proposals.

**Analysis Framework (per iteration):**
1. Per-strategy Win Rate / PF / Edge Ratio comparison
2. Top 5 losing trades root cause analysis
3. MFE vs realized profit (Heat Captured) — leaving money on table?
4. MAE vs SL distance — SL too wide or too tight?
5. Per-regime performance decomposition — which regime loses money?

**Proposal Format:**

```
ITERATION #N Change Proposal
─────────────────────────────
TYPE: PARAM_TUNE | NEW_STRATEGY

[When PARAM_TUNE]
Diagnosis: [core issue, 1 line]
Change 1: [file:param] current -> proposed (rationale)
Change 2: ...
Expected effect: [Return/MaxDD/Sharpe direction]
Risk: [potential side effects]

[When NEW_STRATEGY]
Diagnosis: gap in current strategy portfolio
Strategy name: [snake_case]
Concept: [1-2 line description]
Entry conditions: [specific conditions]
Exit conditions: [specific conditions]
Required indicators: [IndicatorSpec list]
Regime fit: [which regimes it works in]
Expected effect: [portfolio complement effect]
```

**New Strategy Trigger:**
- 5 consecutive PARAM_TUNE iterations without reaching Sharpe/Calmar 0.8
- Strategy team identifies regime gap (no strategy performs in a regime)
- Strategy team autonomous judgment

### Dev Team

| Agent | Owns | Role |
|-------|------|------|
| Dev-2 (backend-architect) | batch/ | batch_simulator.py changes |
| Dev-3 (python-expert) | execution/, main.py | exit_rules.py, main.py changes |
| Dev-4 (devops-architect) | scripts/ | backtest script creation |

For NEW_STRATEGY:
- Dev-3: create `autotrader/strategy/[name].py` (ABC pattern)
- Dev-2: register in batch_simulator.py
- Dev-3: add SL/TP params in exit_rules.py
- Orchestrator approval required for FROZEN strategy files

### Test Team

| Agent | Owns | Role |
|-------|------|------|
| Test-1 (quality-engineer) | tests/ | Unit test updates, full suite pass |
| Test-2 (performance-engineer) | backtest/ | Backtest script + execution |

## Data Strategy

### Period 2 (existing)
- File: `data/historical_bars.pkl`
- Range: 2025-02-28 ~ 2026-02-27
- Symbols: 453 (S&P 500)
- Used for: iteration loop (fast feedback)

### Period 1 (to download)
- File: `data/historical_bars_period1.pkl`
- Range: 2024-03-01 ~ 2025-02-28
- Symbols: same 453
- Used for: multi-period validation only

## Metrics Calculation

### Sharpe Ratio
- Daily returns from equity curve
- Sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)
- Risk-free rate: 0

### Calmar Ratio
- Calmar = annualized_return / abs(max_drawdown)
- annualized_return = (final_equity / initial_equity - 1) * (252 / trading_days)

### S&P 500 Benchmark
- Download via yfinance for each period
- Calculate same metrics for comparison

## Iteration Results Log

```
data/backtest_results/iterations/
  iter_01_proposal.md     # strategy team proposal
  iter_01_result.json     # backtest result
  iter_02_proposal.md
  iter_02_result.json
  ...
  final_period1.json      # multi-period validation
  final_period2.json
```

## Tunable Parameters (80+)

### High Impact
- Regime allocation weights (16 params: 4 strategies x 4 regimes)
- Per-strategy GDR thresholds (6 params)
- Base risk per trade (4 params)
- RSI entry thresholds (8 params across strategies)

### Medium Impact
- ATR multipliers for SL/TP (12 params)
- Max hold days (3 params)
- 2-stage SL upgrade thresholds (3 params)
- Position caps (5 params)

### Low Impact
- Emergency stop thresholds (3 params)
- Trailing stop settings (2 params)
- Gap filter / slippage (3 params)

## Guardrails

1. **Max 15 iterations** — prevent infinite loop
2. **1-3 params per iteration** — track causation
3. **3 consecutive no-improvement** — force direction change
4. **File ownership enforced** — orchestrator never implements
5. **All tests must pass** — no skipping validation
6. **Strategy team docs** — every iteration documented in `docs/analysis/`
