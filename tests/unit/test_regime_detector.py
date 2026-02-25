"""Tests for portfolio-level RegimeDetector.

Covers regime classification logic, boundary conditions,
weight mappings, and defensive edge cases.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector


@pytest.fixture
def detector() -> RegimeDetector:
    return RegimeDetector()


# ── Regime classification tests ──────────────────────────────────────


class TestClassifyTrend:
    """TREND: ADX >= 25 AND width_ratio >= 1.3"""

    def test_strong_trend_classified(self, detector: RegimeDetector):
        result = detector.classify(adx=30.0, bb_width=0.065, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND

    def test_adx_exactly_25_with_expanding_bands(self, detector: RegimeDetector):
        # ADX == 25 should still be >= threshold
        result = detector.classify(adx=25.0, bb_width=0.065, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND

    def test_width_ratio_exactly_1_3(self, detector: RegimeDetector):
        # width_ratio == 1.3 should still be >= threshold
        result = detector.classify(adx=28.0, bb_width=0.065, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND


class TestClassifyRanging:
    """RANGING: ADX < 20 AND width_ratio <= 0.8"""

    def test_ranging_market_classified(self, detector: RegimeDetector):
        result = detector.classify(adx=15.0, bb_width=0.035, bb_width_avg=0.05, atr_ratio=0.01)
        assert result == MarketRegime.RANGING

    def test_adx_exactly_20_not_ranging(self, detector: RegimeDetector):
        # ADX == 20 is NOT < 20, so should not be RANGING
        result = detector.classify(adx=20.0, bb_width=0.035, bb_width_avg=0.05, atr_ratio=0.01)
        assert result != MarketRegime.RANGING

    def test_width_ratio_exactly_0_8(self, detector: RegimeDetector):
        # width_ratio == 0.8 should still be <= threshold
        result = detector.classify(adx=15.0, bb_width=0.04, bb_width_avg=0.05, atr_ratio=0.01)
        assert result == MarketRegime.RANGING


class TestClassifyHighVolatility:
    """HIGH_VOLATILITY: ADX < 20 AND width_ratio >= 1.3 AND atr_ratio > 0.03"""

    def test_high_volatility_classified(self, detector: RegimeDetector):
        result = detector.classify(adx=15.0, bb_width=0.07, bb_width_avg=0.05, atr_ratio=0.04)
        assert result == MarketRegime.HIGH_VOLATILITY

    def test_atr_ratio_exactly_0_03_not_high_vol(self, detector: RegimeDetector):
        # atr_ratio == 0.03 is NOT > 0.03, so should not be HIGH_VOLATILITY
        result = detector.classify(adx=15.0, bb_width=0.07, bb_width_avg=0.05, atr_ratio=0.03)
        assert result != MarketRegime.HIGH_VOLATILITY

    def test_high_adx_prevents_high_volatility(self, detector: RegimeDetector):
        # ADX >= 20 with expanding bands and high vol -> not HIGH_VOLATILITY
        result = detector.classify(adx=25.0, bb_width=0.07, bb_width_avg=0.05, atr_ratio=0.04)
        assert result != MarketRegime.HIGH_VOLATILITY


class TestClassifyUncertain:
    """UNCERTAIN: everything else (ADX between 20-25, normal width, etc.)"""

    def test_mid_range_adx_normal_width(self, detector: RegimeDetector):
        result = detector.classify(adx=22.0, bb_width=0.05, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.UNCERTAIN

    def test_bb_width_avg_zero_returns_uncertain(self, detector: RegimeDetector):
        # Division protection: bb_width_avg == 0
        result = detector.classify(adx=30.0, bb_width=0.065, bb_width_avg=0.0, atr_ratio=0.04)
        assert result == MarketRegime.UNCERTAIN

    def test_low_adx_expanding_bands_low_atr(self, detector: RegimeDetector):
        # ADX < 20, width_ratio >= 1.3, but atr_ratio <= 0.03 -> UNCERTAIN
        result = detector.classify(adx=15.0, bb_width=0.07, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.UNCERTAIN


class TestBoundaryConditions:
    """Boundary tests at exact threshold values."""

    def test_adx_exactly_25_boundary(self, detector: RegimeDetector):
        # ADX exactly 25 with expanding bands -> TREND (>= 25)
        result = detector.classify(adx=25.0, bb_width=0.065, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND

    def test_adx_exactly_20_boundary(self, detector: RegimeDetector):
        # ADX exactly 20 with contracting bands -> not RANGING (needs < 20)
        result = detector.classify(adx=20.0, bb_width=0.035, bb_width_avg=0.05, atr_ratio=0.01)
        assert result == MarketRegime.UNCERTAIN

    def test_adx_just_below_25_not_trend(self, detector: RegimeDetector):
        result = detector.classify(adx=24.99, bb_width=0.065, bb_width_avg=0.05, atr_ratio=0.02)
        assert result != MarketRegime.TREND

    def test_adx_just_below_20_is_ranging(self, detector: RegimeDetector):
        result = detector.classify(adx=19.99, bb_width=0.035, bb_width_avg=0.05, atr_ratio=0.01)
        assert result == MarketRegime.RANGING


# ── Weight mapping tests ─────────────────────────────────────────────


class TestTrendWeights:
    def test_trend_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND)
        assert weights["rsi_mean_reversion"] == 0.15
        assert weights["adx_pullback"] == 0.30
        assert weights["bb_squeeze"] == 0.20
        assert weights["overbought_short"] == 0.10
        assert weights["regime_momentum"] == 0.25

    def test_trend_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestRangingWeights:
    def test_ranging_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.35
        assert weights["adx_pullback"] == 0.10
        assert weights["bb_squeeze"] == 0.25
        assert weights["overbought_short"] == 0.20
        assert weights["regime_momentum"] == 0.10

    def test_ranging_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.RANGING)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestHighVolatilityWeights:
    def test_high_volatility_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert weights["rsi_mean_reversion"] == 0.20
        assert weights["adx_pullback"] == 0.10
        assert weights["bb_squeeze"] == 0.30
        assert weights["overbought_short"] == 0.25
        assert weights["regime_momentum"] == 0.15

    def test_high_volatility_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestUncertainWeights:
    def test_uncertain_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.UNCERTAIN)
        assert weights["rsi_mean_reversion"] == 0.20
        assert weights["adx_pullback"] == 0.15
        assert weights["bb_squeeze"] == 0.20
        assert weights["overbought_short"] == 0.20
        assert weights["regime_momentum"] == 0.15

    def test_uncertain_weights_sum_to_0_90(self, detector: RegimeDetector):
        """UNCERTAIN keeps 10% cash buffer, so weights sum to 0.90."""
        weights = detector.get_weights(MarketRegime.UNCERTAIN)
        assert abs(sum(weights.values()) - 0.90) < 1e-9


class TestAllRegimeWeightSums:
    """All non-UNCERTAIN regimes sum to 1.0."""

    @pytest.mark.parametrize("regime", [MarketRegime.TREND, MarketRegime.RANGING, MarketRegime.HIGH_VOLATILITY])
    def test_non_uncertain_regimes_sum_to_one(self, detector: RegimeDetector, regime: MarketRegime):
        weights = detector.get_weights(regime)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestGetWeightsReturnsCopy:
    """get_weights returns a copy, not a reference to the internal dict."""

    def test_modifying_returned_dict_does_not_affect_internal(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND)
        original_value = weights["adx_pullback"]
        weights["adx_pullback"] = 999.0

        fresh_weights = detector.get_weights(MarketRegime.TREND)
        assert fresh_weights["adx_pullback"] == original_value
