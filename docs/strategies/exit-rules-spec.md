# Exit Rules Specification

**Source:** Strategy Team Panel Discussion, 2026-02-27
**Status:** Approved for implementation
**Version:** 1.0

---

## Overview

This document defines the formal exit rules for all AutoTrader v2 strategies, covering stop-loss and take-profit parameters, entry day behavior, time-based forced exits, same-day re-entry restrictions, and execution mechanics. All times are US Eastern (ET). All ATR values refer to the 14-period Average True Range calculated on the daily timeframe.

---

## 1. ATR-Based Stop-Loss and Take-Profit Per Strategy

Stop-loss and take-profit levels are calculated from the **entry price** using ATR multiples. The first condition reached triggers the exit.

| Strategy | SL (ATR mult) | TP Condition | Trailing Stop | Max Hold (days) | Target R:R |
|---|---|---|---|---|---|
| RSI Mean Reversion (Long) | 2.5x ATR | RSI > 50 OR 3.0x ATR gain (first) | None | 5 | 1.5:1 |
| RSI Mean Reversion (Short) | 2.5x ATR | RSI < 50 OR 3.0x ATR gain (first) | None | 5 | 1.5:1 |
| BB Squeeze | 2.0x ATR | RSI > 75 (long) / RSI < 25 (short) OR 3.0x ATR gain (first) | None | 5 | 2.0:1 |
| ADX Pullback | 1.5x ATR (fixed) | RSI > 70 OR 2.5x ATR gain (first) | 2.0x ATR trailing | 7 | 2.0:1 |
| Overbought Short | 2.5x ATR + 5% abs cap | RSI < 55 OR pct_b < 0.50 (first) | None | 5 | 1.5:1 |
| Regime Momentum | 1.5x ATR (fixed) | RSI > 75 OR 3.0x ATR gain (first) | 2.0x ATR trailing | 7 | 2.5:1 |

### Notes on SL Calculation

- **Fixed SL** (ADX Pullback, Regime Momentum): Stop-loss price is set at entry and does not move against the position. The trailing stop only moves in the favorable direction.
- **Overbought Short absolute cap:** Stop-loss is the tighter of `2.5x ATR above entry` or `entry_price * 1.05`. This caps catastrophic loss on a short squeeze scenario.
- **Trailing stop activation:** For ADX Pullback and Regime Momentum, the trailing stop activates immediately on Day 2 (after the entry day skip). The trailing stop replaces the fixed SL once the position moves favorably by at least 1.0x ATR.

### TP Priority

When both RSI and ATR TP conditions are active, whichever is triggered first on the daily close governs exit. Intraday TP targets are not evaluated; exits execute on the next morning's open following a daily close trigger.

---

## 2. Entry Day Skip Rule

### Behavior

- **Day 1 (entry day):** Normal SL/TP checks are **suspended**. Only emergency stop-loss applies.
- **Day 2 onward:** Normal SL/TP activates. All levels are calculated from the **entry price**, not from the previous close.

### Emergency Stop-Loss (Day 1 Only)

Two emergency thresholds are monitored intraday via the 1-minute streaming feed:

| Threshold | Trigger | Execution |
|---|---|---|
| -7% from entry price (long) / +7% (short) | 2 consecutive 1-minute bars both confirm the breach | Execute market order after 2nd confirming bar |
| -10% from entry price (long) / +10% (short) | Any single 1-minute bar breaches threshold | Execute market order immediately (1 bar) |

The 2-bar confirmation on the -7% threshold reduces false triggers from intraday wicks. The -10% immediate exit prevents catastrophic single-session loss with no confirmation delay.

### Rationale

Historical analysis of this strategy set indicates approximately 70% of premature stop-outs occur on the entry day due to intraday noise around the open. Daily signals with 2-5 day intended hold periods are not designed to withstand intraday volatility. Additionally, executing a same-day close would constitute a pattern day trade (PDT rule), which must be avoided given the account size constraints. Suspending normal SL on Day 1 directly addresses both concerns.

---

## 3. Time-Based Forced Exit

When neither SL nor TP is triggered, positions are force-closed at the open of the trading day following the maximum hold period.

| Strategy Group | Max Hold (days) | Exit Mechanism | Rationale |
|---|---|---|---|
| RSI Mean Reversion | 5 days | Time-based forced exit | Signal decay analysis shows mean reversion edge peaks Day 2-3 and drops sharply after Day 5 |
| Overbought Short | 5 days | Time-based forced exit | Same mean reversion decay pattern as RSI MR |
| BB Squeeze | 5 days | Time-based forced exit | Reduced from 7 days; breakout signal information decays significantly after Day 5 |
| ADX Pullback | 7 days | Safety net; trailing stop is primary exit | Trend-following strategies can run longer; trailing stop handles normal exits |
| Regime Momentum | 7 days | Safety net; trailing stop is primary exit | Same rationale as ADX Pullback |

### Day Count Convention

- Day 1 = entry day (market open when position is established)
- Day count increments at each daily close
- Force exit executes at the open of Day N+1 (e.g., a 5-day hold force-closes at the open of Day 6)

---

## 4. No Same-Day Re-Entry After Exit

Once a position in a symbol is closed during a trading day, that symbol is **blocked from any new entry for the remainder of that calendar day**.

### Scope

| Dimension | Rule |
|---|---|
| Direction | Both long and short blocked |
| Strategy | All strategies blocked (cross-strategy restriction) |
| Time basis | US Eastern calendar date |
| Reset | Daily at market open (9:30 AM ET) |
| Next day | Re-entry allowed if a new signal is generated |

**Example:** If ADX Pullback closes a long position in AAPL at 11:00 AM ET, RSI Mean Reversion cannot open a short position in AAPL later the same day, even if a valid signal exists.

### Implementation

Maintain a set `_closed_today: set[str]` containing symbols closed during the current session. Check this set before any order submission. Clear the set at the daily market open.

---

## 5. SL/TP Execution Mechanics

### Hybrid Execution Model

SL and TP orders use a hybrid approach combining broker-side stop orders with real-time streaming monitoring:

| Layer | Mechanism | Purpose |
|---|---|---|
| Primary precision | Real-time 1-minute streaming monitor | Detects exact breach timing; handles indicator-based TP (RSI, pct_b) |
| Safety net | Alpaca stop orders (submitted at position open on Day 2) | Ensures execution even if streaming monitor has a connectivity gap |

### Trailing Stop Implementation

- Applicable strategies: ADX Pullback, Regime Momentum
- Trailing stop is **not** implemented via Alpaca trailing stop orders (they do not allow ATR-based distance)
- Instead: the streaming monitor updates the trailing stop price on each daily close
- The initial trailing stop is set at `entry_price - (2.0 * ATR)` for longs and moves up as price makes new highs
- The Alpaca stop order (safety net) is updated to the new trailing level after each favorable close

### Mean Reversion Strategies: No Trailing Stop

RSI Mean Reversion, Overbought Short, and BB Squeeze do not use trailing stops. The 2-5 day intended hold is too short for trailing stop mechanics to add value; a fixed TP target and time-based exit are sufficient for these strategies.

---

## 6. Exit Decision Hierarchy

The following priority order governs which exit rule triggers first (highest priority listed first):

1. **Emergency stop-loss** (Day 1 only): -10% immediate, -7% after 2 confirming bars
2. **Stop-loss** (Day 2+): ATR-based fixed or trailing, calculated from entry price
3. **Take-profit** (Day 2+): Indicator-based (RSI, pct_b) or ATR-based, first condition met
4. **Time-based forced exit**: Max hold days reached, execute at next open
5. **Regime-based forced exit**: Position incompatible with new regime (handled by RegimePositionReviewer)
6. **Rotation forced exit**: Weekly rotation or event-driven rotation (handled by RotationManager)

---

## 7. Implementation Notes

- All SL/TP levels must be stored per position in the `OpenPositionTracker` metadata at the time of entry on Day 2.
- On Day 1, the streaming monitor watches only the emergency thresholds (-7% with 2-bar confirm, -10% immediate).
- The streaming monitor must distinguish between Day 1 and Day 2+ using the position entry date (US Eastern calendar date).
- `_closed_today` must be checked in `_signal_to_order()` before order submission and populated in the position close callback.
- Time-based forced exits should be queued at the daily scan (8:00 PM ET) to execute at the following open, not intraday.
