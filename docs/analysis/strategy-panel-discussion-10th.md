# Strategy Panel Discussion: 10th Backtest Failure Analysis

**Date**: 2026-02-28
**Format**: 5-Expert Emergency Panel -- Post-Mortem and 11th Backtest Redesign
**Data**: 10th Backtest (10A/10B/10C variants, $100K initial, 251 trading days, S&P 500 universe)

---

## Panel Members

| ID | Role | Expertise |
|---|---|---|
| Strat-1 | Swing Trade Expert | Entry/exit timing, market condition |
| Strat-2 | Quant Researcher | ATR multipliers, parameter statistics |
| Strat-3 | Risk Manager | Position sizing, drawdown control |
| Strat-4 | Trade Analyst | Backtest interpretation, MFE/MAE patterns |
| Strat-5 | Quant Algorithm Expert | Portfolio math, Kelly criterion, correlation |

---

## 10th Backtest Results Summary

| Metric | 9th Baseline | 10A (Risk Only) | 10B (Signal Only) | 10C (Full) |
|---|:---:|:---:|:---:|:---:|
| Trades | 308 | 114 | 263 | 98 |
| Win Rate | 36.4% | 30.7% | 33.8% | 24.5% |
| Profit Factor | 1.043 | 0.763 | 1.028 | 0.796 |
| Return | +4.9% | -5.5% | +3.2% | -3.9% |
| Sharpe | 1.172 | 0.782 | 1.188 | 0.781 |
| Max DD | 50.4% | 45.7% | 50.3% | 43.9% |

### 10C Per-Strategy Breakdown

| Strategy | Trades | WR | PnL | PF |
|---|---|---|---|---|
| rsi_mean_reversion | 62 | 21.0% | -$4,483 | 0.62 |
| consecutive_down | 33 | 33.3% | +$258 | 1.03 |
| volume_divergence | 3 | 0.0% | -$237 | 0.00 |

### Prediction vs Reality

| 9th Panel Prediction | 10th Actual (10C) | Deviation |
|---|---|---|
| DD 15-22% | 43.9% | 2x over |
| Return +8-12% | -3.9% | Wrong direction |
| Sharpe 1.3-1.6 | 0.781 | Less than half |
| vol_div 40-60 trades | 3 trades | 95% shortfall |

---

## Agenda 1: Circuit Breaker Failure Analysis

**[Strat-5 (Quant Algorithm Expert)]**: The circuit breaker is the single largest contributor to the 10th backtest failure. Let me quantify why with formal analysis.

**Defining "Normal Operating Drawdown"**: The system's normal DD range is a function of win rate, position count, correlation, and risk per trade. Let me compute it.

With 10A parameters (RISK=1.5%, MAX_TOTAL=4, correlation rho=0.4):

```
Portfolio sigma per concurrent event:
  sigma_p = R * sqrt(N + N*(N-1)*rho)
          = 0.015 * sqrt(4 + 4*3*0.4)
          = 0.015 * sqrt(8.8)
          = 0.015 * 2.97
          = 4.45% per stop-out cycle
```

With WR=30.7% (10A observed), consecutive losing streaks are common:

```
P(3 consecutive losses) = 0.693^3 = 33.3% (once every 3 cycles)
P(5 consecutive losses) = 0.693^5 = 15.5% (once every 6-7 cycles)
```

Expected DD from 3 consecutive full portfolio stop-outs:

```
DD_3_cycle = 1 - (1 - 0.0445)^3 = 12.7%
DD_5_cycle = 1 - (1 - 0.0445)^5 = 20.4%
```

**The critical finding**: A 3-cycle consecutive loss event (12.7% DD) occurs approximately once every 3 portfolio turnover cycles. With 2 entries/day and ~2 trades/week average throughput, a full cycle is roughly 2 weeks. So a 10% DD event occurs roughly every 6 weeks -- approximately 4-5 times per year.

This means the 10% circuit breaker triggers during **normal operation**, not during exceptional stress. It is a filter that blocks normal trading, not a safety mechanism.

In 10A, 33 circuit breaker events with 119 days blocked (47% of all trading days) confirms this mathematically: the system spends nearly half its time in a state that the circuit breaker considers "abnormal" but is actually expected behavior given the parameters.

**The death spiral mechanism**: After circuit breaker release, the equity is already depressed. The peak_equity is still at the old high. So a minor drawdown from the reduced equity base immediately re-triggers the circuit breaker:

```
Example:
  Peak equity: $100,000
  CB triggers at: $90,000 (10% DD)
  7-day pause, equity stays ~$90,000
  CB releases, 1 losing trade: equity -> $88,700 (1.5% loss)
  New DD from peak: ($100,000 - $88,700) / $100,000 = 11.3%
  CB re-triggers immediately
```

This is a structural flaw. The peak_equity never resets, so every re-trigger occurs at a progressively lower equity while the peak remains at the all-time high.

**My recommendation**: The circuit breaker in its current form must be either fundamentally redesigned or removed. A 10% threshold with static peak is mathematically incompatible with this system's normal DD profile.

**[Strat-3 (Risk Manager)] responding to Strat-5**: I designed the circuit breaker recommendation in the 9th panel. I accept the failure. The math is clear -- 10% was too aggressive and the static peak created the death spiral. Let me propose the fix.

The issue has two components:
1. **Threshold too low**: 10% is within normal operating DD
2. **Binary response**: complete shutdown vs. no restriction is too blunt

I propose replacing the circuit breaker with a **graduated drawdown response** (GDR):

```
Tier 0 (DD <  15%): Normal operation. max_daily_entries = 2
Tier 1 (DD 15-25%): Caution mode.    max_daily_entries = 1
Tier 2 (DD >  25%): Halt mode.       max_daily_entries = 0, 3-day pause
```

Key design differences from the failed circuit breaker:
- **Higher threshold**: Tier 1 starts at 15%, which is outside the normal 12.7% 3-cycle DD
- **Graduated response**: Tier 1 reduces entry rate instead of halting completely. The system can still capture opportunities at reduced pace
- **Rolling peak**: Use 60-day rolling equity high instead of all-time peak. This prevents the death spiral where old peaks trap the system permanently
- **Shorter pause**: Tier 2 is only 3 calendar days, not 7

**[Strat-1 (Swing Trade Expert)] responding to Strat-3**: The graduated approach is correct, but I want to challenge one thing: do we even need Tier 2? If Tier 1 reduces entries to 1/day, the system is already significantly risk-constrained. Adding a full halt at 25% may create the same death spiral at a different level.

In 18 years of swing trading, I have never used a full trading halt. When drawdowns get severe, I reduce size -- I trade 50% or 25% position sizes -- but I never stop trading entirely. The edge does not disappear during drawdowns; only the position size should change.

My counter-proposal:

```
DD < 15%:  Normal.     RISK_PER_TRADE = 2.0%, entries = 2/day
DD 15-25%: Reduced.    RISK_PER_TRADE = 1.0%, entries = 1/day
DD > 25%:  Minimal.    RISK_PER_TRADE = 0.5%, entries = 1/day
```

No halt at any level. Just graduated size reduction.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: Strat-1's approach has theoretical support. In Kelly criterion framework, the optimal response to a shrinking bankroll is proportional bet reduction, not cessation. A gambler with a positive edge should never stop playing -- they should reduce stakes.

However, I want to add a nuance. The "no halt" approach assumes our edge is real and persistent. With WR 36.4% and PF 1.043, our edge is razor-thin. During a true regime change (not just noise), continuing to trade at any size bleeds capital. We need a mechanism to distinguish "normal drawdown" from "edge loss."

For now, I support Strat-1's graduated size reduction with one modification: track the **rolling 30-trade win rate**. If it drops below 25% (significantly below system WR of 36%), apply an additional 50% size reduction regardless of DD tier. This gives a signal-quality based brake, not just equity-based.

**[Strat-4 (Trade Analyst)]**: Let me add data perspective. In 10A, the circuit breaker blocked 119 trading days. During those blocked days, I estimated the missed opportunity by checking what 10B (which has no circuit breaker) did during those periods. The 10B system generated an estimated $2,800 in profit during the 119 days that 10A was sitting idle. The circuit breaker did not just fail to protect -- it actively destroyed the system's ability to recover.

**[Strat-2 (Quant Researcher)]**: One more issue with peak_equity. In a system with max DD of 50%, the peak_equity is essentially "never reached again" for most of the backtest. This means the circuit breaker is in a permanent triggering state once the first significant DD occurs. We absolutely need the rolling peak concept.

**Panel Consensus on Agenda 1**:
- **REMOVE** current circuit breaker (DD 10% + 7-day halt + static peak)
- **REPLACE** with graduated drawdown response using rolling 60-day peak:
  - DD < 15%: Normal operation (RISK=2.0%, entries=2/day)
  - DD 15-25%: Reduced mode (RISK=1.0%, entries=1/day)
  - DD > 25%: Minimal mode (RISK=0.5%, entries=1/day, NO full halt)
- Rolling peak resets to 60-day rolling equity high (not all-time peak)
- No full trading halt at any level -- graduated reduction only

---

## Agenda 2: Position Sizing Rollback

**[Strat-4 (Trade Analyst)]**: Let me present the 10A data that shows the position sizing changes were counterproductive.

10A applied: RISK 2%->1.5%, MAX_TOTAL 6->4, MAX_LONG 5->3, circuit breaker.

The trade count dropped from 308 to 114 -- a 63% reduction. This is not just position *sizing* shrinkage; it is position *count* destruction. The system's edge comes from a large number of small bets. With 114 trades, we are below the statistical significance threshold for a 36% WR system.

```
Expected standard error of WR estimate:
  SE = sqrt(WR * (1-WR) / N)

  N=308: SE = sqrt(0.364 * 0.636 / 308) = 2.7%  -> 95% CI: [31.0%, 41.8%]
  N=114: SE = sqrt(0.307 * 0.693 / 114) = 4.3%  -> 95% CI: [22.1%, 39.3%]
```

With only 114 trades, the observed WR of 30.7% has a confidence interval so wide that the true WR could be anywhere from 22% to 39%. We cannot distinguish our system from random at 114 trades.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-4**: I agree that the trade count drop is catastrophic. But let me separate the effects of MAX_TOTAL vs RISK% vs circuit breaker.

- **RISK 2%->1.5%**: This reduces position *size* (dollars per trade), not position *count*. A $300 position becomes $225. The trade still executes. This alone should NOT reduce trade count.
- **MAX_TOTAL 6->4**: This reduces the maximum number of concurrent positions. With average holding period of 3 days and 2 entries/day, the old system could have up to 6 concurrent positions. With cap at 4, once 4 are open, no new entries until exits occur. This does reduce trade count but not by 63%.
- **Circuit breaker**: This blocks ALL entries for 7 days. With 33 events blocking 119 days, this is the primary driver of trade count reduction.

My estimate of individual contributions to the 308->114 trade drop:
```
Circuit breaker effect: ~140 trades blocked (47% of trading days)
MAX_TOTAL 6->4 effect: ~30-40 trades blocked (position cap constraints)
Interaction effect: ~15-20 trades (CB + cap compounding)
```

Conclusion: The circuit breaker alone accounts for approximately 72% of the trade reduction. MAX_TOTAL reduction accounts for about 20%. RISK% has near-zero impact on trade count.

**[Strat-3 (Risk Manager)]**: Given this decomposition, the path is clear:
1. **RISK_PER_TRADE**: Keep at 2.0% (rollback from 1.5%). The Kelly analysis showed 1.17% as optimal, but 2.0% with 4-5 positions gives reasonable exposure. 1.5% was an unnecessary restriction that shrank PnL without helping DD.
2. **MAX_TOTAL**: Move to 5 (compromise between 6 and 4). This allows reasonable diversification without excessive correlation exposure.
3. **MAX_LONG**: Move to 4 (proportional to MAX_TOTAL 5).
4. **Circuit breaker**: Replace with GDR as agreed in Agenda 1.

**[Strat-1 (Swing Trade Expert)] responding to Strat-3**: I support RISK back to 2.0%. In practical trading, 2% risk per trade with 5 concurrent positions is standard for aggressive swing trading. We are trading a $1K-$5K account -- position sizes are already tiny. Further reduction makes individual trade PnL nearly invisible.

However, I want to flag that MAX_TOTAL=5 with MAX_LONG=4 still leaves us exposed to all-long correlation during market declines. We should pair this with the GDR from Agenda 1. The two mechanisms together -- position cap at 5 plus graduated DD response -- provide layered protection without the binary shutdown problem.

**[Strat-2 (Quant Researcher)]**: One quantitative check on MAX_TOTAL=5 with RISK=2.0%:

```
sigma_portfolio = 0.02 * sqrt(5 + 5*4*0.4) = 0.02 * sqrt(13) = 0.02 * 3.61 = 7.2%
```

Per concurrent stop-out cycle is 7.2% portfolio risk. With the GDR Tier 1 at 15%, this means the system enters caution mode after 2 consecutive full stop-out cycles. That is reasonable -- 2 consecutive full stops is a genuine stress signal.

**Panel Consensus on Agenda 2**:
- **ROLLBACK** RISK_PER_TRADE: 1.5% -> 2.0% (return to 9th baseline)
- **MODIFY** MAX_TOTAL: 4 -> 5 (compromise, not full rollback to 6)
- **MODIFY** MAX_LONG: 3 -> 4 (proportional to MAX_TOTAL=5)
- **KEEP** MAX_SHORT: 3 (unchanged)
- Position sizing changes interact with GDR from Agenda 1

---

## Agenda 3: 10B as Foundation for 11th Backtest

**[Strat-4 (Trade Analyst)]**: 10B is the only variant that produced a positive return (+3.2%) and improved Sharpe (1.188 vs 1.172 baseline). Let me decompose what 10B changed and what worked:

10B changes applied:
- consecutive_down RSI_MAX: 50 -> 45
- rsi_mr ATR TP cap: 1.5 -> 2.0
- vol_div regime_compatibility: 0.70 -> 0.85
- Strategy diversity bonus in ranking

Results:
- 263 trades (vs 308 baseline) -- modest 15% reduction, mostly from consec_down signal tightening
- Sharpe 1.188 (marginal improvement over 1.172)
- DD 50.3% (essentially unchanged from 50.4%)

The 10B results are modest but directionally correct. The signal quality improvements did not hurt and slightly helped. The problem is that 10B did nothing for DD -- which was the primary goal.

**[Strat-2 (Quant Researcher)]**: Let me trace each 10B change's individual contribution:

1. **RSI_MAX 50->45 (consec_down)**: Reduced consec_down trades from approximately 80 to 55-60. The removed trades (RSI 45-50 range) were the weakest signals. This improved consec_down WR by approximately 3-4 percentage points. Positive change.

2. **TP cap 1.5->2.0 (rsi_mr)**: Allowed winners to develop further. Average TP exit PnL increased from $921 to approximately $1,050. But some trades that previously hit TP at 1.5 ATR now held longer and reverted, time-exiting at lower levels. Net effect: approximately neutral.

3. **vol_div regime_compat 0.70->0.85**: Minimal impact. vol_div still only generated 3-11 trades in the portfolio mix because the diversity bonus was not aggressive enough to overcome signal strength disadvantage.

4. **Diversity bonus (+0.15/+0.05)**: Helped marginally. vol_div trades went from 11 (9th) to approximately 15-20 in 10B. Still far below the 40-60 target.

**[Strat-5 (Quant Algorithm Expert)]**: The volume_divergence underperformance in portfolio mix persists even with 10B changes. This tells me the ranking formula needs a more fundamental adjustment. The current diversity bonus of +0.15 is insufficient when vol_div signal_strength is 0.35-0.55 versus 0.55-0.75 for other strategies.

Two options:
1. **Increase diversity bonus to +0.25 for 0 positions**: This may be enough to overcome the strength gap
2. **Per-strategy entry slot reservation**: Reserve 1 of the 2 daily entry slots for the underrepresented strategy. This guarantees vol_div gets at least 1 entry per day when it generates signals.

I prefer option 1 -- it is parametric rather than structural, and easier to tune in subsequent backtests.

**[Strat-1 (Swing Trade Expert)]**: Looking at this practically, vol_div's solo performance (PF 1.382, DD 4.3%) is the best of all three strategies. It is a waste to have a system that systematically suppresses its best-performing strategy. If we cannot get vol_div to 30+ trades via ranking adjustments, we should consider running it as a separate portfolio with its own capital allocation, not competing in the same ranking pool.

But for 11th backtest, let me support Strat-5's option 1 -- increase diversity bonus to +0.25. If 11th still shows vol_div < 20 trades, we escalate to structural changes.

**[Strat-3 (Risk Manager)]**: From a risk perspective, 10B's unchanged DD (50.3%) tells us that signal quality improvements alone cannot solve the DD problem. DD reduction requires position management changes. This confirms that we need BOTH tracks:
- Signal quality (10B changes, refined)
- Position management (GDR, position caps, but NOT the failed circuit breaker)

The 11th backtest should be 10B + "light risk management" (GDR + position cap at 5), explicitly avoiding the aggressive constraints that destroyed 10A.

**Panel Consensus on Agenda 3**:
- **ADOPT** 10B as the baseline for 11th backtest signal quality changes
- **KEEP** from 10B: RSI_MAX=45, TP cap=2.0, vol_div regime_compat=0.85
- **STRENGTHEN** diversity bonus: +0.15 -> +0.25 (for 0 positions), +0.05 -> +0.10 (for 1 position)
- **COMBINE** with GDR and moderate position caps (from Agendas 1-2)
- If vol_div < 20 trades in 11th, escalate to structural ranking changes

---

## Agenda 4: rsi_mean_reversion Structural Assessment

**[Strat-4 (Trade Analyst)]**: In 10C, rsi_mr had 62 trades, WR 21%, PF 0.62, PnL -$4,483. This is the single largest contributor to the portfolio's negative return. But we need to be careful about attributing this solely to the strategy.

Comparison across test variants:

```
rsi_mr performance (estimated):
  9th baseline:  ~190 trades, PF 1.116, main profit driver
  10A (risk):    ~40-50 trades, PF < 1.0 (starved by CB + position caps)
  10B (signal):  ~170 trades, PF ~1.05 (modest signal improvement)
  10C (full):    62 trades, WR 21%, PF 0.62 (worst of all)
```

The 10C rsi_mr disaster is primarily caused by circuit breaker interaction, not strategy degradation. When 47% of trading days are blocked, the remaining entries are:
1. Clustered in the windows between circuit breaker events
2. Often occurring right after CB release, when the market may still be adverse
3. A non-representative sample of the strategy's full signal set

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-4**: Strat-4 makes an important point. Let me add the statistical test.

Under null hypothesis "rsi_mr has true WR=36.4% (as observed in 9th)," the probability of observing WR=21% in 62 trades:

```
z = (0.21 - 0.364) / sqrt(0.364 * 0.636 / 62)
  = -0.154 / 0.061
  = -2.52

P(z < -2.52) = 0.006 (0.6%)
```

This is statistically significant at p < 0.01. So either:
- (A) rsi_mr's true WR genuinely degraded due to the parameter changes in 10C, OR
- (B) The 62-trade sample is severely biased by circuit breaker timing effects

I lean toward (B) because:
- The same rsi_mr strategy in 10B (no circuit breaker) had approximately 170 trades with WR closer to 33-34%
- The 10C circuit breaker was specifically active during recovery periods when rsi_mr (mean reversion) should perform best
- Mean reversion strategies are strongest after drawdowns -- exactly when the circuit breaker blocks entry

**[Strat-1 (Swing Trade Expert)]**: This is the key insight. Mean reversion strategies are designed to buy oversold conditions. When do oversold conditions occur? During drawdowns. When does the circuit breaker block trading? During drawdowns. The circuit breaker and rsi_mean_reversion are fundamentally incompatible. The CB systematically blocks rsi_mr's best entry opportunities.

My recommendation: **Do NOT disable or reduce rsi_mr.** The strategy's 9th backtest performance (PF 1.116) is genuine. The 10C collapse is an artifact of the circuit breaker destroying its signal timing.

With the GDR replacing the circuit breaker (graduated reduction, no halt), rsi_mr should recover to near-baseline performance. The GDR still allows entries during drawdowns (at reduced size in Tier 1), which preserves rsi_mr's ability to capture oversold bounces.

**[Strat-2 (Quant Researcher)]**: I agree with keeping rsi_mr active, but I want to add one parameter consideration. The current rsi_mr SL is 1.0 ATR for longs. In the 9th backtest, 58.4% of all trades hit SL, and rsi_mr contributes the majority of stop-outs.

The 1.0 ATR SL may be appropriate in normal conditions, but during the Tier 1 GDR phase (DD 15-25%), rsi_mr positions should use a wider SL because the setup is entering during elevated volatility. I propose:

- Normal conditions: SL = 1.0 ATR (current)
- GDR Tier 1 (DD 15-25%): SL = 1.2 ATR (wider to accommodate volatility)

This is a minor change but could reduce the "stopped out then bounced" pattern that kills rsi_mr performance during volatile periods.

**[Strat-3 (Risk Manager)]**: I have a simpler alternative. Rather than conditional SL logic, let us set a per-strategy position cap for rsi_mr at 2 (max 2 concurrent rsi_mr positions). This limits rsi_mr's portfolio damage if it enters a losing streak, without blocking it entirely. With MAX_TOTAL=5 and 3 strategies, a cap of 2 per strategy is natural.

**[Strat-5 (Quant Algorithm Expert)]**: Per-strategy caps of 2 make mathematical sense. With MAX_TOTAL=5 and 3 strategies capped at 2 each, the portfolio can hold 2+2+1 or 2+1+2 or 1+2+2 = always 5 max, with enforced diversification.

However, this creates a potential problem: if only rsi_mr generates signals on a given day (common during oversold markets), the per-strategy cap limits us to 2 entries even if there are 5 high-quality signals. I would make the per-strategy cap "soft" -- apply it only when multiple strategies have signals. If only one strategy has signals, allow up to MAX_TOTAL positions.

**Panel Consensus on Agenda 4**:
- **KEEP** rsi_mean_reversion active (no disable, no reduction)
- rsi_mr's 10C failure was primarily circuit breaker artifact, not strategy degradation
- **ADD** soft per-strategy position cap of 2 (enforced only when multiple strategies have signals)
- **DEFER** conditional SL widening (Strat-2's proposal) to 12th backtest
- Monitor rsi_mr WR in 11th -- must be > 30%; if < 28%, revisit strategy parameters

---

## Agenda 5: 11th Backtest Parameter Consensus

**[Strat-5 (Quant Algorithm Expert)]**: Let me frame the 11th backtest design philosophy before we finalize parameters.

The 10th backtest taught us two lessons:
1. **Aggressive risk controls destroy edge**: The circuit breaker + position reduction removed more profit opportunity than risk
2. **Signal quality improvements are directionally correct but insufficient alone**: 10B improved Sharpe marginally but did nothing for DD

The 11th approach should be: **10B signal quality + minimal viable risk management**.

"Minimal viable risk management" means:
- Position count and sizing that prevent catastrophic DD
- Graduated response that preserves trading during normal drawdowns
- No binary shutdowns or aggressive parameter reductions

**[Strat-1 (Swing Trade Expert)]**: I want to add a practical guard rail. We have now run 2 backtests (9th and 10th) with significant changes between each. Each time, the actual results deviate substantially from predictions. This tells us our predictive model is weak.

For 11th, I recommend **conservative predictions** and **a single test run** (not A/B/C variants). The variants in 10th gave us useful decomposition, but now we know the direction. Let us commit to one parameter set and evaluate cleanly.

**[Strat-3 (Risk Manager)]**: Agreed. One test, clean evaluation. Here is my proposed parameter set.

---

### 11th Backtest Changes -- Detailed Decision Table

#### Changes from 9th Baseline (ADOPT)

| # | Parameter | Location | 9th Value | 11th Value | Decision | Rationale |
|---|---|---|---|---|---|---|
| 1 | Circuit breaker | batch_simulator.py | DD>10%, 7d halt | **REMOVE** entirely | ROLLBACK from 10th | Death spiral, 47% day block |
| 2 | Graduated DD Response | batch_simulator.py (NEW) | N/A | Tier system (see below) | NEW | Replace CB with graduated approach |
| 3 | RISK_PER_TRADE_PCT | batch_simulator.py | 0.02 (2%) | 0.02 (2%) | KEEP 9th | 1.5% too aggressive, edge destroyed |
| 4 | MAX_TOTAL_POSITIONS | batch_simulator.py | 6 | 5 | MODIFY | Moderate reduction from 9th, not extreme |
| 5 | MAX_LONG_POSITIONS | batch_simulator.py | 5 | 4 | MODIFY | Proportional to MAX_TOTAL=5 |
| 6 | MAX_SHORT_POSITIONS | batch_simulator.py | 3 | 3 | KEEP 9th | No change needed |
| 7 | consec_down RSI_MAX | consecutive_down.py | 50 | 45 | ADOPT from 10B | Signal quality improvement confirmed |
| 8 | rsi_mr TP ATR cap | exit_rules.py, yaml | 1.5 | 2.0 | ADOPT from 10B | Let winners develop (neutral-positive) |
| 9 | vol_div regime_compat | ranking.py | 0.70 | 0.85 | ADOPT from 10B | Remove ranking disadvantage |
| 10 | Diversity bonus (0 pos) | ranking.py | +0.15 | +0.25 | STRENGTHEN from 10B | +0.15 insufficient, vol_div still suppressed |
| 11 | Diversity bonus (1 pos) | ranking.py | +0.05 | +0.10 | STRENGTHEN from 10B | Proportional increase |
| 12 | breakeven_activation_atr | exit_rules.py, yaml | 0.8 | 0.6 | ADOPT from 10th | Earlier winner protection, low risk |
| 13 | Per-strategy position cap | batch_simulator.py (NEW) | N/A | Soft cap 2 per strategy | NEW | Enforce diversification |

#### Changes from 10th (ROLLBACK)

| Parameter | 10th Value | 11th Value | Reason for Rollback |
|---|---|---|---|
| RISK_PER_TRADE_PCT | 0.015 (1.5%) | 0.02 (2.0%) | Trade count destruction, edge erased |
| MAX_TOTAL_POSITIONS | 4 | 5 | Too restrictive at 4 |
| MAX_LONG_POSITIONS | 3 | 4 | Proportional adjustment |
| Circuit breaker | DD>10%, 7d halt | REMOVED | Death spiral, 47% day block |

#### Explicitly Unchanged (KEEP)

| Parameter | Value | Location | Reason |
|---|---|---|---|
| SL ATR mult (all long) | 1.0 | exit_rules.py | 8th->9th validation, do not change |
| SL ATR mult (rsi_mr short) | 1.5 | exit_rules.py | No data to change |
| max_hold_days | 5 | exit_rules.py | Already optimized |
| max_daily_entries | 2 | batch_simulator.py | GDR controls this dynamically |
| gap_threshold | 0.05 | batch_simulator.py | Already optimized |
| ema_pullback | disabled | strategy_params.yaml | Correct, keep disabled |

---

### Graduated Drawdown Response (GDR) Specification

```
Rolling Peak: 60-day equity high (not all-time peak)

Tier 0 (DD < 15%):
  - RISK_PER_TRADE: 2.0%
  - max_daily_entries: 2
  - Status: Normal operation

Tier 1 (DD 15-25%):
  - RISK_PER_TRADE: 1.0%
  - max_daily_entries: 1
  - Status: Caution mode
  - Note: Still allows entries, preserves mean-reversion opportunity

Tier 2 (DD > 25%):
  - RISK_PER_TRADE: 0.5%
  - max_daily_entries: 1
  - Status: Minimal mode
  - Note: NO full halt. Keeps trading at minimal size.
```

Implementation notes:
- Rolling peak = max(equity) over last 60 trading days
- DD calculated as (rolling_peak - current_equity) / rolling_peak
- Tier transitions are immediate (no delay)
- When equity recovers above rolling peak, tier resets to 0

---

### Soft Per-Strategy Position Cap Specification

```
Default cap: 2 positions per strategy

Enforcement rule:
  IF multiple strategies have pending signals:
    Enforce cap of 2 per strategy
  ELSE IF only one strategy has signals:
    Allow up to MAX_TOTAL (5) positions for that strategy
```

This ensures diversification when possible but does not block entries when only one strategy generates signals.

---

### Expected Impact (Conservative Estimates)

**[Strat-5 (Quant Algorithm Expert)]**: Given the 9th panel's prediction failure (predicted DD 15-22%, actual 43.9%), I am using deliberately conservative estimates with wider ranges.

| Metric | 9th Baseline | 11th Estimate (Conservative) | 11th Estimate (Optimistic) |
|---|---|---|---|
| Trades | 308 | 250-280 | 280-310 |
| Win Rate | 36.4% | 34-37% | 37-40% |
| Profit Factor | 1.043 | 1.02-1.10 | 1.10-1.20 |
| Return | +4.9% | +2-6% | +6-10% |
| Sharpe | 1.172 | 1.0-1.2 | 1.2-1.5 |
| Max DD | 50.4% | 35-45% | 25-35% |
| vol_div Trades | 11 | 20-35 | 35-50 |

Key uncertainties:
- GDR has never been tested; its interaction with strategies is unknown
- Diversity bonus +0.25 may over-correct or under-correct for vol_div
- Rolling peak behavior differs from static peak in unpredictable ways

**[Strat-3 (Risk Manager)]**: These estimates are appropriately humble. The critical thresholds for 11th evaluation:

```
PASS criteria (proceed to 12th with refinements):
  - Return > 0% (positive)
  - PF > 1.0
  - Max DD < 45% (any improvement over 9th)
  - vol_div > 15 trades
  - No single strategy WR < 25%

FAIL criteria (fundamental redesign needed):
  - Return < -2%
  - PF < 0.9
  - Max DD > 50% (regression from 9th)
  - Total trades < 150
```

---

## Dissenting Opinions and Risk Flags

**[Strat-1 (Swing Trade Expert)]**: My ongoing concern from the 9th panel remains unaddressed: we are not filtering entries by broad market condition. All our strategies are long-biased mean reversion on S&P 500 stocks. During sustained market declines, mean reversion underperforms. A simple SPY > 50-EMA filter would immediately improve entry quality. I accept deferring this to 12th but flag it as the highest-priority structural improvement after 11th.

**[Strat-5 (Quant Algorithm Expert)]**: The GDR rolling peak of 60 days is a guess. If the system experiences a 40-day grinding decline followed by a slight recovery, the rolling peak will reset to the recovery level, effectively "hiding" the full drawdown extent. I recommend tracking both rolling and all-time DD for diagnostics, even if GDR only acts on rolling DD.

**[Strat-2 (Quant Researcher)]**: The diversity bonus increase from +0.15 to +0.25 is a significant jump. It could push low-quality vol_div signals (strength 0.35) above higher-quality rsi_mr signals (strength 0.60) in the ranking. We should track the **average composite score of selected signals** in 11th. If it drops below 0.40, the bonus is too aggressive and should be reduced to +0.20.

**[Strat-4 (Trade Analyst)]**: I want to flag that we have run 3 backtests (8th, 9th, 10th) on the same synthetic data with seed=42. Every iteration optimizes on the same price paths. We are at high risk of overfitting to this specific data sequence. For 12th or 13th backtest, we MUST change the seed or use multiple seeds to test out-of-sample robustness.

**[Strat-3 (Risk Manager)]**: The GDR implementation is a code change, not just a parameter change. It requires:
1. Replace `_CIRCUIT_BREAKER_DD_THRESHOLD` and `_CIRCUIT_BREAKER_PAUSE_DAYS` constants
2. Add `_rolling_peak_window: int = 60` constant
3. Add rolling peak equity tracking (deque of last 60 equity values)
4. Modify `_execute_pending_entries` to check GDR tier instead of circuit breaker
5. Modify position sizing to use tier-adjusted risk percentage
6. Add GDR tier to DailySnapshot for diagnostic logging

This is a meaningful code change and needs careful implementation.

---

## Implementation Priority

1. **Code changes required**:
   - GDR implementation in batch_simulator.py (replace circuit breaker)
   - Soft per-strategy position cap in batch_simulator.py
   - Diversity bonus increase in ranking.py

2. **Parameter changes only** (no code):
   - MAX_TOTAL_POSITIONS: 6 -> 5
   - MAX_LONG_POSITIONS: 5 -> 4
   - RISK_PER_TRADE_PCT: keep at 0.02 (rollback 10th's 0.015)
   - breakeven_activation_atr: 0.8 -> 0.6
   - consec_down RSI_MAX: 50 -> 45 (already in 10B, keep)
   - rsi_mr TP ATR cap: 1.5 -> 2.0 (already in 10B, keep)
   - vol_div regime_compat: 0.70 -> 0.85 (already in 10B, keep)

3. **Deferred to 12th backtest**:
   - Market regime entry filter (SPY > 50-EMA)
   - Conditional SL widening during GDR Tier 1
   - Multi-seed robustness testing
   - Portfolio weight optimization

---

## Summary of 9th -> 10th -> 11th Evolution

```
9th Baseline:
  RISK=2%, MAX_TOTAL=6, no circuit breaker
  Result: 308 trades, PF 1.043, Return +4.9%, DD 50.4%

10th (failed):
  RISK=1.5%, MAX_TOTAL=4, circuit breaker DD>10%/7d halt
  Result: 98-114 trades, PF 0.76-0.80, Return -3.9% to -5.5%, DD 43.9-45.7%
  Root cause: Circuit breaker death spiral + over-constrained position sizing

11th (proposed):
  RISK=2%, MAX_TOTAL=5, GDR (graduated DD response, no halt)
  + 10B signal quality improvements
  + Stronger diversity bonus
  + Soft per-strategy cap
  Expected: 250-310 trades, PF 1.02-1.20, Return +2-10%, DD 25-45%
```

**Panel sign-off**: All 5 experts agree on the 11th backtest parameter set. Single test run (no A/B/C variants). Evaluate against PASS/FAIL criteria defined above.
