"""Capital allocation engine based on market regime.

Thin wrapper around ``PositionSizer`` from the unified trading core.
Determines effective risk percentage from the regime allocation table
and GDR/safety-net state, then delegates position sizing to the
unified ``PositionSizer``.

Position caps are managed by EntryManager (not duplicated here).
"""
from __future__ import annotations

from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.trading.constants import (
    DEFAULT_BASE_RISK,
    PORTFOLIO_SAFETY_NET_RISK,
    SHORT_SIZE_RATIO,
    MAX_POSITION_PCT as _MAX_POSITION_PCT,
    MIN_POSITION_VALUE as _MIN_POSITION_VALUE,
)
from autotrader.trading.position_sizer import PositionSizer


class AllocationEngine:
    """Risk-based position sizing engine driven by market regime.

    Delegates core sizing to ``PositionSizer`` from the unified trading
    core.  This wrapper handles regime-based risk determination and the
    fallback sizing path when no ATR or stop_distance is available.
    """

    MIN_POSITION_VALUE: float = _MIN_POSITION_VALUE
    MAX_POSITION_PCT: float = _MAX_POSITION_PCT

    def __init__(self, regime_detector: RegimeDetector) -> None:
        self._detector = regime_detector
        self._sizer = PositionSizer(
            max_position_pct=_MAX_POSITION_PCT,
            min_position_value=_MIN_POSITION_VALUE,
            short_size_ratio=SHORT_SIZE_RATIO,
        )

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
            effective_risk_pct = PORTFOLIO_SAFETY_NET_RISK
        else:
            alloc = self._detector.get_allocation(regime)
            base_risk = alloc.get_risk(strategy_name, DEFAULT_BASE_RISK)
            effective_risk_pct = base_risk * gdr_risk_mult

        # Determine the effective stop distance for the PositionSizer
        effective_stop_distance: float
        if stop_distance is not None and stop_distance > 0:
            effective_stop_distance = stop_distance
        elif atr is not None and atr > 0:
            effective_stop_distance = 2.0 * atr
        else:
            # Fallback: treat risk as position weight.
            # This path cannot be delegated to PositionSizer because
            # the sizer requires a positive stop_distance.
            qty = int((equity * effective_risk_pct * 5) / price)
            max_by_position = int((equity * self.MAX_POSITION_PCT) / price)
            qty = min(qty, max_by_position)
            if direction == "short":
                qty = int(qty * SHORT_SIZE_RATIO)
            if qty * price < self.MIN_POSITION_VALUE:
                return 0
            return max(0, qty)

        # Delegate to unified PositionSizer
        return self._sizer.calculate(
            equity=equity,
            price=price,
            stop_distance=effective_stop_distance,
            direction=direction,
            risk_pct=effective_risk_pct,
        )

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
