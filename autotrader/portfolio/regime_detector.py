"""Backward-compatible re-export of RegimeDetector.

The canonical implementation lives in autotrader.trading.regime.
``RegimeDetector`` is an alias for ``RegimeClassifier`` so that
existing live-trading code and tests continue to work unchanged.
"""
from autotrader.trading.regime import (
    MarketRegime,
    ALLOCATION_TABLE as _ALLOCATION_TABLE,
    RegimeAllocation,
    RegimeClassifier as RegimeDetector,
)

__all__ = ["MarketRegime", "RegimeAllocation", "RegimeDetector", "_ALLOCATION_TABLE"]
