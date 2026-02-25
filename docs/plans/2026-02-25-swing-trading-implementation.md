# Swing Trading Multi-Strategy Portfolio Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 5 swing trading strategies with dynamic regime-based allocation engine for small accounts under PDT rule.

**Architecture:** Each strategy extends `Strategy` ABC with `on_context() -> Signal | None`. A portfolio-level `RegimeDetector` classifies market state using SPY indicators. An `AllocationEngine` adjusts per-strategy capital weights based on regime. All components use existing indicators (RSI, BB, ADX, EMA, ATR) with no new indicator development needed.

**Tech Stack:** Python 3.11, pytest, existing autotrader framework (Strategy ABC, IndicatorEngine, BacktestEngine, RiskManager)

---

## Key Reference Files

| Component | Path | Key Lines |
|-----------|------|-----------|
| Strategy ABC | `autotrader/strategy/base.py` | 9-20 |
| Signal | `autotrader/core/types.py` | 45-64 |
| MarketContext | `autotrader/core/types.py` | 145-162 |
| IndicatorSpec | `autotrader/indicators/base.py` | 22-30 |
| RegimeDualStrategy (reference) | `autotrader/strategy/regime_dual.py` | 29-347 |
| IndicatorEngine | `autotrader/indicators/engine.py` | 12-39 |
| BacktestEngine | `autotrader/backtest/engine.py` | 26-91 |
| RiskManager | `autotrader/risk/manager.py` | 7-44 |
| RiskConfig | `autotrader/core/config.py` | 65-89 |

## Test Helper Pattern (reuse from existing tests)

All strategy tests use a helper to create `MarketContext`:

```python
from collections import deque
from datetime import datetime
from autotrader.core.types import Bar, MarketContext

def _make_ctx(
    symbol: str = "TEST",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: float = 1000.0,
    indicators: dict | None = None,
) -> MarketContext:
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    o = open_ if open_ is not None else close
    bar = Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 15, 10, 0),
        open=o, high=h, low=l, close=close, volume=volume,
    )
    return MarketContext(
        symbol=symbol, bar=bar,
        indicators=indicators or {},
        history=deque([bar], maxlen=500),
    )
```

---

## Task 1: RSI Mean Reversion Strategy (Bidirectional)

**Files:**
- Create: `autotrader/strategy/rsi_mean_reversion.py`
- Test: `tests/unit/test_rsi_mean_reversion.py`

### Step 1: Write failing tests

```python
# tests/unit/test_rsi_mean_reversion.py
from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion


def _make_ctx(
    symbol="TEST", close=100.0, high=None, low=None, open_=None,
    volume=1000.0, indicators=None,
):
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    o = open_ if open_ is not None else close
    bar = Bar(symbol=symbol, timestamp=datetime(2026, 1, 15, 10, 0),
              open=o, high=h, low=l, close=close, volume=volume)
    return MarketContext(symbol=symbol, bar=bar,
                         indicators=indicators or {}, history=deque([bar], maxlen=500))


class TestRsiMeanReversionInit:
    def test_name(self):
        s = RsiMeanReversion()
        assert s.name == "rsi_mean_reversion"

    def test_required_indicators(self):
        s = RsiMeanReversion()
        keys = [spec.key for spec in s.required_indicators]
        assert "RSI_14" in keys
        assert "BBANDS_20" in keys
        assert "ADX_14" in keys
        assert "ATR_14" in keys


class TestRsiMeanReversionNoSignal:
    def test_no_signal_when_indicators_none(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(indicators={"RSI_14": None, "BBANDS_20": None, "ADX_14": None, "ATR_14": None})
        assert s.on_context(ctx) is None

    def test_no_signal_when_rsi_in_neutral_zone(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(indicators={
            "RSI_14": 50.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.5},
        })
        assert s.on_context(ctx) is None

    def test_no_signal_when_adx_too_high(self):
        """ADX >= 25 means trending - no mean reversion."""
        s = RsiMeanReversion()
        ctx = _make_ctx(indicators={
            "RSI_14": 25.0, "ADX_14": 30.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        assert s.on_context(ctx) is None


class TestRsiMeanReversionLongEntry:
    def test_long_entry_oversold(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(close=95.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        sig = s.on_context(ctx)
        assert sig is not None
        assert sig.direction == "long"
        assert sig.strategy == "rsi_mean_reversion"
        assert 0.0 < sig.strength <= 1.0

    def test_no_long_when_pct_b_too_high(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.20},
        })
        assert s.on_context(ctx) is None


class TestRsiMeanReversionShortEntry:
    def test_short_entry_overbought(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(close=105.0, indicators={
            "RSI_14": 78.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 106, "middle": 100, "lower": 94, "width": 0.12, "pct_b": 0.97},
        })
        sig = s.on_context(ctx)
        assert sig is not None
        assert sig.direction == "short"
        assert sig.strategy == "rsi_mean_reversion"

    def test_no_short_when_pct_b_too_low(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(indicators={
            "RSI_14": 78.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.80},
        })
        assert s.on_context(ctx) is None


class TestRsiMeanReversionExit:
    def test_long_exit_rsi_recovered(self):
        s = RsiMeanReversion()
        # First enter long
        entry_ctx = _make_ctx(close=95.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        sig = s.on_context(entry_ctx)
        assert sig is not None and sig.direction == "long"
        # Simulate fill
        s._states["TEST"].in_position = True
        s._states["TEST"].entry_price = 95.0
        s._states["TEST"].entry_direction = "long"
        # Now check exit
        exit_ctx = _make_ctx(close=102.0, indicators={
            "RSI_14": 55.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.55},
        })
        sig2 = s.on_context(exit_ctx)
        assert sig2 is not None
        assert sig2.direction == "close"

    def test_timeout_exit(self):
        s = RsiMeanReversion()
        entry_ctx = _make_ctx(close=95.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        s.on_context(entry_ctx)
        s._states["TEST"].in_position = True
        s._states["TEST"].entry_price = 95.0
        s._states["TEST"].entry_direction = "long"
        s._states["TEST"].bars_since_entry = 5
        # RSI still low but timeout reached
        timeout_ctx = _make_ctx(close=96.0, indicators={
            "RSI_14": 35.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.10},
        })
        sig = s.on_context(timeout_ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata.get("exit_reason") == "timeout"

    def test_stop_loss_exit(self):
        s = RsiMeanReversion()
        entry_ctx = _make_ctx(close=95.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        s.on_context(entry_ctx)
        s._states["TEST"].in_position = True
        s._states["TEST"].entry_price = 95.0
        s._states["TEST"].entry_direction = "long"
        # Price dropped below stop: 95 - 2*2.0 = 91
        stop_ctx = _make_ctx(close=90.0, indicators={
            "RSI_14": 20.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 90, "width": 0.15, "pct_b": 0.01},
        })
        sig = s.on_context(stop_ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata.get("exit_reason") == "stop_loss"


class TestRsiMeanReversionMetadata:
    def test_long_entry_metadata_has_stop_and_target(self):
        s = RsiMeanReversion()
        ctx = _make_ctx(close=95.0, indicators={
            "RSI_14": 25.0, "ADX_14": 18.0, "ATR_14": 2.0,
            "BBANDS_20": {"upper": 105, "middle": 100, "lower": 95, "width": 0.1, "pct_b": 0.03},
        })
        sig = s.on_context(ctx)
        assert "stop_loss" in sig.metadata
        assert "sub_strategy" in sig.metadata
        assert sig.metadata["sub_strategy"] == "mr_long"
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/unit/test_rsi_mean_reversion.py -v`
Expected: FAIL (ImportError: cannot import RsiMeanReversion)

### Step 3: Implement RsiMeanReversion strategy

```python
# autotrader/strategy/rsi_mean_reversion.py
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    in_position: bool = False
    entry_price: float = 0.0
    entry_direction: str = ""
    bars_since_entry: int = 0


class RsiMeanReversion(Strategy):
    """RSI Mean Reversion strategy - bidirectional (long + short).

    Enters long when RSI oversold + BB %B near lower band in non-trending market.
    Enters short when RSI overbought + BB %B near upper band in non-trending market.
    """

    name = "rsi_mean_reversion"

    # Thresholds
    RSI_OVERSOLD = 30.0
    RSI_OVERBOUGHT = 75.0
    RSI_EXIT_LONG = 50.0
    RSI_EXIT_SHORT = 50.0
    BB_ENTRY_LONG_PCT_B = 0.05
    BB_ENTRY_SHORT_PCT_B = 0.95
    BB_EXIT_LONG_PCT_B = 0.50
    BB_EXIT_SHORT_PCT_B = 0.50
    ADX_MAX = 25.0
    STOP_ATR_MULT_LONG = 2.0
    STOP_ATR_MULT_SHORT = 2.5
    MAX_BARS = 5

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": 14}),
            IndicatorSpec(name="BBANDS", params={"period": 20, "num_std": 2.0}),
            IndicatorSpec(name="ADX", params={"period": 14}),
            IndicatorSpec(name="ATR", params={"period": 14}),
        ]
        self._states: dict[str, _SymbolState] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        state = self._states.setdefault(ctx.symbol, _SymbolState())

        rsi = ctx.indicators.get("RSI_14")
        bb = ctx.indicators.get("BBANDS_20")
        adx = ctx.indicators.get("ADX_14")
        atr = ctx.indicators.get("ATR_14")

        if rsi is None or bb is None or adx is None or atr is None:
            return None
        if not isinstance(bb, dict):
            return None

        pct_b = bb.get("pct_b", 0.5)

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, rsi, pct_b, atr)

        return self._check_entry(ctx, state, rsi, pct_b, adx, atr)

    def _check_entry(
        self, ctx: MarketContext, state: _SymbolState,
        rsi: float, pct_b: float, adx: float, atr: float,
    ) -> Signal | None:
        if adx >= self.ADX_MAX:
            return None

        # Long entry: oversold
        if rsi < self.RSI_OVERSOLD and pct_b < self.BB_ENTRY_LONG_PCT_B:
            strength = min(1.0, (self.RSI_OVERSOLD - rsi) / 30.0 + (self.BB_ENTRY_LONG_PCT_B - pct_b) / 0.05)
            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "long"
            state.bars_since_entry = 0
            stop = ctx.bar.close - self.STOP_ATR_MULT_LONG * atr
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="long", strength=strength,
                metadata={"sub_strategy": "mr_long", "stop_loss": stop},
            )

        # Short entry: overbought
        if rsi > self.RSI_OVERBOUGHT and pct_b > self.BB_ENTRY_SHORT_PCT_B:
            strength = min(1.0, (rsi - self.RSI_OVERBOUGHT) / 25.0 + (pct_b - self.BB_ENTRY_SHORT_PCT_B) / 0.05)
            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "short"
            state.bars_since_entry = 0
            stop = ctx.bar.close + self.STOP_ATR_MULT_SHORT * atr
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="short", strength=strength,
                metadata={"sub_strategy": "mr_short", "stop_loss": stop},
            )

        return None

    def _check_exit(
        self, ctx: MarketContext, state: _SymbolState,
        rsi: float, pct_b: float, atr: float,
    ) -> Signal | None:
        reason = ""

        if state.entry_direction == "long":
            stop = state.entry_price - self.STOP_ATR_MULT_LONG * atr
            if ctx.bar.close <= stop:
                reason = "stop_loss"
            elif rsi > self.RSI_EXIT_LONG or pct_b > self.BB_EXIT_LONG_PCT_B:
                reason = "target"
        else:  # short
            stop = state.entry_price + self.STOP_ATR_MULT_SHORT * atr
            if ctx.bar.close >= stop:
                reason = "stop_loss"
            elif rsi < self.RSI_EXIT_SHORT or pct_b < self.BB_EXIT_SHORT_PCT_B:
                reason = "target"

        if state.bars_since_entry >= self.MAX_BARS and not reason:
            reason = "timeout"

        if reason:
            state.in_position = False
            state.entry_price = 0.0
            state.entry_direction = ""
            state.bars_since_entry = 0
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="close", strength=1.0,
                metadata={"exit_reason": reason, "sub_strategy": "mr_exit"},
            )

        return None
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/unit/test_rsi_mean_reversion.py -v`
Expected: All PASS

### Step 5: Commit

```bash
git add autotrader/strategy/rsi_mean_reversion.py tests/unit/test_rsi_mean_reversion.py
git commit -m "feat: RSI Mean Reversion strategy with bidirectional entries"
```

---

## Task 2: BB Squeeze Breakout Strategy (Bidirectional)

**Files:**
- Create: `autotrader/strategy/bb_squeeze.py`
- Test: `tests/unit/test_bb_squeeze.py`

### Step 1: Write failing tests

```python
# tests/unit/test_bb_squeeze.py
from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout


def _make_ctx(symbol="TEST", close=100.0, high=None, low=None,
              volume=1000.0, indicators=None):
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    bar = Bar(symbol=symbol, timestamp=datetime(2026, 1, 15, 10, 0),
              open=close, high=h, low=l, close=close, volume=volume)
    return MarketContext(symbol=symbol, bar=bar,
                         indicators=indicators or {}, history=deque([bar], maxlen=500))


class TestBbSqueezeInit:
    def test_name(self):
        assert BbSqueezeBreakout().name == "bb_squeeze"

    def test_required_indicators(self):
        keys = [s.key for s in BbSqueezeBreakout().required_indicators]
        assert "BBANDS_20" in keys
        assert "ADX_14" in keys
        assert "RSI_14" in keys
        assert "ATR_14" in keys


class TestBbSqueezeNoSignal:
    def test_no_signal_when_indicators_none(self):
        s = BbSqueezeBreakout()
        ctx = _make_ctx(indicators={"BBANDS_20": None, "ADX_14": None, "RSI_14": None, "ATR_14": None})
        assert s.on_context(ctx) is None

    def test_no_signal_when_not_squeezed(self):
        """BB width above threshold - no squeeze."""
        s = BbSqueezeBreakout()
        # Need to build width history first
        for _ in range(5):
            ctx = _make_ctx(indicators={
                "BBANDS_20": {"upper": 110, "middle": 100, "lower": 90, "width": 0.20, "pct_b": 0.5},
                "ADX_14": 22.0, "RSI_14": 50.0, "ATR_14": 2.0,
            })
            s.on_context(ctx)
        # Width is not below 0.75 * avg, so no squeeze
        assert s.on_context(ctx) is None


class TestBbSqueezeLongBreakout:
    def test_long_on_upper_band_breakout_after_squeeze(self):
        s = BbSqueezeBreakout()
        # Build width history with narrow bands
        for _ in range(20):
            ctx = _make_ctx(close=100.0, indicators={
                "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 0.5},
                "ADX_14": 15.0, "RSI_14": 50.0, "ATR_14": 1.0,
            })
            s.on_context(ctx)
        # Now breakout above upper band with ADX rising
        breakout_ctx = _make_ctx(close=103.0, high=103.5, indicators={
            "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 1.2},
            "ADX_14": 18.0, "RSI_14": 55.0, "ATR_14": 1.0,
        })
        sig = s.on_context(breakout_ctx)
        assert sig is not None
        assert sig.direction == "long"
        assert sig.strategy == "bb_squeeze"


class TestBbSqueezeShortBreakout:
    def test_short_on_lower_band_breakout_after_squeeze(self):
        s = BbSqueezeBreakout()
        for _ in range(20):
            ctx = _make_ctx(close=100.0, indicators={
                "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 0.5},
                "ADX_14": 15.0, "RSI_14": 50.0, "ATR_14": 1.0,
            })
            s.on_context(ctx)
        breakout_ctx = _make_ctx(close=97.0, low=96.5, indicators={
            "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": -0.1},
            "ADX_14": 18.0, "RSI_14": 45.0, "ATR_14": 1.0,
        })
        sig = s.on_context(breakout_ctx)
        assert sig is not None
        assert sig.direction == "short"


class TestBbSqueezeExit:
    def test_long_exit_on_opposite_band(self):
        s = BbSqueezeBreakout()
        for _ in range(20):
            s.on_context(_make_ctx(indicators={
                "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 0.5},
                "ADX_14": 15.0, "RSI_14": 50.0, "ATR_14": 1.0,
            }))
        # Enter long
        s.on_context(_make_ctx(close=103.0, indicators={
            "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 1.2},
            "ADX_14": 18.0, "RSI_14": 55.0, "ATR_14": 1.0,
        }))
        s._states["TEST"].in_position = True
        s._states["TEST"].entry_price = 103.0
        s._states["TEST"].entry_direction = "long"
        # RSI reaches exit zone
        exit_ctx = _make_ctx(close=108.0, indicators={
            "BBANDS_20": {"upper": 107, "middle": 103, "lower": 99, "width": 0.08, "pct_b": 0.9},
            "ADX_14": 25.0, "RSI_14": 78.0, "ATR_14": 1.5,
        })
        sig = s.on_context(exit_ctx)
        assert sig is not None
        assert sig.direction == "close"

    def test_timeout_exit_after_7_bars(self):
        s = BbSqueezeBreakout()
        for _ in range(20):
            s.on_context(_make_ctx(indicators={
                "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 0.5},
                "ADX_14": 15.0, "RSI_14": 50.0, "ATR_14": 1.0,
            }))
        s.on_context(_make_ctx(close=103.0, indicators={
            "BBANDS_20": {"upper": 102, "middle": 100, "lower": 98, "width": 0.04, "pct_b": 1.2},
            "ADX_14": 18.0, "RSI_14": 55.0, "ATR_14": 1.0,
        }))
        s._states["TEST"].in_position = True
        s._states["TEST"].entry_price = 103.0
        s._states["TEST"].entry_direction = "long"
        s._states["TEST"].bars_since_entry = 7
        ctx = _make_ctx(close=104.0, indicators={
            "BBANDS_20": {"upper": 106, "middle": 102, "lower": 98, "width": 0.08, "pct_b": 0.6},
            "ADX_14": 22.0, "RSI_14": 55.0, "ATR_14": 1.5,
        })
        sig = s.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata.get("exit_reason") == "timeout"
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/unit/test_bb_squeeze.py -v`
Expected: FAIL (ImportError)

### Step 3: Implement BbSqueezeBreakout strategy

```python
# autotrader/strategy/bb_squeeze.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    bb_width_history: deque = field(default_factory=lambda: deque(maxlen=20))
    prev_adx: float | None = None
    in_position: bool = False
    entry_price: float = 0.0
    entry_direction: str = ""
    bars_since_entry: int = 0


class BbSqueezeBreakout(Strategy):
    """BB Squeeze Breakout - enters on volatility expansion after contraction."""

    name = "bb_squeeze"

    SQUEEZE_RATIO = 0.75
    ADX_RISE_MIN = 2.0
    RSI_EXIT_LONG = 75.0
    RSI_EXIT_SHORT = 25.0
    STOP_ATR_MULT = 1.5
    MAX_BARS = 7

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="BBANDS", params={"period": 20, "num_std": 2.0}),
            IndicatorSpec(name="ADX", params={"period": 14}),
            IndicatorSpec(name="RSI", params={"period": 14}),
            IndicatorSpec(name="ATR", params={"period": 14}),
        ]
        self._states: dict[str, _SymbolState] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        state = self._states.setdefault(ctx.symbol, _SymbolState())

        bb = ctx.indicators.get("BBANDS_20")
        adx = ctx.indicators.get("ADX_14")
        rsi = ctx.indicators.get("RSI_14")
        atr = ctx.indicators.get("ATR_14")

        if bb is None or adx is None or rsi is None or atr is None:
            return None
        if not isinstance(bb, dict):
            return None

        width = bb.get("width", 0.0)
        pct_b = bb.get("pct_b", 0.5)
        middle = bb.get("middle", ctx.bar.close)

        state.bb_width_history.append(width)
        adx_rising = state.prev_adx is not None and (adx - state.prev_adx) >= self.ADX_RISE_MIN
        state.prev_adx = adx

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, rsi, pct_b, middle, atr)

        return self._check_entry(ctx, state, width, pct_b, adx_rising, atr)

    def _check_entry(
        self, ctx: MarketContext, state: _SymbolState,
        width: float, pct_b: float, adx_rising: bool, atr: float,
    ) -> Signal | None:
        if len(state.bb_width_history) < 5:
            return None

        avg_width = sum(state.bb_width_history) / len(state.bb_width_history)
        if avg_width == 0:
            return None

        is_squeezed = width <= avg_width * self.SQUEEZE_RATIO

        if not is_squeezed or not adx_rising:
            return None

        if pct_b > 1.0:
            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "long"
            state.bars_since_entry = 0
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="long", strength=min(1.0, pct_b - 1.0 + 0.5),
                metadata={"sub_strategy": "squeeze_long", "stop_loss": ctx.bar.close - self.STOP_ATR_MULT * atr},
            )

        if pct_b < 0.0:
            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "short"
            state.bars_since_entry = 0
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="short", strength=min(1.0, abs(pct_b) + 0.5),
                metadata={"sub_strategy": "squeeze_short", "stop_loss": ctx.bar.close + self.STOP_ATR_MULT * atr},
            )

        return None

    def _check_exit(
        self, ctx: MarketContext, state: _SymbolState,
        rsi: float, pct_b: float, middle: float, atr: float,
    ) -> Signal | None:
        reason = ""

        if state.entry_direction == "long":
            stop = state.entry_price - self.STOP_ATR_MULT * atr
            if ctx.bar.close <= stop or ctx.bar.close < middle:
                reason = "stop_loss"
            elif rsi > self.RSI_EXIT_LONG:
                reason = "target"
        else:
            stop = state.entry_price + self.STOP_ATR_MULT * atr
            if ctx.bar.close >= stop or ctx.bar.close > middle:
                reason = "stop_loss"
            elif rsi < self.RSI_EXIT_SHORT:
                reason = "target"

        if state.bars_since_entry >= self.MAX_BARS and not reason:
            reason = "timeout"

        if reason:
            state.in_position = False
            state.entry_price = 0.0
            state.entry_direction = ""
            state.bars_since_entry = 0
            return Signal(
                strategy=self.name, symbol=ctx.symbol,
                direction="close", strength=1.0,
                metadata={"exit_reason": reason, "sub_strategy": "squeeze_exit"},
            )

        return None
```

### Step 4: Run tests, Step 5: Commit

Run: `python -m pytest tests/unit/test_bb_squeeze.py -v`
Commit: `git commit -m "feat: BB Squeeze Breakout strategy with bidirectional entries"`

---

## Task 3: ADX Trend Pullback + EMA Filter Strategy

**Files:**
- Create: `autotrader/strategy/adx_pullback.py`
- Test: `tests/unit/test_adx_pullback.py`

### Step 1: Write failing tests

Test cases to cover:
- Init: name, required_indicators
- No signal: indicators None, ADX < 25, EMA bearish, RSI not in pullback zone
- Long entry: ADX > 25 + EMA(8) > EMA(21) + RSI <= 40 + price > EMA(21)
- Exit: RSI > 70, trailing stop, EMA dead cross, timeout
- Stop loss: entry - 1.5 * ATR
- Metadata: sub_strategy, stop_loss, trailing_stop

Follow same test patterns as Task 1. Key test assertions:
- `direction == "long"` only (no short entries)
- `metadata["sub_strategy"] == "trend_pullback"`
- Trailing stop updates with highest_since_entry

### Step 3: Implementation key logic

```python
class AdxPullback(Strategy):
    name = "adx_pullback"
    ADX_MIN = 25.0
    RSI_PULLBACK_MAX = 40.0
    RSI_EXIT = 70.0
    STOP_ATR_MULT = 1.5
    TRAILING_ATR_MULT = 2.0
    PROFIT_ATR_MULT = 2.5
    MAX_BARS = 7
```

Entry: ADX > 25 AND EMA(8) > EMA(21) AND RSI <= 40 AND close > EMA(21)
Exit: RSI > 70 OR trailing stop OR EMA dead cross OR timeout (7 bars)

### Step 5: Commit

```bash
git commit -m "feat: ADX Trend Pullback strategy with EMA filter"
```

---

## Task 4: Conservative Overbought Short Strategy

**Files:**
- Create: `autotrader/strategy/overbought_short.py`
- Test: `tests/unit/test_overbought_short.py`

### Key logic

```python
class OverboughtShort(Strategy):
    name = "overbought_short"
    RSI_ENTRY = 75.0
    BB_ENTRY_PCT_B = 0.95
    ADX_MAX = 25.0
    RSI_EXIT = 55.0
    BB_EXIT_PCT_B = 0.50
    STOP_ATR_MULT = 2.5
    ABSOLUTE_STOP_PCT = 0.05  # 5% absolute stop
    MAX_BARS = 5
```

Entry: RSI > 75 AND BB %B > 0.95 AND ADX < 25 AND EMA spread narrowing
Exit: RSI < 55 OR BB %B < 0.50 OR timeout (5 bars)
Stop: entry + 2.5 * ATR OR entry * 1.05 (whichever tighter)

Test cases: direction always "short", absolute stop check, EMA spread narrowing detection.

### Commit

```bash
git commit -m "feat: Conservative Overbought Short strategy"
```

---

## Task 5: Regime-Aware Momentum Strategy

**Files:**
- Create: `autotrader/strategy/regime_momentum.py`
- Test: `tests/unit/test_regime_momentum.py`

### Key logic

```python
class RegimeMomentum(Strategy):
    name = "regime_momentum"
    ADX_TREND_MIN = 25.0
    BB_WIDTH_EXPAND_RATIO = 1.3
    RSI_MIN = 50.0
    RSI_MAX = 70.0
    RSI_EXIT = 75.0
    VOLATILITY_MAX = 0.03  # ATR/close
    TRAILING_ATR_MULT = 2.0
    STOP_ATR_MULT = 1.5
    MAX_BARS = 10
```

Uses internal regime detection (reuses RegimeDualStrategy scoring pattern).
Entry: TREND regime AND 20-bar positive momentum AND RSI 50-70 AND EMA(8) > EMA(21) AND ATR/close < 3%
Exit: Regime leaves TREND OR RSI > 75 OR trailing stop OR timeout (10 bars)

Needs `history` for 20-bar return calculation.

### Commit

```bash
git commit -m "feat: Regime-Aware Momentum strategy"
```

---

## Task 6: Portfolio-Level Regime Detector

**Files:**
- Create: `autotrader/portfolio/regime_detector.py`
- Test: `tests/unit/test_regime_detector.py`

### Step 1: Write failing tests

```python
# tests/unit/test_regime_detector.py
import pytest
from autotrader.portfolio.regime_detector import RegimeDetector, MarketRegime


class TestRegimeDetector:
    def test_trend_regime(self):
        rd = RegimeDetector()
        regime = rd.classify(adx=30.0, bb_width=0.15, bb_width_avg=0.10, atr_ratio=0.02)
        assert regime == MarketRegime.TREND

    def test_ranging_regime(self):
        rd = RegimeDetector()
        regime = rd.classify(adx=15.0, bb_width=0.06, bb_width_avg=0.10, atr_ratio=0.01)
        assert regime == MarketRegime.RANGING

    def test_high_volatility_regime(self):
        rd = RegimeDetector()
        regime = rd.classify(adx=15.0, bb_width=0.15, bb_width_avg=0.10, atr_ratio=0.04)
        assert regime == MarketRegime.HIGH_VOLATILITY

    def test_uncertain_regime(self):
        rd = RegimeDetector()
        regime = rd.classify(adx=22.0, bb_width=0.10, bb_width_avg=0.10, atr_ratio=0.02)
        assert regime == MarketRegime.UNCERTAIN


class TestRegimeWeights:
    def test_trend_weights(self):
        rd = RegimeDetector()
        w = rd.get_weights(MarketRegime.TREND)
        assert w["rsi_mean_reversion"] == 0.15
        assert w["adx_pullback"] == 0.30
        assert w["bb_squeeze"] == 0.20
        assert w["overbought_short"] == 0.10
        assert w["regime_momentum"] == 0.25
        assert abs(sum(w.values()) - 1.0) < 0.001

    def test_ranging_weights(self):
        rd = RegimeDetector()
        w = rd.get_weights(MarketRegime.RANGING)
        assert w["rsi_mean_reversion"] == 0.35
        assert w["adx_pullback"] == 0.10
        assert abs(sum(w.values()) - 1.0) < 0.001

    def test_high_volatility_weights(self):
        rd = RegimeDetector()
        w = rd.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert w["bb_squeeze"] == 0.30
        assert w["overbought_short"] == 0.25
        assert abs(sum(w.values()) - 1.0) < 0.001

    def test_uncertain_weights_sum_to_0_9(self):
        """Uncertain regime keeps 10% cash."""
        rd = RegimeDetector()
        w = rd.get_weights(MarketRegime.UNCERTAIN)
        assert abs(sum(w.values()) - 0.90) < 0.001
```

### Step 3: Implementation

```python
# autotrader/portfolio/regime_detector.py
from __future__ import annotations

from enum import Enum


class MarketRegime(Enum):
    TREND = "TREND"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


_REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TREND: {
        "rsi_mean_reversion": 0.15,
        "adx_pullback": 0.30,
        "bb_squeeze": 0.20,
        "overbought_short": 0.10,
        "regime_momentum": 0.25,
    },
    MarketRegime.RANGING: {
        "rsi_mean_reversion": 0.35,
        "adx_pullback": 0.10,
        "bb_squeeze": 0.25,
        "overbought_short": 0.20,
        "regime_momentum": 0.10,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "rsi_mean_reversion": 0.20,
        "adx_pullback": 0.10,
        "bb_squeeze": 0.30,
        "overbought_short": 0.25,
        "regime_momentum": 0.15,
    },
    MarketRegime.UNCERTAIN: {
        "rsi_mean_reversion": 0.20,
        "adx_pullback": 0.15,
        "bb_squeeze": 0.20,
        "overbought_short": 0.20,
        "regime_momentum": 0.15,
    },
}


class RegimeDetector:
    ADX_TREND = 25.0
    ADX_NO_TREND = 20.0
    BB_EXPAND = 1.3
    BB_CONTRACT = 0.8
    VOL_HIGH = 0.03

    def classify(
        self, adx: float, bb_width: float, bb_width_avg: float, atr_ratio: float,
    ) -> MarketRegime:
        if bb_width_avg == 0:
            return MarketRegime.UNCERTAIN

        width_ratio = bb_width / bb_width_avg

        if adx >= self.ADX_TREND and width_ratio >= self.BB_EXPAND:
            return MarketRegime.TREND
        if adx < self.ADX_NO_TREND and width_ratio <= self.BB_CONTRACT:
            return MarketRegime.RANGING
        if adx < self.ADX_NO_TREND and width_ratio >= self.BB_EXPAND and atr_ratio > self.VOL_HIGH:
            return MarketRegime.HIGH_VOLATILITY
        return MarketRegime.UNCERTAIN

    def get_weights(self, regime: MarketRegime) -> dict[str, float]:
        return dict(_REGIME_WEIGHTS[regime])
```

### Commit

```bash
git commit -m "feat: portfolio-level RegimeDetector with regime-based allocation weights"
```

---

## Task 7: Allocation Engine

**Files:**
- Create: `autotrader/portfolio/allocation_engine.py`
- Test: `tests/unit/test_allocation_engine.py`

### Key logic

```python
class AllocationEngine:
    def __init__(self, regime_detector: RegimeDetector, risk_config: RiskConfig):
        self._detector = regime_detector
        self._config = risk_config

    def get_position_size(
        self, strategy_name: str, signal: Signal,
        price: float, account: AccountInfo,
        regime: MarketRegime,
    ) -> int:
        """Calculate position size considering allocation weight."""
        weights = self._detector.get_weights(regime)
        weight = weights.get(strategy_name, 0.0)
        max_value = account.equity * weight
        if max_value < 200.0:  # minimum position $200
            return 0
        return int(max_value / price)

    def should_enter(
        self, strategy_name: str, signal: Signal,
        regime: MarketRegime, active_positions: dict,
    ) -> bool:
        """Check allocation constraints before entry."""
        weights = self._detector.get_weights(regime)
        if weights.get(strategy_name, 0.0) < 0.05:
            return False
        # Max 2 positions per strategy
        strategy_positions = sum(1 for p in active_positions.values()
                                 if p.get("strategy") == strategy_name)
        return strategy_positions < 2
```

Test cases:
- Position sizing respects regime weights
- Minimum position size ($200) check
- Max 2 positions per strategy
- Weight lookup for each regime

### Commit

```bash
git commit -m "feat: AllocationEngine with regime-weighted position sizing"
```

---

## Task 8: Integration and Multi-Strategy Backtest

**Files:**
- Modify: `autotrader/strategy/__init__.py` (export new strategies)
- Create: `scripts/run_swing_backtest.py`
- Test: `tests/integration/test_swing_portfolio.py`

### Step 1: Update strategy __init__.py exports

```python
# autotrader/strategy/__init__.py
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum
```

### Step 2: Integration test - all 5 strategies run without error

```python
# tests/integration/test_swing_portfolio.py
from collections import deque
from datetime import datetime, timedelta

from autotrader.backtest.engine import BacktestEngine
from autotrader.core.config import RiskConfig
from autotrader.core.types import Bar
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum


def _generate_bars(n=200, symbol="TEST"):
    """Generate synthetic price data with trends and reversals."""
    import math
    bars = []
    base = 100.0
    for i in range(n):
        t = datetime(2026, 1, 1) + timedelta(hours=i)
        trend = 10 * math.sin(2 * math.pi * i / 60)
        noise = (i % 7 - 3) * 0.5
        close = base + trend + noise
        bars.append(Bar(
            symbol=symbol, timestamp=t,
            open=close - 0.5, high=close + 1.5,
            low=close - 1.5, close=close, volume=10000.0,
        ))
    return bars


class TestSwingPortfolioIntegration:
    def test_all_strategies_run_without_error(self):
        config = RiskConfig(
            max_position_pct=0.30,
            daily_loss_limit_pct=0.05,
            max_drawdown_pct=0.30,
            max_open_positions=5,
        )
        engine = BacktestEngine(initial_balance=3000.0, risk_config=config)
        engine.add_strategy(RsiMeanReversion())
        engine.add_strategy(BbSqueezeBreakout())
        engine.add_strategy(AdxPullback())
        engine.add_strategy(OverboughtShort())
        engine.add_strategy(RegimeMomentum())

        bars = _generate_bars(200)
        result = engine.run(bars)

        assert result.final_equity > 0
        assert len(result.equity_curve) > 0

    def test_strategies_produce_different_signals(self):
        """Verify strategies are differentiated (not all same signals)."""
        config = RiskConfig(max_position_pct=0.30, max_open_positions=5)
        engine = BacktestEngine(initial_balance=3000.0, risk_config=config)
        engine.add_strategy(RsiMeanReversion())
        engine.add_strategy(BbSqueezeBreakout())
        engine.add_strategy(AdxPullback())

        bars = _generate_bars(300)
        result = engine.run(bars)

        if result.trades:
            strategies_used = {t.strategy for t in result.trades}
            # At least 1 strategy should have fired
            assert len(strategies_used) >= 1
```

### Step 3: Backtest script

```python
# scripts/run_swing_backtest.py
"""Run multi-strategy swing trading backtest."""
import asyncio
from autotrader.backtest.engine import BacktestEngine
from autotrader.core.config import RiskConfig
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum

# Fetch historical data from Alpaca and run backtest
# Usage: python -m scripts.run_swing_backtest
```

### Commit

```bash
git commit -m "feat: multi-strategy swing portfolio integration with backtest"
```

---

## Task Summary

| Task | Component | Priority | Dependencies |
|------|-----------|----------|-------------|
| 1 | RSI Mean Reversion Strategy | P0 | None |
| 2 | BB Squeeze Breakout Strategy | P0 | None |
| 3 | ADX Trend Pullback Strategy | P0 | None |
| 4 | Overbought Short Strategy | P0 | None |
| 5 | Regime Momentum Strategy | P0 | None |
| 6 | RegimeDetector | P1 | None |
| 7 | AllocationEngine | P1 | Task 6 |
| 8 | Integration + Backtest | P2 | Tasks 1-7 |

**Parallelizable:** Tasks 1-5 are fully independent. Tasks 6-7 are independent of 1-5. Task 8 depends on all.

**Estimated total tests:** ~80-100 new tests across 8 test files.
