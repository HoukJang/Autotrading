# Strategy Panel Review: 12th Backtest Results

**Date**: 2026-02-28
**Format**: 5-Expert Panel -- Post-12th Backtest Analysis and 13th Iteration Design
**Data**: 12th Backtest ($100K initial, 251 trading days, S&P 500 universe, real Alpaca data)
**Configurations Tested**: 12A (Per-Strategy GDR), 12B (Simplified), 12C (Control)
**Status**: CONDITIONAL PASS -- Architectural hypothesis validated; deployment blocked by DD and robustness gaps

---

## Panel Members

| ID | Role | Style | Key Question |
|---|---|---|---|
| Strat-2 | Portfolio Risk Manager | Portfolio protection, drawdown control | "What is the worst-case correlated scenario?" |
| Strat-4 | Trade Analyst | Data-driven, evidence-based | "What does the data actually show?" |
| Strat-5 | Quant Algorithm Expert | Renaissance-style mathematical rigor | "What does the math say about optimal sizing?" |
| Strat-6 | Trading System Architect | Two Sigma/DE Shaw structural design | "Is this a parameter problem or an architecture problem?" |
| Strat-7 | Root Cause / Structure Analyst | Bridgewater-style first principles | "Why did this happen, and what structural assumption is wrong?" |

---

## 1. Panel Discussion

### Opening: Hypothesis Validation

**[Strat-7 (Root Cause Analyst)]**: The 12th backtest was designed to test a specific architectural hypothesis: *per-strategy GDR decoupling eliminates collateral damage and restores edge capture*. Let me evaluate whether the data validates or refutes this hypothesis.

The 12th panel discussion identified four broken structural assumptions in the 11th system. The 12A configuration was designed to fix Assumption #4 ("a single GDR tier is sufficient for a multi-strategy system"). Let me trace the causal chain through the results:

```
Hypothesis: Per-strategy GDR -> strategies throttled independently -> no collateral damage
            -> edge capture restored -> higher return, better risk-adjusted metrics

Evidence FOR:
  12A return +5.4% vs 12C return +0.6% (9x improvement)
  12A PF 1.163 vs 12C PF 1.012 (16x improvement in excess return)
  12A Calmar 0.126 vs 12C Calmar 0.014 (9x improvement)
  12A DD 42.4% vs 12C DD 45.3% (2.9pp improvement)

  consec_down PnL: +$3,840 (12A) vs +$2,552 (12C) -- 50% improvement
  rsi_mr PnL: +$3,357 (12A) vs +$39 (12C) -- 86x improvement

Evidence AGAINST:
  Safety net active 54.8% of days -- system still spending majority time throttled
  vol_div still negative: -$2,261 (12A) vs -$2,299 (12C) -- essentially unchanged
  Max DD 42.4% -- still far from 35% PASS threshold
  SL rate 63.3% -- identical to prior iterations
```

My assessment: **the hypothesis is VALIDATED at the architectural level but INCOMPLETE at the portfolio level.** The per-strategy GDR solved the collateral damage problem exactly as predicted. consec_down is no longer dragged down by rsi_mr. rsi_mr at 1% base risk generates meaningful positive PnL instead of near-zero. But the portfolio-level problems (high DD, high SL rate, vol_div losses) are orthogonal to the GDR architecture. They require separate interventions.

**[Strat-6 (System Architect)]**: Let me confirm Strat-7's assessment with an architectural analysis. The two-layer design (per-strategy GDR + portfolio safety net) is functioning as intended. The layers are doing their jobs:

```
Layer 1 (Per-Strategy GDR):
  rsi_mr at 1% base risk -> its own drawdown is contained
  consec_down at 2% base risk -> runs at full capacity
  vol_div at 2% base risk -> runs at full capacity
  RESULT: No cross-strategy throttling observed. Architecture correct.

Layer 2 (Portfolio Safety Net):
  Activated 8 times, covering 138 days (54.8%)
  20% DD threshold is being breached frequently
  RESULT: Functioning but OVER-TRIGGERING. Parameter problem, not architecture problem.
```

The question I always ask is: "Is this a parameter problem or an architecture problem?" For Layer 1, the architecture is proven correct. For Layer 2, the 54.8% activation rate is a **parameter calibration issue**. The 20% DD threshold is set inside the system's normal operating range, which means the safety net is acting as a persistent drag rather than an emergency brake.

This is the exact same pattern we diagnosed in the 11th backtest for portfolio-level GDR -- the threshold is set below the system's normal drawdown envelope. We fixed it at Layer 1 by decoupling strategies. Now we need to fix it at Layer 2 by recalibrating the safety net.

**[Strat-4 (Trade Analyst)]**: Let me provide the numerical foundation for this discussion. I want to decompose the 12A results strategy by strategy, because the aggregate numbers hide the real story.

**Per-Strategy Decomposition (12A):**

```
rsi_mr:     98 trades | WR 29.6% | PnL +$3,357 | PF 1.20 | MaxCL 19
consec_down: 49 trades | WR 42.9% | PnL +$3,840 | PF 1.69 | MaxCL 6
vol_div:     30 trades | WR 30.0% | PnL -$2,261 | PF 0.71 | MaxCL 9

Portfolio:   177 trades | -- | PnL +$5,356 | PF 1.163 | --
```

Several observations:

**1. rsi_mr is now a genuine contributor.** The combination of 1% base risk and per-strategy GDR thresholds (3%/6%) transformed rsi_mr from near-zero (+$39 in 12C) to the second-largest profit source (+$3,357 in 12A). This is a 86x improvement with essentially the same number of trades (98 vs 103) and similar win rate (29.6% vs 29.1%). The improvement is almost entirely from better sizing management -- losses are smaller (1% risk), and the strategy isn't being throttled by other strategies' behavior.

**2. consec_down remains the backbone.** PF 1.69 across 49 trades with a MaxCL of only 6. This is the most robust strategy. Its improvement from 12C (+$2,552) to 12A (+$3,840) confirms that it was being throttled in the control configuration.

**3. vol_div is destroying portfolio value.** PF 0.71 across 30 trades with MaxCL 9. Net PnL of -$2,261. This is consistent across ALL configurations:
  - 12A: -$2,261 (PF 0.71)
  - 12B: -$2,089 (PF 0.74)
  - 12C: -$2,299 (PF 0.60)

Without vol_div, the 12A portfolio PnL would be +$7,617 (return +7.6%), PF approximately 1.30. vol_div is costing the portfolio $2,261 in direct losses plus additional safety net activations from the drawdown it contributes.

**[Strat-5 (Quant Algorithm Expert)]**: Let me formalize Strat-4's observation about vol_div with Kelly criterion analysis.

**Kelly Criterion Assessment per Strategy (12A data):**

```
consec_down:
  WR = 42.9%, PF = 1.69
  b = avg_win / avg_loss = PF * (1 - WR) / WR = 1.69 * 0.571 / 0.429 = 2.25
  f* = (p * b - q) / b = (0.429 * 2.25 - 0.571) / 2.25 = 0.175
  Half-Kelly: 8.75% of capital
  Current: 2% risk -> 0.23 Kelly -> CONSERVATIVE, appropriate for single-strategy allocation

rsi_mr:
  WR = 29.6%, PF = 1.20
  b = 1.20 * 0.704 / 0.296 = 2.85
  f* = (0.296 * 2.85 - 0.704) / 2.85 = -0.0514
  NOTE: Kelly fraction is NEGATIVE at these win rate/PF combinations.

  Wait -- let me recalculate. PF = total_win / total_loss = sum(winners) / |sum(losers)|.
  With WR 29.6% and PF 1.20:
    avg_win / avg_loss = PF * (1 - WR) / WR = 1.20 * 0.704 / 0.296 = 2.854
    f* = (0.296 * 2.854 - 0.704) / 2.854 = (0.845 - 0.704) / 2.854 = 0.049
  Kelly fraction = 4.9%, half-Kelly = 2.45%
  Current: 1% risk -> 0.20 Kelly -> APPROPRIATE

vol_div:
  WR = 30.0%, PF = 0.71
  b = 0.71 * 0.70 / 0.30 = 1.657
  f* = (0.30 * 1.657 - 0.70) / 1.657 = (0.497 - 0.70) / 1.657 = -0.122
  Kelly fraction = NEGATIVE (-12.2%)
```

**The mathematics are unambiguous.** vol_div has a negative Kelly fraction in the portfolio context. The optimal bet size is zero. Every dollar risked on vol_div has negative expected value at the observed win rate and payoff ratio. The solo PF of 1.279 does not manifest in the portfolio because of signal interaction effects -- when all three strategies compete for the same universe, vol_div's lower-conviction signals are selected into worse trades.

Continuing to trade vol_div is mathematically equivalent to paying a fee. The portfolio is voluntarily destroying $2,261 per 251 trading days.

**[Strat-2 (Portfolio Risk Manager)]**: I need to address the safety net activation problem and the DD target.

**Safety Net Analysis:**

```
Safety net threshold: 20% portfolio DD
Activation count: 8 times
Total days under safety net: 138 (54.8%)
Recovery threshold: 15% DD

When safety net is active:
  - All strategies limited to 0.5% risk (regardless of their own tier)
  - Max 1 entry per day total
  - This throttles consec_down and rsi_mr during their potentially profitable periods
```

The 54.8% activation rate tells me that the portfolio DD exceeds 20% for more than half the backtest period. This means the portfolio's peak-to-trough drawdown is not a brief dip but a **sustained condition**. The equity curve is spending extended periods below the 20% DD watermark.

Two possible interpretations:

**Interpretation A: The 20% threshold is too tight.** The system's natural DD profile exceeds 20% routinely. If we widen to 25%, the safety net might activate for 30-35% of days instead of 54.8%. This would give the profitable strategies more room to operate.

**Interpretation B: The system genuinely has excessive drawdown risk.** 42.4% max DD on a $1-5K account means the account drops from $5,000 to $2,880 at worst. Widening the safety net means ACCEPTING this drawdown. Is that tolerable?

For the actual trading account ($1-5K, aggressive risk tolerance per project specification), I assess:
- $1K account: 42.4% DD = $424 loss. Account goes to $576. Recovery to $1K requires +73.6% return. **Extremely difficult to recover.**
- $5K account: 42.4% DD = $2,120 loss. Account goes to $2,880. Recovery to $5K requires +73.6% return. **Still very difficult.**

The 35% DD PASS target exists for a reason. At 42.4%, the system requires unrealistically high subsequent returns to recover from drawdown.

**[Strat-7 (Root Cause Analyst)]**: Strat-2 raises a fundamental point. Let me trace the root cause of the persistent 42% DD.

**Root Cause Chain for 42.4% Max DD:**

```
Step 1: rsi_mr generates 98 trades at 29.6% WR -> 69 losing trades
Step 2: 112 total SL exits across all strategies (63.3% of all exits)
Step 3: SL exits generate -$29,405 in total losses
Step 4: Even with TP (+$22,877) and time_exit (+$11,257), net is only +$5,356
Step 5: The path to +$5,356 goes through a -42.4% DD trough

The DD is caused by the TIMING of losses, not just their magnitude.
SL losses cluster during adverse market periods.
All three strategies are mean-reversion / buy-the-dip -> correlated losses in downtrends.
```

**Counterfactual: "What if vol_div were removed from 12A?"**

vol_div contributed -$2,261 in losses. Those losses occurred during periods that likely ADDED to the portfolio DD. Removing vol_div would:
1. Eliminate $2,261 in direct losses
2. Reduce DD contribution from vol_div's losing trades
3. Reduce safety net activation frequency (fewer concurrent losses)

Estimated impact: DD reduction of 3-6 percentage points, bringing max DD to approximately 36-39%. This is closer to the 35% target but still not there.

The remaining DD comes from two sources:
- rsi_mr's loss streaks (MaxCL 19, which can generate $3,000-5,000 in sequential losses at 1% risk)
- Correlated drawdowns when both rsi_mr and consec_down lose during market downtrends

**[Strat-6 (System Architect)]**: Let me address the 12B vs 12A complexity question.

**12B vs 12A Comparison:**

```
                    12A (Per-Strat GDR)    12B (Simplified)
Return              +5.4%                  +3.6%
PF                  1.163                  1.094
Max DD              42.4%                  46.2%
Trades              177                    189
Sharpe              0.634                  0.651
Calmar              0.126                  0.079

12A advantages: +1.8% return, +0.069 PF, -3.8% DD, +0.047 Calmar
12B advantages: +0.017 Sharpe, +12 trades
```

12B has marginally higher Sharpe (0.651 vs 0.634), which means slightly better risk-adjusted return per unit of volatility. But Sharpe does not penalize drawdown severity -- Calmar does. 12A's Calmar ratio is 59% higher than 12B's (0.126 vs 0.079), which reflects the better DD management.

From an architectural standpoint: 12A is more complex (per-strategy state tracking, independent thresholds, two-layer risk system). Is this complexity justified?

My engineering assessment: **YES, the complexity is justified.** The per-strategy GDR is not arbitrary complexity -- it solves a specific structural defect (collateral damage). The complexity is proportional to the problem's dimensionality (3 independent risk sources require 3 independent control variables). Furthermore, the additional code is localized to the risk management module and does not increase overall system coupling.

The 12B "simplified" approach gets 67% of 12A's return improvement (3.6% vs 5.4%) with simpler implementation. But it does NOT solve the collateral damage problem structurally. If a future strategy is added with different DD characteristics, 12B will break in the same way the original GDR broke. 12A's architecture is extensible; 12B's is not.

---

### Mid-Discussion: Addressing the Eight Key Issues

**[Strat-4 (Trade Analyst)]**: Let me systematically address each of the eight issues raised.

**Issue 1: Is the 12A improvement structural or coincidental?**

The evidence for structural improvement is strong:
- The mechanism matches the prediction from the 12th design panel
- The improvement is concentrated exactly where predicted (consec_down unthrottled, rsi_mr at reduced base risk)
- The 12C control with identical data but legacy GDR produces +0.6% -- the architecture is the variable, not the data
- The effect is consistent: 12A > 12B > 12C across return, PF, and Calmar

However, this is ONE time period with deterministic data. "Structural" means the mechanism is correct, but the *magnitude* of improvement may vary across time periods. We need walk-forward testing to confirm the magnitude is stable.

**My confidence: 85% structural, 15% period-dependent magnitude.**

**[Strat-5 (Quant Algorithm Expert)]**:

**Issue 2: Safety net 54.8% activation -- should threshold widen?**

Mathematical analysis of the safety net dynamics:

```
Current: 20% DD activation, 15% DD recovery
Hysteresis band: 5 percentage points

If portfolio DD path looks like:
  Day 1-50: DD climbs from 0% to 22% (safety net activates)
  Day 51-80: At 0.5% risk, slow recovery. DD drops to 18%.
  Day 81-100: DD rises back to 21% (net re-enters safety net)
  Day 101-130: Another slow recovery to 16%.
  Day 131: DD drops below 15% (safety net deactivates)
  Day 132-150: At full risk, DD quickly rises back above 20%
  Cycle repeats.
```

The 5pp hysteresis band (20% -> 15%) is too narrow for this system's volatility. The portfolio oscillates around the 20% DD level, causing repeated activation/deactivation cycles.

**Recommendation:** Widen to **25% activation / 18% recovery** (7pp band). This keeps the safety net as a genuine emergency mechanism while reducing activation to an estimated 25-35% of days.

Alternatively, the safety net risk could use 1.0% instead of 0.5%, allowing faster recovery from DD while still protecting against catastrophic loss. At 0.5% risk, the recovery rate is too slow relative to the natural equity volatility.

**[Strat-7 (Root Cause Analyst)]**:

**Issue 3: DD 42.4% vs 35% target -- what would bring DD below 35%?**

I need to decompose the DD path to understand what drives it.

The 42.4% DD is the peak-to-trough decline in the equity curve. This is caused by:

```
DD Contributors (estimated from exit data):
  SL exits: 112 trades, -$29,405 total
  Of these, rsi_mr: ~65 SL exits, ~-$18,000 (at 1% risk)
  consec_down: ~25 SL exits, ~-$6,500 (at 2% risk)
  vol_div: ~22 SL exits, ~-$4,900 (at 2% risk)
```

To bring DD below 35%, three interventions are available:

```
Intervention A: Remove vol_div
  Estimated DD reduction: 3-6pp -> DD ~36-39%
  Probability of achieving 35% target: 30%

Intervention B: Remove vol_div + widen safety net to 25%
  More time at full capacity -> more TP/time_exit profits to offset SL losses
  Estimated DD reduction: 4-8pp -> DD ~34-38%
  Probability of achieving 35% target: 50%

Intervention C: Remove vol_div + reduce rsi_mr base risk to 0.75%
  Fewer $ lost per rsi_mr SL -> reduces equity curve drawdown depth
  Estimated DD reduction: 5-10pp -> DD ~32-37%
  Probability of achieving 35% target: 60%

Intervention D: All of above + adaptive SL (wider initial SL to reduce SL trigger rate)
  Fewer SL triggers -> fewer loss-clusters
  Estimated DD reduction: 8-15pp -> DD ~27-34%
  Probability of achieving 35% target: 75%
```

No single intervention will reliably achieve 35%. A combination of B+C or B+C+D is needed.

**[Strat-4 (Trade Analyst)]**:

**Issue 4: vol_div negative in ALL configurations. Should it be removed?**

The data is clear:

```
vol_div performance across all tested configurations:
  12A: -$2,261 (PF 0.71, WR 30.0%, 30 trades)
  12B: -$2,089 (PF 0.74, WR 27.6%, 29 trades)
  12C: -$2,299 (PF 0.60, WR 28.6%, 21 trades)
  11th: -$2,951 (PF 0.55, WR ~28%, 22 trades)

Solo performance (11th): +$4,700 (PF 1.279, 104 trades)
```

The solo-to-portfolio degradation is extreme. Solo vol_div is profitable with 104 trades and PF 1.279. Portfolio vol_div generates only 21-30 trades (70-80% reduction) and is consistently loss-making.

Root cause: when all three strategies compete for entries, vol_div's signals are lower-conviction and lower-priority in the ranking. The top-N candidate selection filters OUT vol_div's best signals in favor of rsi_mr and consec_down signals. What remains are vol_div's second-tier signals, which have negative edge.

**My recommendation: REMOVE vol_div from the portfolio.** It is not fixable by parameter tuning. The issue is structural -- signal competition. Possible alternatives:
- Run vol_div as a separate, independent portfolio with its own capital allocation
- Redesign vol_div's entry criteria to differentiate from rsi_mr/consec_down
- Replace vol_div with a trend-following strategy that provides genuine diversification

**[Strat-2 (Portfolio Risk Manager)]**:

**Issue 5: rsi_mr MaxCL 19 persists across all configs.**

A maximum consecutive loss streak of 19 is extreme. At 1% risk per trade, 19 consecutive losses produce approximately $19,000 in losses (19% of $100K). This single streak accounts for nearly half the max DD.

Is this acceptable? It depends on the probability distribution. With 29.6% WR, the probability of 19 consecutive losses is:

```
P(19 consecutive losses) = (1 - 0.296)^19 = 0.704^19 = 0.00085 = 0.085%
```

In a 98-trade sample with 29.6% WR, the expected number of 19-loss streaks is approximately:

```
Expected occurrence in 98 trades: ~98 * 0.00085 = 0.083
```

So a 19-streak in 98 trades is unlikely but not impossible (~8.3% probability of occurring at least once in a 98-trade sample). It is within the realm of bad luck rather than broken strategy.

However, the practical impact is severe. For a $5K account at 1% risk, 19 consecutive losses = 19 * $50 = $950, which is a 19% DD from this streak alone. Combined with partial recovery and subsequent losses, total DD reaches dangerous levels.

**My assessment: MaxCL 19 is statistically consistent with a 30% WR strategy, but its portfolio impact is severe. The solution is not to "fix" the MaxCL but to ensure the portfolio can absorb it.** This argues for keeping rsi_mr at 1% risk (or reducing further to 0.75%) and ensuring the safety net catches the aggregate DD.

**[Strat-5 (Quant Algorithm Expert)]**:

**Issue 6: SL rate 63.3% (target <50%) -- is this a problem?**

The SL rate decomposition:

```
Exit breakdown (12A):
  stop_loss:    112 (63.3%) -> avg PnL -$262.54
  take_profit:   36 (20.3%) -> avg PnL +$635.48
  time_exit:     27 (15.3%) -> avg PnL +$416.94
  forced_close:   2 ( 1.1%) -> avg PnL +$103.42
```

The system's edge comes from a small number of large winners compensating for many small losers. This is a valid trading approach (trend-following and mean-reversion systems often exhibit this pattern). The question is whether the ratio is optimal.

**Expected PnL per trade:**

```
E[PnL] = 0.633 * (-$262.54) + 0.203 * (+$635.48) + 0.153 * (+$416.94) + 0.011 * (+$103.42)
       = -$166.19 + $129.00 + $63.79 + $1.14
       = +$27.74 per trade

At 177 trades: 177 * $27.74 = $4,910 (close to actual $5,356)
```

The per-trade edge is +$27.74, which is thin but positive. The 63.3% SL rate is concerning because it means the edge depends on the TP and time_exit trades being sufficiently large to compensate. If market conditions change such that TP hits become less frequent or smaller, the edge disappears.

**Is the 50% SL target realistic?** For mean-reversion strategies with 30% WR, no. The SL rate will always be high because most "dip-buying" entries do not immediately reverse. The target should be strategy-specific:
- consec_down (42.9% WR): SL rate target of 45-50% is realistic
- rsi_mr (29.6% WR): SL rate target of 55-60% is more realistic
- Portfolio blended target: 50-55%

The current 63.3% is above even the adjusted target, suggesting stops may be too tight. The SL at 1.0x ATR is aggressive -- widening to 1.2-1.5x ATR would reduce SL triggers at the cost of larger individual losses.

**[Strat-6 (System Architect)]**:

**Issue 7: Multi-seed validation was effectively skipped.**

This is a significant methodological concern. All backtest results are from the same time period with identical, deterministic market data. Seed variation only affects synthetic data generation, which is not used in real data backtests.

What this means:
- We have ONE equity curve path for each configuration
- We cannot assess variance, confidence intervals, or robustness
- The performance differences (12A vs 12B vs 12C) could be amplified or reversed in different market regimes
- The MaxCL 19 for rsi_mr might be 12 in one period and 26 in another

**Required validation before deployment:**

```
1. Walk-forward testing:
   - In-sample: first 150 days -> optimize parameters
   - Out-of-sample: remaining 101 days -> validate
   - At minimum, split the 251 days into 3 folds

2. Regime-specific testing:
   - Bull market period (e.g., 2023 rally)
   - Bear market period (e.g., 2022 decline)
   - Range-bound period (e.g., 2024 H1)

3. Monte Carlo permutation:
   - Shuffle the daily returns to create synthetic paths
   - Test whether performance metrics are statistically significant
   - Confidence interval: at least 95% of permutations profitable
```

Without this validation, deploying any configuration carries unquantified risk. The 12A results are promising but could be an artifact of this specific market period.

**[Strat-4 (Trade Analyst)]**:

**Issue 8: 12B vs 12A complexity tradeoff.**

I have already seen Strat-6's architectural argument for 12A. Let me add the statistical perspective.

```
12A superiority metrics:
  Return delta: +1.8pp (5.4% vs 3.6%)
  PF delta: +0.069 (1.163 vs 1.094)
  DD delta: -3.8pp (42.4% vs 46.2%)
  Calmar delta: +0.047 (0.126 vs 0.079)

12B superiority metrics:
  Sharpe delta: +0.017 (0.651 vs 0.634)
  Trade count: +12 (189 vs 177)
```

12A wins on 4 of 6 metrics, and the metrics it wins on (return, PF, DD, Calmar) are all more important for deployment decisions than the metrics 12B wins on (marginal Sharpe, trade count).

However, the Sharpe difference is meaningful in one respect: 12B's higher Sharpe means lower return volatility relative to return magnitude. This suggests 12B has a smoother equity curve even though the endpoint is lower. For a small account where drawdown tolerance is low, the smoother curve might be preferable.

**My recommendation: 12A is the correct choice.** The added complexity of per-strategy GDR is architecturally justified and empirically validated. The Sharpe difference is within noise (0.017 on a 1-year backtest is not statistically significant).

---

### Closing: Risk Assessment and Forward View

**[Strat-2 (Portfolio Risk Manager)]**: Let me summarize the remaining risks for 12A deployment.

**Risk Register:**

| # | Risk | Severity | Probability | Mitigation |
|---|------|----------|-------------|------------|
| R1 | DD exceeds 42% in live trading (worse than backtest) | HIGH | MEDIUM | Safety net, position caps, manual override |
| R2 | vol_div continues destroying value | HIGH | HIGH (>90%) | Remove from portfolio |
| R3 | rsi_mr enters 19+ loss streak on small account | HIGH | LOW (~8%) | 1% risk cap, safety net backstop |
| R4 | Results are period-specific, fail in different regime | HIGH | UNKNOWN | Walk-forward validation required |
| R5 | Safety net over-activation throttles recovery | MEDIUM | HIGH (54.8%) | Widen threshold to 25% |
| R6 | Slippage and execution differs from backtest model | MEDIUM | MEDIUM | Conservative slippage model, paper trade first |
| R7 | All strategies correlate in sustained downturn | HIGH | MEDIUM | Add trend-following strategy for diversification |

**[Strat-7 (Root Cause Analyst)]**: I want to flag one structural concern that no amount of parameter tuning will fix.

All three current strategies are **contrarian/mean-reversion**. They buy weakness. In a trending market (up or down), they all fail simultaneously. The portfolio has ZERO trend-following exposure.

This is the deepest structural risk. The per-strategy GDR and safety net can LIMIT losses during a trend, but they cannot GENERATE profits during a trend. The portfolio has a blind spot to trending environments.

For a $1-5K account, one sustained downtrend (like Q1 2022) could produce 30-40% DD even with all safety mechanisms active, because every entry is a losing entry. No amount of risk reduction fixes a strategy that enters in the wrong direction.

**Long-term recommendation: add a trend-following strategy** (e.g., momentum breakout, moving average crossover) that BENEFITS from sustained trends. This provides genuine portfolio diversification, not just multiple variations of the same thesis.

**[Strat-5 (Quant Algorithm Expert)]**: Agreed with Strat-7. Let me quantify. The correlation between the three strategies' returns is:

```
Estimated return correlation (all mean-reversion):
  rsi_mr vs consec_down: ~0.4-0.6 (both buy dips)
  rsi_mr vs vol_div: ~0.3-0.5 (both contrarian)
  consec_down vs vol_div: ~0.3-0.5 (both contrarian)

Effective portfolio diversification ratio: ~0.5-0.6
Ideal diversification ratio: <0.3 (with trend-following component)
```

Adding one trend-following strategy with -0.2 to 0.0 correlation to the mean-reversion strategies would reduce portfolio DD by an estimated 20-30% while maintaining or improving return. This is the highest-leverage improvement available.

**[Strat-6 (System Architect)]**: Final architectural observation. The per-strategy GDR architecture was designed to be **extensible**. Adding a 4th strategy requires:
1. Add strategy class to `_STRATEGY_CLASSES`
2. Add base risk to `_STRATEGY_BASE_RISK`
3. Add GDR thresholds to `_STRATEGY_GDR_THRESHOLDS`
4. Increase `_MAX_DAILY_ENTRIES` if needed

The architecture does not need modification. This validates the design decision to build per-strategy rather than per-portfolio controls. The system is ready for expansion.

---

## 2. Assessment Summary

### Is 12A the right choice?

**UNANIMOUS: YES.** 12A is the best configuration tested. The per-strategy GDR architecture is validated both theoretically (solves collateral damage, extensible design) and empirically (best return, best PF, best DD, best Calmar).

### Remaining Risks

| Risk Category | Assessment |
|---|---|
| **DD adequacy** | FAIL. 42.4% DD is unacceptable for $1-5K account. Must improve to <35%. |
| **vol_div drag** | FAIL. Negative Kelly, negative PnL in all configs. Must be removed or replaced. |
| **Robustness** | UNKNOWN. No out-of-sample validation. Walk-forward testing mandatory. |
| **Strategy correlation** | ELEVATED. All strategies are mean-reversion. No trend-following diversification. |
| **Safety net calibration** | MARGINAL. 54.8% activation is excessive. Threshold needs widening. |
| **SL rate** | MARGINAL. 63.3% is high but consistent with 30% WR strategies. Not fixable without strategy redesign. |
| **Architecture** | PASS. Per-strategy GDR + safety net is proven correct and extensible. |

### What should be prioritized next?

1. **Remove vol_div** -- immediate, zero-risk improvement (+$2,261 PnL swing)
2. **Recalibrate safety net** -- widen to 25% activation, 18% recovery
3. **Walk-forward validation** -- split data into in-sample/out-of-sample
4. **Consider trend-following strategy** -- highest-leverage portfolio improvement
5. **Paper trade 12A (minus vol_div)** -- real execution validation

---

## 3. Recommendations for 13th Iteration

| Priority | Change | Rationale | Expected Impact |
|----------|--------|-----------|-----------------|
| P0 | Remove vol_div from portfolio | Negative Kelly (-12.2%), negative PnL in all configs, destroying $2,261/year | Return +7.6%, DD reduction 3-6pp |
| P0 | Walk-forward validation on 12A config | No out-of-sample testing done; deployment blocked without it | Robustness confidence |
| P1 | Widen safety net to 25%/18% (activation/recovery) | 54.8% activation rate throttles recovery; current 20% is inside normal DD range | Safety net activation reduced to ~25-35%, faster equity recovery |
| P1 | Increase safety net risk to 0.75% (from 0.5%) | At 0.5% risk, recovery from DD is too slow relative to equity volatility | Faster recovery from safety net periods |
| P2 | Reduce rsi_mr base risk to 0.75% (from 1.0%) | rsi_mr MaxCL 19 at 1% risk generates ~$19K DD; 0.75% reduces to ~$14K | DD reduction 3-5pp, return reduction ~$800-1,000 |
| P2 | Test wider SL multiplier for rsi_mr (1.2-1.5x ATR) | 63.3% SL rate suggests stops too tight; wider stops reduce trigger rate | SL rate reduction to 50-55%, larger individual losses but fewer of them |
| P3 | Research trend-following strategy for portfolio | All current strategies are mean-reversion; zero trend exposure creates blind spot | Portfolio correlation reduction, DD reduction in trending markets |
| P3 | Regime-specific backtesting (bull/bear/range) | Current test is single period; unknown behavior in different regimes | Confidence in strategy across market conditions |

---

## 4. Open Questions (Carry Forward)

| # | Question | Owner | Status |
|---|----------|-------|--------|
| Q1 | Does vol_div have ANY viable configuration in a multi-strategy portfolio, or is signal competition fatal? | Strat-4, Strat-7 | OPEN -- Recommend testing vol_div solo portfolio as separate allocation |
| Q2 | What is the optimal rsi_mr base risk? 1.0% may still be too high given MaxCL 19. Is 0.75% or 0.5% better? | Strat-5 | OPEN -- Requires parameter sweep with walk-forward validation |
| Q3 | Can the safety net use a time-based decay instead of pure DD threshold? (e.g., reduce severity after 20 days) | Strat-6 | OPEN -- Architectural question for 14th iteration |
| Q4 | What trend-following strategy would provide maximum diversification benefit? Momentum breakout? MA crossover? | Strat-7 | OPEN -- Research phase, not implementation |
| Q5 | Should we test a 2-strategy portfolio (rsi_mr + consec_down) before adding a 4th strategy? | Strat-2 | OPEN -- 13th iteration should test this as baseline |
| Q6 | Is the slippage model (3bps) realistic for the $1-5K account size? Small accounts may face wider spreads. | Strat-4 | OPEN -- Compare backtest fills vs paper trading fills |
| Q7 | How does the system perform when starting capital is $5K instead of $100K? Position sizing constraints may be binding. | Strat-5 | OPEN -- Critical for real deployment; minimum viable trade size may filter out many signals |
| Q8 | Should the 13th iteration use a different time period entirely, or extend the current period? | Strat-6 | OPEN -- Ideally both: original period for regression testing + new period for out-of-sample |

---

## 5. Final Verdict

### CONTINUE ITERATING -- 12A architecture as base, with targeted modifications

**Rationale:**

12A validates the per-strategy GDR architecture -- the most significant structural improvement since the project began. Return improved 4.2x (5.4% vs 1.3%), PF improved 16x in excess return, and DD improved 3.8 percentage points. These are not marginal gains; they represent a qualitative shift in system behavior.

However, deployment is blocked by three unresolved issues:

1. **DD 42.4% exceeds the 35% PASS threshold.** No configuration has achieved this target. The primary levers are vol_div removal (3-6pp DD reduction) and safety net recalibration (additional 2-4pp).

2. **No out-of-sample validation.** All results are from one time period with deterministic data. We cannot assess statistical significance or regime robustness. Walk-forward testing is mandatory before any live deployment.

3. **vol_div is a confirmed portfolio drag.** Negative Kelly fraction, negative PnL in all configurations, unfixable by parameter tuning. Must be removed before 13th iteration.

**Recommended 13th iteration scope:**

```
Configuration 13A: 2-strategy (rsi_mr + consec_down), per-strategy GDR,
                   safety net 25%/18%, rsi_mr at 1% risk
Configuration 13B: Same as 13A but rsi_mr at 0.75% risk
Configuration 13C: Same as 13A with rsi_mr SL widened to 1.5x ATR

All configurations: walk-forward validation (150-day train / 101-day test)
If time permits: test on different date range for out-of-sample validation
```

**Deployment gate for live paper trading:**
- Return >= +3.0% (in-sample AND out-of-sample)
- PF >= 1.10 (in-sample AND out-of-sample)
- Max DD <= 35% (in-sample AND out-of-sample)
- SL rate <= 55% (portfolio level)
- Walk-forward consistency: out-of-sample metrics within 50% of in-sample

Until these gates are met, the system remains in backtest development. The architecture is sound; the edge needs validation.

---

**Panel Signatures:**

- Strat-2 (Portfolio Risk Manager): CONCUR. Emphasize DD must reach <35% before any deployment.
- Strat-4 (Trade Analyst): CONCUR. vol_div removal is the single highest-impact action.
- Strat-5 (Quant Algorithm Expert): CONCUR. Walk-forward validation is non-negotiable.
- Strat-6 (Trading System Architect): CONCUR. Architecture is ready for expansion; parameters need tuning.
- Strat-7 (Root Cause / Structure Analyst): CONCUR. Add trend-following research to 13th iteration scope, even if implementation is deferred to 14th.
