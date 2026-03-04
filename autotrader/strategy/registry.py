"""Strategy registry for instance management and auto-discovery metadata.

Two complementary registries:

1. ``StrategyRegistry`` -- instance-level registry used by the live system
   and engine to manage instantiated Strategy objects.  (Unchanged API.)

2. ``StrategyMetaRegistry`` -- class-level registry where each strategy
   self-declares its constants (position caps, risk parameters, GDR
   thresholds, etc.) via a ``StrategyMeta`` dataclass.  This enables
   zero-touch strategy addition: new strategies register themselves at
   import time, and consumers can query the registry instead of manually
   editing multiple constant dictionaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from autotrader.strategy.base import Strategy


# ---------------------------------------------------------------------------
# Instance-level registry (existing API -- unchanged)
# ---------------------------------------------------------------------------


class StrategyRegistry:
    """Runtime registry of instantiated Strategy objects."""

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        if strategy.name in self._strategies:
            raise ValueError(f"Strategy already registered: {strategy.name}")
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Strategy | None:
        return self._strategies.get(name)

    def all(self) -> list[Strategy]:
        return list(self._strategies.values())


# ---------------------------------------------------------------------------
# Metadata declaration (new)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyMeta:
    """Constants and metadata for a strategy, declared by the strategy itself.

    Each strategy module registers a ``StrategyMeta`` instance at import
    time so that its trading constants are co-located with its logic
    rather than scattered across ``trading/constants.py``.
    """

    name: str                                  # e.g. "breakout_momentum"
    display_name: str                          # e.g. "Breakout Momentum"
    max_positions: int                         # per-strategy position cap
    soft_cap: int                              # soft cap for allocation
    base_risk: float                           # base risk per trade
    sl_atr_mult: dict[str, float]              # {"long": 2.5} or {"long": 2.0, "short": 2.5}
    tp_atr_mult: float | None                  # TP ATR multiplier (None = indicator-based)
    max_hold_days: int                         # max bars in position
    gdr_thresholds: tuple[float, float]        # (tier1, tier2) drawdown thresholds
    entry_group: str = "A"                     # "A" (MOO) or "B" (Confirm)


# ---------------------------------------------------------------------------
# Class-level metadata registry (new)
# ---------------------------------------------------------------------------


class StrategyMetaRegistry:
    """Global registry of strategy metadata declarations.

    Strategies register themselves at module import time via
    ``StrategyMetaRegistry.register()``.  Consumers (batch_simulator,
    allocation engine, etc.) can query this registry for strategy
    constants instead of maintaining separate dictionaries.
    """

    _meta: dict[str, StrategyMeta] = {}
    _classes: dict[str, Type[Strategy]] = {}

    @classmethod
    def register(cls, strategy_class: Type[Strategy], meta: StrategyMeta) -> Type[Strategy]:
        """Register a strategy class with its metadata.

        Returns the strategy class unchanged, so this can be used as a
        post-class-definition call.
        """
        if meta.name in cls._meta:
            raise ValueError(f"Strategy metadata already registered: {meta.name}")
        cls._meta[meta.name] = meta
        cls._classes[meta.name] = strategy_class
        return strategy_class

    @classmethod
    def get_meta(cls, name: str) -> StrategyMeta | None:
        """Return the metadata for a registered strategy, or None."""
        return cls._meta.get(name)

    @classmethod
    def get_class(cls, name: str) -> Type[Strategy] | None:
        """Return the strategy class for a registered strategy, or None."""
        return cls._classes.get(name)

    @classmethod
    def all_strategies(cls) -> dict[str, StrategyMeta]:
        """Return a copy of all registered strategy metadata."""
        return dict(cls._meta)

    @classmethod
    def all_names(cls) -> list[str]:
        """Return a list of all registered strategy names."""
        return list(cls._meta.keys())

    @classmethod
    def _clear(cls) -> None:
        """Clear all registrations. For testing only."""
        cls._meta.clear()
        cls._classes.clear()
