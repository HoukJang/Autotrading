"""Unit tests for AdaptiveMeanReversion strategy.

Tests cover:
- Name and required indicators
- ADX regime filter (ADX >= 25 blocks entry)
- ADX slope filter (rising ADX blocks entry)
- Long Gate A (BB/RSI extreme, no EMA50 filter)
- Long Gate B (consecutive down days + RSI < 40, no EMA50 filter)
- Short Gate A (BB/RSI extreme + close > EMA50)
- No short via Gate B (Gate B is long-only)
- Exit: BB/RSI target, EMA(5), timeout
- Signal metadata (stop_loss, entry_adx, sub_strategy)
- Signal strength clamping [0.0, 1.0]
- Multiple symbol independence
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import pytest

from autotrader.core.types import Bar, MarketContext
from autotrader.strategy.adaptive_mean_reversion import AdaptiveMeanReversion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: float = 1_000_000,
    symbol: str = "TEST",
    timestamp: datetime | None = None,
) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=timestamp or datetime(2024, 6, 15, tzinfo=timezone.utc),
        open=open_ if open_ is not None else close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=volume,
    )


def _full_indicators(
    rsi: float = 35.0,
    adx: float = 18.0,
    atr: float = 2.0,
    pct_b: float = 0.10,
    ema_50: float = 105.0,
    ema_5: float = 98.0,
) -> dict:
    """Return a complete indicator dict for AdaptiveMeanReversion."""
    return {
        "RSI_14": rsi,
        "ADX_14": adx,
        "ATR_14": atr,
        "EMA_50": ema_50,
        "EMA_5": ema_5,
        "BBANDS_20": {
            "pct_b": pct_b,
            "upper": 110.0,
            "lower": 90.0,
            "middle": 100.0,
        },
    }


def _make_ctx(
    close: float = 100.0,
    indicators: dict | None = None,
    history: deque | None = None,
    history_len: int = 60,
    symbol: str = "TEST",
) -> MarketContext:
    """Create a MarketContext with optional history."""
    bar = _make_bar(close=close, symbol=symbol)
    if history is None:
        history = deque(maxlen=500)
        for i in range(history_len):
            history.append(_make_bar(close=100.0 + i * 0.1, symbol=symbol))
    history.append(bar)
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


def _make_ctx_with_descending_history(
    close: float | None = None,
    indicators: dict | None = None,
    down_days: int = 3,
    base_close: float = 100.0,
    symbol: str = "TEST",
) -> MarketContext:
    """Create a MarketContext with consecutive down closes for Gate B testing.

    The current bar close defaults to ``base_close - (down_days + 1)`` so
    that the current bar itself counts as another down day, giving a total
    consecutive-down count equal to ``down_days``.  With ``down_days=3`` and
    ``base_close=100`` the history ends:  ...100, 99, 98, 97, **96** where
    the bold value is the current bar.  That gives 4 transitions
    (100->99->98->97->96) but the *first* transition (100->99) anchors the
    series so the consecutive down count is ``4`` -- however we only need
    ``down_days`` transitions *inside* the descending segment, so we create
    ``down_days - 1`` descending history bars and let the current bar be the
    final step down.
    """
    # down_days-1 history bars descend from base, current bar is one more step
    if close is None:
        close = base_close - down_days * 1.0

    bar = _make_bar(close=close, symbol=symbol)
    history: deque[Bar] = deque(maxlen=500)
    # Pad with flat bars
    for i in range(57):
        history.append(_make_bar(close=base_close, symbol=symbol))
    # Descending history bars (down_days - 1 steps down from base)
    for i in range(down_days - 1):
        desc_close = base_close - (i + 1) * 1.0
        history.append(_make_bar(close=desc_close, symbol=symbol))
    # Append current bar (one more step down)
    history.append(bar)
    return MarketContext(
        symbol=symbol,
        bar=bar,
        indicators=indicators or {},
        history=history,
    )


def _prime_adx_history(
    strategy: AdaptiveMeanReversion,
    symbol: str,
    adx_values: list[float],
) -> None:
    """Feed bars to build ADX history without triggering entry."""
    for adx_val in adx_values:
        ctx = _make_ctx(
            close=100.0,
            symbol=symbol,
            indicators=_full_indicators(
                rsi=50.0,
                adx=adx_val,
                pct_b=0.50,  # neutral -- won't trigger any gate
                ema_50=100.0,  # close == ema_50 -- blocks entry
            ),
        )
        strategy.on_context(ctx)


def _enter_long_gate_a(
    strategy: AdaptiveMeanReversion,
    symbol: str = "TEST",
    close: float = 95.0,
    adx: float = 18.0,
    rsi: float = 30.0,
    pct_b: float = 0.10,
    atr: float = 2.0,
    ema_50: float = 105.0,
    ema_5: float = 93.0,
) -> "Signal | None":
    """Helper to produce a long entry via Gate A."""
    ctx = _make_ctx(
        close=close,
        symbol=symbol,
        indicators=_full_indicators(
            rsi=rsi, adx=adx, atr=atr, pct_b=pct_b,
            ema_50=ema_50, ema_5=ema_5,
        ),
    )
    return strategy.on_context(ctx)


def _enter_short_gate_a(
    strategy: AdaptiveMeanReversion,
    symbol: str = "TEST",
    close: float = 110.0,
    adx: float = 18.0,
    rsi: float = 75.0,
    pct_b: float = 0.90,
    atr: float = 2.0,
    ema_50: float = 100.0,
    ema_5: float = 112.0,
) -> "Signal | None":
    """Helper to produce a short entry via Gate A."""
    ctx = _make_ctx(
        close=close,
        symbol=symbol,
        indicators=_full_indicators(
            rsi=rsi, adx=adx, atr=atr, pct_b=pct_b,
            ema_50=ema_50, ema_5=ema_5,
        ),
    )
    return strategy.on_context(ctx)


# ===================================================================
# 1. Initialization
# ===================================================================


class TestInit:
    def test_name(self):
        strategy = AdaptiveMeanReversion()
        assert strategy.name == "adaptive_mean_reversion"

    def test_required_indicators(self):
        strategy = AdaptiveMeanReversion()
        keys = {spec.key for spec in strategy.required_indicators}
        expected = {"RSI_14", "BBANDS_20", "ADX_14", "ATR_14", "EMA_50", "EMA_5"}
        assert keys == expected

    def test_required_indicators_count(self):
        strategy = AdaptiveMeanReversion()
        assert len(strategy.required_indicators) == 6


# ===================================================================
# 2. ADX Regime Filter
# ===================================================================


class TestADXFilter:
    def test_no_signal_adx_too_high(self):
        """ADX >= 25 blocks entry entirely."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=25.0, pct_b=0.10, ema_50=105.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_no_signal_adx_well_above_threshold(self):
        """ADX = 35 should block entry."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=35.0, pct_b=0.10, ema_50=105.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_signal_with_adx_just_below_threshold(self):
        """ADX = 24.9 should allow entry."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=24.9, pct_b=0.10, ema_50=105.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"

    def test_no_signal_adx_slope_too_steep(self):
        """ADX rising > 2.0 over last 3 bars blocks entry."""
        strategy = AdaptiveMeanReversion()
        # Build ADX history: 18.0, 19.0, 20.0, then entry bar at 21.0
        # Slope = 21.0 - 18.0 = 3.0 > 2.0
        _prime_adx_history(strategy, "TEST", [18.0, 19.0, 20.0])

        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=21.0, pct_b=0.10, ema_50=105.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_signal_with_adx_slope_at_boundary(self):
        """ADX slope of exactly 2.0 should block entry (> check)."""
        strategy = AdaptiveMeanReversion()
        # Build ADX history: 18.0, 19.0, 19.5 -> entry at 20.0
        # Slope = 20.0 - 18.0 = 2.0, but check is > 2.0, so this passes
        _prime_adx_history(strategy, "TEST", [18.0, 19.0, 19.5])

        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=20.0, pct_b=0.10, ema_50=105.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None

    def test_signal_with_adx_slope_just_above_boundary(self):
        """ADX slope of 2.1 should block entry."""
        strategy = AdaptiveMeanReversion()
        _prime_adx_history(strategy, "TEST", [18.0, 19.0, 19.5])

        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=20.1, pct_b=0.10, ema_50=105.0,
            ),
        )
        assert strategy.on_context(ctx) is None

    def test_adx_slope_skipped_with_insufficient_history(self):
        """With < 4 ADX history entries, slope check is skipped."""
        strategy = AdaptiveMeanReversion()
        # Only 1 prior bar (2 total ADX entries) -- slope check skipped
        _prime_adx_history(strategy, "TEST", [15.0])

        ctx = _make_ctx(
            close=95.0,
            indicators=_full_indicators(
                rsi=30.0, adx=20.0, pct_b=0.10, ema_50=105.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None


# ===================================================================
# 3. Long Entry -- Gate A
# ===================================================================


class TestLongGateA:
    def test_long_gate_a_entry(self):
        """pct_b < 0.30, RSI < 45, ADX < 25 -> long signal."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.strategy == "adaptive_mean_reversion"
        assert signal.symbol == "TEST"
        assert signal.metadata["sub_strategy"] == "mr_long_gate_a"

    def test_long_gate_a_no_signal_pct_b_too_high(self):
        """pct_b >= 0.30 blocks Gate A long."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy, pct_b=0.35, rsi=30.0)
        # pct_b 0.35 >= 0.30, Gate B won't fire (flat history, no consecutive down)
        assert signal is None

    def test_long_gate_a_no_signal_rsi_too_high(self):
        """RSI >= 45 blocks Gate A long (with pct_b that would pass)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy, pct_b=0.10, rsi=47.0)
        # Gate A: rsi 47 >= 45 -> fail
        # Gate B: no consecutive down -> fail
        assert signal is None

    def test_long_gate_a_entry_close_above_ema50(self):
        """close > EMA50 does NOT block long entry (EMA filter removed for longs)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(
            strategy, close=110.0, ema_50=105.0, pct_b=0.10, rsi=30.0,
        )
        # EMA(50) filter removed for longs -> Gate A still fires
        assert signal is not None
        assert signal.direction == "long"

    def test_long_gate_a_boundary_pct_b(self):
        """pct_b exactly 0.30 should NOT trigger (requires < 0.30)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy, pct_b=0.30, rsi=30.0)
        assert signal is None

    def test_long_gate_a_boundary_rsi(self):
        """RSI exactly 45.0 should NOT trigger (requires < 45.0)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy, pct_b=0.10, rsi=45.0)
        assert signal is None


# ===================================================================
# 4. Long Entry -- Gate B
# ===================================================================


class TestLongGateB:
    def test_long_gate_b_entry(self):
        """3+ consecutive down days + RSI < 40 -> long."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=3,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=35.0, adx=18.0, atr=2.0,
                pct_b=0.35,  # above Gate A threshold (0.30)
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.direction == "long"
        assert signal.metadata["sub_strategy"] == "mr_long_gate_b"
        assert signal.metadata["down_days"] >= 3

    def test_long_gate_b_insufficient_down_days(self):
        """Only 2 consecutive down days -> no Gate B signal."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=98.0,
            down_days=2,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=45.0, adx=18.0, atr=2.0,
                pct_b=0.30,  # above Gate A threshold
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_long_gate_b_rsi_too_high(self):
        """RSI >= 40 blocks Gate B."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=4,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=52.0, adx=18.0, atr=2.0,
                pct_b=0.30,
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is None

    def test_long_gate_b_close_above_ema50_still_works(self):
        """close > EMA50 does NOT block long entries (EMA filter removed).

        Gate B still requires RSI < 40 and 3+ down days.
        """
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=106.0,
            down_days=4,
            base_close=110.0,
            indicators=_full_indicators(
                rsi=35.0, adx=18.0, atr=2.0,
                pct_b=0.35,  # above Gate A threshold
                ema_50=105.0, ema_5=107.0,
            ),
        )
        signal = strategy.on_context(ctx)
        # EMA filter removed for longs, Gate B fires: rsi=35 < 40, down_days=4 >= 3
        assert signal is not None
        assert signal.direction == "long"
        assert signal.metadata["sub_strategy"] == "mr_long_gate_b"

    def test_gate_a_preferred_over_gate_b(self):
        """When both gates fire, Gate A takes priority (checked first)."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=4,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=30.0, adx=18.0, atr=2.0,
                pct_b=0.10,  # Gate A also passes
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_long_gate_a"


# ===================================================================
# 5. Short Entry -- Gate A
# ===================================================================


class TestShortGateA:
    def test_short_gate_a_entry(self):
        """pct_b > 0.80, RSI > 60, close > EMA50 -> short signal."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy)
        assert signal is not None
        assert signal.direction == "short"
        assert signal.strategy == "adaptive_mean_reversion"
        assert signal.metadata["sub_strategy"] == "mr_short_gate_a"

    def test_short_gate_a_no_signal_pct_b_too_low(self):
        """pct_b <= 0.80 blocks Gate A short."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy, pct_b=0.75, rsi=75.0)
        assert signal is None

    def test_short_gate_a_no_signal_rsi_too_low(self):
        """RSI <= 60 blocks Gate A short."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy, pct_b=0.90, rsi=58.0)
        assert signal is None

    def test_short_gate_a_no_signal_close_below_ema50(self):
        """close <= EMA50 blocks short entry."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(
            strategy, close=95.0, ema_50=100.0, pct_b=0.90, rsi=75.0,
        )
        # close=95 < ema_50=100 -> short branch skipped
        # long: pct_b=0.90 > 0.30 -> Gate A fails, rsi=75 > 40 -> Gate B fails
        assert signal is None

    def test_short_gate_a_boundary_pct_b(self):
        """pct_b exactly 0.80 should NOT trigger (requires > 0.80)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy, pct_b=0.80, rsi=75.0)
        assert signal is None

    def test_short_gate_a_boundary_rsi(self):
        """RSI exactly 60.0 should NOT trigger (requires > 60.0)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy, pct_b=0.90, rsi=60.0)
        assert signal is None

    def test_no_short_gate_b(self):
        """Gate B does not produce short entries (long-only gate)."""
        strategy = AdaptiveMeanReversion()
        # Create descending history but with close > EMA50 (short territory)
        # Gate B only checks in the long branch (close < EMA50)
        ctx = _make_ctx_with_descending_history(
            close=110.0,
            down_days=5,
            base_close=115.0,
            indicators=_full_indicators(
                rsi=55.0, adx=18.0, atr=2.0,
                pct_b=0.70,  # below Gate A short threshold
                ema_50=100.0, ema_5=112.0,
            ),
        )
        signal = strategy.on_context(ctx)
        # close=110 > ema_50=100 -> short branch, but pct_b=0.70 < 0.80 -> no short
        assert signal is None


# ===================================================================
# 6. Exit Logic
# ===================================================================


class TestExitLogic:
    def test_long_exit_rsi_target(self):
        """Long exits when RSI > 55."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None
        assert signal.direction == "long"

        # Next bar: RSI > 55 -> exit
        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=56.0, adx=18.0, pct_b=0.45, ema_50=105.0, ema_5=97.0,
            ),
        )
        exit_signal = strategy.on_context(ctx)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "target"

    def test_long_exit_pct_b_target(self):
        """Long exits when pct_b > 0.60."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=45.0, adx=18.0, pct_b=0.65, ema_50=105.0, ema_5=97.0,
            ),
        )
        exit_signal = strategy.on_context(ctx)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "target"

    def test_long_no_exit_below_targets(self):
        """Long stays open when RSI <= 55 AND pct_b <= 0.60 AND bars < 2."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        ctx = _make_ctx(
            close=94.0,
            indicators=_full_indicators(
                rsi=40.0, adx=18.0, pct_b=0.30, ema_50=105.0, ema_5=96.0,
            ),
        )
        result = strategy.on_context(ctx)
        assert result is None

    def test_short_exit_rsi_target(self):
        """Short exits when RSI < 45."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy)
        assert signal is not None
        assert signal.direction == "short"

        ctx = _make_ctx(
            close=108.0,
            indicators=_full_indicators(
                rsi=43.0, adx=18.0, pct_b=0.55, ema_50=100.0, ema_5=109.0,
            ),
        )
        exit_signal = strategy.on_context(ctx)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "target"

    def test_short_exit_pct_b_target(self):
        """Short exits when pct_b < 0.40."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy)
        assert signal is not None

        ctx = _make_ctx(
            close=108.0,
            indicators=_full_indicators(
                rsi=55.0, adx=18.0, pct_b=0.35, ema_50=100.0, ema_5=109.0,
            ),
        )
        exit_signal = strategy.on_context(ctx)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "target"

    def test_ema5_exit_long_after_min_bars(self):
        """Long exits when close > EMA(5) after 2+ bars."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        # Bar 1: stay in position (below targets, bars_since_entry=1)
        ctx1 = _make_ctx(
            close=94.0,
            indicators=_full_indicators(
                rsi=40.0, adx=18.0, pct_b=0.25, ema_50=105.0, ema_5=96.0,
            ),
        )
        assert strategy.on_context(ctx1) is None

        # Bar 2: close > EMA5, bars_since_entry=2 -> ema5_exit
        ctx2 = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=48.0, adx=18.0, pct_b=0.45, ema_50=105.0, ema_5=97.0,
            ),
        )
        exit_signal = strategy.on_context(ctx2)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "ema5_exit"

    def test_ema5_exit_not_before_min_bars(self):
        """EMA(5) exit should not fire on bar 1 (need >= 2 bars)."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        # Bar 1: close > EMA5 but only 1 bar in -> no EMA exit
        # Also ensure BB/RSI targets don't fire
        ctx1 = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=48.0, adx=18.0, pct_b=0.45, ema_50=105.0, ema_5=97.0,
            ),
        )
        result = strategy.on_context(ctx1)
        # pct_b=0.45 <= 0.60 and rsi=48 <= 55 -> no target exit
        # bars_since_entry=1 < 2 -> no EMA exit
        assert result is None

    def test_ema5_exit_short_after_min_bars(self):
        """Short exits when close < EMA(5) after 2+ bars."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy)
        assert signal is not None

        # Bar 1: stay in (above targets)
        ctx1 = _make_ctx(
            close=111.0,
            indicators=_full_indicators(
                rsi=60.0, adx=18.0, pct_b=0.75, ema_50=100.0, ema_5=110.0,
            ),
        )
        assert strategy.on_context(ctx1) is None

        # Bar 2: close < EMA5, bars_since_entry=2 -> ema5_exit
        ctx2 = _make_ctx(
            close=108.0,
            indicators=_full_indicators(
                rsi=52.0, adx=18.0, pct_b=0.55, ema_50=100.0, ema_5=109.0,
            ),
        )
        exit_signal = strategy.on_context(ctx2)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "ema5_exit"

    def test_timeout_exit(self):
        """bars_since_entry >= 7 triggers timeout exit."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        # Bars 1-6: stay in position (no targets hit, no EMA exit)
        for i in range(6):
            ctx = _make_ctx(
                close=94.0,
                indicators=_full_indicators(
                    rsi=40.0, adx=18.0, pct_b=0.25, ema_50=105.0, ema_5=96.0,
                ),
            )
            result = strategy.on_context(ctx)
            assert result is None, f"Unexpected exit on bar {i + 1}"

        # Bar 7: timeout
        ctx7 = _make_ctx(
            close=94.0,
            indicators=_full_indicators(
                rsi=40.0, adx=18.0, pct_b=0.25, ema_50=105.0, ema_5=96.0,
            ),
        )
        exit_signal = strategy.on_context(ctx7)
        assert exit_signal is not None
        assert exit_signal.direction == "close"
        assert exit_signal.metadata["exit_reason"] == "timeout"

    def test_target_takes_priority_over_ema5(self):
        """BB/RSI target should fire before EMA(5) check."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        # Bar 1: neutral
        ctx1 = _make_ctx(
            close=94.0,
            indicators=_full_indicators(
                rsi=40.0, adx=18.0, pct_b=0.25, ema_50=105.0, ema_5=96.0,
            ),
        )
        assert strategy.on_context(ctx1) is None

        # Bar 2: both RSI > 55 (target) and close > EMA5 (ema5_exit)
        # Target should take priority
        ctx2 = _make_ctx(
            close=100.0,
            indicators=_full_indicators(
                rsi=58.0, adx=18.0, pct_b=0.55, ema_50=105.0, ema_5=98.0,
            ),
        )
        exit_signal = strategy.on_context(ctx2)
        assert exit_signal is not None
        assert exit_signal.metadata["exit_reason"] == "target"


# ===================================================================
# 7. Signal Metadata
# ===================================================================


class TestMetadata:
    def test_signal_has_stop_loss_long(self):
        """Long signal: stop_loss = close - 2.5 * ATR."""
        strategy = AdaptiveMeanReversion()
        close = 95.0
        atr = 3.0
        signal = _enter_long_gate_a(strategy, close=close, atr=atr)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close - 2.5 * atr)

    def test_signal_has_stop_loss_short(self):
        """Short signal: stop_loss = close + 2.0 * ATR."""
        strategy = AdaptiveMeanReversion()
        close = 110.0
        atr = 3.0
        signal = _enter_short_gate_a(strategy, close=close, atr=atr)
        assert signal is not None
        assert signal.metadata["stop_loss"] == pytest.approx(close + 2.0 * atr)

    def test_signal_has_entry_adx(self):
        """Signal metadata must include entry_adx."""
        strategy = AdaptiveMeanReversion()
        adx = 20.0
        signal = _enter_long_gate_a(strategy, adx=adx)
        assert signal is not None
        assert signal.metadata["entry_adx"] == pytest.approx(adx)

    def test_gate_b_has_down_days_metadata(self):
        """Gate B signal metadata includes down_days count."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=4,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=35.0, adx=18.0, atr=2.0,
                pct_b=0.35,  # above Gate A threshold (0.30)
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert "down_days" in signal.metadata
        assert signal.metadata["down_days"] >= 3

    def test_sub_strategy_long_gate_a(self):
        """Gate A long -> sub_strategy == 'mr_long_gate_a'."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_long_gate_a"

    def test_sub_strategy_short_gate_a(self):
        """Gate A short -> sub_strategy == 'mr_short_gate_a'."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_short_gate_a(strategy)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_short_gate_a"

    def test_sub_strategy_long_gate_b(self):
        """Gate B long -> sub_strategy == 'mr_long_gate_b'."""
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=3,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=35.0, adx=18.0, atr=2.0,
                pct_b=0.35,  # above Gate A threshold (0.30)
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        assert signal.metadata["sub_strategy"] == "mr_long_gate_b"


# ===================================================================
# 8. Signal Strength
# ===================================================================


class TestSignalStrength:
    def test_long_gate_a_strength_formula(self):
        """Gate A long strength: min(1.0, (0.30 - pct_b) / 0.30 + (45.0 - rsi) / 45.0)."""
        strategy = AdaptiveMeanReversion()
        pct_b = 0.10
        rsi = 30.0
        expected = min(1.0, (0.30 - pct_b) / 0.30 + (45.0 - rsi) / 45.0)

        signal = _enter_long_gate_a(strategy, pct_b=pct_b, rsi=rsi)
        assert signal is not None
        assert signal.strength == pytest.approx(expected, abs=1e-6)

    def test_short_gate_a_strength_formula(self):
        """Gate A short strength: min(1.0, (pct_b - 0.80) / 0.20 + (rsi - 60.0) / 40.0)."""
        strategy = AdaptiveMeanReversion()
        pct_b = 0.90
        rsi = 75.0
        expected = min(
            1.0,
            (pct_b - 0.80) / (1.0 - 0.80) + (rsi - 60.0) / (100.0 - 60.0),
        )

        signal = _enter_short_gate_a(strategy, pct_b=pct_b, rsi=rsi)
        assert signal is not None
        assert signal.strength == pytest.approx(expected, abs=1e-6)

    def test_signal_strength_clamped_to_1(self):
        """Strength must not exceed 1.0 even with extreme values."""
        strategy = AdaptiveMeanReversion()
        # Extreme values: pct_b very low, RSI very low
        signal = _enter_long_gate_a(strategy, pct_b=0.01, rsi=10.0)
        assert signal is not None
        assert signal.strength <= 1.0

    def test_signal_strength_non_negative(self):
        """Strength must be >= 0.0."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None
        assert signal.strength >= 0.0

    def test_gate_b_strength_formula(self):
        """Gate B strength: min(1.0, (40 - rsi)/40 + min(down_days, 5)/5)."""
        strategy = AdaptiveMeanReversion()
        rsi = 35.0
        down_days = 4
        ctx = _make_ctx_with_descending_history(
            close=96.0,
            down_days=down_days,
            base_close=100.0,
            indicators=_full_indicators(
                rsi=rsi, adx=18.0, atr=2.0,
                pct_b=0.35,  # above Gate A threshold (0.30)
                ema_50=105.0, ema_5=97.0,
            ),
        )
        signal = strategy.on_context(ctx)
        assert signal is not None
        expected = min(1.0, (40.0 - rsi) / 40.0 + min(down_days, 5) / 5.0)
        assert signal.strength == pytest.approx(expected, abs=1e-6)


# ===================================================================
# 9. No Signal When Indicators Missing
# ===================================================================


class TestMissingIndicators:
    def test_no_signal_when_all_missing(self):
        strategy = AdaptiveMeanReversion()
        ctx = _make_ctx(indicators={})
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_rsi_missing(self):
        strategy = AdaptiveMeanReversion()
        ind = _full_indicators()
        del ind["RSI_14"]
        ctx = _make_ctx(indicators=ind)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_bbands_missing(self):
        strategy = AdaptiveMeanReversion()
        ind = _full_indicators()
        del ind["BBANDS_20"]
        ctx = _make_ctx(indicators=ind)
        assert strategy.on_context(ctx) is None

    def test_no_signal_when_bbands_not_dict(self):
        strategy = AdaptiveMeanReversion()
        ind = _full_indicators()
        ind["BBANDS_20"] = 42.0  # not a dict
        ctx = _make_ctx(indicators=ind)
        assert strategy.on_context(ctx) is None


# ===================================================================
# 10. Multiple Symbols
# ===================================================================


class TestMultipleSymbols:
    def test_independent_symbol_tracking(self):
        """Entry on AAPL should not affect GOOG state."""
        strategy = AdaptiveMeanReversion()

        # Enter on AAPL
        signal_a = _enter_long_gate_a(strategy, symbol="AAPL")
        assert signal_a is not None
        assert signal_a.symbol == "AAPL"

        # GOOG should also be able to enter
        signal_g = _enter_long_gate_a(strategy, symbol="GOOG")
        assert signal_g is not None
        assert signal_g.symbol == "GOOG"

    def test_no_double_entry_same_symbol(self):
        """While in position, same symbol should not enter again."""
        strategy = AdaptiveMeanReversion()
        signal = _enter_long_gate_a(strategy)
        assert signal is not None

        # Try entering again on same symbol
        signal2 = _enter_long_gate_a(strategy)
        # Should be None (in_position=True -> goes to exit logic, but may or may not exit)
        # The exit check will run, and with default indicators it may trigger.
        # Ensure it doesn't produce a new long entry signal.
        if signal2 is not None:
            assert signal2.direction == "close"  # can only be a close, not another entry

    def test_independent_adx_history(self):
        """ADX history is tracked per symbol."""
        strategy = AdaptiveMeanReversion()

        # AAPL: build steep ADX slope -> should block
        _prime_adx_history(strategy, "AAPL", [18.0, 19.0, 20.0])
        ctx_a = _make_ctx(
            close=95.0, symbol="AAPL",
            indicators=_full_indicators(rsi=30.0, adx=21.0, pct_b=0.10, ema_50=105.0),
        )
        # ADX slope for AAPL: 21 - 18 = 3.0 > 2.0 -> blocked
        assert strategy.on_context(ctx_a) is None

        # GOOG: no prior ADX history -> slope check skipped -> should pass
        ctx_g = _make_ctx(
            close=95.0, symbol="GOOG",
            indicators=_full_indicators(rsi=30.0, adx=21.0, pct_b=0.10, ema_50=105.0),
        )
        signal = strategy.on_context(ctx_g)
        assert signal is not None
        assert signal.symbol == "GOOG"


# ===================================================================
# 11. Consecutive Down Day Counting
# ===================================================================


class TestConsecutiveDownCounting:
    def test_zero_down_days_flat_history(self):
        """Flat history (all same close) -> 0 down days."""
        strategy = AdaptiveMeanReversion()
        history = deque(maxlen=500)
        for _ in range(10):
            history.append(_make_bar(close=100.0))
        bar = _make_bar(close=100.0)
        history.append(bar)
        ctx = MarketContext(
            symbol="TEST", bar=bar, indicators={}, history=history,
        )
        assert strategy._count_consecutive_down(ctx) == 0

    def test_three_consecutive_down(self):
        """3 descending closes -> 3 down days."""
        strategy = AdaptiveMeanReversion()
        history = deque(maxlen=500)
        history.append(_make_bar(close=100.0))
        history.append(_make_bar(close=99.0))
        history.append(_make_bar(close=98.0))
        bar = _make_bar(close=97.0)
        history.append(bar)
        ctx = MarketContext(
            symbol="TEST", bar=bar, indicators={}, history=history,
        )
        assert strategy._count_consecutive_down(ctx) == 3

    def test_interrupted_sequence(self):
        """Up day breaks the consecutive count."""
        strategy = AdaptiveMeanReversion()
        history = deque(maxlen=500)
        history.append(_make_bar(close=100.0))
        history.append(_make_bar(close=99.0))
        history.append(_make_bar(close=100.5))  # up day breaks streak
        history.append(_make_bar(close=99.5))
        bar = _make_bar(close=98.5)
        history.append(bar)
        ctx = MarketContext(
            symbol="TEST", bar=bar, indicators={}, history=history,
        )
        assert strategy._count_consecutive_down(ctx) == 2

    def test_current_bar_appended_if_not_in_history(self):
        """Current bar is counted even if not yet in history."""
        strategy = AdaptiveMeanReversion()
        history = deque(maxlen=500)
        history.append(_make_bar(close=100.0, timestamp=datetime(2024, 6, 13, tzinfo=timezone.utc)))
        history.append(_make_bar(close=99.0, timestamp=datetime(2024, 6, 14, tzinfo=timezone.utc)))
        # current bar NOT in history -- distinct timestamp triggers append
        bar = _make_bar(close=98.0, timestamp=datetime(2024, 6, 15, tzinfo=timezone.utc))
        ctx = MarketContext(
            symbol="TEST", bar=bar, indicators={}, history=history,
        )
        assert strategy._count_consecutive_down(ctx) == 2


# ===================================================================
# 12. Exit Signal Properties
# ===================================================================


class TestExitSignalProperties:
    def test_exit_signal_strength_is_1(self):
        """Exit signals always have strength 1.0."""
        strategy = AdaptiveMeanReversion()
        _enter_long_gate_a(strategy)

        ctx = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=58.0, adx=18.0, pct_b=0.55, ema_50=105.0, ema_5=97.0,
            ),
        )
        exit_signal = strategy.on_context(ctx)
        assert exit_signal is not None
        assert exit_signal.strength == 1.0

    def test_exit_resets_position_state(self):
        """After exit, strategy can enter again on same symbol."""
        strategy = AdaptiveMeanReversion()
        signal1 = _enter_long_gate_a(strategy)
        assert signal1 is not None

        # Trigger exit
        ctx_exit = _make_ctx(
            close=98.0,
            indicators=_full_indicators(
                rsi=58.0, adx=18.0, pct_b=0.55, ema_50=105.0, ema_5=97.0,
            ),
        )
        exit_signal = strategy.on_context(ctx_exit)
        assert exit_signal is not None
        assert exit_signal.direction == "close"

        # Should be able to enter again
        signal2 = _enter_long_gate_a(strategy)
        assert signal2 is not None
        assert signal2.direction == "long"
