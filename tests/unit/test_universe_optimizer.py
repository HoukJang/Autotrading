"""Task 6: Portfolio Optimizer Tests.

Tests for greedy portfolio selection with sector cap, min sectors,
regime diversity, rotation limit, and open position protection constraints.
"""
from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate, ScoredCandidate
from autotrader.universe.optimizer import PortfolioOptimizer


def _scored(
    symbol: str,
    sector: str,
    score: float,
    trend_pct: float = 0.40,
    range_pct: float = 0.40,
) -> ScoredCandidate:
    c = StockCandidate(
        symbol=symbol, sector=sector, close=100.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=trend_pct, range_pct=range_pct, vol_cycle=0.5,
    )
    return ScoredCandidate(
        candidate=c, proxy_score=score, backtest_score=score, final_score=score,
    )


class TestPortfolioOptimizer:
    def test_selects_top_n(self):
        opt = PortfolioOptimizer(target_size=3)
        candidates = [
            _scored("A", "Tech", 0.9),
            _scored("B", "Finance", 0.8),
            _scored("C", "Health", 0.7),
            _scored("D", "Energy", 0.6),
        ]
        result = opt.optimize(candidates)
        assert len(result) == 3
        assert result[0].candidate.symbol == "A"

    def test_sector_cap_enforced(self):
        opt = PortfolioOptimizer(target_size=5, max_per_sector=2)
        candidates = [
            _scored("A", "Tech", 0.95),
            _scored("B", "Tech", 0.90),
            _scored("C", "Tech", 0.85),
            _scored("D", "Finance", 0.80),
            _scored("E", "Health", 0.75),
            _scored("F", "Energy", 0.70),
        ]
        result = opt.optimize(candidates)
        tech_count = sum(1 for r in result if r.candidate.sector == "Tech")
        assert tech_count <= 2

    def test_min_sectors_enforced(self):
        opt = PortfolioOptimizer(target_size=5, min_sectors=3)
        candidates = [
            _scored("A", "Tech", 0.95),
            _scored("B", "Tech", 0.90),
            _scored("C", "Tech", 0.85),
            _scored("D", "Tech", 0.80),
            _scored("E", "Finance", 0.40),
            _scored("F", "Health", 0.35),
            _scored("G", "Energy", 0.30),
        ]
        result = opt.optimize(candidates)
        sectors = {r.candidate.sector for r in result}
        assert len(sectors) >= 3

    def test_regime_diversity_trend(self):
        opt = PortfolioOptimizer(
            target_size=6, min_trend_capable=3, min_range_capable=2,
        )
        candidates = [
            _scored("A", "Tech", 0.9, trend_pct=0.50, range_pct=0.10),
            _scored("B", "Fin", 0.85, trend_pct=0.50, range_pct=0.10),
            _scored("C", "Health", 0.80, trend_pct=0.50, range_pct=0.10),
            _scored("D", "Energy", 0.75, trend_pct=0.10, range_pct=0.60),
            _scored("E", "Util", 0.70, trend_pct=0.10, range_pct=0.60),
            _scored("F", "Mat", 0.65, trend_pct=0.10, range_pct=0.60),
        ]
        result = opt.optimize(candidates)
        trend = sum(1 for r in result if r.candidate.trend_pct > 0.30)
        rng = sum(1 for r in result if r.candidate.range_pct > 0.40)
        assert trend >= 3
        assert rng >= 2

    def test_max_rotation(self):
        opt = PortfolioOptimizer(target_size=5, max_rotation=2)
        candidates = [
            _scored("NEW1", "Tech", 0.95),
            _scored("NEW2", "Fin", 0.90),
            _scored("NEW3", "Health", 0.85),
            _scored("OLD1", "Energy", 0.60),
            _scored("OLD2", "Util", 0.55),
            _scored("OLD3", "Mat", 0.50),
        ]
        current_pool = ["OLD1", "OLD2", "OLD3"]
        result = opt.optimize(candidates, current_pool=current_pool)
        new_symbols = [
            r.candidate.symbol for r in result
            if r.candidate.symbol not in current_pool
        ]
        assert len(new_symbols) <= 2

    def test_open_positions_protected(self):
        opt = PortfolioOptimizer(target_size=3)
        candidates = [
            _scored("NEW1", "Tech", 0.95),
            _scored("NEW2", "Fin", 0.90),
            _scored("NEW3", "Health", 0.85),
            _scored("HELD", "Energy", 0.30),
        ]
        result = opt.optimize(candidates, open_positions=["HELD"])
        symbols = [r.candidate.symbol for r in result]
        assert "HELD" in symbols

    def test_empty_candidates(self):
        opt = PortfolioOptimizer(target_size=5)
        result = opt.optimize([])
        assert result == []

    def test_fewer_candidates_than_target(self):
        opt = PortfolioOptimizer(target_size=10)
        candidates = [_scored("A", "Tech", 0.9), _scored("B", "Fin", 0.8)]
        result = opt.optimize(candidates)
        assert len(result) == 2

    def test_only_open_positions(self):
        """When all candidates are open positions, all should be included."""
        opt = PortfolioOptimizer(target_size=3)
        candidates = [
            _scored("H1", "Tech", 0.5),
            _scored("H2", "Fin", 0.4),
        ]
        result = opt.optimize(candidates, open_positions=["H1", "H2"])
        symbols = [r.candidate.symbol for r in result]
        assert "H1" in symbols
        assert "H2" in symbols
        assert len(result) == 2
