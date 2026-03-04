"""Portfolio-level market regime detection.

SPY-based 5-regime classifier with 2-day confirmation.
Classifies the current market environment into one of five regimes
(TREND_UP, TREND_DOWN, RANGING, HIGH_VOLATILITY, UNCERTAIN) using
SPY ADX, close vs EMA_50 relationship, and Bollinger Band ratio.
Each regime maps to per-strategy allocation parameters including
risk percentages and entry blocking flags.
"""
from __future__ import annotations

# MarketRegime enum and allocation table are defined in the unified
# trading.regime module (SSOT).  Re-exported here for backward compat.
from autotrader.trading.regime import MarketRegime, ALLOCATION_TABLE as _ALLOCATION_TABLE


class RegimeDetector:
    """SPY-based 5-regime classifier with 2-day confirmation."""

    def __init__(self) -> None:
        self._confirmed: MarketRegime = MarketRegime.UNCERTAIN
        self._pending: MarketRegime | None = None
        self._pending_days: int = 0

    @property
    def confirmed_regime(self) -> MarketRegime:
        return self._confirmed

    def classify(
        self,
        adx: float,
        close: float,
        ema_50: float,
        bb_ratio: float,
    ) -> MarketRegime:
        """Raw classification from SPY indicators (no confirmation).

        Args:
            adx: Current ADX(14) value.
            close: SPY close price.
            ema_50: SPY EMA(50) value.
            bb_ratio: (BB_upper - BB_lower) / BB_middle.

        Returns:
            MarketRegime enum value.
        """
        if adx >= 25.0 and close > ema_50:
            return MarketRegime.TREND_UP
        if adx >= 25.0 and close < ema_50:
            return MarketRegime.TREND_DOWN
        if adx < 20.0 and bb_ratio < 0.8:
            return MarketRegime.RANGING
        if bb_ratio > 1.2 and adx < 25.0:
            return MarketRegime.HIGH_VOLATILITY
        return MarketRegime.UNCERTAIN

    def update(
        self,
        adx: float,
        close: float,
        ema_50: float,
        bb_ratio: float,
    ) -> MarketRegime:
        """Classify with 2-day confirmation. Returns confirmed regime.

        Args:
            adx: Current ADX(14) value.
            close: SPY close price.
            ema_50: SPY EMA(50) value.
            bb_ratio: (BB_upper - BB_lower) / BB_middle.

        Returns:
            The confirmed MarketRegime after applying 2-day confirmation.
        """
        raw = self.classify(adx, close, ema_50, bb_ratio)
        if raw == self._confirmed:
            self._pending = None
            self._pending_days = 0
            return self._confirmed
        if raw == self._pending:
            self._pending_days += 1
            if self._pending_days >= 2:
                self._confirmed = raw
                self._pending = None
                self._pending_days = 0
        else:
            self._pending = raw
            self._pending_days = 1
        return self._confirmed

    def get_weights(self, regime: MarketRegime) -> dict[str, float]:
        """Backward-compatible: returns risk percentages as weights."""
        alloc = self.get_allocation(regime)
        return {k: v for k, v in alloc.items() if isinstance(v, float)}

    @staticmethod
    def get_allocation(regime: MarketRegime) -> dict:
        """Return full allocation dict for a given regime."""
        return dict(_ALLOCATION_TABLE[regime])
