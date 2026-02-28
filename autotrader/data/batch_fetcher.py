"""BatchFetcher: fetches daily bars and latest quotes for the nightly scan pipeline.

Fetches daily OHLCV bars for up to 503 S&P 500 symbols in batches of 50
symbols per request using Alpaca's IEX data feed. Also provides latest
quote fetching for pre-market gap detection at 9:25 AM ET.

Design decisions:
- IEX feed (not SIP) -- the paper account does not have SIP access.
- Batch size of 50 to stay within Alpaca's per-request symbol limit.
- Exponential backoff on rate-limit (429) and transient errors.
- Concurrent batches (up to MAX_CONCURRENT) to complete < 60 s for 503 symbols.
- Partial failures are swallowed per-batch; caller receives whatever succeeded.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from autotrader.core.types import Bar, Timeframe

logger = logging.getLogger(__name__)

# Maximum number of concurrent batch requests sent to Alpaca
_MAX_CONCURRENT = 5
# Number of symbols per REST request (Alpaca hard limit)
_BATCH_SIZE = 50
# Maximum retry attempts per batch before giving up
_MAX_RETRIES = 3
# Base delay for exponential backoff in seconds
_BACKOFF_BASE = 1.0


class BatchFetcher:
    """Fetches daily bars and latest quotes for a large symbol universe.

    Wraps Alpaca's StockHistoricalDataClient with batching, concurrency
    control, and retry logic to efficiently fetch data for hundreds of
    symbols within the tight nightly scan window.

    Usage::

        fetcher = BatchFetcher(api_key, secret_key)
        bars = await fetcher.fetch_daily_bars(symbols, days=120)
        quotes = await fetcher.fetch_latest_quotes(symbols)
    """

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        # StockHistoricalDataClient is synchronous; we call it inside
        # executor threads to avoid blocking the event loop.
        self._client: StockHistoricalDataClient | None = None

    def _get_client(self) -> StockHistoricalDataClient:
        """Lazily create the Alpaca data client (not thread-safe, reuse same instance)."""
        if self._client is None:
            self._client = StockHistoricalDataClient(
                self._api_key, self._secret_key
            )
        return self._client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def fetch_daily_bars(
        self, symbols: list[str], days: int = 120
    ) -> dict[str, list[Bar]]:
        """Fetch ``days`` calendar days of daily OHLCV bars for all symbols.

        Symbols with no data (e.g., newly listed or halted) are silently
        omitted from the returned dict. Symbols that fail due to transient
        errors after retries are logged and omitted.

        Args:
            symbols: List of trading symbols to fetch.
            days: Number of calendar days of history to request.

        Returns:
            Mapping of symbol -> list[Bar] ordered oldest-first.
            Symbols with no available data are absent from the dict.
        """
        end_dt = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_dt = end_dt - timedelta(days=days)

        batches = _chunk(symbols, _BATCH_SIZE)
        logger.info(
            "Fetching daily bars for %d symbols in %d batches (days=%d)",
            len(symbols),
            len(batches),
            days,
        )
        t0 = time.monotonic()

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        tasks = [
            self._fetch_bars_batch(batch, start_dt, end_dt, semaphore)
            for batch in batches
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        result: dict[str, list[Bar]] = {}
        failed_batches = 0
        for br in batch_results:
            if isinstance(br, Exception):
                failed_batches += 1
                logger.warning("Batch fetch exception: %s", br)
                continue
            result.update(br)  # type: ignore[arg-type]

        elapsed = time.monotonic() - t0
        logger.info(
            "Daily bar fetch complete: %d/%d symbols, %.1fs elapsed, %d failed batches",
            len(result),
            len(symbols),
            elapsed,
            failed_batches,
        )
        return result

    async def fetch_latest_quotes(
        self, symbols: list[str]
    ) -> dict[str, float]:
        """Fetch the latest ask/bid midpoint price for pre-market gap detection.

        Used by GapFilter at 9:25 AM ET to detect gap-up/gap-down vs
        previous close. Returns the midpoint of the latest ask and bid.
        If a symbol has no quote data, it is omitted (caller treats this
        as "no data available -> keep candidate").

        Args:
            symbols: List of trading symbols.

        Returns:
            Mapping of symbol -> latest midpoint price (ask+bid)/2.
            Symbols with unavailable quotes are absent.
        """
        batches = _chunk(symbols, _BATCH_SIZE)
        logger.debug(
            "Fetching latest quotes for %d symbols in %d batches",
            len(symbols),
            len(batches),
        )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        tasks = [
            self._fetch_quotes_batch(batch, semaphore) for batch in batches
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        result: dict[str, float] = {}
        for br in batch_results:
            if isinstance(br, Exception):
                logger.warning("Quote batch fetch exception: %s", br)
                continue
            result.update(br)  # type: ignore[arg-type]

        logger.debug("Quote fetch complete: %d/%d symbols", len(result), len(symbols))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_bars_batch(
        self,
        symbols: list[str],
        start_dt: datetime,
        end_dt: datetime,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, list[Bar]]:
        """Fetch daily bars for a single batch with retry/backoff under semaphore."""
        async with semaphore:
            loop = asyncio.get_running_loop()
            for attempt in range(_MAX_RETRIES):
                try:
                    return await loop.run_in_executor(
                        None,
                        self._sync_fetch_bars_batch,
                        symbols,
                        start_dt,
                        end_dt,
                    )
                except Exception as exc:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "Bars batch attempt %d/%d failed (%s), retrying in %.1fs",
                            attempt + 1,
                            _MAX_RETRIES,
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Bars batch failed after %d attempts: %s (symbols: %s...)",
                            _MAX_RETRIES,
                            exc,
                            symbols[:3],
                        )
                        return {}
        return {}  # unreachable, satisfies type checker

    def _sync_fetch_bars_batch(
        self,
        symbols: list[str],
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, list[Bar]]:
        """Synchronous Alpaca call run inside an executor thread."""
        client = self._get_client()
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX,
        )
        raw = client.get_stock_bars(request)

        result: dict[str, list[Bar]] = {}
        for sym in symbols:
            try:
                alpaca_bars = raw[sym]
            except (KeyError, IndexError, TypeError):
                continue
            if not alpaca_bars:
                continue
            bars: list[Bar] = []
            for ab in alpaca_bars:
                ts: datetime = ab.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                bars.append(
                    Bar(
                        symbol=sym,
                        timestamp=ts,
                        open=float(ab.open),
                        high=float(ab.high),
                        low=float(ab.low),
                        close=float(ab.close),
                        volume=float(ab.volume),
                        timeframe=Timeframe.DAILY,
                    )
                )
            if bars:
                result[sym] = bars
        return result

    async def _fetch_quotes_batch(
        self,
        symbols: list[str],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, float]:
        """Fetch latest quotes for a single batch with retry/backoff under semaphore."""
        async with semaphore:
            loop = asyncio.get_running_loop()
            for attempt in range(_MAX_RETRIES):
                try:
                    return await loop.run_in_executor(
                        None,
                        self._sync_fetch_quotes_batch,
                        symbols,
                    )
                except Exception as exc:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "Quotes batch attempt %d/%d failed (%s), retrying in %.1fs",
                            attempt + 1,
                            _MAX_RETRIES,
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Quotes batch failed after %d attempts: %s",
                            _MAX_RETRIES,
                            exc,
                        )
                        return {}
        return {}

    def _sync_fetch_quotes_batch(self, symbols: list[str]) -> dict[str, float]:
        """Synchronous Alpaca latest-quote call run inside an executor thread."""
        client = self._get_client()
        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbols,
            feed=DataFeed.IEX,
        )
        raw = client.get_stock_latest_quote(request)

        result: dict[str, float] = {}
        for sym in symbols:
            try:
                quote: Any = raw[sym]
                ask = float(quote.ask_price or 0.0)
                bid = float(quote.bid_price or 0.0)
                if ask > 0 and bid > 0:
                    result[sym] = (ask + bid) / 2.0
                elif ask > 0:
                    result[sym] = ask
                elif bid > 0:
                    result[sym] = bid
            except (KeyError, TypeError, AttributeError):
                pass
        return result


def _chunk(items: list, size: int) -> list[list]:
    """Split a list into sub-lists of at most ``size`` items."""
    return [items[i : i + size] for i in range(0, len(items), size)]
