"""Tests for AllocationEngine.

Covers position sizing, entry gating, weight retrieval,
regime-based variation, risk-based ATR sizing, short direction
reduction, and edge cases.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.allocation_engine import (
    RISK_PER_TRADE_PCT,
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


# ── Position size calculation tests ──────────────────────────────────


class TestGetPositionSize:
    def test_basic_position_size(self, engine: AllocationEngine):
        """equity * weight / price = shares (truncated to int)."""
        # TREND: ema_pullback weight = 0.40
        # 10000 * 0.40 / 150.0 = 26.666 -> 26 shares
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=150.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 26

    def test_position_size_truncates_to_int(self, engine: AllocationEngine):
        """Fractional shares truncated, not rounded."""
        # TREND: volume_divergence weight = 0.25
        # 10000 * 0.25 / 300.0 = 8.333... -> 8
        size = engine.get_position_size(
            strategy_name="volume_divergence", price=300.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 8

    def test_position_size_zero_when_price_zero(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=0.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 0

    def test_position_size_zero_when_price_negative(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=-50.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 0

    def test_position_size_zero_when_below_minimum(self, engine: AllocationEngine):
        """max_value < MIN_POSITION_VALUE ($200) -> 0 shares."""
        # TREND: rsi_mean_reversion weight = 0.15
        # 1000 * 0.15 = $150 < $200 minimum
        size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=50.0,
            equity=1000.0, regime=MarketRegime.TREND,
        )
        assert size == 0

    def test_position_size_unknown_strategy_returns_zero(self, engine: AllocationEngine):
        """Strategy not in weight dict -> weight 0.0 -> 0 shares."""
        size = engine.get_position_size(
            strategy_name="nonexistent_strategy", price=100.0,
            equity=50000.0, regime=MarketRegime.TREND,
        )
        assert size == 0


# ── should_enter tests ───────────────────────────────────────────────


class TestShouldEnter:
    def test_allowed_when_weight_sufficient_and_below_max(self, engine: AllocationEngine):
        """Weight >= 0.05 and position_count < 2 -> True."""
        assert engine.should_enter(
            strategy_name="ema_pullback", regime=MarketRegime.TREND,
            strategy_position_count=0,
        ) is True

    def test_allowed_with_one_existing_position(self, engine: AllocationEngine):
        assert engine.should_enter(
            strategy_name="ema_pullback", regime=MarketRegime.TREND,
            strategy_position_count=1,
        ) is True

    def test_blocked_when_weight_below_threshold(self, engine: AllocationEngine):
        """Weight < 0.05 -> entry denied.

        No strategy in the current weight tables has weight < 0.05,
        so we test with a nonexistent strategy (weight = 0.0).
        """
        assert engine.should_enter(
            strategy_name="nonexistent_strategy", regime=MarketRegime.TREND,
            strategy_position_count=0,
        ) is False

    def test_blocked_when_max_positions_reached(self, engine: AllocationEngine):
        """position_count >= MAX_POSITIONS_PER_STRATEGY (2) -> entry denied."""
        assert engine.should_enter(
            strategy_name="ema_pullback", regime=MarketRegime.TREND,
            strategy_position_count=2,
        ) is False

    def test_blocked_when_positions_exceed_max(self, engine: AllocationEngine):
        assert engine.should_enter(
            strategy_name="ema_pullback", regime=MarketRegime.TREND,
            strategy_position_count=5,
        ) is False


# ── get_all_weights tests ────────────────────────────────────────────


class TestGetAllWeights:
    def test_returns_correct_weights_for_trend(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.TREND)
        assert weights["ema_pullback"] == 0.40
        assert weights["volume_divergence"] == 0.25
        assert len(weights) == 4

    def test_returns_correct_weights_for_ranging(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.35
        assert len(weights) == 4


# ── Regime-based variation tests ─────────────────────────────────────


class TestRegimeVariation:
    def test_trend_gives_more_to_pullback_than_ranging(self, engine: AllocationEngine):
        """TREND allocates more to ema_pullback (0.40) than RANGING (0.10)."""
        trend_size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        ranging_size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.RANGING,
        )
        assert trend_size > ranging_size

    def test_ranging_gives_more_to_rsi_than_trend(self, engine: AllocationEngine):
        """RANGING allocates more to rsi_mean_reversion (0.35) than TREND (0.15)."""
        ranging_size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=100.0,
            equity=10000.0, regime=MarketRegime.RANGING,
        )
        trend_size = engine.get_position_size(
            strategy_name="rsi_mean_reversion", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert ranging_size > trend_size


# ── Small account tests ─────────────────────────────────────────────


class TestSmallAccount:
    def test_1000_equity_realistic_sizes(self, engine: AllocationEngine):
        """$1000 equity: only strategies with weight >= 0.20 can allocate ($200 min)."""
        # TREND weights: ema_pullback=0.40 -> $400 OK, vol_div=0.25 -> $250 OK,
        # consec_down=0.20 -> $200 OK, rsi_mr=0.15 -> $150 SKIP
        ema_pb = engine.get_position_size("ema_pullback", 50.0, 1000.0, MarketRegime.TREND)
        vol_div = engine.get_position_size("volume_divergence", 50.0, 1000.0, MarketRegime.TREND)
        consec = engine.get_position_size("consecutive_down", 50.0, 1000.0, MarketRegime.TREND)
        rsi_mr = engine.get_position_size("rsi_mean_reversion", 50.0, 1000.0, MarketRegime.TREND)

        assert ema_pb == 8     # 400 / 50 = 8
        assert vol_div == 5    # 250 / 50 = 5
        assert consec == 4     # 200 / 50 = 4
        assert rsi_mr == 0     # 150 < 200 minimum


# -- Risk-based sizing tests -----------------------------------------------


class TestRiskBasedSizing:
    """Tests for ATR-based risk sizing and short direction reduction."""

    def test_risk_based_sizing_limits_position(self, engine: AllocationEngine):
        """High ATR makes risk-based qty the binding constraint."""
        # TREND: ema_pullback weight = 0.40
        # weight_qty = int(10000 * 0.40 / 100) = 40
        # risk_per_trade = 10000 * 0.02 = 200
        # stop_distance = 2.0 * 8.0 = 16.0
        # risk_qty = int(200 / 16) = 12
        # qty = min(40, 12) = 12
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
            atr=8.0, direction="long",
        )
        assert size == 12

    def test_risk_based_sizing_with_low_atr(self, engine: AllocationEngine):
        """Low ATR means weight-based qty is the binding constraint."""
        # TREND: ema_pullback weight = 0.40
        # weight_qty = int(10000 * 0.40 / 100) = 40
        # risk_per_trade = 10000 * 0.02 = 200
        # stop_distance = 2.0 * 0.5 = 1.0
        # risk_qty = int(200 / 1.0) = 200
        # qty = min(40, 200) = 40
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
            atr=0.5, direction="long",
        )
        assert size == 40

    def test_short_direction_reduces_size(self, engine: AllocationEngine):
        """Short position sized at 65% of equivalent long position."""
        # TREND: ema_pullback weight = 0.40
        # weight_qty = int(10000 * 0.40 / 100) = 40
        # No ATR -> qty stays at weight_qty = 40
        # short reduction: int(40 * 0.65) = 26
        long_size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
            direction="long",
        )
        short_size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
            direction="short",
        )
        assert long_size == 40
        assert short_size == 26
        assert short_size == int(long_size * SHORT_SIZE_RATIO)

    def test_short_with_risk_based_sizing(self, engine: AllocationEngine):
        """Both risk cap and short reduction applied together."""
        # TREND: ema_pullback weight = 0.40
        # weight_qty = int(10000 * 0.40 / 100) = 40
        # risk_per_trade = 10000 * 0.02 = 200
        # stop_distance = 2.0 * 8.0 = 16.0
        # risk_qty = int(200 / 16) = 12
        # qty = min(40, 12) = 12
        # short reduction: int(12 * 0.65) = 7
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
            atr=8.0, direction="short",
        )
        assert size == 7

    def test_backward_compatibility_no_atr(self, engine: AllocationEngine):
        """When atr=None, behaves identically to the original weight-only logic."""
        # TREND: ema_pullback weight = 0.40
        # 10000 * 0.40 / 150.0 = 26.666 -> 26 shares
        size = engine.get_position_size(
            strategy_name="ema_pullback", price=150.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 26

    def test_risk_per_trade_2pct(self, engine: AllocationEngine):
        """Verify exact risk calculation: $3000 * 2% = $60, ATR=$2, stop=$4, max=15."""
        # RANGING: consecutive_down weight = 0.30
        # weight_qty = int(3000 * 0.30 / 20) = 45
        # risk_per_trade = 3000 * 0.02 = 60
        # stop_distance = 2.0 * 2.0 = 4.0
        # risk_qty = int(60 / 4.0) = 15
        # qty = min(45, 15) = 15
        # 15 * 20 = 300 >= 200 minimum -> OK
        size = engine.get_position_size(
            strategy_name="consecutive_down", price=20.0,
            equity=3000.0, regime=MarketRegime.RANGING,
            atr=2.0, direction="long",
        )
        assert size == 15

        # Confirm the risk math independently
        risk_amount = 3000.0 * RISK_PER_TRADE_PCT
        assert risk_amount == 60.0
        stop = 2.0 * 2.0
        assert stop == 4.0
        assert int(risk_amount / stop) == 15

    def test_short_minimum_position_check(self, engine: AllocationEngine):
        """Short reduction that drops qty*price below $200 returns 0."""
        # TREND: consecutive_down weight = 0.20
        # weight_qty = int(2000 * 0.20 / 150) = int(2.666) = 2
        # No ATR -> qty = 2
        # short reduction: int(2 * 0.65) = 1
        # 1 * 150 = 150 < 200 minimum -> 0
        size = engine.get_position_size(
            strategy_name="consecutive_down", price=150.0,
            equity=2000.0, regime=MarketRegime.TREND,
            direction="short",
        )
        assert size == 0

        # Verify that the long version would have passed
        long_size = engine.get_position_size(
            strategy_name="consecutive_down", price=150.0,
            equity=2000.0, regime=MarketRegime.TREND,
            direction="long",
        )
        assert long_size == 2  # 2 * 150 = 300 >= 200
