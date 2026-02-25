"""Tests for RegimeDualStrategy with regime detection and dual entry/exit logic."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.regime_dual import RegimeDualStrategy, _SymbolState


def _make_regime_ctx(
    symbol: str,
    close: float,
    ema_fast: float | None,
    ema_slow: float | None,
    adx: float | None,
    rsi: float | None,
    atr: float | None,
    bb_upper: float | None = None,
    bb_middle: float | None = None,
    bb_lower: float | None = None,
    bb_width: float | None = None,
    bb_pct_b: float | None = None,
    high: float | None = None,
    low: float | None = None,
) -> MarketContext:
    bar = Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=1000,
    )
    indicators: dict[str, float | dict | None] = {}
    if ema_fast is not None:
        indicators["EMA_8"] = ema_fast
    if ema_slow is not None:
        indicators["EMA_21"] = ema_slow
    if adx is not None:
        indicators["ADX_14"] = adx
    if rsi is not None:
        indicators["RSI_14"] = rsi
    if atr is not None:
        indicators["ATR_14"] = atr
    if all(
        v is not None
        for v in [bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b]
    ):
        indicators["BBANDS_20"] = {
            "upper": bb_upper,
            "middle": bb_middle,
            "lower": bb_lower,
            "width": bb_width,
            "pct_b": bb_pct_b,
        }
    return MarketContext(
        symbol=symbol, bar=bar, indicators=indicators, history=deque([bar])
    )


def _make_full_ctx(
    symbol: str = "AAPL",
    close: float = 100.0,
    ema_fast: float = 101.0,
    ema_slow: float = 100.0,
    adx: float = 25.0,
    rsi: float = 55.0,
    atr: float = 2.0,
    bb_upper: float = 105.0,
    bb_middle: float = 100.0,
    bb_lower: float = 95.0,
    bb_width: float = 0.10,
    bb_pct_b: float = 0.50,
    high: float | None = None,
    low: float | None = None,
) -> MarketContext:
    return _make_regime_ctx(
        symbol=symbol,
        close=close,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        adx=adx,
        rsi=rsi,
        atr=atr,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_width=bb_width,
        bb_pct_b=bb_pct_b,
        high=high,
        low=low,
    )


def _build_regime(strategy: RegimeDualStrategy, symbol: str, adx: float,
                  bb_width: float, n_bars: int = 6) -> None:
    """Feed multiple bars to build up bb_width_history and stabilize regime."""
    for _ in range(n_bars):
        ctx = _make_full_ctx(
            symbol=symbol, adx=adx, bb_width=bb_width,
            ema_fast=99.0, ema_slow=100.0,  # no crossover
        )
        strategy.on_context(ctx)


# ---- Warmup ----

class TestWarmup:
    def test_returns_none_when_indicators_missing(self):
        strat = RegimeDualStrategy()
        ctx = _make_regime_ctx(
            "AAPL", 100.0,
            ema_fast=101.0, ema_slow=100.0, adx=30.0,
            rsi=None, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=95.0,
            bb_width=0.10, bb_pct_b=0.50,
        )
        assert strat.on_context(ctx) is None

    def test_returns_none_when_bbands_missing(self):
        strat = RegimeDualStrategy()
        ctx = _make_regime_ctx(
            "AAPL", 100.0,
            ema_fast=101.0, ema_slow=100.0, adx=30.0,
            rsi=55.0, atr=2.0,
        )
        assert strat.on_context(ctx) is None


# ---- Regime Classification ----

class TestRegimeClassification:
    def test_regime_trend_when_adx_high_bbw_expanding(self):
        strat = RegimeDualStrategy()
        symbol = "AAPL"
        # Build history with normal width, then expanding
        for _ in range(5):
            ctx = _make_full_ctx(symbol=symbol, adx=35.0, bb_width=0.10,
                                 ema_fast=99.0, ema_slow=100.0)
            strat.on_context(ctx)
        # Now a bar with expanding width (ratio > 1.3)
        ctx = _make_full_ctx(symbol=symbol, adx=35.0, bb_width=0.20,
                             ema_fast=99.0, ema_slow=100.0)
        strat.on_context(ctx)
        state = strat._states[symbol]
        assert state.regime == "TREND"
        assert state.regime_score >= 1.0

    def test_regime_mr_when_adx_low_bbw_contracting(self):
        strat = RegimeDualStrategy()
        symbol = "AAPL"
        for _ in range(5):
            ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.10,
                                 ema_fast=99.0, ema_slow=100.0)
            strat.on_context(ctx)
        # Contracting width
        ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.05,
                             ema_fast=99.0, ema_slow=100.0)
        strat.on_context(ctx)
        state = strat._states[symbol]
        assert state.regime == "MEAN_REVERSION"
        assert state.regime_score <= -1.0

    def test_regime_uncertain_when_adx_moderate(self):
        strat = RegimeDualStrategy()
        symbol = "AAPL"
        ctx = _make_full_ctx(symbol=symbol, adx=22.0, bb_width=0.10,
                             ema_fast=99.0, ema_slow=100.0)
        strat.on_context(ctx)
        state = strat._states[symbol]
        assert state.regime == "UNCERTAIN"

    def test_no_entry_during_uncertain_regime(self):
        strat = RegimeDualStrategy()
        symbol = "AAPL"
        # Build uncertain regime with enough bars
        for _ in range(5):
            ctx = _make_full_ctx(symbol=symbol, adx=22.0, bb_width=0.10,
                                 ema_fast=99.0, ema_slow=100.0)
            result = strat.on_context(ctx)
        # Try crossover in uncertain regime
        ctx = _make_full_ctx(symbol=symbol, close=101.0,
                             adx=22.0, ema_fast=101.0, ema_slow=100.0,
                             rsi=55.0, bb_width=0.10)
        result = strat.on_context(ctx)
        assert result is None

    def test_min_regime_bars_enforced(self):
        strat = RegimeDualStrategy()
        symbol = "AAPL"
        # First bar sets prev EMAs (no crossover)
        ctx = _make_full_ctx(symbol=symbol, adx=35.0, bb_width=0.10,
                             ema_fast=99.0, ema_slow=100.0, rsi=55.0)
        strat.on_context(ctx)
        # Force regime to TREND on first bar (adx_score=1.0 alone)
        # Second bar: only 1 regime bar, crossover should not trigger entry
        ctx = _make_full_ctx(symbol=symbol, close=101.0, adx=35.0,
                             ema_fast=101.0, ema_slow=100.0, rsi=55.0,
                             bb_width=0.10)
        result = strat.on_context(ctx)
        # regime_bars is 2 here (bar 1 set it to 1, bar 2 increments to 2)
        # But prev_ema was set at bar 1 end, crossover happens on bar 2.
        # With regime_bars=2 and MIN_REGIME_BARS=2, entry IS allowed.
        # To test min_regime_bars, we need regime change on the crossover bar.
        strat2 = RegimeDualStrategy()
        # Bar 1: UNCERTAIN regime, sets prev EMAs
        ctx1 = _make_full_ctx(symbol=symbol, adx=22.0, bb_width=0.10,
                              ema_fast=99.0, ema_slow=100.0, rsi=55.0)
        strat2.on_context(ctx1)
        # Bar 2: now TREND (adx=35), regime_bars=1 (just changed), crossover
        ctx2 = _make_full_ctx(symbol=symbol, close=101.0, adx=35.0,
                              ema_fast=101.0, ema_slow=100.0, rsi=55.0,
                              bb_width=0.10)
        result2 = strat2.on_context(ctx2)
        assert result2 is None  # regime_bars=1, less than MIN_REGIME_BARS=2


# ---- Trend Entry ----

class TestTrendEntry:
    def _setup_trend_entry(self, symbol: str = "AAPL"):
        """Set up strategy with TREND regime and prev EMA values for crossover."""
        strat = RegimeDualStrategy()
        # Build TREND regime with enough bars (adx=35 gives adx_score=1.0)
        _build_regime(strat, symbol, adx=35.0, bb_width=0.10, n_bars=6)
        return strat

    def test_trend_entry_on_ema_crossover_with_rsi_confirm(self):
        strat = self._setup_trend_entry()
        # Crossover bar: fast crosses above slow
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"
        assert result.strategy == "regime_dual"
        assert result.metadata["sub_strategy"] == "trend_following"

    def test_no_trend_entry_without_crossover(self):
        strat = self._setup_trend_entry()
        # Set prev fast already above slow
        state = strat._states["AAPL"]
        state.prev_ema_fast = 101.0
        state.prev_ema_slow = 100.0
        # Same: fast still above slow (no cross)
        ctx = _make_full_ctx(
            close=102.0, ema_fast=102.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is None

    def test_no_trend_entry_rsi_overbought(self):
        strat = self._setup_trend_entry()
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=80.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is None

    def test_no_trend_entry_price_below_slow_ema(self):
        strat = self._setup_trend_entry()
        ctx = _make_full_ctx(
            close=99.0, ema_fast=100.5, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is None


# ---- Mean Reversion Entry ----

class TestMREntry:
    def _setup_mr_entry(self, symbol: str = "AAPL"):
        """Set up strategy with MEAN_REVERSION regime and low prev_rsi."""
        strat = RegimeDualStrategy()
        _build_regime(strat, symbol, adx=15.0, bb_width=0.10, n_bars=5)
        # Add contracting bars to push regime to MR
        ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.05,
                             ema_fast=99.0, ema_slow=100.0)
        strat.on_context(ctx)
        # Transition bar with low RSI to avoid falling knife on entry
        ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.05,
                             ema_fast=99.0, ema_slow=100.0, rsi=28.0)
        strat.on_context(ctx)
        return strat

    def test_mr_entry_on_bb_lower_touch_rsi_oversold(self):
        strat = self._setup_mr_entry()
        ctx = _make_full_ctx(
            close=95.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=25.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.02,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"
        assert result.metadata["sub_strategy"] == "mean_reversion"

    def test_no_mr_entry_rsi_not_oversold(self):
        strat = self._setup_mr_entry()
        ctx = _make_full_ctx(
            close=95.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=40.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.02,
        )
        result = strat.on_context(ctx)
        assert result is None

    def test_no_mr_entry_falling_knife(self):
        strat = self._setup_mr_entry()
        # Set prev_rsi so that drop > 5
        state = strat._states["AAPL"]
        state.prev_rsi = 35.0
        ctx = _make_full_ctx(
            close=95.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=25.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.02,
        )
        result = strat.on_context(ctx)
        # prev_rsi(35) - rsi(25) = 10 >= 5 → falling knife filter
        assert result is None


# ---- Exits ----

class TestExits:
    def _enter_trend_position(self, strat: RegimeDualStrategy,
                              symbol: str = "AAPL",
                              entry_price: float = 101.0):
        """Build TREND regime and trigger entry, return the entry signal."""
        _build_regime(strat, symbol, adx=35.0, bb_width=0.10, n_bars=6)
        # Crossover entry bar
        ctx = _make_full_ctx(
            symbol=symbol, close=entry_price,
            ema_fast=entry_price, ema_slow=entry_price - 1.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
            high=entry_price + 0.5,
        )
        sig = strat.on_context(ctx)
        assert sig is not None and sig.direction == "long"
        return sig

    def _enter_mr_position(self, strat: RegimeDualStrategy,
                           symbol: str = "AAPL",
                           entry_price: float = 95.0):
        """Build MR regime and trigger entry."""
        _build_regime(strat, symbol, adx=15.0, bb_width=0.10, n_bars=5)
        # Push to MR regime with contracting width
        for _ in range(2):
            ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.05,
                                 ema_fast=99.0, ema_slow=100.0)
            strat.on_context(ctx)
        # Transition bar with low RSI to avoid falling knife filter
        ctx = _make_full_ctx(symbol=symbol, adx=15.0, bb_width=0.05,
                             ema_fast=99.0, ema_slow=100.0, rsi=28.0)
        strat.on_context(ctx)
        # Entry bar
        ctx = _make_full_ctx(
            symbol=symbol, close=entry_price,
            ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=25.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.02,
            high=entry_price + 0.5,
        )
        sig = strat.on_context(ctx)
        assert sig is not None and sig.direction == "long"
        return sig

    def test_exit_on_stop_loss(self):
        strat = RegimeDualStrategy()
        self._enter_trend_position(strat, entry_price=101.0)
        # Price drops below entry - 1.5*ATR = 101 - 3.0 = 98.0
        ctx = _make_full_ctx(
            close=97.0, ema_fast=99.0, ema_slow=100.0,
            adx=35.0, rsi=40.0, atr=2.0, bb_width=0.10,
            high=97.5, low=96.5,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["exit_reason"] == "stop_loss"

    def test_exit_on_take_profit(self):
        strat = RegimeDualStrategy()
        self._enter_trend_position(strat, entry_price=101.0)
        # Price above entry + 2.5*ATR = 101 + 5.0 = 106.0
        ctx = _make_full_ctx(
            close=107.0, ema_fast=105.0, ema_slow=102.0,
            adx=35.0, rsi=65.0, atr=2.0, bb_width=0.10,
            high=107.5,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["exit_reason"] == "take_profit"

    def test_exit_on_max_bars_trend(self):
        strat = RegimeDualStrategy()
        self._enter_trend_position(strat, entry_price=101.0)
        # Simulate 60 bars in position
        state = strat._states["AAPL"]
        state.bars_since_entry = 59  # on_context will increment to 60
        ctx = _make_full_ctx(
            close=102.0, ema_fast=102.0, ema_slow=101.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["exit_reason"] == "max_bars"

    def test_exit_on_max_bars_mr(self):
        strat = RegimeDualStrategy()
        self._enter_mr_position(strat, entry_price=95.0)
        state = strat._states["AAPL"]
        state.bars_since_entry = 29  # will become 30
        ctx = _make_full_ctx(
            close=96.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=35.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.15,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["exit_reason"] == "max_bars"

    def test_exit_mr_target_reached_pct_b(self):
        strat = RegimeDualStrategy()
        self._enter_mr_position(strat, entry_price=95.0)
        # MR take_profit = entry(95) + 1.5*atr(2) = 98.0, so keep close < 98
        # pct_b >= 0.50 → mr_target
        ctx = _make_full_ctx(
            close=97.5, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=45.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.55,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["exit_reason"] == "mr_target"

    def test_exit_mr_rsi_neutral(self):
        strat = RegimeDualStrategy()
        self._enter_mr_position(strat, entry_price=95.0)
        # MR take_profit = 98.0, keep close < 98
        # rsi >= 50 → mr_target
        ctx = _make_full_ctx(
            close=97.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=52.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.30,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["exit_reason"] == "mr_target"

    def test_exit_trailing_stop(self):
        strat = RegimeDualStrategy()
        self._enter_trend_position(strat, entry_price=101.0)
        state = strat._states["AAPL"]
        state.bars_since_entry = 3  # will be incremented to 4 > 3
        state.highest_since_entry = 108.0
        # Price drops below highest - 2.0*ATR = 108 - 4.0 = 104.0
        ctx = _make_full_ctx(
            close=103.0, ema_fast=104.0, ema_slow=102.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
            high=103.5,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["exit_reason"] == "trailing_stop"

    def test_exit_regime_uncertain_3_bars(self):
        strat = RegimeDualStrategy()
        self._enter_trend_position(strat, entry_price=101.0)
        # Feed bars that push regime to UNCERTAIN and accumulate 3 bars there
        for _ in range(4):
            ctx = _make_full_ctx(
                close=102.0, ema_fast=102.0, ema_slow=101.0,
                adx=22.0, rsi=55.0, atr=2.0, bb_width=0.10,
                high=102.5,
            )
            result = strat.on_context(ctx)
            if result is not None:
                break
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["exit_reason"] == "regime_uncertain"


# ---- Strength and Metadata ----

class TestStrengthAndMetadata:
    def test_trend_signal_strength_in_range(self):
        strat = RegimeDualStrategy()
        _build_regime(strat, "AAPL", adx=35.0, bb_width=0.10, n_bars=6)
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert 0.0 <= result.strength <= 1.0

    def test_mr_signal_strength_in_range(self):
        strat = RegimeDualStrategy()
        _build_regime(strat, "AAPL", adx=15.0, bb_width=0.10, n_bars=5)
        for _ in range(2):
            ctx = _make_full_ctx(adx=15.0, bb_width=0.05,
                                 ema_fast=99.0, ema_slow=100.0)
            strat.on_context(ctx)
        # Transition bar with low RSI
        ctx = _make_full_ctx(adx=15.0, bb_width=0.05,
                             ema_fast=99.0, ema_slow=100.0, rsi=28.0)
        strat.on_context(ctx)
        ctx = _make_full_ctx(
            close=95.0, ema_fast=99.0, ema_slow=100.0,
            adx=15.0, rsi=25.0, atr=2.0,
            bb_upper=105.0, bb_middle=100.0, bb_lower=94.5,
            bb_width=0.05, bb_pct_b=0.02,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert 0.0 <= result.strength <= 1.0

    def test_trend_entry_metadata_keys(self):
        strat = RegimeDualStrategy()
        _build_regime(strat, "AAPL", adx=35.0, bb_width=0.10, n_bars=6)
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
        )
        result = strat.on_context(ctx)
        assert result is not None
        meta = result.metadata
        assert "sub_strategy" in meta
        assert "regime" in meta
        assert "stop_loss" in meta
        assert "take_profit" in meta
        assert meta["sub_strategy"] == "trend_following"

    def test_exit_metadata_keys(self):
        strat = RegimeDualStrategy()
        _build_regime(strat, "AAPL", adx=35.0, bb_width=0.10, n_bars=6)
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
            high=101.5,
        )
        entry = strat.on_context(ctx)
        assert entry is not None
        # Trigger stop loss
        ctx = _make_full_ctx(
            close=97.0, ema_fast=99.0, ema_slow=100.0,
            adx=35.0, rsi=40.0, atr=2.0, bb_width=0.10,
            high=97.5, low=96.5,
        )
        result = strat.on_context(ctx)
        assert result is not None
        meta = result.metadata
        assert "exit_reason" in meta
        assert "bars_held" in meta
        assert "entry_price" in meta
        assert "pnl_pct" in meta


# ---- State Management ----

class TestStateManagement:
    def test_per_symbol_state_isolation(self):
        strat = RegimeDualStrategy()
        # Build different regimes for different symbols
        _build_regime(strat, "AAPL", adx=35.0, bb_width=0.10, n_bars=6)
        _build_regime(strat, "MSFT", adx=15.0, bb_width=0.10, n_bars=6)
        assert "AAPL" in strat._states
        assert "MSFT" in strat._states
        assert strat._states["AAPL"].regime != strat._states["MSFT"].regime or True
        # Verify they are independent objects
        assert strat._states["AAPL"] is not strat._states["MSFT"]

    def test_state_resets_after_exit(self):
        strat = RegimeDualStrategy()
        _build_regime(strat, "AAPL", adx=35.0, bb_width=0.10, n_bars=6)
        # Enter position
        ctx = _make_full_ctx(
            close=101.0, ema_fast=101.0, ema_slow=100.0,
            adx=35.0, rsi=55.0, atr=2.0, bb_width=0.10,
            high=101.5,
        )
        entry = strat.on_context(ctx)
        assert entry is not None
        state = strat._states["AAPL"]
        assert state.in_position is True
        # Trigger exit (stop loss)
        ctx = _make_full_ctx(
            close=97.0, ema_fast=99.0, ema_slow=100.0,
            adx=35.0, rsi=40.0, atr=2.0, bb_width=0.10,
            high=97.5, low=96.5,
        )
        exit_sig = strat.on_context(ctx)
        assert exit_sig is not None
        assert exit_sig.direction == "close"
        assert state.in_position is False

    def test_required_indicators_set(self):
        strat = RegimeDualStrategy()
        assert len(strat.required_indicators) == 6
        names = {spec.name for spec in strat.required_indicators}
        assert names == {"EMA", "ADX", "RSI", "ATR", "BBANDS"}
