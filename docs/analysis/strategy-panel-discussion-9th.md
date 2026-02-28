# Strategy Panel Discussion: 9th Backtest Analysis

**Date**: 2026-02-28
**Format**: 5-Expert Panel Discussion
**Data**: 9th Backtest (308 trades, $100K initial, 251 trading days, S&P 500 universe)

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

## Agenda 1: Max Drawdown 50% -- Root Cause and Solutions

**[Strat-5 (Quant Algorithm Expert)]**: Let me decompose the 50.4% drawdown mathematically. With current parameters -- 2% risk per trade, max 6 positions, all S&P 500 longs -- we need to understand why 12% theoretical max portfolio risk produces a 50% realized DD.

The answer is threefold:

First, **correlation**. S&P 500 stocks have average pairwise correlation of approximately 0.35-0.45. When 6 positions are simultaneously long, the portfolio behaves roughly like a 2.5-3x leveraged single position during stress events. The effective single-event portfolio risk is not 6 x 2% = 12%, but rather:

```
sigma_portfolio = sqrt(N * sigma^2 + N*(N-1) * rho * sigma^2)
                = sigma * sqrt(N + N*(N-1)*rho)
                = 0.02 * sqrt(6 + 6*5*0.4)
                = 0.02 * sqrt(18)
                = 0.02 * 4.24
                = 8.5% per concurrent loss event
```

Second, **sequential compounding**. The 2% risk is recalculated on current equity, but during a drawdown, new positions are opened while existing positions are already losing. If the market drops for 3 consecutive weeks, you could experience 3-4 full portfolio stop-out cycles: 8.5% x 4 events = 34% compounded to approximately 30%. Add the unrealized losses accumulating before stops trigger and you approach 50%.

Third, **asymmetric recovery**. After a 30% DD, you need a 43% gain to recover. The reduced equity means position sizes shrink, slowing recovery.

Now, Kelly criterion analysis. With overall WR = 36.4% and payoff ratio = $921/$478 = 1.93:

```
Kelly f* = (b*p - q) / b
         = (1.93 * 0.364 - 0.636) / 1.93
         = (0.703 - 0.636) / 1.93
         = 0.035 = 3.5%
```

But this 3.5% is the Kelly-optimal fraction of capital to risk **per independent bet**. Our bets are NOT independent -- they are correlated. The correlation-adjusted Kelly is:

```
f*_adjusted = f* / (1 + (N-1)*rho) = 0.035 / (1 + 5*0.4) = 0.035 / 3.0 = 1.17%
```

Current 2% risk per trade is **1.7x the correlation-adjusted Kelly optimal**. We are significantly over-betting relative to our edge.

**[Strat-3 (Risk Manager)] responding to Strat-5**: Your math is clean and it confirms my intuition. The 2% per trade sounds conservative in isolation, but with 6 correlated positions it is aggressive. I want to highlight three concrete failure modes I see in the data:

1. **No portfolio-level risk cap**: We cap individual trade risk at 2% but have no aggregate exposure limit. If all 6 positions are long and the market drops 3%, every position hits SL simultaneously. There is no circuit breaker.

2. **Sequential re-entry during drawdowns**: When positions get stopped out, the system immediately opens new positions the next evening. During a sustained market decline, this creates a "conveyor belt of losses" -- new positions enter and immediately get stopped out, draining capital at the rate of 2% per position per day.

3. **No drawdown pause mechanism**: The batch simulator has no equity curve circuit breaker. In any professional risk management system, new entries would be suspended when DD exceeds a threshold (typically 10-15% for a system like ours).

**[Strat-1 (Swing Trade Expert)] responding to Strat-3**: I agree with the math, but I want to add a practical dimension. As a swing trader, I would never enter 2 new positions per day during a market selloff. The problem is not just position sizing -- it is that **we are trading blind to market regime during entries**.

Look at the exit data: 180 stop losses out of 308 trades = 58.4%. That means nearly 6 out of every 10 trades hit their stop. In healthy market conditions, you expect 40-45% stop rate at most. The 58% rate tells me we are entering trades during adverse conditions far too often.

I would argue for a **VIX-based or breadth-based entry filter** before we even get to position sizing. If the broad market is in a decline (e.g., SPY below its 20-day EMA, or VIX > 25), we should reduce max_daily_entries to 1 or 0.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: VIX filter is a good qualitative idea, but it introduces a new parameter to optimize and risks overfitting. I prefer the mathematical approach: reduce the risk per trade to 1.2-1.5% (fractional Kelly) and cap max total positions at 4. This achieves the same effect without adding conditional logic that may not generalize out-of-sample.

Let me run the numbers. With RISK_PER_TRADE = 1.5% and MAX_TOTAL = 4:
```
sigma_portfolio = 0.015 * sqrt(4 + 4*3*0.4) = 0.015 * sqrt(8.8) = 0.015 * 2.97 = 4.5%
```

At 4.5% per concurrent event, even 5 sequential stop-out cycles would compound to approximately 20-22% DD. That is a much more acceptable range.

**[Strat-3 (Risk Manager)] responding to Strat-5**: I like the fractional Kelly approach, but I want to add one structural change that is orthogonal to position sizing: an **equity curve circuit breaker**. When equity drops more than 10% from its rolling peak, pause all new entries for 5 trading days. This breaks the "conveyor belt of losses" pattern directly.

This is not overfitting -- it is a generic risk management principle used by virtually every managed fund. It does not depend on any specific market indicator.

**[Strat-4 (Trade Analyst)]**: Let me ground this discussion in specific data. Looking at the DD timeline, the 50.4% DD did not happen in one event -- it accumulated over weeks. The pattern is:

1. Day N: 4-6 positions open, all long S&P stocks
2. Day N+1 to N+3: Market declines, positions accumulate unrealized losses
3. Day N+3 to N+5: SL triggers fire, realizing losses of 2% each = 8-12% total
4. Day N+4 to N+6: New positions opened from evening scan, immediately into declining market
5. Repeat cycle 3-4 times over 15-20 trading days

The forced_close exits (4 trades, +$3,139) actually performed well -- they represent regime-change closes that avoided further losses. This is evidence that **proactive closing works**.

**Panel Consensus on Agenda 1**:
- Reduce RISK_PER_TRADE_PCT from 2.0% to 1.5% (fractional Kelly)
- Reduce MAX_TOTAL_POSITIONS from 6 to 4
- Reduce MAX_LONG_POSITIONS from 5 to 3
- Add equity curve circuit breaker: pause entries when DD > 10% from peak (structural change, requires code implementation)
- Expected DD reduction: 50% -> 18-22%

---

## Agenda 2: volume_divergence Portfolio Mix Problem

**[Strat-4 (Trade Analyst)]**: This is one of the most striking anomalies in the data. volume_divergence solo performance: 112 trades, PF 1.382, Return +7.1%, Max DD 4.3%. This is the best risk-adjusted strategy by far (DD only 4.3%). Yet in the portfolio mix, it shrinks to 11 trades with PF 0.21 and -$5,339 PnL.

The 11 trades in the mix are a tiny, statistically insignificant sample drawn from a pool of 112 potential trades. The question is: why does the ranking system almost never select vol_div signals?

**[Strat-2 (Quant Researcher)]**: I traced this to the SignalRanker scoring formula. The composite score is:

```
composite = signal_strength * 0.6 + regime_compatibility * 0.3 + sector_diversity * 0.1
```

volume_divergence has regime_compatibility = 0.70, versus 0.80 for rsi_mean_reversion and consecutive_down. That is a 0.03 penalty in the composite score (0.30 * 0.10 difference). But the bigger issue is **signal_strength**.

Looking at vol_div's strength formula:
```python
strength = min(1.0, vol_ratio * 0.5 + (RSI_MAX - rsi) / RSI_MAX * 0.5)
```

With RSI_MAX = 45, even if RSI is 25, the RSI component is only (45-25)/45 * 0.5 = 0.22. The vol_ratio component rarely exceeds 0.3. So typical vol_div signal_strength is 0.35-0.55.

Meanwhile, consecutive_down strength includes `(down_days - 3 + 1) * 0.15 + (RSI_MAX - rsi) / RSI_MAX`, which with RSI_MAX = 50 and RSI = 35 gives (50-35)/50 = 0.30, plus 0.15 for base = 0.45, and with 4+ down days it easily hits 0.60+.

So vol_div is systematically ranked below the other strategies in composite score. With max_daily_entries = 2, the top-2 signals always come from rsi_mr or consec_down, and vol_div never gets executed.

**[Strat-1 (Swing Trade Expert)] responding to Strat-2**: This is a classic resource contention problem. In practice, you would not run three mean-reversion strategies competing for the same 2 entry slots. Each strategy captures a different type of setup -- vol_div specifically targets selling exhaustion, which is a different timing than RSI oversold or consecutive down. They should not be in direct competition.

My recommendation: **reserve at least 1 entry slot per strategy type**. If vol_div generates a signal, it gets one of the 2 daily entries guaranteed, regardless of composite score ranking.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: Reserved slots are a valid approach, but they reduce optimization flexibility. I prefer a different solution: **per-strategy position quota with minimum allocation**.

Currently `_MAX_STRATEGY_POSITIONS` in entry_manager.py is an empty dict -- there are no per-strategy caps. I propose:

```python
_MAX_STRATEGY_POSITIONS = {
    "rsi_mean_reversion": 2,
    "consecutive_down": 2,
    "volume_divergence": 2,
}
```

This ensures no single strategy dominates while allowing each strategy fair access. Combined with increasing vol_div's regime_compatibility from 0.70 to 0.85, the ranking score penalty disappears and vol_div gets a fair chance at selection.

**[Strat-2 (Quant Researcher)] responding to Strat-5**: I agree with the regime_compat fix, but the per-strategy position cap creates a different problem. With MAX_TOTAL = 4 (from our DD discussion) and 3 strategies each capped at 2, the math works out -- but what if only one strategy generates signals on a given day? We should not block entries because the strategy already has 2 positions while the portfolio has room.

Better approach: **weighted composite scoring boost** for underrepresented strategies. When a strategy has 0 positions, add a +0.15 bonus to its composite score. When it has 1 position, +0.05. When it has 2+, no bonus. This naturally creates diversity without hard caps.

**[Strat-3 (Risk Manager)]**: From a risk perspective, vol_div's solo DD of 4.3% is exactly the kind of strategy I want more exposure to. Its low correlation with the other strategies would actually *reduce* portfolio DD through diversification. The current ranking system is perversely selecting the more correlated signals.

I support Strat-2's approach -- a diversity bonus in the ranking formula. This is the least invasive code change and it naturally balances the portfolio.

**Panel Consensus on Agenda 2**:
- Raise vol_div regime_compatibility: 0.70 -> 0.85 in ranking.py
- Add portfolio diversity bonus in SignalRanker: +0.15 composite for strategies with 0 current positions, +0.05 for 1 position (requires code change to pass current position state to ranker)
- As a simpler alternative if code change is deferred: set per-strategy position cap of 2 in entry_manager.py
- Expected impact: vol_div trades increase from 11 to 40-60 in portfolio mix

---

## Agenda 3: MFE/MAE Ratio Collapse (1.04x)

**[Strat-4 (Trade Analyst)]**: This is the data point that concerns me most. Let me present the comparison:

| Strategy | 8th Backtest | 9th Backtest | Change |
|---|---|---|---|
| consecutive_down MFE/MAE | 7.99x (5 trades) | 1.04x (271 trades) | -87% |
| rsi_mean_reversion MFE/MAE | 1.14x (193 trades) | 1.04x (190 trades) | -9% |

For consecutive_down, the answer is clear: **RSI_MAX 40 -> 50 destroyed signal quality**. With RSI < 40, only deeply oversold stocks with strong EMA-50 support triggered -- these were high-conviction setups. With RSI < 50, the strategy now triggers on garden-variety pullbacks that have no particular edge.

The 5-trade sample in 8th backtest had selection bias (only the most extreme setups), but even accounting for that, a drop from 7.99x to 1.04x is catastrophic. The MFE/MAE optimal SL went from 0.22 ATR (extremely tight, indicating very directional moves) to 0.79 ATR (indicating random-walk-like behavior).

For rsi_mean_reversion, the 1.14x -> 1.04x drop is smaller but still concerning. This could be partially an SL artifact: tighter SL (1.0 vs 1.5 ATR) means MAE is mechanically capped at a lower level (trades hit SL before MAE can expand), while MFE is also reduced because some trades that would have recovered after a brief dip are now stopped out prematurely.

**[Strat-2 (Quant Researcher)] responding to Strat-4**: I want to dissect the SL artifact hypothesis for rsi_mr. With 1.0 ATR SL, any trade whose adverse excursion exceeds 1.0 ATR is stopped out -- this caps the MAE at approximately 1.0 ATR. But MFE is uncapped. So if the SL change were the only factor, MFE/MAE should have **increased**, not decreased.

The fact that MFE/MAE decreased from 1.14x to 1.04x despite the mechanical MAE cap means that the tighter SL is also killing winners. Trades that need a 1.0-1.5 ATR drawdown before reversing are now stopped out, and these trades had above-average MFE. We are cutting off the left tail of MAE but also removing trades with high MFE from the sample.

For consecutive_down, there is no SL artifact -- the SL is the same (1.0 ATR in both tests). The 7.99x -> 1.04x is purely signal quality degradation from RSI_MAX expansion.

**[Strat-5 (Quant Algorithm Expert)]**: Let me frame this differently. An MFE/MAE ratio of 1.04x for both strategies means the expected favorable excursion is only 4% larger than the expected adverse excursion. This is barely above random (1.0x). For a viable trading strategy, I want MFE/MAE > 1.3x at minimum, ideally > 1.5x.

The question is whether we can restore signal quality without sacrificing trade frequency entirely. My proposal for consecutive_down:

**Tiered entry based on RSI level**:
- RSI < 40: Full size position (original high-quality signal)
- RSI 40-45: Half size position (moderate-quality signal)
- RSI 45-50: No entry (remove these low-quality signals)

This gives us a compromise: we get more trades than RSI_MAX = 40 (from the 40-45 band), but we do not dilute the portfolio with the weakest signals from the 45-50 band.

**[Strat-1 (Swing Trade Expert)] responding to Strat-5**: The tiered sizing is elegant but adds complexity. From a practical standpoint, I would just set RSI_MAX = 45. The 40-45 band captures genuine pullbacks in uptrending stocks -- a trader would recognize these as legitimate setups. The 45-50 band is just noise -- RSI 48 in a stock above EMA(50) is not a pullback, it is normal trading.

For rsi_mr, the 1.04x MFE/MAE suggests we need to reconsider the TP logic. The current TP is RSI > 50 or pct_b > 0.50, capped at 1.5 ATR. With a 1.0 ATR SL and 1.04x MFE/MAE, the R:R is approximately 1:1. We should either:
1. Tighten the SL to 0.8 ATR to improve R:R (but risks more stop-outs), or
2. Allow wider MFE development by removing the 1.5 ATR TP cap and letting the indicator-based TP run

I favor option 2 -- let winners run longer. The 1.5 ATR cap is cutting profits short.

**[Strat-4 (Trade Analyst)] responding to Strat-1**: Looking at the TP data: 72 take_profit exits averaged +$921. 52 time_exit trades averaged +$394. The time exits are significantly less profitable, which tells me that some trades that should reach TP are timing out before they get there. If we remove the ATR TP cap for rsi_mr and rely purely on the indicator-based TP (RSI > 50 / pct_b > 0.50), those trades have more room to develop.

But there is a risk: without an ATR cap, outlier trades could sit unrealized for 4-5 days and then get time-exited at a lower level. The indicator-based TP depends on RSI and Bollinger Bands resetting, which may not happen in a trending market.

My recommendation: raise the ATR TP cap from 1.5 to 2.0 rather than removing it entirely. This gives winners more room while still providing a ceiling.

**Panel Consensus on Agenda 3**:
- consecutive_down RSI_MAX: 50 -> 45 (compromise between quality and frequency)
- rsi_mean_reversion ATR TP cap: 1.5 -> 2.0 (let winners run, but maintain ceiling)
- Monitor MFE/MAE in 10th backtest; if consec_down MFE/MAE < 1.5x at RSI_MAX 45, revert to 40
- Do NOT implement tiered sizing yet -- test RSI_MAX 45 first, reassess in 11th backtest

---

## Agenda 4: Return +4.9% Improvement

**[Strat-4 (Trade Analyst)]**: The return decomposition is straightforward:

| Exit Type | Count | Total PnL | Avg PnL | Weight |
|---|---|---|---|---|
| stop_loss | 180 (58.4%) | -$85,964 | -$478 | Primary loss driver |
| take_profit | 72 (23.4%) | +$66,298 | +$921 | Primary profit driver |
| time_exit | 52 (16.9%) | +$20,487 | +$394 | Secondary profit |
| forced_close | 4 (1.3%) | +$3,139 | +$785 | Negligible volume |

The SL:TP ratio is 180:72 = 2.5:1. For every TP, we have 2.5 SL exits. Combined with the payoff ratio ($921/$478 = 1.93x), the expectancy per trade is:

```
E = WR_tp * Avg_TP + WR_time * Avg_Time - WR_sl * Avg_SL
  = 0.234 * $921 + 0.169 * $394 - 0.584 * $478
  = $215 + $67 - $279
  = +$3 per trade
```

A $3/trade expectancy on $100K capital is essentially break-even. The system has a marginal edge at best. To improve returns, we need either:
- Fewer stop losses (better entry filters, or different SL level)
- Higher average TP gains (let winners run)
- Both

**[Strat-1 (Swing Trade Expert)]**: The 58.4% stop loss rate is the smoking gun. In a healthy mean-reversion system, you expect 35-40% stop-outs, not 58%. Two things drive this:

1. **Adverse entries**: We are entering during market conditions that do not favor mean reversion. A VIX or breadth filter would immediately reduce the SL rate by 10-15%.

2. **SL too tight for the setup**: 1.0 ATR SL on a mean-reversion strategy is aggressive. The trade thesis is "stock is oversold and will bounce" -- but oversold stocks often get more oversold before bouncing. A 1.2 ATR SL would give setups more room to develop while still being tighter than the previous 1.5 ATR.

I would not go back to 1.5 ATR -- the 8th backtest showed that was too wide. But 1.0 ATR might be too tight. Let me propose 1.2 ATR as a compromise for the rsi_mr strategy specifically.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: I disagree with loosening SL. The data shows the SL problem is not the distance -- it is the **frequency of adverse entries**. Look at it this way: if 58% of trades hit SL, and we widen SL from 1.0 to 1.2 ATR, some of those trades will now time-exit instead of SL-exit. But the average time_exit PnL is only +$394, while the SL loss goes from -$478 to approximately -$574 (1.2x the distance). We are trading a definite loss increase on remaining SL trades for an uncertain gain on converted trades.

Instead, I propose we attack the problem from the portfolio weight angle. Currently all strategies get equal weight in position sizing. But our data shows:

| Strategy | Solo PF | Solo Sharpe | Solo DD |
|---|---|---|---|
| rsi_mean_reversion | 1.116 | 1.170 | 50.6% |
| consecutive_down | 1.146 | 0.757 | 8.5% |
| volume_divergence | 1.382 | 0.816 | 4.3% |

volume_divergence has the best PF (1.382) and lowest DD (4.3%). It should get a disproportionate share of capital. I propose **inverse-DD weighting**:

```
weight_vol_div = (1/4.3) / (1/50.6 + 1/8.5 + 1/4.3)
               = 0.233 / (0.020 + 0.118 + 0.233)
               = 0.233 / 0.371
               = 62.8%
```

This is aggressive, but directionally correct. A more conservative approach: equal-risk allocation where each strategy contributes equally to portfolio volatility.

**[Strat-3 (Risk Manager)] responding to Strat-5**: I appreciate the mathematical elegance, but inverse-DD weighting based on a single backtest is dangerously overfit. The 4.3% DD for vol_div and 50.6% for rsi_mr are in-sample observations. Out-of-sample, these could easily swap.

My recommendation is simpler: keep equal weighting but **reduce overall exposure during high-loss periods**. The equity curve circuit breaker we discussed in Agenda 1 addresses the return problem too -- by avoiding the "conveyor belt" losses, we preserve more capital for profitable periods.

**[Strat-2 (Quant Researcher)]**: I want to add one specific parameter insight. The breakeven activation at 0.8 ATR is helping, but not fast enough. Looking at the exit data, many TP trades first dipped to near-SL levels before recovering. If we activate breakeven at 0.6 ATR (i.e., once a trade is 0.6 ATR in profit, move SL to entry), we protect more winners from reverting to losses.

The risk: with 0.6 ATR activation, some trades will be stopped at breakeven that would have gone on to TP. But the asymmetry favors protection -- a prevented $478 loss is more valuable than an incremental $400 gain on a trade that was already in profit.

**Panel Consensus on Agenda 4**:
- Keep SL at 1.0 ATR (do not loosen) -- the problem is entry frequency, not SL distance
- Raise rsi_mr ATR TP cap from 1.5 to 2.0 (let winners develop)
- Reduce breakeven_activation from 0.8 to 0.6 ATR (protect winners earlier)
- Equity curve circuit breaker addresses conveyor-belt losses (structural change)
- Defer portfolio weight optimization until we have 3+ backtests to validate (avoid overfitting)

---

## Agenda 5: 10th Backtest Parameter Consensus

**[Strat-5 (Quant Algorithm Expert)]**: Let me summarize what we have agreed on, with my assessment of expected impact and risk for each change.

**[Strat-1 (Swing Trade Expert)]**: Before we finalize, I want to flag that we are proposing 8+ simultaneous parameter changes. If the 10th backtest shows improvement, we will not know which changes contributed. I recommend we split into two test runs:

- **10A**: Risk management changes only (position sizing, position caps, circuit breaker)
- **10B**: Signal quality changes (RSI_MAX, vol_div ranking, TP cap, breakeven)

Then compare 10A vs 10B vs 10A+10B combined.

**[Strat-5 (Quant Algorithm Expert)] responding to Strat-1**: Agreed. But for practical purposes, let me present the full combined parameter set. The test runner can split it into sub-tests.

**[Strat-3 (Risk Manager)]**: I want to add one more item. The current max_daily_entries of 2 should be conditional. During normal conditions, 2 entries per day is fine. But after a stop-loss day (any position was stopped out today), max_daily_entries should drop to 1 the next day. This is a simple anti-cascading rule.

**[Strat-2 (Quant Researcher)] responding to Strat-3**: That adds conditional logic that is hard to test and risks path dependency. I prefer keeping max_daily_entries at 2 and letting the circuit breaker handle the cascade scenario. But I will not block it if the panel agrees.

**[Strat-4 (Trade Analyst)]**: I side with Strat-2 on this. The circuit breaker is cleaner. Let me summarize all changes.

---

## Consensus: 10th Backtest Parameter Changes

### Category A: Risk Management (Priority 1)

| # | Parameter | File | Current | Proposed | Rationale |
|---|---|---|---|---|---|
| A1 | RISK_PER_TRADE_PCT | batch_simulator.py | 0.02 (2%) | 0.015 (1.5%) | Fractional Kelly (correlation-adjusted) |
| A2 | MAX_TOTAL_POSITIONS | batch_simulator.py | 6 | 4 | Reduce correlated exposure |
| A3 | MAX_LONG_POSITIONS | batch_simulator.py | 5 | 3 | Proportional to total cap |
| A4 | breakeven_activation_atr | exit_rules.py, yaml | 0.8 | 0.6 | Earlier winner protection |
| A5 | Equity curve circuit breaker | batch_simulator.py (NEW) | N/A | Pause entries at 10% DD from peak, resume after 5 days | Break loss cascading |

### Category B: Signal Quality (Priority 2)

| # | Parameter | File | Current | Proposed | Rationale |
|---|---|---|---|---|---|
| B1 | consecutive_down RSI_MAX | consecutive_down.py | 50 | 45 | Restore signal quality (MFE/MAE 1.04x -> target 2.0x+) |
| B2 | rsi_mr ATR TP cap | exit_rules.py | 1.5 | 2.0 | Let winners develop further |
| B3 | vol_div regime_compatibility | ranking.py | 0.70 | 0.85 | Remove ranking disadvantage |
| B4 | Strategy diversity bonus | ranking.py (NEW) | N/A | +0.15 composite for 0 positions, +0.05 for 1 position | Portfolio balance |

### Category C: Unchanged (Explicitly Confirmed)

| Parameter | File | Value | Reason to Keep |
|---|---|---|---|
| SL ATR mult (all long) | exit_rules.py | 1.0 | 8th->9th data shows 1.0 is correct level |
| SL ATR mult (rsi_mr short) | exit_rules.py | 1.5 | No short-specific data to change |
| max_hold_days (all) | exit_rules.py | 5 | Already optimized in 8th->9th |
| max_daily_entries | batch_simulator.py | 2 | Circuit breaker handles cascading better |
| gap_threshold | batch_simulator.py | 0.05 | Already optimized in 8th->9th |
| ema_pullback | batch_simulator.py | disabled | Correct decision, keep disabled |

### Expected Combined Impact

| Metric | 9th (Current) | 10th (Projected) | Driver |
|---|---|---|---|
| Max DD | 50.4% | 15-22% | A1+A2+A3+A5 (position sizing + circuit breaker) |
| Return | +4.9% | +8-12% | B1+B2+B4 (better signals + more vol_div) |
| Sharpe | 1.172 | 1.3-1.6 | DD reduction dominates Sharpe improvement |
| Win Rate | 36.4% | 38-42% | B1 (fewer low-quality consec_down entries) |
| Profit Factor | 1.043 | 1.15-1.25 | B2+A4 (higher TP, earlier breakeven) |
| vol_div Trades | 11 | 40-60 | B3+B4 (ranking fix + diversity bonus) |

### Validation Plan

**[Strat-5 (Quant Algorithm Expert)]**: Run three sub-tests to isolate effects:

| Test | Changes Applied | Purpose |
|---|---|---|
| 10A | A1-A4 only (no circuit breaker) | Isolate position sizing impact on DD |
| 10B | B1-B3 only (no diversity bonus) | Isolate signal quality impact on returns |
| 10C | A1-A5 + B1-B4 (full set) | Combined effect measurement |

Compare all three to 9th baseline. If 10C improvement is within 20% of 10A + 10B sum, the changes are additive and safe. If 10C is much worse than individual improvements, there are negative interactions to investigate.

**[Strat-4 (Trade Analyst)]**: Additionally, track these diagnostic metrics in 10th backtest:

1. **consec_down MFE/MAE at RSI_MAX 45**: Must be > 1.5x; if < 1.3x, revert to 40
2. **vol_div trade count in portfolio**: Must be > 30; if < 20, ranking fix is insufficient
3. **Max consecutive loss days**: Must be < 8; if > 10, circuit breaker threshold needs tightening
4. **SL rate**: Must be < 50%; if > 55%, entry quality is still the core problem
5. **Time-exit average PnL**: Should increase from +$394; if it decreases, TP cap change is counterproductive

---

## Dissenting Opinions and Risks

**[Strat-1 (Swing Trade Expert)]**: I remain concerned that we are not addressing entry quality directly. All our changes are about risk management (reduce exposure) and exit optimization (TP, breakeven). The fundamental issue -- entering trades that have no edge -- is not solved by smaller position sizes. I advocate for a market regime filter on entries (SPY above 20-EMA) as a future addition if 10th results are still marginal.

**[Strat-5 (Quant Algorithm Expert)]**: The risk of reducing position sizes (A1-A3) is that we proportionally reduce returns in good periods. If the market trends up strongly and all 3 long positions profit, we capture less than the old 6-position portfolio would have. The Sharpe improvement comes from reducing DD more than reducing returns, but the absolute return ceiling is lower.

**[Strat-2 (Quant Researcher)]**: The diversity bonus (B4) introduces a new parameter in the ranking formula. If mis-calibrated, it could force inferior signals into the portfolio. I recommend we track the average composite score of selected signals -- if it drops below 0.40, the diversity bonus is too aggressive.

**[Strat-3 (Risk Manager)]**: The circuit breaker (A5) requires new code in batch_simulator.py. It should be implemented as a simple state variable: `_peak_equity`, `_dd_from_peak`, and `_pause_entries_until`. When `_dd_from_peak > 0.10`, set `_pause_entries_until = current_date + 5 trading days`. In `_execute_pending_entries`, check `if current_date < _pause_entries_until: return 0`.

---

## Implementation Priority

1. **Immediate (parameter changes only, no code changes)**: A1, A2, A3, A4, B1, B2, B3
2. **Short-term (code changes required)**: A5 (circuit breaker), B4 (diversity bonus)
3. **Deferred to 11th backtest**: Market regime entry filter, portfolio weight optimization, tiered position sizing

**Panel sign-off**: All 5 experts agree on the parameter change set above. Run 10A/10B/10C validation tests before combining all changes.
