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


class TestClassifyTrendScaledThreshold:
    """TREND with ADX-scaled BB threshold: higher ADX relaxes BB requirement."""

    def test_high_adx_with_borderline_bb_is_trend(self, detector: RegimeDetector):
        # ADX=67, bb_ratio=0.99 -- the original bug case
        # bb_threshold = max(0.8, 1.0 - (67-25)*0.005) = max(0.8, 0.79) = 0.8
        result = detector.classify(adx=67.0, bb_width=0.0495, bb_width_avg=0.05, atr_ratio=0.03)
        assert result == MarketRegime.TREND

    def test_moderate_adx_with_slightly_low_bb_is_trend(self, detector: RegimeDetector):
        # ADX=40, bb_ratio=0.95
        # bb_threshold = max(0.8, 1.0 - (40-25)*0.005) = max(0.8, 0.925) = 0.925
        result = detector.classify(adx=40.0, bb_width=0.0475, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND

    def test_adx_25_still_requires_full_bb_expand(self, detector: RegimeDetector):
        # ADX=25, bb_ratio=0.95 -- threshold stays at 1.0 for ADX exactly 25
        result = detector.classify(adx=25.0, bb_width=0.0475, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.UNCERTAIN

    def test_threshold_floor_at_bb_contract(self, detector: RegimeDetector):
        # ADX=100 (extreme), bb_ratio=0.81 -- floor is 0.8
        result = detector.classify(adx=100.0, bb_width=0.0405, bb_width_avg=0.05, atr_ratio=0.02)
        assert result == MarketRegime.TREND

    def test_threshold_floor_blocks_below_contract(self, detector: RegimeDetector):
        # ADX=100, bb_ratio=0.79 -- below floor of 0.8
        result = detector.classify(adx=100.0, bb_width=0.0395, bb_width_avg=0.05, atr_ratio=0.02)
        assert result != MarketRegime.TREND


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
        assert weights["consecutive_down"] == 0.20
        assert weights["ema_pullback"] == 0.40
        assert weights["volume_divergence"] == 0.25

    def test_trend_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.TREND)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestRangingWeights:
    def test_ranging_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.35
        assert weights["consecutive_down"] == 0.30
        assert weights["ema_pullback"] == 0.10
        assert weights["volume_divergence"] == 0.25

    def test_ranging_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.RANGING)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestHighVolatilityWeights:
    def test_high_volatility_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert weights["rsi_mean_reversion"] == 0.25
        assert weights["consecutive_down"] == 0.30
        assert weights["ema_pullback"] == 0.10
        assert weights["volume_divergence"] == 0.35

    def test_high_volatility_weights_sum_to_one(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.HIGH_VOLATILITY)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestUncertainWeights:
    def test_uncertain_weights_values(self, detector: RegimeDetector):
        weights = detector.get_weights(MarketRegime.UNCERTAIN)
        assert weights["rsi_mean_reversion"] == 0.25
        assert weights["consecutive_down"] == 0.25
        assert weights["ema_pullback"] == 0.25
        assert weights["volume_divergence"] == 0.25

    def test_uncertain_weights_sum_to_1_0(self, detector: RegimeDetector):
        """UNCERTAIN weights sum to 1.0."""
        weights = detector.get_weights(MarketRegime.UNCERTAIN)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


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
        original_value = weights["ema_pullback"]
        weights["ema_pullback"] = 999.0

        fresh_weights = detector.get_weights(MarketRegime.TREND)
        assert fresh_weights["ema_pullback"] == original_value


# -- VIX-adjusted weight tests -----------------------------------------------


class TestVixAdjustedWeights:
    """Tests for get_vix_adjusted_weights with VIX sentiment scaling."""

    def test_normal_sentiment_no_change(self, detector: RegimeDetector):
        """NORMAL VIX should return weights unchanged."""
        from autotrader.data.market_sentiment import SentimentLevel

        base = detector.get_weights(MarketRegime.TREND)
        adjusted = detector.get_vix_adjusted_weights(MarketRegime.TREND, SentimentLevel.NORMAL)
        assert adjusted == base

    def test_high_vix_boosts_defensive(self, detector: RegimeDetector):
        """HIGH VIX should boost consecutive_down and volume_divergence, reduce ema_pullback."""
        from autotrader.data.market_sentiment import SentimentLevel

        base = detector.get_weights(MarketRegime.TREND)
        adjusted = detector.get_vix_adjusted_weights(MarketRegime.TREND, SentimentLevel.HIGH)
        assert adjusted["consecutive_down"] > base["consecutive_down"]
        assert adjusted["volume_divergence"] > base["volume_divergence"]
        assert adjusted["ema_pullback"] < base["ema_pullback"]

    def test_extreme_vix_stronger_adjustment(self, detector: RegimeDetector):
        """EXTREME VIX should have stronger adjustments than HIGH."""
        from autotrader.data.market_sentiment import SentimentLevel

        high = detector.get_vix_adjusted_weights(MarketRegime.TREND, SentimentLevel.HIGH)
        extreme = detector.get_vix_adjusted_weights(MarketRegime.TREND, SentimentLevel.EXTREME)
        assert extreme["consecutive_down"] > high["consecutive_down"]

    def test_low_vix_slight_caution(self, detector: RegimeDetector):
        """LOW VIX should slightly boost volume_divergence (complacency risk)."""
        from autotrader.data.market_sentiment import SentimentLevel

        base = detector.get_weights(MarketRegime.TREND)
        adjusted = detector.get_vix_adjusted_weights(MarketRegime.TREND, SentimentLevel.LOW)
        assert adjusted["volume_divergence"] > base["volume_divergence"]

    def test_weights_non_negative(self, detector: RegimeDetector):
        """All adjusted weights must be >= 0."""
        from autotrader.data.market_sentiment import SentimentLevel

        for regime in MarketRegime:
            for level in SentimentLevel:
                weights = detector.get_vix_adjusted_weights(regime, level)
                for v in weights.values():
                    assert v >= 0.0, f"Negative weight for {regime}/{level}: {weights}"

    def test_elevated_vix_moderate_adjustment(self, detector: RegimeDetector):
        """ELEVATED VIX should have moderate adjustments."""
        from autotrader.data.market_sentiment import SentimentLevel

        base = detector.get_weights(MarketRegime.RANGING)
        adjusted = detector.get_vix_adjusted_weights(MarketRegime.RANGING, SentimentLevel.ELEVATED)
        # Should be between base and HIGH adjustment
        assert adjusted != base  # Some adjustment should occur
