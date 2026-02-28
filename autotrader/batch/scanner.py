"""NightlyScanner: runs all strategies against S&P 500 symbols after market close.

Pipeline:
    1. Fetch 120 days of daily bars for all S&P 500 symbols (BatchFetcher)
    2. For each symbol with sufficient bars:
       a. Compute indicators via IndicatorEngine
       b. Build a MarketContext with history deque
       c. Run all strategies via StrategyEngine
       d. Collect non-None signals (direction != "close")
    3. Rank candidates using SignalRanker (top 12)
    4. Persist BatchResult to data/batch_results.json

Error handling:
    - Symbols that fail indicator computation or strategy execution are
      skipped individually (logged at WARNING level).
    - If < 10 symbols have enough data, the scan is aborted (logged as ERROR).
    - Missing data/results dir is created automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from autotrader.batch.ranking import SignalRanker
from autotrader.batch.types import BatchResult, Candidate, ScanResult
from autotrader.core.types import Bar, MarketContext, Timeframe
from autotrader.data.batch_fetcher import BatchFetcher
from autotrader.indicators.engine import IndicatorEngine
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

logger = logging.getLogger(__name__)

# Path to persist batch results for the dashboard
_BATCH_RESULTS_PATH = os.path.join("data", "batch_results.json")

# Minimum number of bars a symbol must have to be scanned
_MIN_BARS_REQUIRED = 60

# Number of candidates to select
_TOP_N = 12

# Minimum symbols with data before aborting the scan
_MIN_SYMBOLS_THRESHOLD = 10

# All strategies instantiated once and reused across symbols
_STRATEGY_CLASSES = [
    AdxPullback,
    RsiMeanReversion,
    BbSqueezeBreakout,
    OverboughtShort,
    RegimeMomentum,
]

# Union of all required IndicatorSpecs across all strategies (deduped by key)
def _build_indicator_specs() -> list[IndicatorSpec]:
    """Collect the union of required IndicatorSpecs from all strategies."""
    seen: dict[str, IndicatorSpec] = {}
    for cls in _STRATEGY_CLASSES:
        instance = cls()
        for spec in instance.required_indicators:
            if spec.key not in seen:
                seen[spec.key] = spec
    return list(seen.values())


# Sector map for S&P 500 symbols (GICS sectors, top holdings per sector).
# This is a curated subset covering the most-traded S&P 500 symbols.
# The full list comes from sp500.py or Wikipedia fetching; this provides
# a fallback for ranking diversification purposes.
_SECTOR_MAP: dict[str, str] = {
    # Information Technology
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AMD": "Information Technology",
    "INTC": "Information Technology",
    "AVGO": "Information Technology",
    "QCOM": "Information Technology",
    "TXN": "Information Technology",
    "MU": "Information Technology",
    "AMAT": "Information Technology",
    "LRCX": "Information Technology",
    "KLAC": "Information Technology",
    "NOW": "Information Technology",
    "CRM": "Information Technology",
    "ORCL": "Information Technology",
    "IBM": "Information Technology",
    "ACN": "Information Technology",
    "INTU": "Information Technology",
    "ADBE": "Information Technology",
    "SNPS": "Information Technology",
    "CDNS": "Information Technology",
    "HPQ": "Information Technology",
    "DELL": "Information Technology",
    "ANET": "Information Technology",
    "FTNT": "Information Technology",
    # Communication Services
    "GOOGL": "Communication Services",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "DIS": "Communication Services",
    "TMUS": "Communication Services",
    "VZ": "Communication Services",
    "T": "Communication Services",
    "CHTR": "Communication Services",
    "CMCSA": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    "LOW": "Consumer Discretionary",
    "TJX": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary",
    "ABNB": "Consumer Discretionary",
    "EBAY": "Consumer Discretionary",
    "F": "Consumer Discretionary",
    "GM": "Consumer Discretionary",
    # Consumer Staples
    "WMT": "Consumer Staples",
    "COST": "Consumer Staples",
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "PEP": "Consumer Staples",
    "PM": "Consumer Staples",
    "MO": "Consumer Staples",
    "CL": "Consumer Staples",
    "MDLZ": "Consumer Staples",
    # Financials
    "JPM": "Financials",
    "BAC": "Financials",
    "WFC": "Financials",
    "GS": "Financials",
    "MS": "Financials",
    "BLK": "Financials",
    "SCHW": "Financials",
    "C": "Financials",
    "USB": "Financials",
    "AXP": "Financials",
    "COF": "Financials",
    "MCO": "Financials",
    "SPGI": "Financials",
    "CB": "Financials",
    # Healthcare
    "JNJ": "Healthcare",
    "LLY": "Healthcare",
    "ABBV": "Healthcare",
    "MRK": "Healthcare",
    "PFE": "Healthcare",
    "TMO": "Healthcare",
    "ABT": "Healthcare",
    "DHR": "Healthcare",
    "AMGN": "Healthcare",
    "GILD": "Healthcare",
    "CVS": "Healthcare",
    "CI": "Healthcare",
    "UNH": "Healthcare",
    "ELV": "Healthcare",
    "HUM": "Healthcare",
    "ISRG": "Healthcare",
    "SYK": "Healthcare",
    "MDT": "Healthcare",
    "BSX": "Healthcare",
    "BMY": "Healthcare",
    # Industrials
    "CAT": "Industrials",
    "DE": "Industrials",
    "HON": "Industrials",
    "UPS": "Industrials",
    "GE": "Industrials",
    "BA": "Industrials",
    "RTX": "Industrials",
    "LMT": "Industrials",
    "NOC": "Industrials",
    "GD": "Industrials",
    "MMM": "Industrials",
    "FDX": "Industrials",
    "ETN": "Industrials",
    "EMR": "Industrials",
    "PH": "Industrials",
    # Energy
    "XOM": "Energy",
    "CVX": "Energy",
    "COP": "Energy",
    "SLB": "Energy",
    "EOG": "Energy",
    "PSX": "Energy",
    "MPC": "Energy",
    "VLO": "Energy",
    # Materials
    "LIN": "Materials",
    "APD": "Materials",
    "SHW": "Materials",
    "FCX": "Materials",
    "NEM": "Materials",
    "NUE": "Materials",
    "DD": "Materials",
    # Real Estate
    "AMT": "Real Estate",
    "PLD": "Real Estate",
    "CCI": "Real Estate",
    "EQIX": "Real Estate",
    "SPG": "Real Estate",
    "O": "Real Estate",
    "VICI": "Real Estate",
    # Utilities
    "NEE": "Utilities",
    "DUK": "Utilities",
    "SO": "Utilities",
    "D": "Utilities",
    "AEP": "Utilities",
    "EXC": "Utilities",
    "XEL": "Utilities",
}


class NightlyScanner:
    """Scans the full S&P 500 universe after market close and produces ranked candidates.

    Usage::

        scanner = NightlyScanner(fetcher, ranker)
        result = await scanner.run(symbols)
    """

    def __init__(
        self,
        fetcher: BatchFetcher,
        ranker: SignalRanker | None = None,
        results_path: str = _BATCH_RESULTS_PATH,
        sector_map: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            fetcher: BatchFetcher for daily bar retrieval.
            ranker: SignalRanker instance; defaults to SignalRanker(top_n=12).
            results_path: File path to save BatchResult JSON.
            sector_map: Optional symbol->sector mapping for diversification.
        """
        self._fetcher = fetcher
        self._ranker = ranker or SignalRanker(top_n=_TOP_N)
        self._results_path = results_path
        self._sector_map = sector_map if sector_map is not None else _SECTOR_MAP
        # Build indicator specs once (union across all strategies)
        self._indicator_specs = _build_indicator_specs()
        # Instantiate one fresh set of strategies per scanner instance
        self._strategies = [cls() for cls in _STRATEGY_CLASSES]

    async def run(
        self,
        symbols: list[str],
        days: int = 120,
        regime: str = "UNCERTAIN",
    ) -> BatchResult:
        """Execute the full nightly scan pipeline.

        Args:
            symbols: Full S&P 500 symbol list (up to 503 symbols).
            days: Number of calendar days of bar history to fetch.
            regime: Current market regime string (from RegimeDetector or SPY proxy).

        Returns:
            BatchResult with ranked candidates and execution metadata.
            The result is also persisted to disk as JSON.
        """
        t0 = time.monotonic()
        logger.info(
            "NightlyScanner: starting scan for %d symbols (days=%d, regime=%s)",
            len(symbols),
            days,
            regime,
        )

        # Stage 1: Fetch all bars
        try:
            bars_by_symbol = await self._fetcher.fetch_daily_bars(symbols, days=days)
        except Exception:
            logger.exception("NightlyScanner: fatal error fetching bars")
            bars_by_symbol = {}

        if len(bars_by_symbol) < _MIN_SYMBOLS_THRESHOLD:
            logger.error(
                "NightlyScanner: only %d symbols had data (minimum %d), aborting scan",
                len(bars_by_symbol),
                _MIN_SYMBOLS_THRESHOLD,
            )
            result = BatchResult(
                run_at=datetime.now(tz=timezone.utc),
                scan_duration_secs=time.monotonic() - t0,
                symbols_scanned=0,
                symbols_with_signals=0,
                candidates=[],
                errors=[{"symbol": "__all__", "error": "insufficient_data"}],
                regime=regime,
            )
            self._save_result(result)
            return result

        # Stage 2: Scan each symbol
        scan_results: list[ScanResult] = []
        errors: list[dict[str, str]] = []
        symbols_with_signals = 0

        for symbol, bars in bars_by_symbol.items():
            try:
                symbol_results = self._scan_symbol(symbol, bars)
                if symbol_results:
                    symbols_with_signals += 1
                    scan_results.extend(symbol_results)
            except Exception as exc:
                logger.warning("NightlyScanner: failed to scan %s: %s", symbol, exc)
                errors.append({"symbol": symbol, "error": str(exc)})

        logger.info(
            "NightlyScanner: scanned %d symbols, %d with signals, %d errors",
            len(bars_by_symbol),
            symbols_with_signals,
            len(errors),
        )

        # Stage 3: Rank and select top candidates
        candidates = self._ranker.rank(scan_results, sector_map=self._sector_map)

        # Stage 4: Build and persist result
        result = BatchResult(
            run_at=datetime.now(tz=timezone.utc),
            scan_duration_secs=time.monotonic() - t0,
            symbols_scanned=len(bars_by_symbol),
            symbols_with_signals=symbols_with_signals,
            candidates=candidates,
            errors=errors,
            regime=regime,
        )

        self._save_result(result)

        logger.info(
            "NightlyScanner: scan complete in %.1fs -- %d candidates selected",
            result.scan_duration_secs,
            len(candidates),
        )
        for cand in candidates:
            logger.info(
                "  [%d] %-6s %-22s %-5s strength=%.3f composite=%.4f",
                cand.rank,
                cand.symbol,
                cand.strategy,
                cand.direction,
                cand.signal_strength,
                cand.composite_score,
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_symbol(self, symbol: str, bars: list[Bar]) -> list[ScanResult]:
        """Compute indicators and run all strategies against a single symbol.

        Args:
            symbol: Trading symbol.
            bars: List of daily Bar objects (oldest first).

        Returns:
            List of ScanResult objects (one per strategy that fired).
            Close signals are excluded (scanner only cares about entries).
        """
        if len(bars) < _MIN_BARS_REQUIRED:
            return []

        # Build history deque (most-recent-last, same as live trading)
        history: deque[Bar] = deque(bars, maxlen=500)

        # Compute all indicators
        engine = IndicatorEngine()
        for spec in self._indicator_specs:
            engine.register(spec)

        indicators = engine.compute(history)

        # Check that core indicators are available (warmup complete)
        if not _has_required_indicators(indicators):
            return []

        # Build MarketContext using the latest bar
        latest_bar = bars[-1]
        ctx = MarketContext(
            symbol=symbol,
            bar=latest_bar,
            indicators=indicators,
            history=history,
        )

        prev_close = latest_bar.close
        scanned_at = datetime.now(tz=timezone.utc)

        results: list[ScanResult] = []
        for strategy in self._strategies:
            try:
                signal = strategy.on_context(ctx)
            except Exception as exc:
                logger.debug(
                    "Strategy %s failed on %s: %s", strategy.name, symbol, exc
                )
                continue

            if signal is None:
                continue
            # Skip close signals (scanner only cares about entries)
            if signal.direction == "close":
                continue

            flat_indicators = _flatten_indicators(indicators)

            results.append(
                ScanResult(
                    symbol=symbol,
                    strategy=strategy.name,
                    direction=signal.direction,
                    signal_strength=signal.strength,
                    indicators=flat_indicators,
                    prev_close=prev_close,
                    scanned_at=scanned_at,
                    metadata=dict(signal.metadata),
                )
            )

        return results

    def _save_result(self, result: BatchResult) -> None:
        """Persist the batch result to JSON for the dashboard."""
        try:
            os.makedirs(os.path.dirname(self._results_path) or ".", exist_ok=True)
            tmp_path = self._results_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2)
            # Atomic rename to avoid partial writes being read by dashboard
            os.replace(tmp_path, self._results_path)
            logger.info("BatchResult saved to %s", self._results_path)
        except Exception:
            logger.exception("Failed to save batch result to %s", self._results_path)


def _has_required_indicators(indicators: dict[str, Any]) -> bool:
    """Return True if the minimum required indicators are all non-None.

    The minimum set needed for any strategy to fire is:
    RSI, ADX, ATR, and BBANDS.
    """
    required_keys = ["RSI_14", "ADX_14", "ATR_14", "BBANDS_20"]
    return all(indicators.get(k) is not None for k in required_keys)


def _flatten_indicators(indicators: dict[str, Any]) -> dict[str, float | dict | None]:
    """Return a copy of the indicators dict suitable for JSON serialization."""
    flat: dict[str, float | dict | None] = {}
    for key, value in indicators.items():
        if isinstance(value, dict):
            # Include BB sub-values as a nested dict
            flat[key] = {
                k: round(float(v), 6) if isinstance(v, (int, float)) else v
                for k, v in value.items()
            }
        elif isinstance(value, (int, float)):
            flat[key] = round(float(value), 6)
        else:
            flat[key] = value
    return flat
