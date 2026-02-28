"""Unit tests for GapFilter (autotrader/batch/gap_filter.py).

Tests cover:
- Filter out gaps > +3%
- Filter out gaps < -3%
- Keep gaps within +/-3%
- Keep candidates when pre-market data unavailable
- Negative gap (gap down) filtering
- Edge case: exactly 3% gap (at boundary)
- Empty candidate list
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from autotrader.batch.gap_filter import GapFilter
from autotrader.batch.types import Candidate, FilteredCandidate, ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scan_result(
    symbol: str = "AAPL",
    prev_close: float = 100.0,
) -> ScanResult:
    return ScanResult(
        symbol=symbol,
        strategy="rsi_mean_reversion",
        direction="long",
        signal_strength=0.80,
        indicators={},
        prev_close=prev_close,
        scanned_at=datetime.now(tz=timezone.utc),
    )


def _make_candidate(
    symbol: str = "AAPL",
    prev_close: float = 100.0,
) -> Candidate:
    sr = _make_scan_result(symbol=symbol, prev_close=prev_close)
    return Candidate(scan_result=sr, composite_score=0.80, regime_compatibility=0.80)


def _make_fetcher(quotes: dict[str, float]) -> MagicMock:
    """Create a mock BatchFetcher that returns the given quote dict."""
    fetcher = MagicMock()
    fetcher.fetch_latest_quotes = AsyncMock(return_value=quotes)
    return fetcher


# ---------------------------------------------------------------------------
# Test class: gap filtering logic
# ---------------------------------------------------------------------------

class TestGapFilterBehavior:
    """Core gap filter pass/fail logic."""

    @pytest.mark.asyncio
    async def test_gap_up_beyond_threshold_is_filtered(self):
        """Pre-market price > prev_close * 1.03 should be filtered out."""
        prev_close = 100.0
        pre_market = 104.0  # +4% gap -> filtered
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert len(result) == 1
        fc = result[0]
        assert fc.passed_filter is False
        assert fc.gap_pct is not None
        assert fc.gap_pct > 0.03

    @pytest.mark.asyncio
    async def test_gap_down_beyond_threshold_is_filtered(self):
        """Pre-market price < prev_close * 0.97 should be filtered out."""
        prev_close = 100.0
        pre_market = 96.0  # -4% gap -> filtered
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert len(result) == 1
        fc = result[0]
        assert fc.passed_filter is False
        assert fc.gap_pct is not None
        assert fc.gap_pct < -0.03

    @pytest.mark.asyncio
    async def test_gap_within_threshold_passes(self):
        """Pre-market price within +/-3% of prev_close should pass."""
        prev_close = 100.0
        pre_market = 102.0  # +2% gap -> within threshold
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert len(result) == 1
        fc = result[0]
        assert fc.passed_filter is True
        assert fc.gap_pct is not None
        assert abs(fc.gap_pct) <= 0.03

    @pytest.mark.asyncio
    async def test_no_gap_passes(self):
        """Pre-market price equal to prev_close (0% gap) should pass."""
        prev_close = 100.0
        fetcher = _make_fetcher({"AAPL": prev_close})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is True
        assert result[0].gap_pct == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_small_negative_gap_passes(self):
        """Small gap down (-1%) should be kept."""
        prev_close = 100.0
        pre_market = 99.0  # -1% gap
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is True


class TestGapFilterEdgeCases:
    """Boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_exactly_3_percent_gap_up_is_kept(self):
        """A gap of exactly +3.0% should NOT be filtered (> not >=)."""
        prev_close = 100.0
        pre_market = 103.0  # exactly +3.0%
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        # abs(gap) > threshold => filtered; exactly 3% is NOT > 3%, so passes
        assert result[0].passed_filter is True

    @pytest.mark.asyncio
    async def test_just_above_3_percent_gap_is_filtered(self):
        """A gap of +3.001% should be filtered."""
        prev_close = 100.0
        pre_market = 103.01  # just over 3%
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is False

    @pytest.mark.asyncio
    async def test_no_pre_market_data_candidate_kept(self):
        """When symbol is missing from quotes dict, candidate should be kept."""
        fetcher = _make_fetcher({})  # No data for AAPL
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", 100.0)]

        result = await gf.filter(candidates)

        assert len(result) == 1
        fc = result[0]
        assert fc.passed_filter is True
        assert fc.gap_pct is None
        assert fc.pre_market_price is None

    @pytest.mark.asyncio
    async def test_zero_price_treated_as_no_data(self):
        """A pre-market price of 0 should be treated as unavailable -> keep."""
        fetcher = _make_fetcher({"AAPL": 0.0})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", 100.0)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is True
        assert result[0].gap_pct is None

    @pytest.mark.asyncio
    async def test_empty_candidate_list_returns_empty(self):
        """filter([]) should return []."""
        fetcher = _make_fetcher({})
        gf = GapFilter(fetcher, gap_threshold=0.03)

        result = await gf.filter([])

        assert result == []

    @pytest.mark.asyncio
    async def test_fetcher_exception_keeps_all_candidates(self):
        """If fetcher raises an exception, all candidates should be kept."""
        fetcher = MagicMock()
        fetcher.fetch_latest_quotes = AsyncMock(side_effect=RuntimeError("network error"))
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [
            _make_candidate("AAPL", 100.0),
            _make_candidate("MSFT", 200.0),
        ]

        result = await gf.filter(candidates)

        assert len(result) == 2
        for fc in result:
            assert fc.passed_filter is True

    @pytest.mark.asyncio
    async def test_gap_pct_calculated_correctly(self):
        """Verify gap_pct = (pre_market - prev_close) / prev_close."""
        prev_close = 200.0
        pre_market = 210.0  # +5% gap
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        fc = result[0]
        expected_gap_pct = (pre_market - prev_close) / prev_close
        assert fc.gap_pct == pytest.approx(expected_gap_pct)
        assert fc.passed_filter is False

    @pytest.mark.asyncio
    async def test_multiple_candidates_mixed_results(self):
        """Some pass, some fail; results should reflect individual decisions."""
        fetcher = _make_fetcher({
            "AAPL": 104.0,   # +4% -> filtered
            "MSFT": 200.0,   # 0% -> pass
            "NVDA": 288.0,   # -4% -> filtered (prev_close=300)
        })
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [
            _make_candidate("AAPL", 100.0),
            _make_candidate("MSFT", 200.0),
            _make_candidate("NVDA", 300.0),
        ]

        result = await gf.filter(candidates)

        assert len(result) == 3
        result_map = {fc.symbol: fc for fc in result}
        assert result_map["AAPL"].passed_filter is False
        assert result_map["MSFT"].passed_filter is True
        assert result_map["NVDA"].passed_filter is False

    @pytest.mark.asyncio
    async def test_custom_gap_threshold_respected(self):
        """Custom threshold (e.g., 5%) should be used instead of default 3%."""
        prev_close = 100.0
        pre_market = 104.0  # +4% -> passes at 5% threshold, fails at 3%
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.05)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is True

    @pytest.mark.asyncio
    async def test_negative_gap_exactly_minus_3_pct_is_kept(self):
        """Gap of exactly -3.0% should NOT be filtered (> not >=)."""
        prev_close = 100.0
        pre_market = 97.0  # exactly -3.0%
        fetcher = _make_fetcher({"AAPL": pre_market})
        gf = GapFilter(fetcher, gap_threshold=0.03)
        candidates = [_make_candidate("AAPL", prev_close)]

        result = await gf.filter(candidates)

        assert result[0].passed_filter is True
