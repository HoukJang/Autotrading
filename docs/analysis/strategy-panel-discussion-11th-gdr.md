# Strategy Panel Discussion: Per-Strategy GDR Architecture

**Date**: 2026-02-28
**Format**: 5-Expert Panel -- Focused Debate on GDR Architecture
**Predecessor**: 11th Backtest Analysis (strategy-panel-discussion-11th.md)
**Scope**: Per-strategy independent GDR vs portfolio-level single GDR
**Status**: DESIGN DECISION REQUIRED

---

## Panel Members

| ID | Role | Expertise |
|---|---|---|
| Strat-1 | Swing Trade Specialist | Entry/exit timing, SL/TP optimization, risk/reward calibration |
| Strat-2 | Portfolio Risk Manager | Drawdown control, correlation management, portfolio-level risk |
| Strat-3 | Market Microstructure Expert | Slippage, gap risk, order execution, market dynamics |
| Strat-4 | Trade Analyst | Statistical analysis, backtesting methodology, edge quantification |
| Strat-5 | Quant Algorithm Expert | Mathematical optimization, Kelly criterion, statistical modeling |

---

## Problem Statement

The 11th backtest revealed that the portfolio-level GDR creates a **collateral damage** problem. One poorly-performing strategy (rsi_mr, solo DD 48.4%) drags the entire portfolio into Tier 2 (0.5% risk), throttling strategies with excellent standalone drawdown profiles (consec_down DD 1.9%, vol_div DD 3.4%). Result: the system operates at minimal capacity for 51% of trading days.

### Current GDR Implementation (Single Portfolio-Level)

```
_GDR_ROLLING_WINDOW = 60      # 60-day rolling peak
_GDR_TIER1_DD = 0.15           # DD > 15% -> Tier 1 (risk x0.5, 1 entry/day)
_GDR_TIER2_DD = 0.25           # DD > 25% -> Tier 2 (risk x0.25, 1 entry/day)
```

One `self._gdr_tier` integer controls ALL strategies uniformly.

### 11th Backtest Key Data

| Strategy | Portfolio Trades | Solo PF | Solo DD | Solo Return | Portfolio PF |
|---|:---:|:---:|:---:|:---:|:---:|
| rsi_mr | 103 (59%) | 1.195 | 48.4% | +5.8% | 1.07 |
| consec_down | 49 | 1.423 | 1.9% | +5.4% | 1.47 |
| vol_div | 22 | 1.279 | 3.4% | +4.7% | 0.55 |

GDR Tier Distribution:
- Tier 0: 98 days (39%) -- full capacity
- Tier 1: 26 days (10%) -- half capacity
- Tier 2: 127 days (51%) -- quarter capacity

**Effective risk utilization: 56.8% of designed capacity.**

---

## Panel Discussion

### Phase 1: Problem Diagnosis

**[Strat-4 (Trade Analyst)]**: Before discussing solutions, I want to quantify exactly how much the current GDR is costing us. Let me decompose the 11th result.

At full capacity (Tier 0 all year), each strategy could have generated:
```
rsi_mr:      103 trades at 2% risk -> avg PnL/trade = $56 -> total $5,768
consec_down: 49 trades at 2% risk  -> avg PnL/trade = $110 -> total $5,400 (approx)
vol_div:     22 trades at 2% risk  -> avg PnL/trade = $214 -> total $4,700 (approx)
```

But 61% of trading days were in Tier 1 or 2. For those days, risk was reduced to 0.5-1.0%, cutting winning trade PnL by 50-75% while the losing trades that CREATED the drawdown already occurred at full 2% risk. The asymmetry is devastating.

The actual portfolio return was +1.3% ($1,300). If consec_down and vol_div had operated at full capacity throughout, even while rsi_mr was in Tier 2, the estimated additional return is:
```
consec_down Tier 2 days with reduced PnL: ~30 trades affected
  Lost PnL per trade: avg $110 * (1.0 - 0.25) = ~$82/trade
  Total opportunity cost: ~$2,460

vol_div Tier 2 days with reduced PnL: ~13 trades affected
  Lost PnL per trade: avg $214 * (1.0 - 0.25) = ~$160/trade
  Total opportunity cost: ~$2,080

Total collateral damage: ~$4,540
```

That is **3.5x the actual portfolio return** lost to collateral GDR throttling. The GDR intended to protect against rsi_mr's losses is destroying more value through collateral suppression than it is preventing in risk.

**[Strat-2 (Portfolio Risk Manager)]**: Strat-4's math is alarming but directionally correct. However, I need to push back on the framing. The GDR's purpose is not to maximize return -- it is to prevent catastrophic drawdown. If removing the GDR from consec_down and vol_div increases total risk exposure during stress periods, we could face a scenario where ALL three strategies hit losing streaks simultaneously.

The question is: what is the probability of correlated drawdowns across all three strategies? If they trade the same S&P 500 universe with the same daily bars, there IS correlation risk. A broad market sell-off hits all three strategies simultaneously.

**[Strat-5 (Quant Algorithm Expert)]**: Strat-2 raises the right concern. Let me analyze the correlation structure from the 11th data.

rsi_mr is a mean-reversion strategy (buys oversold conditions). consec_down buys after consecutive red days (also mean-reversion in nature). vol_div buys on volume divergence (also contrarian). All three are fundamentally contrarian/mean-reversion strategies that BUY into weakness. This means they share a common risk factor: all three fail simultaneously in sustained downtrends.

However, the magnitude of their exposure differs dramatically:
- rsi_mr: aggressive entries (103 trades/year), high SL rate (64%), generates large drawdowns
- consec_down: selective entries (49 trades/year), excellent risk control, DD stays under 2%
- vol_div: very selective (22 trades/year), moderate edge, low DD

Even if all three strategies enter losing streaks during a market downturn, consec_down and vol_div will generate much smaller dollar losses per trade because their edge profiles are fundamentally better-controlled. The risk of "all three blowing up simultaneously" is real in direction but NOT equal in magnitude.

**[Strat-1 (Swing Trade Specialist)]**: From a trade-level perspective, I see another angle. The current GDR throttles not just risk size but also entry count (Tier 1/2: 1 entry/day). When consec_down gets a perfect setup -- 3 consecutive down days on a fundamentally strong stock -- but the portfolio GDR says "1 entry/day" and rsi_mr already used that slot, consec_down's high-quality signal is discarded entirely.

This is the most damaging aspect: not just reduced position size, but complete signal suppression. The 1 entry/day limit in Tier 2 means strategies compete for a single daily slot, and there is no priority mechanism. A marginal rsi_mr signal might claim the slot before a superior consec_down signal.

**[Strat-3 (Market Microstructure Expert)]**: Adding the execution dimension. In Tier 2, the system takes positions at 0.5% risk. For a $100K account, that is $500 risk per trade. With a 1.0 ATR SL distance (typical for our strategies), and ATR around $3-5 for most S&P 500 stocks, the position size becomes:

```
qty = $500 / $4.0 (avg ATR) = 125 shares
cost = 125 * $150 (avg stock price) = $18,750
```

At Tier 0, the same trade would be:
```
qty = $2,000 / $4.0 = 500 shares
cost = 500 * $150 = $75,000
```

Tier 2 positions are so small that commissions and slippage become proportionally significant. At $0.005/share commission and 0.03% slippage:
- Tier 2: commission $1.25, slippage $5.63 -> total friction $6.88 on $500 risk = **1.4% of risk budget consumed by friction**
- Tier 0: commission $5.00, slippage $22.50 -> total friction $27.50 on $2,000 risk = **1.4% of risk budget consumed by friction**

Actually, the friction ratio is similar. I retract the execution cost concern -- it scales proportionally. The real execution issue is that Tier 2 generates too-small positions that barely move the equity needle. A winning trade at Tier 2 generates $150-300 profit. At 32.8% WR, you need many such wins to recover a single Tier 0 loss.

---

### Phase 2: Equity Attribution Methods

**[Strat-5 (Quant Algorithm Expert)]**: The central technical challenge of per-strategy GDR is equity attribution. Each strategy does not have its own capital pool. They share one account. I see four candidate methods:

**Method 1: Virtual Capital Split**
```
virtual_allocation[s] = initial_capital / N_strategies
strategy_equity[s] = virtual_allocation[s] + cumulative_pnl[s]
strategy_dd[s] = (strategy_peak[s] - strategy_equity[s]) / strategy_peak[s]
```
Problem: Virtual allocation is arbitrary. If we add a 4th strategy, every existing strategy's DD calculation changes retroactively. Also, position sizing uses total equity, not virtual allocation, creating a disconnect.

**Method 2: Rolling Trade Performance**
```
recent_trades[s] = last 20 trades for strategy s
win_rate[s] = wins / total
loss_streak[s] = current consecutive losses
GDR triggered by: loss_streak > threshold OR win_rate < threshold
```
Problem: Trade-count-based metrics have high variance with small samples. vol_div with 22 trades/year has only ~1.7 trades per rolling-20 window per month. Unstable.

**Method 3: PnL Contribution DD (my recommendation)**
```
cumulative_pnl[s] = sum of all closed trade PnL for strategy s
rolling_peak_pnl[s] = max(cumulative_pnl[s]) over last 60 equity snapshots
pnl_dd[s] = rolling_peak_pnl[s] - cumulative_pnl[s]  (in dollars)
strategy_dd_pct[s] = pnl_dd[s] / current_total_equity
```
This measures each strategy's drawdown contribution as a percentage of total portfolio equity. No artificial capital split needed. The denominator (total equity) is the true resource being protected.

**Method 4: Normalized Risk-Adjusted DD**
```
capital_deployed[s] = sum of recent position sizes for strategy s
pnl_dd[s] = (same as Method 3)
strategy_dd_pct[s] = pnl_dd[s] / avg_capital_deployed[s]
```
Problem: Capital deployed fluctuates daily with position entries/exits. Over-complicated.

I strongly recommend **Method 3**: PnL Contribution DD. It is clean, attributable, and uses the correct denominator (total equity). Every dollar of PnL belongs unambiguously to one strategy. The DD is measured relative to the thing we care about protecting -- the whole account.

**[Strat-2 (Portfolio Risk Manager)]**: I agree with Method 3 conceptually, but I want to stress-test it with the 11th data.

In the 11th backtest, rsi_mr generated $5,800 total return but had a solo DD of 48.4% on $100K. Within the portfolio context, rsi_mr's PnL path would show cumulative peaks and troughs. Let me estimate:

rsi_mr has 103 trades, WR ~30%, avg win $566, avg loss -$269. Over 251 trading days, there are extended losing streaks (MaxCL = 19). During a 19-trade losing streak:
```
Losses: 19 * $269 = $5,111 cumulative PnL decline
As % of portfolio equity (~$100K): 5.1%
```

At 2% risk per trade and 1.0 ATR SL, each SL loss is approximately $2,000. But wait -- not every loss is a full SL hit. Some are partial losses from time exits. The avg loss of $269 seems too small. Let me reconsider.

Actually, the 11th backtest avg loss is $269 because GDR was already active. Many losses occurred at Tier 2 (0.5% risk), so losses were $500 * some fraction. The TIER 0 losses would be around $2,000 * (SL hit rate). This confirms the asymmetry problem.

For per-strategy GDR thresholds, I need the question: "At what PnL contribution DD should we start worrying about a strategy?"

**[Strat-4 (Trade Analyst)]**: Let me derive appropriate thresholds from the 11th data and theoretical expectations.

For Method 3 (PnL Contribution DD as % of total equity):

**rsi_mr expected behavior**:
- At full 2% risk, a losing streak of 5 trades = 5 * ~$1,500 avg SL loss = $7,500 = 7.5% of $100K
- A losing streak of 10 = $15,000 = 15% contribution DD
- A losing streak of 19 (observed MaxCL) = $28,500 = 28.5% contribution DD
- With 30% WR and 103 trades/year, a 10-trade losing streak is statistically expected (~once per year)

**consec_down expected behavior**:
- Solo DD 1.9% on $100K = $1,900 max contribution DD ever observed
- At full 2% risk, losing streak of 5 = ~$5,000 = 5% contribution DD
- With 49 trades/year, this is less likely but possible

**vol_div expected behavior**:
- Solo DD 3.4% on $100K = $3,400 max contribution DD ever observed
- With only 22 trades/year, extended losing streaks are shorter
- A 5-trade losing streak = ~$5,000 = 5% contribution DD

Based on this analysis, I propose **strategy-specific thresholds**:

| Strategy | Tier 1 Threshold | Tier 2 Threshold | Rationale |
|---|:---:|:---:|---|
| rsi_mr | 8% | 15% | 10-trade losing streak is normal; 15+ is stress |
| consec_down | 4% | 8% | Solo DD 1.9%; 4% is already 2x normal max |
| vol_div | 4% | 8% | Solo DD 3.4%; 4% is just above normal max |

**[Strat-1 (Swing Trade Specialist)]**: I want to challenge Strat-4's thresholds for rsi_mr. You are proposing Tier 1 at 8% contribution DD. But rsi_mr at full 2% risk will routinely contribute 7-8% DD from normal losing streaks. We would be putting rsi_mr into Tier 1 during its normal operating mode, which partially recreates the original problem.

The point of per-strategy GDR is to let strategies breathe within their expected volatility range. I would argue for **wider** thresholds for rsi_mr:

| Strategy | Tier 1 Threshold | Tier 2 Threshold | Rationale |
|---|:---:|:---:|---|
| rsi_mr | 12% | 20% | Expected losing streaks produce 7-10% DD; only throttle truly exceptional stress |
| consec_down | 4% | 8% | Tight because normal DD is tiny; any significant DD signals strategy failure |
| vol_div | 4% | 8% | Same logic as consec_down |

**[Strat-5 (Quant Algorithm Expert)]**: Both proposals have merit. Let me approach this mathematically.

The key principle: GDR should activate when the observed drawdown exceeds what is statistically expected at some confidence level. I will use the concept of a "drawdown surprise."

For a strategy with win rate p and average loss L:
```
Expected max DD over N trades = L * max_consecutive_losses(p, N, confidence)
```

Using the geometric distribution approximation:
```
Expected max consecutive losses = log(N * (1-p)) / log(1-p)
```

For rsi_mr (p=0.30, N=103):
```
Expected MaxCL = log(103 * 0.70) / log(0.70) = log(72.1) / log(0.70) = 4.28 / 0.357 = 12.0
```

So a 12-trade losing streak is the expected maximum over 103 trades. At ~$1,500 per SL loss (full risk):
```
Expected max contribution DD = 12 * $1,500 / $100,000 = 18%
```

GDR Tier 1 should trigger ABOVE the expected maximum. I propose:
```
Tier 1 = 1.0x expected max DD (triggers at the expected worst case)
Tier 2 = 1.5x expected max DD (triggers at genuinely exceptional stress)
```

| Strategy | Expected MaxCL | Expected Max DD | Tier 1 (1.0x) | Tier 2 (1.5x) |
|---|:---:|:---:|:---:|:---:|
| rsi_mr | 12 | 18% | 18% | 27% |
| consec_down | 5 | 4% | 4% | 6% |
| vol_div | 4 | 3.5% | 3.5% | 5% |

**[Strat-2 (Portfolio Risk Manager)]**: Strat-5's statistical approach is rigorous, but I have a practical concern. With rsi_mr Tier 1 at 18%, the strategy can contribute 18% drawdown before ANY throttling. If consec_down and vol_div are also in mild drawdowns (say 2% each), total portfolio DD would be 22% before any GDR activates.

That is acceptable IF we have a portfolio-level safety net. But without one, the system could reach 30%+ DD with all strategies in Tier 0. That exceeds our stated max DD tolerance.

I **require** a portfolio-level safety net for this design to be viable. Proposal:
```
PORTFOLIO_GDR_TIER1 = 0.25  # total DD > 25% -> all strategies min Tier 1
PORTFOLIO_GDR_TIER2 = 0.35  # total DD > 35% -> all strategies Tier 2
```

This ensures the system cannot reach catastrophic territory even if per-strategy GDR thresholds are generous.

---

### Phase 3: Architecture Decision

**[Strat-3 (Market Microstructure Expert)]**: Before we finalize, I want to address the entry limit question. The current GDR controls two things:
1. Risk multiplier (how big each trade is)
2. Entry limit (how many trades per day)

For per-strategy GDR, I propose we **decouple** these:
- **Risk multiplier**: per-strategy (controlled by per-strategy GDR tier)
- **Entry limit**: portfolio-level (kept at MAX_DAILY_ENTRIES, modified only by portfolio-level safety net)

Reasoning: Entry limits exist to prevent overcommitting capital in a single day. That is a portfolio-level concern, not a strategy-level one. Whether we enter 2 consec_down trades or 1 rsi_mr + 1 consec_down, the capital commitment is similar.

If we make entry limits per-strategy, the interaction becomes chaotic. Three strategies in Tier 0 could generate 3 x 2 = 6 entries/day. That contradicts our position limits (_MAX_TOTAL_POSITIONS = 5).

**[Strat-1 (Swing Trade Specialist)]**: I agree with Strat-3's decoupling proposal. Entry limits should remain portfolio-level. But I want to add one refinement: **priority ordering by GDR tier**.

When multiple strategies have pending signals and the daily entry limit constrains selection, strategies in LOWER GDR tiers (healthier performance) should get priority. This ensures the best-performing strategies claim available slots before throttled strategies.

Implementation: During signal ranking, add a GDR tier factor to the composite score. Tier 0 signals get a bonus, Tier 2 signals get a penalty.

**[Strat-4 (Trade Analyst)]**: Strat-1's priority mechanism is clever but potentially dangerous from a backtest validity perspective. It introduces path-dependent behavior where the order of signal processing affects which trades are taken. This makes the backtest harder to validate and more sensitive to implementation details.

I suggest a simpler rule: **Tier 2 strategies are excluded from signal generation entirely.** If a strategy is in Tier 2, it generates zero signals for that day. Tier 1 strategies generate signals normally but at reduced risk sizing. Tier 0 strategies operate fully.

This is cleaner and avoids the ranking interaction complexity.

**[Strat-2 (Portfolio Risk Manager)]**: I disagree with Strat-4's "exclude Tier 2 from signals" proposal. That effectively recreates the old circuit breaker for that strategy. The whole point of GDR is graduated response, not binary on/off.

Let me propose the consensus architecture:

**HYBRID GDR ARCHITECTURE**:

1. **Per-strategy GDR** controls the **risk multiplier** for each strategy independently
2. **Portfolio-level GDR** provides a **safety net** that overrides when total DD is extreme
3. **Entry limits remain portfolio-level** (MAX_DAILY_ENTRIES = 2)
4. **Signal ranking** is unmodified; all strategies generate signals regardless of GDR tier
5. When a strategy's signal is selected for entry, ITS specific GDR tier determines the position size

**[Strat-5 (Quant Algorithm Expert)]**: I support Strat-2's architecture. Let me formalize the complete specification.

---

### Phase 4: Simplicity vs Complexity Trade-off

**[Strat-4 (Trade Analyst)]**: Before we finalize the per-strategy approach, I must raise the alternative: **simply widening the portfolio-level GDR thresholds**.

Current: Tier 1 at 15%, Tier 2 at 25%.
Proposed alternative: Tier 1 at 25%, Tier 2 at 35%.

This is a one-line change. It would reduce Tier 2 days from 51% to perhaps 20-25%, giving the system more operating room. No equity attribution needed, no per-strategy tracking, no additional state management.

Expected impact:
```
If Tier 2 days drop from 127 to ~50:
  - ~77 additional Tier 0/1 days
  - ~77 * 1.39 avg entries * 1.135% avg risk -> more capacity
  - But also more exposure during drawdowns
```

The question is: does the added complexity of per-strategy GDR justify the benefit over simply widening thresholds?

**[Strat-5 (Quant Algorithm Expert)]**: Strat-4 raises a fair point. Let me quantify both approaches.

**Approach A: Widen portfolio GDR to 25%/35%**
- Pros: One-line change, zero complexity increase
- Cons: rsi_mr DD still throttles consec_down and vol_div; just delays the throttling
- When DD is between 15-25%, consec_down and vol_div are STILL throttled even though they are performing well
- Expected Tier 2 days: ~50 (down from 127)
- Expected Tier 0 days: ~160 (up from 98)

**Approach B: Per-strategy GDR**
- Pros: Strategies operate independently; good performance is never penalized by bad
- Cons: More complex implementation (~50 lines of code), requires threshold calibration
- consec_down and vol_div would be in Tier 0 for ~95% of days (their solo DDs are tiny)
- Only rsi_mr would experience GDR activation
- Expected system capacity: ~85-90% (vs current 57%)

The benefit is quantifiable. Per-strategy GDR recovers approximately $4,000-5,000/year in collateral damage (Strat-4's earlier estimate). Approach A recovers perhaps $2,000-3,000 by widening thresholds. The incremental benefit of per-strategy GDR is $1,500-2,500/year on $100K.

More importantly, per-strategy GDR is **architecturally correct**. As we add more strategies in the future, the collateral damage problem grows linearly with portfolio GDR but stays constant with per-strategy GDR. It is a one-time investment in the right abstraction.

**[Strat-3 (Market Microstructure Expert)]**: I agree with Strat-5. From an execution perspective, per-strategy GDR also enables better capital allocation. When consec_down operates at full 2% risk during a period where rsi_mr is throttled, the capital is being deployed to the strategy with the best recent track record. This is essentially a dynamic allocation mechanism disguised as risk control.

**[Strat-1 (Swing Trade Specialist)]**: I want to add one more consideration. In live trading, if I see consec_down consistently generating $100 winners instead of $400 winners because the GDR is throttling it due to rsi_mr's losses, I would manually override the GDR for consec_down. Per-strategy GDR automates this correct human judgment.

**[Strat-2 (Portfolio Risk Manager)]**: The panel consensus appears to favor per-strategy GDR. I concur, WITH the mandatory portfolio-level safety net. The implementation complexity is modest (I estimate 40-60 lines in batch_simulator.py), and the benefit is both immediate (more capacity) and structural (scales with future strategies).

Let me note one risk: per-strategy GDR is harder to explain to a non-technical observer. "Why is rsi_mr trading at 0.5% risk while consec_down trades at 2%?" requires understanding the equity attribution mechanism. But this is a documentation concern, not an architectural one.

---

### Phase 5: Threshold Calibration Debate

**[Strat-5 (Quant Algorithm Expert)]**: We have not reached consensus on the thresholds. Let me present a calibrated proposal based on the statistical analysis and the panel's input.

**Principle**: Each strategy's GDR thresholds should reflect its **expected drawdown profile**, with Tier 1 triggering at the expected max DD and Tier 2 triggering at 1.5x expected max DD.

However, I want to simplify. Instead of different thresholds per strategy, we can use **uniform percentage thresholds** with the understanding that the per-strategy PnL contribution DD will naturally differ by strategy volatility.

Consider: if all strategies have the same thresholds (e.g., 5% and 10% contribution DD), the low-DD strategies (consec_down, vol_div) will almost never trigger, while the high-DD strategy (rsi_mr) will trigger during normal losing streaks.

Let me test uniform thresholds of 5%/10% against the 11th data:

**rsi_mr at uniform 5%/10%**:
- 10-trade losing streak at full risk: ~$15,000 = 15% contribution DD -> well above both thresholds
- Would enter Tier 2 after ~7 consecutive losses ($10,500 = 10.5%)
- Expected: Tier 0 for ~60% of year, Tier 1 for ~15%, Tier 2 for ~25%
- This is STILL throttling rsi_mr too aggressively during normal operation

**rsi_mr at 10%/18%**:
- Enters Tier 1 after ~7 losses ($10,000)
- Enters Tier 2 after ~12 losses ($18,000)
- Expected: Tier 0 for ~80% of year, Tier 1 for ~10%, Tier 2 for ~10%
- This matches the statistical expectation better

**consec_down at uniform 5%/10%**:
- Solo DD 1.9% means cumulative PnL rarely drops more than $2,000
- At 5% threshold ($5,000), almost never triggers
- Expected: Tier 0 for ~98% of year

**vol_div at uniform 5%/10%**:
- Solo DD 3.4%, similar profile to consec_down
- Expected: Tier 0 for ~95% of year

Given this analysis, uniform thresholds of 5%/10% work well for consec_down and vol_div but are too tight for rsi_mr. We have two options:

**Option X: Uniform thresholds with wider values (8%/15%)**
- Works for rsi_mr (Tier 0 ~75% of year)
- Works for consec_down and vol_div (Tier 0 ~99% of year)
- Simple: same constants for all strategies
- Risk: if a new strategy has very tight DD profile, 8% might be too generous

**Option Y: Per-strategy threshold configuration**
- rsi_mr: 10%/18%
- consec_down: 4%/8%
- vol_div: 4%/8%
- More precise but requires recalibration when strategy behavior changes
- Adds configuration complexity

**[Strat-4 (Trade Analyst)]**: I favor Option X (uniform 8%/15%) for the 12th backtest. Here is my reasoning:

1. We are TESTING the per-strategy GDR architecture. Adding per-strategy threshold tuning introduces another variable. We cannot attribute results to the architecture vs the threshold calibration.

2. Uniform thresholds make the A/B comparison cleaner. We change ONE thing (per-strategy vs portfolio) and keep thresholds consistent.

3. After we validate the architecture works, we can tune thresholds in a subsequent backtest (13th).

**[Strat-1 (Swing Trade Specialist)]**: I support Strat-4's testing methodology. Test the architecture first with uniform thresholds, tune later. But I want to run TWO threshold variants to bound the sensitivity:

- 12A: Per-strategy GDR with 5%/10% thresholds (tight)
- 12B: Per-strategy GDR with 10%/20% thresholds (loose)

If both outperform the 11th baseline (portfolio GDR at 15%/25%), the architecture is validated regardless of threshold choice. If only one outperforms, threshold calibration matters and we need to investigate further.

**[Strat-2 (Portfolio Risk Manager)]**: I agree with the two-variant approach. But I want to fix the portfolio-level safety net for both variants:

```
PORTFOLIO_SAFETY_TIER1_DD = 0.25  # total DD > 25% -> all strategies min Tier 1
PORTFOLIO_SAFETY_TIER2_DD = 0.35  # total DD > 35% -> all strategies Tier 2
```

This ensures we never exceed 35% portfolio DD without maximum throttling, regardless of per-strategy thresholds.

**[Strat-5 (Quant Algorithm Expert)]**: I want to add a third test variant for completeness:

- 12C: Portfolio GDR only, but widened thresholds (25%/35%)

This is the "simple alternative" baseline. If 12C performs as well as 12A/12B, the complexity of per-strategy GDR is not justified. If 12A or 12B outperforms 12C, per-strategy GDR proves its value.

**[Strat-3 (Market Microstructure Expert)]**: Agreed. Three variants gives us a proper comparison:
1. Per-strategy GDR tight (12A)
2. Per-strategy GDR loose (12B)
3. Portfolio GDR widened (12C, control)

All three should be compared against the 11th baseline (portfolio GDR at 15%/25%).

---

## Panel Consensus

### Decision: APPROVE Per-Strategy GDR (Hybrid Architecture)

**Vote**: 5-0 in favor of per-strategy GDR with portfolio-level safety net.

**Rationale**:
1. The collateral damage from portfolio-level GDR costs approximately $4,500/year on $100K -- 3.5x the actual portfolio return
2. Per-strategy GDR eliminates collateral throttling while maintaining strategy-level risk control
3. Implementation complexity is modest (~50-70 lines of new code in batch_simulator.py)
4. The architecture scales correctly with future strategy additions
5. Portfolio-level safety net preserves catastrophic risk protection

### Dissent Notes
- Strat-2 emphasizes the portfolio safety net is NON-NEGOTIABLE
- Strat-4 notes this adds testing complexity and requires the 12C control variant for validation

---

## Implementation Specification (for Dev-3)

### 1. New Constants

```python
# Per-strategy GDR thresholds
# Contribution DD = (strategy_pnl_peak - strategy_pnl_current) / current_total_equity
# 12A variant uses tight thresholds, 12B variant uses loose thresholds.

# 12A: Tight per-strategy thresholds
_PER_STRATEGY_GDR_TIER1_DD_12A: float = 0.05   # 5% contribution DD -> Tier 1
_PER_STRATEGY_GDR_TIER2_DD_12A: float = 0.10   # 10% contribution DD -> Tier 2

# 12B: Loose per-strategy thresholds
_PER_STRATEGY_GDR_TIER1_DD_12B: float = 0.10   # 10% contribution DD -> Tier 1
_PER_STRATEGY_GDR_TIER2_DD_12B: float = 0.20   # 20% contribution DD -> Tier 2

# 12C: Portfolio GDR only (widened from 15%/25% to 25%/35%)
_PORTFOLIO_GDR_TIER1_DD_12C: float = 0.25
_PORTFOLIO_GDR_TIER2_DD_12C: float = 0.35

# Portfolio-level safety net (used in 12A and 12B variants)
_PORTFOLIO_SAFETY_TIER1_DD: float = 0.25   # total DD > 25% -> all strategies min Tier 1
_PORTFOLIO_SAFETY_TIER2_DD: float = 0.35   # total DD > 35% -> all strategies Tier 2

# GDR risk multipliers (unchanged from current implementation)
_GDR_RISK_MULT: dict[int, float] = {
    0: 1.0,    # Tier 0: normal  (RISK_PER_TRADE_PCT * 1.0 = 2%)
    1: 0.5,    # Tier 1: reduced (RISK_PER_TRADE_PCT * 0.5 = 1%)
    2: 0.25,   # Tier 2: minimal (RISK_PER_TRADE_PCT * 0.25 = 0.5%)
}

# Entry limits remain portfolio-level (unchanged)
_GDR_MAX_ENTRIES: dict[int, int] = {
    0: 2,   # 2 entries/day
    1: 2,   # 2 entries/day (no longer reduced by strategy GDR)
    2: 1,   # 1 entry/day (only via portfolio safety net)
}
```

### 2. New State Variables

```python
# Replace single self._gdr_tier with per-strategy tracking:

# Per-strategy cumulative PnL tracking
self._strategy_cumulative_pnl: dict[str, float] = {}
# Per-strategy rolling peak PnL (60-day window via deque of snapshots)
self._strategy_pnl_history: dict[str, deque[float]] = {}
# Per-strategy GDR tier
self._strategy_gdr_tier: dict[str, int] = {}
# Portfolio-level GDR tier (safety net)
self._portfolio_gdr_tier: int = 0

# Initialize for each strategy:
for strategy_cls in _STRATEGY_CLASSES:
    name = strategy_cls.name
    self._strategy_cumulative_pnl[name] = 0.0
    self._strategy_pnl_history[name] = deque(maxlen=_GDR_ROLLING_WINDOW)
    self._strategy_gdr_tier[name] = 0
```

### 3. PnL Attribution

When a trade closes, attribute PnL to the strategy:

```python
def _close_position(self, sym: str, exit_price: float, exit_reason: str,
                    bar_date: date) -> BatchTradeRecord:
    pos = self._positions[sym]
    # ... existing PnL calculation ...

    # NEW: Attribute PnL to strategy
    strategy_name = pos.held.strategy
    self._strategy_cumulative_pnl[strategy_name] += pnl

    # ... rest of existing close logic ...
```

### 4. Per-Strategy GDR Update Logic

```python
def _update_gdr(self) -> None:
    """Update per-strategy GDR tiers and portfolio safety net.

    Called once per trading day after equity snapshot.

    Per-strategy GDR:
      - Track each strategy's cumulative PnL
      - Compute contribution DD = (peak_pnl - current_pnl) / total_equity
      - Assign tier based on contribution DD thresholds

    Portfolio safety net:
      - Compute total portfolio DD from rolling 60-day peak
      - If total DD exceeds safety thresholds, override strategy tiers upward
    """
    # Step 1: Update per-strategy GDR tiers
    for strategy_name in self._strategy_cumulative_pnl:
        current_pnl = self._strategy_cumulative_pnl[strategy_name]
        self._strategy_pnl_history[strategy_name].append(current_pnl)

        if not self._strategy_pnl_history[strategy_name]:
            self._strategy_gdr_tier[strategy_name] = 0
            continue

        rolling_peak_pnl = max(self._strategy_pnl_history[strategy_name])
        pnl_dd = rolling_peak_pnl - current_pnl  # dollars below peak

        if self._equity <= 0:
            self._strategy_gdr_tier[strategy_name] = 0
            continue

        contribution_dd = pnl_dd / self._equity  # as fraction of total equity

        prev_tier = self._strategy_gdr_tier[strategy_name]
        if contribution_dd > self._per_strat_tier2_dd:
            self._strategy_gdr_tier[strategy_name] = 2
        elif contribution_dd > self._per_strat_tier1_dd:
            self._strategy_gdr_tier[strategy_name] = 1
        else:
            self._strategy_gdr_tier[strategy_name] = 0

        if self._strategy_gdr_tier[strategy_name] != prev_tier:
            logger.info(
                "Strategy GDR [%s]: tier %d -> %d (contribution_dd=%.1f%%, "
                "pnl=%.0f, peak_pnl=%.0f, equity=%.0f)",
                strategy_name, prev_tier, self._strategy_gdr_tier[strategy_name],
                contribution_dd * 100, current_pnl, rolling_peak_pnl, self._equity,
            )

    # Step 2: Update portfolio-level safety net
    self._equity_history.append(self._equity)
    if self._equity_history:
        rolling_peak = max(self._equity_history)
        if rolling_peak > 0:
            portfolio_dd = (rolling_peak - self._equity) / rolling_peak

            prev_portfolio_tier = self._portfolio_gdr_tier
            if portfolio_dd > self._portfolio_safety_tier2_dd:
                self._portfolio_gdr_tier = 2
            elif portfolio_dd > self._portfolio_safety_tier1_dd:
                self._portfolio_gdr_tier = 1
            else:
                self._portfolio_gdr_tier = 0

            if self._portfolio_gdr_tier != prev_portfolio_tier:
                logger.info(
                    "Portfolio GDR safety net: tier %d -> %d "
                    "(portfolio_dd=%.1f%%, peak=%.0f, equity=%.0f)",
                    prev_portfolio_tier, self._portfolio_gdr_tier,
                    portfolio_dd * 100, rolling_peak, self._equity,
                )

    # Step 3: Apply safety net override (raise strategy tiers if portfolio is stressed)
    if self._portfolio_gdr_tier > 0:
        for strategy_name in self._strategy_gdr_tier:
            if self._strategy_gdr_tier[strategy_name] < self._portfolio_gdr_tier:
                self._strategy_gdr_tier[strategy_name] = self._portfolio_gdr_tier
```

### 5. Entry Logic Modification

In `_process_entries()`, change from single GDR tier to per-strategy lookup:

```python
def _process_entries(self, pending_signals, day_bars, trading_date):
    # Portfolio-level entry limit (from portfolio safety net tier)
    portfolio_entry_limit = _GDR_MAX_ENTRIES[self._portfolio_gdr_tier]
    effective_daily_entries = min(self._max_daily_entries, portfolio_entry_limit)

    if self._portfolio_gdr_tier > 0:
        logger.info(
            "Portfolio GDR safety net Tier %d: entry limit=%d",
            self._portfolio_gdr_tier, effective_daily_entries,
        )

    # ... existing loop over pending_signals ...

    for sym, scan_result, prev_close in pending_signals:
        # ... existing position/direction/gap checks ...

        # Get THIS strategy's GDR tier for risk sizing
        strategy_name = scan_result.strategy
        strategy_tier = self._strategy_gdr_tier.get(strategy_name, 0)
        strategy_risk_mult = _GDR_RISK_MULT[strategy_tier]

        if strategy_tier > 0:
            logger.info(
                "Strategy GDR [%s] Tier %d: risk_mult=%.2f",
                strategy_name, strategy_tier, strategy_risk_mult,
            )

        # ... existing ATR/equity/fill_price calculation ...

        qty = self._calculate_qty(
            equity=equity,
            fill_price=fill_price,
            stop_distance=stop_distance,
            gdr_risk_mult=strategy_risk_mult,  # PER-STRATEGY mult (was global)
        )

        # ... rest of entry logic unchanged ...
```

### 6. Config Parameter for Variant Selection

```python
class BatchBacktester:
    def __init__(
        self,
        initial_capital: float = 100_000.0,
        gdr_mode: str = "per_strategy",  # "per_strategy" | "portfolio_only"
        per_strat_tier1_dd: float = 0.05,
        per_strat_tier2_dd: float = 0.10,
        portfolio_safety_tier1_dd: float = 0.25,
        portfolio_safety_tier2_dd: float = 0.35,
        # For 12C variant (portfolio_only mode):
        portfolio_gdr_tier1_dd: float = 0.25,
        portfolio_gdr_tier2_dd: float = 0.35,
    ):
```

### 7. Reset Logic

```python
def _reset(self):
    # ... existing reset ...

    # Per-strategy GDR state
    for strategy_cls in _STRATEGY_CLASSES:
        name = strategy_cls.name
        self._strategy_cumulative_pnl[name] = 0.0
        self._strategy_pnl_history[name] = deque(maxlen=_GDR_ROLLING_WINDOW)
        self._strategy_gdr_tier[name] = 0
    self._portfolio_gdr_tier = 0
```

### 8. Metrics Collection

Add per-strategy GDR tier distribution to metrics output:

```python
# In _compute_metrics() or equivalent:
strategy_gdr_stats = {}
for strategy_name in self._strategy_gdr_tier:
    # Count days at each tier (requires daily tracking)
    strategy_gdr_stats[strategy_name] = {
        "tier_0_days": tier_0_count,
        "tier_1_days": tier_1_count,
        "tier_2_days": tier_2_count,
        "pct_tier_0": tier_0_count / total_days * 100,
    }
```

---

## Sub-Test Plan

### 12A: Per-Strategy GDR -- Tight Thresholds

**Config**:
```python
BatchBacktester(
    initial_capital=100_000,
    gdr_mode="per_strategy",
    per_strat_tier1_dd=0.05,       # 5% strategy contribution DD -> Tier 1
    per_strat_tier2_dd=0.10,       # 10% strategy contribution DD -> Tier 2
    portfolio_safety_tier1_dd=0.25, # 25% total DD -> safety net Tier 1
    portfolio_safety_tier2_dd=0.35, # 35% total DD -> safety net Tier 2
)
```

**Hypothesis**: consec_down and vol_div operate at Tier 0 for 95%+ of days. rsi_mr spends ~60-70% in Tier 0 (down from current 39%). Total return improves from +1.3% to +3-5%. Portfolio DD may increase slightly due to more risk deployed.

**Key Metrics to Track**:
- Per-strategy GDR tier distribution (days at each tier)
- Per-strategy contribution DD peak
- Portfolio DD (watch for safety net activations)
- Return attribution by strategy
- Comparison of consec_down and vol_div PnL vs 11th baseline

### 12B: Per-Strategy GDR -- Loose Thresholds

**Config**:
```python
BatchBacktester(
    initial_capital=100_000,
    gdr_mode="per_strategy",
    per_strat_tier1_dd=0.10,       # 10% strategy contribution DD -> Tier 1
    per_strat_tier2_dd=0.20,       # 20% strategy contribution DD -> Tier 2
    portfolio_safety_tier1_dd=0.25, # 25% total DD -> safety net Tier 1
    portfolio_safety_tier2_dd=0.35, # 35% total DD -> safety net Tier 2
)
```

**Hypothesis**: Similar to 12A but rsi_mr operates at full capacity for ~80% of days. Higher return potential but also higher DD risk. If rsi_mr hits a 15-trade losing streak at full risk, contribution DD reaches ~22% before Tier 2 activates. Portfolio safety net may trigger.

**Key Metrics to Track**:
- Same as 12A
- Specifically: does the portfolio safety net activate? If so, how often?
- Max portfolio DD -- is it materially worse than 11th?
- rsi_mr's PnL: does operating at full risk longer produce better returns, or do the larger losses offset the larger wins?

### 12C: Portfolio GDR Only -- Widened Thresholds (Control)

**Config**:
```python
BatchBacktester(
    initial_capital=100_000,
    gdr_mode="portfolio_only",
    portfolio_gdr_tier1_dd=0.25,   # widened from 0.15
    portfolio_gdr_tier2_dd=0.35,   # widened from 0.25
)
```

**Hypothesis**: Simpler than per-strategy but still an improvement over 11th. Tier 2 days should drop from 127 to ~40-60. Return should improve to +2-4%. BUT consec_down and vol_div are still penalized when rsi_mr causes DD between 15-25% (which is frequent).

**Key Metrics to Track**:
- GDR tier distribution (compare to 11th: 39%/10%/51%)
- Return improvement over 11th
- Whether consec_down/vol_div show improved PnL (they may not, since portfolio-level still applies)

### Success Criteria

| Metric | 11th Baseline | 12A Target | 12B Target | 12C Target |
|---|:---:|:---:|:---:|:---:|
| Total Return | +1.3% | +3-5% | +4-7% | +2-4% |
| Portfolio DD | 46.2% | < 50% | < 55% | < 50% |
| Profit Factor | 1.027 | > 1.05 | > 1.05 | > 1.04 |
| Tier 0 Days (portfolio) | 39% | N/A | N/A | > 60% |
| consec_down PF | 1.47 | > 1.5 | > 1.5 | > 1.47 |
| vol_div PF | 0.55 | > 0.6 | > 0.7 | > 0.55 |

### Decision Matrix After 12th Backtests

| Outcome | Decision |
|---|---|
| 12A > 12B > 12C > 11th | Per-strategy GDR with tight thresholds; architecture validated |
| 12B > 12A > 12C > 11th | Per-strategy GDR with loose thresholds; tight thresholds are too restrictive |
| 12C >= 12A/12B | Per-strategy GDR adds complexity without benefit; use simple widened thresholds |
| 12A or 12B > 11th, but DD > 55% | Per-strategy GDR works for return but needs tighter safety net |
| All variants worse than 11th | GDR thresholds are not the core problem; revisit strategy edge |

---

## Risk Assessment

**[Strat-2 (Portfolio Risk Manager)]**: Final risk notes for the implementation:

1. **Overfitting risk**: We are calibrating thresholds based on one backtest (11th). The 12th backtest validates on the SAME data (same seed, same period). True validation requires out-of-sample testing (different seed or time period).

2. **Correlation risk during market stress**: Per-strategy GDR assumes strategies fail independently. In a 2020-March-style crash, all three mean-reversion strategies would fail simultaneously. The portfolio safety net at 25%/35% must be non-negotiable.

3. **Future strategy additions**: When adding a 4th or 5th strategy, the per-strategy GDR thresholds should be recalibrated. A strategy with unknown DD profile should start with tight thresholds (5%/10%) and widen after observational data is collected.

4. **Implementation correctness**: The PnL attribution must be exact. Every dollar of PnL must be attributed to exactly one strategy. No PnL from commissions, slippage, or cash balance changes should leak into strategy attribution. Only closed trade PnL counts.

---

## Summary of Changes Required

| Component | File | Change Type | Effort |
|---|---|---|---|
| GDR state variables | batch_simulator.py | Add per-strategy tracking dicts | Small |
| PnL attribution | batch_simulator.py (_close_position) | Accumulate PnL by strategy | Small |
| GDR update logic | batch_simulator.py (_update_gdr) | Rewrite for per-strategy + safety net | Medium |
| Entry logic | batch_simulator.py (_process_entries) | Per-strategy risk mult lookup | Small |
| Constructor params | batch_simulator.py (__init__) | Add gdr_mode and threshold params | Small |
| Reset logic | batch_simulator.py (_reset) | Reset per-strategy state | Small |
| Metrics output | batch_simulator.py (_compute_metrics) | Add per-strategy GDR stats | Small |
| Test runner script | scripts/run_backtest.py (or similar) | Run 12A/12B/12C variants | Medium |
| Unit tests | tests/ | Test per-strategy GDR logic | Medium |

**Estimated total effort**: 4-6 hours of implementation + testing.

---

*Panel discussion concluded. All 5 experts approve the hybrid per-strategy GDR architecture with portfolio-level safety net. Three test variants (12A, 12B, 12C) designed for the 12th backtest cycle.*
