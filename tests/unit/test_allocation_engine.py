"""Tests for AllocationEngine.

Covers position sizing, entry gating, weight retrieval,
regime-based variation, and edge cases.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.allocation_engine import AllocationEngine
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
        # TREND: adx_pullback weight = 0.30
        # 10000 * 0.30 / 150.0 = 20 shares
        size = engine.get_position_size(
            strategy_name="adx_pullback", price=150.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 20

    def test_position_size_truncates_to_int(self, engine: AllocationEngine):
        """Fractional shares truncated, not rounded."""
        # TREND: regime_momentum weight = 0.25
        # 10000 * 0.25 / 300.0 = 8.333... -> 8
        size = engine.get_position_size(
            strategy_name="regime_momentum", price=300.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 8

    def test_position_size_zero_when_price_zero(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="adx_pullback", price=0.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 0

    def test_position_size_zero_when_price_negative(self, engine: AllocationEngine):
        size = engine.get_position_size(
            strategy_name="adx_pullback", price=-50.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        assert size == 0

    def test_position_size_zero_when_below_minimum(self, engine: AllocationEngine):
        """max_value < MIN_POSITION_VALUE ($200) -> 0 shares."""
        # TREND: overbought_short weight = 0.10
        # 1000 * 0.10 = $100 < $200 minimum
        size = engine.get_position_size(
            strategy_name="overbought_short", price=50.0,
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
            strategy_name="adx_pullback", regime=MarketRegime.TREND,
            strategy_position_count=0,
        ) is True

    def test_allowed_with_one_existing_position(self, engine: AllocationEngine):
        assert engine.should_enter(
            strategy_name="adx_pullback", regime=MarketRegime.TREND,
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
            strategy_name="adx_pullback", regime=MarketRegime.TREND,
            strategy_position_count=2,
        ) is False

    def test_blocked_when_positions_exceed_max(self, engine: AllocationEngine):
        assert engine.should_enter(
            strategy_name="adx_pullback", regime=MarketRegime.TREND,
            strategy_position_count=5,
        ) is False


# ── get_all_weights tests ────────────────────────────────────────────


class TestGetAllWeights:
    def test_returns_correct_weights_for_trend(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.TREND)
        assert weights["adx_pullback"] == 0.30
        assert weights["regime_momentum"] == 0.25
        assert len(weights) == 5

    def test_returns_correct_weights_for_ranging(self, engine: AllocationEngine):
        weights = engine.get_all_weights(MarketRegime.RANGING)
        assert weights["rsi_mean_reversion"] == 0.35
        assert len(weights) == 5


# ── Regime-based variation tests ─────────────────────────────────────


class TestRegimeVariation:
    def test_trend_gives_more_to_pullback_than_ranging(self, engine: AllocationEngine):
        """TREND allocates more to adx_pullback (0.30) than RANGING (0.10)."""
        trend_size = engine.get_position_size(
            strategy_name="adx_pullback", price=100.0,
            equity=10000.0, regime=MarketRegime.TREND,
        )
        ranging_size = engine.get_position_size(
            strategy_name="adx_pullback", price=100.0,
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
        # TREND weights: pullback=0.30 -> $300 OK, momentum=0.25 -> $250 OK,
        # squeeze=0.20 -> $200 OK, rsi_mr=0.15 -> $150 SKIP, short=0.10 -> $100 SKIP
        pullback = engine.get_position_size("adx_pullback", 50.0, 1000.0, MarketRegime.TREND)
        momentum = engine.get_position_size("regime_momentum", 50.0, 1000.0, MarketRegime.TREND)
        squeeze = engine.get_position_size("bb_squeeze", 50.0, 1000.0, MarketRegime.TREND)
        rsi_mr = engine.get_position_size("rsi_mean_reversion", 50.0, 1000.0, MarketRegime.TREND)
        short = engine.get_position_size("overbought_short", 50.0, 1000.0, MarketRegime.TREND)

        assert pullback == 6   # 300 / 50 = 6
        assert momentum == 5   # 250 / 50 = 5
        assert squeeze == 4    # 200 / 50 = 4
        assert rsi_mr == 0     # 150 < 200 minimum
        assert short == 0      # 100 < 200 minimum
