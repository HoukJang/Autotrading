# Strategy Panel Discussion: 11th Backtest Analysis

**Date**: 2026-02-28
**Format**: 5-Expert Panel -- Post-11th Backtest Analysis and 12th Backtest Design
**Data**: 11th Backtest ($100K initial, 251 trading days, S&P 500 universe, seed=42)
**Status**: CONDITIONAL PASS -- Positive return but marginal; systemic issues identified

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

## 11th Backtest Results Summary

### Portfolio Performance

| Metric | 9th (Baseline) | 10C (Failed) | 11th | Trend |
|---|:---:|:---:|:---:|---|
| Total Trades | 308 | 98 | 174 | Declining |
| Win Rate | 36.4% | 24.5% | 32.8% | Declining |
| Profit Factor | 1.043 | 0.796 | 1.027 | Declining |
| Return | +4.9% | -3.9% | +1.3% | Declining |
| Max DD | 50.4% | 43.9% | 46.2% | Flat |
| Sharpe | 1.172 | 0.781 | 0.645 | Declining |
| Avg Win | $856 | $674 | $566 | Declining |
| Avg Loss | -$469 | -$275 | -$269 | Improved |

### 10th Panel Predictions vs 11th Actuals

| Metric | 10th Panel Conservative | 10th Panel Optimistic | 11th Actual | Deviation |
|---|---|---|---|---|
| Trades | 250-280 | 280-310 | 174 | 38% below conservative |
| Win Rate | 34-37% | 37-40% | 32.8% | Below conservative |
| PF | 1.02-1.10 | 1.10-1.20 | 1.027 | Near bottom of range |
| Return | +2-6% | +6-10% | +1.3% | Below conservative |
| Max DD | 35-45% | 25-35% | 46.2% | Above conservative |
| vol_div Trades | 20-35 | 35-50 | 22 | Near bottom of range |

---

## Agenda 1: The GDR Circular Dependency -- Core Systemic Issue

**[Strat-4 (Trade Analyst)]**: Let me start with what I consider the single most important finding in the 11th data. The GDR tier distribution tells the entire story:

```
Tier 0 (Normal):  98 days (39%) -- RISK 2%, 2 entries/day
Tier 1 (Reduced): 26 days (10%) -- RISK 1%, 1 entry/day
Tier 2 (Minimal): 127 days (51%) -- RISK 0.5%, 1 entry/day
```

The system operates in its most restricted mode for **more than half of all trading days**. Let me compute the effective operating capacity.

```
Effective avg risk  = 0.39*2.0% + 0.10*1.0% + 0.51*0.5% = 1.135%
Effective avg entries = 0.39*2 + 0.10*1 + 0.51*1 = 1.39 entries/day

Baseline capacity: 2.0% risk, 2.0 entries/day
Effective capacity: 1.135% risk, 1.39 entries/day
Risk utilization: 1.135/2.0 = 56.8%
Entry utilization: 1.39/2.0 = 69.5%
```

The 11th system operates at approximately **57% of its designed risk capacity**. This directly explains the return compression from +4.9% (9th) to +1.3% (11th). The GDR is not causing a death spiral like the old circuit breaker, but it is imposing a persistent drag that consumes nearly half the system's earning potential.

**[Strat-5 (Quant Algorithm Expert)]**: Strat-4's capacity analysis is precise. Let me formalize the circular dependency mechanism that creates this outcome.

**The GDR Feedback Loop:**

```
Step 1: rsi_mr generates trades with WR ~30%, SL rate 64%
Step 2: Sequential SL hits accumulate -> portfolio DD increases
Step 3: DD exceeds 15% -> GDR Tier 1 activates (RISK halved)
Step 4: DD exceeds 25% -> GDR Tier 2 activates (RISK quartered)
Step 5: At 0.5% risk, winning trades generate tiny PnL
Step 6: Tiny wins cannot recover the DD accumulated at 2% risk losses
Step 7: System remains in Tier 2 because recovery is too slow
Step 8: Eventually rolling peak shifts down -> DD recalculates lower
Step 9: Brief Tier 0 period -> rsi_mr enters at full size -> losses restart cycle
```

This is a **reinforcing feedback loop** with an asymmetric gain/loss structure. Losses occur at 2% risk (Tier 0), but recovery happens at 0.5% risk (Tier 2). The system needs 4x more winning trades in Tier 2 to recover each dollar lost in Tier 0.

Let me quantify: A single SL at Tier 0 (2% risk) loses approximately $2,000. A TP at Tier 2 (0.5% risk) gains approximately $300-400 (assuming similar R:R ratio). The system needs 5-6 Tier 2 winners to offset each Tier 0 loser. With 32.8% WR, this means approximately 15-18 Tier 2 trades to recover one Tier 0 loss. At 1 entry/day, that is 15-18 trading days per recovery unit.

**[Strat-2 (Portfolio Risk Manager)]**: This is exactly the pattern I feared when we discussed the GDR in the 10th panel. We successfully avoided the death spiral (the GDR never halts trading), but we created a different problem: **asymmetric recovery drag**.

The root cause is not the GDR concept -- graduated response is correct. The root cause is the **threshold calibration relative to this system's normal drawdown profile**.

Let me trace why the thresholds are wrong. rsi_mr solo DD is 48.4%. In the portfolio with 3 strategies, rsi_mr constitutes 59% of trades (103 out of 174). The portfolio's DD is therefore dominated by rsi_mr's behavior. When rsi_mr enters one of its natural losing streaks (MaxCL = 19), the portfolio DD quickly breaches 15% and then 25%.

The 15% Tier 1 threshold is inside rsi_mr's **normal operating range**. A strategy with 30% WR and MaxCL of 19 will routinely produce 15%+ drawdowns. The GDR is treating normal rsi_mr behavior as exceptional stress.

**[Strat-1 (Swing Trade Specialist)]**: Let me put this in practical trading terms. I have managed accounts through drawdowns far worse than 15%. A 15% DD in an aggressive swing trading system targeting small accounts ($1K-$5K) is Tuesday. You do not cut your size in half because you are down 15%.

The 25% threshold for Tier 2 is similarly too low. With 6 concurrent positions at 2% risk each, a single correlated market event can create a 8-10% portfolio loss. Two such events in a month -- entirely normal in volatile markets -- and you hit 20%. Three events and you are at 25%, triggering Tier 2.

The thresholds were designed for a theoretical system with 15-22% max DD (the 9th panel's failed prediction). The reality is this system has 46-50% DD under normal conditions. The GDR thresholds need to match the system's actual DD profile, not the hoped-for DD profile.

**[Strat-3 (Market Microstructure Expert)]**: I want to add a microstructure dimension. When the GDR reduces risk to 0.5% per trade, position sizes become extremely small. On a $100K account at 0.5% risk with 1.0 ATR SL, a typical position is:

```
Stock price: $150
ATR: $3.00 (2% of price)
SL distance: $3.00 (1.0 ATR)
Risk dollars: $100,000 * 0.005 = $500
Position size: $500 / $3.00 = 166 shares
Position value: 166 * $150 = $24,900

Per-trade slippage (3 bps): $24,900 * 0.0003 * 2 = $14.94
Commission: 166 * $0.005 * 2 = $1.66
Total friction: $16.60
```

At Tier 2, a winning trade might gain $300-400. The $16.60 friction is 4-5% of the gain. At Tier 0 with full position sizes, the same friction is 1-2% of a $1,000+ gain. The GDR does not just reduce position size -- it disproportionately increases the friction cost as a percentage of PnL.

For the real target account ($1K-$5K), the numbers are even worse:

```
$3,000 account at Tier 2 (0.5% risk):
Risk dollars: $3,000 * 0.005 = $15
Position size: $15 / $3.00 = 5 shares
Position value: 5 * $150 = $750
Winning PnL: ~$15-20
Friction: $750 * 0.0003 * 2 + 5 * $0.005 * 2 = $0.50
```

At the real account size, Tier 2 positions are nearly untradeable. Five shares of a $150 stock produces $15-20 in PnL per winning trade. After 5-6 consecutive losses (expected at 30% WR), you need 15-20 winners to recover. The math does not work.

**[Strat-5 (Quant Algorithm Expert)]**: Strat-3 raises a critical point about the real account size. But let me stay focused on the backtest analysis where we have concrete data. The question is: what GDR thresholds would have produced a Tier distribution that does not suppress returns?

Let me model this. The 11th backtest shows 46.2% max DD. If we reconstruct the approximate DD timeline:

```
Target Tier 2 days: < 20% of total (< 50 days)
Target Tier 1 days: < 15% of total (< 38 days)
Target Tier 0 days: > 65% of total (> 163 days)
```

To achieve this distribution with a 46% max DD, the thresholds need to be:

```
Tier 1 threshold: ~25% DD (triggered only in upper half of DD range)
Tier 2 threshold: ~40% DD (triggered only near max DD)
```

However, I want to flag an important caution. We are now calibrating the GDR thresholds to fit the observed DD of the 11th backtest. This is in-sample optimization. If the 12th backtest has a different DD profile (which it might, since we are also changing rsi_mr parameters), these thresholds could be wrong again.

A more robust approach: set thresholds as a **fraction of expected maximum DD** rather than absolute percentages. If our system's structural max DD is approximately 45-50%, then:

```
Tier 1: 50% of max DD = 22.5-25%
Tier 2: 75% of max DD = 33.75-37.5%
```

Rounding to practical values: Tier 1 at 25%, Tier 2 at 35%.

**Panel Discussion on GDR Rolling Window:**

**[Strat-2 (Portfolio Risk Manager)]**: The 60-day rolling window also needs examination. With 60 trading days (approximately 3 calendar months), the peak equity used for DD calculation resets relatively quickly. In the 11th backtest, this means:

1. System builds equity in Tier 0 (say equity rises from $100K to $104K)
2. Loss streak drops equity to $85K (DD = 18.3% from $104K peak)
3. Tier 1 activates, system trades at half size
4. Over 60 days, the peak gradually shifts down as the $104K equity drops out of the rolling window
5. If current equity is $88K and the rolling 60-day peak is now $92K, DD is only 4.3%
6. System returns to Tier 0, trades at full size
7. New loss streak from $88K drops to $75K (DD = 14.8% from $92K rolling peak)
8. This $75K equity is actually 25% below the original $100K, but GDR only sees 14.8%

This is the rolling peak's double-edged sword. It prevents the old death spiral (static peak trapping), but it also allows the system to "forget" previous drawdowns and trade aggressively from a depressed equity base.

I recommend extending to **90 days**. This gives the system 4.5 calendar months of DD memory, which covers 2-3 full loss/recovery cycles at our system's typical velocity. It still resets eventually (preventing death spiral) but holds the memory long enough to prevent premature return to full risk after a deep DD.

**[Strat-4 (Trade Analyst)]**: I support 90 days based on the data. In the 11th backtest, the average duration of a DD event (from peak to trough) is approximately 35-45 trading days. With a 60-day window, the system starts forgetting the DD while it is still in progress. A 90-day window would contain the full DD event in most cases.

**Panel Consensus on Agenda 1:**
- GDR thresholds are the primary driver of return suppression
- Current 15%/25% thresholds are inside the system's normal DD operating range
- **WIDEN** GDR Tier 1: 15% -> 25% DD
- **WIDEN** GDR Tier 2: 25% -> 35% DD
- **EXTEND** rolling window: 60 -> 90 trading days
- Expected impact: Tier 2 days from 51% to ~15-25%, Tier 0 days from 39% to ~60-70%
- Effective risk utilization: from 57% to ~75-85% of capacity
- Risk: Wider thresholds mean the system endures deeper DD before reducing risk. Max DD may increase by 3-5 percentage points. This is an acceptable trade-off for a system that already has 46% DD.

---

## Agenda 2: rsi_mean_reversion -- The Portfolio DD Driver

**[Strat-4 (Trade Analyst)]**: rsi_mr is the dominant strategy in the portfolio -- 103 out of 174 trades (59%). It is also the primary driver of drawdown. Let me present the key comparison:

```
rsi_mr SOLO:   142 trades, PF 1.195, Return +5.8%, DD 48.4%, MFE/MAE 1.08x
rsi_mr PORTFOLIO: 103 trades, PF 1.07, PnL +$1,373, SL 64.1%, MaxCL 19

consec_down SOLO: 105 trades, PF 1.423, Return +5.4%, DD 1.9%, MFE/MAE 1.06x
consec_down PORT: 49 trades, PF 1.47, PnL +$2,426, SL 57.1%, MaxCL 8

vol_div SOLO:  104 trades, PF 1.279, Return +4.7%, DD 3.4%, MFE/MAE 1.40x
vol_div PORT:  22 trades, PF 0.55, PnL -$2,951, SL 72.7%, MaxCL 8
```

The critical number: rsi_mr solo DD is 48.4%. This single strategy's drawdown profile is what triggers GDR Tier 2 for 51% of the backtest. consec_down has 1.9% DD and vol_div has 3.4%. If rsi_mr were removed, the portfolio's DD would be dramatically lower and the GDR would rarely activate.

But here is the dilemma: rsi_mr solo has PF 1.195 and +5.8% return. It has a genuine, statistically meaningful edge (142 trades). Removing it discards real alpha.

**[Strat-1 (Swing Trade Specialist)]**: I have been advocating for entry quality improvements since the 9th panel. Let me finally make the case with data.

rsi_mr's 64% SL rate is the highest of all three strategies. For a mean-reversion strategy, this means the majority of "oversold" entries are not genuine reversals -- they are stocks that continue declining through the stop loss. The strategy is catching falling knives 64% of the time.

Current rsi_mr entry conditions:
```
RSI_OVERSOLD = 30
BB_LONG_ENTRY_PCT_B = 0.05
ADX_MAX = 25
```

These conditions require RSI < 30, price near lower Bollinger Band, and ADX < 25 (non-trending). The 30 RSI threshold is standard, but in practice it catches too many stocks in early-stage declines that have not yet bottomed.

My recommendation: **tighten RSI_OVERSOLD from 30 to 25**. RSI < 25 is a more extreme oversold condition that historically correlates with higher bounce probability. The trade-off is fewer signals, but the remaining signals should have higher quality.

Expected impact:
- rsi_mr trade count: 103 -> ~65-75 (30-35% reduction)
- rsi_mr SL rate: 64.1% -> ~50-55% (improved signal quality)
- rsi_mr WR: 30.1% -> 35-38% (removing weakest signals)
- rsi_mr solo DD: 48.4% -> ~35-40% (fewer losing trades)

**[Strat-5 (Quant Algorithm Expert)]**: Let me evaluate Strat-1's proposal mathematically. With RSI_OVERSOLD at 25 instead of 30:

```
Assumed new rsi_mr parameters:
  Trades: 70 (from 103, 32% reduction)
  WR: 36% (from 30.1%, removing ~30 of the worst trades)
  Avg Win: $566 (unchanged)
  Avg Loss: -$269 (unchanged)

Expected PnL per trade: 0.36 * $566 - 0.64 * $269 = $203.76 - $172.16 = +$31.60
Total expected PnL: 70 * $31.60 = +$2,212

Compare to current rsi_mr:
  Expected PnL per trade: 0.301 * $566 - 0.699 * $269 = $170.37 - $188.03 = -$17.66
  Actual total PnL: +$1,373 (slightly positive despite negative per-trade expectancy
  -- suggesting the winners are larger than the average implies)
```

The per-trade expectancy improves from approximately break-even to +$31.60, which is directionally correct. However, I want to flag an assumption issue: we are assuming that the removed 30-35 trades are the worst performers. If the RSI 25-30 band contains a mix of winners and losers proportional to the overall WR, the improvement would be smaller.

A more conservative estimate: removing trades in the RSI 25-30 band improves WR by only 3 percentage points (to 33%), not 6. In that case:

```
Conservative: 70 trades * (0.33*$566 - 0.67*$269) = 70 * ($186.78 - $180.23) = 70 * $6.55 = +$459
```

Still positive, and with fewer total trades, the DD contribution shrinks.

**[Strat-2 (Portfolio Risk Manager)]**: I want to address the broader question: should we cap rsi_mr's portfolio allocation?

Currently rsi_mr takes 59% of all trades. With the soft per-strategy cap of 2 concurrent positions and MAX_TOTAL of 5, rsi_mr can theoretically hold 2/5 = 40% of positions. But in terms of trade count (entries over time), rsi_mr dominates because it generates more frequent signals.

I propose a **hard trade frequency cap**: rsi_mr can enter at most 1 position per day, regardless of signal count. Combined with the existing max 2 concurrent positions, this naturally limits rsi_mr's portfolio DD contribution.

Currently, rsi_mr enters 103 times over 251 days = 0.41 entries/day average. With 1/day cap, the impact is modest on total count but prevents cluster entries during volatile periods when rsi_mr might try to enter 2 positions simultaneously.

**[Strat-1 (Swing Trade Specialist)] responding to Strat-2**: I do not support a hard frequency cap for a single strategy. This is the kind of ad-hoc structural constraint that creates unpredictable interaction effects (lesson from 10th backtest). If we tighten rsi_mr's entry conditions (RSI 30 -> 25), the signal frequency drops naturally. Let the filter do the work, not the cap.

**[Strat-3 (Market Microstructure Expert)]**: I want to highlight an important data point from the MFE/MAE table:

```
rsi_mr solo MFE/MAE: 1.08x
rsi_mr portfolio MFE/MAE: 0.99x
```

In solo mode, rsi_mr trades exhibit a slight edge in price movement (MFE exceeds MAE by 8%). In the portfolio context, this edge disappears entirely (0.99x is essentially random). Why?

The portfolio MFE/MAE is lower because the GDR Tier 2 selects rsi_mr entries at the worst possible times. After a drawdown recovery (when GDR transitions from Tier 2 back to Tier 0), the market may have already bounced significantly. The "oversold" conditions that triggered signals are partially resolved by the time the GDR allows full-size entries again. The delay between signal quality and execution timing degrades MFE/MAE.

This is another form of the GDR interaction effect. The GDR does not just reduce position size -- it subtly alters which signals get executed at full size, biasing toward post-recovery entries rather than peak-oversold entries.

**Panel Consensus on Agenda 2:**
- rsi_mr has a genuine edge (solo PF 1.195) but its DD profile (48.4%) drives GDR activation
- **TIGHTEN** RSI_OVERSOLD: 30 -> 25 (reduce signal frequency by ~30%, improve quality)
- **KEEP** BB_LONG_ENTRY_PCT_B at 0.05 (do not change multiple entry parameters simultaneously)
- **KEEP** ADX_MAX at 25 (defer to 13th backtest if RSI change alone is insufficient)
- **DO NOT** add hard frequency caps (let entry filter do the work)
- **DO NOT** remove rsi_mr (genuine edge, worth preserving)
- Expected impact: rsi_mr solo DD from 48.4% to ~35-40%, SL rate from 64% to ~50-55%

---

## Agenda 3: volume_divergence Portfolio Suppression

**[Strat-4 (Trade Analyst)]**: vol_div is the most puzzling strategy in our portfolio. The solo vs portfolio comparison:

```
Solo:      104 trades, PF 1.279, Return +4.7%, DD 3.4%, MFE/MAE 1.40x
Portfolio: 22 trades, PF 0.55, PnL -$2,951, SL 72.7%, MFE/MAE 0.83x
```

Let me decompose the failure modes:

1. **Trade count suppression**: 104 solo -> 22 portfolio (79% reduction). This improved from 10C (3 trades) but remains far below solo potential.

2. **Win rate collapse**: Solo WR (implied from PF 1.279 with similar avg wins/losses) is approximately 40-45%. Portfolio WR is 27.3%. The 22 portfolio trades are a severely biased sample.

3. **SL rate**: 72.7% (16 of 22 trades hit SL). This is the highest SL rate of all strategies in the portfolio. The 22 trades that made it through the ranking filter were the worst performers.

**Why does this happen?**

The diversity bonus of +0.25 increased vol_div from 3 to 22 trades. This is progress. But the trades that get selected are disproportionately those where vol_div happens to generate a signal on days when rsi_mr and consec_down also generate signals -- because the ranking only picks vol_div when the diversity bonus pushes it above competitors.

On days where only vol_div generates signals and the other strategies do not, there is no competition and vol_div would win easily. But these days often fall during GDR Tier 2 (1 entry/day, 0.5% risk). The resulting positions are tiny and produce negligible PnL.

On days where all three strategies compete, vol_div wins only when it has the +0.25 bonus and its base composite score is close to the others. These tend to be vol_div signals with higher-than-average signal_strength (>0.50), which paradoxically may not be vol_div's best setups.

**[Strat-5 (Quant Algorithm Expert)]**: Strat-4 identifies a selection bias problem. The ranking system selects vol_div trades based on composite score, not on vol_div's own predictive quality. The diversity bonus helps, but it selects the **relatively best** vol_div signals for ranking purposes, which may not be the **absolutely best** vol_div signals for profitability.

However, I want to caution against overinterpreting 22 trades. The standard error on a 27.3% WR estimate with N=22:

```
SE = sqrt(0.273 * 0.727 / 22) = sqrt(0.0090) = 0.095
95% CI: [8.3%, 46.3%]
```

The confidence interval spans from 8% to 46%. We have essentially zero statistical information about vol_div's true portfolio WR from 22 trades. The -$2,951 PnL could easily be noise.

**[Strat-1 (Swing Trade Specialist)]**: I have advocated for structural changes to vol_div allocation since the 9th panel. Three backtests later, the diversity bonus approach has produced incremental improvement (3 -> 22 trades) but remains inadequate.

I now want to escalate to the structural option that was deferred from the 10th panel: **guaranteed minimum allocation**. Specifically:

```
Rule: If vol_div generates >= 1 signal on a given day, at least 1 of the
      daily entry slots must go to the highest-ranked vol_div signal,
      UNLESS the vol_div signal composite score (before diversity bonus)
      is below 0.30 (quality floor).
```

This ensures vol_div gets executed when it has reasonable signals, without forcing bad signals into the portfolio. The 0.30 quality floor prevents the system from entering weak vol_div trades just for diversification.

**[Strat-2 (Portfolio Risk Manager)]**: I am hesitant about guaranteed allocation. It creates a structural preference for one strategy that is not justified by the portfolio data (PF 0.55, -$2,951). Yes, the solo performance is strong, but we have three backtests showing portfolio underperformance.

My counter-proposal: **wait for the GDR threshold widening to take effect**. If GDR Tier 2 drops from 51% to ~15-25% of days, vol_div will have 2 entry slots available for ~75% of trading days instead of only 39%. With more available slots and the existing +0.25 diversity bonus, vol_div should naturally reach 40-50 trades.

Let me estimate:
```
Current: 251 days, 39% Tier 0 (2 entries) = 98 days with 2 slots
Expected with new GDR: 251 days, 65% Tier 0 = 163 days with 2 slots

Current vol_div selection rate in Tier 0: ~22/(98*2 + 153*1) = 22/349 = 6.3%
If selection rate stays constant with more Tier 0 days: 6.3% * (163*2 + 88*1) = 6.3% * 414 = 26 trades

Hmm -- only 26 trades. The improvement is marginal because vol_div's selection rate is
inherently low against rsi_mr competition.
```

So the GDR fix alone would only increase vol_div from 22 to ~26 trades. This is not enough.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-2**: Strat-2's estimate confirms that the GDR fix alone is insufficient for vol_div. The fundamental problem is ranking competition, not GDR suppression.

I now support Strat-1's guaranteed minimum allocation, but with a modification. Instead of a guaranteed slot, use a **strategy rotation priority system**:

```
Day N:     Priority order: [vol_div, rsi_mr, consec_down]
Day N+1:   Priority order: [rsi_mr, consec_down, vol_div]
Day N+2:   Priority order: [consec_down, vol_div, rsi_mr]
Day N+3:   Cycle repeats
```

On each day, the first entry slot goes to the highest-scored signal from the priority strategy (if any). The second slot goes to the best remaining signal. This gives each strategy a fair rotational advantage without permanently favoring one strategy.

**[Strat-3 (Market Microstructure Expert)]**: The rotation system is elegant but adds implementation complexity. Let me propose a simpler alternative that achieves a similar effect: **increase the diversity bonus for vol_div specifically**.

The current diversity bonus is strategy-agnostic (+0.25 for 0 positions, +0.10 for 1 position). What if we made it proportional to the strategy's portfolio underrepresentation?

```
Expected portfolio share: 1/3 = 33.3% per strategy
Actual rsi_mr share: 59% (overrepresented by +25.7%)
Actual consec_down share: 28.2% (underrepresented by -5.1%)
Actual vol_div share: 12.6% (underrepresented by -20.7%)

Diversity bonus = max(0, underrepresentation * 2)
vol_div: 0.207 * 2 = +0.414 (very large bonus)
consec_down: 0.051 * 2 = +0.102
rsi_mr: 0 (overrepresented, no bonus)
```

This is too aggressive as a static parameter. But it illustrates that the current flat +0.25 is insufficient for vol_div's level of underrepresentation.

**[Strat-4 (Trade Analyst)]**: We are overcomplicating this. The 10th panel explicitly said: "If vol_div < 20 trades in 11th, escalate to structural changes." We have 22 trades, which is technically above 20 but still inadequate. I agree with escalation.

However, I want to remind everyone of the 10th backtest lesson: structural changes have unpredictable interaction effects. Any vol_div allocation change should be tested in isolation (12A test) before combining with GDR and rsi_mr changes.

**Panel Consensus on Agenda 3:**
- vol_div remains severely suppressed in portfolio despite diversity bonus
- GDR fix alone is insufficient to resolve this (estimated +4 trades only)
- **INCREASE** diversity bonus for 0-position strategies: +0.25 -> +0.35
- **KEEP** diversity bonus for 1-position strategies: +0.10 (unchanged)
- **DEFER** guaranteed allocation and rotation systems to 13th if +0.35 is insufficient
- **MONITOR** vol_div composite scores -- if average drops below 0.35, the bonus is pushing bad signals
- Expected impact: vol_div trades from 22 to ~35-45 in portfolio

---

## Agenda 4: Stop Loss Rate and Exit Optimization

**[Strat-1 (Swing Trade Specialist)]**: The 63.2% overall SL rate remains our persistent structural problem. Let me present the exit breakdown analysis:

```
Exit Type    | Count | %     | Total PnL   | Avg PnL    | Per-Trade Edge
stop_loss    | 110   | 63.2% | -$29,984    | -$272.58   | Primary loss driver
take_profit  | 34    | 19.5% | +$20,926    | +$615.48   | Primary profit source
time_exit    | 28    | 16.1% | +$9,706     | +$346.66   | Secondary profit
```

System expectancy per trade:
```
E = 0.195 * $615.48 + 0.161 * $346.66 - 0.632 * $272.58
  = $120.02 + $55.81 - $172.27
  = +$3.56 per trade
```

A $3.56 per-trade expectancy on 174 trades produces $619 total PnL -- compared to actual +$848 (total net PnL after adjustments). The system is barely break-even on a per-trade basis.

The target SL rate is <50%. We are 13 percentage points above target. Every 1% reduction in SL rate translates to approximately 1.7 additional non-SL exits (on 174 trades), each worth approximately +$480 (weighted average of TP and time_exit PnL). So a 13% SL rate reduction would convert approximately 22 trades from SL to TP/time_exit, adding approximately $22 * ($480 - (-$273)) = $22 * $753 = $16,566 in PnL.

This is the single highest-impact improvement available if we can achieve it.

**[Strat-5 (Quant Algorithm Expert)]**: Let me examine whether the 1.0 ATR SL is the right level based on the MFE/MAE data.

```
Portfolio MFE/MAE:
  consec_down: MFE 2.11%, MAE 2.22%, ratio 0.95x
  rsi_mr:      MFE 3.14%, MAE 3.17%, ratio 0.99x
  vol_div:     MFE 2.13%, MAE 2.58%, ratio 0.83x
```

These MFE/MAE ratios below 1.0x indicate that on average, trades move against us more than they move in our favor. In a viable trading system, you need MFE/MAE > 1.2x at minimum.

However, the solo MFE/MAE tells a different story:
```
consec_down: 1.06x (marginal edge)
rsi_mr:      1.08x (marginal edge)
vol_div:     1.40x (strong edge)
```

The portfolio context degrades MFE/MAE for all strategies. This confirms that the portfolio selection and GDR timing effects are corrupting signal quality, as discussed in Agenda 2.

Regarding the SL level: the user notes that MFE/MAE analysis suggests optimal SL at ~0.7-0.9 ATR. Tightening SL from 1.0 to 0.8 ATR would:
- Reduce average loss: -$273 * 0.8 = -$218 (save $55 per SL exit)
- Increase SL rate: more trades would be stopped out before bouncing
- Net effect: uncertain, depends on how many trades in the 0.8-1.0 ATR MAE band would have become winners

**[Strat-1 (Swing Trade Specialist)] responding to Strat-5**: I strongly oppose tightening SL below 1.0 ATR. We have three backtests showing that tighter SLs increase the stop-out rate, which feeds the GDR circular dependency. The 8th-to-9th transition from 1.5 to 1.0 ATR was validated, but going below 1.0 risks repeating the cascading failure pattern.

The SL problem is not the distance -- it is the entry quality. If we tighten rsi_mr entries (RSI 30 -> 25), the SL rate for rsi_mr should drop from 64% to ~50-55%. consec_down at 57% SL rate also needs attention. Let me look at its entry conditions.

consec_down RSI_MAX is currently 45 (reduced from 50 in 10th panel). The 57% SL rate suggests some of the RSI 35-45 entries are still too loose. However, consec_down's portfolio PF is 1.47 (excellent) and its solo DD is 1.9%. I do NOT recommend further tightening consec_down -- the strategy works well despite the SL rate because its winners are substantially larger than its losers.

**[Strat-2 (Portfolio Risk Manager)]**: I want to address the breakeven activation. Current breakeven_activation_atr is 0.6 (moved SL to entry after 0.6 ATR profit). How is this interacting with the SL rate?

In theory, breakeven activation should reduce realized SL losses because some trades that dip after an initial profit would be stopped at breakeven rather than at the SL level. But the 63% SL rate suggests most losing trades never reach 0.6 ATR profit -- they go directly against us from entry.

If 63% of trades never reach 0.6 ATR MFE, breakeven activation is irrelevant for those trades. It only helps the remaining 37% (roughly the winning trades) by protecting their initial profits. This is still valuable, but it does not address the core SL rate problem.

I support keeping breakeven at 0.6 ATR. It is not the solution, but it is not causing harm.

**[Strat-3 (Market Microstructure Expert)]**: One point on SL execution. The backtest simulates SL triggers using daily high/low. In reality, intraday price action may touch the SL level and then reverse within the same bar. The backtest cannot capture this nuance -- if daily_low <= SL_price, the trade is stopped out, even if the close was above SL.

This means our backtest SL rate is likely **overstated** compared to live trading with minute-bar SL checking. Some of the 110 SL exits would, in reality, have briefly touched the SL level and recovered. The actual live SL rate might be 55-58% instead of 63%.

However, the converse is also true: in live trading, gaps below SL would produce worse fills than the backtest assumes. These effects roughly cancel out.

**Panel Consensus on Agenda 4:**
- **KEEP** SL at 1.0 ATR for all long positions (do not tighten or loosen)
- **KEEP** breakeven_activation at 0.6 ATR (helpful but not the core fix)
- SL rate reduction must come from entry quality improvements (Agenda 2, rsi_mr RSI 30->25)
- **DO NOT** adjust consec_down SL parameters (PF 1.47 is strong despite 57% SL rate)
- Expected SL rate improvement: 63% -> ~55-58% (from rsi_mr entry tightening alone)

---

## Agenda 5: Declining Return Trend and Structural Assessment

**[Strat-4 (Trade Analyst)]**: The return trend across backtests is concerning:

```
9th:  +4.9% (308 trades, no GDR, no circuit breaker)
10C:  -3.9% (98 trades, circuit breaker death spiral)
11th: +1.3% (174 trades, GDR with 51% Tier 2)
```

Adjusted for trade count:
```
9th:  +$15.91 per trade (308 trades)
10C:  -$39.80 per trade (98 trades -- corrupted by circuit breaker)
11th: +$4.89 per trade (174 trades)
```

The per-trade edge has declined from $15.91 (9th) to $4.89 (11th). This is a 69% decline in per-trade profitability. Is this a parameter optimization artifact or a genuine edge erosion?

Let me decompose the sources:

1. **GDR drag**: Trades executed in Tier 1 and Tier 2 have reduced position sizes, so their PnL contribution is proportionally smaller. If we estimate that 61% of trades occur in Tier 1/2 with 50%/25% of normal sizing, the average trade PnL is mechanically reduced by approximately 40%.

2. **Signal quality changes**: The 10B signal improvements (RSI_MAX 45, TP cap 2.0, diversity bonus) were validated as positive or neutral in the 10th analysis. These should not reduce per-trade edge.

3. **Selection bias**: With fewer total trades (174 vs 308), the ranking system selects a different subset. The 9th ran every signal; the 11th is filtered through GDR entry limits, soft caps, and diversity bonuses. The filtering may inadvertently exclude profitable trades.

My assessment: The declining return is **primarily GDR-driven**, not a fundamental edge loss. The strategies' solo performance remains healthy (rsi_mr PF 1.195, consec_down PF 1.423, vol_div PF 1.279). The portfolio assembly and risk management layer is destroying value rather than preserving it.

**[Strat-5 (Quant Algorithm Expert)]**: Let me quantify the "portfolio efficiency" -- how much solo alpha the portfolio captures.

```
Solo return sum: +5.8% + 5.4% + 4.7% = +15.9% (if each ran with full capital)
Equal-weight solo: +15.9% / 3 = +5.3% (equal capital allocation)

Portfolio actual: +1.3%
Portfolio efficiency: 1.3% / 5.3% = 24.5%
```

The portfolio captures only 24.5% of the available solo alpha. In the 9th backtest:

```
9th portfolio: +4.9%
9th solo sum (estimated): ~+15% (similar solo performance)
9th efficiency: 4.9% / 5.0% = ~98% (but this includes favorable cross-strategy timing)
```

Wait -- the 9th efficiency appears much higher, but that is because the 9th had no GDR, no soft caps, and no diversity bonus. It ran every signal it could. The portfolio was inefficient in DD terms (50.4%) but efficient in alpha capture.

The 11th's GDR and structural controls have reduced alpha capture by approximately 75%. We traded DD control (46.2% vs 50.4%, a marginal 4% improvement) for a 73% reduction in returns. This is a terrible trade-off.

**[Strat-2 (Portfolio Risk Manager)]**: I must defend the GDR concept while acknowledging the calibration failure. The GDR is meant to protect capital during genuine stress periods. The problem is that **the current system's normal DD exceeds the GDR's stress threshold**.

This is not a GDR design flaw -- it is a DD problem. If we could reduce the system's structural DD to 25-30% (through entry quality improvements), the current GDR thresholds (15%/25%) would function correctly, only activating during genuine stress.

The alternative approach (widening GDR thresholds to match current DD) is pragmatic but accepts the 45-50% DD as structural. I want to be explicit about this trade-off: **widening GDR means accepting deep drawdowns as the cost of maintaining returns**.

For a $1K-$5K account with aggressive risk tolerance, this may be acceptable. A 45% DD on a $3K account is a $1,350 loss -- significant but not catastrophic. The user has explicitly stated aggressive risk tolerance.

**[Strat-1 (Swing Trade Specialist)]**: Strat-2 raises the key trade-off. Let me frame it as two distinct strategies for the 12th backtest:

**Strategy A: Fix the DD, keep tight GDR** (reduce DD to match thresholds)
- Requires: dramatically tighter entry filters, possibly removing rsi_mr's short positions, adding market regime filter
- Expected: DD 25-30%, Return +3-5%, GDR rarely activates
- Risk: Too many simultaneous changes, high risk of overfitting (10th lesson)
- Timeline: Would require 2-3 additional backtest iterations to validate

**Strategy B: Accept the DD, widen GDR** (widen thresholds to match reality)
- Requires: GDR threshold adjustment (simple parameter change), RSI tightening (moderate parameter change)
- Expected: DD 42-48%, Return +3-5%, GDR activates less frequently
- Risk: Deep DD accepted as structural; if live market is more volatile than synthetic, DD could exceed 50%
- Timeline: Single backtest iteration

I advocate for **Strategy B** for the 12th backtest, with Strategy A elements (market regime filter, entry quality) deferred to 13th. Reason: Strategy B is a smaller change set with more predictable interaction effects. We have been burned twice (10th, 11th) by making too many changes simultaneously.

**[Strat-5 (Quant Algorithm Expert)]**: I support Strategy B. But I want to add a critical caveat. We have now run backtests 8th through 11th on seed=42. Each iteration optimizes parameters to fit the same synthetic price paths. We are deep into overfitting territory.

The 12th backtest should be the LAST iteration on seed=42. After 12th, regardless of outcome, we must validate with multiple seeds (42, 123, 456, 789) to test out-of-sample robustness. If the system only works on seed=42, all our optimization is worthless.

**Panel Consensus on Agenda 5:**
- Declining returns are primarily GDR-driven, not fundamental edge loss
- Solo strategies retain genuine edges; the portfolio layer destroys alpha
- **ADOPT Strategy B**: Widen GDR thresholds to match system's DD profile
- Accept 42-48% DD as structural for an aggressive swing trading system
- rsi_mr RSI tightening (30->25) provides moderate DD reduction
- **MANDATE** multi-seed validation after 12th backtest (regardless of outcome)
- Market regime filter remains highest-priority structural improvement for 13th

---

## Agenda 6: 12th Backtest Parameter Consensus

**[Strat-5 (Quant Algorithm Expert)]**: Based on our discussion, here is the consolidated change set for the 12th backtest. I am categorizing by priority and flagging interaction risks.

---

### 12th Backtest Changes -- Detailed Decision Table

#### P0 (Must Do) -- GDR Recalibration

| # | Parameter | Location | 11th Value | 12th Value | Rationale |
|---|---|---|---|---|---|
| 1 | GDR_TIER1_DD | batch_simulator.py | 0.15 (15%) | **0.25 (25%)** | Current 15% inside normal DD range; system spends 51% in Tier 2 |
| 2 | GDR_TIER2_DD | batch_simulator.py | 0.25 (25%) | **0.35 (35%)** | Allow system to operate at full capacity longer before risk reduction |
| 3 | GDR_ROLLING_WINDOW | batch_simulator.py | 60 days | **90 days** | Longer memory prevents premature return to full risk after deep DD |

#### P0 (Must Do) -- rsi_mr Signal Quality

| # | Parameter | Location | 11th Value | 12th Value | Rationale |
|---|---|---|---|---|---|
| 4 | RSI_OVERSOLD | rsi_mean_reversion.py | 30 | **25** | Reduce SL rate from 64% to ~50-55%; only deeply oversold entries |

#### P1 (Should Do) -- Portfolio Diversity

| # | Parameter | Location | 11th Value | 12th Value | Rationale |
|---|---|---|---|---|---|
| 5 | Diversity bonus (0 pos) | ranking.py | +0.25 | **+0.35** | vol_div still suppressed at 22 trades; escalate diversity incentive |
| 6 | Diversity bonus (1 pos) | ranking.py | +0.10 | +0.10 | Keep unchanged; single-position strategies already have adequate incentive |

#### Explicitly Unchanged (KEEP)

| Parameter | Value | Location | Reason |
|---|---|---|---|
| RISK_PER_TRADE_PCT | 0.02 (2%) | batch_simulator.py | Validated across 9th and 11th; do not change |
| SL ATR mult (all long) | 1.0 | exit_rules.py | Validated across 8th-11th; SL rate issue is entry quality not SL distance |
| SL ATR mult (rsi_mr short) | 1.5 | exit_rules.py | No data to justify change |
| breakeven_activation_atr | 0.6 | exit_rules.py | Working as designed; provides winner protection |
| MAX_TOTAL_POSITIONS | 5 | batch_simulator.py | Moderate cap validated in 11th |
| MAX_LONG_POSITIONS | 4 | batch_simulator.py | Proportional to MAX_TOTAL=5 |
| MAX_SHORT_POSITIONS | 3 | batch_simulator.py | No change needed |
| max_hold_days | 5 | exit_rules.py | Already optimized |
| max_daily_entries (baseline) | 2 | batch_simulator.py | GDR controls this dynamically |
| gap_threshold | 0.05 | batch_simulator.py | Already optimized |
| consec_down RSI_MAX | 45 | consecutive_down.py | PF 1.47 in portfolio; do not touch |
| rsi_mr TP ATR cap | 2.0 | exit_rules.py / yaml | Validated in 10B |
| vol_div regime_compat | 0.85 | ranking.py | Validated in 10B |
| SOFT_STRATEGY_CAP | 2 | batch_simulator.py | Working as designed |
| BB_LONG_ENTRY_PCT_B | 0.05 | rsi_mean_reversion.py | Do not change multiple rsi_mr params |
| ADX_MAX | 25 | rsi_mean_reversion.py | Defer to 13th |

#### GDR Tier Configuration (12th Backtest)

```
Rolling Peak: 90-day equity high (extended from 60)

Tier 0 (DD < 25%):
  - RISK_PER_TRADE: 2.0%
  - max_daily_entries: 2
  - Status: Normal operation

Tier 1 (DD 25-35%):
  - RISK_PER_TRADE: 1.0%
  - max_daily_entries: 1
  - Status: Caution mode

Tier 2 (DD > 35%):
  - RISK_PER_TRADE: 0.5%
  - max_daily_entries: 1
  - Status: Minimal mode (NO halt)
```

---

### Expected Impact (Conservative Estimates)

**[Strat-5 (Quant Algorithm Expert)]**: Following the lesson from 9th and 10th panels, I am using deliberately wide uncertainty ranges. Our prediction track record is poor -- the 10th panel missed on every single metric.

| Metric | 11th Actual | 12th Conservative | 12th Optimistic |
|---|---|---|---|
| Trades | 174 | 160-200 | 200-250 |
| Win Rate | 32.8% | 33-37% | 37-40% |
| Profit Factor | 1.027 | 1.03-1.12 | 1.12-1.25 |
| Return | +1.3% | +2-5% | +5-8% |
| Sharpe | 0.645 | 0.8-1.2 | 1.2-1.5 |
| Max DD | 46.2% | 42-50% | 35-42% |
| vol_div Trades | 22 | 30-45 | 45-60 |
| Tier 2 Days | 127 (51%) | 30-70 (12-28%) | 10-30 (4-12%) |
| SL Rate | 63.2% | 55-60% | 50-55% |

**Key Uncertainty Factors:**
1. GDR threshold widening has never been tested; interaction with the new rsi_mr entry filter is unknown
2. RSI 30->25 may reduce rsi_mr trades more than expected if few signals fall in the 25-30 RSI band on this particular seed
3. Diversity bonus +0.35 may push weak vol_div signals into the portfolio, degrading overall quality
4. Rolling window 60->90 changes the DD calculation dynamics in ways that are hard to predict analytically

**[Strat-4 (Trade Analyst)]**: Note on trade count prediction: RSI 30->25 reduces rsi_mr from ~103 to ~65-75 trades. With wider GDR (more Tier 0 days), other strategies get more entries. But total trades may still be lower because we are filtering out ~30 rsi_mr signals. My estimate: 160-200 total trades.

---

### Sub-Test Plan

**[Strat-1 (Swing Trade Specialist)]**: Given our lesson from the 10th (interaction effects between simultaneous changes), I recommend a focused sub-test approach. However, unlike the 10th where we ran 3 sub-tests, I want to limit to 2 sub-tests this time. More tests means more seed=42 optimization.

**12A: GDR Recalibration Only**
- Changes: GDR Tier 1 15%->25%, Tier 2 25%->35%, rolling window 60->90 days
- Purpose: Isolate the GDR threshold effect on returns and DD
- Keep everything else identical to 11th
- Expected: Return increases to +3-5%, DD may increase to 48-50%, Tier 2 drops to ~20-30%

**12B: Full Change Set (GDR + rsi_mr + diversity bonus)**
- Changes: All 6 changes from the decision table above
- Purpose: Measure combined effect of recalibrated GDR + tighter entries + stronger diversity
- Expected: Return +2-5%, DD 42-48%, vol_div > 30 trades

Compare 12A vs 12B:
- If 12B Return > 12A Return: The rsi_mr and diversity changes add value on top of GDR fix
- If 12B Return < 12A Return: The additional changes are counterproductive (negative interaction)
- If 12B DD < 12A DD: The rsi_mr entry tightening is reducing DD as intended
- If 12B DD > 12A DD: The changes are interacting in unexpected ways

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: Two sub-tests is appropriate. But I want to add specific diagnostic metrics to track in both runs:

1. **GDR Tier Distribution**: Days in each tier (must compare 12A vs 12B)
2. **Per-strategy SL rate**: Especially rsi_mr SL rate in 12B (target < 55%)
3. **vol_div trade count and WR**: In 12B (target > 30 trades, WR > 30%)
4. **Average composite score of selected signals**: Must not drop below 0.35 in 12B
5. **MFE/MAE per strategy**: Must improve toward >1.1x for portfolio context
6. **Equity curve shape**: Check for grinding decline patterns vs recovery-capable drawdowns

---

### PASS/FAIL Criteria for 12th Backtest

**[Strat-2 (Portfolio Risk Manager)]**: Based on our trajectory (9th: +4.9%, 11th: +1.3%), the 12th must demonstrate meaningful improvement, not just marginal positive return.

**PASS (Proceed to 13th with refinements):**
- Return > +3.0%
- PF > 1.05
- Max DD < 48% (must not regress from 11th's 46.2% by more than 2%)
- Tier 2 Days < 30% of total (down from 51%)
- SL Rate < 58%
- vol_div > 25 trades with PF > 0.8
- No single strategy WR < 25%

**CONDITIONAL PASS (Proceed with caution):**
- Return > +1.0% (at least match 11th)
- PF > 1.0
- Max DD < 50%
- Tier 2 Days < 40% (meaningful reduction from 51%)

**FAIL (Fundamental redesign needed):**
- Return < 0% (system loses money)
- PF < 0.95
- Max DD > 50% (regression to 9th levels)
- Total trades < 130 (system is over-constrained again)
- Tier 2 Days > 45% (GDR recalibration failed)

**[Strat-5 (Quant Algorithm Expert)]**: If 12th FAILs, the fundamental redesign should include:
1. Market regime filter (SPY > 50-EMA, deferred three times now)
2. Strategy reduction to consec_down + vol_div only (removing rsi_mr entirely)
3. Multi-seed robustness validation
4. Possible architectural change to run strategies as independent portfolios with separate capital allocation

---

## Dissenting Opinions and Risk Flags

**[Strat-1 (Swing Trade Specialist)]**: My deferred market regime filter is now overdue by three backtests. Every panel has acknowledged that entry quality is the core issue, yet we keep adjusting exit rules, position sizes, and risk controls. The market regime filter (SPY > 50-EMA to allow longs) would immediately reduce SL rate by preventing entries during broad market declines. I request that if 12th results show SL rate still above 55%, the market regime filter becomes P0 for 13th -- no more deferrals.

**[Strat-5 (Quant Algorithm Expert)]**: The GDR threshold widening from 15%/25% to 25%/35% is a significant loosening of risk controls. In a worst-case scenario, the system could now endure 35% DD before entering minimal mode. On a $3,000 account, that is a $1,050 loss before risk reduction kicks in. The user has stated aggressive risk tolerance, but I want to be explicit: **we are accepting ~35% drawdown as normal operation**.

Additionally, the RSI_OVERSOLD change from 30 to 25 may interact with the GDR in unexpected ways. Fewer rsi_mr signals means fewer total trades. With fewer trades, each individual trade has more impact on the equity curve. A single bad rsi_mr trade at full 2% risk (Tier 0) now moves the needle more. The portfolio becomes more concentrated and potentially more volatile per-trade.

**[Strat-3 (Market Microstructure Expert)]**: I want to flag a concern about the diversity bonus increase (+0.25 -> +0.35). With +0.35 bonus, a vol_div signal with base composite score of 0.30 gets boosted to 0.65, which would rank above most rsi_mr and consec_down signals with natural composites of 0.55-0.60. We are potentially forcing weak vol_div signals into the portfolio ahead of strong signals from other strategies.

Proposed safeguard: track the **unboosted composite score** of all selected signals in 12B. If the average unboosted score drops below 0.40, the diversity bonus is too aggressive and should be reduced to +0.30 in the next iteration.

**[Strat-4 (Trade Analyst)]**: My standing concern: seed=42 overfitting. We have now run 4+ backtests on the same synthetic data. Every parameter adjustment is calibrated to this specific price sequence. The system's real-world performance will likely be worse than any of our backtest results.

I want to formalize a commitment: **after 12th, run 12th parameters on seeds 123, 456, and 789**. If performance varies by more than 30% across seeds, our optimization is likely overfit.

**[Strat-2 (Portfolio Risk Manager)]**: The 11th showed that the GDR, while preventing death spirals, creates a new problem: asymmetric recovery drag. The 12th's wider thresholds address this, but they do so by accepting deeper drawdowns. If the live market is more volatile than our synthetic data (which it almost certainly is), the actual DD could exceed 50%, and GDR Tier 2 would activate at 35% -- which is better than 25% but still potentially in the system's normal range in real markets.

I recommend that after multi-seed validation, we run one backtest with real historical data (Alpaca 2-year daily bars) before going live. Synthetic data has taught us what it can, but the real market will have fat tails, earnings gaps, sector rotation, and liquidity events that synthetic GBM does not capture.

---

## Implementation Priority

1. **Parameter changes (low risk):**
   - GDR_TIER1_DD: 0.15 -> 0.25 in batch_simulator.py
   - GDR_TIER2_DD: 0.25 -> 0.35 in batch_simulator.py
   - GDR_ROLLING_WINDOW: 60 -> 90 in batch_simulator.py
   - RSI_OVERSOLD: 30 -> 25 in rsi_mean_reversion.py
   - Diversity bonus (0 pos): +0.25 -> +0.35 in ranking.py

2. **Diagnostic additions (medium risk):**
   - Track GDR tier distribution in backtest output
   - Track unboosted composite score of selected signals
   - Track per-strategy MFE/MAE in portfolio context
   - Track Tier 0/1/2 entry counts and per-tier PnL

3. **Deferred to 13th backtest:**
   - Market regime filter (SPY > 50-EMA)
   - ADX_MAX tightening (25 -> 20)
   - Strategy rotation priority system
   - Portfolio weight optimization
   - Multi-seed robustness validation (mandatory)

---

## Summary of 9th -> 10th -> 11th -> 12th Evolution

```
9th Baseline:
  RISK=2%, MAX_TOTAL=6, no circuit breaker, no GDR
  Result: 308 trades, PF 1.043, Return +4.9%, DD 50.4%
  Issue: Uncontrolled DD, conveyor belt of losses

10th (failed):
  RISK=1.5%, MAX_TOTAL=4, circuit breaker DD>10%/7d halt
  Result: 98-114 trades, PF 0.76-0.80, Return -3.9% to -5.5%, DD 43.9-45.7%
  Root cause: Circuit breaker death spiral + over-constrained sizing

11th (conditional pass):
  RISK=2%, MAX_TOTAL=5, GDR Tier 15%/25%, 60d rolling peak
  Result: 174 trades, PF 1.027, Return +1.3%, DD 46.2%
  Root cause: GDR thresholds inside normal DD range; 51% Tier 2 suppresses returns

12th (proposed):
  RISK=2%, MAX_TOTAL=5, GDR Tier 25%/35%, 90d rolling peak, RSI_OVERSOLD 25
  Target: 160-250 trades, PF 1.03-1.25, Return +2-8%, DD 35-50%
  Philosophy: Accept deep DD, maximize alpha capture, improve entry quality
```

**Panel sign-off**: All 5 experts agree on the 12th backtest parameter set. Two sub-tests (12A: GDR only, 12B: full changes). Evaluate against PASS/FAIL criteria defined above. Multi-seed validation mandatory after 12th, regardless of outcome.
