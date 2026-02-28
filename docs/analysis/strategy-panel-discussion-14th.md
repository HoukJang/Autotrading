# Strategy Panel Discussion #14: rsi_mr Regime Transition Fix + adx_breakout Design

**Date**: 2026-02-28
**Panel**: Strat-2 (Risk), Strat-4 (Trade Analyst), Strat-5 (Quant), Strat-6 (Architect), Strat-7 (Root Cause)
**Context**: 13A backtest results, user-identified regime transition vulnerability in rsi_mr
**Scope**: (1) Fix rsi_mr regime transition losses, (2) Finalize adx_breakout trend-following design

---

## 1. Full Panel Discussion

### STRAT-7 (Root Cause / Structure Analyst) -- Opening Diagnosis

The user's diagnosis is precise and I want to validate it structurally before we discuss solutions.

**The Root Cause Chain (confirmed):**

1. rsi_mr's ADX < 25 filter is a **point-in-time snapshot** of a **lagging indicator**. ADX(14) summarizes the last 14+ bars of directional movement. When ADX reads 23 today, it tells us what the market WAS doing, not what it IS BECOMING.

2. The dangerous scenario: ADX is at 22 and rising. The market is transitioning from ranging to trending. RSI hits 30 (oversold in the context of a range), BB %B < 0.05 (at lower band). rsi_mr sees a textbook mean-reversion setup. It enters long.

3. But the "oversold" condition is actually the BEGINNING of a trend breakdown. The market continues lower. ADX climbs past 25, confirming a trend -- but the position is already open and moving against us.

4. The 1.0 ATR stop loss fires. One trade lost. Then the pattern repeats because regime transitions don't happen in a single bar -- they unfold over days. The market oscillates near the transition boundary, generating repeated false mean-reversion signals.

5. Result: MaxCL of 19 consecutive losses. This is not random bad luck. This is a structural vulnerability being exploited by a predictable market behavior.

**The critical structural insight:** The problem is NOT that ADX < 25 is wrong. It is that ADX < 25 is a NECESSARY but INSUFFICIENT condition for mean-reversion entry. We need a second-order condition: not just "is ADX below threshold" but "is ADX stable or declining below threshold."

This is the difference between:
- ADX = 22 and falling (confirmed range, safe to enter)
- ADX = 22 and rising (transition zone, dangerous to enter)

Both pass the ADX < 25 filter. Only one should produce a trade.

### STRAT-6 (Trading System Architect) -- Architecture Assessment

Before we discuss parameter values, I need to flag an architectural constraint that shapes our solution space.

**Current ADX Indicator Architecture:**

Looking at `autotrader/indicators/builtin/trend.py`, the ADX indicator returns a **single scalar float**:

```python
class ADX(Indicator):
    def calculate(self, bars: deque[Bar]) -> float | None:
        # ... computes plus_di, minus_di internally ...
        return adx  # scalar only
```

The +DI and -DI values are computed internally but **discarded**. They are not returned. This means:

1. **Solution A3 (DI Spread Filter)** -- requires architecture change (return dict or new indicator)
2. **Solution B2 (DI Crossover Exit)** -- same dependency
3. **Solution A1 (ADX Direction)** -- can be done WITHOUT architecture change, by storing previous ADX values in strategy state
4. **Solution A2 (ADX Threshold)** -- trivial parameter change, no architecture impact

**My recommendation on DI indicators:**

We should NOT modify the existing ADX indicator to return a dict right now. Why:
- Breaking change: every consumer of `ADX_14` expects a float (rsi_mr, batch_simulator, ranking.py, exit_rules.py)
- The DI spread filter is an optimization, not a necessity
- ADX slope + tighter threshold covers 80%+ of the transition detection need
- We can add DI as a separate indicator later if backtests show we need it

For adx_breakout, we also do NOT strictly need +DI/-DI. The EMA(10) > EMA(21) crossover already establishes trend direction. DI would be redundant confirmation.

**The clean architecture path:**
- rsi_mr: Use internal state to track ADX slope (store prev_adx per symbol)
- adx_breakout: Use existing ADX + EMA indicators, no DI needed
- Future: If needed, create `ADX_FULL` indicator returning dict with {adx, plus_di, minus_di}

**Regarding exit_rules.py for regime guard:**

The `ExitRuleEngine.evaluate()` already receives an `indicators` dict. The ADX_14 value is available there. We can add an `_evaluate_regime_transition()` method that checks ADX for rsi_mr positions -- no architecture change needed, just a new method in the evaluation chain.

### STRAT-5 (Quant Algorithm Expert) -- Mathematical Analysis

**ADX Slope Detection -- What Lookback Period?**

ADX slope can be measured over different windows. Let me analyze the options:

| Method | Formula | Sensitivity | False Positive Risk |
|--------|---------|-------------|---------------------|
| 1-bar delta | ADX[0] < ADX[-1] | High | High (noisy) |
| 2-bar delta | ADX[0] < ADX[-2] | Medium | Medium |
| 3-bar delta | ADX[0] < ADX[-3] | Low | Low (recommended) |
| Linear regression slope | slope of ADX over N bars | Configurable | Depends on N |

I recommend **3-bar lookback** for ADX slope detection:
- `ADX[today] <= ADX[3 bars ago]` means ADX is not rising over the recent window
- 1-bar delta is too noisy -- ADX often jitters +/- 1 point between bars
- 3-bar delta captures genuine directional change while filtering noise
- This translates to: store last 3 ADX values per symbol, check current <= oldest

**Threshold Analysis:**

Current: ADX < 25
Proposed: ADX < 20

Impact modeling based on ADX distribution across S&P 500:
- ADX < 25 captures roughly 55-65% of all stock-days
- ADX < 20 captures roughly 35-45% of all stock-days
- This is a ~30% reduction in eligible signal days
- But the eliminated zone (ADX 20-25) is exactly where transition risk is highest

Combined filter (ADX < 20 AND ADX not rising over 3 bars):
- Captures roughly 25-35% of stock-days
- This is aggressive but targets only confirmed ranging environments
- Expected signal count: ~98 trades -> approximately 60-75 trades
- The lost trades are disproportionately losers (transition zone entries)

**Kelly Criterion Assessment for rsi_mr:**

Current rsi_mr statistics:
- Win rate (W): ~36% (estimated from PF 1.20 and 64% SL rate)
- Average win / Average loss ratio (R): ~1.85 (estimated from PF 1.20, W=0.36)
- Kelly fraction: W - (1-W)/R = 0.36 - 0.64/1.85 = 0.36 - 0.346 = 0.014 = 1.4%

Current base risk is 1.0%. Kelly says 1.4%, so we are slightly under-betting (good for safety).

After fix (projected):
- Win rate: ~48% (removing transition zone losers)
- Average loss stays similar (SL still at 1.0 ATR)
- Average win stays similar (same targets)
- New R estimate: ~1.50 (some of the removed trades were moderate winners too)
- Kelly: 0.48 - 0.52/1.50 = 0.48 - 0.347 = 0.133 = 13.3%

The Kelly fraction jumps dramatically because we are removing the concentrated losing streak. Even with conservative fractional Kelly (0.25x), that would suggest 3.3% risk is acceptable after the fix. However, I recommend keeping base risk at 1.0% until we validate with real backtests.

**ADX Exit Threshold for Regime Guard:**

For Solution B (position-level exit), I need to set the ADX crossover exit threshold:

- ADX < 20 is the entry threshold (proposed)
- If we set exit trigger at 22, we get only 2 points of buffer before a position entered at ADX 19 would be force-exited
- If we set it at 25, we let the transition develop too far -- 5-6 points of ADX rise means 3-4 bars have already passed against us
- **Recommendation: exit trigger at ADX > 23 AND ADX has risen by 3+ points since entry**
- This combines absolute level with rate-of-change for fewer false exits

### STRAT-2 (Portfolio Risk Manager) -- Risk Architecture

**rsi_mr Risk Assessment:**

The 48.4% solo drawdown is the single largest risk in our portfolio. The MaxCL of 19 is catastrophic -- even at 1% base risk, 19 consecutive losses means 19% cumulative drawdown from rsi_mr alone (before GDR kicks in).

The GDR thresholds for rsi_mr are:
- Tier 1 at 3% DD (halves risk to 0.5%)
- Tier 2 at 6% DD (HALTS trading)

So the GDR catches this after 3 losses (3 x 1% = 3% -> Tier 1) and halts after 6 losses. But MaxCL is 19 -- which means many of these losses cluster WITHIN a single GDR cycle, or the strategy recovers just enough to reset the GDR before the next cluster.

**The GDR is reactive, not preventive.** It limits damage after losses occur but does nothing to prevent entering losing trades in the first place. The entry filter fix (Solution A) is therefore more valuable than any GDR tuning.

**Combined Solution Risk Assessment:**

| Fix Layer | What It Prevents | Expected Impact |
|-----------|-----------------|-----------------|
| ADX < 20 (entry filter) | Entry when ADX is near transition | -30% signal count, removes worst clusters |
| ADX slope check (entry filter) | Entry when ADX is rising | Blocks entry even below 20 if trend is forming |
| Regime exit guard (position-level) | Staying in position through transition | Cuts losses short when entry filter fails |
| Adaptive sizing (20-25 zone) | NOT NEEDED if ADX < 20 threshold | Redundant with tighter threshold |

**Solution C (Adaptive Sizing) is unnecessary** if we tighten the threshold to ADX < 20. The 20-25 zone becomes a no-entry zone for rsi_mr. There is no position to size adaptively.

However, I want to keep one safety layer: the regime exit guard (Solution B). Even with ADX < 20 entry, a stock can transition from ADX 18 to ADX 30 in 3-4 bars during a sudden trend initiation (earnings surprise, sector rotation). The exit guard catches this.

**adx_breakout Risk Parameters:**

For a new strategy with unknown real-world performance:
- Start with 1.5% base risk (moderate, given trend strategies have higher individual trade variance)
- SL at 1.5 ATR (wider than rsi_mr's 1.0 ATR -- trend pullbacks need room)
- Trailing stop at 2.0 ATR (let winners run, which is the whole point of trend following)
- GDR: Tier 1 at 4%, Tier 2 at 8% (same as consec_down -- both are single-direction strategies with similar expected frequency)

**Portfolio Position Limits:**

With 3 strategies, we need to update position limits:
- Current: max_total_positions = 5
- Proposed: max_total_positions = 6 (allow each strategy to hold 2 positions)
- Max long: 6 (adx_breakout + consec_down are both long-only, may overlap)
- Max short: 3 (only rsi_mr shorts)
- Max per strategy: soft cap of 2 (adx_breakout should not hold more than 2 trend positions simultaneously)

### STRAT-4 (Trade Analyst) -- Statistical Analysis

**Expected Signal Frequency for adx_breakout:**

Let me estimate signal frequency from S&P 500 universe:

Filtering stages:
1. S&P 500: 500 stocks scanned nightly
2. ADX > 25: ~35-45% of stocks on any given day = 175-225 stocks
3. EMA(10) > EMA(21): ~50% of those (uptrend confirmed) = 88-112 stocks
4. Pullback to EMA(10) (within 1.5%): ~5-10% of trending stocks = 4-11 stocks/day
5. RSI 40-65 (not overbought, not oversold): ~60% of pullbacks = 3-7 stocks/day
6. Signal strength ranking + position limits: 0-1 entries per day

**Annual estimate:** ~150-200 raw signals, ~60-80 entries after ranking/limits/GDR.

This is significantly more active than the 13th panel's estimate. The key variable is the pullback proximity filter (step 4). At 1.5%, we get more signals; at 1.0%, fewer. I recommend starting at 1.5% and tightening if needed.

**Expected Win Rate and Payoff Ratio:**

Trend pullback strategies on S&P 500 constituents historically show:
- Win rate: 42-52% (lower than mean reversion because trend continuation is uncertain)
- Average win: 3-5% per trade (trailing stop lets winners extend)
- Average loss: 1.5-2.5% per trade (SL at 1.5 ATR)
- Payoff ratio: 1.5-2.5x
- Profit Factor: 1.2-1.8x

Conservative estimates for our design:
- Win rate: 45%
- Average win: 3.5% (trailing stop + TP at 3.0 ATR)
- Average loss: 2.0% (SL at 1.5 ATR)
- Payoff ratio: 1.75x
- Expected PF: (0.45 x 3.5) / (0.55 x 2.0) = 1.575 / 1.10 = 1.43

This would be a significant improvement over rsi_mr's current 1.20 PF, but we should not expect it to match consec_down's 1.69 PF (which benefits from a very specific and well-documented edge).

**rsi_mr Post-Fix Projections:**

Current (13A): 98 trades, PF 1.20, PnL +$3,357, DD 48.4%, MaxCL 19
Projected after fix:

| Metric | Current | After Fix (est.) | Basis |
|--------|---------|-----------------|-------|
| Trades | 98 | 65-75 | ~25-30% removed by ADX < 20 + slope |
| Win Rate | ~36% | ~46-50% | Transition losses eliminated |
| PF | 1.20 | 1.35-1.50 | Fewer losses, similar wins |
| PnL | +$3,357 | +$2,800-$3,500 | Less volume but better quality |
| Solo DD | 48.4% | 20-28% | MaxCL reduction is primary driver |
| MaxCL | 19 | 7-10 | No more transition clusters |
| SL Rate | 64% | 45-52% | Fewer SL hits from trend continuation |

The PnL might decrease slightly because we are removing some valid trades along with the bad ones. But the risk-adjusted return (Sharpe, Calmar) should improve dramatically.

**ADX Period for adx_breakout:**

> Should it use the same ADX(14) as rsi_mr, or a different period?

Yes, use ADX(14). Reasons:
1. ADX(14) is the industry standard and well-tested
2. Sharing the indicator computation means no additional warmup or compute cost
3. The 25 threshold for trend identification is calibrated for ADX(14)
4. Using a different period (e.g., ADX(10)) would require recalibrating all thresholds
5. Both strategies reading the same ADX means the regime zones are perfectly complementary: rsi_mr exits where adx_breakout enters

### STRAT-6 (Architect) -- Responding to Strat-5 on Exit Guard

Strat-5 proposes: "exit when ADX > 23 AND ADX has risen by 3+ points since entry."

This requires storing the ADX value at entry time. Where does this go?

**Option A: In HeldPosition (exit_rules.py)**
- Add `entry_adx: float` field to HeldPosition
- Populated at position creation time in entry_manager.py
- Read in _evaluate_regime_transition()
- Clean design, follows existing pattern (entry_atr is already stored)

**Option B: In strategy internal state (_PositionState)**
- Add entry_adx to _PositionState in rsi_mean_reversion.py
- Checked in the strategy's own _check_exit()
- Problem: the strategy's _check_exit is a SIGNAL generator, not an ORDER executor. The actual exit logic lives in ExitRuleEngine.

**Recommendation: Option A.** The regime exit guard should live in `ExitRuleEngine._evaluate_regime_transition()`, positioned BETWEEN SL and TP in the evaluation chain. This is consistent with how all other exits work.

Implementation:
1. Add `entry_adx: float = 0.0` to HeldPosition dataclass
2. In entry_manager._create_held_position, populate from candidate.indicators["ADX_14"]
3. In batch_simulator, populate similarly when creating HeldPosition
4. In ExitRuleEngine.evaluate(), add _evaluate_regime_transition() call after SL, before TP
5. _evaluate_regime_transition(): for rsi_mr positions only, check if current ADX > 23 AND (current ADX - entry_adx) >= 3

### STRAT-7 (Root Cause) -- Validating the Combined Approach

Let me validate that Solutions A + B together don't create new problems:

**Risk 1: Over-filtering rsi_mr signals**
- ADX < 20 + slope check could reduce signals from 98 to 50-60
- If we also force-exit on regime transition, some of those 50-60 will exit early
- Net trades completing normally: maybe 40-50
- Is that enough for statistical significance? Marginal but acceptable for a 2-year backtest. Over 4-year period it would be ~80-100 trades.

**Risk 2: The regime exit guard exits profitable trades**
- Scenario: Enter at ADX 18, position is profitable, ADX rises to 24. Guard triggers exit.
- The position was WINNING but is being force-exited because ADX rose.
- This is acceptable because: (a) the trade has been captured at TP or partial profit, (b) the regime exit fires BEFORE the trailing stop or time exit, (c) the trade would likely give back profits as the trend develops.
- Mitigation: Only trigger regime exit if the position is NOT already at breakeven or better. If position is profitable and has triggered the breakeven stop (0.6 ATR in favor), let the breakeven stop handle it instead of the regime guard.

Wait -- that's an important refinement. Let me revise:

**Refined Regime Exit Guard Logic:**
```
IF strategy == "rsi_mean_reversion":
    IF current_adx > 23 AND (current_adx - entry_adx) >= 3:
        IF position is at a loss (current_price vs entry_price):
            EXIT immediately (reason: "regime_transition")
        ELSE:
            # Position is profitable -- let breakeven stop or TP handle it
            HOLD (but the breakeven stop at entry price protects downside)
```

This way:
- Losing positions in transition zones are cut early (primary goal)
- Profitable positions that happen to coincide with ADX rise are protected by breakeven stop
- We avoid giving up profitable trades unnecessarily

**Risk 3: ADX slope false negatives**
- What if ADX is at 19, has been flat for 3 bars, then suddenly spikes to 28 in one bar?
- This can happen on a gap day or news event
- The entry filter would have allowed entry (ADX < 20, not rising)
- The regime exit guard catches it next bar (ADX > 23, delta >= 3)
- The combination works -- this is exactly why we need BOTH filters

**Structural Verdict:** The combined A + B approach is sound. A handles the common case (gradual transition), B handles the edge case (sudden transition). Together they provide defense-in-depth.

### STRAT-2 (Risk) -- on adx_breakout Position Sizing

**Base risk at 1.5%:**

Let me validate this against our portfolio constraints.

Worst case: 3 strategies all at max positions
- rsi_mr: 2 positions x 1.0% risk = 2.0% equity at risk
- consec_down: 2 positions x 2.0% risk = 4.0% equity at risk
- adx_breakout: 2 positions x 1.5% risk = 3.0% equity at risk
- Total: 9.0% equity simultaneously at risk

For a $5K account: $450 at risk simultaneously. That is aggressive but within the user's stated "aggressive risk tolerance." For $1K account: $90 at risk -- more manageable.

With the 1.5 ATR SL for adx_breakout, the actual position sizes will be:
- qty = risk_per_trade / (1.5 * ATR)
- For a $100 stock with ATR $3: qty = ($5000 * 0.015) / ($3 * 1.5) = $75 / $4.50 = 16 shares
- Position value: $1,600 = 32% of equity -- within _MAX_POSITION_PCT of 20%? No, exceeds it.

**Issue:** 32% exceeds our 20% position cap. The cap will bind and reduce the position.
- Cap-limited qty: $5000 * 0.20 / $100 = 10 shares
- Effective risk: 10 * $4.50 / $5000 = 0.9% (below 1.5% target)

For trend strategies on higher-priced S&P 500 stocks, the position cap will frequently bind. This is actually acceptable -- it means our per-trade risk is naturally limited on expensive stocks.

**Trailing stop implementation for adx_breakout:**

This is a first for our system. Currently `_TRAILING_STRATEGIES` is an empty frozenset. Adding adx_breakout to it activates the existing trailing stop code in ExitRuleEngine._evaluate_trailing().

The existing code requires:
- `_TRAILING_ATR_MULT`: trail distance (set to 2.0 ATR)
- `_TRAILING_ACTIVATION_ATR`: minimum favorable move before trailing starts (set to 1.0 ATR)
- Trail stop is floored at entry price (trailing can never cause a loss once activated)

This is clean -- the infrastructure exists, we just need to register adx_breakout.

### STRAT-4 (Trade Analyst) -- Cross-Strategy Correlation

**Will adx_breakout and rsi_mr be correlated?**

In theory: perfectly anti-correlated. rsi_mr trades ADX < 20, adx_breakout trades ADX > 25. They should never fire on the same stock on the same day.

In practice: they operate on different stocks at different times. During sector rotation:
- Tech stocks might be trending (ADX > 25) -> adx_breakout enters tech
- Utilities might be ranging (ADX < 20) -> rsi_mr enters utilities
- This is diversification by regime, which is exactly what we want

**Portfolio-level correlation estimate:**
- rsi_mr vs adx_breakout: -0.15 to -0.30 (weak negative correlation, ideal)
- rsi_mr vs consec_down: +0.20 to +0.40 (both are mean reversion, some overlap)
- adx_breakout vs consec_down: near zero (different regime targets, different holding patterns)

This is a genuinely complementary portfolio. The drawdowns from rsi_mr during trending markets should overlap with adx_breakout's winning periods.

**Combined Portfolio Projection:**

| Metric | 13A (2 strats) | Projected 14B (3 strats) | Basis |
|--------|---------------|-------------------------|-------|
| Return | +7.5% | +9-12% | adx_breakout adds new alpha source |
| PF | 1.309 | 1.35-1.50 | Better strategy quality + diversification |
| Max DD | 41.3% | 25-32% | rsi_mr fix + anti-correlation benefit |
| Sharpe | 0.672 | 0.80-1.00 | Lower DD + higher return |

### STRAT-5 (Quant) -- adx_breakout Design Refinements

**Pullback Proximity Filter:**

The entry condition "close within 1.5% of EMA(10)" needs precise definition:

```python
pullback = (close - ema_10) / ema_10
# For long: pullback should be small and positive OR slightly negative
# -0.015 <= pullback <= 0.005  (pulled back to or slightly below EMA10)
```

Wait -- this needs careful thought. If we require close to be ABOVE EMA(10) but within 1.5%, we miss the best pullback entries where price briefly dips below EMA(10).

**Revised pullback filter:**
- Upper bound: close <= EMA(10) * 1.005 (no more than 0.5% above EMA10 -- not extended)
- Lower bound: close >= EMA(10) * 0.985 (no more than 1.5% below EMA10 -- not collapsed)
- This captures the "kissing the moving average" pattern

**RSI Filter Rationale (40-65):**

- RSI < 40: Too oversold for a trending stock -- might be trend reversal, not pullback
- RSI > 65: Not enough of a pullback to offer good entry -- already extended
- RSI 40-65: Sweet spot where the stock has pulled back enough to offer value but not so much that the trend is broken
- This is more permissive than typical RSI-based entries because we are NOT looking for oversold conditions -- we are looking for "cooled off from overbought"

**Max Hold 7 Days:**

For a swing trading system with PDT constraints (2-5 day minimum hold):
- 7 days is appropriate for trend pullback
- Trailing stop should handle most exits before timeout
- If neither trailing stop nor TP hits in 7 days, the trend has stalled -- exit at market

**EMA Period Selection:**

EMA(10) and EMA(21) form the dual-EMA trend identification:
- EMA(10) > EMA(21) = uptrend (21 is approximately one trading month)
- 10/21 is a well-tested combination for swing trading (vs 5/20 which is too fast, or 20/50 which is too slow for our 7-day max hold)
- Cross-reference: consec_down uses EMA(50) as trend filter. These do NOT conflict because EMA(50) is a longer-term trend gauge, while EMA(10)/EMA(21) capture medium-term momentum.

### STRAT-6 (Architect) -- Final Architecture Integration

**Strategy Registration Changes:**

The system uses several parallel registries that must all be updated:

1. `batch_simulator.py`:
   - `_STRATEGY_CLASSES`: add `AdxBreakout`
   - `_STRATEGY_NAMES`: add `"adx_breakout"`
   - `_STRATEGY_BASE_RISK`: add `"adx_breakout": 0.015`
   - `_STRATEGY_GDR_THRESHOLDS`: add `"adx_breakout": (0.04, 0.08)`

2. `exit_rules.py`:
   - `_MAX_HOLD_DAYS`: add `"adx_breakout": 7`
   - `_SL_ATR_MULT`: add `"adx_breakout": {"long": 1.5}`
   - `_TP_ATR_MULT`: add `"adx_breakout": 3.0`
   - `_TRAILING_STRATEGIES`: add `"adx_breakout"` to the frozenset
   - `_TRAILING_ACTIVATION_ATR`: add `"adx_breakout": 1.0`

3. `entry_manager.py`:
   - `_GROUP_A_STRATEGIES`: add `"adx_breakout"`

4. `ranking.py`:
   - `_REGIME_COMPAT`: add `("adx_breakout", "long"): 0.85`
   - Add ADX boost logic for adx_breakout (when ADX > 30, boost compatibility)

5. `strategy_params.yaml`:
   - Add `adx_breakout` section with all parameters
   - Add to `entry_groups.moo.strategies`
   - Add to `per_strategy_gdr.base_risk`
   - Add to `per_strategy_gdr.thresholds`

6. `HeldPosition` dataclass:
   - Add `entry_adx: float = 0.0` field

**Indicator Sharing:**

adx_breakout requires: EMA(10), EMA(21), ADX(14), ATR(14), RSI(14)
rsi_mr requires: RSI(14), BBANDS(20), ADX(14), ATR(14)
consec_down requires: RSI(14), ATR(14), EMA(50), EMA(5)

Shared indicators (computed once): RSI(14), ATR(14), ADX(14)
New indicators needed: EMA(10), EMA(21)
EMA(5) and EMA(50) already registered by consec_down.

Total indicator set per symbol:
- RSI(14), ATR(14), ADX(14), BBANDS(20), EMA(5), EMA(10), EMA(21), EMA(50)
- 8 indicators. The IndicatorEngine handles this efficiently since each is computed once per bar.

---

## 2. rsi_mr Fix Recommendation

### Recommended Solution: A + B Combined (Prevention + Treatment)

**Solution A: Entry Filter Enhancement**

Change 1 -- Tighten ADX threshold:
```python
ADX_MAX = 20.0  # was 25.0
```

Change 2 -- ADX slope check (3-bar lookback):
```python
# In strategy class, add per-symbol ADX history tracking
_adx_history: dict[str, list[float]]  # stores last 4 ADX values per symbol

# In _check_entry, after ADX threshold check:
if adx >= self.ADX_MAX:
    return None

# ADX slope check: ADX must not be rising over last 3 bars
adx_hist = self._adx_history.get(symbol, [])
if len(adx_hist) >= 3 and adx > adx_hist[-3]:
    return None  # ADX is rising -- regime transition risk
```

**Solution B: Position-Level Regime Exit Guard**

In `exit_rules.py`, add `_evaluate_regime_transition()`:
```python
_REGIME_EXIT_ADX_THRESHOLD = 23.0  # exit if ADX rises above this
_REGIME_EXIT_ADX_DELTA = 3.0       # AND has risen by this many points since entry

def _evaluate_regime_transition(self, position, bar_close, indicators):
    if position.strategy != "rsi_mean_reversion":
        return _HOLD

    adx = indicators.get("ADX_14")
    if adx is None:
        return _HOLD

    # Only force exit losing positions -- profitable ones have breakeven stop
    is_losing = (
        (position.direction == "long" and bar_close < position.entry_price) or
        (position.direction == "short" and bar_close > position.entry_price)
    )

    if not is_losing:
        return _HOLD

    if adx > _REGIME_EXIT_ADX_THRESHOLD and (adx - position.entry_adx) >= _REGIME_EXIT_ADX_DELTA:
        return ExitDecision(action="exit", reason="regime_transition", target_price=bar_close)

    return _HOLD
```

Call order in `evaluate()`: Emergency -> SL -> **Regime Transition** -> TP -> Trailing -> Time

**Solution C: NOT recommended.** With ADX < 20 threshold, the 20-25 adaptive sizing zone is empty. Solution C adds complexity without benefit.

### Expected Impact

| Metric | Before Fix | After Fix (A+B) | Change |
|--------|-----------|-----------------|--------|
| Trade Count | ~98 | 60-75 | -25-35% |
| Win Rate | ~36% | 46-50% | +10-14pp |
| PF | 1.20 | 1.35-1.50 | +0.15-0.30 |
| Solo DD | 48.4% | 20-28% | -20-28pp |
| MaxCL | 19 | 7-10 | -9-12 |
| SL Rate | 64% | 45-52% | -12-19pp |
| PnL | +$3,357 | +$2,500-$3,500 | -15% to +5% |

**Indicator Requirements:**
- No new indicators needed
- ADX(14) already computed, just need to store previous values in strategy state
- entry_adx field added to HeldPosition for exit guard

---

## 3. adx_breakout Final Design

### Entry Rules

```python
class AdxBreakout(Strategy):
    name = "adx_breakout"

    # Indicator parameters
    ADX_PERIOD = 14
    ATR_PERIOD = 14
    RSI_PERIOD = 14
    EMA_FAST_PERIOD = 10
    EMA_SLOW_PERIOD = 21

    # Entry thresholds
    ADX_MIN = 25.0              # Minimum ADX for trend confirmation
    RSI_MIN = 40.0              # RSI lower bound (not oversold)
    RSI_MAX = 65.0              # RSI upper bound (not overbought)
    PULLBACK_UPPER = 0.005      # Max distance above EMA10 (0.5%)
    PULLBACK_LOWER = -0.015     # Max distance below EMA10 (-1.5%)

    # Exit parameters
    SL_ATR_MULT = 1.5
    TP_ATR_MULT = 3.0           # Hard TP cap
    MAX_HOLD_BARS = 7

    required_indicators = [
        IndicatorSpec(name="ADX", params={"period": 14}),
        IndicatorSpec(name="ATR", params={"period": 14}),
        IndicatorSpec(name="RSI", params={"period": 14}),
        IndicatorSpec(name="EMA", params={"period": 10}),
        IndicatorSpec(name="EMA", params={"period": 21}),
    ]
```

**Entry Logic:**
```python
def _check_entry(self, ctx, state, ind):
    adx = ind["adx"]
    rsi = ind["rsi"]
    ema_10 = ind["ema_10"]
    ema_21 = ind["ema_21"]
    atr = ind["atr"]
    close = ctx.bar.close

    # 1. Trend confirmation: ADX > 25
    if adx < self.ADX_MIN:
        return None

    # 2. Uptrend direction: EMA(10) > EMA(21)
    if ema_10 <= ema_21:
        return None

    # 3. RSI in pullback zone (not extended, not collapsing)
    if rsi < self.RSI_MIN or rsi > self.RSI_MAX:
        return None

    # 4. Price near EMA(10) -- pullback proximity
    pullback_pct = (close - ema_10) / ema_10
    if pullback_pct > self.PULLBACK_UPPER or pullback_pct < self.PULLBACK_LOWER:
        return None

    # 5. Signal strength: stronger ADX + deeper pullback = stronger signal
    adx_component = min(1.0, (adx - self.ADX_MIN) / 25.0)  # ADX 25-50 maps to 0-1
    pullback_component = min(1.0, abs(pullback_pct) / 0.015) if pullback_pct <= 0 else 0.3
    strength = 0.6 * adx_component + 0.4 * pullback_component

    stop_loss = close - self.SL_ATR_MULT * atr

    state.in_position = True
    state.entry_price = close
    state.bars_since_entry = 0

    return Signal(
        strategy=self.name,
        symbol=ctx.symbol,
        direction="long",
        strength=strength,
        metadata={
            "sub_strategy": "trend_pullback_long",
            "stop_loss": stop_loss,
            "entry_adx": adx,
        },
    )
```

**Exit Logic (strategy-level):**

adx_breakout does NOT have complex indicator-based exits like rsi_mr. All exits are handled by ExitRuleEngine:
- SL: 1.5 ATR (fixed)
- TP: 3.0 ATR (fixed)
- Trailing: 2.0 ATR trail, activated after 1.0 ATR favorable move
- Time: 7 days max hold

The strategy's own `_check_exit()` only handles the trend-breakdown exit:
```python
def _check_exit(self, ctx, state, ind):
    ema_10 = ind["ema_10"]
    ema_21 = ind["ema_21"]

    # Trend breakdown: EMA(10) crosses below EMA(21)
    if ema_10 < ema_21:
        state.in_position = False
        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="close",
            strength=1.0,
            metadata={"exit_reason": "trend_breakdown"},
        )

    return None
```

### Risk Parameters
```yaml
adx_breakout:
  base_risk: 0.015          # 1.5%
  sl_atr_mult_long: 1.5
  tp_atr_mult: 3.0
  max_hold_days: 7
  trailing_stop: true
  trailing_atr_mult: 2.0
  trailing_activation_atr: 1.0
  breakeven_activation_atr: 0.6
  gdr_thresholds: [0.04, 0.08]  # Tier 1 at 4%, Tier 2 at 8%
```

### Expected Performance
- Annual signals: 60-80 entries (after ranking/limits)
- Win rate: 42-50%
- Average win: 3.0-4.5% (trailing stop extends winners)
- Average loss: 1.5-2.5% (1.5 ATR SL)
- Payoff ratio: 1.5-2.0x
- Estimated PF: 1.3-1.5
- Expected solo DD: 15-25%
- Expected MaxCL: 6-10

---

## 4. Combined Architecture -- Regime Activity Matrix

| Market Regime | rsi_mr | adx_breakout | consec_down |
|---------------|--------|-------------|-------------|
| **Deep Ranging** (ADX < 15) | ACTIVE (high confidence) | INACTIVE | ACTIVE (if conditions met) |
| **Ranging** (ADX 15-20) | ACTIVE (standard) | INACTIVE | ACTIVE |
| **Transition** (ADX 20-25) | BLOCKED (new filter) | INACTIVE | ACTIVE (no ADX filter) |
| **Trending** (ADX 25-35) | BLOCKED | ACTIVE (primary zone) | ACTIVE (if above EMA50) |
| **Strong Trend** (ADX > 35) | BLOCKED | ACTIVE (strong signals) | ACTIVE (if above EMA50) |
| **High Volatility** (any ADX) | REDUCED (GDR tier may fire) | ACTIVE (if ADX > 25) | ACTIVE |

**Key observations:**
1. There is a clean hand-off between rsi_mr (ADX < 20) and adx_breakout (ADX > 25)
2. The ADX 20-25 zone is a NO-TRADE zone for both rsi_mr and adx_breakout -- this is the "dead zone" where regime is uncertain
3. consec_down operates independently of ADX -- it uses EMA(50) as its trend filter. It can trade in any regime as long as its specific conditions are met (3+ down days, above EMA50, RSI < 45)
4. In high volatility, GDR thresholds may activate and reduce activity across all strategies -- this is the portfolio safety net working as designed

**Regime Transition Scenario (the dangerous one):**

Day 1: ADX = 18, rsi_mr enters long on oversold RSI
Day 2: ADX = 20, still < 23 threshold, hold
Day 3: ADX = 22, position losing, ADX delta from entry = 4 points, above threshold
-> Regime exit guard fires, exits at market -> limited loss (2-3 bars held instead of hitting SL)

Day 4: ADX = 25, adx_breakout now eligible
Day 5: ADX = 27, EMA10 > EMA21, pullback to EMA10 -> adx_breakout enters

The system smoothly transitions from mean-reversion to trend-following as the market regime changes. This is exactly the complementary behavior we designed for.

---

## 5. Risk Parameters Table

| Parameter | rsi_mr (UPDATED) | adx_breakout (NEW) | consec_down (unchanged) |
|-----------|---------|-------------|-------------|
| Base Risk | 1.0% | 1.5% | 2.0% |
| SL (ATR) Long | 1.0 | 1.5 | 1.0 |
| SL (ATR) Short | 1.5 | N/A (long only) | N/A (long only) |
| TP (ATR) | None (indicator-based: RSI>50 or BB %B>0.50, cap 2.0 ATR) | 3.0 | None (EMA5 crossover) |
| Max Hold | 5 days | 7 days | 5 days |
| Trailing | No | Yes (2.0 ATR, activate at 1.0 ATR) | No |
| Breakeven | 0.6 ATR | 0.6 ATR | 0.6 ATR |
| GDR Tier 1 | 3% DD | 4% DD | 4% DD |
| GDR Tier 2 (HALT) | 6% DD | 8% DD | 8% DD |
| Direction | Long + Short | Long only | Long only |
| Entry Group | A (MOO) | A (MOO) | A (MOO) |
| ADX Filter | < 20 (entry) + slope check | > 25 (entry) | None |
| Regime Exit Guard | Yes (ADX > 23, delta >= 3, losing only) | No | No |

---

## 6. Implementation Spec for Dev-3

### New Files

**`autotrader/strategy/adx_breakout.py`** (NEW)
- Class: `AdxBreakout(Strategy)`
- name = `"adx_breakout"`
- required_indicators: ADX(14), ATR(14), RSI(14), EMA(10), EMA(21)
- _PositionState: in_position, entry_price, bars_since_entry
- _check_entry(): ADX > 25, EMA10 > EMA21, pullback proximity, RSI 40-65
- _check_exit(): EMA10 < EMA21 trend breakdown only
- All other exits (SL/TP/trailing/time) handled by ExitRuleEngine

### Modified Files

**`autotrader/strategy/rsi_mean_reversion.py`** -- Entry filter fix
- Add `_adx_history: dict[str, list[float]]` to `__init__`
- In `on_context()`: append current ADX to `_adx_history[symbol]`, trim to last 4 values
- Change `ADX_MAX = 25.0` to `ADX_MAX = 20.0`
- In `_check_entry()`: after ADX threshold check, add slope check:
  ```python
  ADX_SLOPE_LOOKBACK = 3
  # Check if ADX is rising over last 3 bars
  adx_hist = self._adx_history.get(symbol, [])
  if len(adx_hist) >= self.ADX_SLOPE_LOOKBACK:
      if adx > adx_hist[-self.ADX_SLOPE_LOOKBACK]:
          return None  # ADX rising, skip entry
  ```

**`autotrader/execution/exit_rules.py`** -- Regime exit guard + adx_breakout support
- Add to `HeldPosition`: `entry_adx: float = 0.0`
- Add constants:
  ```python
  _REGIME_EXIT_ADX = 23.0
  _REGIME_EXIT_DELTA = 3.0
  _REGIME_EXIT_STRATEGIES = frozenset({"rsi_mean_reversion"})
  ```
- Add `_evaluate_regime_transition()` method
- Insert call in `evaluate()` between `_evaluate_sl()` and `_evaluate_tp()`
- Add to `_MAX_HOLD_DAYS`: `"adx_breakout": 7`
- Add to `_SL_ATR_MULT`: `"adx_breakout": {"long": 1.5}`
- Add to `_TP_ATR_MULT`: `"adx_breakout": 3.0`
- Change `_TRAILING_STRATEGIES`: `frozenset({"adx_breakout"})`
- Add to `_TRAILING_ACTIVATION_ATR`: `"adx_breakout": 1.0`

**`autotrader/execution/entry_manager.py`** -- Register adx_breakout
- Add `"adx_breakout"` to `_GROUP_A_STRATEGIES`
- In `_create_held_position()`: populate `entry_adx` from `candidate.indicators.get("ADX_14", 0.0)`

**`autotrader/backtest/batch_simulator.py`** -- Register adx_breakout + fix rsi_mr
- Add `from autotrader.strategy.adx_breakout import AdxBreakout`
- Add `AdxBreakout` to `_STRATEGY_CLASSES`
- Add `"adx_breakout"` to `_STRATEGY_NAMES`
- Add `"adx_breakout": 0.015` to `_STRATEGY_BASE_RISK`
- Add `"adx_breakout": (0.04, 0.08)` to `_STRATEGY_GDR_THRESHOLDS`
- Update `_GROUP_A` to include `"adx_breakout"`
- In position creation code: populate `entry_adx` from indicators
- Update `_MAX_TOTAL_POSITIONS = 6`

**`autotrader/batch/ranking.py`** -- Ranking support
- Add `("adx_breakout", "long"): 0.85` to `_REGIME_COMPAT`
- Add ADX boost logic for adx_breakout:
  ```python
  if scan_result.strategy == "adx_breakout":
      adx = scan_result.indicators.get("ADX_14")
      if isinstance(adx, (int, float)) and adx > 30:
          boost = min(0.05, (adx - 30) / 200)
          base = min(1.0, base + boost)
  ```

**`config/strategy_params.yaml`** -- Configuration
- Add to `entry_groups.moo.strategies`: `adx_breakout`
- Add `adx_breakout` section under `strategies:`
- Add to `per_strategy_gdr.base_risk`: `adx_breakout: 0.015`
- Add to `per_strategy_gdr.thresholds`: `adx_breakout: [0.04, 0.08]`

### New Indicator Requirements
- `EMA(10)`: key = "EMA_10" -- new, registered by adx_breakout
- `EMA(21)`: key = "EMA_21" -- new, registered by adx_breakout
- All others (ADX_14, ATR_14, RSI_14, BBANDS_20, EMA_5, EMA_50) already exist

---

## 7. Sub-Test Plan

### Test 14A: Conservative (rsi_mr fix only, minimal changes)
**Purpose**: Isolate rsi_mr improvement without adx_breakout noise

Configuration:
- rsi_mr: ADX_MAX = 20.0 (tightened threshold only, NO slope check, NO regime exit guard)
- consec_down: unchanged
- adx_breakout: NOT included
- All other parameters: same as 13A

Expected:
- rsi_mr trades: 75-85 (moderate reduction)
- rsi_mr DD: 30-40% (partial improvement)
- rsi_mr MaxCL: 12-15 (partial improvement)
- Portfolio DD: 35-40%

### Test 14B: Full Implementation (rsi_mr fix + adx_breakout)
**Purpose**: Full combined system validation

Configuration:
- rsi_mr: ADX_MAX = 20.0 + ADX slope check (3-bar) + regime exit guard (ADX > 23, delta >= 3)
- consec_down: unchanged
- adx_breakout: full spec as designed above (ADX > 25, EMA10/21, RSI 40-65, trailing 2.0 ATR)
- Position limits: max_total = 6, max_long = 6, max_short = 3

Expected:
- rsi_mr trades: 60-75
- rsi_mr DD: 20-28%
- rsi_mr MaxCL: 7-10
- adx_breakout trades: 40-60
- adx_breakout PF: 1.20-1.50
- Portfolio return: 9-12%
- Portfolio DD: 25-32%
- Portfolio Sharpe: 0.80-1.00

### Test 14C: rsi_mr Full Fix Only (no adx_breakout, all rsi_mr fixes)
**Purpose**: Isolate the FULL rsi_mr fix improvement (A+B combined)

Configuration:
- rsi_mr: ADX_MAX = 20.0 + ADX slope check (3-bar) + regime exit guard
- consec_down: unchanged
- adx_breakout: NOT included
- Position limits: same as 13A

Expected:
- rsi_mr trades: 55-70
- rsi_mr DD: 20-28%
- rsi_mr MaxCL: 7-10
- Portfolio DD: 30-38%

**Comparison Logic:**
- 14C vs 13A: measures pure rsi_mr fix impact
- 14A vs 14C: measures value of slope check + regime exit (14C has both, 14A has neither)
- 14B vs 14C: measures adx_breakout's portfolio contribution

---

## 8. PASS/FAIL Criteria

### Hard PASS Requirements (all must be met)

| # | Metric | Target | Basis | Test |
|---|--------|--------|-------|------|
| P1 | rsi_mr solo DD | < 32% | From 48.4%, must halve the problem | 14B, 14C |
| P2 | rsi_mr MaxCL | <= 12 | From 19, must break clustering | 14B, 14C |
| P3 | rsi_mr PF | >= 1.10 | Must not destroy the edge | 14B, 14C |
| P4 | Portfolio DD | < 35% | From 41.3%, meaningful reduction | 14B |
| P5 | Portfolio PF | >= 1.25 | From 1.309, acceptable regression floor | 14B |
| P6 | consec_down PF | >= 1.50 | Must not regress (unchanged strategy) | All |
| P7 | All tests pass | 903+ tests | No regressions | All |
| P8 | adx_breakout trades | >= 25 | Must generate meaningful signal count | 14B |

### Soft PASS Targets (aspirational, not blocking)

| # | Metric | Target | Basis |
|---|--------|--------|-------|
| S1 | rsi_mr solo DD | < 25% | Full fix eliminates transition losses |
| S2 | rsi_mr MaxCL | <= 8 | Tight cluster prevention |
| S3 | adx_breakout PF | >= 1.30 | Competitive with consec_down |
| S4 | Portfolio Sharpe | >= 0.80 | From 0.672, meaningful improvement |
| S5 | Portfolio return | >= 9% | From 7.5%, new alpha source contributes |
| S6 | adx_breakout solo DD | < 25% | Trend strategies can have higher DD but should be contained |

### FAIL Conditions (any one triggers review)

| # | Condition | Action |
|---|-----------|--------|
| F1 | rsi_mr PF < 1.00 | ADX threshold too tight -- revert to 22 |
| F2 | rsi_mr trades < 40 | Over-filtering -- relax slope check or threshold |
| F3 | adx_breakout PF < 1.00 | Strategy design flawed -- review entry criteria |
| F4 | Portfolio DD > 40% | Strategies are correlated -- review position limits |
| F5 | consec_down performance degrades > 10% | Cross-strategy interference -- review ranking/allocation |
| F6 | adx_breakout MaxCL > 15 | Trend strategy has its own clustering -- add regime guard |

### Decision Matrix

| 14A Result | 14C Result | 14B Result | Decision |
|------------|------------|------------|----------|
| PASS | PASS | PASS | Ship 14B config (full implementation) |
| PASS | PASS | FAIL (adx_breakout) | Ship 14C config (rsi_mr fix only), debug adx_breakout |
| PASS | FAIL (over-filtered) | -- | Ship 14A config (threshold only), revisit slope/guard |
| FAIL | -- | -- | Threshold too tight, try ADX < 22 instead of 20 |

---

## Panel Consensus Summary

### Unanimous Agreement
1. The regime transition vulnerability is the **single most impactful fix** available for the portfolio
2. **Combined A+B** (prevention + treatment) is superior to either alone
3. **ADX < 20** threshold with **3-bar slope check** is the right entry filter
4. **adx_breakout** is naturally complementary and fills the trending regime gap
5. The **ADX 20-25 dead zone** is architecturally sound -- no strategy should trade in uncertain regime territory
6. **Solution C (adaptive sizing) is unnecessary** given the tighter ADX < 20 threshold
7. adx_breakout should use **ADX(14)** same as rsi_mr for clean regime hand-off

### Points of Deliberation
1. **Regime exit guard scope**: Strat-7 refined the guard to only exit LOSING positions, preserving profitable ones for the breakeven stop. Panel agreed this is correct.
2. **adx_breakout signal frequency**: Strat-4 estimates 60-80 entries/year, Strat-5 estimates 40-60. The difference is in the pullback proximity filter tightness. Will be resolved by backtest.
3. **Base risk for adx_breakout**: Strat-2 flagged that 1.5% risk can exceed the 20% position cap on expensive stocks. Panel agreed the cap is the correct binding constraint and 1.5% is the right TARGET risk.

### Implementation Priority
1. **First**: rsi_mr entry filter (ADX < 20 + slope) -- highest impact, lowest risk
2. **Second**: Regime exit guard in exit_rules.py -- defense-in-depth
3. **Third**: adx_breakout strategy implementation -- new alpha source
4. **Fourth**: Integration (ranking, entry_manager, batch_simulator, config)
5. **Fifth**: Test plan execution (14A -> 14C -> 14B sequence)

---

*Panel discussion concluded. All recommendations are consensus unless noted. Ready for Dev-3 implementation.*
