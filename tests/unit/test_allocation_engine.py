"""Tests for AllocationEngine.

Covers risk-based position sizing (primary), MAX_POSITION_PCT hard cap,
entry gating, weight retrieval, regime-based variation, ATR-based sizing,
short direction reduction, GDR/safety-net hooks, and edge cases.

Updated for the risk-based primary sizing model where the regime
allocation table provides per-trade risk percentages, and
MAX_POSITION_PCT (25%) is the hard cap.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.allocation_engine import (
    SHORT_SIZE_RATIO,
    AllocationEngine,
)
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector


@pytest.fixture
def detector() -> RegimeDetector:
    return RegimeDetector()


@pytest.fixture
def engine(detector: RegimeDetector) -> AllocationEngine:
    return AllocationEngine(regime_detector=detector)


# -- Position size calculation tests ----------------------------------------


class TestGetPositionSize:
    def test_basic_position_size_fallback(self, engine: AllocationEngine):
        """Fallback sizing (no ATR/stop): qty = equity * risk * 5 / price.

        TREND_UP: breakout_momentum risk = 0.040
        qty = int(10000 * 0.040 * 5 / 150.0) = int(13.33) = 13
        max_by_position = int(10000 * 0.25 / 150) = 16
        result = min(13, 16) = 13
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=150.0,
            equity=10000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 13

    def test_position_size_truncates_to_int(self, engine: AllocationEngine):
        """Fractional shares truncated, not rounded.

        TREND_UP: breakout_momentum risk = 0.040
        qty = int(10000 * 0.040 * 5 / 130.0) = int(15.38) = 15
        max_by_position = int(10000 * 0.25 / 130) = 19
        result = min(15, 19) = 15
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=130.0,
            equity=10000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 15

    def test_position_size_zero_when_price_zero(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=0.0,
            equity=10000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 0

    def test_position_size_zero_when_price_negative(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=-50.0,
            equity=10000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 0

    def test_position_size_zero_when_below_minimum(self, engine: AllocationEngine):
        """Small equity + low risk -> qty * price < $200 minimum.

        TREND_DOWN: breakout_momentum risk = 0.005
        qty = int(1000 * 0.005 * 5 / 50.0) = int(0.5) = 0
        0 * 50 < 200 -> 0
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=50.0,
            equity=1000.0, regime=MarketRegime.TREND_DOWN,
        )
        assert size == 0

    def test_position_size_unknown_strategy_uses_default_risk(self, engine: AllocationEngine):
        """Unknown strategy gets default base_risk of 0.02.

        qty = int(5000 * 0.02 * 5 / 100) = int(5.0) = 5
        max_by_position = int(5000 * 0.25 / 100) = 12
        result = min(5, 12) = 5
        5 * 100 = 500 >= 200 -> 5
        """
        size = engine.get_position_size(
            strategy_name="nonexistent_strategy", price=100.0,
            equity=5000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 5


# -- should_enter tests -----------------------------------------------------


class TestShouldEnter:
    def test_allowed_when_weight_nonzero(self, engine: AllocationEngine):
        """Weight >= 0.001 -> True (position caps moved to EntryManager)."""
        assert engine.should_enter(
            strategy_name="breakout_momentum", regime=MarketRegime.TREND_UP,
            strategy_position_count=0,
        ) is True

    def test_allowed_regardless_of_position_count(self, engine: AllocationEngine):
        """Position cap enforcement is in EntryManager now, not here."""
        assert engine.should_enter(
            strategy_name="breakout_momentum", regime=MarketRegime.TREND_UP,
            strategy_position_count=5,
        ) is True

    def test_blocked_when_weight_zero(self, engine: AllocationEngine):
        """Weight 0.0 -> entry denied (unknown strategy)."""
        assert engine.should_enter(
            strategy_name="nonexistent_strategy", regime=MarketRegime.TREND_UP,
            strategy_position_count=0,
        ) is False


# -- get_all_weights tests --------------------------------------------------


class TestGetAllWeights:
    def test_returns_correct_weights_for_trend_up(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.TREND_UP)
        assert weights["breakout_momentum"] == 0.040
        assert weights["rsi_mean_reversion"] == 0.012
        assert len(weights) == 2

    def test_returns_correct_weights_for_ranging(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.040
        assert weights["breakout_momentum"] == 0.005
        assert len(weights) == 2


# -- Regime-based variation tests -------------------------------------------


class TestRegimeVariation:
    def test_trend_up_gives_more_to_breakout_than_ranging(self, engine: AllocationEngine):
        """TREND_UP allocates more risk to breakout_momentum (0.040) than RANGING (0.005)."""
        trend_size = engine.get_position_size(
            strategy_name="breakout_momentum", price=10.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
        )
        ranging_size = engine.get_position_size(
            strategy_name="breakout_momentum", price=10.0,
            equity=50000.0, regime=MarketRegime.RANGING,
        )
        assert trend_size > ranging_size

    def test_ranging_gives_more_to_rsi_than_trend_up(self, engine: AllocationEngine):
        """RANGING allocates more risk to rsi_mean_reversion (0.040) than TREND_UP (0.012)."""
        ranging_size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=10.0,
            equity=50000.0, regime=MarketRegime.RANGING,
        )
        trend_size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=10.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
        )
        assert ranging_size > trend_size


# -- Risk-based sizing tests ------------------------------------------------


class TestRiskBasedSizing:
    """Tests for ATR-based risk sizing and short direction reduction."""

    def test_risk_based_sizing_with_atr(self, engine: AllocationEngine):
        """ATR-based sizing: qty = risk_per_trade / (2 * ATR).

        TREND_UP: breakout_momentum risk = 0.040
        risk_per_trade = 50000 * 0.040 = 2000
        qty = int(2000 / (2 * 80)) = int(12.5) = 12
        max_by_position = int(50000 * 0.25 / 100) = 125
        result = min(12, 125) = 12
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            atr=80.0, direction="long",
        )
        assert size == 12

    def test_risk_based_sizing_with_low_atr(self, engine: AllocationEngine):
        """Low ATR gives large qty, capped by MAX_POSITION_PCT.

        TREND_UP: breakout_momentum risk = 0.040
        risk_per_trade = 50000 * 0.040 = 2000
        qty = int(2000 / (2 * 0.5)) = int(2000) = 2000
        max_by_position = int(50000 * 0.25 / 100) = 125
        result = min(2000, 125) = 125
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            atr=0.5, direction="long",
        )
        assert size == 125

    def test_short_direction_reduces_size(self, engine: AllocationEngine):
        """Short position sized at 65% of equivalent long position.

        TREND_UP: breakout_momentum risk = 0.040
        Fallback: qty = int(50000 * 0.040 * 5 / 100) = 100
        max_by_position = int(50000 * 0.25 / 100) = 125
        long_qty = min(100, 125) = 100
        short_qty = int(100 * 0.65) = 65
        """
        long_size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            direction="long",
        )
        short_size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            direction="short",
        )
        assert long_size == 100
        assert short_size == 65
        assert short_size == int(long_size * SHORT_SIZE_RATIO)

    def test_backward_compatibility_no_atr(self, engine: AllocationEngine):
        """No ATR -> fallback sizing.

        TREND_UP: breakout_momentum risk = 0.040
        qty = int(50000 * 0.040 * 5 / 150) = int(66.66) = 66
        max_by_position = int(50000 * 0.25 / 150) = 83
        result = min(66, 83) = 66
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=150.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 66

    def test_risk_sizing_with_atr_rsi_ranging(self, engine: AllocationEngine):
        """Verify ATR-based risk calculation for MR in RANGING.

        RANGING: rsi_mean_reversion risk = 0.040
        risk_per_trade = 30000 * 0.040 = 1200
        qty = int(1200 / (2 * 2.0)) = int(300) = 300
        max_by_position = int(30000 * 0.25 / 20) = 375
        result = min(300, 375) = 300
        """
        size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=20.0,
            equity=30000.0, regime=MarketRegime.RANGING,
            atr=2.0, direction="long",
        )
        assert size == 300

    def test_stop_distance_overrides_atr(self, engine: AllocationEngine):
        """Explicit stop_distance takes priority over 2*ATR.

        TREND_UP: breakout_momentum risk = 0.040
        risk_per_trade = 50000 * 0.040 = 2000
        qty = int(2000 / 10.0) = 200
        max_by_position = int(50000 * 0.25 / 100) = 125
        result = min(200, 125) = 125
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            atr=80.0, direction="long",
            stop_distance=10.0,
        )
        assert size == 125


# -- MAX_POSITION_PCT hard cap tests ----------------------------------------


class TestMaxPositionCap:
    def test_hard_cap_limits_large_positions(self, engine: AllocationEngine):
        """MAX_POSITION_PCT (25%) caps position value.

        Low-priced stock with high risk -> uncapped qty would be huge.
        equity=10000, price=1.0, risk=0.040
        fallback: qty = int(10000 * 0.040 * 5 / 1.0) = 2000
        max_by_position = int(10000 * 0.25 / 1.0) = 2500
        result = min(2000, 2500) = 2000
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=1.0,
            equity=10000.0, regime=MarketRegime.TREND_UP,
        )
        assert size == 2000

    def test_max_position_pct_is_25_percent(self, engine: AllocationEngine):
        assert engine.MAX_POSITION_PCT == 0.25


# -- GDR and safety net tests (Phase 4 hooks) --------------------------------


class TestGDRAndSafetyNet:
    def test_gdr_risk_mult_reduces_size(self, engine: AllocationEngine):
        """gdr_risk_mult=0.5 halves the effective risk.

        TREND_UP: breakout_momentum risk = 0.040
        effective_risk = 0.040 * 0.5 = 0.020
        fallback: qty = int(50000 * 0.020 * 5 / 100) = 50
        max_by_position = 125
        result = min(50, 125) = 50
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            gdr_risk_mult=0.5,
        )
        assert size == 50

    def test_safety_net_forces_half_percent_risk(self, engine: AllocationEngine):
        """safety_net_active=True forces 0.5% risk regardless of regime.

        effective_risk = 0.005
        fallback: qty = int(50000 * 0.005 * 5 / 100) = 12
        max_by_position = 125
        result = min(12, 125) = 12
        """
        size = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            safety_net_active=True,
        )
        assert size == 12

    def test_safety_net_overrides_gdr_mult(self, engine: AllocationEngine):
        """safety_net_active takes precedence over gdr_risk_mult."""
        size_safety = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            gdr_risk_mult=2.0,
            safety_net_active=True,
        )
        size_no_safety = engine.get_position_size(
            strategy_name="breakout_momentum", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND_UP,
            gdr_risk_mult=2.0,
            safety_net_active=False,
        )
        assert size_safety < size_no_safety
