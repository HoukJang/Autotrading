"""Backward-compatible re-export of RegimeClassifier.

The canonical implementation lives in autotrader.trading.regime.
This module re-exports ``RegimeClassifier`` and the ``Regime`` alias
so that existing backtest code and tests continue to work unchanged.
"""
from autotrader.trading.regime import (
    MarketRegime as Regime,
    ALLOCATION_TABLE as _ALLOCATION_TABLE,
    RegimeClassifier,
)

__all__ = ["Regime", "RegimeClassifier"]
