"""Regime-change position re-evaluation.

When the market regime changes, existing positions from strategies that are
incompatible with the new regime should be reviewed and potentially closed.
Compatibility is determined by the strategy's entry-blocking flags in the
new regime -- a blocked strategy signals positions should be unwound.
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
# A strategy is *compatible* with a regime when it is NOT blocked
# from entering in that regime.  Blocked strategies indicate the
# strategy is a poor fit and open positions should be closed on
# regime transition.
#
# Reference (from _ALLOCATION_TABLE):
#   breakout_momentum: TREND_DOWN -> breakout_blocked=True
#   rsi_mean_reversion: compatible in all regimes
# ---------------------------------------------------------------------------

STRATEGY_REGIME_COMPATIBLE: dict[str, set[MarketRegime]] = {
    "breakout_momentum": {
        MarketRegime.TREND_UP,
        MarketRegime.RANGING,
        MarketRegime.HIGH_VOLATILITY,
        MarketRegime.UNCERTAIN,
        # NOT TREND_DOWN (breakout_blocked=True)
    },
    "rsi_mean_reversion": {
        MarketRegime.TREND_UP,
        MarketRegime.TREND_DOWN,
        MarketRegime.RANGING,
        MarketRegime.HIGH_VOLATILITY,
        MarketRegime.UNCERTAIN,
    },
}


class RegimePositionReviewer:
    """Reviews open positions when regime changes and recommends closures.

    The reviewer compares each open position's originating strategy against
    a compatibility matrix.  Strategies blocked in the new regime receive
    a ``"close"`` recommendation.
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
