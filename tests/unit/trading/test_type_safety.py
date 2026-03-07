"""Tests for type-safe dataclasses: RegimeAllocation and TradeMetaSnapshot.

Validates that the frozen RegimeAllocation dataclass correctly replaced the
former untyped dict entries in ALLOCATION_TABLE, and that TradeMetaSnapshot
handles missing keys and nested metadata gracefully.
"""
from __future__ import annotations

import pytest

from autotrader.trading.regime import (
    ALLOCATION_TABLE,
    MarketRegime,
    RegimeAllocation,
    RegimeClassifier,
)
from autotrader.trading.types import TradeMetaSnapshot


# ---------------------------------------------------------------------------
# RegimeAllocation dataclass tests
# ---------------------------------------------------------------------------


class TestRegimeAllocation:
    """RegimeAllocation dataclass field access and defaults."""

    def test_default_values(self):
        alloc = RegimeAllocation()
        assert alloc.breakout_momentum == 0.0
        assert alloc.rsi_mean_reversion == 0.0
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is False

    def test_custom_values(self):
        alloc = RegimeAllocation(
            breakout_momentum=0.04,
            rsi_mean_reversion=0.012,
            breakout_blocked=False,
            mr_short_blocked=True,
        )
        assert alloc.breakout_momentum == 0.04
        assert alloc.rsi_mean_reversion == 0.012
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is True

    def test_frozen_immutability(self):
        alloc = RegimeAllocation(breakout_momentum=0.04)
        with pytest.raises(AttributeError):
            alloc.breakout_momentum = 0.05  # type: ignore[misc]

    def test_get_risk_breakout_momentum(self):
        alloc = RegimeAllocation(breakout_momentum=0.04, rsi_mean_reversion=0.012)
        assert alloc.get_risk("breakout_momentum") == 0.04

    def test_get_risk_rsi_mean_reversion(self):
        alloc = RegimeAllocation(breakout_momentum=0.04, rsi_mean_reversion=0.012)
        assert alloc.get_risk("rsi_mean_reversion") == 0.012

    def test_get_risk_unknown_strategy_returns_default(self):
        alloc = RegimeAllocation(breakout_momentum=0.04)
        assert alloc.get_risk("unknown_strategy") == 0.0
        assert alloc.get_risk("unknown_strategy", 0.02) == 0.02

    def test_equality(self):
        a = RegimeAllocation(breakout_momentum=0.04, mr_short_blocked=True)
        b = RegimeAllocation(breakout_momentum=0.04, mr_short_blocked=True)
        assert a == b

    def test_inequality(self):
        a = RegimeAllocation(breakout_momentum=0.04)
        b = RegimeAllocation(breakout_momentum=0.05)
        assert a != b


# ---------------------------------------------------------------------------
# ALLOCATION_TABLE structure tests
# ---------------------------------------------------------------------------


class TestAllocationTable:
    """ALLOCATION_TABLE returns RegimeAllocation instances for every regime."""

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_all_regimes_present(self, regime: MarketRegime):
        assert regime in ALLOCATION_TABLE

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_all_entries_are_regime_allocation(self, regime: MarketRegime):
        alloc = ALLOCATION_TABLE[regime]
        assert isinstance(alloc, RegimeAllocation)

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_risk_fractions_are_positive(self, regime: MarketRegime):
        alloc = ALLOCATION_TABLE[regime]
        assert alloc.breakout_momentum >= 0.0
        assert alloc.rsi_mean_reversion >= 0.0

    def test_trend_up_values_match(self):
        alloc = ALLOCATION_TABLE[MarketRegime.TREND_UP]
        assert alloc.breakout_momentum == 0.040
        assert alloc.rsi_mean_reversion == 0.012
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is True

    def test_trend_down_values_match(self):
        alloc = ALLOCATION_TABLE[MarketRegime.TREND_DOWN]
        assert alloc.breakout_momentum == 0.005
        assert alloc.rsi_mean_reversion == 0.025
        assert alloc.breakout_blocked is True
        assert alloc.mr_short_blocked is False

    def test_ranging_values_match(self):
        alloc = ALLOCATION_TABLE[MarketRegime.RANGING]
        assert alloc.breakout_momentum == 0.005
        assert alloc.rsi_mean_reversion == 0.040
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is False

    def test_high_vol_values_match(self):
        alloc = ALLOCATION_TABLE[MarketRegime.HIGH_VOLATILITY]
        assert alloc.breakout_momentum == 0.005
        assert alloc.rsi_mean_reversion == 0.020
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is True

    def test_uncertain_values_match(self):
        alloc = ALLOCATION_TABLE[MarketRegime.UNCERTAIN]
        assert alloc.breakout_momentum == 0.008
        assert alloc.rsi_mean_reversion == 0.025
        assert alloc.breakout_blocked is False
        assert alloc.mr_short_blocked is False


class TestRegimeClassifierAllocationAccess:
    """get_allocation returns RegimeAllocation, get_weights returns dict."""

    def test_get_allocation_returns_regime_allocation(self):
        alloc = RegimeClassifier.get_allocation(MarketRegime.TREND_UP)
        assert isinstance(alloc, RegimeAllocation)

    def test_get_weights_returns_dict_of_floats(self):
        rc = RegimeClassifier()
        weights = rc.get_weights(MarketRegime.TREND_UP)
        assert isinstance(weights, dict)
        assert len(weights) == 2
        assert all(isinstance(v, float) for v in weights.values())

    def test_get_weights_excludes_booleans(self):
        rc = RegimeClassifier()
        weights = rc.get_weights(MarketRegime.TREND_UP)
        assert "breakout_blocked" not in weights
        assert "mr_short_blocked" not in weights

    def test_get_weights_returns_copy(self):
        rc = RegimeClassifier()
        weights = rc.get_weights(MarketRegime.TREND_UP)
        original = weights["breakout_momentum"]
        weights["breakout_momentum"] = 999.0
        fresh = rc.get_weights(MarketRegime.TREND_UP)
        assert fresh["breakout_momentum"] == original


# ---------------------------------------------------------------------------
# TradeMetaSnapshot tests
# ---------------------------------------------------------------------------


class TestTradeMetaSnapshot:
    """TradeMetaSnapshot construction and from_dict backward compat."""

    def test_default_values(self):
        snap = TradeMetaSnapshot()
        assert snap.strategy == "unknown"
        assert snap.direction == "long"
        assert snap.entry_atr == 0.0
        assert snap.entry_adx == 0.0
        assert snap.sub_strategy == ""
        assert snap.timestamp == ""

    def test_custom_values(self):
        snap = TradeMetaSnapshot(
            strategy="breakout_momentum",
            direction="short",
            entry_atr=2.5,
            entry_adx=30.0,
            sub_strategy="breakout_high",
            timestamp="2025-06-01T10:00:00",
        )
        assert snap.strategy == "breakout_momentum"
        assert snap.direction == "short"
        assert snap.entry_atr == 2.5
        assert snap.entry_adx == 30.0
        assert snap.sub_strategy == "breakout_high"
        assert snap.timestamp == "2025-06-01T10:00:00"

    def test_from_dict_full(self):
        data = {
            "strategy": "rsi_mean_reversion",
            "direction": "short",
            "timestamp": "2025-06-01T10:00:00",
            "metadata": {
                "entry_atr": 1.5,
                "entry_adx": 18.0,
                "sub_strategy": "bb_cross",
            },
        }
        snap = TradeMetaSnapshot.from_dict(data)
        assert snap.strategy == "rsi_mean_reversion"
        assert snap.direction == "short"
        assert snap.entry_atr == 1.5
        assert snap.entry_adx == 18.0
        assert snap.sub_strategy == "bb_cross"
        assert snap.timestamp == "2025-06-01T10:00:00"

    def test_from_dict_missing_metadata(self):
        data = {"strategy": "breakout_momentum"}
        snap = TradeMetaSnapshot.from_dict(data)
        assert snap.strategy == "breakout_momentum"
        assert snap.direction == "long"
        assert snap.entry_atr == 0.0
        assert snap.entry_adx == 0.0
        assert snap.sub_strategy == ""

    def test_from_dict_empty_dict(self):
        snap = TradeMetaSnapshot.from_dict({})
        assert snap.strategy == "unknown"
        assert snap.direction == "long"
        assert snap.entry_atr == 0.0

    def test_from_dict_partial_metadata(self):
        data = {
            "strategy": "breakout_momentum",
            "metadata": {"entry_atr": 3.0},
        }
        snap = TradeMetaSnapshot.from_dict(data)
        assert snap.entry_atr == 3.0
        assert snap.entry_adx == 0.0
        assert snap.sub_strategy == ""

    def test_from_dict_coerces_types(self):
        """Numeric strings in metadata should be coerced to float."""
        data = {
            "metadata": {
                "entry_atr": "2.5",
                "entry_adx": "28",
                "sub_strategy": 42,
            },
        }
        snap = TradeMetaSnapshot.from_dict(data)
        assert snap.entry_atr == 2.5
        assert snap.entry_adx == 28.0
        assert snap.sub_strategy == "42"

    def test_mutable_by_default(self):
        """TradeMetaSnapshot is mutable (not frozen) for cache updates."""
        snap = TradeMetaSnapshot()
        snap.strategy = "rsi_mean_reversion"
        assert snap.strategy == "rsi_mean_reversion"
