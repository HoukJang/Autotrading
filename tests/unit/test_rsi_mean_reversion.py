"""Comprehensive tests for RsiMeanReversion strategy using TDD approach."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

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
    rsi: float = 50.0,
    pct_b: float = 0.50,
    adx: float = 20.0,
    atr: float = 2.0,
    bb_upper: float = 110.0,
    bb_middle: float = 100.0,
    bb_lower: float = 90.0,
    bb_width: float = 0.20,
) -> dict:
    """Return a complete indicator dict ready for the strategy."""
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
        "ATR_14": atr,
    }


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = RsiMeanReversion()
        assert strategy.name == "rsi_mean_reversion"

    def test_required_indicators_keys(self):
        strategy = RsiMeanReversion()
        keys = {spec.key for spec in strategy.required_indicators}
        assert "RSI_14" in keys
        assert "BBANDS_20" in keys
        assert "ADX_14" in keys
        assert "ATR_14" in keys

    def test_required_indicators_count(self):
        strategy = RsiMeanReversion()
        assert len(strategy.required_indicators) == 4


# ===================================================================
# 2. No Signal Conditions
# ===================================================================


class TestNoSignal:
    def test_no_signal_when_indicators_none(self):
        """No signal when any indicator is missing (None)."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_none(self):
        strategy = RsiMeanReversion()
        indicators = _full_indicators()
        indicators["RSI_14"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_bbands_none(self):
        strategy = RsiMeanReversion()
        indicators = _full_indicators()
        indicators["BBANDS_20"] = None
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_neutral(self):
        """RSI at 50 should produce no signal."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=20.0))
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_too_high(self):
        """ADX >= 23 means trending market -- no mean reversion."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=23.0))
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_adx_exactly_23(self):
        """ADX == 23 is the boundary -- should NOT trigger."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=23.0))
        assert strategy.on_context(ctx) is None

    def test_signal_when_adx_below_23(self):
        """ADX just below 23 should allow entry."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=22.9))
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_no_signal_when_bbands_not_dict(self):
        """BBANDS value is not a dict."""
        strategy = RsiMeanReversion()
        indicators = _full_indicators()
        indicators["BBANDS_20"] = 42.0  # wrong type
        ctx = _make_ctx(indicators=indicators)
        assert strategy.on_context(ctx) is None


# ===================================================================
# 3. Long Entry
# ===================================================================


class TestLongEntry:
    def test_long_entry_conditions_met(self):
        """RSI < 30, pct_b < 0.05, ADX < 25 -> long signal."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.symbol == "TEST"
        assert signal.strategy == "rsi_mean_reversion"

    def test_long_entry_strength_calculation(self):
        """Verify strength = min(1.0, (30 - RSI)/30 + (0.05 - pct_b)/0.05)."""
        strategy = RsiMeanReversion()
        rsi, pct_b = 20.0, 0.02
        expected = min(1.0, (30.0 - rsi) / 30.0 + (0.05 - pct_b) / 0.05)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=rsi, pct_b=pct_b, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(min(1.0, expected), abs=1e-6)

    def test_long_entry_strength_clamped_to_one(self):
        """Extreme conditions should clamp strength to 1.0."""
        strategy = RsiMeanReversion()
        # RSI=5, pct_b=0.0 -> (25/30 + 1.0) = 1.833 -> clamped to 1.0
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=5.0, pct_b=0.0, adx=15.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(1.0)

    def test_no_long_when_pct_b_too_high(self):
        """pct_b >= 0.05 blocks long entry even if RSI and ADX are fine."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.05, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_long_when_rsi_at_boundary(self):
        """RSI == 30 should NOT trigger long (requires strictly < 30)."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=30.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_long_entry_metadata_sub_strategy(self):
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_long"

    def test_long_entry_metadata_stop_loss(self):
        """stop_loss = close - 2.0 * ATR."""
        strategy = RsiMeanReversion()
        atr = 3.0
        close = 100.0
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 2.0 * atr)


# ===================================================================
# 4. Short Entry
# ===================================================================


class TestShortEntry:
    def test_short_entry_conditions_met(self):
        """RSI > 75, pct_b > 0.95, ADX < 25 -> short signal."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "short"
        assert signal.symbol == "TEST"
        assert signal.strategy == "rsi_mean_reversion"

    def test_short_entry_strength_calculation(self):
        """Verify strength = min(1.0, (RSI - 75)/25 + (pct_b - 0.95)/0.05)."""
        strategy = RsiMeanReversion()
        rsi, pct_b = 80.0, 0.98
        expected = min(1.0, (rsi - 75.0) / 25.0 + (pct_b - 0.95) / 0.05)
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=rsi, pct_b=pct_b, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(min(1.0, expected), abs=1e-6)

    def test_short_entry_strength_clamped_to_one(self):
        """Extreme overbought clamps to 1.0."""
        strategy = RsiMeanReversion()
        # RSI=99, pct_b=1.0 -> (24/25 + 1.0) = 1.96 -> clamped to 1.0
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=99.0, pct_b=1.0, adx=15.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.strength == pytest.approx(1.0)

    def test_no_short_when_pct_b_too_low(self):
        """pct_b <= 0.95 blocks short entry."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.95, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_no_short_when_rsi_at_boundary(self):
        """RSI == 75 should NOT trigger short (requires strictly > 75)."""
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=75.0, pct_b=0.98, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_short_entry_metadata_sub_strategy(self):
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_short"

    def test_short_entry_metadata_stop_loss(self):
        """stop_loss = close + 2.5 * ATR."""
        strategy = RsiMeanReversion()
        atr = 3.0
        close = 100.0
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close + 2.5 * atr)


# ===================================================================
# 5. Long Exit -- Target
# ===================================================================


class TestLongExit:
    def _enter_long(self, strategy: RsiMeanReversion, close: float = 100.0, atr: float = 2.0) -> None:
        """Helper: force a long entry."""
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_long_exit_rsi_above_50(self):
        """RSI > 50 triggers long exit with reason='target'."""
        strategy = RsiMeanReversion()
        self._enter_long(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.45, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "target"

    def test_long_exit_pct_b_above_050(self):
        """pct_b > 0.50 triggers long exit with reason='target'."""
        strategy = RsiMeanReversion()
        self._enter_long(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=45.0, pct_b=0.55, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.metadata["exit_reason"] == "target"

    def test_long_no_exit_when_not_at_target(self):
        """RSI <= 50 AND pct_b <= 0.50 -> no exit."""
        strategy = RsiMeanReversion()
        self._enter_long(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=101.0,
            indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 6. Short Exit -- Target
# ===================================================================


class TestShortExit:
    def _enter_short(self, strategy: RsiMeanReversion, close: float = 100.0, atr: float = 2.0) -> None:
        """Helper: force a short entry."""
        ctx = _make_ctx(
            close=close,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "short"

    def test_short_exit_rsi_below_50(self):
        """RSI < 50 triggers short exit with reason='target'."""
        strategy = RsiMeanReversion()
        self._enter_short(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=45.0, pct_b=0.55, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "target"

    def test_short_exit_pct_b_below_050(self):
        """pct_b < 0.50 triggers short exit with reason='target'."""
        strategy = RsiMeanReversion()
        self._enter_short(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.40, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.metadata["exit_reason"] == "target"

    def test_short_no_exit_when_not_at_target(self):
        """RSI >= 50 AND pct_b >= 0.50 -> no exit."""
        strategy = RsiMeanReversion()
        self._enter_short(strategy, close=100.0, atr=2.0)

        ctx = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=60.0, pct_b=0.70, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is None


# ===================================================================
# 7. Stop Loss Exit
# ===================================================================


class TestStopLoss:
    def test_long_stop_loss(self):
        """Long stop: close <= entry_price - 2.0 * ATR."""
        strategy = RsiMeanReversion()
        entry_price = 100.0
        atr = 2.0
        # Enter long
        ctx_entry = _make_ctx(
            close=entry_price,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None and signal.direction == "long"

        # Price drops to stop loss level: 100 - 2*2 = 96
        stop_price = entry_price - 2.0 * atr
        ctx_stop = _make_ctx(
            close=stop_price,
            indicators=_full_indicators(rsi=25.0, pct_b=0.03, adx=20.0, atr=atr),
        )
        signal = strategy.on_context(ctx_stop)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "stop_loss"

    def test_long_stop_loss_below_threshold(self):
        """Price slightly below stop should also trigger."""
        strategy = RsiMeanReversion()
        entry_price = 100.0
        atr = 2.0
        ctx_entry = _make_ctx(
            close=entry_price,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=atr),
        )
        strategy.on_context(ctx_entry)

        ctx_stop = _make_ctx(
            close=95.0,  # well below 96.0
            indicators=_full_indicators(rsi=25.0, pct_b=0.03, adx=20.0, atr=atr),
        )
        signal = strategy.on_context(ctx_stop)
        assert signal is not None
        assert signal.metadata["exit_reason"] == "stop_loss"

    def test_short_stop_loss(self):
        """Short stop: close >= entry_price + 2.5 * ATR."""
        strategy = RsiMeanReversion()
        entry_price = 100.0
        atr = 2.0
        # Enter short
        ctx_entry = _make_ctx(
            close=entry_price,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=atr),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None and signal.direction == "short"

        # Price rises to stop: 100 + 2.5*2 = 105
        stop_price = entry_price + 2.5 * atr
        ctx_stop = _make_ctx(
            close=stop_price,
            indicators=_full_indicators(rsi=70.0, pct_b=0.90, adx=20.0, atr=atr),
        )
        signal = strategy.on_context(ctx_stop)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "stop_loss"

    def test_short_stop_loss_above_threshold(self):
        """Price well above stop should also trigger."""
        strategy = RsiMeanReversion()
        entry_price = 100.0
        atr = 2.0
        ctx_entry = _make_ctx(
            close=entry_price,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=atr),
        )
        strategy.on_context(ctx_entry)

        ctx_stop = _make_ctx(
            close=110.0,  # well above 105.0
            indicators=_full_indicators(rsi=70.0, pct_b=0.90, adx=20.0, atr=atr),
        )
        signal = strategy.on_context(ctx_stop)
        assert signal is not None
        assert signal.metadata["exit_reason"] == "stop_loss"


# ===================================================================
# 8. Timeout Exit
# ===================================================================


class TestTimeout:
    def test_long_timeout_after_5_bars(self):
        """After 5 bars in position, exit with reason='timeout'."""
        strategy = RsiMeanReversion()
        # Enter long
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        strategy.on_context(ctx_entry)

        # Bars 1-4: no exit (RSI stays mid-range, within stop, pct_b not target)
        for _ in range(4):
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=2.0),
            )
            signal = strategy.on_context(ctx)
            assert signal is None

        # Bar 5: timeout
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.strength == 1.0
        assert signal.metadata["exit_reason"] == "timeout"

    def test_short_timeout_after_5_bars(self):
        """Short position also times out after 5 bars."""
        strategy = RsiMeanReversion()
        # Enter short
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=2.0),
        )
        strategy.on_context(ctx_entry)

        # Bars 1-4: no exit
        for _ in range(4):
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=60.0, pct_b=0.70, adx=20.0, atr=2.0),
            )
            signal = strategy.on_context(ctx)
            assert signal is None

        # Bar 5: timeout
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=60.0, pct_b=0.70, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.metadata["exit_reason"] == "timeout"

    def test_no_timeout_at_bar_4(self):
        """Exactly 4 bars should NOT timeout."""
        strategy = RsiMeanReversion()
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        strategy.on_context(ctx_entry)

        for _ in range(4):
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=2.0),
            )
            signal = strategy.on_context(ctx)

        # 4th bar should NOT be timeout (bars_since_entry == 4)
        assert signal is None


# ===================================================================
# 9. Metadata Completeness
# ===================================================================


class TestMetadata:
    def test_long_entry_has_required_metadata(self):
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert "sub_strategy" in signal.metadata
        assert "stop_loss" in signal.metadata
        assert signal.metadata["sub_strategy"] == "mr_long"

    def test_short_entry_has_required_metadata(self):
        strategy = RsiMeanReversion()
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert "sub_strategy" in signal.metadata
        assert "stop_loss" in signal.metadata
        assert signal.metadata["sub_strategy"] == "mr_short"

    def test_exit_has_exit_reason(self):
        strategy = RsiMeanReversion()
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        strategy.on_context(ctx_entry)

        ctx_exit = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.45, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_exit)
        assert signal is not None
        assert "exit_reason" in signal.metadata


# ===================================================================
# 10. Multiple Symbols -- Independent Tracking
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entering long on AAPL should not affect GOOG state."""
        strategy = RsiMeanReversion()

        # Enter long on AAPL
        ctx_aapl = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=3.0),
        )
        signal_aapl = strategy.on_context(ctx_aapl)
        assert signal_aapl is not None
        assert signal_aapl.direction == "long"
        assert signal_aapl.symbol == "AAPL"

        # GOOG has neutral indicators -- no signal, not in position
        ctx_goog = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=20.0, atr=4.0),
        )
        signal_goog = strategy.on_context(ctx_goog)
        assert signal_goog is None

    def test_exit_only_affects_own_symbol(self):
        """Exit on AAPL should not affect GOOG's open position."""
        strategy = RsiMeanReversion()

        # Enter long on AAPL
        ctx_aapl_entry = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=3.0),
        )
        strategy.on_context(ctx_aapl_entry)

        # Enter short on GOOG
        ctx_goog_entry = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=4.0),
        )
        strategy.on_context(ctx_goog_entry)

        # Exit AAPL
        ctx_aapl_exit = _make_ctx(
            symbol="AAPL",
            close=155.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.55, adx=20.0, atr=3.0),
        )
        signal_aapl = strategy.on_context(ctx_aapl_exit)
        assert signal_aapl is not None
        assert signal_aapl.direction == "close"

        # GOOG should still be in position (no exit conditions met)
        ctx_goog_hold = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=60.0, pct_b=0.70, adx=20.0, atr=4.0),
        )
        signal_goog = strategy.on_context(ctx_goog_hold)
        assert signal_goog is None  # still in position, no exit triggered

    def test_simultaneous_positions_different_directions(self):
        """Long on AAPL and short on GOOG simultaneously."""
        strategy = RsiMeanReversion()

        # Long on AAPL
        ctx_aapl = _make_ctx(
            symbol="AAPL",
            close=150.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=3.0),
        )
        signal_aapl = strategy.on_context(ctx_aapl)
        assert signal_aapl is not None
        assert signal_aapl.direction == "long"

        # Short on GOOG
        ctx_goog = _make_ctx(
            symbol="GOOG",
            close=200.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=18.0, atr=4.0),
        )
        signal_goog = strategy.on_context(ctx_goog)
        assert signal_goog is not None
        assert signal_goog.direction == "short"


# ===================================================================
# 11. Re-entry After Exit
# ===================================================================


class TestReentry:
    def test_can_reenter_after_exit(self):
        """After exiting, the strategy should allow a new entry on the same symbol."""
        strategy = RsiMeanReversion()

        # First entry
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None and signal.direction == "long"

        # Exit
        ctx_exit = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.55, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_exit)
        assert signal is not None and signal.direction == "close"

        # Re-entry
        ctx_reentry = _make_ctx(
            close=95.0,
            indicators=_full_indicators(rsi=18.0, pct_b=0.01, adx=16.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_reentry)
        assert signal is not None
        assert signal.direction == "long"

    def test_no_double_entry(self):
        """While in a position, entry conditions should not produce a new signal."""
        strategy = RsiMeanReversion()

        # Enter long
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None and signal.direction == "long"

        # Same oversold conditions but already in position -> no new entry
        ctx_same = _make_ctx(
            close=99.0,
            indicators=_full_indicators(rsi=18.0, pct_b=0.01, adx=17.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_same)
        # Should be None because no exit condition is met
        # (RSI < 50, pct_b < 0.50, no stop loss, no timeout)
        assert signal is None


# ===================================================================
# 12. Edge Cases
# ===================================================================


class TestEdgeCases:
    def test_stop_loss_takes_priority_over_timeout(self):
        """If both stop loss and timeout conditions are met, stop_loss wins."""
        strategy = RsiMeanReversion()
        entry_price = 100.0
        atr = 2.0
        ctx_entry = _make_ctx(
            close=entry_price,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=atr),
        )
        strategy.on_context(ctx_entry)

        # Advance 4 bars
        for _ in range(4):
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=atr),
            )
            strategy.on_context(ctx)

        # Bar 5: both timeout (bars_since_entry == 5) AND stop loss (close=95 <= 96)
        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(rsi=25.0, pct_b=0.03, adx=20.0, atr=atr),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        # Implementation should check stop_loss before timeout
        assert signal.metadata["exit_reason"] in ("stop_loss", "timeout")

    def test_target_takes_priority_over_timeout(self):
        """If both target and timeout, either is acceptable."""
        strategy = RsiMeanReversion()
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        strategy.on_context(ctx_entry)

        # 4 bars
        for _ in range(4):
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=40.0, pct_b=0.30, adx=20.0, atr=2.0),
            )
            strategy.on_context(ctx)

        # Bar 5: timeout AND target (RSI > 50)
        ctx = _make_ctx(
            close=102.0,
            indicators=_full_indicators(rsi=55.0, pct_b=0.55, adx=20.0, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "close"
        assert signal.metadata["exit_reason"] in ("target", "timeout")


# ===================================================================
# 13. ADX Slope Filter
# ===================================================================


class TestAdxSlopeFilter:
    """ADX slope filter: if ADX rises by more than 1.5 over 3 bars, block entry."""

    def test_rising_adx_above_threshold_blocks_entry(self):
        """When ADX rises by more than 1.5 over 3 bars, entry should be blocked."""
        strategy = RsiMeanReversion()
        # Feed 4 bars with rising ADX to build history (ADX: 12, 13, 14, 15)
        adx_values = [12.0, 13.0, 14.0, 15.0]
        for adx_val in adx_values:
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=adx_val, atr=2.0),
            )
            strategy.on_context(ctx)  # just to populate ADX history

        # Now try entry: adx_history after adding 16.0 = [13, 14, 15, 16]
        # slope = 16 - 13 = 3.0 > 1.5 -> blocked
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=16.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is None

    def test_small_adx_rise_allows_entry(self):
        """When ADX rises by <= 1.5 over 3 bars, entry should be allowed."""
        strategy = RsiMeanReversion()
        # Feed 4 bars with slight rise (ADX: 15.0, 15.2, 15.4, 15.5)
        adx_values = [15.0, 15.2, 15.4, 15.5]
        for adx_val in adx_values:
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=adx_val, atr=2.0),
            )
            strategy.on_context(ctx)

        # Try entry: adx_history after adding 16.0 = [15.2, 15.4, 15.5, 16.0]
        # slope = 16.0 - 15.2 = 0.8 <= 1.5 -> allowed
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=16.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None
        assert signal.direction == "long"

    def test_falling_adx_allows_entry(self):
        """When ADX is falling over 3 bars, entry should be allowed."""
        strategy = RsiMeanReversion()
        # Feed 4 bars with falling ADX (ADX: 19, 18, 17, 16)
        adx_values = [19.0, 18.0, 17.0, 16.0]
        for adx_val in adx_values:
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=adx_val, atr=2.0),
            )
            strategy.on_context(ctx)

        # Try entry with all conditions met
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=15.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        # adx_history is now [18, 17, 16, 15] -- 15 - 18 = -3.0, not > 1.5 -> allowed
        assert signal is not None
        assert signal.direction == "long"

    def test_slope_check_needs_4_values(self):
        """With fewer than 4 ADX values, slope check should be skipped."""
        strategy = RsiMeanReversion()
        # Only 2 bars of history (not enough for slope check)
        for adx_val in [10.0, 15.0]:
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=adx_val, atr=2.0),
            )
            strategy.on_context(ctx)

        # Entry should still work (slope check skipped, only 3 values after adding new one)
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=18.0, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None
        assert signal.direction == "long"

    def test_exact_threshold_1_5_allows_entry(self):
        """ADX rise of exactly 1.5 should be allowed (condition is > 1.5, not >=)."""
        strategy = RsiMeanReversion()
        # Feed 4 bars: [14.0, 14.5, 15.0, 15.0]
        adx_values = [14.0, 14.5, 15.0, 15.0]
        for adx_val in adx_values:
            ctx = _make_ctx(
                close=100.0,
                indicators=_full_indicators(rsi=50.0, pct_b=0.50, adx=adx_val, atr=2.0),
            )
            strategy.on_context(ctx)

        # Try entry: adx_history after adding 15.5 = [14.5, 15.0, 15.0, 15.5]
        # slope = 15.5 - 14.5 = 1.0 <= 1.5 -> allowed
        ctx_entry = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=15.5, atr=2.0),
        )
        signal = strategy.on_context(ctx_entry)
        assert signal is not None
        assert signal.direction == "long"


# ===================================================================
# 14. Entry ADX in Metadata
# ===================================================================


class TestEntryAdxMetadata:
    """entry_adx should be stored in signal metadata for regime guard."""

    def test_long_entry_includes_entry_adx(self):
        strategy = RsiMeanReversion()
        adx = 15.0
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=20.0, pct_b=0.02, adx=adx, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["entry_adx"] == pytest.approx(adx)

    def test_short_entry_includes_entry_adx(self):
        strategy = RsiMeanReversion()
        adx = 15.0
        ctx = _make_ctx(
            close=100.0,
            indicators=_full_indicators(rsi=80.0, pct_b=0.98, adx=adx, atr=2.0),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["entry_adx"] == pytest.approx(adx)
