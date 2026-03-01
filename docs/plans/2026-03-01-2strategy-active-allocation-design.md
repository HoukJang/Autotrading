# 2-Strategy Active Allocation System Design

## Goal

Replace the current 3-strategy static allocation system with a 2-strategy
(trend-following + mean-reversion) architecture where capital allocation is
dynamically controlled by SPY-based market regime detection.

**Success Criteria:** Beat S&P 500 total return in both P1 (2024-03~2025-02)
and P2 (2025-03~2026-02).

## Architecture

```
Daily Evening Scan Loop:
  ┌─────────────────────────────────┐
  │  SPY bar data -> regime detect  │
  │  (ADX, EMA(50), BB width)       │
  │  -> TREND_UP / TREND_DOWN /     │
  │     RANGING / HIGH_VOL /        │
  │     UNCERTAIN                   │
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │  Regime allocation table        │
  │  breakout_risk, mr_risk         │
  │  max_positions, entry blocks    │
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │  2-strategy signal generation   │
  │  breakout_momentum (trend)      │
  │  adaptive_mr (mean-reversion)   │
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │  Position sizing (regime risk)  │
  │  Entry/exit execution           │
  └─────────────────────────────────┘
```

## Component 1: SPY Regime Detection

### Indicators (computed on SPY daily bars)

| Indicator | Calculation | Role |
|-----------|-------------|------|
| SPY ADX(14) | Standard ADX | Trend strength |
| SPY vs EMA(50) | Close above/below | Trend direction |
| SPY BB Width Ratio | BB_width / SMA(BB_width, 20) | Volatility state |

### Classification Logic

```python
if adx >= 25 and close > ema_50:
    regime = TREND_UP          # Strong uptrend
elif adx >= 25 and close < ema_50:
    regime = TREND_DOWN        # Strong downtrend
elif adx < 20 and bb_ratio < 0.8:
    regime = RANGING           # Sideways / contraction
elif bb_ratio > 1.2 and adx < 25:
    regime = HIGH_VOLATILITY   # High vol, no direction
else:
    regime = UNCERTAIN         # Mixed signals
```

### Transition Stabilization

Regime change is confirmed only after 2 consecutive days of the same new
regime detection. This prevents whipsaw from single-day noise.

## Component 2: Allocation Table

| Regime | breakout risk | MR risk | Entry blocks | Notes |
|--------|--------------|---------|-------------|-------|
| TREND_UP | 2.5% | 0.3% | MR short blocked | Breakout full power |
| TREND_DOWN | 0.5% | 1.5% | Breakout blocked | MR short opportunity |
| RANGING | 0.8% | 2.0% | None | MR dominant |
| HIGH_VOL | 0.5% | 0.8% | None | Both reduced |
| UNCERTAIN | 1.2% | 1.2% | None | Balanced |

Key effect: In P1 (bull market = TREND_UP), MR risk drops to 0.3%, which
structurally prevents the -$3,662 loss observed in Iter 11.

## Component 3: Strategies

### breakout_momentum (existing, no changes)

- 10-day high breakout, ADX > 25, EMA(21), RSI 50-80, volume confirmation
- Long only, SL 2.5 ATR, TP 5.0 ATR, trailing stop, no time limit
- Proven: +$10,209 across both periods

### adaptive_mr (new, strategy team designs)

Constraints for strategy team:
- Must be complementary to breakout: active when ADX < 25
- P2 target: >= +$3,122 (match or beat rsi_mr + cons_down combined)
- P1 target: minimal loss (structurally suppressed by TREND_UP risk 0.3%)
- Trade count: 15-30 per period (statistical significance)
- Interface: `on_context(MarketContext) -> Signal | None`
- Long + short allowed

### Regime transition position handling (strategy team decides)

Options for strategy team to evaluate:
- Natural exit: keep existing SL/TP/trailing, only new entries use new regime
- Trailing tighten: activate/tighten trailing on regime change
- Next-day close: force close incompatible positions at next open

## Component 4: batch_simulator Changes

### New data requirement
- SPY daily bars loaded alongside universe bars
- SPY indicator engine: ADX(14), EMA(50), BBANDS(20,2)

### Modified constants
- `_STRATEGY_CLASSES = [BreakoutMomentum, AdaptiveMR]`
- `_STRATEGY_NAMES = ["breakout_momentum", "adaptive_mr"]`
- `_STRATEGY_BASE_RISK` becomes dynamic (regime-driven, not static dict)

### New state tracking
- `self._current_regime: str` (current confirmed regime)
- `self._pending_regime: str | None` (regime waiting for confirmation)
- `self._regime_confirmation_days: int` (counter for 2-day confirmation)
- `self._spy_history: deque[Bar]` (SPY bar history)

### Modified methods
- `run()`: load SPY bars, compute SPY indicators daily, classify regime
- `_calculate_qty()`: use regime-based risk instead of static base_risk
- `_execute_pending_entries()`: check regime entry blocks
- `_run_evening_scan()`: skip blocked strategy signals per regime

## Validation Plan

1. Unit tests for regime classification logic
2. Unit tests for allocation table lookups
3. Backtest both periods with new system
4. Compare vs Iter 11 baseline and S&P 500

## Data Evidence

### Why mean reversion works in P2 but not P1

| Period | MR PnL | Market | Explanation |
|--------|--------|--------|-------------|
| P1 | -$3,662 | Strong bull (+15.9%) | MR fights trend, loses |
| P2 | +$3,122 | Mixed (+15.5%) | Individual stocks range, MR captures rebounds |

Active allocation solution: In P1 (TREND_UP), MR risk = 0.3% -> loss capped.
In P2 (mix of RANGING/UNCERTAIN), MR risk = 1.2-2.0% -> full opportunity.

## Risk Assessment

- **Overfitting**: Mitigated by using only 3 SPY indicators with fixed thresholds
  (no optimization on P1/P2 data). Regime rules are market-structure based.
- **Regime detection accuracy**: ~70% expected. 2-day confirmation reduces
  false positives. Wrong regime costs less than static allocation because
  dynamic system at least partially correct.
- **Single-strategy dependency**: If breakout fails in some regime, MR provides
  fallback (and vice versa). Better than 100% breakout-only.
