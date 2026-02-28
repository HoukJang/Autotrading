"""Unit tests for NightlyScanner (autotrader/batch/scanner.py).

Tests cover:
- Scan produces ScanResult for each symbol with signal
- Symbols with no signal are excluded
- Partial failure handling (some symbols fail, others succeed)
- BatchResult saved to JSON correctly
- Minimum symbol threshold (< 10 symbols = abort)
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autotrader.batch.scanner import NightlyScanner
from autotrader.batch.types import BatchResult, Candidate, ScanResult
from autotrader.batch.ranking import SignalRanker
from autotrader.core.types import Bar, Timeframe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    symbol: str = "AAPL",
    close: float = 150.0,
    timestamp: datetime | None = None,
) -> Bar:
    ts = timestamp or datetime(2026, 2, 20, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=ts,
        open=148.0,
        high=152.0,
        low=147.0,
        close=close,
        volume=1_000_000,
        timeframe=Timeframe.DAILY,
    )


def _make_bars(symbol: str = "AAPL", n: int = 80, close: float = 150.0) -> list[Bar]:
    """Return n daily bars for a symbol."""
    from datetime import timedelta
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        _make_bar(symbol=symbol, close=close, timestamp=base + timedelta(days=i))
        for i in range(n)
    ]


def _make_fetcher(bars_by_symbol: dict[str, list[Bar]]) -> MagicMock:
    """Create a mock BatchFetcher returning preset bars."""
    fetcher = MagicMock()
    fetcher.fetch_daily_bars = AsyncMock(return_value=bars_by_symbol)
    return fetcher


def _make_ranker_with_candidates(candidates: list[Candidate]) -> MagicMock:
    """Create a mock SignalRanker that returns preset candidates."""
    ranker = MagicMock(spec=SignalRanker)
    ranker.rank = MagicMock(return_value=candidates)
    return ranker


# ---------------------------------------------------------------------------
# Test class: normal scan behavior
# ---------------------------------------------------------------------------

class TestNightlyScannerNormalBehavior:
    """Tests for the core scan pipeline under normal conditions."""

    @pytest.mark.asyncio
    async def test_scan_returns_batch_result(self):
        """run() should return a BatchResult instance."""
        bars = _make_bars("AAPL", n=80)
        fetcher = _make_fetcher({"AAPL": bars})

        # Mock _scan_symbol to return a ScanResult so we don't need real indicators
        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", return_value=[]):
                result = await scanner.run(["AAPL"])

        assert isinstance(result, BatchResult)

    @pytest.mark.asyncio
    async def test_scan_records_symbols_scanned_count(self):
        """symbols_scanned should equal the number of symbols that returned bars."""
        # Use 12 symbols (>= _MIN_SYMBOLS_THRESHOLD=10) to avoid abort
        sym_list = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA",
                    "META", "NFLX", "JPM", "BAC", "WFC", "GS"]
        bars_by_symbol = {sym: _make_bars(sym, n=80) for sym in sym_list}
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", return_value=[]):
                result = await scanner.run(list(bars_by_symbol.keys()))

        assert result.symbols_scanned == len(sym_list)

    @pytest.mark.asyncio
    async def test_symbols_with_no_signal_are_excluded_from_count(self):
        """symbols_with_signals should only count symbols that produced at least one signal."""
        # 11 symbols to exceed _MIN_SYMBOLS_THRESHOLD=10
        sym_list = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA",
                    "META", "NFLX", "JPM", "BAC", "WFC"]
        bars_by_symbol = {sym: _make_bars(sym, n=80) for sym in sym_list}
        fetcher = _make_fetcher(bars_by_symbol)

        aapl_result = ScanResult(
            symbol="AAPL", strategy="rsi_mean_reversion", direction="long",
            signal_strength=0.8, prev_close=150.0, scanned_at=datetime.now(tz=timezone.utc),
        )

        def mock_scan_symbol(symbol, bars):
            if symbol == "AAPL":
                return [aapl_result]
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", side_effect=mock_scan_symbol):
                result = await scanner.run(list(bars_by_symbol.keys()))

        assert result.symbols_with_signals == 1

    @pytest.mark.asyncio
    async def test_candidates_from_ranker_are_in_result(self):
        """BatchResult.candidates should be whatever the ranker returns."""
        # Use 10 symbols to exceed _MIN_SYMBOLS_THRESHOLD=10; mock the ScanResult for AAPL
        sym_list = ["AAPL"] + [f"SYM{i}" for i in range(9)]
        bars_by_symbol = {sym: _make_bars(sym, n=80) for sym in sym_list}
        fetcher = _make_fetcher(bars_by_symbol)

        sr = ScanResult(
            symbol="AAPL", strategy="rsi_mean_reversion", direction="long",
            signal_strength=0.8, prev_close=150.0, scanned_at=datetime.now(tz=timezone.utc),
        )
        expected_candidate = Candidate(scan_result=sr, rank=1, composite_score=0.85)
        ranker = _make_ranker_with_candidates([expected_candidate])

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=ranker,
                results_path=results_path,
            )

            def mock_scan(symbol, bars):
                if symbol == "AAPL":
                    return [sr]
                return []

            with patch.object(scanner, "_scan_symbol", side_effect=mock_scan):
                result = await scanner.run(list(bars_by_symbol.keys()))

        assert len(result.candidates) == 1
        assert result.candidates[0].symbol == "AAPL"


# ---------------------------------------------------------------------------
# Test class: minimum symbol threshold
# ---------------------------------------------------------------------------

class TestMinimumSymbolThreshold:
    """Scans should abort if fewer than 10 symbols have data."""

    @pytest.mark.asyncio
    async def test_fewer_than_10_symbols_aborts_scan(self):
        """When fewer than 10 symbols return bars, result should have no candidates."""
        bars_by_symbol = {
            f"SYM{i}": _make_bars(f"SYM{i}", n=80) for i in range(5)
        }
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=SignalRanker(),
                results_path=results_path,
            )
            result = await scanner.run(list(bars_by_symbol.keys()))

        assert result.candidates == []
        assert result.symbols_scanned == 0
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_exactly_9_symbols_aborts(self):
        """9 symbols is below threshold (< 10)."""
        bars_by_symbol = {
            f"SYM{i}": _make_bars(f"SYM{i}", n=80) for i in range(9)
        }
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=SignalRanker(),
                results_path=results_path,
            )
            result = await scanner.run(list(bars_by_symbol.keys()))

        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_empty_fetch_result_aborts(self):
        """Empty dict from fetcher should abort scan."""
        fetcher = _make_fetcher({})

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=SignalRanker(),
                results_path=results_path,
            )
            result = await scanner.run(["AAPL", "MSFT"])

        assert result.candidates == []
        assert result.symbols_scanned == 0


# ---------------------------------------------------------------------------
# Test class: partial failure handling
# ---------------------------------------------------------------------------

class TestPartialFailureHandling:
    """Some symbols fail during scan; others should still succeed."""

    @pytest.mark.asyncio
    async def test_failing_symbol_recorded_in_errors(self):
        """Symbols that throw during _scan_symbol should appear in errors list."""
        bars_by_symbol = {
            "AAPL": _make_bars("AAPL", n=80),
            "BROKEN": _make_bars("BROKEN", n=80),
            **{f"OK{i}": _make_bars(f"OK{i}", n=80) for i in range(15)},
        }
        fetcher = _make_fetcher(bars_by_symbol)

        def mock_scan_symbol(symbol, bars):
            if symbol == "BROKEN":
                raise ValueError("indicator failure")
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", side_effect=mock_scan_symbol):
                result = await scanner.run(list(bars_by_symbol.keys()))

        error_symbols = [e["symbol"] for e in result.errors]
        assert "BROKEN" in error_symbols

    @pytest.mark.asyncio
    async def test_successful_symbols_still_scanned_after_failure(self):
        """Failure of one symbol should not prevent others from being scanned."""
        symbols = [f"GOOD{i}" for i in range(12)] + ["BROKEN"]
        bars_by_symbol = {sym: _make_bars(sym, n=80) for sym in symbols}
        fetcher = _make_fetcher(bars_by_symbol)

        scan_count = {"count": 0}

        def mock_scan_symbol(symbol, bars):
            if symbol == "BROKEN":
                raise ValueError("broken")
            scan_count["count"] += 1
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", side_effect=mock_scan_symbol):
                result = await scanner.run(symbols)

        # 12 good symbols should have been scanned
        assert scan_count["count"] == 12

    @pytest.mark.asyncio
    async def test_fetch_exception_results_in_empty_bars(self):
        """If fetcher raises an exception, result should have no candidates."""
        fetcher = MagicMock()
        fetcher.fetch_daily_bars = AsyncMock(side_effect=RuntimeError("API timeout"))

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=SignalRanker(),
                results_path=results_path,
            )
            result = await scanner.run(["AAPL", "MSFT"])

        assert result.candidates == []
        assert result.symbols_scanned == 0


# ---------------------------------------------------------------------------
# Test class: BatchResult JSON persistence
# ---------------------------------------------------------------------------

class TestBatchResultJsonPersistence:
    """BatchResult should be saved to disk as valid JSON."""

    @pytest.mark.asyncio
    async def test_result_saved_to_json_file(self):
        """After run(), a JSON file should exist at results_path."""
        bars_by_symbol = {f"SYM{i}": _make_bars(f"SYM{i}", n=80) for i in range(15)}
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "subdir", "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", return_value=[]):
                await scanner.run(list(bars_by_symbol.keys()))

            assert os.path.exists(results_path)

    @pytest.mark.asyncio
    async def test_saved_json_is_valid_and_contains_required_keys(self):
        """The saved JSON should be parseable and contain run_at and candidates."""
        bars_by_symbol = {f"SYM{i}": _make_bars(f"SYM{i}", n=80) for i in range(15)}
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", return_value=[]):
                await scanner.run(list(bars_by_symbol.keys()))

            with open(results_path, encoding="utf-8") as f:
                data = json.load(f)

        assert "run_at" in data
        assert "candidates" in data
        assert "symbols_scanned" in data
        assert "regime" in data

    @pytest.mark.asyncio
    async def test_regime_included_in_saved_json(self):
        """The regime parameter passed to run() should appear in the saved JSON."""
        bars_by_symbol = {f"SYM{i}": _make_bars(f"SYM{i}", n=80) for i in range(15)}
        fetcher = _make_fetcher(bars_by_symbol)

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = os.path.join(tmpdir, "results.json")
            scanner = NightlyScanner(
                fetcher=fetcher,
                ranker=_make_ranker_with_candidates([]),
                results_path=results_path,
            )

            with patch.object(scanner, "_scan_symbol", return_value=[]):
                await scanner.run(list(bars_by_symbol.keys()), regime="TREND")

            with open(results_path, encoding="utf-8") as f:
                data = json.load(f)

        assert data["regime"] == "TREND"
