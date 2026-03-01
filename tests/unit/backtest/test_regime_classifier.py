"""Tests for SPY-based regime classifier."""
from __future__ import annotations

import pytest
from autotrader.backtest.regime_classifier import RegimeClassifier, Regime


class TestClassify:
    """Raw classification without confirmation."""

    def test_trend_up(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0) == Regime.TREND_UP

    def test_trend_down(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=28.0, close=430.0, ema_50=440.0, bb_ratio=1.0) == Regime.TREND_DOWN

    def test_ranging(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=15.0, close=445.0, ema_50=440.0, bb_ratio=0.7) == Regime.RANGING

    def test_high_volatility(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=22.0, close=445.0, ema_50=440.0, bb_ratio=1.3) == Regime.HIGH_VOLATILITY

    def test_uncertain_fallthrough(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=22.0, close=445.0, ema_50=440.0, bb_ratio=0.9) == Regime.UNCERTAIN

    def test_adx_boundary_25_above_ema(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=25.0, close=441.0, ema_50=440.0, bb_ratio=1.0) == Regime.TREND_UP

    def test_adx_boundary_25_below_ema(self):
        rc = RegimeClassifier()
        assert rc.classify(adx=25.0, close=439.0, ema_50=440.0, bb_ratio=1.0) == Regime.TREND_DOWN


class TestConfirmation:
    """2-day confirmation logic."""

    def test_initial_regime_is_uncertain(self):
        rc = RegimeClassifier()
        assert rc.confirmed_regime == Regime.UNCERTAIN

    def test_single_day_does_not_confirm(self):
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        assert rc.confirmed_regime == Regime.UNCERTAIN

    def test_two_consecutive_days_confirms(self):
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        rc.update(adx=32.0, close=455.0, ema_50=442.0, bb_ratio=1.1)
        assert rc.confirmed_regime == Regime.TREND_UP

    def test_whipsaw_does_not_confirm(self):
        rc = RegimeClassifier()
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)  # TREND_UP
        rc.update(adx=15.0, close=445.0, ema_50=440.0, bb_ratio=0.7)  # RANGING
        assert rc.confirmed_regime == Regime.UNCERTAIN

    def test_same_regime_resets_pending(self):
        rc = RegimeClassifier()
        # Confirm TREND_UP
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        rc.update(adx=31.0, close=451.0, ema_50=441.0, bb_ratio=1.0)
        assert rc.confirmed_regime == Regime.TREND_UP
        # Stay in TREND_UP
        rc.update(adx=29.0, close=448.0, ema_50=442.0, bb_ratio=0.9)
        assert rc.confirmed_regime == Regime.TREND_UP  # still confirmed

    def test_transition_requires_new_two_days(self):
        rc = RegimeClassifier()
        # Confirm TREND_UP
        rc.update(adx=30.0, close=450.0, ema_50=440.0, bb_ratio=1.0)
        rc.update(adx=31.0, close=451.0, ema_50=441.0, bb_ratio=1.0)
        assert rc.confirmed_regime == Regime.TREND_UP
        # One day of RANGING
        rc.update(adx=15.0, close=445.0, ema_50=440.0, bb_ratio=0.7)
        assert rc.confirmed_regime == Regime.TREND_UP  # not yet
        # Second day of RANGING
        rc.update(adx=14.0, close=444.0, ema_50=441.0, bb_ratio=0.6)
        assert rc.confirmed_regime == Regime.RANGING  # now confirmed


class TestAllocation:
    """Allocation table lookups (BM + MR 2-strategy portfolio, Iter 29)."""

    def test_trend_up_allocation(self):
        alloc = RegimeClassifier.get_allocation(Regime.TREND_UP)
        assert alloc["breakout_momentum"] == 0.040
        assert alloc["rsi_mean_reversion"] == 0.012
        assert alloc["breakout_blocked"] is False
        assert alloc["mr_short_blocked"] is True
        assert "trend_pullback" not in alloc
        assert "tp_blocked" not in alloc

    def test_trend_down_allocation(self):
        alloc = RegimeClassifier.get_allocation(Regime.TREND_DOWN)
        assert alloc["breakout_momentum"] == 0.005
        assert alloc["rsi_mean_reversion"] == 0.025
        assert alloc["breakout_blocked"] is True
        assert alloc["mr_short_blocked"] is False
        assert "trend_pullback" not in alloc
        assert "tp_blocked" not in alloc

    def test_ranging_allocation(self):
        alloc = RegimeClassifier.get_allocation(Regime.RANGING)
        assert alloc["breakout_momentum"] == 0.005
        assert alloc["rsi_mean_reversion"] == 0.040
        assert alloc["breakout_blocked"] is False
        assert alloc["mr_short_blocked"] is False
        assert "trend_pullback" not in alloc
        assert "tp_blocked" not in alloc

    def test_high_vol_allocation(self):
        alloc = RegimeClassifier.get_allocation(Regime.HIGH_VOLATILITY)
        assert alloc["breakout_momentum"] == 0.005
        assert alloc["rsi_mean_reversion"] == 0.020
        assert alloc["breakout_blocked"] is False
        assert alloc["mr_short_blocked"] is True
        assert "trend_pullback" not in alloc
        assert "tp_blocked" not in alloc

    def test_uncertain_allocation(self):
        alloc = RegimeClassifier.get_allocation(Regime.UNCERTAIN)
        assert alloc["breakout_momentum"] == 0.008
        assert alloc["rsi_mean_reversion"] == 0.025
        assert alloc["breakout_blocked"] is False
        assert alloc["mr_short_blocked"] is False
        assert "trend_pullback" not in alloc
        assert "tp_blocked" not in alloc

    def test_allocation_returns_copy(self):
        alloc1 = RegimeClassifier.get_allocation(Regime.TREND_UP)
        alloc2 = RegimeClassifier.get_allocation(Regime.TREND_UP)
        alloc1["breakout_momentum"] = 999
        assert alloc2["breakout_momentum"] == 0.040  # original value unchanged
