from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate
from autotrader.universe.filters import HardFilter


def _make_candidate(**overrides) -> StockCandidate:
    defaults = dict(
        symbol="AAPL", sector="Technology", close=150.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
    )
    defaults.update(overrides)
    return StockCandidate(**defaults)


class TestHardFilter:
    def test_passes_good_candidate(self):
        f = HardFilter()
        c = _make_candidate()
        assert f.passes(c) is True

    def test_rejects_low_dollar_volume(self):
        f = HardFilter()
        c = _make_candidate(avg_dollar_volume=10e6)
        assert f.passes(c) is False

    def test_rejects_low_volume(self):
        f = HardFilter()
        c = _make_candidate(avg_volume=500_000)
        assert f.passes(c) is False

    def test_rejects_price_too_low(self):
        f = HardFilter()
        c = _make_candidate(close=15.0)
        assert f.passes(c) is False

    def test_rejects_price_too_high(self):
        f = HardFilter()
        c = _make_candidate(close=250.0)
        assert f.passes(c) is False

    def test_rejects_atr_ratio_too_low(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.005)
        assert f.passes(c) is False

    def test_rejects_atr_ratio_too_high(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.05)
        assert f.passes(c) is False

    def test_rejects_high_gap_frequency(self):
        f = HardFilter()
        c = _make_candidate(gap_frequency=0.20)
        assert f.passes(c) is False

    def test_filter_list(self):
        f = HardFilter()
        candidates = [
            _make_candidate(symbol="AAPL"),
            _make_candidate(symbol="BAD", avg_dollar_volume=1e6),
            _make_candidate(symbol="MSFT"),
        ]
        result = f.filter(candidates)
        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[1].symbol == "MSFT"

    def test_custom_thresholds(self):
        f = HardFilter(
            min_dollar_volume=10e6,
            min_volume=100_000,
            min_price=5.0,
            max_price=500.0,
            min_atr_ratio=0.005,
            max_atr_ratio=0.08,
            max_gap_frequency=0.25,
        )
        c = _make_candidate(close=300.0, avg_volume=200_000, avg_dollar_volume=20e6)
        assert f.passes(c) is True

    def test_boundary_min_dollar_volume_passes(self):
        """Exact boundary value should pass."""
        f = HardFilter()
        c = _make_candidate(avg_dollar_volume=50e6)
        assert f.passes(c) is True

    def test_boundary_min_dollar_volume_fails(self):
        """Just below boundary should fail."""
        f = HardFilter()
        c = _make_candidate(avg_dollar_volume=49_999_999.99)
        assert f.passes(c) is False

    def test_boundary_min_price_passes(self):
        f = HardFilter()
        c = _make_candidate(close=20.0)
        assert f.passes(c) is True

    def test_boundary_max_price_passes(self):
        f = HardFilter()
        c = _make_candidate(close=200.0)
        assert f.passes(c) is True

    def test_boundary_min_atr_ratio_passes(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.01)
        assert f.passes(c) is True

    def test_boundary_max_atr_ratio_passes(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.04)
        assert f.passes(c) is True

    def test_boundary_max_gap_frequency_passes(self):
        f = HardFilter()
        c = _make_candidate(gap_frequency=0.15)
        assert f.passes(c) is True

    def test_filter_empty_list(self):
        f = HardFilter()
        assert f.filter([]) == []

    def test_filter_all_rejected(self):
        f = HardFilter()
        candidates = [
            _make_candidate(symbol="A", avg_dollar_volume=1e6),
            _make_candidate(symbol="B", close=5.0),
        ]
        assert f.filter(candidates) == []
