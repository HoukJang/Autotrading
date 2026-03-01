"""Tests for portfolio-level RegimeDetector.

Covers 5-regime SPY-based classification logic, boundary conditions,
allocation table mappings, 2-day confirmation, and defensive edge cases.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.regime_detector import (
    MarketRegime,
    RegimeDetector,
    _ALLOCATION_TABLE,
)


@pytest.fixture
def detector() -> RegimeDetector:
    return RegimeDetector()


# -- Regime classification tests (raw classify, no confirmation) -----------


class TestClassifyTrendUp:
    """TREND_UP: ADX >= 25 AND close > ema_50"""

    def test_strong_trend_up(self, detector: RegimeDetector):
        result = detector.classify(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_UP

    def test_adx_exactly_25_close_above_ema(self, detector: RegimeDetector):
        result = detector.classify(adx=25.0, close=451.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_UP

    def test_close_equal_ema_not_trend_up(self, detector: RegimeDetector):
        # close == ema_50 means NOT close > ema_50
        result = detector.classify(adx=30.0, close=450.0, ema_50=450.0, bb_ratio=0.5)
        assert result != MarketRegime.TREND_UP


class TestClassifyTrendDown:
    """TREND_DOWN: ADX >= 25 AND close < ema_50"""

    def test_strong_trend_down(self, detector: RegimeDetector):
        result = detector.classify(adx=30.0, close=440.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_DOWN

    def test_adx_exactly_25_close_below_ema(self, detector: RegimeDetector):
        result = detector.classify(adx=25.0, close=449.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_DOWN

    def test_close_equal_ema_not_trend_down(self, detector: RegimeDetector):
        result = detector.classify(adx=30.0, close=450.0, ema_50=450.0, bb_ratio=0.5)
        assert result != MarketRegime.TREND_DOWN


class TestClassifyRanging:
    """RANGING: ADX < 20 AND bb_ratio < 0.8"""

    def test_ranging_market(self, detector: RegimeDetector):
        result = detector.classify(adx=15.0, close=450.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.RANGING

    def test_adx_exactly_20_not_ranging(self, detector: RegimeDetector):
        result = detector.classify(adx=20.0, close=450.0, ema_50=450.0, bb_ratio=0.5)
        assert result != MarketRegime.RANGING

    def test_bb_ratio_exactly_0_8_not_ranging(self, detector: RegimeDetector):
        # bb_ratio == 0.8 is NOT < 0.8
        result = detector.classify(adx=15.0, close=450.0, ema_50=450.0, bb_ratio=0.8)
        assert result != MarketRegime.RANGING


class TestClassifyHighVolatility:
    """HIGH_VOLATILITY: bb_ratio > 1.2 AND adx < 25"""

    def test_high_volatility(self, detector: RegimeDetector):
        result = detector.classify(adx=15.0, close=450.0, ema_50=450.0, bb_ratio=1.5)
        assert result == MarketRegime.HIGH_VOLATILITY

    def test_bb_ratio_exactly_1_2_not_high_vol(self, detector: RegimeDetector):
        # bb_ratio == 1.2 is NOT > 1.2
        result = detector.classify(adx=15.0, close=450.0, ema_50=450.0, bb_ratio=1.2)
        assert result != MarketRegime.HIGH_VOLATILITY

    def test_adx_25_prevents_high_vol(self, detector: RegimeDetector):
        # adx >= 25 -> TREND_UP or TREND_DOWN, not HIGH_VOL
        result = detector.classify(adx=25.0, close=460.0, ema_50=450.0, bb_ratio=1.5)
        assert result != MarketRegime.HIGH_VOLATILITY


class TestClassifyUncertain:
    """UNCERTAIN: everything else"""

    def test_mid_range_adx_normal_bb(self, detector: RegimeDetector):
        result = detector.classify(adx=22.0, close=450.0, ema_50=450.0, bb_ratio=0.9)
        assert result == MarketRegime.UNCERTAIN

    def test_adx_below_20_bb_ratio_between_0_8_and_1_2(self, detector: RegimeDetector):
        result = detector.classify(adx=18.0, close=450.0, ema_50=450.0, bb_ratio=1.0)
        assert result == MarketRegime.UNCERTAIN


class TestBoundaryConditions:
    """Boundary tests at exact threshold values."""

    def test_adx_exactly_25_close_above(self, detector: RegimeDetector):
        result = detector.classify(adx=25.0, close=451.0, ema_50=450.0, bb_ratio=0.9)
        assert result == MarketRegime.TREND_UP

    def test_adx_just_below_25_not_trend(self, detector: RegimeDetector):
        result = detector.classify(adx=24.99, close=460.0, ema_50=450.0, bb_ratio=0.9)
        assert result != MarketRegime.TREND_UP
        assert result != MarketRegime.TREND_DOWN

    def test_adx_just_below_20_is_ranging(self, detector: RegimeDetector):
        result = detector.classify(adx=19.99, close=450.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.RANGING


# -- 2-day confirmation tests ---------------------------------------------


class TestTwoDayConfirmation:
    """Test the update() method's built-in 2-day confirmation."""

    def test_initial_confirmed_is_uncertain(self, detector: RegimeDetector):
        assert detector.confirmed_regime == MarketRegime.UNCERTAIN

    def test_first_call_does_not_confirm(self, detector: RegimeDetector):
        result = detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.UNCERTAIN
        assert detector.confirmed_regime == MarketRegime.UNCERTAIN

    def test_confirmed_after_two_days(self, detector: RegimeDetector):
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        result = detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_UP
        assert detector.confirmed_regime == MarketRegime.TREND_UP

    def test_flickering_resets(self, detector: RegimeDetector):
        # Day 1: TREND_UP
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        # Day 2: back to UNCERTAIN indicators
        detector.update(adx=22.0, close=450.0, ema_50=450.0, bb_ratio=0.9)
        # Still UNCERTAIN (not confirmed)
        assert detector.confirmed_regime == MarketRegime.UNCERTAIN
        # Day 3-4: new TREND_UP attempt
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        result = detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        assert result == MarketRegime.TREND_UP

    def test_same_regime_resets_pending(self, detector: RegimeDetector):
        # Confirm TREND_UP first
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        assert detector.confirmed_regime == MarketRegime.TREND_UP
        # One bar of RANGING, then back to TREND_UP
        detector.update(adx=15.0, close=450.0, ema_50=450.0, bb_ratio=0.5)
        detector.update(adx=30.0, close=460.0, ema_50=450.0, bb_ratio=0.5)
        # Still TREND_UP (pending RANGING was reset)
        assert detector.confirmed_regime == MarketRegime.TREND_UP


# -- Weight/allocation mapping tests --------------------------------------


class TestGetWeights:
    """get_weights returns only float-valued entries from allocation table."""

    def test_trend_up_weights(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND_UP)
        assert weights["breakout_momentum"] == 0.040
        assert weights["rsi_mean_reversion"] == 0.012
        assert len(weights) == 2

    def test_trend_down_weights(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND_DOWN)
        assert weights["breakout_momentum"] == 0.005
        assert weights["rsi_mean_reversion"] == 0.025

    def test_ranging_weights(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.040
        assert weights["breakout_momentum"] == 0.005

    def test_high_volatility_weights(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert weights["breakout_momentum"] == 0.005
        assert weights["rsi_mean_reversion"] == 0.020

    def test_uncertain_weights(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.UNCERTAIN)
        assert weights["breakout_momentum"] == 0.008
        assert weights["rsi_mean_reversion"] == 0.025


class TestGetAllocation:
    """get_allocation returns full allocation dict including blocking flags."""

    def test_trend_up_has_mr_short_blocked(self, detector: RegimeDetector):
        alloc = detector.get_allocation(MarketRegime.TREND_UP)
        assert alloc["mr_short_blocked"] is True
        assert alloc["breakout_blocked"] is False

    def test_trend_down_has_breakout_blocked(self, detector: RegimeDetector):
        alloc = detector.get_allocation(MarketRegime.TREND_DOWN)
        assert alloc["breakout_blocked"] is True
        assert alloc["mr_short_blocked"] is False

    def test_ranging_nothing_blocked(self, detector: RegimeDetector):
        alloc = detector.get_allocation(MarketRegime.RANGING)
        assert alloc["breakout_blocked"] is False
        assert alloc["mr_short_blocked"] is False


class TestAllRegimesHaveAllocations:
    """Every regime must have an entry in the allocation table."""

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_regime_has_allocation(self, detector: RegimeDetector, regime: MarketRegime):
        alloc = detector.get_allocation(regime)
        assert "breakout_momentum" in alloc
        assert "rsi_mean_reversion" in alloc
        assert "breakout_blocked" in alloc
        assert "mr_short_blocked" in alloc


class TestGetWeightsReturnsCopy:
    """get_weights returns a copy, not a reference to the internal dict."""

    def test_modifying_returned_dict_does_not_affect_internal(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND_UP)
        original_value = weights["breakout_momentum"]
        weights["breakout_momentum"] = 999.0

        fresh_weights = detector.get_weights(MarketRegime.TREND_UP)
        assert fresh_weights["breakout_momentum"] == original_value
