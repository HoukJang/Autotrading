"""Regime-change position re-evaluation.

When the market regime changes, existing positions from strategies that are
incompatible with the new regime should be reviewed and potentially closed.
Compatibility is determined by the strategy's allocation weight in the new
regime -- a weight of 10% or below signals the strategy is a poor fit and
positions should be unwound.
"""
from __future__ import annotations

from dataclasses import dataclass

from autotrader.portfolio.regime_detector import MarketRegime


@dataclass(frozen=True)
class PositionReview:
    """Result of reviewing a single position against a new regime.

    Attributes:
        symbol: Ticker symbol of the position.
        strategy: Name of the strategy that opened the position.
        action: Recommended action -- ``"keep"`` or ``"close"``.
        reason: Machine-readable explanation for the recommendation.
    """

    symbol: str
    strategy: str
    action: str  # "keep" or "close"
    reason: str


# ---------------------------------------------------------------------------
# Strategy-regime compatibility matrix
#
# A strategy is *compatible* with a regime when its allocation weight in
# ``_REGIME_WEIGHTS`` exceeds 10%.  Weight <= 10% means the strategy is a
# poor fit and open positions should be closed on regime transition.
#
# Reference weights (from regime_detector._REGIME_WEIGHTS):
#
#   rsi_mean_reversion : TREND 15% | RANGING 35% | HIGH_VOL 20% | UNCERTAIN 20%
#   adx_pullback       : TREND 30% | RANGING 10% | HIGH_VOL 10% | UNCERTAIN 15%
#   bb_squeeze         : TREND 20% | RANGING 25% | HIGH_VOL 30% | UNCERTAIN 20%
#   overbought_short   : TREND 10% | RANGING 20% | HIGH_VOL 25% | UNCERTAIN 20%
#   regime_momentum    : TREND 25% | RANGING 10% | HIGH_VOL 15% | UNCERTAIN 15%
# ---------------------------------------------------------------------------

STRATEGY_REGIME_COMPATIBLE: dict[str, set[MarketRegime]] = {
    "rsi_mean_reversion": {
        MarketRegime.TREND,            # 15%
        MarketRegime.RANGING,          # 35%
        MarketRegime.HIGH_VOLATILITY,  # 20%
        MarketRegime.UNCERTAIN,        # 20%
    },
    "adx_pullback": {
        MarketRegime.TREND,            # 30%
        MarketRegime.UNCERTAIN,        # 15%
        # RANGING 10%, HIGH_VOL 10% -- incompatible
    },
    "bb_squeeze": {
        MarketRegime.TREND,            # 20%
        MarketRegime.RANGING,          # 25%
        MarketRegime.HIGH_VOLATILITY,  # 30%
        MarketRegime.UNCERTAIN,        # 20%
    },
    "overbought_short": {
        MarketRegime.RANGING,          # 20%
        MarketRegime.HIGH_VOLATILITY,  # 25%
        MarketRegime.UNCERTAIN,        # 20%
        # TREND 10% -- incompatible
    },
    "regime_momentum": {
        MarketRegime.TREND,            # 25%
        MarketRegime.HIGH_VOLATILITY,  # 15%
        MarketRegime.UNCERTAIN,        # 15%
        # RANGING 10% -- incompatible
    },
}


class RegimePositionReviewer:
    """Reviews open positions when regime changes and recommends closures.

    The reviewer compares each open position's originating strategy against
    a compatibility matrix.  Strategies whose allocation weight drops to 10%
    or below in the new regime receive a ``"close"`` recommendation.
    """

    def review(
        self,
        new_regime: MarketRegime,
        position_strategy_map: dict[str, str],
    ) -> list[PositionReview]:
        """Review all open positions against the new regime.

        Args:
            new_regime: The newly confirmed regime.
            position_strategy_map: Mapping of symbol to strategy name for
                every currently open position.

        Returns:
            List of :class:`PositionReview` with action recommendations.
            One entry per position, ordered consistently with the input map.
        """
        reviews: list[PositionReview] = []
        for symbol, strategy in position_strategy_map.items():
            compatible_regimes = STRATEGY_REGIME_COMPATIBLE.get(strategy)
            if compatible_regimes is None:
                reviews.append(
                    PositionReview(
                        symbol=symbol,
                        strategy=strategy,
                        action="keep",
                        reason="unknown_strategy",
                    )
                )
                continue

            if new_regime in compatible_regimes:
                reviews.append(
                    PositionReview(
                        symbol=symbol,
                        strategy=strategy,
                        action="keep",
                        reason="compatible",
                    )
                )
            else:
                reviews.append(
                    PositionReview(
                        symbol=symbol,
                        strategy=strategy,
                        action="close",
                        reason=f"incompatible_with_{new_regime.value}",
                    )
                )
        return reviews
