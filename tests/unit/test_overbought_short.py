"""Tests for OverboughtShort strategy -- conservative short-only mean reversion."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.strategy.overbought_short import OverboughtShort


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
    rsi: float = 80.0,
    pct_b: float = 0.98,
    adx: float = 20.0,
    ema_8: float = 102.0,
    ema_21: float = 100.0,
    atr: float = 2.0,
    bb_upper: float = 110.0,
    bb_middle: float = 100.0,
    bb_lower: float = 90.0,
    bb_width: float = 0.20,
) -> dict:
    """Return a full indicator dict with sane overbought defaults."""
    return {
        "RSI_14": rsi,
        "BBANDS_20": {
            "upper": bb_upper,
            "middle": bb_middle,
            "lower": bb_lower,
            "width": bb_width,
            "pct_b": pct_b,
        },
        "ADX_14": adx,
        "EMA_8": ema_8,
        "EMA_21": ema_21,
        "ATR_14": atr,
    }


def _prime_momentum(strategy: OverboughtShort, symbol: str = "TEST",
                    ema_8: float = 103.0, ema_21: float = 100.0) -> None:
    """Feed one bar to set prev_ema_spread so momentum fading can be detected."""
    ctx = _make_ctx(
        symbol=symbol,
        close=100.0,
        indicators=_full_indicators(
            rsi=60.0, pct_b=0.50, adx=20.0,
            ema_8=ema_8, ema_21=ema_21, atr=2.0,
        ),
    )
    strategy.on_context(ctx)


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------
class TestInit:
    def test_strategy_name(self):
        strat = OverboughtShort()
        assert strat.name == "overbought_short"

    def test_required_indicators_keys(self):
        strat = OverboughtShort()
        keys = {spec.key for spec in strat.required_indicators}
        expected = {"RSI_14", "BBANDS_20", "ADX_14", "EMA_8", "EMA_21", "ATR_14"}
        assert keys == expected

    def test_required_indicators_count(self):
        strat = OverboughtShort()
        assert len(strat.required_indicators) == 6


# ---------------------------------------------------------------------------
# 2. No-signal conditions
# ---------------------------------------------------------------------------
class TestNoSignal:
    def test_no_signal_when_indicators_none(self):
        """All indicators missing -> None."""
        strat = OverboughtShort()
        ctx = _make_ctx(indicators={})
        assert strat.on_context(ctx) is None

    def test_no_signal_when_partial_indicators(self):
        """Some indicators present but not all -> None."""
        strat = OverboughtShort()
        ctx = _make_ctx(indicators={"RSI_14": 80.0, "ADX_14": 20.0})
        assert strat.on_context(ctx) is None

    def test_no_signal_rsi_below_75(self):
        """RSI < 75 -> not overbought, no entry."""
        strat = OverboughtShort()
        _prime_momentum(strat)
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=70.0, pct_b=0.98, adx=20.0,
                                        ema_8=102.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_pct_b_below_095(self):
        """BB %B < 0.95 -> not at upper band, no entry."""
        strat = OverboughtShort()
        _prime_momentum(strat)
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=80.0, pct_b=0.90, adx=20.0,
                                        ema_8=102.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_adx_ge_25(self):
        """ADX >= 25 -> trending market, too risky to short."""
        strat = OverboughtShort()
        _prime_momentum(strat)
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=25.0,
                                        ema_8=102.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_adx_above_25(self):
        """ADX > 25 (e.g. 30) -> trending market, no entry."""
        strat = OverboughtShort()
        _prime_momentum(strat)
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=30.0,
                                        ema_8=102.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_momentum_not_fading(self):
        """EMA spread widening -> momentum not fading -> no entry."""
        strat = OverboughtShort()
        # Prime with narrower spread
        _prime_momentum(strat, ema_8=101.0, ema_21=100.0)
        # Now wider spread -> momentum INCREASING, not fading
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=20.0,
                                        ema_8=103.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None

    def test_no_signal_first_bar_no_prev_spread(self):
        """First bar has no prev_ema_spread -> cannot detect momentum fading."""
        strat = OverboughtShort()
        ctx = _make_ctx(
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=20.0,
                                        ema_8=102.0, ema_21=100.0),
        )
        assert strat.on_context(ctx) is None


# ---------------------------------------------------------------------------
# 3. Short entry
# ---------------------------------------------------------------------------
class TestShortEntry:
    def _trigger_entry(self, symbol: str = "TEST", close: float = 100.0,
                       rsi: float = 80.0, pct_b: float = 0.98, adx: float = 20.0,
                       ema_8: float = 102.0, ema_21: float = 100.0,
                       atr: float = 2.0,
                       prime_ema_8: float = 103.0,
                       prime_ema_21: float = 100.0) -> tuple[OverboughtShort, Signal | None]:
        strat = OverboughtShort()
        _prime_momentum(strat, symbol=symbol,
                        ema_8=prime_ema_8, ema_21=prime_ema_21)
        ctx = _make_ctx(
            symbol=symbol,
            close=close,
            indicators=_full_indicators(
                rsi=rsi, pct_b=pct_b, adx=adx,
                ema_8=ema_8, ema_21=ema_21, atr=atr,
            ),
        )
        sig = strat.on_context(ctx)
        return strat, sig

    def test_short_entry_all_conditions_met(self):
        """RSI>75 + pct_b>0.95 + ADX<25 + momentum fading -> short signal."""
        _, sig = self._trigger_entry()
        assert sig is not None
        assert sig.direction == "short"

    def test_direction_always_short_never_long(self):
        """OverboughtShort strategy must never produce a long signal."""
        _, sig = self._trigger_entry()
        assert sig is not None
        assert sig.direction == "short"
        assert sig.direction != "long"

    def test_signal_strategy_name(self):
        _, sig = self._trigger_entry()
        assert sig is not None
        assert sig.strategy == "overbought_short"

    def test_signal_symbol(self):
        _, sig = self._trigger_entry(symbol="AAPL")
        assert sig is not None
        assert sig.symbol == "AAPL"

    def test_strength_calculation(self):
        """Strength = min(1.0, (RSI-75)/25 + (pct_b-0.95)/0.05)."""
        # RSI=80, pct_b=0.98 -> (80-75)/25 + (0.98-0.95)/0.05 = 0.2 + 0.6 = 0.8
        _, sig = self._trigger_entry(rsi=80.0, pct_b=0.98)
        assert sig is not None
        assert abs(sig.strength - 0.8) < 1e-9

    def test_strength_clamps_at_1(self):
        """Strength should be clamped at 1.0 for extreme values."""
        # RSI=100, pct_b=1.0 -> (100-75)/25 + (1.0-0.95)/0.05 = 1.0 + 1.0 = 2.0 -> clamped to 1.0
        _, sig = self._trigger_entry(rsi=100.0, pct_b=1.0)
        assert sig is not None
        assert sig.strength == 1.0

    def test_strength_minimum_at_boundary(self):
        """Just at thresholds: RSI=75.01, pct_b=0.951 -> small positive strength."""
        _, sig = self._trigger_entry(rsi=75.01, pct_b=0.951)
        assert sig is not None
        assert sig.strength > 0.0
        assert sig.strength < 0.1

    def test_metadata_sub_strategy(self):
        _, sig = self._trigger_entry()
        assert sig is not None
        assert sig.metadata["sub_strategy"] == "overbought_short"

    def test_metadata_stop_loss_atr_based(self):
        """stop_loss = min(close + 2.5*ATR, close * 1.05)."""
        # close=100, ATR=2 -> ATR stop = 100+5=105, abs stop = 100*1.05=105 -> min=105
        _, sig = self._trigger_entry(close=100.0, atr=2.0)
        assert sig is not None
        assert "stop_loss" in sig.metadata
        assert abs(sig.metadata["stop_loss"] - 105.0) < 1e-9

    def test_metadata_stop_loss_absolute_tighter(self):
        """When 5% stop is tighter than ATR-based, use 5%."""
        # close=100, ATR=3 -> ATR stop = 100+7.5=107.5, abs stop = 105 -> min=105
        _, sig = self._trigger_entry(close=100.0, atr=3.0)
        assert sig is not None
        assert abs(sig.metadata["stop_loss"] - 105.0) < 1e-9

    def test_metadata_stop_loss_atr_tighter(self):
        """When ATR-based stop is tighter than 5%, use ATR stop."""
        # close=100, ATR=1 -> ATR stop = 100+2.5=102.5, abs stop = 105 -> min=102.5
        _, sig = self._trigger_entry(close=100.0, atr=1.0)
        assert sig is not None
        assert abs(sig.metadata["stop_loss"] - 102.5) < 1e-9

    def test_state_updated_on_entry(self):
        """After entry, internal state should reflect in_position=True."""
        strat, sig = self._trigger_entry(close=100.0)
        assert sig is not None
        state = strat._states["TEST"]
        assert state.in_position is True
        assert state.entry_price == 100.0
        assert state.bars_since_entry == 0


# ---------------------------------------------------------------------------
# 4. Exit conditions
# ---------------------------------------------------------------------------
class TestExits:
    def _enter_position(self, symbol: str = "TEST",
                        entry_close: float = 100.0,
                        atr: float = 2.0) -> OverboughtShort:
        """Prime momentum, trigger entry, return strategy in position."""
        strat = OverboughtShort()
        _prime_momentum(strat, symbol=symbol, ema_8=103.0, ema_21=100.0)
        ctx = _make_ctx(
            symbol=symbol,
            close=entry_close,
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=102.0, ema_21=100.0, atr=atr,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None and sig.direction == "short"
        return strat

    def test_exit_rsi_below_55(self):
        """RSI drops below 55 -> target exit."""
        strat = self._enter_position(entry_close=100.0, atr=2.0)
        ctx = _make_ctx(
            close=97.0,
            indicators=_full_indicators(
                rsi=50.0, pct_b=0.60, adx=20.0,
                ema_8=99.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata["exit_reason"] == "target"

    def test_exit_pct_b_below_050(self):
        """BB %B drops below 0.50 -> target exit."""
        strat = self._enter_position(entry_close=100.0, atr=2.0)
        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=60.0, pct_b=0.45, adx=20.0,
                ema_8=99.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata["exit_reason"] == "target"

    def test_exit_atr_stop_loss(self):
        """close >= entry + 2.5*ATR -> stop_loss exit (ATR stop tighter than 5%)."""
        # entry=100, ATR=1.5 -> ATR stop = 100+3.75=103.75, abs stop = 105
        # close=104 >= 103.75 but < 105 -> ATR stop triggers, not absolute
        strat = self._enter_position(entry_close=100.0, atr=1.5)
        ctx = _make_ctx(
            close=104.0,
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=103.0, ema_21=100.0, atr=1.5,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata["exit_reason"] == "stop_loss"

    def test_exit_absolute_stop_5pct(self):
        """close >= entry * 1.05 -> absolute_stop exit."""
        # entry=100, 5% stop = 105. ATR=1 -> ATR stop = 102.5 (tighter)
        # So use ATR=3 -> ATR stop = 107.5. Now 5% at 105 is tighter.
        # close=105.5 >= 105 but < 107.5 -> absolute_stop triggers
        strat = self._enter_position(entry_close=100.0, atr=3.0)
        ctx = _make_ctx(
            close=105.5,
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=103.0, ema_21=100.0, atr=3.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata["exit_reason"] == "absolute_stop"

    def test_exit_timeout_5_bars(self):
        """After 5 bars in position with no other exit -> timeout."""
        strat = self._enter_position(entry_close=100.0, atr=2.0)
        # Feed 4 bars that do not trigger any exit (RSI still high, pct_b high,
        # price below stop)
        for _ in range(4):
            ctx = _make_ctx(
                close=101.0,
                indicators=_full_indicators(
                    rsi=70.0, pct_b=0.80, adx=20.0,
                    ema_8=101.0, ema_21=100.0, atr=2.0,
                ),
            )
            sig = strat.on_context(ctx)
            # These should not trigger exit (RSI 70 >= 55, pct_b 0.80 >= 0.50,
            # close 101 < 105 stop, bars < 5)
            assert sig is None

        # 5th bar -> timeout
        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(
                rsi=70.0, pct_b=0.80, adx=20.0,
                ema_8=101.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "close"
        assert sig.metadata["exit_reason"] == "timeout"

    def test_exit_signal_strength_is_1(self):
        """All exit signals should have strength=1.0."""
        strat = self._enter_position(entry_close=100.0, atr=2.0)
        ctx = _make_ctx(
            close=97.0,
            indicators=_full_indicators(
                rsi=50.0, pct_b=0.40, adx=20.0,
                ema_8=99.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.strength == 1.0

    def test_state_reset_after_exit(self):
        """After exit, in_position should be False."""
        strat = self._enter_position(entry_close=100.0, atr=2.0)
        ctx = _make_ctx(
            close=97.0,
            indicators=_full_indicators(
                rsi=50.0, pct_b=0.40, adx=20.0,
                ema_8=99.0, ema_21=100.0, atr=2.0,
            ),
        )
        strat.on_context(ctx)
        state = strat._states["TEST"]
        assert state.in_position is False

    def test_no_exit_when_not_in_position(self):
        """No exit signal when not in position even with exit conditions."""
        strat = OverboughtShort()
        ctx = _make_ctx(
            indicators=_full_indicators(
                rsi=50.0, pct_b=0.40, adx=20.0,
                ema_8=99.0, ema_21=100.0, atr=2.0,
            ),
        )
        assert strat.on_context(ctx) is None


# ---------------------------------------------------------------------------
# 5. EMA spread tracking
# ---------------------------------------------------------------------------
class TestEmaSpreadTracking:
    def test_spread_tracked_across_bars(self):
        """prev_ema_spread should update after each bar."""
        strat = OverboughtShort()
        ctx1 = _make_ctx(
            indicators=_full_indicators(
                rsi=60.0, pct_b=0.50, adx=20.0,
                ema_8=103.0, ema_21=100.0, atr=2.0,
            ),
        )
        strat.on_context(ctx1)
        state = strat._states["TEST"]
        assert state.prev_ema_spread == pytest.approx(3.0)

        ctx2 = _make_ctx(
            indicators=_full_indicators(
                rsi=60.0, pct_b=0.50, adx=20.0,
                ema_8=101.5, ema_21=100.0, atr=2.0,
            ),
        )
        strat.on_context(ctx2)
        assert state.prev_ema_spread == pytest.approx(1.5)

    def test_momentum_fading_detected_when_spread_narrows(self):
        """Narrowing EMA spread triggers momentum fading -> entry allowed."""
        strat = OverboughtShort()
        # Bar 1: wide spread
        _prime_momentum(strat, ema_8=105.0, ema_21=100.0)
        # Bar 2: narrower spread + all entry conditions
        ctx = _make_ctx(
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=103.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is not None
        assert sig.direction == "short"

    def test_momentum_not_fading_when_spread_widens(self):
        """Widening EMA spread -> momentum increasing -> no entry."""
        strat = OverboughtShort()
        _prime_momentum(strat, ema_8=101.0, ema_21=100.0)
        ctx = _make_ctx(
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=104.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is None

    def test_momentum_not_fading_when_spread_equal(self):
        """Equal EMA spread -> not narrowing -> no entry."""
        strat = OverboughtShort()
        _prime_momentum(strat, ema_8=102.0, ema_21=100.0)
        ctx = _make_ctx(
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=102.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig = strat.on_context(ctx)
        assert sig is None


# ---------------------------------------------------------------------------
# 6. Per-symbol isolation
# ---------------------------------------------------------------------------
class TestSymbolIsolation:
    def test_independent_states_per_symbol(self):
        strat = OverboughtShort()
        ctx_a = _make_ctx(
            symbol="AAPL",
            indicators=_full_indicators(ema_8=103.0, ema_21=100.0),
        )
        ctx_b = _make_ctx(
            symbol="MSFT",
            indicators=_full_indicators(ema_8=105.0, ema_21=100.0),
        )
        strat.on_context(ctx_a)
        strat.on_context(ctx_b)
        assert "AAPL" in strat._states
        assert "MSFT" in strat._states
        assert strat._states["AAPL"] is not strat._states["MSFT"]
        assert strat._states["AAPL"].prev_ema_spread == pytest.approx(3.0)
        assert strat._states["MSFT"].prev_ema_spread == pytest.approx(5.0)

    def test_entry_on_one_symbol_does_not_affect_other(self):
        strat = OverboughtShort()
        # Prime both symbols
        _prime_momentum(strat, symbol="AAPL", ema_8=103.0, ema_21=100.0)
        _prime_momentum(strat, symbol="MSFT", ema_8=103.0, ema_21=100.0)

        # Enter AAPL
        ctx_a = _make_ctx(
            symbol="AAPL",
            close=100.0,
            indicators=_full_indicators(
                rsi=80.0, pct_b=0.98, adx=20.0,
                ema_8=102.0, ema_21=100.0, atr=2.0,
            ),
        )
        sig_a = strat.on_context(ctx_a)
        assert sig_a is not None
        assert strat._states["AAPL"].in_position is True
        assert strat._states["MSFT"].in_position is False
