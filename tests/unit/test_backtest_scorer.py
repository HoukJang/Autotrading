"""Task 5: Backtest Scorer Integration Tests.

Unit tests for BacktestScorer scoring logic plus integration test
that runs BacktestEngine with all 5 strategies on synthetic bars
and feeds the result into BacktestScorer.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

import pytest

from autotrader.universe.scorer import BacktestScorer
from autotrader.backtest.engine import BacktestEngine, BacktestResult
from autotrader.core.config import RiskConfig
from autotrader.core.types import Bar
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum


# ─────────────────────────────────────────────────────
# Unit tests for BacktestScorer
# ─────────────────────────────────────────────────────

class TestBacktestScorer:
    def test_zero_trades_returns_zero(self):
        scorer = BacktestScorer()
        assert scorer.score_from_metrics(0, 0.0, 0.0, 0) == 0.0

    def test_perfect_score(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=15, win_rate=1.0, profit_factor=5.0, strategies_active=5,
        )
        assert score == pytest.approx(1.0)

    def test_moderate_performance(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=5, win_rate=0.55, profit_factor=1.5, strategies_active=3,
        )
        assert 0.3 < score < 0.7

    def test_high_win_rate_higher_score(self):
        scorer = BacktestScorer()
        high = scorer.score_from_metrics(10, 0.70, 2.0, 4)
        low = scorer.score_from_metrics(10, 0.35, 0.8, 4)
        assert high > low

    def test_more_strategies_active_higher_score(self):
        scorer = BacktestScorer()
        diverse = scorer.score_from_metrics(10, 0.55, 1.5, 5)
        narrow = scorer.score_from_metrics(10, 0.55, 1.5, 1)
        assert diverse > narrow

    def test_inf_profit_factor_capped(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(5, 0.60, float("inf"), 3)
        assert score <= 1.0


# ─────────────────────────────────────────────────────
# Integration: BacktestEngine + BacktestScorer
# ─────────────────────────────────────────────────────

class TestBacktestScorerWithEngine:
    """Integration test: run BacktestEngine with all 5 strategies and feed results to BacktestScorer."""

    @staticmethod
    def _make_bars(symbol: str, n: int = 100) -> list[Bar]:
        """Generate synthetic price bars with seeded randomness for reproducibility."""
        bars: list[Bar] = []
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        price = 100.0
        for i in range(n):
            random.seed(i + hash(symbol) % 10000)
            change = random.gauss(0, 2)
            price = max(10.0, price + change)
            bars.append(Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=i),
                open=price - 0.5,
                high=price + 1.5,
                low=price - 1.5,
                close=price,
                volume=1_000_000.0,
            ))
        return bars

    def test_engine_result_feeds_scorer(self):
        """Run BacktestEngine with all 5 strategies on synthetic data, then score the result."""
        risk = RiskConfig(
            max_position_pct=0.30,
            max_drawdown_pct=0.30,
            max_open_positions=5,
        )
        engine = BacktestEngine(3000.0, risk)
        strategies = [
            RsiMeanReversion(),
            BbSqueezeBreakout(),
            AdxPullback(),
            OverboughtShort(),
            RegimeMomentum(),
        ]
        for s in strategies:
            engine.add_strategy(s)

        bars = self._make_bars("AAPL", 120)
        result = engine.run(bars)

        # Verify the engine produced a valid result
        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0

        # Extract unique strategy names from trades
        strategy_names = {t.strategy for t in result.trades}

        # Feed into BacktestScorer
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=result.total_trades,
            win_rate=result.metrics.get("win_rate", 0.0),
            profit_factor=result.metrics.get("profit_factor", 0.0),
            strategies_active=len(strategy_names),
        )

        # Score must be a valid float in [0.0, 1.0]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
