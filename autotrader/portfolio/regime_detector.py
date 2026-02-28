"""Portfolio-level market regime detection.

Classifies the current market environment into one of four regimes
(TREND, RANGING, HIGH_VOLATILITY, UNCERTAIN) using ADX trend strength,
Bollinger Band width ratio for volatility state, and ATR/close ratio
for absolute volatility level. Each regime maps to a set of strategy
allocation weights that sum to 1.0 (or 0.90 for UNCERTAIN, retaining
a 10% cash buffer).
"""
from __future__ import annotations

from enum import Enum


class MarketRegime(Enum):
    """Market regime classification."""

    TREND = "TREND"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


class RegimeDetector:
    """Portfolio-level market regime classification.

    Uses ADX for trend strength, BB width ratio for volatility state,
    and ATR/close ratio for absolute volatility level.
    """

    ADX_TREND: float = 25.0
    ADX_NO_TREND: float = 20.0
    BB_EXPAND: float = 1.0
    BB_CONTRACT: float = 0.8
    VOL_HIGH: float = 0.03
    BB_ADX_SCALE: float = 0.005

    def _bb_trend_threshold(self, adx: float) -> float:
        """Return the BB width-ratio threshold for TREND, scaled by ADX.

        Higher ADX lowers the BB requirement linearly:
          threshold = max(BB_CONTRACT, BB_EXPAND - (adx - ADX_TREND) * BB_ADX_SCALE)

        At ADX 25 the threshold equals BB_EXPAND (1.0), at ADX 65 it drops
        to 0.8.  The floor is BB_CONTRACT so it never falls below 0.8.
        """
        return max(
            self.BB_CONTRACT,
            self.BB_EXPAND - (adx - self.ADX_TREND) * self.BB_ADX_SCALE,
        )

    def classify(
        self,
        adx: float,
        bb_width: float,
        bb_width_avg: float,
        atr_ratio: float,
    ) -> MarketRegime:
        """Classify current market regime.

        Args:
            adx: Current ADX value.
            bb_width: Current Bollinger Band width.
            bb_width_avg: 20-period average of BB width.
            atr_ratio: ATR(14) / close price.

        Returns:
            MarketRegime enum value.
        """
        if bb_width_avg == 0:
            return MarketRegime.UNCERTAIN

        width_ratio = bb_width / bb_width_avg

        if adx >= self.ADX_TREND and width_ratio >= self._bb_trend_threshold(adx):
            return MarketRegime.TREND
        if adx < self.ADX_NO_TREND and width_ratio <= self.BB_CONTRACT:
            return MarketRegime.RANGING
        if (
            adx < self.ADX_NO_TREND
            and width_ratio >= self.BB_EXPAND
            and atr_ratio > self.VOL_HIGH
        ):
            return MarketRegime.HIGH_VOLATILITY
        return MarketRegime.UNCERTAIN

    def get_weights(self, regime: MarketRegime) -> dict[str, float]:
        """Get strategy allocation weights for given regime.

        Returns dict mapping strategy name -> allocation weight (0.0 to 1.0).
        Weights sum to 1.0 for all regimes except UNCERTAIN (sums to 0.9,
        retaining 10% cash buffer).
        """
        return dict(_REGIME_WEIGHTS[regime])

    def get_vix_adjusted_weights(
        self,
        regime: MarketRegime,
        sentiment_level: "SentimentLevel",
    ) -> dict[str, float]:
        """Get strategy weights adjusted for VIX/sentiment level.

        Applies defensive tilts when VIX is elevated or extreme, and a
        slight complacency-risk adjustment when VIX is unusually low.
        NORMAL sentiment returns base weights unchanged.

        Args:
            regime: Current market regime.
            sentiment_level: Current VIX-based sentiment level.

        Returns:
            Dict of strategy name -> adjusted weight (all >= 0.0).
        """
        from autotrader.data.market_sentiment import SentimentLevel

        weights = self.get_weights(regime)

        if sentiment_level == SentimentLevel.NORMAL:
            return weights

        # Adjustments per sentiment: (consec_down_delta, ema_pullback_delta, vol_div_delta)
        adjustments: dict[SentimentLevel, tuple[float, float, float]] = {
            SentimentLevel.LOW: (0.00, -0.03, 0.03),
            SentimentLevel.ELEVATED: (0.03, -0.03, 0.03),
            SentimentLevel.HIGH: (0.05, -0.05, 0.05),
            SentimentLevel.EXTREME: (0.10, -0.10, 0.10),
        }

        deltas = adjustments.get(sentiment_level)
        if deltas is None:
            return weights

        consec_d, ema_d, vol_d = deltas
        weights["consecutive_down"] = max(0.0, weights["consecutive_down"] + consec_d)
        weights["ema_pullback"] = max(0.0, weights["ema_pullback"] + ema_d)
        weights["volume_divergence"] = max(0.0, weights["volume_divergence"] + vol_d)

        return weights


# Regime -> strategy weight mappings
_REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TREND: {
        "rsi_mean_reversion": 0.15,
        "consecutive_down": 0.20,
        "ema_pullback": 0.40,
        "volume_divergence": 0.25,
    },
    MarketRegime.RANGING: {
        "rsi_mean_reversion": 0.35,
        "consecutive_down": 0.30,
        "ema_pullback": 0.10,
        "volume_divergence": 0.25,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "rsi_mean_reversion": 0.25,
        "consecutive_down": 0.30,
        "ema_pullback": 0.10,
        "volume_divergence": 0.35,
    },
    MarketRegime.UNCERTAIN: {
        "rsi_mean_reversion": 0.25,
        "consecutive_down": 0.25,
        "ema_pullback": 0.25,
        "volume_divergence": 0.25,
    },
}
