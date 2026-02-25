# Swing Trading Multi-Strategy Portfolio Design

## Overview

5-strategy swing trading portfolio with dynamic regime-based allocation for small accounts ($1K-$5K) under PDT rule constraints.

## Constraints

- **Capital**: $1,000-$5,000
- **PDT Rule**: No day trading (must hold overnight, 2-5 day minimum holds)
- **Risk Tolerance**: Aggressive (20-30% max drawdown)
- **Target Assets**: US individual stocks (S&P 500 components)
- **Timeframe**: Daily bars primary, 5-min bars for entry timing only
- **Existing Infrastructure**: RSI, BollingerBands, ADX, EMA, SMA, ATR all implemented

## Strategy 1: RSI Mean Reversion (Bidirectional)

**Type**: Mean Reversion | **Direction**: Long + Short | **Market**: Non-trending (ADX < 25)

### Entry (Long)
- RSI(14) < 30
- BB %B < 0.05
- ADX(14) < 25
- Limit order near previous day's low

### Entry (Short)
- RSI(14) > 75
- BB %B > 0.95
- ADX(14) < 25
- Limit order near previous day's high

### Exit
- Long: RSI > 50 OR BB %B > 0.50
- Short: RSI < 50 OR BB %B < 0.50
- Timeout: 5 days

### Stop Loss
- Long: entry - 2.0 x ATR(14)
- Short: entry + 2.5 x ATR(14)

### Indicators Required
RSI(14), BollingerBands(20, 2), ADX(14), ATR(14)

### Expected Performance
- Win rate: 62-68% (long), 55-60% (short)
- Risk/Reward: 1:1.2 (long), 1:1.0 (short)
- Holding: 2-5 days

---

## Strategy 2: ADX Trend Pullback + EMA Filter

**Type**: Trend Following | **Direction**: Long only | **Market**: Trending (ADX > 25)

### Entry
- ADX(14) > 25
- EMA(8) > EMA(21)
- RSI(14) temporarily drops to <= 40 (pullback)
- Price > EMA(21)

### Exit
- RSI > 70
- OR entry + 2.5 x ATR reached
- OR trailing stop: high - 2.0 x ATR
- OR EMA(8) < EMA(21) dead cross

### Stop Loss
- Recent swing low - 0.5 x ATR
- OR entry - 1.5 x ATR (whichever is closer)

### Indicators Required
ADX(14), EMA(8), EMA(21), RSI(14), ATR(14)

### Expected Performance
- Win rate: 55-60%
- Risk/Reward: 1:2.0
- Holding: 2-7 days

---

## Strategy 3: BB Squeeze Breakout (Bidirectional)

**Type**: Volatility Breakout | **Direction**: Long + Short | **Market**: Low vol -> High vol transition

### Entry
- BB Width <= 20-day moving average x 0.75 (squeeze confirmed)
- ADX(14) rising (current > previous by +2)
- Direction:
  - Price > BB upper: Long
  - Price < BB lower: Short

### Exit
- Opposite BB band touch
- OR RSI > 75 (long) / RSI < 25 (short)
- OR 7-day timeout

### Stop Loss
- BB middle line (SMA 20) breach
- OR entry +/- 1.5 x ATR

### Indicators Required
BollingerBands(20, 2), ADX(14), RSI(14), ATR(14)

### Expected Performance
- Win rate: 50-55%
- Risk/Reward: 1:2.0
- Holding: 2-7 days

---

## Strategy 4: Conservative Overbought Short

**Type**: Mean Reversion (Short) | **Direction**: Short only | **Market**: Overheated + weakening trend

### Entry
- RSI(14) > 75
- BB %B > 0.95
- ADX(14) < 25
- EMA(8) - EMA(21) spread narrowing (momentum fading)

### Exit
- RSI < 55
- OR BB %B < 0.50
- OR 5-day timeout

### Stop Loss
- entry + 2.5 x ATR(14)
- Absolute stop: +5% from entry (small account protection)

### Indicators Required
RSI(14), BollingerBands(20, 2), ADX(14), EMA(8), EMA(21), ATR(14)

### Expected Performance
- Win rate: 55-60%
- Risk/Reward: 1:0.9
- Holding: 2-5 days

---

## Strategy 5: Regime-Aware Momentum

**Type**: Adaptive Momentum | **Direction**: Long only | **Market**: Trend regime only

### Entry
- Regime = TREND (ADX >= 25 + BB Width expanding)
- 20-day return positive
- RSI(14) 50-70 (healthy momentum, not overheated)
- EMA(8) > EMA(21)
- ATR(14) / close < 0.03 (exclude excessively volatile stocks)

### Exit
- Regime leaves TREND (-> UNCERTAIN or MEAN_REVERSION)
- OR RSI > 75
- OR trailing stop: high - 2.0 x ATR
- OR 10-day timeout

### Stop Loss
- entry - 1.5 x ATR(14)

### Indicators Required
ADX(14), BollingerBands(20, 2), EMA(8), EMA(21), RSI(14), ATR(14)

### Expected Performance
- Win rate: 50-55%
- Risk/Reward: 1:2.5
- Holding: 3-10 days

---

## Market Regime Detection (Portfolio Level)

Uses SPY as market proxy. Evaluates weekly (Monday pre-market) + emergency triggers.

### Regime Classification

```
TREND:           ADX >= 25 AND BB_Width >= avg_20d x 1.3
RANGING:         ADX < 20  AND BB_Width <= avg_20d x 0.8
HIGH_VOLATILITY: ADX < 20  AND BB_Width >= avg_20d x 1.3 AND ATR/close > 0.03
UNCERTAIN:       Everything else
```

### Regime Scoring (reuse existing RegimeDualStrategy logic)
- ADX >= 30: +1.0 | >= 25: +0.5 | < 20: -1.0 | else: 0.0
- BB width ratio > 1.3: +0.5 | < 0.8: -0.5 | else: 0.0
- ATR/close > 0.03: volatility flag

---

## Dynamic Allocation Engine

### Base Allocation

| Strategy | Base | Min | Max | Role |
|----------|------|-----|-----|------|
| 1: RSI Mean Reversion | 25% | 15% | 35% | Core income |
| 2: ADX Trend Pullback | 20% | 10% | 30% | Trend capture |
| 3: BB Squeeze Breakout | 25% | 15% | 35% | Diversifier |
| 4: Conservative Short | 15% | 5% | 25% | Hedge |
| 5: Regime Momentum | 15% | 5% | 25% | Opportunity |

### Regime-Based Adjustment

**TREND regime:**
```
S1: 15% (-) | S2: 30% (+) | S3: 20% (=) | S4: 10% (-) | S5: 25% (+)
```

**RANGING regime:**
```
S1: 35% (+) | S2: 10% (-) | S3: 25% (=) | S4: 20% (+) | S5: 10% (-)
```

**HIGH_VOLATILITY regime:**
```
S1: 20% (=) | S2: 10% (-) | S3: 30% (+) | S4: 25% (+) | S5: 15% (=)
```

**UNCERTAIN regime:**
```
S1: 20% | S2: 15% | S3: 20% | S4: 20% | S5: 15% | Cash: 10%
```

### Rebalancing Triggers

- **Periodic**: Every Monday pre-market
- **Emergency**:
  - Portfolio drawdown > 15%: All positions 50% reduction
  - Single strategy drawdown > 10%: Strategy allocation to minimum (5%)
  - 3+ strategies simultaneous loss: Immediate regime re-evaluation
  - Overnight gap > 3%: Review position for immediate exit

---

## Position Sizing Rules

- Single position max: 30% of account
- Max concurrent positions per strategy: 2
- Total max concurrent positions: 5
- Single trade loss limit: 2% of account
- Daily loss limit: 5% of account
- Minimum position size: $200 (below this, skip entry)

### Quarter Kelly (Phase C - after 2-3 months of data)
```python
kelly_fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
actual_size = kelly_fraction * 0.25  # Quarter Kelly
```

---

## Common Execution Rules

1. **S&P 500 components only** - Liquidity and spread guarantee
2. **Daily bar signals** - 5-min bars only for entry timing
3. **Limit orders preferred** - Eliminate slippage
4. **Earnings blackout** - No new entries 2 days before earnings
5. **Correlation guard** - If 2+ strategies signal same stock, reduce each by 50%
6. **Sector cap** - Max 40% in any single sector

---

## Implementation Priority

| Order | Strategy | Rationale |
|-------|----------|-----------|
| 1 | RSI Mean Reversion | All indicators ready. High win rate for capital protection. |
| 2 | BB Squeeze Breakout | Reuses BB/ADX. Bidirectional = instant diversification with S1. |
| 3 | ADX Trend Pullback | Reuses ADX/EMA/RSI. Adds trend-following axis. |
| 4 | Conservative Short | Extends S1's short logic. Completes portfolio hedge. |
| 5 | Regime Momentum | Reuses RegimeDualStrategy regime detection. Most complex. |

After all 5 strategies: Implement Allocation Engine + Regime Detection at portfolio level.

---

## Architecture Integration

### New Components Needed
- `AllocationEngine` - Manages strategy weights based on regime
- `RegimeDetector` (portfolio level) - SPY-based market regime classification
- `PortfolioAllocator` - Position sizing with allocation weights
- 5 new Strategy subclasses

### Reused Components
- All 6 existing indicators (no new indicators needed)
- Strategy ABC and Signal/MarketContext model
- BacktestEngine for validation
- RiskManager for constraint enforcement
- IndicatorEngine for computation

### Strategy Correlation Matrix (estimated)

```
              S1       S2       S3       S4       S5
S1 RSI MR     1.00    -0.15     0.10     0.30    -0.20
S2 Pullback  -0.15     1.00     0.25    -0.30     0.45
S3 Squeeze    0.10     0.25     1.00    -0.10     0.20
S4 Short      0.30    -0.30    -0.10     1.00    -0.35
S5 Momentum  -0.20     0.45     0.20    -0.35     1.00
```

Highest correlation: S2-S5 (0.45) - mitigated by different entry timing and regime filter on S5.
Best diversifier: S3 (lowest avg correlation with all others).
Best hedge: S4 (negative correlation with trend strategies).
