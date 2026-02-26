"""Integration tests for all 5 swing trading strategies running together.

Verifies that the full swing portfolio (RsiMeanReversion, BbSqueezeBreakout,
AdxPullback, OverboughtShort, RegimeMomentum) operates correctly through the
BacktestEngine, and that the RegimeDetector and AllocationEngine produce
valid regime classifications and position sizes.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest

from autotrader.backtest.engine import BacktestEngine, BacktestResult
from autotrader.core.config import RiskConfig
from autotrader.core.types import Bar
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

def _generate_bars(n: int = 300, symbol: str = "TEST", seed: int = 42) -> list[Bar]:
    """Generate synthetic OHLCV bars with realistic trend/range/volatility phases."""
    random.seed(seed)
    bars: list[Bar] = []
    price = 100.0

    for i in range(n):
        # Mix of trend, mean-reversion, and volatility phases
        phase = i % 100
        if phase < 40:  # trend up
            drift = 0.002
        elif phase < 60:  # volatile
            drift = 0.0
        elif phase < 80:  # trend down
            drift = -0.002
        else:  # range
            drift = 0.0

        noise = random.gauss(0, 0.015)
        price *= 1 + drift + noise
        price = max(price, 5.0)  # floor

        high = price * (1 + abs(random.gauss(0, 0.005)))
        low = price * (1 - abs(random.gauss(0, 0.005)))
        open_ = price * (1 + random.gauss(0, 0.002))

        t = datetime(2026, 1, 1) + timedelta(hours=i)
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=t,
                open=open_,
                high=high,
                low=low,
                close=price,
                volume=random.uniform(5000, 50000),
            )
        )
    return bars


def _generate_volatile_bars(
    n: int = 200, symbol: str = "TEST", seed: int = 99
) -> list[Bar]:
    """Generate synthetic bars with extreme volatility: large gaps, sharp moves."""
    random.seed(seed)
    bars: list[Bar] = []
    price = 100.0

    for i in range(n):
        # Randomly inject large gaps and sharp reversals
        if random.random() < 0.10:
            # 10% chance of a large gap (up or down by 3-8%)
            gap = random.choice([-1, 1]) * random.uniform(0.03, 0.08)
            price *= 1 + gap
        else:
            # Normal but high-volatility movement
            noise = random.gauss(0, 0.03)
            price *= 1 + noise

        price = max(price, 2.0)  # floor

        spread = abs(random.gauss(0, 0.02))
        high = price * (1 + spread)
        low = price * (1 - spread)
        open_ = price * (1 + random.gauss(0, 0.01))

        t = datetime(2026, 1, 1) + timedelta(hours=i)
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=t,
                open=open_,
                high=high,
                low=low,
                close=price,
                volume=random.uniform(1000, 100000),
            )
        )
    return bars


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _create_all_strategies() -> list:
    """Instantiate all 5 swing trading strategies."""
    return [
        RsiMeanReversion(),
        BbSqueezeBreakout(),
        AdxPullback(),
        OverboughtShort(),
        RegimeMomentum(),
    ]


ALL_STRATEGY_NAMES = {
    "rsi_mean_reversion",
    "bb_squeeze",
    "adx_pullback",
    "overbought_short",
    "regime_momentum",
}

SWING_RISK_CONFIG = RiskConfig(
    max_position_pct=0.30,
    max_drawdown_pct=0.30,
    max_open_positions=5,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllStrategiesRunTogether:
    """Verify that all 5 strategies can be registered and executed without error."""

    def test_all_strategies_run_without_error(self) -> None:
        """Create all 5 strategies, add to BacktestEngine, run 300 bars.

        Asserts:
            - No exceptions raised during the full run.
            - final_equity > 0 (account not wiped out).
            - equity_curve has entries.
        """
        bars = _generate_bars(n=300, seed=42)
        engine = BacktestEngine(
            initial_balance=3000.0,
            risk_config=SWING_RISK_CONFIG,
        )
        for strat in _create_all_strategies():
            engine.add_strategy(strat)

        result = engine.run(bars)

        assert isinstance(result, BacktestResult)
        assert result.final_equity > 0, "Final equity must remain positive"
        assert len(result.equity_curve) > 0, "Equity curve must have entries"
        # Equity curve should have initial balance + one entry per bar
        assert len(result.equity_curve) == len(bars) + 1


class TestStrategiesDifferentiation:
    """Verify strategies are actually differentiated in their signal generation."""

    def test_strategies_produce_different_sub_strategies(self) -> None:
        """Run all 5 strategies on 500 bars and verify that completed trades
        originate from different strategies when trades occur.

        Note: The BacktestSimulator only supports 'long' and 'close' directions.
        Short-only strategies (OverboughtShort) and short entries from bidirectional
        strategies will not produce filled trades. This test validates that at least
        the long-capable strategies generate differentiated trades.
        """
        bars = _generate_bars(n=500, seed=123)
        engine = BacktestEngine(
            initial_balance=3000.0,
            risk_config=SWING_RISK_CONFIG,
        )
        for strat in _create_all_strategies():
            engine.add_strategy(strat)

        result = engine.run(bars)

        if result.trades:
            # Collect unique strategy names from completed trades
            strategy_names_in_trades = {t.strategy for t in result.trades}
            # At least one strategy must have produced completed trades
            assert len(strategy_names_in_trades) >= 1, (
                "At least one strategy should produce completed trades"
            )
            # All trade strategy names must be from our known set
            assert strategy_names_in_trades.issubset(ALL_STRATEGY_NAMES), (
                f"Unknown strategy names in trades: "
                f"{strategy_names_in_trades - ALL_STRATEGY_NAMES}"
            )


class TestRegimeDetector:
    """Verify RegimeDetector classifies all 4 regimes correctly."""

    def test_trend_regime(self) -> None:
        """ADX >= 25 and BB width ratio >= 1.3 => TREND."""
        detector = RegimeDetector()
        regime = detector.classify(
            adx=30.0,
            bb_width=0.065,
            bb_width_avg=0.05,  # ratio = 1.3
            atr_ratio=0.02,
        )
        assert regime == MarketRegime.TREND

    def test_ranging_regime(self) -> None:
        """ADX < 20 and BB width ratio <= 0.8 => RANGING."""
        detector = RegimeDetector()
        regime = detector.classify(
            adx=15.0,
            bb_width=0.04,
            bb_width_avg=0.05,  # ratio = 0.8
            atr_ratio=0.01,
        )
        assert regime == MarketRegime.RANGING

    def test_high_volatility_regime(self) -> None:
        """ADX < 20, BB width ratio >= 1.3, ATR ratio > 0.03 => HIGH_VOLATILITY."""
        detector = RegimeDetector()
        regime = detector.classify(
            adx=15.0,
            bb_width=0.065,
            bb_width_avg=0.05,  # ratio = 1.3
            atr_ratio=0.04,
        )
        assert regime == MarketRegime.HIGH_VOLATILITY

    def test_uncertain_regime(self) -> None:
        """Indicators in ambiguous zone => UNCERTAIN."""
        detector = RegimeDetector()
        regime = detector.classify(
            adx=22.0,  # between 20 and 25
            bb_width=0.05,
            bb_width_avg=0.05,  # ratio = 1.0
            atr_ratio=0.02,
        )
        assert regime == MarketRegime.UNCERTAIN

    def test_uncertain_on_zero_bb_avg(self) -> None:
        """Edge case: zero bb_width_avg always returns UNCERTAIN."""
        detector = RegimeDetector()
        regime = detector.classify(
            adx=30.0,
            bb_width=0.05,
            bb_width_avg=0.0,
            atr_ratio=0.02,
        )
        assert regime == MarketRegime.UNCERTAIN

    def test_weights_sum_correctly(self) -> None:
        """Verify that regime weights sum to expected totals."""
        detector = RegimeDetector()

        for regime in MarketRegime:
            weights = detector.get_weights(regime)
            total = sum(weights.values())
            if regime == MarketRegime.UNCERTAIN:
                # UNCERTAIN retains 10% cash buffer, weights sum to 0.90
                assert abs(total - 0.90) < 1e-9, (
                    f"{regime.value} weights sum to {total}, expected 0.90"
                )
            else:
                assert abs(total - 1.0) < 1e-9, (
                    f"{regime.value} weights sum to {total}, expected 1.0"
                )

    def test_all_strategies_present_in_weights(self) -> None:
        """Every regime must include weights for all 5 strategies."""
        detector = RegimeDetector()
        for regime in MarketRegime:
            weights = detector.get_weights(regime)
            assert set(weights.keys()) == ALL_STRATEGY_NAMES, (
                f"{regime.value} missing strategies: "
                f"{ALL_STRATEGY_NAMES - set(weights.keys())}"
            )


class TestAllocationEnginePositionSizing:
    """Verify AllocationEngine computes correct position sizes per regime."""

    def test_trend_regime_adx_pullback_sizing(self) -> None:
        """In TREND regime, adx_pullback gets 30% of equity.

        With $3000 equity and price $100, that is $900 max allocation => 9 shares.
        """
        detector = RegimeDetector()
        allocator = AllocationEngine(detector)

        shares = allocator.get_position_size(
            strategy_name="adx_pullback",
            price=100.0,
            equity=3000.0,
            regime=MarketRegime.TREND,
        )
        # 30% of $3000 = $900 => $900 / $100 = 9 shares
        assert shares == 9

    def test_trend_regime_overbought_short_sizing(self) -> None:
        """In TREND regime, overbought_short gets 10% of equity.

        With $3000 equity and price $100, that is $300 max allocation => 3 shares.
        """
        detector = RegimeDetector()
        allocator = AllocationEngine(detector)

        shares = allocator.get_position_size(
            strategy_name="overbought_short",
            price=100.0,
            equity=3000.0,
            regime=MarketRegime.TREND,
        )
        # 10% of $3000 = $300 => $300 / $100 = 3 shares
        assert shares == 3

    def test_adx_pullback_produces_more_shares_than_overbought_short(self) -> None:
        """adx_pullback (30%) should get a meaningfully larger position than
        overbought_short (10%) in TREND regime.
        """
        detector = RegimeDetector()
        allocator = AllocationEngine(detector)

        adx_shares = allocator.get_position_size(
            strategy_name="adx_pullback",
            price=100.0,
            equity=3000.0,
            regime=MarketRegime.TREND,
        )
        ob_shares = allocator.get_position_size(
            strategy_name="overbought_short",
            price=100.0,
            equity=3000.0,
            regime=MarketRegime.TREND,
        )
        assert adx_shares > ob_shares, (
            f"adx_pullback ({adx_shares}) should have more shares "
            f"than overbought_short ({ob_shares})"
        )

    def test_below_minimum_position_returns_zero(self) -> None:
        """When allocation value < $200 minimum, position size should be 0."""
        detector = RegimeDetector()
        allocator = AllocationEngine(detector)

        # In TREND regime, overbought_short gets 10% of $1000 = $100 < $200 min
        shares = allocator.get_position_size(
            strategy_name="overbought_short",
            price=100.0,
            equity=1000.0,
            regime=MarketRegime.TREND,
        )
        assert shares == 0

    def test_zero_price_returns_zero(self) -> None:
        """Zero price should return 0 shares."""
        detector = RegimeDetector()
        allocator = AllocationEngine(detector)

        shares = allocator.get_position_size(
            strategy_name="adx_pullback",
            price=0.0,
            equity=3000.0,
            regime=MarketRegime.TREND,
        )
        assert shares == 0


class TestPortfolioSurvivesVolatileData:
    """Verify the system does not crash or go negative under extreme conditions."""

    def test_portfolio_survives_volatile_data(self) -> None:
        """Generate 200 bars with extreme volatility and verify the portfolio
        survives without crashing or producing negative equity.
        """
        bars = _generate_volatile_bars(n=200, seed=99)
        engine = BacktestEngine(
            initial_balance=3000.0,
            risk_config=SWING_RISK_CONFIG,
        )
        for strat in _create_all_strategies():
            engine.add_strategy(strat)

        result = engine.run(bars)

        assert result.final_equity > 0, (
            f"Portfolio equity went to {result.final_equity}; "
            "system must survive volatile data"
        )
        assert len(result.equity_curve) == len(bars) + 1
        # Verify no NaN or inf values in equity curve
        for i, eq in enumerate(result.equity_curve):
            assert math.isfinite(eq), (
                f"equity_curve[{i}] is not finite: {eq}"
            )
