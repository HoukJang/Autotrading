"""Tests for StrategyMetaRegistry and StrategyMeta declarations.

Validates:
    - Registration mechanics (register, get, duplicate detection)
    - All active strategies are registered with correct metadata
    - Registry values match SSOT constants in trading/constants.py
    - get_meta / get_class API correctness
"""
from __future__ import annotations

import pytest

from autotrader.strategy.base import Strategy
from autotrader.strategy.registry import StrategyMeta, StrategyMetaRegistry, StrategyRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Save and restore the global StrategyMetaRegistry state around each test.

    This prevents test-level registrations from polluting the global
    registry or conflicting with the strategy module-level registrations.
    """
    saved_meta = dict(StrategyMetaRegistry._meta)
    saved_classes = dict(StrategyMetaRegistry._classes)
    yield
    StrategyMetaRegistry._meta = saved_meta
    StrategyMetaRegistry._classes = saved_classes


def _make_meta(name: str = "test_strat", **overrides) -> StrategyMeta:
    """Create a StrategyMeta with sensible defaults for testing."""
    defaults = dict(
        name=name,
        display_name="Test Strategy",
        max_positions=2,
        soft_cap=2,
        base_risk=0.02,
        sl_atr_mult={"long": 2.0},
        tp_atr_mult=3.0,
        max_hold_days=10,
        gdr_thresholds=(0.04, 0.08),
        entry_group="A",
    )
    defaults.update(overrides)
    return StrategyMeta(**defaults)


class _DummyStrategy(Strategy):
    name = "test_strat"

    def on_context(self, ctx):
        return None


class _AnotherStrategy(Strategy):
    name = "another_strat"

    def on_context(self, ctx):
        return None


# ---------------------------------------------------------------------------
# StrategyMetaRegistry -- core mechanics
# ---------------------------------------------------------------------------


class TestStrategyMetaRegistryMechanics:
    """Core registration, retrieval, and error handling."""

    def test_register_and_get_meta(self):
        meta = _make_meta()
        StrategyMetaRegistry.register(_DummyStrategy, meta)
        assert StrategyMetaRegistry.get_meta("test_strat") is meta

    def test_register_and_get_class(self):
        meta = _make_meta()
        StrategyMetaRegistry.register(_DummyStrategy, meta)
        assert StrategyMetaRegistry.get_class("test_strat") is _DummyStrategy

    def test_register_returns_class(self):
        meta = _make_meta()
        result = StrategyMetaRegistry.register(_DummyStrategy, meta)
        assert result is _DummyStrategy

    def test_duplicate_registration_raises(self):
        meta = _make_meta()
        StrategyMetaRegistry.register(_DummyStrategy, meta)
        with pytest.raises(ValueError, match="already registered"):
            StrategyMetaRegistry.register(_DummyStrategy, meta)

    def test_get_meta_unknown_returns_none(self):
        assert StrategyMetaRegistry.get_meta("nonexistent") is None

    def test_get_class_unknown_returns_none(self):
        assert StrategyMetaRegistry.get_class("nonexistent") is None

    def test_all_strategies_returns_copy(self):
        meta_a = _make_meta("strat_a")
        meta_b = _make_meta("strat_b")
        StrategyMetaRegistry.register(_DummyStrategy, meta_a)
        StrategyMetaRegistry.register(_AnotherStrategy, meta_b)
        result = StrategyMetaRegistry.all_strategies()
        assert "strat_a" in result
        assert "strat_b" in result
        # Verify it is a copy, not the internal dict
        result["strat_c"] = meta_a  # type: ignore[assignment]
        assert "strat_c" not in StrategyMetaRegistry.all_strategies()

    def test_all_names(self):
        meta_a = _make_meta("strat_a")
        meta_b = _make_meta("strat_b")
        StrategyMetaRegistry.register(_DummyStrategy, meta_a)
        StrategyMetaRegistry.register(_AnotherStrategy, meta_b)
        names = StrategyMetaRegistry.all_names()
        assert "strat_a" in names
        assert "strat_b" in names

    def test_clear(self):
        StrategyMetaRegistry.register(_DummyStrategy, _make_meta())
        StrategyMetaRegistry._clear()
        assert StrategyMetaRegistry.all_strategies() == {}
        assert StrategyMetaRegistry.all_names() == []


# ---------------------------------------------------------------------------
# StrategyMeta -- frozen dataclass
# ---------------------------------------------------------------------------


class TestStrategyMeta:
    """StrategyMeta is a frozen dataclass with correct field types."""

    def test_frozen(self):
        meta = _make_meta()
        with pytest.raises(AttributeError):
            meta.name = "changed"  # type: ignore[misc]

    def test_fields(self):
        meta = _make_meta(
            name="bm",
            display_name="Breakout Momentum",
            max_positions=2,
            soft_cap=2,
            base_risk=0.02,
            sl_atr_mult={"long": 2.5},
            tp_atr_mult=4.0,
            max_hold_days=15,
            gdr_thresholds=(0.04, 0.08),
            entry_group="A",
        )
        assert meta.name == "bm"
        assert meta.display_name == "Breakout Momentum"
        assert meta.max_positions == 2
        assert meta.soft_cap == 2
        assert meta.base_risk == 0.02
        assert meta.sl_atr_mult == {"long": 2.5}
        assert meta.tp_atr_mult == 4.0
        assert meta.max_hold_days == 15
        assert meta.gdr_thresholds == (0.04, 0.08)
        assert meta.entry_group == "A"

    def test_default_entry_group(self):
        meta = _make_meta()
        assert meta.entry_group == "A"

    def test_tp_atr_mult_none(self):
        meta = _make_meta(tp_atr_mult=None)
        assert meta.tp_atr_mult is None


# ---------------------------------------------------------------------------
# Active strategy registration verification
# ---------------------------------------------------------------------------


class TestActiveStrategyRegistrations:
    """Verify that all active strategies have registered themselves."""

    def test_breakout_momentum_registered(self):
        # Import triggers self-registration
        from autotrader.strategy.breakout_momentum import BreakoutMomentum  # noqa: F401

        meta = StrategyMetaRegistry.get_meta("breakout_momentum")
        assert meta is not None
        assert meta.display_name == "Breakout Momentum"
        assert StrategyMetaRegistry.get_class("breakout_momentum") is BreakoutMomentum

    def test_rsi_mean_reversion_registered(self):
        from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion  # noqa: F401

        meta = StrategyMetaRegistry.get_meta("rsi_mean_reversion")
        assert meta is not None
        assert meta.display_name == "RSI Mean Reversion"
        assert StrategyMetaRegistry.get_class("rsi_mean_reversion") is RsiMeanReversion

    def test_all_active_strategies_registered(self):
        """All strategies listed in STRATEGY_NAMES must be in the registry."""
        from autotrader.trading.constants import STRATEGY_NAMES

        # Trigger imports
        import autotrader.strategy.breakout_momentum  # noqa: F401
        import autotrader.strategy.rsi_mean_reversion  # noqa: F401

        registered = StrategyMetaRegistry.all_names()
        for name in STRATEGY_NAMES:
            assert name in registered, f"Strategy '{name}' not registered in StrategyMetaRegistry"


# ---------------------------------------------------------------------------
# Registry <-> constants.py SSOT sync
# ---------------------------------------------------------------------------


class TestRegistrySSOTSync:
    """Verify that registry declarations match trading/constants.py values."""

    def test_validate_registry_sync_no_errors(self):
        """The validation function should return no errors when in sync."""
        from autotrader.trading.constants import validate_registry_sync

        errors = validate_registry_sync()
        assert errors == [], f"Registry sync errors: {errors}"

    def test_breakout_momentum_constants_match(self):
        from autotrader.strategy.breakout_momentum import BreakoutMomentum  # noqa: F401
        from autotrader.trading.constants import (
            MAX_HOLD_DAYS,
            MAX_STRATEGY_POSITIONS,
            SL_ATR_MULT,
            SOFT_STRATEGY_CAP,
            STRATEGY_BASE_RISK,
            STRATEGY_GDR_THRESHOLDS,
            TP_ATR_MULT,
        )

        meta = StrategyMetaRegistry.get_meta("breakout_momentum")
        assert meta is not None

        assert meta.max_positions == MAX_STRATEGY_POSITIONS["breakout_momentum"]
        assert meta.soft_cap == SOFT_STRATEGY_CAP["breakout_momentum"]
        assert abs(meta.base_risk - STRATEGY_BASE_RISK["breakout_momentum"]) < 1e-9
        assert meta.sl_atr_mult == SL_ATR_MULT["breakout_momentum"]
        assert meta.tp_atr_mult == TP_ATR_MULT["breakout_momentum"]
        assert meta.max_hold_days == MAX_HOLD_DAYS["breakout_momentum"]
        assert meta.gdr_thresholds == STRATEGY_GDR_THRESHOLDS["breakout_momentum"]

    def test_rsi_mean_reversion_constants_match(self):
        from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion  # noqa: F401
        from autotrader.trading.constants import (
            MAX_HOLD_DAYS,
            MAX_STRATEGY_POSITIONS,
            SL_ATR_MULT,
            SOFT_STRATEGY_CAP,
            STRATEGY_BASE_RISK,
            STRATEGY_GDR_THRESHOLDS,
            TP_ATR_MULT,
        )

        meta = StrategyMetaRegistry.get_meta("rsi_mean_reversion")
        assert meta is not None

        assert meta.max_positions == MAX_STRATEGY_POSITIONS["rsi_mean_reversion"]
        assert meta.soft_cap == SOFT_STRATEGY_CAP["rsi_mean_reversion"]
        assert abs(meta.base_risk - STRATEGY_BASE_RISK["rsi_mean_reversion"]) < 1e-9
        assert meta.sl_atr_mult == SL_ATR_MULT["rsi_mean_reversion"]
        assert meta.tp_atr_mult == TP_ATR_MULT["rsi_mean_reversion"]
        assert meta.max_hold_days == MAX_HOLD_DAYS["rsi_mean_reversion"]
        assert meta.gdr_thresholds == STRATEGY_GDR_THRESHOLDS["rsi_mean_reversion"]


# ---------------------------------------------------------------------------
# Existing StrategyRegistry (instance-level) backward compat
# ---------------------------------------------------------------------------


class TestStrategyRegistryBackwardCompat:
    """Ensure the original StrategyRegistry API still works unchanged."""

    def test_register_and_get(self):
        reg = StrategyRegistry()
        strat = _DummyStrategy()
        reg.register(strat)
        assert reg.get("test_strat") is strat
        assert len(reg.all()) == 1

    def test_duplicate_raises(self):
        reg = StrategyRegistry()
        reg.register(_DummyStrategy())
        with pytest.raises(ValueError):
            reg.register(_DummyStrategy())
