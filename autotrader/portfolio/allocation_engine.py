"""Capital allocation engine based on market regime.

Risk-based position sizing engine. Primary sizing uses per-trade risk
percentage from the regime allocation table, capped by MAX_POSITION_PCT
of equity. Short positions are reduced by SHORT_SIZE_RATIO.

Position caps are managed by EntryManager (not duplicated here).
"""
from __future__ import annotations

from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector

SHORT_SIZE_RATIO: float = 0.65  # Short positions sized at 65% of long


class AllocationEngine:
    """Risk-based position sizing engine driven by market regime.

    Primary sizing uses the regime allocation table to determine
    per-trade risk percentage, then sizes the position so that the
    stop-loss distance consumes at most that risk amount. The result
    is hard-capped at MAX_POSITION_PCT of equity per position.

    Supports future Phase 4 hooks: GDR risk multiplier and safety net.
    """

    MIN_POSITION_VALUE: float = 200.0    # Minimum $200 per position
    MAX_POSITION_PCT: float = 0.25       # Max 25% of equity per position (Iter 29)

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
        stop_distance: float | None = None,
        gdr_risk_mult: float = 1.0,
        safety_net_active: bool = False,
    ) -> int:
        """Calculate position size using risk-based primary sizing.

        Sizing priority:
        1. Determine effective risk pct from regime table (or safety net).
        2. Compute qty from risk_per_trade / stop_distance.
        3. Hard cap at MAX_POSITION_PCT of equity.
        4. Apply short size reduction.

        Args:
            strategy_name: Name of the strategy requesting position.
            price: Current price of the asset.
            equity: Current account equity.
            regime: Current market regime.
            atr: Current Average True Range for the asset.
            direction: Trade direction, ``"long"`` or ``"short"``.
            stop_distance: Actual distance from entry to stop-loss in price
                units. Overrides 2*ATR default when provided.
            gdr_risk_mult: GDR multiplier applied to base risk (Phase 4).
            safety_net_active: When True, forces 0.5% risk (Phase 4).

        Returns:
            Number of shares to trade (0 if below minimum or invalid price).
        """
        if price <= 0:
            return 0

        # Determine effective risk percentage
        if safety_net_active:
            effective_risk_pct = 0.005  # 0.5% during safety net
        else:
            alloc = self._detector.get_allocation(regime)
            base_risk = alloc.get(strategy_name, 0.02)
            # Ensure we only use numeric risk values, not boolean flags
            if not isinstance(base_risk, (int, float)):
                base_risk = 0.02
            effective_risk_pct = base_risk * gdr_risk_mult

        # Risk-based primary sizing
        risk_per_trade = equity * effective_risk_pct

        if stop_distance is not None and stop_distance > 0:
            qty = int(risk_per_trade / stop_distance)
        elif atr is not None and atr > 0:
            qty = int(risk_per_trade / (2.0 * atr))
        else:
            # Fallback: treat risk as position weight
            qty = int((equity * effective_risk_pct * 5) / price)

        # Hard cap: MAX_POSITION_PCT of equity
        max_by_position = int((equity * self.MAX_POSITION_PCT) / price)
        qty = min(qty, max_by_position)

        # Short size reduction
        if direction == "short":
            qty = int(qty * SHORT_SIZE_RATIO)

        # Min position value check
        if qty * price < self.MIN_POSITION_VALUE:
            return 0

        return max(0, qty)

    def should_enter(
        self,
        strategy_name: str,
        regime: MarketRegime,
        strategy_position_count: int,
    ) -> bool:
        """Check if strategy is allowed to enter based on allocation weight.

        Position caps are enforced by EntryManager. This method only
        checks that the regime gives a non-zero weight to the strategy.

        Args:
            strategy_name: Name of the strategy.
            regime: Current market regime.
            strategy_position_count: Number of active positions for this strategy.

        Returns:
            True if entry is allowed.
        """
        weights = self._detector.get_weights(regime)
        return weights.get(strategy_name, 0.0) >= 0.001

    def get_all_weights(self, regime: MarketRegime) -> dict[str, float]:
        """Get all strategy weights for current regime."""
        return self._detector.get_weights(regime)
