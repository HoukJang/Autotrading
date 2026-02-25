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
    BB_EXPAND: float = 1.3
    BB_CONTRACT: float = 0.8
    VOL_HIGH: float = 0.03

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

        if adx >= self.ADX_TREND and width_ratio >= self.BB_EXPAND:
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


# Regime -> strategy weight mappings
_REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TREND: {
        "rsi_mean_reversion": 0.15,
        "adx_pullback": 0.30,
        "bb_squeeze": 0.20,
        "overbought_short": 0.10,
        "regime_momentum": 0.25,
    },
    MarketRegime.RANGING: {
        "rsi_mean_reversion": 0.35,
        "adx_pullback": 0.10,
        "bb_squeeze": 0.25,
        "overbought_short": 0.20,
        "regime_momentum": 0.10,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "rsi_mean_reversion": 0.20,
        "adx_pullback": 0.10,
        "bb_squeeze": 0.30,
        "overbought_short": 0.25,
        "regime_momentum": 0.15,
    },
    MarketRegime.UNCERTAIN: {
        "rsi_mean_reversion": 0.20,
        "adx_pullback": 0.15,
        "bb_squeeze": 0.20,
        "overbought_short": 0.20,
        "regime_momentum": 0.15,
    },
}
