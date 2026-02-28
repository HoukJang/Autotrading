# Strategy Panel Discussion: 12th Backtest Design -- Per-Strategy GDR Architecture

**Date**: 2026-02-28
**Format**: 5-Expert Panel (Restructured) -- Root Cause Analysis and Architectural Redesign
**Predecessor**: 11th Backtest Results + GDR Discussion (strategy-panel-discussion-11th.md, strategy-panel-discussion-11th-gdr.md)
**Data**: 11th Backtest ($100K initial, 251 trading days, S&P 500 universe, seed=42)
**Status**: ARCHITECTURAL DECISION -- Per-Strategy GDR Design

---

## Panel Members (New Roster)

| ID | Role | Style | Key Question |
|---|---|---|---|
| Strat-2 | Portfolio Risk Manager | Portfolio protection, drawdown control | "What is the worst-case correlated scenario?" |
| Strat-4 | Trade Analyst | Data-driven, evidence-based | "What does the data actually show?" |
| Strat-5 | Quant Algorithm Expert | Renaissance-style mathematical rigor | "What does the math say about optimal sizing?" |
| Strat-6 | Trading System Architect (NEW) | Two Sigma/DE Shaw structural design | "Is this a parameter problem or an architecture problem?" |
| Strat-7 | Root Cause / Structure Analyst (NEW) | Bridgewater-style first principles | "Why did this happen, and what structural assumption is wrong?" |

---

## 1. Full Panel Discussion

### Opening: Root Cause Diagnosis

**[Strat-7 (Root Cause Analyst)]**: I want to start this session differently from prior panels. Before we discuss solutions, I need to trace the causal chain from first principles. The 11th backtest is not a failure -- it is a *diagnostic*. It tells us exactly what structural assumption is broken.

The prior panels identified the GDR circular dependency. That diagnosis is correct but incomplete. Let me trace the full root cause chain:

```
Structural Assumption #1: "All strategies share a common risk profile"
  -> WRONG. Solo DD ranges from 1.9% (consec_down) to 48.4% (rsi_mr)
  -> 25x difference in drawdown characteristics

Structural Assumption #2: "Portfolio DD reflects systemic risk"
  -> PARTIALLY WRONG. Portfolio DD is 46.2%, but it is not systemic.
  -> It is DOMINATED by one strategy (rsi_mr = 59% of trades)
  -> consec_down and vol_div are collateral casualties, not risk contributors

Structural Assumption #3: "Throttling the portfolio protects against tail risk"
  -> WRONG IN PRACTICE. The GDR throttles winners more than losers.
  -> Losses already occurred at full risk; recovery happens at quarter risk.
  -> This is like applying the brakes after the crash.

Structural Assumption #4: "A single GDR tier is sufficient for a multi-strategy system"
  -> WRONG BY CONSTRUCTION. When strategies have heterogeneous risk profiles,
     a single control variable cannot optimize for all simultaneously.
     This is the fundamental architectural flaw.
```

The key insight: **this is not a calibration problem, it is a dimensionality problem**. One GDR tier (1 dimension) cannot control three strategies with independent risk profiles (3 dimensions). No amount of threshold tuning will fix this. You need N independent control variables for N independent risk sources.

**[Strat-6 (System Architect)]**: Strat-7 has it exactly right. Let me restate this in architectural terms.

The current system has a **coupling defect**. The GDR module receives a single input (portfolio equity) and produces a single output (tier level) that is broadcast to all strategies uniformly. This is a *shared-state anti-pattern*. It is equivalent to a microservices architecture where one service's failure triggers a circuit breaker that shuts down all services -- including healthy ones.

The question I always ask is: "Is this a parameter problem or an architecture problem?" The answer here is unambiguous. Let me demonstrate with a thought experiment:

```
Thought experiment: Can ANY set of portfolio-level GDR thresholds solve this?

Option A: Widen thresholds (e.g., 30%/50%)
  -> rsi_mr solo DD is 48.4%. Even at 50% Tier 2, the portfolio will still
     spend significant time in Tier 1-2 during rsi_mr losing streaks.
  -> Meanwhile consec_down (DD 1.9%) and vol_div (DD 3.4%) never need
     throttling at all. Wider thresholds give them nothing because they
     never triggered the narrow thresholds either -- they were throttled
     by rsi_mr's drawdown, not their own.
  -> VERDICT: Marginal improvement, does not solve the root cause.

Option B: Tighten thresholds (e.g., 10%/15%)
  -> rsi_mr would be throttled even faster, spending 70%+ days in Tier 2.
  -> consec_down and vol_div still collateral damage.
  -> VERDICT: Makes the problem worse.

Option C: Remove GDR entirely
  -> rsi_mr operates at full 2% risk through its 48% DD.
  -> This is unacceptable for a $1-5K account. A 48% DD on $5K = $2,400 loss.
  -> VERDICT: Unacceptable risk.

Conclusion: No single-variable solution exists. The architecture must change.
```

**[Strat-4 (Trade Analyst)]**: Let me ground Strat-6's analysis in the actual data. The numbers make the case overwhelmingly:

**Solo vs Portfolio Performance Gap -- The Smoking Gun:**

| Strategy | Solo PF | Portfolio PF | Solo DD | Portfolio DD | Solo MFE/MAE | Portfolio MFE/MAE |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| rsi_mr | 1.195 | 1.07 | 48.4% | 46.2%* | 1.08x | 0.99x |
| consec_down | 1.423 | 1.47 | 1.9% | 46.2%* | 1.06x | 0.95x |
| vol_div | 1.279 | 0.55 | 3.4% | 46.2%* | 1.40x | 0.83x |

*All strategies share the same portfolio DD since GDR is portfolio-level.

The critical observation: **vol_div goes from PF 1.279 (profitable solo) to PF 0.55 (deeply unprofitable in portfolio)**. This is not because vol_div's signals degraded. It is because:

1. vol_div generates only 22 trades in the portfolio vs 104 solo (79% trade reduction)
2. GDR throttled vol_div's sizing when it did trade (0.5% risk instead of 2%)
3. Vol_div's MFE/MAE collapses from 1.40x solo to 0.83x portfolio

The 1.40x solo MFE/MAE means vol_div's winning trades move 40% more in favorable direction than adverse. This is an excellent edge that the portfolio GDR is destroying.

consec_down maintains portfolio PF of 1.47 (even better than solo 1.423) because its signals are selective enough that even throttled sizing still captures the edge. But it could generate much more absolute return at full sizing.

**[Strat-5 (Quant Algorithm Expert)]**: Let me quantify the economic damage with mathematical precision.

**Opportunity Cost Decomposition:**

For each strategy, I will compute the theoretical return at full risk capacity vs actual portfolio return:

```
consec_down:
  Solo return: +5.4% ($5,400)
  Portfolio return contribution: +$2,426 (2.4%)
  Capture ratio: 2,426/5,400 = 44.9%
  Lost opportunity: $2,974 (55.1% of solo capacity destroyed)

vol_div:
  Solo return: +4.7% ($4,700)
  Portfolio return contribution: -$2,951 (negative!)
  Capture ratio: NEGATIVE (complete value destruction)
  Lost opportunity: $7,651

rsi_mr:
  Solo return: +5.8% ($5,800)
  Portfolio return contribution: +$1,373 (1.4%)
  Capture ratio: 1,373/5,800 = 23.7%
  Lost opportunity: $4,427

Total solo capacity: $15,900 (15.9% return)
Actual portfolio return: $1,300 (1.3% return)
System efficiency: 1,300/15,900 = 8.2%
```

The system is capturing only **8.2% of its theoretical edge**. Even accounting for the fact that strategies would interact in a portfolio, this is catastrophically low. A well-designed multi-strategy system should capture 60-80% of combined solo edge.

The Kelly criterion provides additional insight. For a strategy with WR=40.8% and PF=1.47 (consec_down), the Kelly fraction is:

```
f* = (p * b - q) / b
where p = 0.408, q = 0.592, b = avg_win/avg_loss

consec_down solo: b = 1.47 (PF as proxy)
f* = (0.408 * 1.47 - 0.592) / 1.47 = 0.006 / 1.47 = 0.004

This is very low Kelly, meaning position sizes should be modest.
But the key point: Kelly says SIZE based on YOUR edge, not someone else's drawdown.
```

Throttling consec_down's sizing based on rsi_mr's drawdown violates the Kelly principle that sizing should reflect the specific trade's edge characteristics.

**[Strat-2 (Portfolio Risk Manager)]**: Hold on. I need to inject a critical caveat before we rush to decouple everything.

All three strategies share a common vulnerability: **they are all mean-reversion/contrarian strategies that buy into weakness**. In a sustained market downturn:

1. rsi_mr buys oversold stocks that continue falling
2. consec_down buys after consecutive red days that continue
3. vol_div buys on volume divergence during capitulation selling

During a genuine bear market regime, ALL THREE strategies fail simultaneously. The correlation of returns is NOT zero. The solo backtests obscure this because each solo test captures the full universe opportunity set without competition from other strategies.

If we decouple GDR per-strategy, we must answer: **what prevents a scenario where rsi_mr is in Tier 2 (its own), consec_down is in Tier 0 (its own), vol_div is in Tier 0 (its own), but the PORTFOLIO is actually down 30% and continuing to lose?**

This is not hypothetical. It is the exact scenario that a portfolio safety net must catch.

**[Strat-7 (Root Cause Analyst)]**: Strat-2's concern is valid and structurally important. Let me model this precisely.

**Counterfactual Analysis: "What if all three strategies had independent GDR in the 11th backtest?"**

Looking at the 11th data:
- rsi_mr generated -$29,984 in stop losses (110 SL exits, avg -$272.58)
- consec_down was net +$2,426 (but throttled)
- vol_div was net -$2,951 (but also throttled)

Under per-strategy GDR, rsi_mr would have been throttled by its own drawdown (which matches the portfolio DD since it dominates). So rsi_mr's behavior would be roughly similar.

But consec_down would have operated at FULL capacity since its own DD never exceeded 2%. This means:
- More consec_down trades (potentially 80-100 instead of 49)
- Each trade at full 2% risk instead of throttled
- Expected additional PnL: ~$3,000-$5,000

Vol_div similarly would operate at full capacity:
- More vol_div trades (potentially 50-80 instead of 22)
- Each trade at full 2% risk
- Expected additional PnL: ~$2,000-$4,000

**Net expected impact**: Portfolio return moves from +1.3% to approximately +6-10%.

**But here is the risk Strat-2 is concerned about**: If both consec_down and vol_div hit losing streaks in a downturn while rsi_mr is already in drawdown, the TOTAL portfolio loss is unbounded by per-strategy GDR because each strategy only watches itself.

This is why the portfolio safety net is not optional. It is architecturally required.

---

### Phase 2: Architecture Design Debate

**[Strat-6 (System Architect)]**: Based on the root cause analysis, let me propose the architecture formally. I am designing this as a **two-layer risk control system**:

```
LAYER 1: Per-Strategy GDR (individual strategy health)
  - Each strategy has independent equity tracking
  - Each strategy has independent tier thresholds
  - Each strategy's tier controls only that strategy's risk and entries
  - Purpose: prevent individual strategy deterioration from affecting others

LAYER 2: Portfolio Safety Net (systemic risk backstop)
  - Monitors total portfolio drawdown
  - When triggered, overrides ALL strategy-level GDR to minimum tier
  - Purpose: catch correlated failures that per-strategy GDR cannot see
```

This is analogous to how modern financial systems work: individual circuit breakers per instrument, plus market-wide circuit breakers (the NYSE has both). Neither alone is sufficient.

**Design Question 1: Equity Attribution Method**

Three options were proposed:

**Option A: Equal Capital Split** (100K/3 = 33.3K per strategy)
- Pro: Simple, clean separation
- Con: Arbitrary. Why equal? consec_down generates fewer but higher-quality trades
- Con: Doesn't reflect actual capital deployment
- My assessment: Too rigid. Rejects.

**Option B: Cumulative PnL Tracking** (track each strategy's contribution to total equity)
- Pro: Reflects actual performance
- Pro: No arbitrary allocation
- Pro: DD calculated as strategy_DD = (peak_cumulative_pnl - current_cumulative_pnl) / total_equity
- Con: Denominator uses total equity, so a strategy with small PnL contribution has artificially low DD%
- My assessment: Good but needs refinement

**Option C: Rolling Win/Loss Ratio** (not equity-based)
- Pro: Directly tracks strategy health
- Con: Doesn't account for position size
- Con: Disconnected from actual DD
- My assessment: Too indirect

**My recommendation: Modified Option B.** Track cumulative PnL per strategy, but compute DD as:

```python
strategy_dd = (peak_strategy_pnl - current_strategy_pnl) / allocated_risk_capital
```

where `allocated_risk_capital` is the maximum dollar amount at risk per strategy at any given time. For RISK_PER_TRADE=2% and MAX_POSITIONS=5, the max concurrent risk per strategy is approximately:

```
max_concurrent_trades_per_strategy = 2 (soft cap)
risk_per_trade = equity * 0.02 = $2,000
allocated_risk_capital = 2 * $2,000 = $4,000 per strategy
```

Wait -- this is getting circular. Let me reconsider.

**[Strat-5 (Quant Algorithm Expert)]**: Strat-6 is overcomplicating the denominator. Let me simplify with a clean mathematical formulation.

The most robust approach is **strategy-specific rolling PnL peak-to-trough**:

```python
# For each strategy, maintain:
strategy_cumulative_pnl[name] = sum of all closed trade PnL for this strategy
strategy_peak_pnl[name] = max(strategy_cumulative_pnl[name]) over rolling window
strategy_dd[name] = strategy_peak_pnl[name] - strategy_cumulative_pnl[name]
```

The key insight: we do NOT need to express this as a percentage of equity. We can express thresholds in absolute dollar terms relative to the strategy's expected PnL profile, or we can normalize by the strategy's average trade size.

However, for consistency with the existing GDR framework (which uses percentage DD), I recommend:

```python
strategy_dd_pct[name] = strategy_dd[name] / total_equity
```

This denominator (total_equity) is the correct normalization because it represents the actual impact of this strategy's drawdown on the total account. A $4,000 drawdown from rsi_mr is 4% of a $100K account regardless of how we "attribute" equity.

**[Strat-4 (Trade Analyst)]**: Strat-5's formulation is clean. Let me validate it against the 11th data.

In the 11th backtest:
```
rsi_mr cumulative PnL: +$1,373
  Peak PnL at some point was likely ~$6,000-8,000 (given solo return of +5.8%)
  Trough PnL was likely ~-$4,000 (given the SL clusters)
  Strategy DD: ~$10,000-12,000 or ~10-12% of equity

consec_down cumulative PnL: +$2,426
  Peak PnL: ~$3,000-4,000
  Trough PnL: ~$0 (very tight equity curve)
  Strategy DD: ~$1,000-2,000 or ~1-2% of equity

vol_div cumulative PnL: -$2,951
  Peak PnL: ~$1,000 (brief early profits)
  Trough PnL: ~-$3,000
  Strategy DD: ~$4,000 or ~4% of equity
```

These are rough estimates. We need to instrument the backtester to track exact per-strategy PnL curves to validate. But the pattern is clear: rsi_mr's strategy DD (10-12%) would trigger its own Tier 1 at reasonable thresholds, while consec_down (1-2%) would never trigger.

**[Strat-7 (Root Cause Analyst)]**: I want to flag a structural risk in Strat-5's formulation before we proceed.

**Circular Dependency Warning:** If strategy DD is computed as `strategy_dd / total_equity`, and total_equity includes the PnL from ALL strategies, then a drawdown in rsi_mr reduces total_equity, which INCREASES the DD percentage for consec_down and vol_div (because their fixed dollar DD is now a larger fraction of a smaller denominator).

This creates a subtle coupling: rsi_mr losses inflate other strategies' DD percentages. The effect is small (consec_down DD might go from 1.0% to 1.1% if total equity drops 10%), but it exists.

**Mitigation**: Use initial_capital (fixed) as the denominator instead of current total_equity:

```python
strategy_dd_pct[name] = strategy_dd[name] / initial_capital
```

This eliminates cross-strategy contamination entirely. A $1,000 DD from consec_down is always 1.0% of $100K, regardless of what rsi_mr does.

**[Strat-6 (System Architect)]**: Strat-7 identifies a real coupling risk. I agree: **use initial_capital as denominator**. This gives us a fully decoupled per-strategy GDR.

Let me now formalize the complete architecture:

```python
# Per-Strategy GDR State
per_strategy_state = {
    "rsi_mean_reversion": {
        "cumulative_pnl": 0.0,
        "peak_pnl": 0.0,        # rolling window peak
        "pnl_history": deque(maxlen=60),  # daily PnL snapshots
        "tier": 0,
    },
    "consecutive_down": { ... },
    "volume_divergence": { ... },
}

# Per-Strategy GDR Thresholds (DIFFERENT per strategy)
per_strategy_thresholds = {
    "rsi_mean_reversion": {"tier1_dd": 0.08, "tier2_dd": 0.15},
    "consecutive_down":   {"tier1_dd": 0.03, "tier2_dd": 0.06},
    "volume_divergence":  {"tier1_dd": 0.04, "tier2_dd": 0.08},
}

# Portfolio Safety Net
PORTFOLIO_SAFETY_NET_DD = 0.20  # 20% total portfolio DD
PORTFOLIO_SAFETY_NET_TIER = 2   # Override all strategies to Tier 2

# Per-Strategy Entry Limits
per_strategy_entries = {
    0: 1,   # Tier 0: each strategy can enter 1/day (total max 3)
    1: 1,   # Tier 1: still 1/day (but at reduced risk)
    2: 0,   # Tier 2: strategy cannot enter at all
}

# Portfolio-Level Entry Cap (regardless of individual tiers)
MAX_DAILY_ENTRIES_TOTAL = 3  # never more than 3 entries/day combined
```

**[Strat-2 (Portfolio Risk Manager)]**: Hold on. I have concerns about several of these numbers.

**Concern 1: rsi_mr thresholds (8%/15%)**

rsi_mr solo DD is 48.4% in the 11th backtest. If we set Tier 2 at 15%, rsi_mr would enter Tier 2 VERY quickly and stay there for most of the test. Its strategy DD of 10-12% (estimated) exceeds the Tier 1 threshold of 8%.

Are we just recreating the original problem but scoped to rsi_mr?

**[Strat-6 (System Architect)]**: That is precisely the point. rsi_mr SHOULD be throttled when it is losing. The difference is: only rsi_mr gets throttled, not consec_down and vol_div.

Under the current system, rsi_mr's losses throttle everyone. Under per-strategy GDR, rsi_mr's losses only throttle rsi_mr. This is the correct behavior.

The question is: can rsi_mr recover from its own Tier 2 with its own throttled sizing? Let me analyze.

At Tier 2 (0.25x risk multiplier), rsi_mr trades at 0.5% risk. With PF 1.07 (portfolio) or 1.195 (solo), the edge per trade is thin. At 0.5% risk, each winning trade generates approximately $150-200 and each loss costs approximately $100-130. The net expected PnL per trade is roughly $10-30.

With 1 entry per day in Tier 2, rsi_mr generates perhaps 15-20 trades per month. At $10-30 net expected per trade, rsi_mr recovers approximately $150-600/month from its own Tier 2 PnL. If its DD is $10,000, recovery takes 17-67 months. This is effectively permanent throttling.

**[Strat-7 (Root Cause Analyst)]**: Strat-6 just identified a critical issue. **If rsi_mr enters Tier 2 and cannot recover within a reasonable timeframe, per-strategy GDR for rsi_mr is equivalent to permanent deactivation.**

This raises the fundamental question: **should rsi_mr exist in this portfolio at all?**

Let me apply counterfactual analysis:

```
Counterfactual: "What if we ran only consec_down + vol_div?"

Solo results:
  consec_down: +5.4%, DD 1.9%, PF 1.423
  vol_div: +4.7%, DD 3.4%, PF 1.279

Combined estimate (no GDR needed since DD < 5%):
  Expected trades: 105 + 104 = 209 (with some overlap reduction)
  Expected return: +8-10%
  Expected DD: 5-8% (correlated component + idiosyncratic)

This EXCEEDS the 3-strategy portfolio return of +1.3% by 6-8x.
```

rsi_mr's contribution is negative in the portfolio context. It generates 59% of trades but contributes only $1,373 while causing GDR throttling that destroys $7,000+ of value from other strategies.

**[Strat-4 (Trade Analyst)]**: Strat-7's counterfactual is compelling but I must flag the data limitations. We have ONE backtest (seed=42) on synthetic data. The solo results for consec_down and vol_div are also on seed=42.

Before concluding "remove rsi_mr," we need multi-seed validation. It is entirely possible that on seed=17, rsi_mr outperforms while consec_down underperforms. The 11th backtest is ONE sample path.

That said, the structural argument about per-strategy GDR is valid regardless of whether we keep or remove rsi_mr. Even if we keep all three strategies, per-strategy GDR prevents the collateral damage pattern.

**[Strat-5 (Quant Algorithm Expert)]**: Let me provide a mathematical framework for setting the per-strategy thresholds.

**Threshold Calibration Principle:** A strategy's GDR Tier 1 threshold should be set at approximately 1.5-2.0x its expected maximum drawdown under normal conditions. This way, Tier 1 only triggers during genuinely abnormal losing streaks, not during routine operation.

From the solo backtests:
```
rsi_mr expected DD: ~48% (but this is one sample!)
  Conservative expected DD range: 30-60% across seeds
  Tier 1 should trigger at: 1.5x * (estimated normal DD)

  PROBLEM: rsi_mr's "normal" DD is already catastrophic.
  If normal DD is 30%, Tier 1 at 45% is meaningless -- the account
  is already devastated.

  This confirms Strat-7's concern: rsi_mr may not be viable as a
  2% risk strategy. Its edge (PF 1.195) is too thin for its volatility.

consec_down expected DD: ~2% (very stable)
  Conservative expected DD range: 1-5% across seeds
  Tier 1 at 2.0x normal: ~4%
  Tier 2 at 3.0x normal: ~6%

vol_div expected DD: ~3.4% (moderate)
  Conservative expected DD range: 2-8% across seeds
  Tier 1 at 2.0x normal: ~7%
  Tier 2 at 3.0x normal: ~10%
```

For rsi_mr, I propose a different approach entirely. Instead of trying to calibrate GDR thresholds for a high-DD strategy, I propose **reducing rsi_mr's base risk to 1%** (half the standard 2%) and using tighter per-strategy GDR thresholds:

```
rsi_mr:
  BASE_RISK = 0.01 (1% instead of 2%)
  Tier 1 at 5% strategy DD -> risk x0.5 -> 0.5%
  Tier 2 at 10% strategy DD -> risk x0.25 -> 0.25%

  At 1% base risk, each SL costs ~$1,000 instead of ~$2,000
  Max concurrent rsi_mr risk: 2 positions * $1,000 = $2,000
  Expected strategy DD at 1% risk: ~24% (half of 48%)
  Tier 1 at 5%: triggers after ~5 consecutive SLs
  Tier 2 at 10%: triggers after ~10 consecutive SLs
  Recovery: at 0.25% risk, each TP generates ~$75-100
  Recovery time from 10% DD ($10K): ~100 trades = ~100 days

  Still slow recovery, but rsi_mr at reduced base risk generates
  proportionally smaller DD contribution to the portfolio.
```

**[Strat-2 (Portfolio Risk Manager)]**: Strat-5's tiered approach for rsi_mr is reasonable. But I want to push harder on the portfolio safety net design.

**Portfolio Safety Net Analysis:**

The safety net must catch the correlated downturn scenario where all three strategies lose simultaneously. The worst case is:

```
Scenario: Broad market sell-off (2022 style, -20% S&P 500)
  - rsi_mr: buys oversold stocks into falling knives
    Expected loss: 20+ SLs in sequence, strategy DD ~15-25%
  - consec_down: buys after 3 red days, market keeps falling
    Expected loss: 5-10 SLs, strategy DD ~5-10%
  - vol_div: buys on volume divergence during capitulation
    Expected loss: 5-8 SLs, strategy DD ~5-8%

Per-strategy GDR response:
  - rsi_mr hits Tier 2 quickly (strategy DD > 10%)
  - consec_down hits Tier 1 (strategy DD > 4%)
  - vol_div hits Tier 1-2 (strategy DD > 7-10%)

Portfolio DD during this period: 15-25%
```

Under per-strategy GDR, each strategy throttles itself. The portfolio DD is the sum of individual strategy DDs weighted by their capital deployment. In a correlated downturn:

- Individual strategy GDRs catch the individual deterioration
- Portfolio safety net catches the aggregate risk

**My recommendation for safety net threshold: 20% total portfolio DD**

At 20% DD on a $100K account, we are down $20,000. This is severe but not catastrophic. The safety net at 20% forces all strategies to Tier 2 (0.25x risk), which means:
- rsi_mr: 0.25% risk (if not already in Tier 2 from its own GDR)
- consec_down: 0.25% risk (overridden from its own Tier 0)
- vol_div: 0.25% risk (overridden from its own Tier 0)
- Total daily entries: 1 (safety net mode)

This is the "emergency brake" that prevents account destruction.

**For a $1-5K account** (the actual trading account size), 20% DD = $200-$1,000. This is survivable. At $1K account, 20% DD leaves $800 -- still enough to trade with reduced sizing.

**[Strat-6 (System Architect)]**: Let me now consolidate the architecture. I have heard all perspectives and am ready to make structural decisions.

---

### Phase 3: Interaction Analysis and Edge Cases

**[Strat-6 (System Architect)]**: Before finalizing, let me analyze the interactions between per-strategy GDR and existing system components.

**Interaction 1: Soft Strategy Cap (_SOFT_STRATEGY_CAP = 2)**

Currently, when 2+ strategies have signals, each strategy is limited to 2 concurrent positions. Under per-strategy GDR:
- If rsi_mr is in Tier 2 (0 entries), its "slot" can be used by consec_down or vol_div
- The soft cap should STILL apply to prevent any single strategy from monopolizing entries
- But the cap should be applied AFTER per-strategy GDR filtering

Recommendation: Keep soft strategy cap at 2, applied after GDR tier check. If a strategy is in Tier 2 (no entries allowed), its capacity redistributes to other strategies naturally.

**Interaction 2: Diversity Bonus (+0.25 for 0 positions, +0.10 for 1 position)**

The diversity bonus in signal ranking encourages spreading across strategies. Under per-strategy GDR, if rsi_mr is throttled, its "slot" opens for other strategies, which the diversity bonus will naturally direct toward.

Recommendation: Keep diversity bonus unchanged. It complements per-strategy GDR well.

**Interaction 3: MAX_TOTAL_POSITIONS = 5**

This is a portfolio-level hard cap. Per-strategy GDR does not change this. Even if all three strategies are in Tier 0, the total positions cannot exceed 5.

Recommendation: Keep at 5. Consider increasing to 6 in 12B to test impact.

**Interaction 4: MAX_DAILY_ENTRIES = 2**

This is currently a portfolio-level cap. Under per-strategy GDR, each strategy has its own entry allowance. The question is whether we need a portfolio-level cap on top.

Recommendation: Yes. MAX_DAILY_ENTRIES_TOTAL = 3 (one per strategy). This is an increase from 2, justified by the per-strategy GDR providing independent risk control. If any strategy is in Tier 1+, its entry slot is effectively unused.

**[Strat-7 (Root Cause Analyst)]**: I want to flag one more structural concern.

**Re-entry Block Interaction:**

Currently, the re-entry block prevents same-symbol re-entry on the same day across ALL strategies. Under per-strategy GDR, if rsi_mr closes a position and blocks the symbol, consec_down cannot enter that symbol either.

This is correct behavior (the block should remain cross-strategy) because it prevents whipsaw on the same symbol. But with per-strategy GDR, there is a subtle issue: rsi_mr closing a losing position (due to SL) blocks the symbol, and consec_down might have a legitimate signal for the same symbol. However, the signal was generated the night before (from the same bar data), so it is likely redundant.

Recommendation: Keep cross-strategy re-entry block. No change needed.

**[Strat-4 (Trade Analyst)]**: Let me address another concern: **backfitting risk**.

The per-strategy GDR thresholds we are proposing are calibrated to the 11th backtest data (seed=42). The solo DD values (1.9%, 3.4%, 48.4%) are single-sample statistics. On different seeds:

- consec_down DD might be 5-10% (still low, but higher)
- vol_div DD might be 8-15%
- rsi_mr DD might be 20-60%

If we set thresholds too tightly based on seed=42 performance, we may find that on seed=17, consec_down spends 40% of days in Tier 2 because its "normal" DD on that seed is higher than expected.

**Mitigation:** Set thresholds with generous margins. Better to err on the side of too-loose thresholds (which means less GDR protection) than too-tight (which recreates the current problem).

**[Strat-5 (Quant Algorithm Expert)]**: Strat-4's backfitting concern is the most important practical issue. Let me propose a principled threshold approach.

**Threshold Design Principle: Set Tier 1 at 2x and Tier 2 at 4x the strategy's expected per-trade risk.**

```
Expected per-trade risk = RISK_PER_TRADE * risk_mult

consec_down: 2% per trade, expected loss ~$2,000
  Tier 1: 2x * $2,000 = $4,000 = 4% of initial capital
  Tier 2: 4x * $2,000 = $8,000 = 8% of initial capital

vol_div: 2% per trade, expected loss ~$2,000
  Tier 1: 2x * $2,000 = $4,000 = 4% of initial capital
  Tier 2: 4x * $2,000 = $8,000 = 8% of initial capital

rsi_mr at reduced base risk (1%): expected loss ~$1,000
  Tier 1: 3x * $1,000 = $3,000 = 3% of initial capital
  Tier 2: 6x * $1,000 = $6,000 = 6% of initial capital
```

Alternatively, express thresholds in terms of consecutive losing trades:
```
consec_down: Tier 1 after ~2 consecutive SLs, Tier 2 after ~4
vol_div: Tier 1 after ~2, Tier 2 after ~4
rsi_mr: Tier 1 after ~3, Tier 2 after ~6 (at 1% risk)
```

This is robust to seed variation because it is calibrated to the risk PARAMETERS, not the historical performance.

**[Strat-2 (Portfolio Risk Manager)]**: I want to stress-test Strat-5's thresholds with the worst-case scenario.

**Worst Case Under Proposed Architecture:**

```
Scenario: All 3 strategies simultaneously hitting Tier 0 (no GDR throttling)
  Each strategy enters 1 trade/day at full risk
  3 entries/day at 2% risk each (rsi_mr at 1%) = 5% total daily risk exposure
  If all 3 SL out: $5,000 loss in one day (5% of account)

  5 consecutive days of full-loss: $25,000 loss (25% of account)
  -> Portfolio safety net triggers at 20%

  Days to reach safety net: ~4 days of maximum loss
```

This is fast enough. The safety net catches catastrophic correlated failure within 4 days of maximum loss. After that, all strategies are forced to Tier 2 (0.25x risk), limiting further damage to ~$1,250/day.

**Question: Should the portfolio safety net be 20% or 15%?**

At 15%, the safety net triggers after ~3 days of maximum loss. This is more conservative but also risks triggering during normal portfolio volatility (especially with per-strategy GDR already handling individual strategy DD).

My recommendation: **20% portfolio safety net**. The per-strategy GDR provides the first line of defense. The safety net is the second line. Setting it at 20% ensures it only triggers during genuinely correlated failure, not during normal single-strategy drawdowns.

For $1-5K accounts: 20% DD = $200-$1,000. This is painful but survivable.

**[Strat-6 (System Architect)]**: Final architecture summary. Let me write the exact specification.

---

## 2. Root Cause Diagnosis (Strat-7 Led)

### Structural Assumptions That Are Wrong

| # | Assumption | Reality | Impact |
|---|---|---|---|
| 1 | All strategies share common risk profile | DD ranges from 1.9% to 48.4% (25x variance) | Single GDR treats heterogeneous strategies as homogeneous |
| 2 | Portfolio DD reflects systemic risk | Portfolio DD is dominated by rsi_mr (59% of trades) | GDR triggers on individual strategy failure, not portfolio stress |
| 3 | Throttling portfolio protects against tail risk | Throttling winners more than losers (asymmetric recovery) | Net effect is value destruction, not protection |
| 4 | One GDR tier controls multi-strategy portfolio | One control variable for N independent risk sources | Dimensionality mismatch -- architecturally unsolvable |

### Circular Dependencies Identified

**Circular Dependency #1: Asymmetric Recovery Drag**
```
rsi_mr loses at 2% risk
  -> portfolio DD increases
  -> GDR Tier 2 activates
  -> ALL strategies trade at 0.5% risk
  -> Winners generate 4x smaller PnL
  -> Recovery takes 4x longer
  -> Prolonged Tier 2
  -> (cycle restarts when rolling window shifts)
```

**Circular Dependency #2: Collateral Throttling Loop**
```
consec_down has positive edge (+$2,426 PnL)
  -> But portfolio GDR restricts it to Tier 2 sizing
  -> consec_down generates less absolute return
  -> Less absolute return means slower portfolio recovery
  -> Slower recovery means longer Tier 2
  -> Longer Tier 2 means more consec_down throttling
```

**Circular Dependency #3: Vol_div Value Destruction**
```
vol_div solo: PF 1.279, +4.7% return, DD 3.4%
vol_div portfolio: PF 0.55, -$2,951, shared DD 46.2%
  -> GDR restricts vol_div based on rsi_mr's DD
  -> Fewer vol_div trades (22 vs 104 solo)
  -> Those trades at 0.25x sizing
  -> Negative PnL due to reduced capture of winning tails
  -> Vol_div becomes a net drag on portfolio
  -> Portfolio DD worsens
  -> More GDR throttling
```

### Counterfactual Analysis

| Scenario | Expected Portfolio Return | Expected DD | Notes |
|---|---|---|---|
| Current (11th actual) | +1.3% | 46.2% | Baseline |
| Remove GDR entirely | +5-8% (est.) | 55-65% (est.) | Unacceptable DD |
| Widen portfolio GDR (25%/40%) | +2-4% (est.) | 40-50% (est.) | Marginal improvement |
| Per-strategy GDR (proposed) | +5-10% (est.) | 20-35% (est.) | Target outcome |
| Remove rsi_mr entirely | +8-10% (est.) | 5-10% (est.) | Radical simplification |

---

## 3. Architecture Recommendation (Strat-6 Led)

### Decision: Per-Strategy GDR APPROVED with Portfolio Safety Net

The panel unanimously agrees that per-strategy GDR is architecturally necessary. The current portfolio-level GDR is not a calibration problem -- it is a structural flaw that cannot be resolved by parameter tuning.

### Exact Implementation Specification

#### Equity Attribution Method: Modified Option B

**Method**: Track cumulative realized PnL per strategy. Compute strategy DD as peak-to-trough PnL divided by initial capital (fixed denominator).

```python
# State per strategy
@dataclass
class StrategyGDRState:
    cumulative_pnl: float = 0.0
    peak_pnl: float = 0.0
    pnl_history: deque = field(default_factory=lambda: deque(maxlen=60))
    tier: int = 0

# Computation
def update_strategy_gdr(state: StrategyGDRState, trade_pnl: float, initial_capital: float):
    state.cumulative_pnl += trade_pnl
    state.peak_pnl = max(state.peak_pnl, state.cumulative_pnl)
    state.pnl_history.append(state.cumulative_pnl)

    # Rolling peak from history window
    rolling_peak = max(state.pnl_history)
    strategy_dd = (rolling_peak - state.cumulative_pnl) / initial_capital

    # Determine tier
    ...
```

**Rationale**: Fixed denominator (initial_capital) eliminates cross-strategy contamination. Rolling 60-day window allows recovery. PnL-based tracking is accurate and simple.

#### Per-Strategy GDR Thresholds

| Strategy | Base Risk | Tier 1 DD | Tier 1 Risk | Tier 2 DD | Tier 2 Risk |
|---|---|---|---|---|---|
| rsi_mean_reversion | 1.0% (REDUCED) | 3% | 0.5% | 6% | 0.25% |
| consecutive_down | 2.0% | 4% | 1.0% | 8% | 0.5% |
| volume_divergence | 2.0% | 4% | 1.0% | 8% | 0.5% |

**rsi_mr base risk reduction rationale**: rsi_mr's edge (PF 1.195) is too thin relative to its volatility for 2% risk. At 1% base risk:
- Each SL costs ~$1,000 instead of ~$2,000
- Max concurrent rsi_mr risk: 2 * $1,000 = $2,000
- Expected strategy DD: ~24% (half of 48%)
- This DD STILL triggers per-strategy GDR tiers, but with smaller absolute dollar impact

**Threshold calibration rationale**: Tier 1 at approximately 2 consecutive SLs worth of risk, Tier 2 at approximately 4 consecutive SLs. This is parameter-anchored (not data-fitted) and robust to seed variation.

#### Per-Strategy Entry Limits

| Tier | Entries per Strategy | Risk Multiplier |
|---|---|---|
| Tier 0 (Normal) | 1 per day | 1.0x (base risk) |
| Tier 1 (Reduced) | 1 per day | 0.5x |
| Tier 2 (Minimal) | 0 per day (halted) | 0.0x |

```
MAX_DAILY_ENTRIES_TOTAL = 3 (portfolio-level cap, one per strategy at max)
```

**Tier 2 = HALT rationale**: If a strategy has accumulated enough DD to hit Tier 2, it should stop entering entirely until the rolling peak shifts and DD recovers below Tier 1. This prevents the slow-recovery trap where tiny Tier 2 trades cannot recover the DD that put the strategy into Tier 2.

Recovery mechanism: The 60-day rolling window means the peak PnL will naturally reset as older high-PnL days fall off. After ~30-40 days of no new entries, the strategy DD resets toward zero, and the strategy returns to Tier 0.

#### Portfolio Safety Net

```python
PORTFOLIO_SAFETY_NET_DD = 0.20      # 20% total portfolio DD triggers override
PORTFOLIO_SAFETY_NET_TIER = 2        # Override ALL strategies to Tier 2 (halted)
PORTFOLIO_SAFETY_NET_ENTRIES = 1     # Allow only 1 entry/day for best-ranked signal
PORTFOLIO_SAFETY_NET_RISK = 0.005    # Override risk to 0.5% regardless of strategy
```

**Behavior**: When total portfolio equity drops 20% from rolling 60-day peak, ALL strategies are forced to effective Tier 2 (no new entries from halted strategies, 1 safety net entry at 0.5% risk for the highest-ranked signal regardless of strategy).

**Exit from safety net**: When portfolio DD recovers below 15%, per-strategy GDR resumes normal operation.

#### Interaction with Existing Components

| Component | Change Required | Details |
|---|---|---|
| Soft strategy cap (2) | Keep as-is | Applied after GDR tier check |
| Diversity bonus (+0.25/+0.10) | Keep as-is | Natural complement to per-strategy GDR |
| MAX_TOTAL_POSITIONS (5) | Keep at 5 | Portfolio-level hard cap unchanged |
| MAX_LONG (4) / MAX_SHORT (3) | Keep as-is | Direction caps unchanged |
| Re-entry block | Keep as-is | Cross-strategy block still appropriate |
| Gap filter (5%) | Keep as-is | Independent of GDR |
| Breakeven activation (0.6 ATR) | Keep as-is | Exit-side, independent of GDR |
| SL/TP multipliers | Keep as-is | No change to exit rules |

---

## 4. Risk Assessment (Strat-2 Led)

### What Could Go Wrong

| Risk | Probability | Severity | Mitigation |
|---|---|---|---|
| Correlated failure across all strategies | Medium | High | Portfolio safety net at 20% DD |
| rsi_mr base risk reduction eliminates its contribution | Medium | Low | Still 1% risk; if edge exists, it earns |
| Per-strategy thresholds too tight (over-throttling) | Low | Medium | Thresholds set at 2-4x per-trade risk, generous |
| Per-strategy thresholds too loose (under-protection) | Low | High | Portfolio safety net catches aggregate failure |
| Total daily entries increase (3 vs 2) causes more exposure | Medium | Medium | Per-strategy GDR limits each strategy; net exposure may actually decrease |
| Backfitting to seed=42 data | Medium | Medium | Multi-seed validation required (12C test) |
| Increased complexity causes implementation bugs | Medium | High | Careful unit testing; compare portfolio-level vs per-strategy results |

### Worst Case Scenario Analysis

**Worst Case #1: All strategies in Tier 0, all lose simultaneously**
```
Day 1: 3 entries (one per strategy) at 1% + 2% + 2% risk
  All 3 SL out: ~$5,000 loss (5% of account)
  Per-strategy DDs: rsi_mr 1%, consec_down 2%, vol_div 2%

Day 2: Repeat (all strategies still in Tier 0)
  Total loss: ~$10,000 (10% of account)
  Per-strategy DDs: rsi_mr 2%, consec_down 4%, vol_div 4%
  -> consec_down and vol_div hit Tier 1 (reduce to 1% risk)

Day 3: rsi_mr at 1%, consec_down at 1%, vol_div at 1%
  All SL out: ~$3,000 loss
  Total portfolio loss: ~$13,000 (13%)
  rsi_mr hits Tier 1 (DD > 3%)

Day 4: rsi_mr at 0.5%, consec_down at 1%, vol_div at 1%
  All SL out: ~$2,500 loss
  Total portfolio loss: ~$15,500 (15.5%)

Day 5: Continue pattern, total loss approaching 18%
  rsi_mr hits Tier 2 (DD > 6%, halted)
  Portfolio DD approaches 20% -> safety net triggers
```

**Timeline to safety net: ~5 days of maximum correlated loss**

After safety net triggers: all strategies halted except 1 safety entry at 0.5% risk. Maximum further daily loss: ~$500 (0.5% of account). This is manageable.

**Worst Case #2: rsi_mr enters permanent Tier 2**
```
rsi_mr accumulates 6%+ strategy DD
  -> Tier 2: halted (0 entries)
  -> After 30-40 days, rolling peak resets
  -> rsi_mr returns to Tier 0
  -> If rsi_mr immediately hits another losing streak, cycle repeats

Impact on portfolio: Minimal. rsi_mr is halted but consec_down and vol_div
continue at full capacity. The portfolio runs as a 2-strategy system during
rsi_mr's hiatus.
```

This is actually DESIRABLE behavior. The system naturally adapts its active strategy set based on recent performance.

---

## 5. Mathematical Validation (Strat-5 Led)

### Expected Impact on Tier Distribution

**Current (Portfolio-Level GDR):**
| Tier | Days | % |
|---|---|---|
| Tier 0 | 98 | 39% |
| Tier 1 | 26 | 10% |
| Tier 2 | 127 | 51% |

**Expected (Per-Strategy GDR) -- Conservative Estimate:**

For rsi_mr (1% base risk, 3%/6% thresholds):
| Tier | Days (est.) | % |
|---|---|---|
| Tier 0 | 100-120 | 40-48% |
| Tier 1 | 30-50 | 12-20% |
| Tier 2 (halted) | 80-120 | 32-48% |

For consec_down (2% base risk, 4%/8% thresholds):
| Tier | Days (est.) | % |
|---|---|---|
| Tier 0 | 220-240 | 88-96% |
| Tier 1 | 5-20 | 2-8% |
| Tier 2 (halted) | 0-10 | 0-4% |

For vol_div (2% base risk, 4%/8% thresholds):
| Tier | Days (est.) | % |
|---|---|---|
| Tier 0 | 200-230 | 80-92% |
| Tier 1 | 10-30 | 4-12% |
| Tier 2 (halted) | 5-20 | 2-8% |

**Effective portfolio capacity improvement:**
```
Current: Effective risk utilization = 56.8% (all strategies throttled equally)

Proposed (conservative):
  rsi_mr: 40% at 1.0% + 15% at 0.5% + 45% at 0% = 0.475% effective
  consec_down: 90% at 2.0% + 5% at 1.0% + 5% at 0% = 1.85% effective
  vol_div: 85% at 2.0% + 10% at 1.0% + 5% at 0% = 1.80% effective

  Combined effective daily risk exposure:
    0.475% + 1.85% + 1.80% = 4.125% total effective

  Compared to current: (3 strategies * 1.135% effective) = 3.405% total effective

  Improvement: 4.125 / 3.405 = 1.21x (21% improvement in risk deployment)
```

### Expected Return Range (Conservative)

```
Lower bound (pessimistic): +3.0% ($3,000)
  Assumptions: rsi_mr contributes nothing (permanently throttled)
  consec_down: 70% of solo capacity = 0.70 * $5,400 = $3,780
  vol_div: 60% of solo capacity = 0.60 * $4,700 = $2,820
  Total: $6,600 minus rsi_mr residual losses ~$3,000 = $3,600 (3.6%)
  Conservative haircut: $3,000 (3.0%)

Upper bound (optimistic): +8.0% ($8,000)
  Assumptions: All strategies capture 60-75% of solo capacity
  rsi_mr: 30% of solo = $1,740
  consec_down: 75% of solo = $4,050
  vol_div: 60% of solo = $2,820
  Total: $8,610 minus correlation drag ~$1,000 = $7,610 (7.6%)
  Round: $8,000 (8.0%)

Central estimate: +5.0% ($5,000)

Max DD estimate: 20-30% (vs 46.2% current)
  rsi_mr's reduced base risk cuts its DD contribution by 50%
  Per-strategy GDR prevents rsi_mr DD from inflating beyond 6%
  Portfolio safety net caps total DD at 20% plus residual
```

**Warning**: These estimates assume seed=42 performance. Multi-seed validation may narrow or widen these ranges significantly. The 10th backtest overconfidence error must not be repeated.

---

## 6. Data Validation (Strat-4 Led)

### Data Points Supporting the Proposal

| Evidence | Supports | Strength |
|---|---|---|
| Solo vs portfolio MFE/MAE degradation (vol_div: 1.40x -> 0.83x) | Per-strategy GDR preserves individual edge | Strong |
| Solo vs portfolio trade count reduction (vol_div: 104 -> 22) | Entry throttling destroys opportunity set | Strong |
| GDR tier distribution (51% Tier 2) | Current thresholds are too aggressive | Strong |
| consec_down solo DD 1.9% vs portfolio DD 46.2% | Cross-contamination is massive | Strong |
| rsi_mr PF 1.195 solo vs 1.07 portfolio | GDR suppresses rsi_mr's own edge capture | Moderate |
| Portfolio return 1.3% vs combined solo ~15.9% | System efficiency at 8.2% | Strong |

### Data Points Contradicting or Cautioning Against the Proposal

| Evidence | Concern | Strength |
|---|---|---|
| Single seed (seed=42) backtesting | All results may be seed-specific | Critical |
| All strategies are mean-reversion/contrarian | Correlated failure risk is real | Strong |
| rsi_mr solo DD 48.4% | Even per-strategy GDR may not save rsi_mr | Moderate |
| Synthetic data (not real market data) | Real markets have different tail behavior | Moderate |

### Multi-Seed Validation Requirement

The panel UNANIMOUSLY requires multi-seed validation before approving implementation for live trading:

| Seed | Purpose |
|---|---|
| 42 | Primary (comparison to 11th baseline) |
| 17 | Alternative market regime |
| 99 | Stress test |
| 7 | Low-volatility scenario |
| 2024 | Additional diversity |

Minimum requirement: 3 seeds (42, 17, 99). Preferred: all 5.

Acceptance: Per-strategy GDR must outperform portfolio-level GDR on at least 3 of 5 seeds on return AND max DD.

---

## 7. Final Recommendations Table

| Priority | Change | Current | Proposed | Expected Impact | Risk Level |
|---|---|---|---|---|---|
| P0 | Per-strategy GDR architecture | Single portfolio-level tier | Independent tier per strategy | Return: +1.3% -> +3-8% | Medium |
| P0 | Portfolio safety net | None (only portfolio GDR) | 20% DD triggers all-halt override | Prevents correlated blowup | Low |
| P0 | rsi_mr base risk reduction | 2.0% | 1.0% | Halves rsi_mr DD contribution | Low |
| P1 | Per-strategy thresholds | 15%/25% portfolio-level | 3%/6% rsi_mr, 4%/8% others | Strategy-appropriate throttling | Medium |
| P1 | Tier 2 = full halt | Tier 2 = 0.25x risk, 1 entry | Tier 2 = 0 entries, 0 risk | Prevents slow-recovery trap | Low |
| P1 | MAX_DAILY_ENTRIES | 2 (portfolio) | 3 total (1 per strategy) | 50% more entry capacity | Medium |
| P2 | Equity attribution | N/A | Cumulative PnL / initial_capital | Decoupled strategy DD calc | Low |
| P2 | Rolling window | 60 days | 60 days (unchanged) | N/A | N/A |
| P3 | Multi-seed validation | Single seed | 3-5 seeds per test | Reduces backfitting risk | Low |

---

## 8. Sub-Test Plan

### 12A: Per-Strategy GDR (Primary Proposal)

```python
# --- Per-Strategy GDR Configuration ---
PER_STRATEGY_GDR = True
EQUITY_ATTRIBUTION = "cumulative_pnl_over_initial_capital"

# rsi_mr: reduced base risk + tighter per-strategy thresholds
RSI_MR_BASE_RISK = 0.01          # 1% (reduced from 2%)
RSI_MR_TIER1_DD = 0.03           # 3% strategy DD
RSI_MR_TIER2_DD = 0.06           # 6% strategy DD

# consec_down: standard risk + moderate thresholds
CONSEC_DOWN_BASE_RISK = 0.02     # 2%
CONSEC_DOWN_TIER1_DD = 0.04      # 4% strategy DD
CONSEC_DOWN_TIER2_DD = 0.08      # 8% strategy DD

# vol_div: standard risk + moderate thresholds
VOL_DIV_BASE_RISK = 0.02         # 2%
VOL_DIV_TIER1_DD = 0.04          # 4% strategy DD
VOL_DIV_TIER2_DD = 0.08          # 8% strategy DD

# GDR Risk Multipliers (same for all strategies)
GDR_RISK_MULT = {0: 1.0, 1: 0.5, 2: 0.0}  # Tier 2 = HALT

# Entry limits
PER_STRATEGY_ENTRIES = {0: 1, 1: 1, 2: 0}  # per strategy per day
MAX_DAILY_ENTRIES_TOTAL = 3

# Portfolio Safety Net
PORTFOLIO_SAFETY_NET_DD = 0.20    # 20% total portfolio DD
PORTFOLIO_SAFETY_NET_ENTRIES = 1  # 1 entry total in safety net mode
PORTFOLIO_SAFETY_NET_RISK = 0.005 # 0.5% risk in safety net mode

# Unchanged from 11th
MAX_TOTAL_POSITIONS = 5
MAX_LONG_POSITIONS = 4
MAX_SHORT_POSITIONS = 3
SOFT_STRATEGY_CAP = 2
GDR_ROLLING_WINDOW = 60
SL_ATR_MULT = {rsi_mr: {long: 1.0, short: 1.5}, consec_down: {long: 1.0}, vol_div: {long: 1.0}}
BREAKEVEN_ACTIVATION_ATR = 0.6
```

### 12B: Simplified Alternative (Wider Portfolio GDR + rsi_mr Risk Reduction)

Tests whether simpler changes achieve most of the benefit without architectural complexity.

```python
# --- Portfolio-Level GDR (widened thresholds) ---
PER_STRATEGY_GDR = False
GDR_TIER1_DD = 0.25              # 25% (was 15%)
GDR_TIER2_DD = 0.40              # 40% (was 25%)

# rsi_mr base risk still reduced
RSI_MR_BASE_RISK = 0.01          # 1% (reduced from 2%)

# All other strategies at standard risk
CONSEC_DOWN_BASE_RISK = 0.02
VOL_DIV_BASE_RISK = 0.02

# GDR Risk Multipliers
GDR_RISK_MULT = {0: 1.0, 1: 0.5, 2: 0.25}

# Entry limits
MAX_DAILY_ENTRIES = 2             # Unchanged
GDR_MAX_ENTRIES = {0: 2, 1: 1, 2: 1}

# Unchanged from 11th
MAX_TOTAL_POSITIONS = 5
MAX_LONG_POSITIONS = 4
MAX_SHORT_POSITIONS = 3
SOFT_STRATEGY_CAP = 2
GDR_ROLLING_WINDOW = 60
```

### 12C: Multi-Seed Control (11th Config on Different Seeds)

Validates whether 11th results are seed-specific. Uses the EXACT 11th configuration unchanged.

```python
# --- Identical to 11th configuration ---
PER_STRATEGY_GDR = False
GDR_TIER1_DD = 0.15
GDR_TIER2_DD = 0.25
RISK_PER_TRADE_PCT = 0.02         # All strategies at 2%
MAX_DAILY_ENTRIES = 2
GDR_RISK_MULT = {0: 1.0, 1: 0.5, 2: 0.25}
MAX_TOTAL_POSITIONS = 5

# Run on seeds: 17, 99, 7, 2024 (seed=42 is the existing 11th result)
```

### Test Execution Order

1. **12C first** (multi-seed control): Establishes the seed-sensitivity baseline
2. **12B second** (simplified): Tests the minimal-change hypothesis
3. **12A last** (per-strategy GDR): Tests the full architectural proposal

Rationale: Running 12C first tells us whether 11th results are an outlier or representative. If seed=17 and seed=99 show dramatically different patterns, we know the problem is data-specific, not structural. If they show similar patterns (GDR over-throttling), the structural argument is confirmed.

---

## 9. PASS/FAIL Criteria for 12th Backtest

### 12A (Per-Strategy GDR) PASS Criteria

| Metric | PASS Threshold | FAIL Threshold | Weight |
|---|---|---|---|
| Total Return | >= +3.0% | < +1.0% | Critical |
| Max DD | <= 35% | > 45% | Critical |
| Profit Factor | >= 1.10 | < 0.95 | Important |
| Win Rate | >= 30% | < 25% | Important |
| consec_down portfolio PF | >= 1.30 | < 1.00 | Important |
| vol_div portfolio PF | >= 1.00 | < 0.70 | Important |
| rsi_mr portfolio PF | >= 1.00 | < 0.80 | Nice-to-have |
| consec_down Tier 0 days | >= 80% | < 60% | Diagnostic |
| vol_div Tier 0 days | >= 70% | < 50% | Diagnostic |
| Portfolio safety net triggers | <= 3 times | > 10 times | Diagnostic |
| Sharpe Ratio | >= 0.80 | < 0.50 | Nice-to-have |

### 12B (Simplified) PASS Criteria

| Metric | PASS Threshold | FAIL Threshold |
|---|---|---|
| Total Return | >= +2.0% | < +1.0% |
| Max DD | <= 40% | > 50% |
| Profit Factor | >= 1.05 | < 0.95 |
| Tier 0 days | >= 50% | < 35% |

### 12C (Multi-Seed Control) Evaluation

No pass/fail -- this is a diagnostic run. Metrics to collect:

| Metric per Seed | Purpose |
|---|---|
| Total return | Seed sensitivity of returns |
| Max DD | Seed sensitivity of drawdown |
| GDR tier distribution | Is over-throttling consistent across seeds? |
| Per-strategy PnL | Strategy contribution stability |
| Per-strategy trade count | Signal frequency stability |

### Decision Matrix (After All Tests Complete)

| 12A Result | 12B Result | 12C Result | Decision |
|---|---|---|---|
| PASS | PASS | Consistent | Deploy 12A (per-strategy GDR superior) |
| PASS | FAIL | Consistent | Deploy 12A (simplified insufficient) |
| FAIL | PASS | Consistent | Deploy 12B (simpler is enough) |
| FAIL | FAIL | Consistent | Fundamental strategy redesign needed |
| PASS | PASS | Inconsistent | Deploy 12B (simpler is safer given data instability) |
| Any | Any | Highly variable | Pause. Data quality/synthetic model is the issue, not GDR |

### 10th Backtest Overconfidence Guard

The 10th panel predicted +6-10% return; the 11th actual was +1.3%. This panel must not repeat that error.

**Calibration rules:**
1. All "expected" ranges must include a downside that is WORSE than current 11th performance
2. No claim of "guaranteed improvement" -- only "expected improvement with stated uncertainty"
3. Any prediction with confidence > 70% must be explicitly justified with 3+ data points
4. The FAIL thresholds define the actual minimum bar, not the PASS thresholds

---

## Panel Summary and Sign-Off

### Key Decisions Made

1. **Per-strategy GDR: APPROVED** -- Architecturally necessary, not a parameter tuning exercise
2. **Equity attribution: Modified Option B** -- Cumulative PnL / initial_capital (fixed denominator)
3. **rsi_mr base risk: REDUCED to 1%** -- Edge too thin for 2% risk at current volatility
4. **Tier 2 = Full Halt** -- Prevents slow-recovery trap; natural recovery via rolling window
5. **Portfolio safety net: 20% DD** -- Catches correlated failure; per-strategy GDR is first line
6. **MAX_DAILY_ENTRIES: 3** (increased from 2) -- One per strategy, portfolio cap
7. **Multi-seed validation: REQUIRED** -- 12C runs before 12A to establish baseline

### Unresolved Questions (Carry Forward)

1. Should rsi_mr be removed entirely from the portfolio? Data suggests yes, but requires multi-seed confirmation.
2. What is the optimal rolling window for per-strategy GDR? 60 days may be too long for strategies with few trades.
3. Should the portfolio safety net use a different rolling window than per-strategy GDR?
4. Should there be a "Tier -1" (aggressive) when a strategy is on a winning streak? (Inverse GDR for momentum)

### Panel Member Sign-Off

| Member | Verdict | Key Concern |
|---|---|---|
| Strat-2 (Risk Manager) | CONDITIONAL APPROVE | Correlated downturn risk; safety net MUST be implemented alongside per-strategy GDR |
| Strat-4 (Trade Analyst) | APPROVE | Multi-seed validation is essential; single-seed results are insufficient evidence |
| Strat-5 (Quant Expert) | APPROVE | Thresholds should be parameter-anchored, not data-fitted; proposed thresholds meet this criterion |
| Strat-6 (System Architect) | STRONG APPROVE | This is an architecture problem, not a parameter problem; per-strategy GDR is the correct structural fix |
| Strat-7 (Root Cause Analyst) | APPROVE | Root cause chain is clear; all 4 structural assumptions are addressed by the proposal |

---

*Generated by Strategy Team Panel (Restructured) -- 2026-02-28*
*Next: Implement 12C (multi-seed control), then 12B, then 12A*
