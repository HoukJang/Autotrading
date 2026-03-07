"""Unified market regime enum, allocation table, and classifier.

Single Source of Truth for the MarketRegime classification, the
per-strategy allocation table, and the SPY-based regime classifier
used by both the live system (portfolio/regime_detector.py) and the
backtester (backtest/regime_classifier.py).

The enum is named ``MarketRegime`` for backward compatibility with the
live system.  The backtest module re-exports it as ``Regime``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketRegime(Enum):
    """Market regime classification."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class RegimeAllocation:
    """Per-regime allocation parameters for each strategy.

    Replaces the former untyped ``dict`` entries in ALLOCATION_TABLE that
    mixed float risk fractions with boolean blocking flags, causing type
    confusion and requiring isinstance guards at every call-site.

    Attributes:
        breakout_momentum: Capital risk fraction for breakout momentum strategy.
        rsi_mean_reversion: Capital risk fraction for RSI mean-reversion strategy.
        breakout_blocked: Whether breakout entries are blocked in this regime.
        mr_short_blocked: Whether mean-reversion short entries are blocked.
    """

    breakout_momentum: float = 0.0
    rsi_mean_reversion: float = 0.0
    breakout_blocked: bool = False
    mr_short_blocked: bool = False

    def get_risk(self, strategy_name: str, default: float = 0.0) -> float:
        """Return the risk fraction for a given strategy name.

        This provides a dict-like lookup interface for callers that
        resolve the strategy name at runtime (e.g., batch_simulator).

        Args:
            strategy_name: ``"breakout_momentum"`` or ``"rsi_mean_reversion"``.
            default: Value to return if the strategy name is unrecognized.

        Returns:
            The risk fraction, or *default* for unknown strategy names.
        """
        if strategy_name == "breakout_momentum":
            return self.breakout_momentum
        if strategy_name == "rsi_mean_reversion":
            return self.rsi_mean_reversion
        return default


# Allocation table: regime -> RegimeAllocation (strategy risk fractions + blocking flags)
# BM + MR 2-strategy portfolio (Iter 29 configuration)
ALLOCATION_TABLE: dict[MarketRegime, RegimeAllocation] = {
    MarketRegime.TREND_UP: RegimeAllocation(
        breakout_momentum=0.040,
        rsi_mean_reversion=0.012,
        breakout_blocked=False,
        mr_short_blocked=True,
    ),
    MarketRegime.TREND_DOWN: RegimeAllocation(
        breakout_momentum=0.005,
        rsi_mean_reversion=0.025,
        breakout_blocked=True,
        mr_short_blocked=False,
    ),
    MarketRegime.RANGING: RegimeAllocation(
        breakout_momentum=0.005,
        rsi_mean_reversion=0.040,
        breakout_blocked=False,
        mr_short_blocked=False,
    ),
    MarketRegime.HIGH_VOLATILITY: RegimeAllocation(
        breakout_momentum=0.005,
        rsi_mean_reversion=0.020,
        breakout_blocked=False,
        mr_short_blocked=True,
    ),
    MarketRegime.UNCERTAIN: RegimeAllocation(
        breakout_momentum=0.008,
        rsi_mean_reversion=0.025,
        breakout_blocked=False,
        mr_short_blocked=False,
    ),
}


class RegimeClassifier:
    """SPY-based 5-regime classifier with 2-day confirmation.

    Single Source of Truth for regime classification logic.
    Used by both live trading and backtesting systems.
    """

    def __init__(self) -> None:
        self._confirmed: MarketRegime = MarketRegime.UNCERTAIN
        self._pending: MarketRegime | None = None
        self._pending_days: int = 0

    @property
    def confirmed_regime(self) -> MarketRegime:
        return self._confirmed

    def classify(
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
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
        self, adx: float, close: float, ema_50: float, bb_ratio: float,
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
        """Return risk percentages as weights (backward compat).

        Extracts only the float-valued strategy risk fractions from the
        ``RegimeAllocation`` dataclass, excluding boolean blocking flags.
        """
        alloc = ALLOCATION_TABLE[regime]
        return {
            "breakout_momentum": alloc.breakout_momentum,
            "rsi_mean_reversion": alloc.rsi_mean_reversion,
        }

    @staticmethod
    def get_allocation(regime: MarketRegime) -> RegimeAllocation:
        """Return the RegimeAllocation for a given regime."""
        return ALLOCATION_TABLE[regime]
