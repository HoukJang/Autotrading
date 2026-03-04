"""Unified position sizer for risk-based position sizing.

Replaces the duplicated sizing logic between:
  - Live: ``autotrader.portfolio.allocation_engine.AllocationEngine.get_position_size``
  - Backtest: ``autotrader.backtest.batch_simulator.BatchSimulator._calculate_qty``

This module provides the pure sizing calculation only -- it does NOT
handle regime detection, GDR tier computation, or safety-net activation.
The caller is responsible for determining the effective risk percentage
and passing it in.
"""
from __future__ import annotations

import logging

from autotrader.trading.constants import (
    MAX_POSITION_PCT,
    MIN_POSITION_VALUE,
    SHORT_SIZE_RATIO,
)

logger = logging.getLogger("autotrader.trading.position_sizer")


class PositionSizer:
    """Risk-based position sizing engine.

    Pure calculation: given equity, price, stop distance, and effective
    risk percentage, compute the number of shares to trade.

    Sizing steps:
        1. ``risk_amount = equity * risk_pct``
        2. ``qty = risk_amount / stop_distance``
        3. Hard cap: ``qty * price <= equity * MAX_POSITION_PCT``
        4. Short adjustment: ``qty *= SHORT_SIZE_RATIO`` if short
        5. Min value check: ``qty * price >= MIN_POSITION_VALUE`` (else 0)

    All constants are imported from ``autotrader.trading.constants``.
    """

    def __init__(
        self,
        max_position_pct: float = MAX_POSITION_PCT,
        min_position_value: float = MIN_POSITION_VALUE,
        short_size_ratio: float = SHORT_SIZE_RATIO,
    ) -> None:
        self._max_position_pct = max_position_pct
        self._min_position_value = min_position_value
        self._short_size_ratio = short_size_ratio

    def calculate(
        self,
        equity: float,
        price: float,
        stop_distance: float,
        direction: str = "long",
        risk_pct: float = 0.02,
    ) -> int:
        """Calculate the number of shares to trade.

        Args:
            equity: Current portfolio equity in dollars.
            price: Asset price (entry price or current price).
            stop_distance: Absolute dollar distance from entry to
                stop-loss (must be > 0).
            direction: Trade direction, ``"long"`` or ``"short"``.
            risk_pct: Effective per-trade risk as a fraction of equity.
                This should already incorporate regime adjustments,
                GDR multiplier, and safety-net overrides.

        Returns:
            Number of shares to trade.  Returns 0 if:
            - price or stop_distance is <= 0
            - computed position value is below MIN_POSITION_VALUE
        """
        if price <= 0 or stop_distance <= 0:
            return 0

        # Step 1-2: risk-based sizing
        risk_amount = equity * risk_pct
        qty = int(risk_amount / stop_distance)

        # Step 3: hard cap at MAX_POSITION_PCT of equity
        max_by_position = int((equity * self._max_position_pct) / price)
        qty = min(qty, max_by_position)

        # Step 4: short size reduction
        if direction == "short":
            qty = int(qty * self._short_size_ratio)

        # Step 5: minimum position value check
        if qty * price < self._min_position_value:
            return 0

        return max(0, qty)
