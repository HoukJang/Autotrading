# Iteration 0 Baseline Analysis & Iteration 1 Change Proposal

**Date**: 2026-02-28
**Analysts**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Data)

---

## Baseline Results Summary

| Metric | Period 1 (2024-03~2025-02) Bull | Period 2 (2025-03~2026-02) Mixed |
|--------|--------------------------------|----------------------------------|
| S&P Benchmark | +15.9% | +15.5% |
| Strategy Return | **-6.5%** | +10.9% |
| MaxDD | 25.1% | 29.2% |
| Sharpe | -0.109 | 0.519 |
| Calmar | -0.261 | 0.373 |
| Total Trades | 81 | 110 |
| Win Rate | 30.9% | 51.8% |
| Profit Factor | 0.600 | 1.692 |

**Target**: Sharpe >= 1.0 OR Calmar >= 1.0 on BOTH periods

---

## Strategy Team Diagnosis

### Strat-4 (Data Analyst) -- Exit Reason Breakdown

**Stop Loss Dominance is the Core Problem.**

| Strategy | Period | SL Exits | TP Exits | SL Rate | Other |
|----------|--------|----------|----------|---------|-------|
| cons_down | P1 | 44 | 17 | 72% | 0 |
| cons_down | P2 | 37 | 33 | 53% | 6 (forced/time) |
| rsi_mr | P1 | 15 | 2 | 88% | 3 (regime_guard) |
| rsi_mr | P2 | 23 | 4 | 85% | 7 (regime/time) |

Key finding: SL exits dominate across BOTH periods and BOTH strategies. Even in the profitable Period 2, rsi_mr has 85% SL rate -- it survives only because the few TP wins are large enough. This is extremely fragile.

### Strat-1 (Swing Trader) -- Trade Behavior Analysis

The 2-stage SL upgrade system is working against the trade thesis:

1. **Initial SL too tight**: cons_down at 1.2 ATR and rsi_mr at 1.0 ATR. Average daily range for S&P 500 stocks is approximately 1.0-1.5 ATR. A stop at 1.0-1.2 ATR is essentially one day of normal movement -- any normal pullback triggers the stop before the bounce thesis can play out.

2. **Stage 1 BE at 0.7 ATR causes "breakeven whipsaw"**: Price moves +0.7 ATR (well within normal intraday range), SL upgrades to breakeven, price pulls back to entry level = stopped at $0 on what could have been a winning trade. In trending markets, stocks often gap up slightly then pull back before continuing higher.

3. **Bull market paradox for cons_down**: This is a "buy the dip" strategy. In a bull market, dips should recover -- it should be the BEST environment. But WR of only 36% in P1 means the stops are killing the trades before the thesis can play out. The entries are likely correct; the exits are the problem.

### Strat-2 (Quant Analyst) -- Mathematical Impact Analysis

**Risk-reward mathematics under current parameters:**
- cons_down: SL = 1.2 ATR, TP = indicator-based (close > EMA5)
- If average TP = ~0.8 ATR (small bounce above EMA5), then R:R = 0.8/1.2 = 0.67
- At 0.67 R:R, breakeven WR required = 60%. Current P1 WR = 36%. Gap = 24 percentage points.

**Impact of widening SL to 2.0 ATR:**
- Position size reduces proportionally: qty = risk$ / (2.0 * ATR) vs qty = risk$ / (1.2 * ATR)
- Each position is ~60% the size, but trades have ~67% more room to breathe
- If WR improves from 36% to 50%+ (which P2 data suggests is realistic), the net PnL improvement is substantial despite smaller position sizes
- Breakeven WR at R:R 0.8/2.0 = 0.4 requires WR = 71%, BUT many trades currently hitting SL would become TP exits, changing the numerator significantly

**Impact of raising BE trigger from 0.7 to 1.5 ATR:**
- Eliminates "breakeven whipsaw" on trades that move 0.7-1.5 ATR before pulling back
- Expected conversion: ~15-20% of current BE stops become either TP exits or wider-range trade outcomes
- No position sizing impact (only affects SL upgrade, not initial SL)

### Strat-3 (Risk Manager) -- Risk Assessment

**Widening SL concerns:**
- Wider SL = larger per-trade loss when wrong. However, risk-based sizing (qty = risk / SL_distance) means dollar risk per trade is CONSTANT. A wider stop just means smaller position, larger stop distance.
- MaxDD impact: SL cascades cause drawdown. If WR improves, fewer cascading losses, which should REDUCE MaxDD despite wider stops.
- Tail risk: if a trade thesis is fundamentally wrong (not just noise), wider SL delays the exit. Mitigation: the max_hold_days=5 cap limits maximum duration exposure.

**Key risk**: if cons_down entries are bad (not just unlucky noise), wider SLs mean holding bad trades longer. P2 data (55% WR with current tight stops) suggests entries are generally sound.

---

## ITERATION #1 Change Proposal

```
ITERATION #1 Change Proposal
--------------------------------------------
TYPE: PARAM_TUNE

Diagnosis:
  Stop losses are too tight (1.0-1.2 ATR) relative to normal price
  volatility, causing 72-88% of trades to exit via SL before the trade
  thesis can play out. The 2-stage BE trigger at 0.7 ATR compounds
  this by stopping out trades that moved slightly in our favor.

Change 1: [exit_rules.py: _SL_ATR_MULT consecutive_down long]
  Current: 1.2 -> Proposed: 2.0
  Rationale: cons_down has 76+61=137 trades across both periods with
  72% SL rate in P1. This is the highest-volume strategy and highest-
  impact change. 2.0 ATR gives the "buy the dip" thesis adequate room
  for a 2-3 day bounce to develop without noise triggering the stop.
  Risk-based sizing automatically adjusts position size downward.

Change 2: [exit_rules.py: _STAGE1_BE_ACTIVATION_ATR]
  Current: 0.7 -> Proposed: 1.5
  Rationale: Universal change affecting all strategies. 0.7 ATR is
  within normal intraday range, causing frequent "breakeven whipsaw"
  where trades are stopped at $0 on what would have been winners. At
  1.5 ATR, the BE upgrade only activates after a meaningful favorable
  move, preserving the initial trade thesis. This change alone should
  convert 10-15% of current SL/BE exits into TP exits.

Change 3: [exit_rules.py: _SL_ATR_MULT rsi_mean_reversion long]
  Current: 1.0 -> Proposed: 1.5
  Rationale: rsi_mr has 88% SL rate in P1 (15 of 20 trades). 1.0 ATR
  is essentially one day of normal movement -- any noise kills the
  trade. 1.5 ATR is a conservative widening that gives oversold bounce
  trades one additional day of room while keeping the stop meaningful.
  Combined with the BE trigger change, this should substantially
  improve rsi_mr's catastrophic P1 performance.

Expected Effect:
  - P1 Return: -6.5% -> +2% to +5% (bull market dip-buying should work)
  - P2 Return: +10.9% -> +12% to +15% (marginal improvement)
  - P1 WR: 30.9% -> 42-48% (fewer noise SL exits)
  - P2 WR: 51.8% -> 55-58%
  - MaxDD: 25-29% -> 18-22% (fewer cascading SL sequences)
  - P1 Sharpe: -0.109 -> 0.3-0.6
  - P2 Sharpe: 0.519 -> 0.6-0.9
  - Likely still short of Sharpe 1.0 target, but major directional improvement

Risk:
  - Wider SLs mean each losing trade takes 1-2 additional days to exit,
    slightly increasing correlation risk during market-wide selloffs
  - Position sizes shrink ~40% for cons_down (2.0/1.2 ratio), reducing
    per-trade profit magnitude on winners
  - If trade entries are fundamentally wrong (not just noise-stopped),
    wider SLs delay recognition of bad trades. Mitigated by max_hold=5d.
  - Potential side effect: fewer total trades if some currently-stopped
    trades now hold to time_exit instead of generating SL+re-entry pairs
```

---

## Files to Modify

Single file: `autotrader/execution/exit_rules.py`

| Line | Parameter | Current | Proposed |
|------|-----------|---------|----------|
| 32 | `_STAGE1_BE_ACTIVATION_ATR` | 0.7 | 1.5 |
| 44-48 | `_SL_ATR_MULT["consecutive_down"]["long"]` | 1.2 | 2.0 |
| 44-48 | `_SL_ATR_MULT["rsi_mean_reversion"]["long"]` | 1.0 | 1.5 |

Note: batch_simulator.py imports these constants from exit_rules.py, so both backtest and live trading will be updated automatically.

---

## Next Steps (if Iteration 1 results are still below target)

Priority considerations for Iteration 2+:
1. rsi_mr short side: if still underperforming, consider raising SL from 0.75 to 1.2 ATR or disabling shorts in TREND regime
2. cons_down TP: if WR is now acceptable but PF is low, the EMA5 TP might be taking profits too small -- consider EMA10 or ATR-based TP
3. Activate dormant strategies: ema_pullback and volume_divergence generate 0 trades -- investigate and fix entry filters
4. If parameter tuning plateau is reached, consider TYPE: NEW_STRATEGY with a momentum/trend-following strategy to complement the mean-reversion portfolio
