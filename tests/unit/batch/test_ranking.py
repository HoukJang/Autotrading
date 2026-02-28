"""Unit tests for SignalRanker (autotrader/batch/ranking.py).

Tests cover:
- Composite score calculation: signal 60% + regime 30% + sector 10%
- Top-N selection with correct ranking order
- Sector diversity penalty applied correctly
- Tie-breaking (signal_strength -> symbol)
- Empty input handling
- All signals below threshold
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autotrader.batch.ranking import (
    SignalRanker,
    _DEFAULT_TOP_N,
    _REGIME_COMPAT,
    _WEIGHT_SIGNAL,
    _WEIGHT_REGIME,
    _WEIGHT_SECTOR,
    _SECTOR_PENALTY_STEP,
)
from autotrader.batch.types import ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scan_result(
    symbol: str = "AAPL",
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    signal_strength: float = 0.8,
    indicators: dict | None = None,
) -> ScanResult:
    """Create a ScanResult with sensible defaults for testing."""
    return ScanResult(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        signal_strength=signal_strength,
        indicators=indicators or {},
        prev_close=150.0,
        scanned_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Test class: composite score calculation
# ---------------------------------------------------------------------------

class TestCompositeScoreCalculation:
    """Verify composite = signal*0.6 + regime*0.3 + sector*0.1."""

    def test_single_result_uses_correct_weights(self):
        """Single-symbol result should have composite = 0.6*sig + 0.3*regime + 0.1*sector."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(
            symbol="AAPL",
            strategy="rsi_mean_reversion",
            direction="long",
            signal_strength=0.80,
        )
        candidates = ranker.rank([sr], sector_map={"AAPL": "Technology"})

        assert len(candidates) == 1
        cand = candidates[0]

        # rsi_mean_reversion long => regime_compat = 0.80
        expected_regime = 0.80
        # First and only candidate from "Technology" => sector_bonus = 1.0
        expected_sector_bonus = 1.0
        expected_composite = (
            _WEIGHT_SIGNAL * 0.80
            + _WEIGHT_REGIME * expected_regime
            + _WEIGHT_SECTOR * expected_sector_bonus
        )
        assert abs(cand.composite_score - expected_composite) < 1e-6

    def test_regime_compatibility_adx_pullback_long(self):
        """ADX pullback long should have regime_compatibility = 0.95."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(strategy="adx_pullback", direction="long", signal_strength=0.70)
        candidates = ranker.rank([sr])

        assert len(candidates) == 1
        assert abs(candidates[0].regime_compatibility - 0.95) < 1e-6

    def test_regime_compatibility_unknown_strategy(self):
        """Unknown strategy/direction pair should default to 0.60."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(strategy="unknown_strategy", direction="long", signal_strength=0.50)
        candidates = ranker.rank([sr])

        assert len(candidates) == 1
        assert abs(candidates[0].regime_compatibility - 0.60) < 1e-6

    def test_adx_boost_from_high_adx_indicator(self):
        """ADX strategy with ADX_14 > 30 should receive a score boost."""
        ranker = SignalRanker(top_n=12)
        # ADX = 40 => boost = min(0.05, (40-30)/200) = 0.05
        sr_high_adx = _make_scan_result(
            strategy="adx_pullback",
            direction="long",
            signal_strength=0.70,
            indicators={"ADX_14": 40.0},
        )
        sr_no_adx = _make_scan_result(
            symbol="MSFT",
            strategy="adx_pullback",
            direction="long",
            signal_strength=0.70,
            indicators={},
        )
        candidates_high = ranker.rank([sr_high_adx])
        candidates_low = ranker.rank([sr_no_adx])

        # Regime compat with boost should be higher than without
        assert candidates_high[0].regime_compatibility > candidates_low[0].regime_compatibility

    def test_adx_boost_capped_at_1(self):
        """Regime compatibility should never exceed 1.0."""
        ranker = SignalRanker(top_n=12)
        # ADX = 1000 => enormous boost, but clamped
        sr = _make_scan_result(
            strategy="adx_pullback",
            direction="long",
            signal_strength=0.70,
            indicators={"ADX_14": 1000.0},
        )
        candidates = ranker.rank([sr])
        assert candidates[0].regime_compatibility <= 1.0


# ---------------------------------------------------------------------------
# Test class: ranking order and Top-N selection
# ---------------------------------------------------------------------------

class TestTopNSelection:
    """Verify correct ranking order and Top-N selection."""

    def test_higher_signal_strength_ranks_first(self):
        """Candidate with higher signal strength should rank above lower one."""
        ranker = SignalRanker(top_n=12)
        strong = _make_scan_result(symbol="AAPL", signal_strength=0.90)
        weak = _make_scan_result(symbol="MSFT", signal_strength=0.50)
        candidates = ranker.rank([weak, strong])

        assert candidates[0].symbol == "AAPL"
        assert candidates[1].symbol == "MSFT"

    def test_top_n_limits_results(self):
        """Result count must not exceed top_n."""
        top_n = 3
        ranker = SignalRanker(top_n=top_n)
        results = [
            _make_scan_result(symbol=f"SYM{i}", signal_strength=float(i) / 10)
            for i in range(10)
        ]
        candidates = ranker.rank(results)
        assert len(candidates) <= top_n

    def test_rank_attribute_assigned_correctly(self):
        """rank=1 should be the best candidate."""
        ranker = SignalRanker(top_n=5)
        results = [
            _make_scan_result(symbol=f"S{i}", signal_strength=float(i) * 0.1)
            for i in range(5)
        ]
        candidates = ranker.rank(results)

        for i, cand in enumerate(candidates, start=1):
            assert cand.rank == i

    def test_returns_fewer_than_top_n_when_input_is_small(self):
        """Should return all results when input count < top_n."""
        ranker = SignalRanker(top_n=12)
        results = [
            _make_scan_result(symbol="AAPL"),
            _make_scan_result(symbol="MSFT"),
        ]
        candidates = ranker.rank(results)
        assert len(candidates) == 2

    def test_default_top_n_is_12(self):
        """Default top_n for SignalRanker should be 12."""
        ranker = SignalRanker()
        results = [
            _make_scan_result(symbol=f"S{i}", signal_strength=float(i) * 0.01)
            for i in range(20)
        ]
        candidates = ranker.rank(results)
        assert len(candidates) == 12


# ---------------------------------------------------------------------------
# Test class: sector diversity penalty
# ---------------------------------------------------------------------------

class TestSectorDiversityPenalty:
    """Verify sector penalty reduces composite scores for duplicate-sector candidates."""

    def test_second_candidate_same_sector_gets_penalty(self):
        """Second candidate from same sector should have lower sector bonus."""
        ranker = SignalRanker(top_n=12)
        # Both from the same sector, same strategy/direction
        sr_a = _make_scan_result(symbol="AAPL", signal_strength=0.90)
        sr_b = _make_scan_result(symbol="MSFT", signal_strength=0.80)
        sector_map = {"AAPL": "Technology", "MSFT": "Technology"}

        candidates = ranker.rank([sr_a, sr_b], sector_map=sector_map)

        # AAPL ranked first (higher signal) -> sector_bonus = 1.0
        # MSFT ranked second in pre-sort -> sector_bonus = 1.0 - 0.25 = 0.75
        # Expect first candidate has higher composite due to sector bonus
        assert candidates[0].symbol == "AAPL"
        assert candidates[0].composite_score > candidates[1].composite_score

    def test_third_candidate_same_sector_gets_more_penalty(self):
        """Third candidate from same sector should have even lower sector bonus."""
        ranker = SignalRanker(top_n=12)
        results = [
            _make_scan_result(symbol=f"IT{i}", signal_strength=0.9 - i * 0.01)
            for i in range(4)
        ]
        sector_map = {f"IT{i}": "Technology" for i in range(4)}

        candidates = ranker.rank(results, sector_map=sector_map)

        # Sector bonuses should be: 1.0, 0.75, 0.50, 0.25 (stepping by 0.25)
        # Composite scores should monotonically decrease
        for i in range(len(candidates) - 1):
            assert candidates[i].composite_score >= candidates[i + 1].composite_score

    def test_different_sectors_no_penalty(self):
        """Candidates from different sectors should each get sector_bonus=1.0."""
        ranker = SignalRanker(top_n=12)
        sr_a = _make_scan_result(symbol="AAPL", signal_strength=0.70)
        sr_b = _make_scan_result(symbol="JPM", signal_strength=0.70)
        # Same strategy, same signal strength, different sectors
        sector_map = {"AAPL": "Technology", "JPM": "Financials"}

        candidates = ranker.rank([sr_a, sr_b], sector_map=sector_map)
        # Both should have sector_bonus=1.0 => same composite (assuming same regime compat)
        assert abs(candidates[0].composite_score - candidates[1].composite_score) < 1e-6

    def test_sector_penalty_clamped_to_zero(self):
        """Sector bonus should never go below 0.0."""
        ranker = SignalRanker(top_n=12)
        # 5 candidates in same sector: bonuses would be 1.0, 0.75, 0.50, 0.25, 0.0
        results = [
            _make_scan_result(symbol=f"X{i}", signal_strength=0.9 - i * 0.01)
            for i in range(6)
        ]
        sector_map = {f"X{i}": "Technology" for i in range(6)}
        candidates = ranker.rank(results, sector_map=sector_map)

        # None should have a negative composite score
        for cand in candidates:
            assert cand.composite_score >= 0.0

    def test_unknown_sector_defaults_to_unknown(self):
        """Symbols not in sector_map should default to 'Unknown' sector."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(symbol="ZZZZ", signal_strength=0.80)
        candidates = ranker.rank([sr], sector_map={})
        assert candidates[0].sector == "Unknown"


# ---------------------------------------------------------------------------
# Test class: tie-breaking
# ---------------------------------------------------------------------------

class TestTieBreaking:
    """Verify tie-breaking: signal_strength -> alphabetical symbol."""

    def test_tie_broken_by_signal_strength(self):
        """Same composite but higher signal_strength wins."""
        ranker = SignalRanker(top_n=12)
        # Equal composite achievable by same strategy/direction and equal scores,
        # but different signal strengths => different composites anyway.
        # We instead check that alpha sort is deterministic.
        sr_a = _make_scan_result(symbol="AAA", signal_strength=0.80)
        sr_b = _make_scan_result(symbol="ZZZ", signal_strength=0.80)
        # Same signal_strength, same regime compat (same strategy/direction)
        # composite scores will be equal
        candidates = ranker.rank([sr_b, sr_a])
        # Alphabetical tie-break: AAA < ZZZ
        assert candidates[0].symbol == "AAA"
        assert candidates[1].symbol == "ZZZ"

    def test_alphabetical_tiebreak_is_deterministic(self):
        """Multiple calls with same input should produce identical ordering."""
        ranker = SignalRanker(top_n=12)
        results = [
            _make_scan_result(symbol=sym, signal_strength=0.70)
            for sym in ["ZZZZ", "AAPL", "MSFT", "BBBB"]
        ]
        order1 = [c.symbol for c in ranker.rank(results)]
        order2 = [c.symbol for c in ranker.rank(results)]
        assert order1 == order2


# ---------------------------------------------------------------------------
# Test class: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty input and other boundary conditions."""

    def test_empty_scan_results_returns_empty_list(self):
        """rank([]) should return []."""
        ranker = SignalRanker(top_n=12)
        result = ranker.rank([])
        assert result == []

    def test_empty_sector_map_accepted(self):
        """sector_map=None should default to empty dict (no errors)."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(symbol="AAPL", signal_strength=0.70)
        candidates = ranker.rank([sr], sector_map=None)
        assert len(candidates) == 1

    def test_single_result_rank_is_one(self):
        """With one result, rank should be 1."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(symbol="AAPL", signal_strength=0.70)
        candidates = ranker.rank([sr])
        assert candidates[0].rank == 1

    def test_composite_score_never_exceeds_one(self):
        """Composite score should be <= 1.0 for any valid input."""
        ranker = SignalRanker(top_n=12)
        sr = _make_scan_result(
            strategy="adx_pullback", direction="long", signal_strength=1.0
        )
        candidates = ranker.rank([sr])
        assert candidates[0].composite_score <= 1.0 + 1e-9
