# Risk Management Specification

**Source:** Strategy Team Panel Discussion, 2026-02-27
**Status:** Approved for implementation
**Version:** 1.0

---

## Overview

This document defines the risk management rules for AutoTrader v2, covering position sizing, position limits, concentration controls, drawdown management, and a prioritized implementation roadmap. Rules apply to the live trading engine operating on a $1,000-$5,000 account with aggressive risk tolerance, trading S&P 500 stocks on daily bar signals.

---

## 1. Position Sizing

### Core Parameters

| Parameter | Value | Description |
|---|---|---|
| `RISK_PER_TRADE_PCT` | 2% | Maximum account equity at risk per trade |
| `max_position_pct` | 10% | Maximum account equity allocated to a single position |
| `SHORT_SIZE_RATIO` | 0.65 | Short positions sized at 65% of the equivalent long size |

### Sizing Formula

Position quantity is the minimum of two constraints:

```
weight_qty     = (account_equity * max_position_pct) / entry_price
risk_qty       = (account_equity * RISK_PER_TRADE_PCT) / stop_distance
final_qty      = min(weight_qty, risk_qty)
```

Where:

```
stop_distance  = abs(entry_price - signal.metadata["stop_loss"])
```

For short positions:

```
final_qty      = min(weight_qty, risk_qty) * SHORT_SIZE_RATIO
```

### Critical Fix: AllocationEngine Stop Distance

**Current defect:** `AllocationEngine` uses a hardcoded `2.0x ATR` for `stop_distance` regardless of the strategy generating the signal. This causes risk miscalculation for all strategies that use a different SL multiplier (1.5x, 2.5x).

**Required fix:** Pass the signal's actual stop-loss price into `AllocationEngine` so that `stop_distance` is computed from the real per-strategy SL level.

| Fix Component | Action Required |
|---|---|
| `Signal` object | Ensure `metadata["stop_loss"]` is populated with the absolute stop price by each strategy |
| `AllocationEngine.size_position()` | Read `stop_distance` from `abs(entry_price - signal.metadata["stop_loss"])` |
| Remove hardcoded default | Delete the `2.0 * ATR` fallback; raise an error if `stop_loss` is absent from signal metadata |

**Impact:** Without this fix, strategies with a 1.5x ATR SL (ADX Pullback, Regime Momentum) are undersized, and strategies with a 2.5x ATR SL (RSI MR, Overbought Short) are oversized relative to the 2% risk target.

---

## 2. Position Limits

| Limit | Value | Scope |
|---|---|---|
| Max simultaneous open positions | 8 | All strategies combined |
| Max positions per strategy | 2 | Per individual strategy |
| Max new entries per day | 3 | All strategies combined, resets daily |
| Max long positions | 6 | Combined across all strategies |
| Max short positions | 3 | Combined across all strategies |
| Max positions in same GICS sector | 3 | Sector concentration cap |

### Direction Limit Rationale

The long/short asymmetry (6 long, 3 short) reflects the long-term equity risk premium. S&P 500 stocks trend upward over time; short positions carry higher risk of being caught in broad market rallies. Short exposure is capped at 3 positions (37.5% of max 8) to prevent overexposure to short-squeeze and momentum reversal risk.

### Sector Concentration Rationale

Limiting any single GICS sector to 3 simultaneous positions prevents correlated drawdowns. S&P 500 sector performance is highly correlated within sectors during stress events; this cap ensures diversified exposure.

---

## 3. Drawdown Management

| Parameter | Value | Description |
|---|---|---|
| `max_drawdown_pct` | 15% | Trading halts if account drops 15% from peak equity |
| `daily_loss_limit_pct` | 2% | No new entries if daily loss reaches 2% of opening equity |
| Peak equity reset | Weekly rotation | `peak_equity` resets at the weekly rotation event |

### Drawdown Halt Behavior

When `max_drawdown_pct` is breached:
- No new entries are permitted
- Existing positions continue to be managed by normal SL/TP and exit rules
- Trading resumes after manual review and reset, or at the next weekly rotation when `peak_equity` resets

### Daily Loss Limit Behavior

When `daily_loss_limit_pct` is reached:
- No new entries for the remainder of the current trading day
- Existing positions continue to be managed normally
- Limit resets at the next market open

---

## 4. Implementation Priority

Changes are organized into three priority tiers based on risk impact and implementation urgency.

### P0 — Immediate (Critical Risk Fixes)

These items must be implemented before the next live trading session. Each represents an active risk miscalculation or missing safety mechanism.

| Item | Description | Component |
|---|---|---|
| AllocationEngine stop_distance fix | Use `signal.metadata["stop_loss"]` instead of hardcoded 2.0x ATR | `AllocationEngine` |
| Daily entry limit (max 3) | Counter checked before each order, reset at market open | `LiveTrader._signal_to_order()` |
| Same-day re-entry block | `_closed_today: set[str]` checked and populated on close | `LiveTrader` |
| Emergency stop -7% (2-bar confirm) | Streaming monitor on Day 1 positions | Streaming monitor |
| Emergency stop -10% (immediate) | Streaming monitor on Day 1 positions | Streaming monitor |

### P1 — Short-Term (Risk Parameter Corrections)

These items correct strategy parameters that deviate from panel-approved values. Implement within the next development sprint.

| Item | Current Value | Corrected Value | Component |
|---|---|---|---|
| Direction limits: max long | None | 6 | `LiveTrader` / `AllocationEngine` |
| Direction limits: max short | None | 3 | `LiveTrader` / `AllocationEngine` |
| BB Squeeze SL multiplier | 1.5x ATR | 2.0x ATR | `BBSqueezeStrategy` |
| RSI MR SL multiplier | 2.0x ATR | 2.5x ATR | `RSIMeanReversionStrategy` |
| ADX Pullback max hold | Current value | 7 days | `ADXPullbackStrategy` |
| BB Squeeze max hold | 7 days | 5 days | `BBSqueezeStrategy` |
| Overbought Short SL abs cap | None | 5% absolute cap | `OverboughtShortStrategy` |

### P2 — Medium-Term (Enhanced Controls)

These items add new capabilities not currently present in the system. Implement after P0 and P1 are complete and tested.

| Item | Description | Component |
|---|---|---|
| Sector concentration limit | Block new entries if same GICS sector already has 3 positions | `AllocationEngine` or `LiveTrader` |
| MOO vs. confirmation entry timing | Scheduler for Group A at 9:30, Group B check at 9:45 | Scheduler / `LiveTrader` |
| ATR-based supplementary TP | ATR TP calculated from entry price, evaluated on daily close | `OpenPositionTracker` |
| Pre-market gap filter | Fetch pre-market prices at 9:25 AM ET, discard if gap > 3% | `LiveTrader` |

---

## 5. Risk Parameter Summary Table

| Parameter | Value | Config Key |
|---|---|---|
| Risk per trade | 2% | `risk_per_trade_pct` |
| Max position size | 10% | `max_position_pct` |
| Short size ratio | 65% | `short_size_ratio` |
| Max open positions | 8 | `max_open_positions` |
| Max per strategy | 2 | `max_per_strategy` |
| Max daily entries | 3 | `max_daily_entries` |
| Max long positions | 6 | `max_long_positions` |
| Max short positions | 3 | `max_short_positions` |
| Max same sector | 3 | `max_same_sector` |
| Max drawdown | 15% | `max_drawdown_pct` |
| Daily loss limit | 2% | `daily_loss_limit_pct` |

All values are also defined in `config/strategy_params.yaml` under the `risk:` section.

---

## 6. Implementation Notes

- The `RISK_PER_TRADE_PCT` and `max_position_pct` limits are independent constraints; the final quantity is `min()` of both.
- Direction limits (6 long / 3 short) should be checked in `_signal_to_order()` before order submission, alongside the existing `max_open_positions` check.
- The sector concentration check requires the GICS sector classification for each symbol. This data can be sourced from the UniverseSelector's symbol metadata or a static sector mapping file.
- `peak_equity` reset on weekly rotation is already implemented; ensure the reset also clears the daily loss limit counter.
- All P0 items must have corresponding unit tests before being merged to the `development` branch.
