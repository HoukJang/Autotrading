"""Capital allocation engine based on market regime.

Determines per-strategy position sizes by combining regime-based
allocation weights with account equity and risk constraints such as
minimum position value and maximum positions per strategy.
"""
from __future__ import annotations

from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector


class AllocationEngine:
    """Manages per-strategy capital allocation based on market regime.

    Determines position sizes by combining regime-based weights
    with account equity and risk constraints.
    """

    MIN_POSITION_VALUE: float = 200.0  # Minimum $200 per position
    MAX_POSITIONS_PER_STRATEGY: int = 2

    def __init__(self, regime_detector: RegimeDetector) -> None:
        self._detector = regime_detector

    def get_position_size(
        self,
        strategy_name: str,
        price: float,
        equity: float,
        regime: MarketRegime,
    ) -> int:
        """Calculate position size considering allocation weight.

        Args:
            strategy_name: Name of the strategy requesting position.
            price: Current price of the asset.
            equity: Current account equity.
            regime: Current market regime.

        Returns:
            Number of shares to buy (0 if below minimum or invalid price).
        """
        if price <= 0:
            return 0
        weights = self._detector.get_weights(regime)
        weight = weights.get(strategy_name, 0.0)
        max_value = equity * weight
        if max_value < self.MIN_POSITION_VALUE:
            return 0
        return int(max_value / price)

    def should_enter(
        self,
        strategy_name: str,
        regime: MarketRegime,
        strategy_position_count: int,
    ) -> bool:
        """Check if strategy is allowed to enter based on allocation constraints.

        Args:
            strategy_name: Name of the strategy.
            regime: Current market regime.
            strategy_position_count: Number of active positions for this strategy.

        Returns:
            True if entry is allowed.
        """
        weights = self._detector.get_weights(regime)
        if weights.get(strategy_name, 0.0) < 0.05:
            return False
        return strategy_position_count < self.MAX_POSITIONS_PER_STRATEGY

    def get_all_weights(self, regime: MarketRegime) -> dict[str, float]:
        """Get all strategy weights for current regime."""
        return self._detector.get_weights(regime)
