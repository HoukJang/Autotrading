"""SPY-based market regime classifier for active strategy allocation.

Classifies market regime using SPY ADX, EMA(50), and BB width ratio.
Provides per-strategy risk allocation based on confirmed regime.
Regime transitions require 2 consecutive days of the same classification.
"""
from __future__ import annotations

from enum import Enum


class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


# Allocation table: regime -> {strategy: risk, blocks}
# BM + rsi_mean_reversion 2-strategy portfolio with complementary balancing
_ALLOCATION_TABLE: dict[Regime, dict] = {
    Regime.TREND_UP: {
        "breakout_momentum": 0.040,     # BM dominant (unchanged)
        "rsi_mean_reversion": 0.012,    # MR allocation (Iter 26: reverted to Iter 23)
        "breakout_blocked": False,
        "mr_short_blocked": True,       # no shorting in uptrend
    },
    Regime.TREND_DOWN: {
        "breakout_momentum": 0.005,     # BM minimal (unchanged)
        "rsi_mean_reversion": 0.025,    # MR strong (unchanged)
        "breakout_blocked": True,       # no BM in downtrend
        "mr_short_blocked": False,
    },
    Regime.RANGING: {
        "breakout_momentum": 0.005,     # BM minimized (was 0.008)
        "rsi_mean_reversion": 0.040,    # MR dominant (was 0.035)
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
    Regime.HIGH_VOLATILITY: {
        "breakout_momentum": 0.005,     # BM minimized (was 0.008)
        "rsi_mean_reversion": 0.020,    # MR increased (was 0.015)
        "breakout_blocked": False,
        "mr_short_blocked": True,       # no shorting in high vol
    },
    Regime.UNCERTAIN: {
        "breakout_momentum": 0.008,     # BM reduced (was 0.012)
        "rsi_mean_reversion": 0.025,    # MR increased (was 0.020)
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
}


class RegimeClassifier:
    """Classifies market regime from SPY indicators with 2-day confirmation."""

    def __init__(self) -> None:
        self._confirmed: Regime = Regime.UNCERTAIN
        self._pending: Regime | None = None
        self._pending_days: int = 0

    @property
    def confirmed_regime(self) -> Regime:
        return self._confirmed

    def classify(
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
    ) -> Regime:
        """Classify regime from raw indicators (no confirmation logic)."""
        if adx >= 25.0 and close > ema_50:
            return Regime.TREND_UP
        if adx >= 25.0 and close < ema_50:
            return Regime.TREND_DOWN
        if adx < 20.0 and bb_ratio < 0.8:
            return Regime.RANGING
        if bb_ratio > 1.2 and adx < 25.0:
            return Regime.HIGH_VOLATILITY
        return Regime.UNCERTAIN

    def update(
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
    ) -> Regime:
        """Classify and apply 2-day confirmation logic. Returns confirmed regime."""
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

    @staticmethod
    def get_allocation(regime: Regime) -> dict:
        """Return allocation dict for a given regime."""
        return dict(_ALLOCATION_TABLE[regime])
