"""Integration tests for the Batch-to-Entry pipeline.

Tests the complete flow:
  Scanner produces BatchResult -> Ranker selects top 12
  -> GapFilter filters -> EntryManager executes

All Alpaca API calls are mocked. Real ranking and gap filter
logic is exercised.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.batch.gap_filter import GapFilter
from autotrader.batch.ranking import SignalRanker
from autotrader.batch.types import BatchResult, Candidate, ScanResult
from autotrader.core.types import AccountInfo, OrderResult, Signal
from autotrader.execution.entry_manager import Candidate as EntryCandiate
from autotrader.execution.entry_manager import EntryManager
from autotrader.execution.exit_rules import ExitRuleEngine
from autotrader.portfolio.regime_detector import MarketRegime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRADE_DATE = date(2026, 2, 24)


def _make_scan_result(
    symbol: str,
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    signal_strength: float = 0.80,
    prev_close: float = 100.0,
) -> ScanResult:
    return ScanResult(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        signal_strength=signal_strength,
        indicators={"ATR_14": 2.0, "RSI_14": 45.0},
        prev_close=prev_close,
        scanned_at=datetime.now(tz=timezone.utc),
    )


def _make_account(equity: float = 20_000.0, cash: float = 20_000.0) -> AccountInfo:
    return AccountInfo(
        account_id="test-integration",
        buying_power=cash,
        portfolio_value=equity,
        cash=cash,
        equity=equity,
    )


def _make_entry_manager(fill_price: float = 100.0) -> EntryManager:
    """Create EntryManager with mocked dependencies."""
    fill_result = OrderResult(
        order_id="fill-001",
        symbol="ANY",
        status="filled",
        filled_qty=10.0,
        filled_price=fill_price,
    )

    order_manager = MagicMock()
    order_manager.submit_entry = AsyncMock(return_value=fill_result)
    order_manager.submit_stop_loss = AsyncMock(return_value=None)

    allocation_engine = MagicMock()
    allocation_engine.should_enter = MagicMock(return_value=True)
    allocation_engine.get_position_size = MagicMock(return_value=10)

    risk_manager = MagicMock()
    risk_manager.validate = MagicMock(return_value=True)

    exit_rule_engine = MagicMock(spec=ExitRuleEngine)
    exit_rule_engine.is_reentry_blocked = MagicMock(return_value=False)

    return EntryManager(
        order_manager=order_manager,
        allocation_engine=allocation_engine,
        risk_manager=risk_manager,
        exit_rule_engine=exit_rule_engine,
    )


# ---------------------------------------------------------------------------
# Test class: Scanner -> Ranker -> GapFilter pipeline
# ---------------------------------------------------------------------------

class TestScannerToGapFilter:
    """Tests for the batch scan and filter pipeline."""

    def test_ranker_selects_top_12_from_scan_results(self):
        """SignalRanker should return at most 12 candidates from scan results."""
        ranker = SignalRanker(top_n=12)
        scan_results = [
            _make_scan_result(f"SYM{i:02d}", signal_strength=0.9 - i * 0.01)
            for i in range(20)  # 20 input, should get 12 out
        ]

        candidates = ranker.rank(scan_results)

        assert len(candidates) <= 12
        assert all(c.rank <= 12 for c in candidates)

    def test_ranker_ranks_by_composite_score_descending(self):
        """Candidates should be ordered best-first by composite score."""
        ranker = SignalRanker(top_n=12)
        scan_results = [
            _make_scan_result("WEAK", signal_strength=0.30),
            _make_scan_result("STRONG", signal_strength=0.90),
            _make_scan_result("MID", signal_strength=0.60),
        ]

        candidates = ranker.rank(scan_results)

        scores = [c.composite_score for c in candidates]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_gap_filter_removes_gapped_candidates(self):
        """GapFilter should remove candidates with >3% gap."""
        ranker = SignalRanker(top_n=12)
        scan_results = [
            _make_scan_result("GAPPED_UP", prev_close=100.0, signal_strength=0.90),
            _make_scan_result("NORMAL", prev_close=100.0, signal_strength=0.80),
        ]
        candidates = ranker.rank(scan_results)

        # GAPPED_UP has +4% pre-market move
        quotes = {"GAPPED_UP": 104.0, "NORMAL": 100.5}

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_latest_quotes = AsyncMock(return_value=quotes)
        gap_filter = GapFilter(mock_fetcher, gap_threshold=0.03)

        filtered = await gap_filter.filter(candidates)

        gapped_results = [fc for fc in filtered if fc.symbol == "GAPPED_UP"]
        normal_results = [fc for fc in filtered if fc.symbol == "NORMAL"]
        assert len(gapped_results) == 1
        assert gapped_results[0].passed_filter is False
        assert normal_results[0].passed_filter is True

    @pytest.mark.asyncio
    async def test_gap_filter_keeps_all_when_no_quotes(self):
        """When fetcher returns no data, all candidates should pass filter."""
        ranker = SignalRanker(top_n=12)
        scan_results = [
            _make_scan_result(f"SYM{i}", signal_strength=0.9 - i * 0.05)
            for i in range(5)
        ]
        candidates = ranker.rank(scan_results)

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_latest_quotes = AsyncMock(return_value={})
        gap_filter = GapFilter(mock_fetcher, gap_threshold=0.03)

        filtered = await gap_filter.filter(candidates)

        assert len(filtered) == 5
        assert all(fc.passed_filter for fc in filtered)

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_entry_candidates(self):
        """End-to-end: scan results -> rank -> gap filter -> entry candidates."""
        # Step 1: Create scan results (as NightlyScanner would)
        scan_results = [
            _make_scan_result(f"SYM{i:02d}", signal_strength=0.9 - i * 0.03)
            for i in range(15)
        ]

        # Step 2: Rank
        ranker = SignalRanker(top_n=12)
        candidates = ranker.rank(scan_results)
        assert len(candidates) <= 12

        # Step 3: Gap filter (no gaps)
        symbols = [c.symbol for c in candidates]
        quotes = {sym: 100.0 for sym in symbols}  # all at prev_close, no gap
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_latest_quotes = AsyncMock(return_value=quotes)
        gap_filter = GapFilter(mock_fetcher, gap_threshold=0.03)

        filtered = await gap_filter.filter(candidates)
        passing = [fc for fc in filtered if fc.passed_filter]

        # All should pass since no gaps
        assert len(passing) == len(candidates)

        # Step 4: Convert to EntryManager candidates
        entry_candidates = [
            EntryCandiate(
                signal=Signal(
                    strategy=fc.candidate.strategy,
                    symbol=fc.symbol,
                    direction=fc.candidate.direction,
                    strength=fc.candidate.signal_strength,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=fc.candidate.prev_close,
                atr=2.0,
                indicators=fc.candidate.scan_result.indicators,
            )
            for fc in passing
        ]

        assert len(entry_candidates) > 0
        assert all(isinstance(c, EntryCandiate) for c in entry_candidates)


# ---------------------------------------------------------------------------
# Test class: EntryManager execution from BatchResult
# ---------------------------------------------------------------------------

class TestEntryManagerFromBatch:
    """Tests that EntryManager correctly processes batch candidates."""

    @pytest.mark.asyncio
    async def test_group_a_candidates_executed_at_moo(self):
        """Group A candidates from batch should be executed via execute_moo."""
        em = _make_entry_manager(fill_price=100.5)

        entry_candidates = [
            EntryCandiate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol="AAPL",
                    direction="long",
                    strength=0.85,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=100.0,
                atr=2.0,
                indicators={},
            ),
            EntryCandiate(
                signal=Signal(
                    strategy="overbought_short",
                    symbol="MSFT",
                    direction="short",
                    strength=0.75,
                    metadata={"entry_atr": 3.0},
                ),
                prev_close=200.0,
                atr=3.0,
                indicators={},
            ),
        ]

        em.load_candidates(entry_candidates)
        assert len(em._group_a) == 2
        assert len(em._group_b) == 0

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        # Both Group A candidates should have been submitted
        assert em._order_manager.submit_entry.call_count == 2

    @pytest.mark.asyncio
    async def test_group_b_candidates_pass_confirmation(self):
        """Group B candidates that confirm should be entered."""
        em = _make_entry_manager(fill_price=99.5)

        entry_candidates = [
            EntryCandiate(
                signal=Signal(
                    strategy="adx_pullback",
                    symbol="NVDA",
                    direction="long",
                    strength=0.80,
                    metadata={"entry_atr": 5.0},
                ),
                prev_close=100.0,
                atr=5.0,
                indicators={},
            ),
        ]

        em.load_candidates(entry_candidates)

        # Confirm: price is at prev_close * 0.998 (within 0.3% tolerance)
        current_prices = {"NVDA": 99.8}  # 99.8 >= 100 * 0.997 = 99.7

        result = await em.execute_confirmation(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
            current_prices=current_prices,
        )

        assert len(result) == 1
        assert result[0].symbol == "NVDA"

    @pytest.mark.asyncio
    async def test_daily_limit_stops_execution_at_3(self):
        """Only 3 entries should be executed per day even with more candidates."""
        em = _make_entry_manager()

        # 5 Group A candidates
        entry_candidates = [
            EntryCandiate(
                signal=Signal(
                    strategy="rsi_mean_reversion",
                    symbol=f"SYM{i}",
                    direction="long",
                    strength=0.8 - i * 0.05,
                    metadata={"entry_atr": 2.0},
                ),
                prev_close=100.0,
                atr=2.0,
                indicators={},
            )
            for i in range(5)
        ]

        em.load_candidates(entry_candidates)

        result = await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.TREND,
            current_date_et=TRADE_DATE,
        )

        # At most 3 entries allowed per day
        assert len(result) <= 3
        assert em._daily_entry_count <= 3

    @pytest.mark.asyncio
    async def test_batch_result_regime_passed_through(self):
        """Regime from BatchResult should be used for allocation decisions."""
        em = _make_entry_manager()

        entry_candidate = EntryCandiate(
            signal=Signal(
                strategy="rsi_mean_reversion",
                symbol="AAPL",
                direction="long",
                strength=0.80,
                metadata={"entry_atr": 2.0},
            ),
            prev_close=100.0,
            atr=2.0,
            indicators={},
        )

        em.load_candidates([entry_candidate])

        # Execute with RANGING regime
        await em.execute_moo(
            account=_make_account(),
            positions=[],
            regime=MarketRegime.RANGING,
            current_date_et=TRADE_DATE,
        )

        # Verify that allocation_engine.should_enter was called with the regime
        em._allocation_engine.should_enter.assert_called()
        call_args = em._allocation_engine.should_enter.call_args
        assert call_args[0][1] == MarketRegime.RANGING or (
            len(call_args[1]) > 0 and call_args[1].get("regime") == MarketRegime.RANGING
        )
