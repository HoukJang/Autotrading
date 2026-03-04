"""Unified market regime enum and allocation table.

Single Source of Truth for the MarketRegime classification and the
per-strategy allocation table used by both the live system
(portfolio/regime_detector.py) and the backtester
(backtest/regime_classifier.py).

The enum is named ``MarketRegime`` for backward compatibility with the
live system.  The backtest module re-exports it as ``Regime``.
"""
from __future__ import annotations

from enum import Enum


class MarketRegime(Enum):
    """Market regime classification."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


# Allocation table: regime -> {strategy: risk_pct, blocking flags}
# BM + MR 2-strategy portfolio (Iter 29 configuration)
ALLOCATION_TABLE: dict[MarketRegime, dict] = {
    MarketRegime.TREND_UP: {
        "breakout_momentum": 0.040,
        "rsi_mean_reversion": 0.012,
        "breakout_blocked": False,
        "mr_short_blocked": True,
    },
    MarketRegime.TREND_DOWN: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.025,
        "breakout_blocked": True,
        "mr_short_blocked": False,
    },
    MarketRegime.RANGING: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.040,
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.020,
        "breakout_blocked": False,
        "mr_short_blocked": True,
    },
    MarketRegime.UNCERTAIN: {
        "breakout_momentum": 0.008,
        "rsi_mean_reversion": 0.025,
        "breakout_blocked": False,
        "mr_short_blocked": False,
    },
}
