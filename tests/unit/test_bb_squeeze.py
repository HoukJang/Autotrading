"""Tests for BbSqueezeBreakout strategy with squeeze detection and bidirectional breakout."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout


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
        open=o,
        high=h,
        low=l,
        close=close,
        volume=volume,
    )
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=deque([bar], maxlen=500),
    )


def _full_indicators(
    bb_upper: float = 110.0,
    bb_middle: float = 100.0,
    bb_lower: float = 90.0,
    bb_width: float = 0.20,
    bb_pct_b: float = 0.50,
    adx: float = 25.0,
    rsi: float = 50.0,
    atr: float = 2.0,
) -> dict:
    return {
        "BBANDS_20": {
            "upper": bb_upper,
            "middle": bb_middle,
            "lower": bb_lower,
            "width": bb_width,
            "pct_b": bb_pct_b,
        },
        "ADX_14": adx,
        "RSI_14": rsi,
        "ATR_14": atr,
    }


def _feed_bars(strategy: BbSqueezeBreakout, n: int, symbol: str = "TEST",
               close: float = 100.0, bb_width: float = 0.20,
               adx: float = 25.0, rsi: float = 50.0, atr: float = 2.0,
               bb_pct_b: float = 0.50) -> None:
    """Feed n bars to build bb_width_history without triggering entry."""
    for _ in range(n):
        indicators = _full_indicators(
            bb_width=bb_width, adx=adx, rsi=rsi, atr=atr, bb_pct_b=bb_pct_b,
        )
        ctx = _make_ctx(symbol=symbol, close=close, indicators=indicators)
        strategy.on_context(ctx)


# ---- Initialization ----

class TestInit:
    def test_name_is_bb_squeeze(self):
        strat = BbSqueezeBreakout()
        assert strat.name == "bb_squeeze"

    def test_required_indicators_contain_correct_keys(self):
        strat = BbSqueezeBreakout()
        keys = {spec.key for spec in strat.required_indicators}
        assert "BBANDS_20" in keys
        assert "ADX_14" in keys
        assert "RSI_14" in keys
        assert "ATR_14" in keys

    def test_required_indicators_count(self):
        strat = BbSqueezeBreakout()
        assert len(strat.required_indicators) == 4


# ---- No Signal Cases ----

class TestNoSignal:
    def test_returns_none_when_indicators_none(self):
        strat = BbSqueezeBreakout()
        ctx = _make_ctx(indicators={})
        assert strat.on_context(ctx) is None

    def test_returns_none_when_partial_indicators(self):
        strat = BbSqueezeBreakout()
        indicators = {"BBANDS_20": {"upper": 110, "middle": 100, "lower": 90,
                                     "width": 0.2, "pct_b": 0.5}}
        ctx = _make_ctx(indicators=indicators)
        assert strat.on_context(ctx) is None

    def test_returns_none_when_not_squeezed(self):
        """Width is above threshold (not squeezed), no signal even with other conditions met."""
        strat = BbSqueezeBreakout()
        # Build 6 bars of normal width history
        _feed_bars(strat, 6, bb_width=0.20, adx=20.0)
        # Now feed a bar where width is still normal (not squeezed)
        # avg_width = 0.20, threshold = 0.20 * 0.75 = 0.15
        # current width 0.20 > 0.15 → not squeezed
        indicators = _full_indicators(bb_width=0.20, adx=25.0, bb_pct_b=1.2)
        ctx = _make_ctx(indicators=indicators)
        result = strat.on_context(ctx)
        assert result is None

    def test_returns_none_when_squeezed_but_adx_not_rising(self):
        """Squeezed but ADX is not rising (diff < 2.0)."""
        strat = BbSqueezeBreakout()
        # Feed 5 bars with normal width to build history, constant ADX
        _feed_bars(strat, 5, bb_width=0.20, adx=25.0)
        # Now feed a squeezed bar (width 0.10 < avg 0.20 * 0.75 = 0.15)
        # but ADX barely changed (25.0 -> 26.0, diff = 1.0 < 2.0)
        indicators = _full_indicators(bb_width=0.10, adx=26.0, bb_pct_b=1.2)
        ctx = _make_ctx(indicators=indicators)
        result = strat.on_context(ctx)
        assert result is None

    def test_returns_none_when_squeezed_adx_rising_but_pct_b_neutral(self):
        """Squeezed and ADX rising, but pct_b between 0.0 and 1.0 (no breakout)."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # Squeezed (0.10 < 0.15) and ADX rising (20 -> 25, diff=5 >= 2)
        indicators = _full_indicators(bb_width=0.10, adx=25.0, bb_pct_b=0.50)
        ctx = _make_ctx(indicators=indicators)
        result = strat.on_context(ctx)
        assert result is None


# ---- Long Entry ----

class TestLongEntry:
    def test_long_entry_on_squeeze_breakout_above(self):
        """Squeezed + ADX rising + pct_b > 1.0 -> long entry."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # Squeeze: 0.10 < 0.20 * 0.75 = 0.15
        # ADX rising: 20 -> 25, diff = 5 >= 2
        # pct_b = 1.2 > 1.0 → long breakout
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"
        assert result.strategy == "bb_squeeze"
        assert result.symbol == "TEST"

    def test_long_entry_strength_calculation(self):
        """Strength = min(1.0, pct_b - 1.0 + 0.5)."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # pct_b = 1.2 → strength = min(1.0, 1.2 - 1.0 + 0.5) = min(1.0, 0.7) = 0.7
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == pytest.approx(0.7, abs=0.01)

    def test_long_entry_strength_capped_at_1(self):
        """Strength caps at 1.0 for extreme breakout."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # pct_b = 2.0 → strength = min(1.0, 2.0 - 1.0 + 0.5) = min(1.0, 1.5) = 1.0
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=2.0, atr=2.0,
        )
        ctx = _make_ctx(close=120.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == pytest.approx(1.0, abs=0.01)

    def test_long_entry_metadata(self):
        """Metadata includes sub_strategy and stop_loss."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["sub_strategy"] == "squeeze_long"
        # stop_loss = close - 1.5 * ATR = 112 - 3.0 = 109.0
        assert result.metadata["stop_loss"] == pytest.approx(109.0, abs=0.01)


# ---- Short Entry ----

class TestShortEntry:
    def test_short_entry_on_squeeze_breakout_below(self):
        """Squeezed + ADX rising + pct_b < 0.0 -> short entry."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # pct_b = -0.3 < 0.0 → short breakout
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=-0.3, rsi=40.0, atr=2.0,
        )
        ctx = _make_ctx(close=88.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "short"
        assert result.strategy == "bb_squeeze"

    def test_short_entry_strength_calculation(self):
        """Strength = min(1.0, abs(pct_b) + 0.5)."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # pct_b = -0.3 → strength = min(1.0, 0.3 + 0.5) = 0.8
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=-0.3, atr=2.0,
        )
        ctx = _make_ctx(close=88.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.strength == pytest.approx(0.8, abs=0.01)

    def test_short_entry_metadata(self):
        """Metadata includes sub_strategy=squeeze_short and stop_loss above close."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=-0.3, rsi=40.0, atr=2.0,
        )
        ctx = _make_ctx(close=88.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.metadata["sub_strategy"] == "squeeze_short"
        # stop_loss = close + 1.5 * ATR = 88 + 3.0 = 91.0
        assert result.metadata["stop_loss"] == pytest.approx(91.0, abs=0.01)


# ---- Long Exits ----

class TestLongExit:
    def _enter_long(self, strat: BbSqueezeBreakout, symbol: str = "TEST",
                    entry_close: float = 112.0) -> Signal:
        """Build history and trigger a long entry."""
        _feed_bars(strat, 5, symbol=symbol, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(symbol=symbol, close=entry_close, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"
        return result

    def test_long_exit_rsi_target(self):
        """Long exit when RSI > 75 → target."""
        strat = BbSqueezeBreakout()
        self._enter_long(strat, entry_close=112.0)
        # Next bar: RSI = 78 > 75
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.80,
            rsi=78.0, atr=2.0, bb_middle=100.0,
        )
        ctx = _make_ctx(close=115.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.strength == 1.0
        assert result.metadata["reason"] == "target"

    def test_long_exit_stop_loss_atr(self):
        """Long exit when close <= entry - 1.5*ATR."""
        strat = BbSqueezeBreakout()
        self._enter_long(strat, entry_close=112.0)
        # entry=112, stop = 112 - 1.5*2.0 = 109.0
        # close=108.5 <= 109.0
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.40,
            rsi=45.0, atr=2.0, bb_middle=105.0,
        )
        ctx = _make_ctx(close=108.5, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "stop_loss"

    def test_long_exit_below_bb_middle(self):
        """Long exit when close < BB middle → stop_loss."""
        strat = BbSqueezeBreakout()
        self._enter_long(strat, entry_close=112.0)
        # close=99 < bb_middle=100, but not ATR stop (112-3=109, 99<109 would also trigger ATR stop)
        # Use entry_close=105 so ATR stop = 105 - 3 = 102, and close=101 < middle=100 NO
        # Actually let's make close above ATR stop but below middle
        strat2 = BbSqueezeBreakout()
        _feed_bars(strat2, 5, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=105.0, indicators=indicators)
        entry = strat2.on_context(ctx)
        assert entry is not None
        # entry=105, ATR stop = 105 - 3 = 102
        # close=103 > 102 (not ATR stop), but close=103 < bb_middle=105 → stop_loss
        indicators2 = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.40,
            rsi=50.0, atr=2.0, bb_middle=105.0,
        )
        ctx2 = _make_ctx(close=103.0, indicators=indicators2)
        result = strat2.on_context(ctx2)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "stop_loss"


# ---- Short Exits ----

class TestShortExit:
    def _enter_short(self, strat: BbSqueezeBreakout, symbol: str = "TEST",
                     entry_close: float = 88.0) -> Signal:
        """Build history and trigger a short entry."""
        _feed_bars(strat, 5, symbol=symbol, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=-0.3, rsi=40.0, atr=2.0,
        )
        ctx = _make_ctx(symbol=symbol, close=entry_close, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "short"
        return result

    def test_short_exit_rsi_target(self):
        """Short exit when RSI < 25 → target."""
        strat = BbSqueezeBreakout()
        self._enter_short(strat, entry_close=88.0)
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.20,
            rsi=22.0, atr=2.0, bb_middle=100.0,
        )
        ctx = _make_ctx(close=85.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.strength == 1.0
        assert result.metadata["reason"] == "target"

    def test_short_exit_stop_loss_atr(self):
        """Short exit when close >= entry + 1.5*ATR."""
        strat = BbSqueezeBreakout()
        self._enter_short(strat, entry_close=88.0)
        # entry=88, stop = 88 + 1.5*2.0 = 91.0
        # close=91.5 >= 91.0
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.60,
            rsi=55.0, atr=2.0, bb_middle=95.0,
        )
        ctx = _make_ctx(close=91.5, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "stop_loss"

    def test_short_exit_above_bb_middle(self):
        """Short exit when close > BB middle → stop_loss."""
        strat = BbSqueezeBreakout()
        self._enter_short(strat, entry_close=88.0)
        # entry=88, ATR stop = 88 + 3 = 91
        # close=90 < 91 (not ATR stop), but close=90 > bb_middle=89 → stop_loss
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.60,
            rsi=50.0, atr=2.0, bb_middle=89.0,
        )
        ctx = _make_ctx(close=90.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "stop_loss"


# ---- Timeout Exit ----

class TestTimeoutExit:
    def test_timeout_exit_after_7_bars_long(self):
        """Timeout exit after bars_since_entry >= 7."""
        strat = BbSqueezeBreakout()
        # Enter long
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        entry = strat.on_context(ctx)
        assert entry is not None

        # Feed 6 neutral bars (no exit trigger, bars_since_entry 1..6)
        for _ in range(6):
            indicators = _full_indicators(
                bb_width=0.15, adx=30.0, bb_pct_b=0.60,
                rsi=55.0, atr=2.0, bb_middle=100.0,
            )
            ctx = _make_ctx(close=112.0, indicators=indicators)
            result = strat.on_context(ctx)
            assert result is None

        # 7th bar → timeout (bars_since_entry = 7)
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.60,
            rsi=55.0, atr=2.0, bb_middle=100.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "timeout"

    def test_timeout_exit_after_7_bars_short(self):
        """Timeout exit for short position after 7 bars."""
        strat = BbSqueezeBreakout()
        # Enter short
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=-0.3, rsi=40.0, atr=2.0,
        )
        ctx = _make_ctx(close=88.0, indicators=indicators)
        entry = strat.on_context(ctx)
        assert entry is not None

        # Feed 6 neutral bars (short: close < entry+ATR stop (91), close > bb_middle,
        # RSI between 25-75). We need close < bb_middle to not exit early.
        for _ in range(6):
            indicators = _full_indicators(
                bb_width=0.15, adx=30.0, bb_pct_b=0.30,
                rsi=45.0, atr=2.0, bb_middle=92.0,
            )
            ctx = _make_ctx(close=88.0, indicators=indicators)
            result = strat.on_context(ctx)
            assert result is None

        # 7th bar → timeout
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.30,
            rsi=45.0, atr=2.0, bb_middle=92.0,
        )
        ctx = _make_ctx(close=88.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "close"
        assert result.metadata["reason"] == "timeout"


# ---- BB Width History Accumulation ----

class TestBbWidthHistory:
    def test_no_squeeze_detection_with_less_than_5_bars(self):
        """Need at least 5 bars of BB width history before squeeze detection works."""
        strat = BbSqueezeBreakout()
        # Feed only 3 bars (the 4th bar processed below will have len=4 < 5)
        _feed_bars(strat, 3, bb_width=0.20, adx=20.0)
        # Even with low width + ADX rising + breakout pct_b, no entry because
        # squeeze cannot be detected without 5 bars of history
        # After this on_context, history has 4 entries (3 fed + 1 current) < 5
        indicators = _full_indicators(
            bb_width=0.05, adx=25.0, bb_pct_b=1.5, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is None

    def test_squeeze_detection_works_with_5_bars(self):
        """After 5 bars of history, squeeze detection is active."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)
        # Now squeeze detection works:
        # avg_width ~ 0.20, threshold = 0.15
        # current width 0.10 < 0.15 → squeezed
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"


# ---- State Management ----

class TestStateManagement:
    def test_per_symbol_state_isolation(self):
        """Different symbols maintain independent state."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, symbol="AAPL", bb_width=0.20, adx=20.0)
        _feed_bars(strat, 5, symbol="MSFT", bb_width=0.20, adx=20.0)

        # Enter long on AAPL only
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx_aapl = _make_ctx(symbol="AAPL", close=112.0, indicators=indicators)
        result_aapl = strat.on_context(ctx_aapl)
        assert result_aapl is not None
        assert result_aapl.direction == "long"

        # MSFT should not be in position
        ctx_msft = _make_ctx(
            symbol="MSFT", close=100.0,
            indicators=_full_indicators(bb_width=0.20, adx=25.0),
        )
        result_msft = strat.on_context(ctx_msft)
        assert result_msft is None

    def test_state_resets_after_exit(self):
        """After exit, in_position resets so new entry is possible."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)

        # Enter long
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        entry = strat.on_context(ctx)
        assert entry is not None

        # Exit via RSI target
        indicators = _full_indicators(
            bb_width=0.15, adx=30.0, bb_pct_b=0.80,
            rsi=78.0, atr=2.0, bb_middle=100.0,
        )
        ctx = _make_ctx(close=115.0, indicators=indicators)
        exit_sig = strat.on_context(ctx)
        assert exit_sig is not None
        assert exit_sig.direction == "close"

        # Feed more bars to rebuild squeeze condition
        _feed_bars(strat, 5, bb_width=0.20, adx=25.0)

        # Can enter again
        indicators = _full_indicators(
            bb_width=0.10, adx=30.0, bb_pct_b=1.3, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=120.0, indicators=indicators)
        result = strat.on_context(ctx)
        assert result is not None
        assert result.direction == "long"

    def test_no_double_entry_while_in_position(self):
        """While in_position, new entry signals are not generated."""
        strat = BbSqueezeBreakout()
        _feed_bars(strat, 5, bb_width=0.20, adx=20.0)

        # Enter long
        indicators = _full_indicators(
            bb_width=0.10, adx=25.0, bb_pct_b=1.2, rsi=60.0, atr=2.0,
        )
        ctx = _make_ctx(close=112.0, indicators=indicators)
        entry = strat.on_context(ctx)
        assert entry is not None

        # Another bar with entry conditions but already in position
        # (RSI is neutral, no exit triggers)
        indicators = _full_indicators(
            bb_width=0.10, adx=28.0, bb_pct_b=1.3, rsi=60.0, atr=2.0,
            bb_middle=100.0,
        )
        ctx = _make_ctx(close=113.0, indicators=indicators)
        result = strat.on_context(ctx)
        # Should be None (no exit triggered, no new entry)
        assert result is None
