# Entry Rules Specification

**Source:** Strategy Team Panel Discussion, 2026-02-27
**Status:** Approved for implementation
**Version:** 1.0

---

## Overview

This document defines the formal entry rules for all AutoTrader v2 strategies. Rules are organized by entry group, timing, pre-market filtering, and daily limits. All times are US Eastern (ET).

---

## 1. Entry Groups

Strategies are divided into two entry groups based on execution timing and confirmation requirements.

### Group A: Market on Open (MOO) — 9:30 AM ET

Strategies in this group execute a **market order at the open** with no additional confirmation condition.

| Strategy | Entry Type | Rationale |
|---|---|---|
| RSI Mean Reversion | Market order at open | Mean reversion benefits from overnight gap extension; entry at open captures the initial reversal impulse |
| Overbought Short | Market order at open | Same rationale; extended overbought conditions from overnight holding favor immediate short entry at open |

**Execution:** Submit market orders at 9:30 AM ET on the trade day following signal generation.

---

### Group B: Confirmation Entry — 9:45 AM ET

Strategies in this group require a **price confirmation check at 9:45 AM ET** before order submission. This window accounts for early-session volatility and avoids false breakout entries.

| Strategy | Confirmation Condition | Direction |
|---|---|---|
| ADX Pullback | Current price >= previous close | Long only — confirms trend continuation |
| BB Squeeze | Price maintains breakout direction vs. previous close | Long or short — confirms breakout is holding |
| Regime Momentum | Current price >= previous close | Long only — confirms momentum is sustained |

#### Confirmation Window Rules

- **Check time:** 9:45 AM ET
- **Deadline:** 10:00 AM ET
- **Condition not met by 10:00 AM:** Signal is **DISCARDED**. It does not carry over to the next trading day.
- **No partial fills or re-attempts** after the 10:00 AM deadline.

**Rationale:** Group B strategies rely on momentum and breakout dynamics. If price has already reversed by 9:45 AM, the technical basis for the signal is invalidated. A hard discard prevents stale entries and eliminates overnight-to-morning signal decay.

---

## 2. Pre-Market Gap Filter — 9:25 AM ET

Before any entry orders are placed, a gap filter is applied to all top-ranked candidates.

### Procedure

1. At **9:25 AM ET**, fetch pre-market prices for the top 12 candidates from the nightly scan.
2. Calculate gap: `gap = (pre_market_price - previous_close) / previous_close`
3. **Discard** any candidate where `|gap| > 3%`.
4. Remaining candidates proceed to their respective entry group timing.

### Parameters

| Parameter | Value |
|---|---|
| Filter time | 9:25 AM ET |
| Gap threshold | +/- 3% from previous close |
| Candidate pool | Top 12 from nightly scan |

### Rationale

Gaps exceeding 3% on S&P 500 constituents indicate material overnight news events (earnings surprises, analyst downgrades, macro data releases, or geopolitical developments). Such gaps invalidate the technical signals that were generated on the prior session's price action. Entering on a gapped symbol introduces unmodeled risk that the strategy's stop-loss parameters do not account for.

---

## 3. Entry Window

| Parameter | Value |
|---|---|
| Window opens | 9:30 AM ET |
| Window closes | 10:00 AM ET |
| Group A execution | 9:30 AM ET (market open) |
| Group B confirmation check | 9:45 AM ET |
| Group B latest execution | 9:59 AM ET (if confirmed at 9:45) |
| No new entries after | 10:00 AM ET |

No entries of any type are permitted after 10:00 AM ET. Signals that fail confirmation or arrive after the window closes are discarded for that trading day.

---

## 4. Daily Entry Limit

**Maximum 3 new entries per day** across all strategies.

If the nightly scan generates more than 3 actionable signals, candidates are ranked by score and only the top 3 are executed. Remaining signals are discarded (not deferred to the following day).

This limit applies per calendar day in US Eastern time.

---

## 5. Signal Validity

- Signals are generated during the **8:00 PM ET nightly scan** of the S&P 500 universe (503 stocks).
- Each signal is valid for **the next trading day only**.
- Signals do not carry over. If not executed on the intended trade day (due to gap filter discard, confirmation failure, or daily limit), the signal expires.
- The nightly scan produces a ranked candidate list; the top 12 proceed to the pre-market gap filter at 9:25 AM ET the following morning.

---

## 6. Execution Flow Summary

```
8:00 PM ET   — Nightly scan runs; top 12 candidates ranked and stored
9:25 AM ET   — Pre-market gap filter applied to top 12 candidates
               Discard: |gap| > 3%
               Proceed: remaining candidates (up to 12)
9:30 AM ET   — Group A executes (RSI Mean Reversion, Overbought Short)
               Market orders submitted at open
               Daily entry counter incremented
9:45 AM ET   — Group B confirmation check (ADX Pullback, BB Squeeze, Regime Momentum)
               Pass: submit limit/market order
               Fail: signal discarded for today
10:00 AM ET  — Entry window closes
               No new entries permitted for remainder of day
End of day   — Daily entry counter reset for next session
```

---

## 7. Implementation Notes

- The pre-market gap filter requires a pre-market data feed capable of returning prices at 9:25 AM ET.
- Group A order submission must be timed to coincide with the 9:30 AM open; market orders submitted at open receive the opening print.
- Group B confirmation requires access to real-time streaming price at 9:45 AM ET (previous close is available from the nightly scan data).
- The daily entry counter (`_daily_entry_count`) must be reset at market open each day (9:30 AM ET) and must be checked before each order submission.
- A set of discarded symbols (`_discarded_today`) should be maintained to prevent re-attempts within the same session.
