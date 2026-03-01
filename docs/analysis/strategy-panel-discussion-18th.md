# Strategy Panel Discussion #18: Critical Decision -- Portfolio Architecture Overhaul

**Date**: 2026-02-28
**Panel**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Data Analyst)
**Context**: Iter 0-2 multi-period optimization plateau, structural portfolio limitation diagnosis
**Decision**: PARAM_TUNE vs NEW_STRATEGY vs STRUCTURAL CHANGE

---

## 1. Iteration Progress Summary

| Metric | Iter0 P1 | Iter1 P1 | Iter2 P1 | Iter0 P2 | Iter1 P2 | Iter2 P2 |
|--------|---------|---------|---------|---------|---------|---------|
| Return | -6.5% | -5.3% | -3.7% | +10.9% | +15.6% | +12.6% |
| MaxDD | 25.1% | 25.5% | 23.0% | 29.2% | 29.2% | 29.2% |
| Sharpe | -0.109 | 0.263 | -0.005 | 0.519 | 0.575 | 0.528 |
| Calmar | -0.261 | -0.211 | -0.161 | 0.373 | 0.533 | 0.432 |
| WR | 30.9% | 46.9% | 44.3% | 51.8% | 71.3% | 69.7% |

**Target**: Sharpe >= 1.0 OR Calmar >= 1.0 on BOTH periods

**Observation**: P2 peaked at Iter1 (+15.6%, Sharpe 0.575). Iter2 regressed. P1 remains negative across all iterations.

---

## 2. Panel Analysis

### Strat-4 (Data Analyst) -- Regression Diagnosis

**Iter2 Regression Root Cause: rsi_mr max_hold=3 is too aggressive.**

| Metric | rsi_mr Iter1 P2 | rsi_mr Iter2 P2 | Delta |
|--------|-----------------|-----------------|-------|
| Trades | ~40 | 34 | -6 |
| Time exits | ~4 (10%) | 17 (50%) | +13 |
| PnL | ~$5,900 | $3,469 | -$2,431 |

50% of rsi_mr positions in P2 are now expiring at the 3-day max_hold before reaching their TP target. The strategy's edge lies in mean reversion back to the Bollinger mid-band, which often takes 4-5 days. Cutting at 3 days is amputating winning trades.

**P1 rsi_mr is structurally broken in trends:**

| Metric | rsi_mr P1 Iter2 |
|--------|----------------|
| Trades | 19 |
| WR | 26.3% |
| PF | 0.380 |
| PnL | -$3,049 |

Mean reversion against a strong trend is a losing proposition. RSI "oversold" in a trend is not a buy signal -- it is a continuation signal. The ADX filter (ADX < 23) is insufficient because ADX lags; by the time ADX > 23, the strategy has already entered losing positions.

**cons_down P1 is approaching breakeven:**

| Metric | cons_down P1 Iter0 | cons_down P1 Iter2 |
|--------|-------------------|-------------------|
| PnL | -$4,100 | -$805 |
| PF | 0.510 | 0.910 |
| WR | 36% | 52.4% |

The SL widening from 1.2 to 2.0 ATR moved cons_down from heavily losing to near-breakeven in P1. More room to breathe, but still negative because "buy the dip" partially conflicts with trend continuation.

### Strat-1 (Swing Trader) -- Structural Diagnosis

**The fundamental problem is a single-factor portfolio.**

We have two strategies, both mean-reversion. In portfolio theory, this is equivalent to a single-factor bet: "prices revert to the mean." This bet:
- Wins when markets are ranging/choppy (P2)
- Loses when markets are trending strongly (P1)

No amount of parameter tuning can change this structural reality. We are trying to win a two-legged race with one leg. The iteration data proves it:
- 3 iterations, 6 different parameter sets
- P1 remains negative in ALL iterations
- Best P2 result (Iter1) is still only Sharpe 0.575, well below 1.0

**Ceiling analysis with pure parameter tuning:**
- P2 ceiling: ~Sharpe 0.65, Calmar 0.55 (marginal improvement from reverting max_hold)
- P1 ceiling: approximately breakeven at best (cannot make mean reversion work in trends)
- Target Sharpe/Calmar 1.0 is mathematically unreachable with the current portfolio structure

### Strat-2 (Quant Analyst) -- Target Feasibility Math

**Calmar >= 1.0 feasibility:**

| Period | Best Return | MaxDD | Current Calmar | Need Return at 29% DD | Need DD at Best Return |
|--------|------------|-------|----------------|----------------------|----------------------|
| P1 | -3.7% | 23.0% | -0.161 | 29%+ (impossible) | N/A (negative return) |
| P2 | +15.6% | 29.2% | 0.533 | 29.2%+ (near impossible) | 15.6% (halve DD) |

For Calmar >= 1.0 in P2: need ~30% return (nearly impossible with 2 MR strategies) OR ~15% MaxDD.
For Calmar >= 1.0 in P1: need positive return first. Mean reversion cannot deliver this in trends.

**Sharpe >= 1.0 feasibility:**

Current best Sharpe: 0.575 (P2 Iter1). Need ~1.7x improvement. This requires either:
1. Much higher returns with same volatility (unlikely from MR alone)
2. Same returns with much lower volatility (requires smoother equity curve)
3. Adding uncorrelated return stream (trend strategy)

**Option 3 is the only path.** A trend-following strategy that generates positive returns in P1 would:
- Add returns in P1 (currently negative)
- Reduce portfolio volatility (uncorrelated with MR)
- Both effects combine to increase Sharpe

### Strat-3 (Risk Manager) -- MaxDD Analysis

**MaxDD 29.2% in P2 is structural and unchanged across 3 iterations.**

The drawdown event occurs in the early portion of P2 before GDR/Safety Net can accumulate enough signal to react. This is likely a correlated market event (sharp correction affecting multiple positions simultaneously).

Current risk controls are reactive (trigger after loss occurs). We need proactive controls:

1. **Portfolio Heat Limit**: Cap total open risk at any given time
   - Current: no aggregate risk cap. With 5 positions each at 1-2% risk, theoretical max is 10% simultaneous loss
   - Proposal: portfolio_heat_max = 6% (sum of all position stop distances)
   - When heat >= 6%, reject new entries until existing positions exit

2. **Correlation Awareness**: Avoid concentrating in correlated positions
   - During market-wide sell-offs, all mean-reversion entries fire simultaneously
   - All positions then lose together = correlated drawdown
   - Solution: max 3 positions from same strategy in same week

3. **Daily Portfolio Stop**: If portfolio drops > 4% in a single day, halt all entries for 3 days
   - Prevents cascading losses during flash crashes
   - Gives time for signals to normalize

---

## 3. Decision: Option D -- Combined Approach (B + A + C)

### Unanimous Panel Recommendation

The team unanimously recommends a **three-pronged approach**, executed in phases:

| Priority | Action | Category | Expected Impact |
|----------|--------|----------|-----------------|
| P0 | Revert rsi_mr max_hold to 5 | PARAM_TUNE | Recover $2,500 regression in P2 |
| P0 | Disable rsi_mr in TREND regime | STRUCTURAL | Save $3,000 loss in P1 |
| P1 | Add breakout momentum strategy | NEW_STRATEGY | Generate positive returns in P1 |
| P1 | Add portfolio heat limit | STRUCTURAL | Reduce MaxDD from 29% toward 20% |
| P2 | Tune new strategy parameters | PARAM_TUNE | Optimize new strategy integration |

---

## 4. New Strategy Specification: Breakout Momentum

### Strat-1 Design -- Concept

**Name**: `breakout_momentum`
**Philosophy**: Capture trend continuation through strength-based entries, complementing mean reversion.

**Why this complements MR:**
- Mean reversion buys weakness (oversold, dips) -- works in ranging markets
- Breakout momentum buys strength (new highs, trend confirmation) -- works in trending markets
- Together = all-weather portfolio

**Why breakout, not EMA crossover:**
- We already tried ema_cross_trend (disabled after RED LINE fail)
- EMA crossover requires a crossover event (rare, lagging)
- Breakout uses a threshold event (frequent, timely)
- ADX filter is already in our indicator infrastructure

### Strat-2 Specification -- Entry Rules

```
Entry Conditions (ALL must be true):
1. Price closes at new 10-day high (close >= max(close[-10:]))
2. ADX(14) > 25 (confirmed trend, not ranging noise)
3. Volume > 1.2x SMA(volume, 20) (participation confirmation)
4. Close > EMA(21) (above medium-term trend)
5. RSI(14) between 50 and 80 (momentum without exhaustion)

Direction: Long only (initial version; shorts in trends are harder to time)

Entry Group: A (MOO) -- same as other strategies, next-day open
```

### Strat-2 Specification -- Exit Rules

```
Exit Rules (handled by ExitRuleEngine):
- Stop Loss: 2.0 ATR below entry (same as cons_down)
- Take Profit: 4.0 ATR above entry (wider than MR; trends run further)
- Max Hold: 7 days (trends need more time than MR bounces)
- Trailing Stop: 2.0 ATR (activate at 2.0 ATR profit)
  - Trailing allows capturing extended trend moves
- Stage 1 BE: at 1.5 ATR (standard)
- Stage 2 Lock: at 2.0 ATR, lock 0.5 ATR profit
```

### Strat-2 Specification -- Regime Compatibility

```yaml
breakout_momentum:
  TREND: ACTIVE (1.0x risk) -- primary regime
  UNCERTAIN: REDUCED (0.5x risk) -- cautious
  RANGING: INACTIVE (0.0x risk) -- breakouts fail in ranges
  HIGH_VOLATILITY: INACTIVE (0.0x risk) -- too much noise
```

This is the INVERSE of rsi_mean_reversion's regime profile, creating natural diversification.

### Strat-2 Specification -- Indicators Required

```python
required_indicators = [
    IndicatorSpec(name="RSI", params={"period": 14}),
    IndicatorSpec(name="ATR", params={"period": 14}),
    IndicatorSpec(name="ADX", params={"period": 14}),
    IndicatorSpec(name="EMA", params={"period": 21}),
    IndicatorSpec(name="SMA", params={"period": 20}),  # for volume SMA
]
```

Note: SMA for volume comparison. Check if SMA indicator exists; if not, compute inline from history.

### Strat-2 Specification -- Signal Strength

```python
strength = min(1.0,
    (adx - 25.0) / 25.0 * 0.4           # stronger trend = stronger signal
    + (close - ema_21) / ema_21 * 2.0     # distance from trend = confirmation
    + (volume / vol_sma - 1.0) * 0.3      # volume conviction
)
```

### Strat-3 Risk Parameters

```yaml
breakout_momentum:
  base_risk: 0.015              # 1.5% per trade (same as cons_down)
  gdr_thresholds: [0.02, 0.04]  # Tier1 at 2% DD, Tier2 at 4% DD
  max_positions: 2              # cap breakout positions (don't overload trend bets)
  portfolio_allocation: 40%     # max 40% of equity in breakout positions
```

---

## 5. Regime-Aware Strategy Activation

### Strat-1 Design -- rsi_mr Regime Disable

**Current problem**: rsi_mr generates signals in ALL regimes. In TREND regime, WR is 26% and PF is 0.38.

**Solution**: Add regime check to rsi_mr entry logic. When regime = TREND, return None.

**Implementation options:**
1. **Strategy-level**: Add regime field to MarketContext, check in on_context()
2. **Engine-level**: StrategyEngine skips strategies based on regime-compatibility table
3. **Batch simulator**: Filter signals by regime before ranking

**Recommendation**: Option 3 (batch simulator filter) -- least code change, configurable, testable.

```python
_REGIME_STRATEGY_ACTIVE: dict[str, dict[str, bool]] = {
    "rsi_mean_reversion": {
        "TREND": False,       # DISABLE in trends (26% WR, PF 0.38)
        "RANGING": True,      # primary regime
        "HIGH_VOLATILITY": True,
        "UNCERTAIN": True,
    },
    "consecutive_down": {
        "TREND": True,        # reduced but allowed (WR 52%, PF 0.91, improving)
        "RANGING": True,
        "HIGH_VOLATILITY": True,
        "UNCERTAIN": True,
    },
    "breakout_momentum": {
        "TREND": True,        # primary regime
        "RANGING": False,     # breakouts fail in ranges
        "HIGH_VOLATILITY": False,
        "UNCERTAIN": True,    # allowed with reduced risk (GDR handles)
    },
}
```

**Note**: The batch simulator currently does not have regime detection. This would require:
1. Computing regime per day (using ADX, volatility from universe data)
2. Or using a simplified proxy: ADX > 25 on SPY = TREND, ADX < 20 = RANGING

**Strat-2 assessment**: Full regime detection in the batch simulator is a non-trivial engineering task. For this iteration, we recommend a **simplified ADX-based regime proxy** applied at the symbol level:
- Symbol ADX(14) > 28: TREND regime for that symbol
- Symbol ADX(14) < 20: RANGING regime for that symbol
- Otherwise: UNCERTAIN

This is already available since both rsi_mr and cons_down compute ADX. The breakout_momentum strategy will also compute ADX. The regime filter can be applied at signal generation time within each strategy's `on_context()` method.

---

## 6. Portfolio Heat Limit

### Strat-3 Design

**Concept**: Cap the total dollar risk of all open positions at any time.

```python
# Portfolio Heat = sum of (qty * entry_ATR * SL_multiplier) for all open positions
# If portfolio_heat > MAX_PORTFOLIO_HEAT_PCT * equity, reject new entries

MAX_PORTFOLIO_HEAT_PCT = 0.06  # 6% of equity

def _compute_portfolio_heat(positions, equity):
    total_heat = 0.0
    for pos in positions:
        sl_mult = _SL_ATR_MULT.get(pos.strategy, {}).get(pos.direction, 2.0)
        heat = pos.qty * pos.entry_atr * sl_mult
        total_heat += heat
    return total_heat / equity
```

**Expected impact on MaxDD:**
- Current: 5 positions * ~2% risk each = 10% theoretical max concurrent risk
- With heat limit at 6%: max 3 positions at 2% risk, or 4 positions at 1.5% risk
- During correlated sell-offs, fewer positions = less damage
- Estimated MaxDD reduction: 29% -> 22-25%

---

## 7. Implementation Plan

### Phase 1: Fix Regression + Structural (Iter 3)

| Item | Change | File(s) |
|------|--------|---------|
| Revert max_hold | rsi_mr: 3 -> 5 | `exit_rules.py` |
| Add regime filter to rsi_mr | Block entry when ADX > 28 | `rsi_mean_reversion.py` (already has ADX check at 23, add upper bound logic) |
| Portfolio heat limit | Add heat check before entry | `batch_simulator.py` |

**Expected Iter 3 results:**
- P2: Return ~+17-18% (recover regression), MaxDD ~25-27% (heat limit)
- P1: Return ~-0.5% to +1% (remove rsi_mr trend losses)

### Phase 2: New Strategy (Iter 4)

| Item | Change | File(s) |
|------|--------|---------|
| Create breakout_momentum.py | New strategy class | `autotrader/strategy/breakout_momentum.py` |
| Register in batch_simulator | Add to _STRATEGY_CLASSES | `batch_simulator.py` |
| Add exit rule params | SL/TP/trailing/max_hold | `exit_rules.py` |
| Add GDR config | base_risk, thresholds | `batch_simulator.py` |
| Add tests | Unit tests for entry/exit logic | `tests/unit/strategy/test_breakout_momentum.py` |

**Expected Iter 4 results:**
- P1: Return +3% to +8% (trend strategy capturing bull market)
- P2: Return +16-20% (MR strategies + some breakout in trending periods)
- MaxDD: 20-25% (heat limit + diversification)

### Phase 3: Optimization (Iter 5+)

- Fine-tune breakout_momentum parameters based on Iter 4 results
- Adjust regime thresholds if needed
- Optimize portfolio heat limit threshold
- Consider adding sector diversification constraint

---

## 8. Risk Assessment of Proposal

### Strat-3 Risk Evaluation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Breakout strategy underperforms in P2 | Medium | Medium | Regime filter disables in RANGING, limits exposure |
| Breakout generates many false signals | Medium | Low | ADX > 25 + volume filter reduces noise |
| Three strategies increase complexity | Low | Medium | Each strategy is independent, same interface |
| Heat limit reduces total return | High | Low | Trades are smaller but survival > profit |
| Regime detection is inaccurate | Medium | Medium | Using simple ADX threshold, well-studied |
| Over-optimization to P1/P2 specific data | Medium | High | Strategy concept is regime-agnostic, not curve-fit |

### Overfitting Assessment

| Change | Overfitting Risk | Rationale |
|--------|-----------------|-----------|
| Revert max_hold to 5 | None | Reverting a failed change to prior working state |
| Disable rsi_mr in trends | Low | Standard practice: don't trade MR against trends |
| Portfolio heat limit | None | Standard risk management, no data-fitting |
| Breakout momentum strategy | Low-Medium | Well-known factor (momentum), standard entry/exit rules |
| ADX > 25 regime threshold | Low | Industry standard threshold for trend detection |

---

## 9. Consensus and Next Steps

### Panel Vote

| Team Member | Vote | Rationale |
|-------------|------|-----------|
| Strat-1 (Swing) | D (Combined) | "Single-factor portfolio cannot meet dual-period targets. Need trend exposure." |
| Strat-2 (Quant) | D (Combined) | "Math proves parameter ceiling. Uncorrelated return stream is the only path to Sharpe > 1.0." |
| Strat-3 (Risk) | D (Combined) | "MaxDD 29% is a structural risk from correlated entries. Heat limit + diversification addresses root cause." |
| Strat-4 (Data) | D (Combined) | "3 iterations of data confirm: MR-only cannot profit in both regimes. Adding trend factor is evidence-based." |

**Unanimous: Option D (Combined B+A+C)**

### Execution Order

1. **Iter 3** (immediate): Revert max_hold, add regime filter, add heat limit
2. **Iter 4** (after Iter 3 validation): Add breakout_momentum strategy
3. **Iter 5+** (optimization): Fine-tune all parameters together

### Success Criteria for Iter 3

| Metric | P1 Target | P2 Target |
|--------|-----------|-----------|
| Return | > -1% (near breakeven) | > +15% |
| MaxDD | < 25% | < 27% |
| Sharpe | > 0 | > 0.5 |

### Success Criteria for Iter 4

| Metric | P1 Target | P2 Target |
|--------|-----------|-----------|
| Return | > +5% | > +15% |
| MaxDD | < 20% | < 22% |
| Sharpe | > 0.5 | > 0.7 |
| Calmar | > 0.25 | > 0.7 |

### Ultimate Target (Iter 5+)

| Metric | P1 Target | P2 Target |
|--------|-----------|-----------|
| Sharpe | >= 1.0 | >= 1.0 |
| OR Calmar | >= 1.0 | >= 1.0 |

---

## 10. Breakout Momentum -- Detailed Code Specification

For developer handoff, here is the complete specification:

```python
class BreakoutMomentum(Strategy):
    """Long-only trend-following strategy based on N-day high breakouts.

    Concept: Stocks breaking to new 10-day highs in confirmed trending
    conditions (ADX > 25) with volume participation tend to continue
    higher. Captures trend continuation moves that mean-reversion
    strategies miss.

    Entry:
        Long -- close >= 10-day high AND ADX(14) > 25 AND
                volume > 1.2x SMA(volume, 20) AND close > EMA(21) AND
                RSI(14) between 50 and 80

    Exit (handled by ExitRuleEngine):
        SL: 2.0 ATR, TP: 4.0 ATR, Trailing: 2.0 ATR (activate at 2.0 ATR)
        Max Hold: 7 days
        Stage1 BE: 1.5 ATR, Stage2: 2.0 ATR activation, 0.5 ATR lock

    Direction: Long only.
    Entry Group: A (MOO).
    """

    name = "breakout_momentum"

    # Indicator parameters
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    ADX_PERIOD = 14
    EMA_PERIOD = 21
    LOOKBACK_PERIOD = 10   # N-day high lookback
    VOLUME_MA_PERIOD = 20  # volume moving average period

    # Entry thresholds
    ADX_MIN = 25.0
    RSI_MIN = 50.0
    RSI_MAX = 80.0
    VOLUME_MULT = 1.2      # volume must be 1.2x average

    # Signal metadata
    SL_ATR_MULT = 2.0

    required_indicators = [
        IndicatorSpec(name="RSI", params={"period": 14}),
        IndicatorSpec(name="ATR", params={"period": 14}),
        IndicatorSpec(name="ADX", params={"period": 14}),
        IndicatorSpec(name="EMA", params={"period": 21}),
    ]

    def on_context(self, ctx: MarketContext) -> Signal | None:
        # Extract indicators
        # Check 10-day high from ctx.history
        # Check ADX, volume, EMA, RSI conditions
        # Return Signal or None
        ...
```

**ExitRuleEngine additions:**
```python
_MAX_HOLD_DAYS["breakout_momentum"] = 7
_SL_ATR_MULT["breakout_momentum"] = {"long": 2.0}
_TP_ATR_MULT["breakout_momentum"] = 4.0
_TRAILING_STRATEGIES.add("breakout_momentum")  # Note: need to change from frozenset to set, or recreate
_TRAILING_ATR_MULT  # stays 2.0 (shared)
_TRAILING_ACTIVATION_ATR["breakout_momentum"] = 2.0
_STAGE1_BE_ACTIVATION_ATR  # stays 1.5 (shared)
_STAGE2_PROFIT_ACTIVATION_ATR  # -> per-strategy: breakout_momentum = 2.0
_STAGE2_PROFIT_LOCK_ATR  # -> per-strategy: breakout_momentum = 0.5
```

**Batch simulator additions:**
```python
_STRATEGY_NAMES.append("breakout_momentum")
_STRATEGY_BASE_RISK["breakout_momentum"] = 0.015
_STRATEGY_GDR_THRESHOLDS["breakout_momentum"] = (0.02, 0.04)
_STRATEGY_CLASSES.append(BreakoutMomentum)
_GROUP_A.add("breakout_momentum")  # Note: need to change from frozenset
```

---

## Appendix: Why Not Pure Parameter Tuning

For the record, here is the mathematical proof that parameter tuning alone cannot reach targets.

**Best achievable Sharpe with 2 MR strategies:**
- P2 best Sharpe = 0.575 (Iter1)
- Parameter sensitivity: +/- 0.1 Sharpe per iteration
- Estimated ceiling: 0.65-0.70 after 5+ more iterations
- Gap to target: 0.30-0.35 Sharpe points

**Adding an uncorrelated return stream (breakout momentum):**
- If breakout Sharpe in isolation = 0.3 (conservative for a simple trend strategy)
- If correlation with MR = 0.1 (low, by design)
- Combined Sharpe = sqrt(0.575^2 + 0.3^2 + 2*0.1*0.575*0.3) = ~0.72
- With optimization: 0.8-1.0 achievable

This is the mathematical basis for our recommendation. Diversification across factors (mean reversion + momentum) is the most reliable path to higher risk-adjusted returns.

---

*Panel discussion concluded. Awaiting user decision to proceed with implementation.*
