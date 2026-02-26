from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from autotrader.core.types import Bar
from autotrader.universe import StockInfo, StockCandidate, ScoredCandidate, UniverseResult
from autotrader.universe.selector import UniverseSelector


def _make_bar_series(
    symbol: str, n: int, start_price: float, seed: int = 42,
) -> list[Bar]:
    """Generate synthetic bar series with deterministic randomness."""
    random.seed(seed)
    bars: list[Bar] = []
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = start_price
    for i in range(n):
        change = random.gauss(0, 2)
        price = max(10.0, price + change)
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=i),
                open=price - 0.5,
                high=price + 1.5,
                low=price - 1.5,
                close=price,
                volume=1_500_000.0,
            )
        )
    return bars


class TestUniverseSelectorInit:
    def test_creates_with_defaults(self):
        sel = UniverseSelector()
        assert sel is not None
        assert sel._initial_balance == 3000.0
        assert sel._target_size == 15
        assert sel._proxy_weight == 0.50
        assert sel._backtest_weight == 0.50

    def test_creates_with_custom_params(self):
        sel = UniverseSelector(
            initial_balance=5000.0,
            target_size=10,
            proxy_weight=0.60,
            backtest_weight=0.40,
        )
        assert sel._initial_balance == 5000.0
        assert sel._target_size == 10
        assert sel._proxy_weight == 0.60
        assert sel._backtest_weight == 0.40


class TestBuildCandidates:
    def test_build_candidates_returns_stock_candidates(self):
        sel = UniverseSelector()
        bars_by_symbol = {
            "AAPL": _make_bar_series("AAPL", 100, 150.0),
        }
        infos = [StockInfo("AAPL", "Tech", "HW")]
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 1
        assert isinstance(result[0], StockCandidate)
        assert result[0].symbol == "AAPL"

    def test_build_candidates_skips_insufficient_data(self):
        sel = UniverseSelector()
        bars_by_symbol = {
            "AAPL": _make_bar_series("AAPL", 5, 150.0),  # too few bars
        }
        infos = [StockInfo("AAPL", "Tech", "HW")]
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 0

    def test_build_candidates_skips_missing_symbol(self):
        sel = UniverseSelector()
        bars_by_symbol = {}  # no bars at all
        infos = [StockInfo("AAPL", "Tech", "HW")]
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 0

    def test_build_candidates_multiple_symbols(self):
        sel = UniverseSelector()
        infos = [
            StockInfo("AAPL", "Tech", "HW"),
            StockInfo("MSFT", "Tech", "SW"),
            StockInfo("TINY", "Tech", "HW"),
        ]
        bars_by_symbol = {
            "AAPL": _make_bar_series("AAPL", 100, 150.0, seed=1),
            "MSFT": _make_bar_series("MSFT", 100, 200.0, seed=2),
            "TINY": _make_bar_series("TINY", 30, 50.0, seed=3),  # too few
        }
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 2
        symbols = {c.symbol for c in result}
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "TINY" not in symbols


class TestBarsToCandidate:
    def test_computes_basic_metrics(self):
        sel = UniverseSelector()
        info = StockInfo("TEST", "Tech", "HW")
        bars = _make_bar_series("TEST", 120, 100.0)
        candidate = sel._bars_to_candidate(info, bars)
        assert candidate is not None
        assert candidate.symbol == "TEST"
        assert candidate.sector == "Tech"
        assert candidate.close > 0.0
        assert candidate.avg_volume > 0.0
        assert candidate.avg_dollar_volume > 0.0
        assert candidate.atr_ratio >= 0.0
        assert 0.0 <= candidate.gap_frequency <= 1.0
        assert 0.0 <= candidate.trend_pct <= 1.0
        assert 0.0 <= candidate.range_pct <= 1.0
        assert candidate.vol_cycle >= 0.0

    def test_atr_ratio_is_positive(self):
        sel = UniverseSelector()
        info = StockInfo("TEST", "Tech", "HW")
        bars = _make_bar_series("TEST", 100, 100.0)
        candidate = sel._bars_to_candidate(info, bars)
        assert candidate is not None
        assert candidate.atr_ratio > 0.0


class TestRunBacktest:
    def test_compute_backtest_scores(self):
        sel = UniverseSelector()
        bars = _make_bar_series("AAPL", 150, 100.0)
        score = sel._run_backtest_for_symbol(bars)
        assert 0.0 <= score <= 1.0

    def test_backtest_with_shorter_data(self):
        sel = UniverseSelector()
        bars = _make_bar_series("TEST", 80, 100.0)
        score = sel._run_backtest_for_symbol(bars)
        assert 0.0 <= score <= 1.0


class TestScoreAndOptimize:
    def test_full_pipeline_returns_universe_result(self):
        sel = UniverseSelector(target_size=3)
        candidates = [
            StockCandidate("A", "Tech", 100.0, 100e6, 2e6, 0.02, 0.05, 0.40, 0.40, 0.5),
            StockCandidate("B", "Fin", 100.0, 80e6, 1.5e6, 0.025, 0.03, 0.35, 0.45, 0.4),
            StockCandidate("C", "Health", 100.0, 60e6, 1.2e6, 0.018, 0.08, 0.50, 0.20, 0.6),
            StockCandidate("D", "Energy", 100.0, 70e6, 1.8e6, 0.022, 0.04, 0.30, 0.50, 0.3),
        ]
        backtest_scores = {"A": 0.6, "B": 0.5, "C": 0.7, "D": 0.4}
        result = sel._score_and_optimize(candidates, backtest_scores, current_pool=[])
        assert isinstance(result, UniverseResult)
        assert len(result.symbols) == 3

    def test_score_and_optimize_combines_proxy_and_backtest(self):
        sel = UniverseSelector(target_size=2, proxy_weight=0.50, backtest_weight=0.50)
        candidates = [
            StockCandidate("A", "Tech", 100.0, 100e6, 2e6, 0.02, 0.05, 0.40, 0.40, 0.5),
            StockCandidate("B", "Fin", 100.0, 80e6, 1.5e6, 0.025, 0.03, 0.35, 0.45, 0.4),
        ]
        backtest_scores = {"A": 0.8, "B": 0.2}
        result = sel._score_and_optimize(candidates, backtest_scores, current_pool=[])
        assert isinstance(result, UniverseResult)
        # All scored candidates should have valid scores
        for sc in result.scored:
            assert 0.0 <= sc.final_score <= 1.0
            assert 0.0 <= sc.proxy_score <= 1.0
            assert 0.0 <= sc.backtest_score <= 1.0

    def test_rotation_tracking(self):
        sel = UniverseSelector(target_size=2)
        candidates = [
            StockCandidate("A", "Tech", 100.0, 100e6, 2e6, 0.02, 0.05, 0.40, 0.40, 0.5),
            StockCandidate("B", "Fin", 100.0, 80e6, 1.5e6, 0.025, 0.03, 0.35, 0.45, 0.4),
            StockCandidate("C", "Health", 100.0, 60e6, 1.2e6, 0.018, 0.08, 0.50, 0.20, 0.6),
        ]
        backtest_scores = {"A": 0.6, "B": 0.5, "C": 0.7}
        # Simulate existing pool
        result = sel._score_and_optimize(
            candidates, backtest_scores, current_pool=["A", "B", "X"],
        )
        # "X" was in current_pool but not in candidates, so it should be rotated out
        assert "X" in result.rotation_out

    def test_empty_candidates(self):
        sel = UniverseSelector(target_size=3)
        result = sel._score_and_optimize([], {}, current_pool=[])
        assert isinstance(result, UniverseResult)
        assert len(result.symbols) == 0


class TestSelectFullPipeline:
    def test_select_returns_universe_result(self):
        sel = UniverseSelector(target_size=3)
        infos = [
            StockInfo("A", "Tech", ""),
            StockInfo("B", "Fin", ""),
            StockInfo("C", "Health", ""),
        ]
        bars_by_symbol = {
            "A": _make_bar_series("A", 120, 100.0, seed=10),
            "B": _make_bar_series("B", 120, 100.0, seed=20),
            "C": _make_bar_series("C", 120, 100.0, seed=30),
        }
        result = sel.select(infos, bars_by_symbol)
        assert isinstance(result, UniverseResult)
        assert result.timestamp is not None

    def test_select_with_current_pool_and_open_positions(self):
        sel = UniverseSelector(target_size=3)
        infos = [
            StockInfo("A", "Tech", ""),
            StockInfo("B", "Fin", ""),
            StockInfo("C", "Health", ""),
            StockInfo("D", "Energy", ""),
        ]
        bars_by_symbol = {
            s: _make_bar_series(s, 120, 100.0, seed=i * 10)
            for i, s in enumerate(["A", "B", "C", "D"])
        }
        result = sel.select(
            infos, bars_by_symbol,
            current_pool=["A", "B"],
            open_positions=["A"],
        )
        assert isinstance(result, UniverseResult)
