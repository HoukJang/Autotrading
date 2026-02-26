"""Integration tests for the full universe selection pipeline.

Uses synthetic data (no API calls needed) to verify end-to-end behavior
of the UniverseSelector orchestrator with all underlying components.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

import pytest

from autotrader.core.types import Bar
from autotrader.universe import StockInfo, StockCandidate, UniverseResult
from autotrader.universe.filters import HardFilter
from autotrader.universe.scorer import ProxyScorer, BacktestScorer
from autotrader.universe.optimizer import PortfolioOptimizer
from autotrader.universe.selector import UniverseSelector


def _make_bars(
    symbol: str,
    n: int = 120,
    base_price: float = 100.0,
    seed: int = 42,
    volume: float | None = None,
) -> list[Bar]:
    """Generate deterministic synthetic bar data.

    Produces bars that pass the default HardFilter thresholds:
    - ATR ratio in [0.01, 0.04]: using tight high/low spread (~1.5pt on 100)
    - Gap frequency < 0.15: open = prior close + tiny noise (no 2%+ gaps)
    - Price in [20, 200], volume >= 1M, dollar_volume >= 50M
    """
    random.seed(seed)
    bars: list[Bar] = []
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = base_price
    prev_close = base_price
    for i in range(n):
        change = random.gauss(0, 0.8)
        price = max(40.0, min(180.0, price + change))
        # Open near previous close to avoid gap triggers
        open_price = prev_close + random.gauss(0, 0.1)
        # Tight high/low spread for ATR ratio ~0.015-0.025
        spread = price * 0.012
        high_price = max(price, open_price) + abs(random.gauss(0, spread * 0.3))
        low_price = min(price, open_price) - abs(random.gauss(0, spread * 0.3))
        vol = volume if volume is not None else random.uniform(1.5e6, 4e6)
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=i),
                open=round(open_price, 2),
                high=round(high_price + spread * 0.5, 2),
                low=round(low_price - spread * 0.5, 2),
                close=round(price, 2),
                volume=vol,
            )
        )
        prev_close = price
    return bars


def _make_infos(n: int = 10) -> list[StockInfo]:
    """Generate N StockInfo objects across 5 sectors."""
    sectors = ["Tech", "Finance", "Health", "Energy", "Consumer"]
    return [
        StockInfo(
            symbol=f"S{i:02d}",
            sector=sectors[i % len(sectors)],
            sub_industry="",
        )
        for i in range(n)
    ]


class TestFullPipeline:
    """End-to-end tests for the universe selection pipeline."""

    def test_end_to_end_selection(self):
        """20 stocks -> select up to 8 -> verify UniverseResult."""
        infos = _make_infos(20)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0 + i * 5, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=8)
        result = selector.select(infos, bars_by_symbol)

        assert isinstance(result, UniverseResult)
        assert 1 <= len(result.symbols) <= 8
        assert result.timestamp is not None
        assert len(result.scored) == len(result.symbols)
        # All selected symbols should be from the input
        input_symbols = {info.symbol for info in infos}
        for sym in result.symbols:
            assert sym in input_symbols

    def test_rotation_tracks_changes(self):
        """Two sequential selections verify rotation_in/out tracking."""
        infos = _make_infos(15)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=5)

        # First selection: no existing pool
        r1 = selector.select(infos, bars_by_symbol)
        assert len(r1.rotation_in) > 0
        assert len(r1.rotation_out) == 0  # nothing to rotate out

        # Second selection with existing pool
        r2 = selector.select(infos, bars_by_symbol, current_pool=r1.symbols)
        # With identical data, rotation should be limited
        assert len(r2.rotation_in) <= 3  # max_rotation default = 3

    def test_hard_filter_reduces_candidates(self):
        """Stocks with low volume get filtered out by HardFilter."""
        infos = _make_infos(10)
        bars_by_symbol = {}
        for i, info in enumerate(infos):
            # First 5 have low volume -> filtered out
            vol = 500_000.0 if i < 5 else 2_000_000.0
            bars: list[Bar] = []
            base = datetime(2025, 1, 1, tzinfo=timezone.utc)
            for j in range(120):
                bars.append(
                    Bar(
                        symbol=info.symbol,
                        timestamp=base + timedelta(days=j),
                        open=99.0,
                        high=101.0,
                        low=98.0,
                        close=100.0,
                        volume=vol,
                    )
                )
            bars_by_symbol[info.symbol] = bars

        selector = UniverseSelector(target_size=5)
        result = selector.select(infos, bars_by_symbol)

        # Only high-volume stocks should pass hard filter
        assert len(result.symbols) <= 5
        # Low-volume symbols should not appear
        low_vol_symbols = {f"S{i:02d}" for i in range(5)}
        for sym in result.symbols:
            assert sym not in low_vol_symbols

    def test_backtest_scores_are_bounded(self):
        """Backtest score should always be in [0.0, 1.0]."""
        selector = UniverseSelector()
        bars = _make_bars("TEST", 150, 100.0)
        score = selector._run_backtest_for_symbol(bars)
        assert 0.0 <= score <= 1.0

    def test_open_positions_preserved(self):
        """Held stock must stay in the universe even with low score."""
        infos = _make_infos(10)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=5)

        # First selection to get a valid pool
        r1 = selector.select(infos, bars_by_symbol)
        assert len(r1.symbols) > 0

        # Pretend we have an open position in the first symbol
        held = r1.symbols[0]
        r2 = selector.select(
            infos,
            bars_by_symbol,
            current_pool=r1.symbols,
            open_positions=[held],
        )
        assert held in r2.symbols


class TestPipelineComponents:
    """Verify individual pipeline stages work together correctly."""

    def test_candidate_metrics_are_valid(self):
        """All computed metrics should have valid ranges."""
        selector = UniverseSelector()
        infos = _make_infos(5)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0, seed=i)
            for i, info in enumerate(infos)
        }
        candidates = selector._build_candidates(infos, bars_by_symbol)
        for c in candidates:
            assert c.close > 0.0
            assert c.avg_volume > 0.0
            assert c.avg_dollar_volume > 0.0
            assert c.atr_ratio >= 0.0
            assert 0.0 <= c.gap_frequency <= 1.0
            assert 0.0 <= c.trend_pct <= 1.0
            assert 0.0 <= c.range_pct <= 1.0
            assert c.vol_cycle >= 0.0

    def test_scored_candidates_have_valid_scores(self):
        """Hybrid scores should be bounded and consistent."""
        selector = UniverseSelector(target_size=5)
        candidates = [
            StockCandidate(
                f"S{i}", "Tech", 100.0, 100e6, 2e6,
                0.02, 0.05, 0.40, 0.40, 0.5,
            )
            for i in range(5)
        ]
        backtest_scores = {f"S{i}": 0.5 for i in range(5)}
        result = selector._score_and_optimize(
            candidates, backtest_scores, current_pool=[],
        )
        for sc in result.scored:
            assert 0.0 <= sc.proxy_score <= 1.0
            assert 0.0 <= sc.backtest_score <= 1.0
            assert 0.0 <= sc.final_score <= 1.0

    def test_empty_bars_produces_empty_result(self):
        """No bar data should produce empty result gracefully."""
        selector = UniverseSelector(target_size=5)
        infos = _make_infos(5)
        result = selector.select(infos, {})
        assert isinstance(result, UniverseResult)
        assert len(result.symbols) == 0
