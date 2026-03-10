# Strategy Panel #37: MAX_PORTFOLIO_HEAT_PCT Review

**Date**: 2026-03-09
**Status**: DECISION MADE
**Parameter**: MAX_PORTFOLIO_HEAT_PCT 0.35 -> 0.90

---

## Context

- System in SYSTEM FREEZE since Panel #34
- Live paper trading since 2026-03-03 ($100K paper balance)
- 4 open positions: MRNA, NFLX, ROST, TGT (all BM long)
- Market value: $48,104 (48.1% of equity) > 35% heat limit
- 5 nightly scan candidates (BLK, NXPI, CF, PAYX, BR) ALL blocked by heat limit
- System at 4 positions but max allowed is 9 -- severely underutilized

## Panel Analysis

### Strat-1 (Swing Trader)
- Heat rises as winning positions grow -- system punishes success
- 5 blocked candidates = direct opportunity cost
- Backtest max 3 positions may have been CAUSED by heat limit binding
- 7 layers of risk controls make heat limit redundant
- **Recommendation: 80-100%**

### Strat-2 (Quant)
- All 6 other risk controls overlap with heat limit (mathematically redundant)
- Worst case: 9 positions x 2% risk = 18% simultaneous risk at SL
- GDR triggers at 4% -- prevents reaching 9 positions under drawdown
- Safety Net at 12% halts everything
- Probability of 9 simultaneous SL hits: 0.002%
- S&P 500 overnight gap > -10%: < 0.05 events/stock/year
- **Recommendation: 90-100%**

### Strat-3 (Risk Manager)
- Correlation risk: 4 BM long positions all move together
- Gap risk bypasses SL (overnight gaps > SL distance)
- BUT: 35% is too low, and Safety Net (12%) covers tail scenarios
- Worst case (market -10% gap with 9 positions) = -10% portfolio, Safety Net triggers
- **Recommendation: 70% (most conservative)**

### Strat-4 (Analyst)
- Backtest heat limit may have been non-binding (never tested at capacity)
- Live trading week 1 already shows binding constraint
- Typical swing systems deploy 60-100% of capital
- At 90%: ~7 positions possible. At 70%: ~5-6 positions possible
- Our system at 35% is extremely conservative for large-cap long-only
- **Recommendation: 90%**

## Vote Summary

| Panelist | Recommended Value | Rationale |
|----------|------------------|-----------|
| Strat-1 | 80-100% | Redundant control, opportunity cost |
| Strat-2 | 90-100% | Mathematically redundant |
| Strat-3 | 70% | Correlation risk buffer |
| Strat-4 | 90% | Data-driven, cross-system comparison |

## Consensus Points (All Agree)

1. 35% is too restrictive -- constrains profit potential unnecessarily
2. 7 independent risk controls provide sufficient downside protection
3. Heat limit is effectively a redundant parameter in this system
4. Winning positions raising heat is a structural flaw of the metric

## SYSTEM FREEZE Override Justification

Panel #34 froze parameters because tuning no longer improved performance.
This case is different:

1. **Bug-like constraint**, not optimization -- system cannot utilize its own capacity
2. **Untested in backtest** -- heat limit never bound during Iter 23 (max 3 positions)
3. **First discovered in live** -- operational issue, not theoretical
4. **Directly limits profit** -- blocking valid signals with passing grades

## Decision

**MAX_PORTFOLIO_HEAT_PCT: 0.35 -> 0.90**

Rationale:
- 3 of 4 panelists recommend 90%+ (median of all votes ~ 90%)
- Allows 7-8 simultaneous positions (near max capacity)
- Maintains small buffer vs 100% (accommodates Strat-3 correlation concern)
- Real risk management remains with SL, GDR, Safety Net, position caps
- No other frozen parameters are changed

## Conditions

- Monitor for 2 additional weeks in paper trading
- Track: simultaneous position count, actual drawdown, heat utilization
- Panel #38 review after observation period
- Fallback: revert to 70% or 35% if problems emerge

## Risk Controls Remaining (unchanged)

1. Risk per trade: 2%
2. Position caps: BM=2, MR=3, total=9
3. Stop losses: BM 2.5 ATR, MR 2.0 ATR
4. GDR: BM (4-8%), MR (2-4%)
5. Safety Net: DD 12%, Recovery 8%
6. Max positions: 8 long, 9 total
7. PDT: 2-5 day minimum holds
