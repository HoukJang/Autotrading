from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate
from autotrader.universe.scorer import ProxyScorer, BacktestScorer


def _make_candidate(**overrides) -> StockCandidate:
    defaults = dict(
        symbol="AAPL", sector="Technology", close=150.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
    )
    defaults.update(overrides)
    return StockCandidate(**defaults)


# ─────────────────────────────────────────────────────
# ProxyScorer Tests
# ─────────────────────────────────────────────────────

class TestProxyScorer:
    def test_score_returns_float_between_0_and_1(self):
        scorer = ProxyScorer()
        candidates = [_make_candidate()]
        scores = scorer.score(candidates, current_pool=[])
        assert 0.0 <= scores[0] <= 1.0

    def test_higher_liquidity_higher_score(self):
        scorer = ProxyScorer()
        low = _make_candidate(symbol="LOW", avg_dollar_volume=55e6)
        high = _make_candidate(symbol="HIGH", avg_dollar_volume=500e6)
        scores = scorer.score([low, high], current_pool=[])
        assert scores[1] > scores[0]

    def test_ideal_atr_ratio_scores_highest(self):
        scorer = ProxyScorer()
        ideal = _make_candidate(symbol="IDEAL", atr_ratio=0.02)
        high = _make_candidate(symbol="HIGH", atr_ratio=0.035)
        low = _make_candidate(symbol="LOW", atr_ratio=0.012)
        scores = scorer.score([ideal, high, low], current_pool=[])
        assert scores[0] >= scores[1]
        assert scores[0] >= scores[2]

    def test_low_gap_frequency_higher_score(self):
        scorer = ProxyScorer()
        safe = _make_candidate(symbol="SAFE", gap_frequency=0.02)
        risky = _make_candidate(symbol="RISKY", gap_frequency=0.12)
        scores = scorer.score([safe, risky], current_pool=[])
        assert scores[0] > scores[1]

    def test_incumbent_bonus(self):
        scorer = ProxyScorer()
        c = _make_candidate(symbol="AAPL")
        score_new = scorer.score([c], current_pool=[])[0]
        score_incumbent = scorer.score([c], current_pool=["AAPL"])[0]
        assert score_incumbent > score_new

    def test_strategy_coverage_dual_capable(self):
        scorer = ProxyScorer()
        dual = _make_candidate(symbol="DUAL", trend_pct=0.45, range_pct=0.45)
        trend_only = _make_candidate(symbol="TREND", trend_pct=0.60, range_pct=0.10)
        scores = scorer.score([dual, trend_only], current_pool=[])
        assert scores[0] > scores[1]

    def test_score_all_returns_correct_count(self):
        scorer = ProxyScorer()
        candidates = [_make_candidate(symbol=f"S{i}") for i in range(5)]
        scores = scorer.score(candidates, current_pool=[])
        assert len(scores) == 5

    def test_score_empty_candidates(self):
        scorer = ProxyScorer()
        scores = scorer.score([], current_pool=[])
        assert scores == []

    def test_single_candidate_liquidity_fallback(self):
        """Single candidate: dv_range is 0, liquidity should be 0.5."""
        scorer = ProxyScorer()
        c = _make_candidate(symbol="SOLO")
        scores = scorer.score([c], current_pool=[])
        assert len(scores) == 1
        assert 0.0 <= scores[0] <= 1.0

    def test_execution_quality_low_vol_cycle(self):
        """Low vol_cycle (consistent volume) should score higher."""
        scorer = ProxyScorer()
        consistent = _make_candidate(symbol="CONSISTENT", vol_cycle=0.1)
        inconsistent = _make_candidate(symbol="INCONSISTENT", vol_cycle=1.2)
        scores = scorer.score([consistent, inconsistent], current_pool=[])
        assert scores[0] > scores[1]

    def test_all_scores_are_non_negative(self):
        scorer = ProxyScorer()
        candidates = [
            _make_candidate(symbol="A", atr_ratio=0.04, gap_frequency=0.14, vol_cycle=1.4),
            _make_candidate(symbol="B", atr_ratio=0.01, gap_frequency=0.01, vol_cycle=0.1),
        ]
        scores = scorer.score(candidates, current_pool=[])
        for s in scores:
            assert s >= 0.0

    def test_weight_sum_is_approximately_0_90(self):
        """Weights sum to 0.90 (remaining 0.10 is LIQUIDITY factor normalization range)."""
        scorer = ProxyScorer()
        total_weight = (
            scorer.W_LIQUIDITY
            + scorer.W_VOL_QUALITY
            + scorer.W_STRATEGY_COVERAGE
            + scorer.W_GAP_SAFETY
            + scorer.W_EXECUTION_QUALITY
            + scorer.W_INCUMBENT
        )
        assert total_weight == pytest.approx(0.90)


# ─────────────────────────────────────────────────────
# BacktestScorer Tests
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

    def test_high_win_rate_high_score(self):
        scorer = BacktestScorer()
        high = scorer.score_from_metrics(10, 0.70, 2.0, 4)
        low = scorer.score_from_metrics(10, 0.35, 0.8, 4)
        assert high > low

    def test_more_strategies_active_higher_score(self):
        scorer = BacktestScorer()
        diverse = scorer.score_from_metrics(10, 0.55, 1.5, 5)
        narrow = scorer.score_from_metrics(10, 0.55, 1.5, 1)
        assert diverse > narrow

    def test_inf_profit_factor_capped_at_1(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(5, 0.60, float("inf"), 3)
        assert score <= 1.0

    def test_win_rate_clamped_to_0_1(self):
        """Win rate above 1.0 should be clamped."""
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(10, 1.5, 2.0, 3)
        score_normal = scorer.score_from_metrics(10, 1.0, 2.0, 3)
        assert score == score_normal

    def test_negative_win_rate_clamped_to_zero(self):
        """Win rate below 0.0 should be clamped."""
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(10, -0.5, 2.0, 3)
        score_zero = scorer.score_from_metrics(10, 0.0, 2.0, 3)
        assert score == score_zero

    def test_activity_capped_at_1(self):
        """More than 10 trades still gives activity = 1.0."""
        scorer = BacktestScorer()
        score_10 = scorer.score_from_metrics(10, 0.5, 1.5, 3)
        score_20 = scorer.score_from_metrics(20, 0.5, 1.5, 3)
        assert score_10 == score_20

    def test_score_deterministic(self):
        scorer = BacktestScorer()
        s1 = scorer.score_from_metrics(8, 0.6, 1.8, 4)
        s2 = scorer.score_from_metrics(8, 0.6, 1.8, 4)
        assert s1 == s2
