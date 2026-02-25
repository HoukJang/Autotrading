"""Tests for RegimeMomentum strategy with adaptive momentum and regime detection."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.regime_momentum import RegimeMomentum


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_ctx_with_history(
    symbol: str = "TEST",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    indicators: dict | None = None,
    history_closes: list[float] | None = None,
) -> MarketContext:
    """Build a MarketContext with optional history for 20-bar return tests."""
    h = high if high is not None else close + 1.0
    l = low if low is not None else close - 1.0
    bar = Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 15, 10, 0),
        open=close,
        high=h,
        low=l,
        close=close,
        volume=1000.0,
    )
    history: deque[Bar] = deque(maxlen=500)
    if history_closes:
        for i, c in enumerate(history_closes):
            history.append(
                Bar(
                    symbol=symbol,
                    timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                    open=c,
                    high=c + 1,
                    low=c - 1,
                    close=c,
                    volume=1000.0,
                )
            )
    history.append(bar)
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


def _default_indicators(
    adx: float = 30.0,
    bb_width: float = 0.10,
    bb_pct_b: float = 0.50,
    ema_8: float = 102.0,
    ema_21: float = 100.0,
    rsi: float = 60.0,
    atr: float = 2.0,
) -> dict:
    """Return a full set of indicators with sensible defaults."""
    return {
        "ADX_14": adx,
        "BBANDS_20": {
            "upper": 110.0,
            "middle": 100.0,
            "lower": 90.0,
            "width": bb_width,
            "pct_b": bb_pct_b,
        },
        "EMA_8": ema_8,
        "EMA_21": ema_21,
        "RSI_14": rsi,
        "ATR_14": atr,
    }


def _build_bb_width_history(
    strategy: RegimeMomentum,
    symbol: str = "TEST",
    n_bars: int = 6,
    adx: float = 30.0,
    bb_width: float = 0.10,
) -> None:
    """Feed bars to accumulate BB width history and stabilize regime.

    Uses bearish EMA (8 < 21) so no entry is triggered.
    """
    # We need 20+ bars of history for momentum calc, so provide that
    history_closes = [90.0 + i * 0.5 for i in range(25)]
    for _ in range(n_bars):
        indicators = _default_indicators(
            adx=adx,
            bb_width=bb_width,
            ema_8=98.0,  # bearish: EMA_8 < EMA_21
            ema_21=100.0,
            rsi=55.0,
        )
        ctx = _make_ctx_with_history(
            symbol=symbol,
            close=100.0,
            indicators=indicators,
            history_closes=history_closes,
        )
        strategy.on_context(ctx)


def _make_entry_ctx(
    symbol: str = "TEST",
    close: float = 105.0,
    adx: float = 30.0,
    bb_width: float = 0.15,
    ema_8: float = 106.0,
    ema_21: float = 104.0,
    rsi: float = 60.0,
    atr: float = 2.0,
    high: float | None = None,
    low: float | None = None,
    history_close_start: float = 80.0,
) -> MarketContext:
    """Build a context that satisfies all entry conditions by default.

    - TREND regime (ADX >= 25, bb_width expanding relative to history avg)
    - Positive 20-bar return (close > close_20_bars_ago)
    - RSI between 50 and 70
    - EMA_8 > EMA_21
    - ATR/close < 0.03
    - Sufficient history (>= 21 bars)
    """
    indicators = _default_indicators(
        adx=adx,
        bb_width=bb_width,
        ema_8=ema_8,
        ema_21=ema_21,
        rsi=rsi,
        atr=atr,
    )
    # 25 bars of history; first bar close = history_close_start, rising to current
    history_closes = [
        history_close_start + i * (close - history_close_start) / 24
        for i in range(25)
    ]
    return _make_ctx_with_history(
        symbol=symbol,
        close=close,
        high=high,
        low=low,
        indicators=indicators,
        history_closes=history_closes,
    )


# ===========================================================================
# 1. Initialization
# ===========================================================================

class TestInit:
    def test_name(self):
        strat = RegimeMomentum()
        assert strat.name == "regime_momentum"

    def test_required_indicators(self):
        strat = RegimeMomentum()
        names = {spec.name for spec in strat.required_indicators}
        assert names == {"ADX", "BBANDS", "EMA", "RSI", "ATR"}
        assert len(strat.required_indicators) == 6  # EMA appears twice (8, 21)


# ===========================================================================
# 2. No-signal scenarios
# ===========================================================================

class TestNoSignal:
    def test_returns_none_when_indicators_none(self):
        """Any indicator being None should return None."""
        strat = RegimeMomentum()
        ctx = _make_ctx_with_history(indicators={"ADX_14": None, "RSI_14": 55.0})
        assert strat.on_context(ctx) is None

    def test_returns_none_when_all_indicators_missing(self):
        strat = RegimeMomentum()
        ctx = _make_ctx_with_history(indicators={})
        assert strat.on_context(ctx) is None

    def test_no_signal_regime_not_trend_adx_low(self):
        """ADX < 25 means regime cannot be TREND."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=15.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(adx=15.0, bb_width=0.15, rsi=60.0)
        assert strat.on_context(ctx) is None

    def test_no_signal_rsi_too_high(self):
        """RSI > 70 should block entry even in TREND regime."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(adx=30.0, bb_width=0.15, rsi=75.0)
        assert strat.on_context(ctx) is None

    def test_no_signal_rsi_too_low(self):
        """RSI < 50 should block entry even in TREND regime."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(adx=30.0, bb_width=0.15, rsi=45.0)
        assert strat.on_context(ctx) is None

    def test_no_signal_ema_bearish(self):
        """EMA_8 < EMA_21 should block entry."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(adx=30.0, bb_width=0.15, ema_8=98.0, ema_21=100.0)
        assert strat.on_context(ctx) is None

    def test_no_signal_too_volatile(self):
        """ATR/close >= 0.03 should block entry."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        # atr=3.5 / close=105.0 = 0.033 > 0.03
        ctx = _make_entry_ctx(adx=30.0, bb_width=0.15, atr=3.5, close=105.0)
        assert strat.on_context(ctx) is None

    def test_no_signal_not_enough_history(self):
        """Need at least 20 bars in history for 20-bar return calculation."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        indicators = _default_indicators(adx=30.0, bb_width=0.15)
        # Only 5 bars of history -- insufficient for 20-bar return
        ctx = _make_ctx_with_history(
            close=105.0,
            indicators=indicators,
            history_closes=[100.0, 101.0, 102.0, 103.0, 104.0],
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_not_enough_bb_width_history(self):
        """Need at least 5 bars of BB width history."""
        strat = RegimeMomentum()
        # Only feed 3 bars (< 5 required)
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=3)
        ctx = _make_entry_ctx(adx=30.0, bb_width=0.15)
        # With only 4 total bars of BB width, regime detection can't confirm TREND
        assert strat.on_context(ctx) is None

    def test_no_signal_negative_momentum(self):
        """20-bar return <= 0 (negative momentum) should block entry."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        indicators = _default_indicators(adx=30.0, bb_width=0.15)
        # History where 20 bars ago close was higher than current
        history_closes = [110.0 - i * 0.5 for i in range(25)]  # declining
        ctx = _make_ctx_with_history(
            close=95.0,  # current close lower than 20-bar-ago close
            indicators=indicators,
            history_closes=history_closes,
        )
        assert strat.on_context(ctx) is None


# ===========================================================================
# 3. Long entry
# ===========================================================================

class TestLongEntry:
    def test_long_entry_all_conditions_met(self):
        """When all conditions align, should produce a long signal."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        # Entry bar: ADX=30 (TREND with expanding BB),
        # positive momentum, RSI=60, EMA bullish, low vol
        ctx = _make_entry_ctx(
            close=105.0,
            adx=30.0,
            bb_width=0.15,  # expanding vs avg ~0.10
            ema_8=106.0,
            ema_21=104.0,
            rsi=60.0,
            atr=2.0,
            history_close_start=80.0,  # positive 20-bar return
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"
        assert result.strategy == "regime_momentum"

    def test_direction_always_long(self):
        """Entry signals are always long (never short)."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx()
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"

    def test_entry_signal_strength_range(self):
        """Strength should be between 0.0 and 1.0."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx()
        result = strat.on_context(ctx)
        assert result is not None
        assert 0.0 <= result.strength <= 1.0

    def test_entry_metadata_contains_required_keys(self):
        """Entry metadata should contain sub_strategy and stop_loss."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(close=105.0, atr=2.0)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["sub_strategy"] == "regime_momentum"
        assert "stop_loss" in result.metadata
        # stop_loss = close - 1.5 * ATR = 105 - 3 = 102
        assert result.metadata["stop_loss"] == pytest.approx(102.0)

    def test_entry_strength_calculation(self):
        """Strength = min(1.0, return_20 * 10 + (ADX - 25) / 25)."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        # 20-bar return: (105 - 80) / 80 = 0.3125
        # strength = min(1.0, 0.3125 * 10 + (30 - 25) / 25) = min(1.0, 3.125 + 0.2)
        # = min(1.0, 3.325) = 1.0
        ctx = _make_entry_ctx(
            close=105.0, adx=30.0, bb_width=0.15,
            history_close_start=80.0,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == pytest.approx(1.0)

    def test_entry_strength_moderate(self):
        """Test moderate strength with small 20-bar return."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=26.0, bb_width=0.10, n_bars=6)
        # 20-bar return: (101 - 100) / 100 = 0.01
        # strength = min(1.0, 0.01 * 10 + (26 - 25) / 25) = min(1.0, 0.1 + 0.04) = 0.14
        ctx = _make_entry_ctx(
            close=101.0, adx=26.0, bb_width=0.15,
            ema_8=102.0, ema_21=100.5,
            history_close_start=100.0,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == pytest.approx(0.14, abs=0.05)

    def test_no_duplicate_entry_while_in_position(self):
        """Should not generate entry signal when already in position."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx1 = _make_entry_ctx()
        result1 = strat.on_context(ctx1)
        assert result1 is not None
        assert result1.direction == "long"

        # Same conditions again -- should NOT enter again
        ctx2 = _make_entry_ctx()
        result2 = strat.on_context(ctx2)
        assert result2 is None


# ===========================================================================
# 4. Exit signals
# ===========================================================================

class TestExitRegimeChange:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        """Build regime and enter a long position."""
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(symbol=symbol, close=105.0, adx=30.0, bb_width=0.15)
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"
        return result

    def test_exit_on_regime_change(self):
        """When regime leaves TREND, should close position."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        # Feed bar with low ADX -> regime changes away from TREND
        indicators = _default_indicators(adx=15.0, bb_width=0.05)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=106.0, indicators=indicators, history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "regime_change"


class TestExitRSI:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(symbol=symbol, close=105.0, adx=30.0, bb_width=0.15)
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"

    def test_exit_rsi_above_75(self):
        """RSI > 75 should trigger target exit."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        # Keep regime in TREND but RSI > 75
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=78.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=110.0, indicators=indicators, history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "target"


class TestExitTrailingStop:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(
            symbol=symbol, close=105.0, high=106.0,
            adx=30.0, bb_width=0.15, atr=2.0,
        )
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"

    def test_exit_trailing_stop(self):
        """close <= highest_since_entry - 2.0*ATR triggers trailing stop."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        state = strat._states["TEST"]
        # Simulate price moving up first
        state.highest_since_entry = 115.0
        state.bars_since_entry = 2  # will be incremented to 3

        # ATR=2.0, trailing stop = 115 - 2*2 = 111. close=110 < 111 -> trigger
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=60.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=110.0, high=110.5, indicators=indicators,
            history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "trailing_stop"


class TestExitStopLoss:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(
            symbol=symbol, close=105.0, adx=30.0, bb_width=0.15, atr=2.0,
        )
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"

    def test_exit_stop_loss(self):
        """close <= entry_price - 1.5*ATR triggers stop loss."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        # entry=105, stop = 105 - 1.5*2 = 102. close=101 < 102 -> trigger
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=55.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=101.0, indicators=indicators, history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "stop_loss"


class TestExitTimeout:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(
            symbol=symbol, close=105.0, adx=30.0, bb_width=0.15, atr=2.0,
        )
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"

    def test_exit_timeout(self):
        """bars_since_entry >= 10 should trigger timeout exit."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        state = strat._states["TEST"]
        state.bars_since_entry = 9  # will be incremented to 10

        # Keep price comfortably within bounds (no other exit triggers)
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=60.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=106.0, high=106.5, indicators=indicators,
            history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "timeout"


# ===========================================================================
# 5. Exit signal properties
# ===========================================================================

class TestExitSignalProperties:
    def _enter_position(self, strat: RegimeMomentum, symbol: str = "TEST"):
        _build_bb_width_history(strat, symbol=symbol, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(
            symbol=symbol, close=105.0, adx=30.0, bb_width=0.15, atr=2.0,
        )
        result = strat.on_context(ctx)
        assert result is not None and result.direction == "long"

    def test_exit_strength_is_one(self):
        """All exit signals should have strength=1.0."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        state = strat._states["TEST"]
        state.bars_since_entry = 9
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=60.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=106.0, high=106.5, indicators=indicators,
            history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == 1.0

    def test_exit_clears_position_state(self):
        """After exit, in_position should be False."""
        strat = RegimeMomentum()
        self._enter_position(strat)
        state = strat._states["TEST"]
        state.bars_since_entry = 9
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=60.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx = _make_ctx_with_history(
            close=106.0, high=106.5, indicators=indicators,
            history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is not None
        assert state.in_position is False


# ===========================================================================
# 6. BB width history accumulation
# ===========================================================================

class TestBBWidthHistory:
    def test_bb_width_history_accumulates(self):
        """BB width values should be appended to history each bar."""
        strat = RegimeMomentum()
        for i in range(5):
            indicators = _default_indicators(bb_width=0.10 + i * 0.01)
            ctx = _make_ctx_with_history(indicators=indicators)
            strat.on_context(ctx)
        state = strat._states["TEST"]
        assert len(state.bb_width_history) == 5
        assert state.bb_width_history[0] == pytest.approx(0.10)
        assert state.bb_width_history[4] == pytest.approx(0.14)

    def test_bb_width_history_maxlen_20(self):
        """BB width history should be capped at 20."""
        strat = RegimeMomentum()
        for i in range(25):
            indicators = _default_indicators(bb_width=0.10 + i * 0.001)
            ctx = _make_ctx_with_history(indicators=indicators)
            strat.on_context(ctx)
        state = strat._states["TEST"]
        assert len(state.bb_width_history) == 20


# ===========================================================================
# 7. 20-bar return calculation
# ===========================================================================

class TestTwentyBarReturn:
    def test_20_bar_return_positive(self):
        """Positive 20-bar return should allow entry when all conditions met."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        # 20 bars ago close=80.0, now close=105.0 -> return = (105-80)/80 = 0.3125
        ctx = _make_entry_ctx(close=105.0, history_close_start=80.0)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"

    def test_20_bar_return_negative_blocks_entry(self):
        """Negative 20-bar return should prevent entry."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        indicators = _default_indicators(adx=30.0, bb_width=0.15)
        # Declining history: 20 bars ago was 120, now 100
        history_closes = [120.0 - i * 0.8 for i in range(25)]
        ctx = _make_ctx_with_history(
            close=100.0, indicators=indicators, history_closes=history_closes,
        )
        result = strat.on_context(ctx)
        assert result is None

    def test_20_bar_return_insufficient_history(self):
        """With < 21 bars total, should return None (cannot compute)."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        indicators = _default_indicators(adx=30.0, bb_width=0.15)
        # Only 10 bars of history + current bar = 11 total, need >= 21
        ctx = _make_ctx_with_history(
            close=105.0,
            indicators=indicators,
            history_closes=[90.0 + i for i in range(10)],
        )
        result = strat.on_context(ctx)
        assert result is None


# ===========================================================================
# 8. Regime detection
# ===========================================================================

class TestRegimeDetection:
    def test_trend_regime(self):
        """ADX >= 25 AND expanding BB width -> TREND."""
        strat = RegimeMomentum()
        # Build base BB width history with normal width
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        # Feed expanding bar
        indicators = _default_indicators(adx=30.0, bb_width=0.15)
        ctx = _make_ctx_with_history(indicators=indicators)
        strat.on_context(ctx)
        state = strat._states["TEST"]
        assert state.current_regime == "TREND"

    def test_ranging_regime(self):
        """ADX < 20 AND contracting BB width -> RANGING."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=15.0, bb_width=0.10, n_bars=6)
        # Feed contracting bar
        indicators = _default_indicators(adx=15.0, bb_width=0.05)
        ctx = _make_ctx_with_history(indicators=indicators)
        strat.on_context(ctx)
        state = strat._states["TEST"]
        assert state.current_regime == "RANGING"

    def test_uncertain_regime(self):
        """Moderate ADX, normal BB width -> UNCERTAIN."""
        strat = RegimeMomentum()
        indicators = _default_indicators(adx=22.0, bb_width=0.10)
        ctx = _make_ctx_with_history(indicators=indicators)
        strat.on_context(ctx)
        state = strat._states["TEST"]
        assert state.current_regime == "UNCERTAIN"

    def test_per_symbol_isolation(self):
        """Each symbol should have independent state."""
        strat = RegimeMomentum()
        ctx_a = _make_ctx_with_history(
            symbol="AAPL",
            indicators=_default_indicators(adx=30.0, bb_width=0.10),
        )
        ctx_b = _make_ctx_with_history(
            symbol="MSFT",
            indicators=_default_indicators(adx=15.0, bb_width=0.10),
        )
        strat.on_context(ctx_a)
        strat.on_context(ctx_b)
        assert "AAPL" in strat._states
        assert "MSFT" in strat._states
        assert strat._states["AAPL"] is not strat._states["MSFT"]


# ===========================================================================
# 9. Highest-since-entry tracking
# ===========================================================================

class TestHighestSinceEntry:
    def test_highest_updated_each_bar(self):
        """highest_since_entry should update with each bar's high."""
        strat = RegimeMomentum()
        _build_bb_width_history(strat, adx=30.0, bb_width=0.10, n_bars=6)
        ctx = _make_entry_ctx(close=105.0, high=106.0, adx=30.0, bb_width=0.15)
        result = strat.on_context(ctx)
        assert result is not None
        state = strat._states["TEST"]
        assert state.highest_since_entry == 106.0

        # Next bar with higher high
        indicators = _default_indicators(adx=30.0, bb_width=0.15, rsi=60.0, atr=2.0)
        history_closes = [80.0 + i for i in range(25)]
        ctx2 = _make_ctx_with_history(
            close=108.0, high=110.0, indicators=indicators,
            history_closes=history_closes,
        )
        strat.on_context(ctx2)
        assert state.highest_since_entry == 110.0
