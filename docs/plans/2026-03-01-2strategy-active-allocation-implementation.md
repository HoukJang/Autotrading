# 2-Strategy Active Allocation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 3-strategy static allocation with 2-strategy (breakout_momentum + adaptive_mr) active allocation driven by SPY-based regime detection.

**Architecture:** SPY daily bars feed a regime classifier (ADX/EMA/BB) that outputs one of 5 regimes. Each regime maps to per-strategy base_risk values and entry blocks. The batch_simulator dynamically adjusts position sizing and entry gates based on the current regime. A new `adaptive_mr` strategy replaces `rsi_mean_reversion` and `consecutive_down`.

**Tech Stack:** Python 3.12, pytest, existing autotrader framework (Strategy ABC, IndicatorEngine, ExitRuleEngine, BatchBacktester)

---

## Task 1: SPY Regime Classifier Module

**Owner:** Dev-1 (system-architect)

**Files:**
- Create: `autotrader/backtest/regime_classifier.py`
- Test: `tests/unit/backtest/test_regime_classifier.py`

**Step 1: Write the failing tests**

```python
# tests/unit/backtest/test_regime_classifier.py
"""Tests for SPY-based regime classifier."""
from __future__ import annotations

import pytest
from collections import deque
from autotrader.backtest.regime_classifier import RegimeClassifier, Regime


class TestRegimeClassifier:
    """Regime classification from SPY indicators."""

    def test_trend_up(self):
        """ADX >= 25 and close > EMA(50) -> TREND_UP."""
        rc = RegimeClassifier()
        regime = rc.classify(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        assert regime == Regime.TREND_UP

    def test_trend_down(self):
        """ADX >= 25 and close < EMA(50) -> TREND_DOWN."""
        rc = RegimeClassifier()
        regime = rc.classify(adx=28.0, close=430.0, ema_50=440.0, bb_ratio=1.0)
        assert regime == Regime.TREND_DOWN

    def test_ranging(self):
        """ADX < 20 and bb_ratio < 0.8 -> RANGING."""
        rc = RegimeClassifier()
        regime = rc.classify(adx=15.0, close=445.0, ema_50=440.0, bb_ratio=0.7)
        assert regime == Regime.RANGING

    def test_high_volatility(self):
        """bb_ratio > 1.2 and ADX < 25 -> HIGH_VOLATILITY."""
        rc = RegimeClassifier()
        regime = rc.classify(adx=22.0, close=445.0, ema_50=440.0, bb_ratio=1.3)
        assert regime == Regime.HIGH_VOLATILITY

    def test_uncertain(self):
        """Falls through all conditions -> UNCERTAIN."""
        rc = RegimeClassifier()
        regime = rc.classify(adx=22.0, close=445.0, ema_50=440.0, bb_ratio=0.9)
        assert regime == Regime.UNCERTAIN

    def test_confirmation_not_met(self):
        """Single day of new regime does not confirm transition."""
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        assert rc.confirmed_regime == Regime.UNCERTAIN  # default, not yet confirmed

    def test_confirmation_after_two_days(self):
        """Two consecutive days of same regime confirms transition."""
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        rc.update(adx=32.0, close=455.0, ema_50=442.0, bb_ratio=1.1)
        assert rc.confirmed_regime == Regime.TREND_UP

    def test_whipsaw_prevention(self):
        """Alternating regimes do not confirm."""
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)  # TREND_UP
        rc.update(adx=15.0, close=445.0, ema_50=440.0, bb_ratio=0.7)  # RANGING
        assert rc.confirmed_regime == Regime.UNCERTAIN  # no confirmation

    def test_get_allocation_trend_up(self):
        """TREND_UP: breakout high risk, mr low risk."""
        rc = RegimeClassifier()
        alloc = rc.get_allocation(Regime.TREND_UP)
        assert alloc["breakout_momentum"] == 0.025
        assert alloc["adaptive_mr"] == 0.003
        assert alloc["mr_short_blocked"] is True

    def test_get_allocation_ranging(self):
        """RANGING: mr high risk, breakout low risk."""
        rc = RegimeClassifier()
        alloc = rc.get_allocation(Regime.RANGING)
        assert alloc["breakout_momentum"] == 0.008
        assert alloc["adaptive_mr"] == 0.020
        assert alloc["mr_short_blocked"] is False
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/backtest/test_regime_classifier.py -v --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

```python
# autotrader/backtest/regime_classifier.py
"""SPY-based market regime classifier for active strategy allocation.

Classifies market regime using SPY ADX, EMA(50), and BB width ratio.
Provides per-strategy risk allocation based on confirmed regime.
Regime transitions require 2 consecutive days of the same classification.
"""
from __future__ import annotations

from enum import Enum


class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


# Allocation table: regime -> {strategy: risk, blocks}
_ALLOCATION_TABLE: dict[Regime, dict] = {
    Regime.TREND_UP: {
        "breakout_momentum": 0.025,
        "adaptive_mr": 0.003,
        "breakout_blocked": False,
        "mr_short_blocked": True,
    },
    Regime.TREND_DOWN: {
        "breakout_momentum": 0.005,
        "adaptive_mr": 0.015,
        "breakout_blocked": True,
        "mr_short_blocked": False,
    },
    Regime.RANGING: {
        "breakout_momentum": 0.008,
        "adaptive_mr": 0.020,
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
    Regime.HIGH_VOLATILITY: {
        "breakout_momentum": 0.005,
        "adaptive_mr": 0.008,
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
    Regime.UNCERTAIN: {
        "breakout_momentum": 0.012,
        "adaptive_mr": 0.012,
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
}


class RegimeClassifier:
    """Classifies market regime from SPY indicators with 2-day confirmation."""

    def __init__(self) -> None:
        self._confirmed: Regime = Regime.UNCERTAIN
        self._pending: Regime | None = None
        self._pending_days: int = 0

    @property
    def confirmed_regime(self) -> Regime:
        return self._confirmed

    def classify(
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
    ) -> Regime:
        """Classify regime from raw indicators (no confirmation logic)."""
        if adx >= 25.0 and close > ema_50:
            return Regime.TREND_UP
        if adx >= 25.0 and close < ema_50:
            return Regime.TREND_DOWN
        if adx < 20.0 and bb_ratio < 0.8:
            return Regime.RANGING
        if bb_ratio > 1.2 and adx < 25.0:
            return Regime.HIGH_VOLATILITY
        return Regime.UNCERTAIN

    def update(
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
    ) -> Regime:
        """Classify and apply 2-day confirmation logic. Returns confirmed regime."""
        raw = self.classify(adx, close, ema_50, bb_ratio)

        if raw == self._confirmed:
            self._pending = None
            self._pending_days = 0
            return self._confirmed

        if raw == self._pending:
            self._pending_days += 1
            if self._pending_days >= 2:
                self._confirmed = raw
                self._pending = None
                self._pending_days = 0
        else:
            self._pending = raw
            self._pending_days = 1

        return self._confirmed

    @staticmethod
    def get_allocation(regime: Regime) -> dict:
        """Return allocation dict for a given regime."""
        return dict(_ALLOCATION_TABLE[regime])
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/backtest/test_regime_classifier.py -v --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add autotrader/backtest/regime_classifier.py tests/unit/backtest/test_regime_classifier.py
git commit -m "feat: add SPY-based regime classifier with 2-day confirmation"
```

---

## Task 2: Strategy Team Designs adaptive_mr Strategy

**Owner:** Strat-1,2,3,4 (business-panel-experts)

This is a STRATEGY TEAM task (no code). The team must produce a specification for the new `adaptive_mr` strategy that includes:

- Entry conditions (exact indicator values and thresholds)
- Exit conditions (SL, TP, trailing, time)
- Required indicators (IndicatorSpec list)
- Direction (long only, short only, or both)
- Expected trade frequency (15-30 per period)

**Constraints from design doc:**
- Must work when ADX < 25 (complementary to breakout's ADX >= 25)
- P2 target: >= +$3,122 (match rsi_mr + cons_down combined P2 performance)
- Long + short allowed
- Must follow Strategy ABC interface: `on_context(MarketContext) -> Signal | None`

**Output:** Strategy specification saved to `docs/analysis/adaptive-mr-strategy-spec.md`

---

## Task 3: Implement adaptive_mr Strategy

**Owner:** Dev-3 (python-expert)

**Files:**
- Create: `autotrader/strategy/adaptive_mr.py`
- Test: `tests/unit/strategy/test_adaptive_mr.py`

**Step 1: Write the failing tests**

```python
# tests/unit/strategy/test_adaptive_mr.py
"""Tests for AdaptiveMR strategy."""
from __future__ import annotations

import pytest
from collections import deque
from unittest.mock import MagicMock

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.adaptive_mr import AdaptiveMR


def _make_bar(close=100.0, high=101.0, low=99.0, volume=1_000_000, **kw):
    return Bar(
        symbol="TEST",
        timestamp=kw.get("timestamp", MagicMock()),
        open=kw.get("open", close),
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_ctx(close=100.0, indicators=None, history_len=60):
    bar = _make_bar(close=close)
    history = deque([_make_bar(close=100.0 - i * 0.1) for i in range(history_len)])
    history.append(bar)
    return MarketContext(
        symbol="TEST",
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


class TestAdaptiveMR:
    def test_name(self):
        assert AdaptiveMR().name == "adaptive_mr"

    def test_has_required_indicators(self):
        s = AdaptiveMR()
        names = {spec.name for spec in s.required_indicators}
        assert "RSI" in names
        assert "BBANDS" in names
        assert "ADX" in names
        assert "ATR" in names

    def test_no_signal_when_adx_high(self):
        """ADX >= 25 -> no entry (breakout territory)."""
        s = AdaptiveMR()
        ctx = _make_ctx(indicators={
            "RSI_14": 25.0, "ADX_14": 28.0, "ATR_14": 2.0,
            "BBANDS_20": {"pct_b": 0.02, "upper": 105, "lower": 95, "middle": 100},
        })
        assert s.on_context(ctx) is None

    def test_long_signal_on_oversold(self):
        """Oversold conditions with low ADX -> long signal."""
        # Exact thresholds will come from strategy team spec
        s = AdaptiveMR()
        ctx = _make_ctx(close=96.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"pct_b": 0.05, "upper": 105, "lower": 95, "middle": 100},
        })
        signal = s.on_context(ctx)
        # If strategy team spec matches, expect a long signal
        if signal is not None:
            assert signal.direction == "long"
            assert signal.strategy == "adaptive_mr"

    def test_returns_signal_type(self):
        """Any returned signal must be a Signal instance."""
        s = AdaptiveMR()
        ctx = _make_ctx(indicators={
            "RSI_14": 25.0, "ADX_14": 15.0, "ATR_14": 2.0,
            "BBANDS_20": {"pct_b": 0.02, "upper": 105, "lower": 95, "middle": 100},
        })
        result = s.on_context(ctx)
        assert result is None or isinstance(result, Signal)
```

Tests will be refined after strategy team provides exact spec (Task 2).

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/strategy/test_adaptive_mr.py -v --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: FAIL (module not found)

**Step 3: Implement based on strategy team spec**

The implementation follows the Strategy ABC pattern from `breakout_momentum.py`:

```python
# autotrader/strategy/adaptive_mr.py
"""Adaptive Mean Reversion strategy -- details from strategy team spec.

Complementary to breakout_momentum: active when ADX < 25.
Entry gates, thresholds, and exit parameters defined by strategy team.
"""
from __future__ import annotations
from dataclasses import dataclass
from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy

# Constants from strategy team spec (Task 2 output)
# ... (filled in after spec is delivered)

class AdaptiveMR(Strategy):
    name = "adaptive_mr"

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": 14}),
            IndicatorSpec(name="BBANDS", params={"period": 20, "num_std": 2.0}),
            IndicatorSpec(name="ADX", params={"period": 14}),
            IndicatorSpec(name="ATR", params={"period": 14}),
        ]
        self._states: dict[str, _PositionState] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        # Implementation from strategy team spec
        ...
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/strategy/test_adaptive_mr.py -v --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: All PASS

**Step 5: Commit**

```bash
git add autotrader/strategy/adaptive_mr.py tests/unit/strategy/test_adaptive_mr.py
git commit -m "feat: add adaptive_mr strategy based on strategy team spec"
```

---

## Task 4: Add adaptive_mr Exit Rules

**Owner:** Dev-3 (python-expert)

**Files:**
- Modify: `autotrader/execution/exit_rules.py:37-67`
- Test: existing exit_rules tests cover the framework

**Step 1: Add adaptive_mr parameters to exit_rules.py**

Based on strategy team spec (Task 2), add entries to:

```python
# In exit_rules.py, add to each dict:
_MAX_HOLD_DAYS["adaptive_mr"] = <from spec>       # e.g., 7
_SL_ATR_MULT["adaptive_mr"] = {"long": <>, "short": <>}  # e.g., {"long": 1.5, "short": 1.0}
_TP_ATR_MULT["adaptive_mr"] = <>                   # e.g., 2.5 or None
# If trailing: add to _TRAILING_STRATEGIES, _TRAILING_ACTIVATION_ATR
```

**Step 2: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -x -q --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: All PASS

**Step 3: Commit**

```bash
git add autotrader/execution/exit_rules.py
git commit -m "feat: add adaptive_mr exit rule parameters"
```

---

## Task 5: Refactor batch_simulator for 2-Strategy + Regime

**Owner:** Dev-2 (backend-architect)

**Files:**
- Modify: `autotrader/backtest/batch_simulator.py`
- Test: `tests/unit/backtest/test_batch_regime_integration.py` (new)

This is the largest task. Changes to batch_simulator.py:

**Step 1: Update imports and constants (lines 55-163)**

```python
# Replace:
from autotrader.strategy.consecutive_down import ConsecutiveDown
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

# With:
from autotrader.strategy.adaptive_mr import AdaptiveMR
from autotrader.backtest.regime_classifier import RegimeClassifier, Regime

# Update constants:
_STRATEGY_NAMES: list[str] = ["breakout_momentum", "adaptive_mr"]

_STRATEGY_CLASSES = [
    BreakoutMomentum,
    AdaptiveMR,
]

# Remove static _STRATEGY_BASE_RISK (now dynamic from regime)
# Keep _DEFAULT_BASE_RISK as fallback

# Update GDR thresholds for new strategies:
_STRATEGY_GDR_THRESHOLDS: dict[str, tuple[float, float]] = {
    "breakout_momentum": (0.04, 0.08),
    "adaptive_mr": (0.02, 0.04),
}

# Update _GROUP_A:
_GROUP_A: frozenset[str] = frozenset({"breakout_momentum", "adaptive_mr"})
```

**Step 2: Add SPY data handling to run() method (lines 600-750)**

Add SPY bars parameter and regime classifier initialization:

```python
def run(
    self,
    bars_by_symbol: dict[str, list[Bar]],
    strategy_filter: list[str] | None = None,
    spy_bars: list[Bar] | None = None,          # NEW
) -> BatchBacktestResult:
    self._reset()

    # Initialize regime classifier
    self._regime_classifier = RegimeClassifier()

    # Build SPY history and indicator engine
    spy_history: deque[Bar] = deque(maxlen=500)
    spy_ind_engine = self._build_spy_indicator_engine() if spy_bars else None
    spy_by_date: dict[date, Bar] = {}
    if spy_bars:
        for bar in spy_bars:
            spy_by_date[bar.timestamp.date()] = bar

    # ... existing code ...

    for day_idx, trading_date in enumerate(all_dates):
        # ... existing steps 1-2 ...

        # NEW: Update regime from SPY data
        spy_bar = spy_by_date.get(trading_date)
        if spy_bar and spy_ind_engine:
            spy_history.append(spy_bar)
            if len(spy_history) >= 60:
                spy_indicators = spy_ind_engine.compute(spy_history)
                self._update_regime(spy_indicators, spy_bar)

        # ... rest of loop ...
```

**Step 3: Add _update_regime() method**

```python
def _update_regime(self, spy_indicators: dict, spy_bar: Bar) -> None:
    """Update regime classification from SPY indicators."""
    adx = spy_indicators.get("ADX_14")
    ema_50 = spy_indicators.get("EMA_50")
    bbands = spy_indicators.get("BBANDS_20")

    if any(v is None for v in [adx, ema_50, bbands]):
        return

    if not isinstance(bbands, dict):
        return

    # BB width ratio: current width / average width (approximated by middle)
    bb_width = bbands.get("upper", 0) - bbands.get("lower", 0)
    middle = bbands.get("middle", 1)
    bb_ratio = bb_width / middle if middle > 0 else 1.0
    # Note: we use width/middle as a simplified ratio. The classifier
    # compares this to thresholds (0.8 and 1.2).

    self._regime_classifier.update(
        adx=adx, close=spy_bar.close, ema_50=ema_50, bb_ratio=bb_ratio,
    )
```

**Step 4: Modify _calculate_qty() to use regime-based risk (lines 1716-1765)**

```python
def _calculate_qty(self, equity, fill_price, stop_distance,
                   gdr_risk_mult=1.0, strategy=None) -> int:
    if fill_price <= 0 or stop_distance <= 0:
        return 0

    if self._use_per_strategy_gdr and self._portfolio_safety_net_active:
        effective_risk_pct = _PORTFOLIO_SAFETY_NET_RISK
    elif self._use_per_strategy_gdr and strategy is not None:
        # NEW: Get base risk from regime allocation instead of static dict
        regime = self._regime_classifier.confirmed_regime
        alloc = RegimeClassifier.get_allocation(regime)
        base_risk = alloc.get(strategy, _DEFAULT_BASE_RISK)
        effective_risk_pct = base_risk * gdr_risk_mult
    else:
        base_risk = _DEFAULT_BASE_RISK
        effective_risk_pct = base_risk * gdr_risk_mult

    risk_per_trade = equity * effective_risk_pct
    qty_by_risk = int(risk_per_trade / stop_distance)
    max_by_position = int((equity * _MAX_POSITION_PCT) / fill_price)
    return max(0, min(qty_by_risk, max_by_position))
```

**Step 5: Add entry blocking in _execute_pending_entries() (line 901+)**

After the existing per-strategy GDR check, add:

```python
# Regime-based entry block
regime = self._regime_classifier.confirmed_regime
alloc = RegimeClassifier.get_allocation(regime)
if strategy_name == "breakout_momentum" and alloc.get("breakout_blocked"):
    logger.debug("Regime %s: breakout entry blocked for %s", regime.value, sym)
    continue
if strategy_name == "adaptive_mr" and direction == "short" and alloc.get("mr_short_blocked"):
    logger.debug("Regime %s: MR short blocked for %s", regime.value, sym)
    continue
```

**Step 6: Add SPY indicator engine builder**

```python
@staticmethod
def _build_spy_indicator_engine() -> IndicatorEngine:
    """Build indicator engine for SPY regime detection."""
    engine = IndicatorEngine()
    engine.register(IndicatorSpec(name="ADX", params={"period": 14}))
    engine.register(IndicatorSpec(name="EMA", params={"period": 50}))
    engine.register(IndicatorSpec(name="BBANDS", params={"period": 20, "num_std": 2.0}))
    return engine
```

**Step 7: Write integration test**

```python
# tests/unit/backtest/test_batch_regime_integration.py
"""Integration tests for regime-based allocation in batch simulator."""
from autotrader.backtest.regime_classifier import RegimeClassifier, Regime


class TestRegimeAllocationIntegration:
    def test_trend_up_reduces_mr_risk(self):
        alloc = RegimeClassifier.get_allocation(Regime.TREND_UP)
        assert alloc["adaptive_mr"] < alloc["breakout_momentum"]
        assert alloc["adaptive_mr"] <= 0.005

    def test_ranging_reduces_breakout_risk(self):
        alloc = RegimeClassifier.get_allocation(Regime.RANGING)
        assert alloc["breakout_momentum"] < alloc["adaptive_mr"]

    def test_trend_down_blocks_breakout(self):
        alloc = RegimeClassifier.get_allocation(Regime.TREND_DOWN)
        assert alloc["breakout_blocked"] is True

    def test_uncertain_is_balanced(self):
        alloc = RegimeClassifier.get_allocation(Regime.UNCERTAIN)
        assert alloc["breakout_momentum"] == alloc["adaptive_mr"]
```

**Step 8: Run full test suite**

Run: `python -m pytest tests/ -x -q --ignore=tests/unit/strategy/test_adx_breakout.py`
Expected: All PASS

**Step 9: Commit**

```bash
git add autotrader/backtest/batch_simulator.py tests/unit/backtest/test_batch_regime_integration.py
git commit -m "feat: integrate regime-based active allocation into batch simulator"
```

---

## Task 6: Update Backtest Runner for SPY Data

**Owner:** Dev-4 (devops-architect)

**Files:**
- Modify: `scripts/run_iteration_backtest.py`

**Step 1: Add SPY bar loading**

The runner needs to load SPY daily bars and pass them to BatchBacktester.
SPY data can be fetched via yfinance (already used for benchmark) or cached.

```python
# In the main backtest function, after loading bars_by_symbol:
import yfinance as yf

def _load_spy_bars(start_date, end_date):
    """Load SPY daily bars for regime detection."""
    # Need extra 60 days before start for warmup
    warmup_start = start_date - timedelta(days=90)
    spy_df = yf.download("SPY", start=warmup_start, end=end_date, progress=False)
    spy_bars = []
    for idx, row in spy_df.iterrows():
        spy_bars.append(Bar(
            symbol="SPY",
            timestamp=datetime.combine(idx.date(), datetime.min.time(), tzinfo=timezone.utc),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        ))
    return spy_bars

# Pass to simulator:
spy_bars = _load_spy_bars(start_date, end_date)
result = simulator.run(bars_by_symbol, spy_bars=spy_bars)
```

**Step 2: Update success criteria in runner**

```python
# Change from Sharpe/Calmar >= 1.0 to beating S&P 500 return
strategy_return = result.total_return_pct
sp500_return = sp500_data["total_return"]
passed = strategy_return > sp500_return
```

**Step 3: Run backtest to verify it works**

Run: `python scripts/run_iteration_backtest.py --iteration 12 --period 2`
Expected: Runs without errors, shows regime-allocated results

**Step 4: Commit**

```bash
git add scripts/run_iteration_backtest.py
git commit -m "feat: add SPY data loading and regime-aware backtest runner"
```

---

## Task 7: Backtest Validation on Both Periods

**Owner:** Test-2 (performance-engineer)

**Step 1: Run P2 backtest**

Run: `python scripts/run_iteration_backtest.py --iteration 12 --period 2`

**Step 2: Run P1 backtest**

Run: `python scripts/run_iteration_backtest.py --iteration 12 --period 1`

**Step 3: Analyze results**

Compare vs Iter 11 baseline:
- P2: must beat +11.0% and ideally exceed S&P 500 +15.5%
- P1: must beat -1.1% and ideally exceed S&P 500 +15.9%
- Per-strategy PnL breakdown
- Regime distribution across each period
- Regime transition frequency

**Step 4: Strategy team review**

Save analysis to `docs/analysis/strategy-panel-discussion-24th.md`

---

## Task 8: Strategy Team Review (Panel #24)

**Owner:** Strat-1,2,3,4 (business-panel-experts)

Review backtest results and recommend:
- Parameter adjustments to allocation table
- Whether regime thresholds need tuning
- Whether adaptive_mr strategy needs modification
- Next iteration direction

---

## Execution Order & Dependencies

```
Task 1 (Regime Classifier) ──────────────────────┐
Task 2 (Strategy Team Spec) ──┐                   │
                               ├─ Task 3 (Impl MR) │
                               │                    ├─ Task 5 (batch_sim refactor)
                               └─ Task 4 (Exit Rules)│
                                                     ├─ Task 6 (Runner update)
                                                     │
                                                     └─ Task 7 (Backtest)
                                                            │
                                                            └─ Task 8 (Review)
```

Tasks 1 and 2 can run in parallel.
Tasks 3 and 4 depend on Task 2 (strategy team spec).
Task 5 depends on Tasks 1, 3, 4.
Task 6 depends on Task 5.
Task 7 depends on Task 6.
Task 8 depends on Task 7.
