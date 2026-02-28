"""Unit tests for BatchFetcher (autotrader/data/batch_fetcher.py).

Tests cover:
- Batch size 50 symbols per request
- IEX feed used (not SIP)
- Retry on API failure
- Latest quote fetching for gap filter
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from autotrader.data.batch_fetcher import BatchFetcher, _chunk, _BATCH_SIZE


# ---------------------------------------------------------------------------
# Helper: create a mock Alpaca bar object
# ---------------------------------------------------------------------------

def _make_alpaca_bar(
    symbol: str,
    open_=148.0,
    high=152.0,
    low=147.0,
    close=150.0,
    volume=1_000_000.0,
    ts: datetime | None = None,
):
    bar = MagicMock()
    bar.timestamp = ts or datetime(2026, 2, 20, tzinfo=timezone.utc)
    bar.open = open_
    bar.high = high
    bar.low = low
    bar.close = close
    bar.volume = volume
    return bar


def _make_alpaca_quote(ask=150.5, bid=149.5):
    quote = MagicMock()
    quote.ask_price = ask
    quote.bid_price = bid
    return quote


def _make_client(bars_raw=None, quotes_raw=None):
    """Create a mock StockHistoricalDataClient."""
    client = MagicMock()
    if bars_raw is not None:
        client.get_stock_bars = MagicMock(return_value=bars_raw)
    if quotes_raw is not None:
        client.get_stock_latest_quote = MagicMock(return_value=quotes_raw)
    return client


# ---------------------------------------------------------------------------
# Test class: _chunk utility function
# ---------------------------------------------------------------------------

class TestChunkUtility:
    """Tests for the private _chunk helper."""

    def test_chunk_splits_evenly(self):
        items = list(range(100))
        chunks = _chunk(items, 50)
        assert len(chunks) == 2
        assert all(len(c) == 50 for c in chunks)

    def test_chunk_handles_remainder(self):
        items = list(range(55))
        chunks = _chunk(items, 50)
        assert len(chunks) == 2
        assert len(chunks[0]) == 50
        assert len(chunks[1]) == 5

    def test_chunk_single_batch(self):
        items = list(range(30))
        chunks = _chunk(items, 50)
        assert len(chunks) == 1
        assert chunks[0] == items

    def test_chunk_empty_list(self):
        chunks = _chunk([], 50)
        assert chunks == []

    def test_chunk_exact_batch_size(self):
        items = list(range(50))
        chunks = _chunk(items, 50)
        assert len(chunks) == 1

    def test_chunk_batch_size_is_50(self):
        """Default batch size constant should be 50."""
        assert _BATCH_SIZE == 50


# ---------------------------------------------------------------------------
# Test class: fetch_daily_bars
# ---------------------------------------------------------------------------

class TestFetchDailyBars:
    """Tests for fetch_daily_bars method."""

    @pytest.mark.asyncio
    async def test_returns_bars_for_all_symbols(self):
        """Should return a dict with bars for each symbol."""
        symbols = ["AAPL", "MSFT"]
        alpaca_bar_aapl = _make_alpaca_bar("AAPL")
        alpaca_bar_msft = _make_alpaca_bar("MSFT")

        raw = {"AAPL": [alpaca_bar_aapl], "MSFT": [alpaca_bar_msft]}
        client = _make_client(bars_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_daily_bars(symbols, days=30)

        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) == 1
        assert len(result["MSFT"]) == 1

    @pytest.mark.asyncio
    async def test_bar_fields_mapped_correctly(self):
        """Bar objects should have open, high, low, close, volume populated."""
        symbols = ["AAPL"]
        raw = {"AAPL": [_make_alpaca_bar("AAPL", open_=100.0, high=110.0, low=95.0, close=105.0, volume=500_000)]}
        client = _make_client(bars_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_daily_bars(symbols, days=30)

        bar = result["AAPL"][0]
        assert bar.open == 100.0
        assert bar.high == 110.0
        assert bar.low == 95.0
        assert bar.close == 105.0
        assert bar.volume == 500_000.0

    @pytest.mark.asyncio
    async def test_symbols_with_no_data_omitted(self):
        """Symbols not returned by Alpaca should be absent from result dict."""
        symbols = ["AAPL", "MISSING"]
        raw = {"AAPL": [_make_alpaca_bar("AAPL")]}  # MISSING not in raw
        client = _make_client(bars_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_daily_bars(symbols, days=30)

        assert "AAPL" in result
        assert "MISSING" not in result

    @pytest.mark.asyncio
    async def test_iex_feed_used_for_bars(self):
        """StockBarsRequest should use DataFeed.IEX (not SIP)."""
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest

        symbols = ["AAPL"]
        raw = {"AAPL": [_make_alpaca_bar("AAPL")]}
        client = _make_client(bars_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        captured_requests = []
        original_get_bars = client.get_stock_bars.side_effect

        def capture_request(req):
            captured_requests.append(req)
            return raw

        client.get_stock_bars = MagicMock(side_effect=capture_request)

        await fetcher.fetch_daily_bars(symbols, days=30)

        assert len(captured_requests) == 1
        assert captured_requests[0].feed == DataFeed.IEX

    @pytest.mark.asyncio
    async def test_batches_50_symbols_per_request(self):
        """110 symbols should result in 3 batch requests (50, 50, 10)."""
        symbols = [f"SYM{i:03d}" for i in range(110)]
        raw = {}  # no bars returned; just counting requests

        request_symbol_counts = []

        def capture_bars_request(req):
            request_symbol_counts.append(len(req.symbol_or_symbols))
            return {}

        client = MagicMock()
        client.get_stock_bars = MagicMock(side_effect=capture_bars_request)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        await fetcher.fetch_daily_bars(symbols, days=30)

        assert len(request_symbol_counts) == 3
        assert request_symbol_counts[0] == 50
        assert request_symbol_counts[1] == 50
        assert request_symbol_counts[2] == 10

    @pytest.mark.asyncio
    async def test_retry_on_api_failure_returns_partial_results(self):
        """A transient API failure should be retried; successful batches return data."""
        symbols = ["AAPL"]
        raw = {"AAPL": [_make_alpaca_bar("AAPL")]}

        call_count = {"n": 0}

        def flaky_get_bars(req):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("rate limit exceeded")
            return raw

        client = MagicMock()
        client.get_stock_bars = MagicMock(side_effect=flaky_get_bars)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch_daily_bars(symbols, days=30)

        # After retry, AAPL should be present
        assert "AAPL" in result

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_empty_for_batch(self):
        """If all 3 retries fail, that batch returns empty dict (not exception)."""
        symbols = ["AAPL"]

        client = MagicMock()
        client.get_stock_bars = MagicMock(side_effect=RuntimeError("persistent failure"))

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch_daily_bars(symbols, days=30)

        # Should return empty dict, not raise
        assert result == {}


# ---------------------------------------------------------------------------
# Test class: fetch_latest_quotes
# ---------------------------------------------------------------------------

class TestFetchLatestQuotes:
    """Tests for fetch_latest_quotes method."""

    @pytest.mark.asyncio
    async def test_returns_midpoint_price(self):
        """Should return (ask + bid) / 2 for each symbol."""
        symbols = ["AAPL"]
        raw = {"AAPL": _make_alpaca_quote(ask=151.0, bid=149.0)}
        client = _make_client(quotes_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_latest_quotes(symbols)

        assert "AAPL" in result
        assert result["AAPL"] == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_iex_feed_used_for_quotes(self):
        """StockLatestQuoteRequest should use DataFeed.IEX."""
        from alpaca.data.enums import DataFeed

        symbols = ["AAPL"]
        raw = {"AAPL": _make_alpaca_quote(ask=150.5, bid=149.5)}

        captured_requests = []

        def capture_quote_request(req):
            captured_requests.append(req)
            return raw

        client = MagicMock()
        client.get_stock_latest_quote = MagicMock(side_effect=capture_quote_request)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        await fetcher.fetch_latest_quotes(symbols)

        assert len(captured_requests) == 1
        assert captured_requests[0].feed == DataFeed.IEX

    @pytest.mark.asyncio
    async def test_symbol_with_no_quote_omitted(self):
        """Symbols without valid quote data should be absent from result."""
        symbols = ["AAPL", "MISSING"]
        raw = {"AAPL": _make_alpaca_quote(ask=150.5, bid=149.5)}
        # MISSING not in raw

        client = _make_client(quotes_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_latest_quotes(symbols)

        assert "AAPL" in result
        assert "MISSING" not in result

    @pytest.mark.asyncio
    async def test_quote_fallback_to_ask_only(self):
        """If bid is 0/None but ask is valid, use ask price."""
        symbols = ["AAPL"]
        raw = {"AAPL": _make_alpaca_quote(ask=150.0, bid=0.0)}
        client = _make_client(quotes_raw=raw)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        result = await fetcher.fetch_latest_quotes(symbols)

        assert "AAPL" in result
        assert result["AAPL"] == 150.0

    @pytest.mark.asyncio
    async def test_retry_on_quote_api_failure(self):
        """Transient failure on quote fetch should be retried."""
        symbols = ["AAPL"]
        raw = {"AAPL": _make_alpaca_quote(ask=150.5, bid=149.5)}

        call_count = {"n": 0}

        def flaky_get_quotes(req):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("timeout")
            return raw

        client = MagicMock()
        client.get_stock_latest_quote = MagicMock(side_effect=flaky_get_quotes)

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch_latest_quotes(symbols)

        assert "AAPL" in result

    @pytest.mark.asyncio
    async def test_all_quote_retries_exhausted_returns_empty(self):
        """If all quote retries fail, return empty dict without raising."""
        symbols = ["AAPL"]

        client = MagicMock()
        client.get_stock_latest_quote = MagicMock(side_effect=RuntimeError("persistent"))

        fetcher = BatchFetcher("key", "secret")
        fetcher._client = client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch_latest_quotes(symbols)

        assert result == {}
