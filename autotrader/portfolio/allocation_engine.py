"""Capital allocation engine based on market regime.

Determines per-strategy position sizes by combining regime-based
allocation weights with account equity and risk constraints such as
minimum position value, maximum positions per strategy, and risk-based
ATR stop-loss sizing.
"""
from __future__ import annotations

from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector

RISK_PER_TRADE_PCT: float = 0.02  # Max 2% account risk per trade
SHORT_SIZE_RATIO: float = 0.65  # Short positions sized at 65% of long


class AllocationEngine:
    """Manages per-strategy capital allocation based on market regime.

    Determines position sizes by combining regime-based weights
    with account equity and risk constraints.  When ATR is provided,
    position size is further capped so that a 2x-ATR stop-loss would
    not exceed RISK_PER_TRADE_PCT of equity.
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
        atr: float | None = None,
        direction: str = "long",
    ) -> int:
        """Calculate position size considering allocation weight and risk.

        Uses the regime-based weight to determine a maximum allocation,
        then optionally caps that size using ATR-based risk sizing so
        that no single trade risks more than RISK_PER_TRADE_PCT of equity.
        Short positions are further reduced by SHORT_SIZE_RATIO.

        Args:
            strategy_name: Name of the strategy requesting position.
            price: Current price of the asset.
            equity: Current account equity.
            regime: Current market regime.
            atr: Current Average True Range for the asset.  When provided,
                 enables risk-based position sizing.  None preserves
                 backward-compatible weight-only sizing.
            direction: Trade direction, either ``"long"`` or ``"short"``.

        Returns:
            Number of shares to trade (0 if below minimum or invalid price).
        """
        if price <= 0:
            return 0

        weights = self._detector.get_weights(regime)
        weight = weights.get(strategy_name, 0.0)
        max_value = equity * weight

        if max_value < self.MIN_POSITION_VALUE:
            return 0

        weight_qty = int(max_value / price)

        qty = weight_qty

        if atr is not None:
            risk_per_trade = equity * RISK_PER_TRADE_PCT
            stop_distance = 2.0 * atr
            if stop_distance > 0:
                risk_qty = int(risk_per_trade / stop_distance)
                qty = min(weight_qty, risk_qty)

        if direction == "short":
            qty = int(qty * SHORT_SIZE_RATIO)

        if qty * price < self.MIN_POSITION_VALUE:
            return 0

        return qty

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
