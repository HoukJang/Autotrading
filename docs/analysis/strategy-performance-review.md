# Strategy Performance Review: 8th Backtest Analysis & Parameter Recommendations

**Date**: 2026-02-28
**Analyst**: Strat-4 (Trade Analyst)
**Data**: Alpaca historical, 453 S&P 500 stocks, 251 trading days, $100K initial equity
**Baseline**: Entry Day Skip ON, gap_threshold 3%, default hold days

---

## Executive Summary

| Metric | Current | Target (Post-Adjustment) | Change Driver |
|--------|---------|--------------------------|---------------|
| Return | +5.0% | +12~15% (est.) | SL tightening + hold 5d + gap 5% |
| Sharpe | 1.143 | 1.3~1.5 (est.) | Hold 5d + disable ema_pullback |
| Max DD | 51.1% | 20~25% (est.) | SL tightening + position limits |
| Win Rate | 37.1% | 42~46% (est.) | Hold 5d + tighter SL |
| Profit Factor | 1.041 | 1.15~1.30 (est.) | Combined adjustments |

**Critical Findings**:
1. Stop losses are 50-90% wider than MFE/MAE optimal values across all strategies
2. `hold_5d` comparison shows +15.1% return vs +5.0% -- the single highest-impact change
3. `ema_pullback` is a structural loser (MFE/MAE 1.09x, PF 0.865) -- disable recommended
4. `consecutive_down` has excellent quality (MFE/MAE 7.99x) but only 5 trades -- frequency increase needed
5. 52% of exits are stop losses totaling -$91,821 -- primary loss driver

---

## 1. ema_pullback: Disable (Recommended)

### Diagnosis

| Metric | Value | Assessment |
|--------|-------|------------|
| Trades | 196 | High frequency |
| Win Rate | 31.1% | Below viable threshold |
| Profit Factor | 0.865 | Net loser (< 1.0) |
| Return | -6.0% | Negative contribution |
| MFE/MAE | 1.09x | Near-random directional signal |
| Opt SL | 0.96 ATR | Current 1.5 ATR is 56% too wide |
| Opt TP | 1.05 ATR | Current 2.0 ATR is 90% too ambitious |

**Root Cause**: MFE/MAE of 1.09x means the average favorable price excursion is only 9% larger than the average adverse excursion. This indicates the entry signal (EMA-21 pullback recovery) has nearly zero predictive power for continuation. No amount of exit parameter tuning can salvage a strategy whose entry signal is fundamentally weak.

**Comparison**: volume_divergence has MFE/MAE 1.34x, rsi_mean_reversion 1.14x -- both demonstrate meaningfully better directional conviction.

### Recommendation: DISABLE

**Primary**: Remove `ema_pullback` from active strategy roster.

| Parameter | Location | Before | After |
|-----------|----------|--------|-------|
| Strategy roster | `batch_simulator.py` `_STRATEGY_CLASSES` | Includes `EmaPullback` | Remove `EmaPullback` |
| Group B | `batch_simulator.py` `_GROUP_B` | `{"ema_pullback"}` | `frozenset()` (empty) |
| entry_groups.confirmation | `strategy_params.yaml` | `ema_pullback` | Remove section or add `enabled: false` |

**Impact**: Eliminates -6.0% drag on portfolio, frees 196 trade slots and position capacity for higher-quality strategies.

### Alternative (If Retained)

If ema_pullback must be kept active, these minimum changes are required:

| Parameter | File | Before | After | Rationale |
|-----------|------|--------|-------|-----------|
| `sl_atr_mult_long` | exit_rules.py / yaml | 1.5 | 1.0 | Align closer to optimal 0.96 |
| `tp_atr_mult` | exit_rules.py / yaml | 2.0 | 1.2 | Align closer to optimal 1.05 |
| `max_hold_days` | exit_rules.py / yaml | 7 | 5 | Consistent with hold_5d improvement |
| `RSI_MIN` | ema_pullback.py | 35.0 | 38.0 | Tighter entry filter |
| `RSI_MAX` | ema_pullback.py | 55.0 | 50.0 | Tighter entry filter |
| `trailing_activation_atr` | exit_rules.py | 1.0 | 0.8 | Earlier trailing activation |

**Warning**: Even with these changes, ema_pullback's structural weakness (MFE/MAE 1.09x) means it will likely remain marginal. These changes may reduce losses but are unlikely to make it consistently profitable.

---

## 2. consecutive_down: Frequency Expansion

### Diagnosis

| Metric | Value | Assessment |
|--------|-------|------------|
| Trades | 5 | Critically low -- 0.002 trades/stock/year |
| Win Rate | 100% | Perfect but low sample |
| MFE/MAE | 7.99x | Exceptional directional quality |
| Sharpe | 2.140 | Best risk-adjusted returns |
| Return | +1.9% | Limited by frequency |
| Avg Hold | 2.4d | Fast resolution |

**Bottleneck Analysis**: The triple filter (3+ down days + close > EMA(50) + RSI < 40) is excessively restrictive for S&P 500 large-caps in uptrends. The RSI < 40 requirement is the primary constraint -- stocks above EMA(50) rarely reach RSI 40 while maintaining 3+ consecutive down days.

### Recommendation

| Parameter | File | Before | After | Rationale |
|-----------|------|--------|-------|-----------|
| `RSI_MAX` | consecutive_down.py | 40.0 | 50.0 | Primary bottleneck; stocks above EMA(50) in mild pullback typically have RSI 40-50 |
| `MIN_DOWN_DAYS` | consecutive_down.py | 3 | 3 | KEEP -- core strategy identity; 2 would fundamentally change the signal |
| `sl_atr_mult_long` | exit_rules.py / yaml | 1.5 | 1.0 | Tighter SL, still conservative vs optimal 0.22 |
| `max_hold_days` | exit_rules.py / yaml | 5 | 5 | KEEP -- already at optimal |

**Expected Frequency**: RSI < 50 (vs < 40) should increase trade count from 5 to approximately 15-30 trades per year, representing a 3-6x increase.

**Quality Impact Assessment**:
- MFE/MAE 7.99x provides a large quality buffer
- Even if loosening RSI_MAX to 50 reduces MFE/MAE to 3.0-4.0x, it remains the highest-quality strategy
- The core signal (3+ consecutive down days above EMA-50) retains its structural validity
- RSI 40-50 still represents a pullback zone, not overbought territory

**Risk Mitigation**: Keep MIN_DOWN_DAYS at 3. Reducing to 2 would double+ the signal frequency but fundamentally changes the strategy from "extended decline bounce" to "minor dip buy" -- a different thesis entirely.

---

## 3. max_hold_days Unification to 5 Days

### Evidence

| Metric | Default (mixed 5/7) | hold_5d (all 5) | Delta |
|--------|---------------------|------------------|-------|
| Return | +5.0% | +15.1% | +10.1pp |
| Win Rate | 37.1% | 44.1% | +7.0pp |
| Sharpe | 1.143 | 1.336 | +0.193 |
| Profit Factor | 1.041 | (improved) | -- |

This is the **single highest-impact parameter change** available. All metrics improve substantially.

### Recommendation

| Strategy | File | Before | After | Impact |
|----------|------|--------|-------|--------|
| `rsi_mean_reversion` | exit_rules.py | 7 | 5 | Primary driver (193 trades affected) |
| `ema_pullback` | exit_rules.py | 7 | 5 | If retained; moot if disabled |
| `consecutive_down` | exit_rules.py | 5 | 5 | No change needed |
| `volume_divergence` | exit_rules.py | 5 | 5 | No change needed |

**Mechanism**: Mean-reversion strategies capture their edge in the first 2-4 days. Days 5-7 add noise and revert the gains. The data clearly shows holding beyond day 5 erodes both win rate and returns.

**Corresponding yaml change**:

| Parameter | File | Before | After |
|-----------|------|--------|-------|
| `rsi_mean_reversion.max_hold_days` | strategy_params.yaml | 7 | 5 |
| `ema_pullback.max_hold_days` | strategy_params.yaml | 7 | 5 |

---

## 4. SL/TP ATR Multiplier Optimization

### Gap Analysis: Current vs Optimal

| Strategy | Direction | Current SL | Optimal SL | Recommended SL | Gap Closed |
|----------|-----------|-----------|-----------|----------------|------------|
| rsi_mean_reversion | long | 1.5 ATR | 0.77 ATR | **1.0 ATR** | 68% |
| rsi_mean_reversion | short | 2.0 ATR | -- | **1.5 ATR** | -- |
| consecutive_down | long | 1.5 ATR | 0.22 ATR | **1.0 ATR** | 39% |
| ema_pullback | long | 1.5 ATR | 0.96 ATR | **1.0 ATR** | 93% |
| volume_divergence | long | 1.5 ATR | 0.89 ATR | **1.0 ATR** | 82% |

| Strategy | Current TP | Optimal TP | Recommended TP |
|----------|-----------|-----------|----------------|
| rsi_mean_reversion | Indicator + 2.0 ATR cap | 0.87 ATR | Indicator + **1.5 ATR** cap |
| ema_pullback | 2.0 ATR | 1.05 ATR | **1.2 ATR** |
| volume_divergence | Indicator | 1.19 ATR | Indicator + **1.5 ATR** cap |
| consecutive_down | EMA(5) crossover | 1.79 ATR | EMA(5) crossover (KEEP) |

### Why 1.0 ATR instead of exact optimal?

1. **Overfitting risk**: MFE/MAE optimal values are in-sample estimates; exact calibration overfits to historical noise
2. **Daily bar granularity**: Intraday price excursions can exceed daily bar ranges; 1.0 ATR provides breathing room
3. **Gap risk**: Overnight gaps of 0.5-1.0 ATR are common in S&P 500; SL below 1.0 ATR risks frequent gap-throughs
4. **Round number simplicity**: 1.0 ATR is easier to reason about and audit
5. **Conservative middle ground**: 1.0 ATR is approximately the midpoint between current (1.5) and optimal (0.77-0.96)

### Specific Code Changes

```python
# exit_rules.py -- _SL_ATR_MULT
# BEFORE:
_SL_ATR_MULT = {
    "rsi_mean_reversion": {"long": 1.5, "short": 2.0},
    "consecutive_down": {"long": 1.5},
    "ema_pullback": {"long": 1.5},
    "volume_divergence": {"long": 1.5},
}

# AFTER:
_SL_ATR_MULT = {
    "rsi_mean_reversion": {"long": 1.0, "short": 1.5},
    "consecutive_down": {"long": 1.0},
    "volume_divergence": {"long": 1.0},
    # ema_pullback removed (disabled)
}
```

```python
# exit_rules.py -- _TP_ATR_MULT
# BEFORE:
_TP_ATR_MULT = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
    "ema_pullback": 2.0,
    "volume_divergence": None,
}

# AFTER:
_TP_ATR_MULT = {
    "rsi_mean_reversion": None,  # keep indicator-based primary
    "consecutive_down": None,     # keep EMA(5) crossover
    "volume_divergence": None,    # keep indicator-based
    # ema_pullback removed (disabled)
}
```

```python
# exit_rules.py -- rsi_mean_reversion auxiliary ATR TP cap (inside _evaluate_tp)
# BEFORE:
atr_tp_mult = 2.0

# AFTER:
atr_tp_mult = 1.5
```

### Expected Impact

- **Average SL loss reduction**: Current avg SL exit = -$91,821 / 131 trades = -$701/trade
- With 1.0 ATR SL (33% tighter): estimated avg SL loss = ~-$467/trade
- **Total loss reduction estimate**: 131 * ($701 - $467) = ~$30,654 saved
- Some current SL trades become time exits (net positive $17K/67 = +$256/trade avg)
- **Net return improvement**: estimated +3~4%

---

## 5. Max Drawdown 51% Mitigation

### Root Cause Decomposition

| Factor | Contribution | Mechanism |
|--------|-------------|-----------|
| rsi_mean_reversion DD | 49.6% | Strategy's own DD nearly equals portfolio DD |
| Wide SL (1.5 ATR) | ~40% | Positions accumulate large unrealized losses |
| Max 8 positions | ~25% | Concentrated correlated losses during market stress |
| 7-day hold for RSI | ~20% | Extends exposure window during drawdowns |
| Breakeven too slow | ~15% | Winners revert to losers before BE activates |

*Note: Contributions overlap; not additive.*

### Multi-Layer Fix

| Parameter | File | Before | After | DD Impact |
|-----------|------|--------|-------|-----------|
| SL ATR mult (all) | exit_rules.py | 1.5 | 1.0 | -15~20% DD |
| max_hold_days (RSI) | exit_rules.py | 7 | 5 | -5~8% DD |
| `_MAX_TOTAL_POSITIONS` | batch_simulator.py | 8 | 6 | -5~10% DD |
| `_MAX_LONG_POSITIONS` | batch_simulator.py | 6 | 5 | -3~5% DD |
| `_MAX_DAILY_ENTRIES` | batch_simulator.py | 3 | 2 | -2~3% DD |
| `_BREAKEVEN_ACTIVATION_ATR` | exit_rules.py | 1.0 | 0.8 | -2~3% DD |
| Disable ema_pullback | batch_simulator.py | active | disabled | -3~5% DD |

**Combined estimated DD reduction**: 51% -> 20~25%

### Corresponding yaml changes

| Parameter | File | Before | After |
|-----------|------|--------|-------|
| `entry_limits.max_daily_entries` | strategy_params.yaml | 3 | 2 |
| `entry_limits.max_long_positions` | strategy_params.yaml | 6 | 5 |
| `breakeven_activation_atr` (all strategies) | strategy_params.yaml | 1.0 | 0.8 |

### Position Sizing Validation

With 1.0 ATR SL and 2% risk per trade:
- Max theoretical daily risk: 2 new entries * 2% = 4%
- Max portfolio risk: 6 positions * 2% = 12% (down from 8 * 2% = 16%)
- Assuming 50% correlation in market stress: effective risk ~ 8-10%
- This maps to a max DD of approximately 20-25% in a severe drawdown scenario

---

## 6. Gap Threshold: 3% vs 5%

### Comparison Data

| Metric | gap_3pct (current) | gap_5pct | Delta |
|--------|-------------------|----------|-------|
| Return | +5.0% | +11.7% | +6.7pp |
| Profit Factor | 1.041 | 1.101 | +0.060 |
| Sharpe | 1.143 | 1.193 | +0.050 |

### Recommendation: 5% (0.05)

| Parameter | File | Before | After |
|-----------|------|--------|-------|
| `_DEFAULT_GAP_THRESHOLD` | batch_simulator.py | 0.03 | 0.05 |
| `gap_filter.max_gap_pct` | strategy_params.yaml | 0.03 | 0.05 |

**Rationale**:
1. All three metrics improve with 5% threshold
2. The 3% filter was too aggressive -- rejecting profitable trades that gap within normal S&P 500 overnight range
3. With tighter SLs (1.0 ATR), gap risk is better controlled at the position level
4. Mean-reversion strategies expect some adverse gap behavior; the edge comes from post-gap recovery
5. S&P 500 large-caps rarely gap >5% on non-event days; 5% catches true outlier events

**Risk consideration**: A 5% gap means a stock could open 5% away from the signal price. With 1.0 ATR SL, some gap entries may be immediately near the SL. However, the data shows this population of trades is net profitable, indicating post-gap mean reversion works.

---

## Complete Parameter Change Summary

### Priority-Ordered Implementation

#### Tier 1: Highest Impact (implement first, re-backtest)

| # | Change | File(s) | Before | After | Expected Impact |
|---|--------|---------|--------|-------|-----------------|
| 1 | max_hold_days RSI | exit_rules.py, yaml | 7 | 5 | +10% return, +7pp WR |
| 2 | SL ATR mult (all long) | exit_rules.py, yaml | 1.5 | 1.0 | -15-20% DD, +3-4% return |
| 3 | SL ATR mult (RSI short) | exit_rules.py, yaml | 2.0 | 1.5 | Reduced short-side losses |
| 4 | Gap threshold | batch_simulator.py, yaml | 0.03 | 0.05 | +6.7% return |

#### Tier 2: Structural Changes

| # | Change | File(s) | Before | After | Expected Impact |
|---|--------|---------|--------|-------|-----------------|
| 5 | Disable ema_pullback | batch_simulator.py, yaml | active | disabled | +6% return (remove drag) |
| 6 | consecutive_down RSI_MAX | consecutive_down.py | 40.0 | 50.0 | 3-6x more trades |
| 7 | Max total positions | batch_simulator.py, yaml | 8 | 6 | -5-10% DD |
| 8 | Max long positions | batch_simulator.py, yaml | 6 | 5 | -3-5% DD |
| 9 | Max daily entries | batch_simulator.py, yaml | 3 | 2 | Slower position buildup |

#### Tier 3: Fine-Tuning

| # | Change | File(s) | Before | After | Expected Impact |
|---|--------|---------|--------|-------|-----------------|
| 10 | Breakeven activation | exit_rules.py, yaml | 1.0 ATR | 0.8 ATR | Earlier loss protection |
| 11 | RSI aux TP cap | exit_rules.py | 2.0 ATR | 1.5 ATR | Earlier profit taking |
| 12 | ema_pullback hold (if kept) | exit_rules.py, yaml | 7 | 5 | Reduced exposure |

---

## File-Specific Change Reference

### `autotrader/execution/exit_rules.py`

```python
# Line 35-40: _MAX_HOLD_DAYS
# BEFORE:
_MAX_HOLD_DAYS = {
    "rsi_mean_reversion": 7,
    "consecutive_down": 5,
    "ema_pullback": 7,
    "volume_divergence": 5,
}
# AFTER:
_MAX_HOLD_DAYS = {
    "rsi_mean_reversion": 5,
    "consecutive_down": 5,
    "volume_divergence": 5,
}

# Line 43-48: _SL_ATR_MULT
# BEFORE:
_SL_ATR_MULT = {
    "rsi_mean_reversion": {"long": 1.5, "short": 2.0},
    "consecutive_down": {"long": 1.5},
    "ema_pullback": {"long": 1.5},
    "volume_divergence": {"long": 1.5},
}
# AFTER:
_SL_ATR_MULT = {
    "rsi_mean_reversion": {"long": 1.0, "short": 1.5},
    "consecutive_down": {"long": 1.0},
    "volume_divergence": {"long": 1.0},
}

# Line 51-56: _TP_ATR_MULT
# BEFORE:
_TP_ATR_MULT = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
    "ema_pullback": 2.0,
    "volume_divergence": None,
}
# AFTER:
_TP_ATR_MULT = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
    "volume_divergence": None,
}

# Line 32: _BREAKEVEN_ACTIVATION_ATR
# BEFORE: 1.0
# AFTER:  0.8

# Line 414-416: rsi_mean_reversion auxiliary TP cap (inside _evaluate_tp)
# BEFORE: atr_tp_mult = 2.0
# AFTER:  atr_tp_mult = 1.5

# Line 58-60: _TRAILING_STRATEGIES and _TRAILING_ATR_MULT
# Remove ema_pullback references if disabled
```

### `autotrader/strategy/consecutive_down.py`

```python
# Line 53: RSI_MAX
# BEFORE: RSI_MAX = 40.0
# AFTER:  RSI_MAX = 50.0
```

### `autotrader/backtest/batch_simulator.py`

```python
# Line 68-71: Position limits
# BEFORE:
_MAX_DAILY_ENTRIES = 3
_MAX_LONG_POSITIONS = 6
_MAX_SHORT_POSITIONS = 3
_MAX_TOTAL_POSITIONS = 8
# AFTER:
_MAX_DAILY_ENTRIES = 2
_MAX_LONG_POSITIONS = 5
_MAX_SHORT_POSITIONS = 3
_MAX_TOTAL_POSITIONS = 6

# Line 77: Gap threshold
# BEFORE: _DEFAULT_GAP_THRESHOLD = 0.03
# AFTER:  _DEFAULT_GAP_THRESHOLD = 0.05

# Line 89-94: Strategy classes
# BEFORE: includes EmaPullback
# AFTER:  remove EmaPullback from list

# Line 63: _GROUP_B
# BEFORE: _GROUP_B = frozenset({"ema_pullback"})
# AFTER:  _GROUP_B = frozenset()
```

### `config/strategy_params.yaml`

```yaml
# gap_filter.max_gap_pct: 0.03 -> 0.05
# entry_limits.max_daily_entries: 3 -> 2
# entry_limits.max_long_positions: 6 -> 5
# strategies.rsi_mean_reversion.sl_atr_mult_long: 1.5 -> 1.0
# strategies.rsi_mean_reversion.sl_atr_mult_short: 2.0 -> 1.5
# strategies.rsi_mean_reversion.tp_atr_mult: 2.0 -> 1.5
# strategies.rsi_mean_reversion.max_hold_days: 7 -> 5
# strategies.rsi_mean_reversion.breakeven_activation_atr: 1.0 -> 0.8
# strategies.consecutive_down.sl_atr_mult_long: 1.5 -> 1.0
# strategies.consecutive_down.breakeven_activation_atr: 1.0 -> 0.8
# strategies.volume_divergence.sl_atr_mult_long: 1.5 -> 1.0
# strategies.volume_divergence.breakeven_activation_atr: 1.0 -> 0.8
# strategies.ema_pullback: add "enabled: false" or remove section
```

---

## Overfitting & Validation Warnings

1. **In-sample bias**: All optimal values are derived from the same 251-day dataset used for evaluation. Walk-forward validation is essential before live deployment.

2. **Regime sensitivity**: The test period may not include severe bear markets or regime changes. Max DD estimates assume similar market conditions.

3. **Interaction effects**: hold_5d (+15.1%) and gap_5pct (+11.7%) improvements were measured independently with default parameters. Combined effects are NOT additive. Realistic combined improvement estimate: +12-15% total return (not +26.8%).

4. **consecutive_down sample size**: 5 trades is insufficient for statistical significance. The 100% WR and 7.99x MFE/MAE could be partially due to small-sample luck. Increasing frequency to 15-30 trades will provide better statistical validation.

5. **SL tightening trade-off**: Tighter SLs increase the number of stopped-out trades. Some positions that would have recovered with wider SLs will be prematurely exited. The MFE/MAE analysis suggests this trade-off is net positive, but the magnitude could differ in out-of-sample data.

---

## Recommended Next Steps

1. **Implement Tier 1 changes** and re-run backtest to measure actual combined impact
2. **Validate ema_pullback disable** by comparing portfolio with/without it using new parameters
3. **Walk-forward test**: Split data into train (first 170 days) and test (last 81 days) to validate parameter stability
4. **Monitor consecutive_down**: After RSI_MAX expansion, track whether MFE/MAE stays above 3.0x
5. **DD stress test**: Run backtest on 2022 bear market data (if available) to validate DD estimates under adverse conditions
6. **Paper trade validation**: Run 2-4 weeks of paper trading with new parameters before live deployment
