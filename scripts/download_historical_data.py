"""Download and cache Alpaca historical bar data for backtesting.

Supports multiple time periods with explicit start/end dates and caches
results as pickle files in the data/ directory.

Usage:
    python scripts/download_historical_data.py --period 1
    python scripts/download_historical_data.py --period 2
    python scripts/download_historical_data.py --all
    python scripts/download_historical_data.py --period 1 --refresh
"""
from __future__ import annotations

import argparse
import logging
import os
import pickle
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Period definitions
# ---------------------------------------------------------------------------

MIN_BARS_REQUIRED = 60


@dataclass(frozen=True)
class PeriodDef:
    """Definition of a historical data download period."""
    period_id: int
    label: str
    start: datetime
    end: datetime
    output_filename: str


PERIODS: dict[int, PeriodDef] = {
    1: PeriodDef(
        period_id=1,
        label="Period 1 (2024-03 ~ 2025-02)",
        start=datetime(2024, 3, 1, tzinfo=timezone.utc),
        end=datetime(2025, 3, 1, tzinfo=timezone.utc),
        output_filename="historical_bars_period1.pkl",
    ),
    2: PeriodDef(
        period_id=2,
        label="Period 2 (2025-03 ~ 2026-02)",
        start=datetime(2025, 2, 28, tzinfo=timezone.utc),
        end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        output_filename="historical_bars.pkl",
    ),
}


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_symbols() -> list[str]:
    """Fetch S&P 500 symbols using the project's SP500Provider."""
    from autotrader.universe.provider import SP500Provider

    provider = SP500Provider()
    stocks = provider.fetch()
    symbols = [s.symbol for s in stocks]
    logger.info("Fetched %d S&P 500 symbols", len(symbols))
    return symbols


def download_bars(
    api_key: str,
    secret_key: str,
    symbols: list[str],
    period: PeriodDef,
) -> dict[str, list]:
    """Download daily bars from Alpaca for a specific date range.

    Uses the Alpaca SDK StockHistoricalDataClient directly with explicit
    start/end dates, bypassing AlpacaAdapter.get_historical_bars() which
    only supports fetching N days from today.

    Args:
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        symbols: List of ticker symbols to download.
        period: Period definition with start/end dates.

    Returns:
        Dictionary mapping symbol to list of Bar objects.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from autotrader.core.types import Bar, Timeframe

    client = StockHistoricalDataClient(api_key, secret_key)
    result: dict[str, list[Bar]] = {}

    batch_size = 50
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    failed_batches = 0

    logger.info(
        "Downloading %s: %s -> %s (%d symbols, %d batches)",
        period.label,
        period.start.strftime("%Y-%m-%d"),
        period.end.strftime("%Y-%m-%d"),
        len(symbols),
        total_batches,
    )

    for batch_idx in range(0, len(symbols), batch_size):
        batch = symbols[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=period.start,
                end=period.end,
            )
            raw = client.get_stock_bars(request)

            for sym in batch:
                try:
                    alpaca_bars = raw[sym]
                except (KeyError, IndexError):
                    continue
                if not alpaca_bars:
                    continue

                bars: list[Bar] = []
                for ab in alpaca_bars:
                    ts = ab.timestamp
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    bars.append(Bar(
                        symbol=str(ab.symbol),
                        timestamp=ts,
                        open=float(ab.open),
                        high=float(ab.high),
                        low=float(ab.low),
                        close=float(ab.close),
                        volume=float(ab.volume),
                        timeframe=Timeframe.DAILY,
                    ))
                result[sym] = bars

            logger.info(
                "  Batch %d/%d done (%d symbols fetched so far)",
                batch_num, total_batches, len(result),
            )

        except Exception:
            failed_batches += 1
            logger.exception(
                "  Batch %d/%d FAILED (symbols: %s...)",
                batch_num, total_batches, batch[:3],
            )

        # Rate limit courtesy: small delay between batches
        if batch_idx + batch_size < len(symbols):
            time.sleep(0.3)

    if failed_batches > 0:
        logger.warning("%d/%d batches failed", failed_batches, total_batches)

    return result


def filter_min_bars(
    bars_dict: dict[str, list],
    min_bars: int = MIN_BARS_REQUIRED,
) -> tuple[dict[str, list], int]:
    """Filter out symbols with fewer than min_bars.

    Returns:
        Tuple of (filtered dict, number of symbols removed).
    """
    filtered: dict[str, list] = {}
    removed = 0
    for sym, bars in bars_dict.items():
        if len(bars) >= min_bars:
            filtered[sym] = bars
        else:
            removed += 1
    return filtered, removed


def save_cache(
    bars_dict: dict[str, list],
    period: PeriodDef,
    data_dir: Path,
) -> Path:
    """Save bars to pickle cache file.

    The pkl structure matches the existing format:
        {"_meta_days": int, "bars": {symbol: [Bar, ...]}}

    Args:
        bars_dict: Dictionary of symbol -> list of Bar.
        period: Period definition for metadata.
        data_dir: Directory to save the file in.

    Returns:
        Path to the saved pickle file.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / period.output_filename

    # Calculate calendar days for _meta_days (matches existing convention)
    meta_days = (period.end - period.start).days

    payload = {
        "_meta_days": meta_days,
        "bars": bars_dict,
    }

    with open(output_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Saved %s (%.1f MB, %d symbols)",
        output_path, file_size_mb, len(bars_dict),
    )
    return output_path


def load_existing_cache(path: Path) -> dict[str, list] | None:
    """Load existing cache if it exists, returning the bars dict or None."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        bars = data.get("bars", {})
        logger.info(
            "Existing cache found: %s (%d symbols)",
            path.name, len(bars),
        )
        return bars
    except Exception:
        logger.warning("Failed to read existing cache %s, will re-download", path)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_period(
    period: PeriodDef,
    api_key: str,
    secret_key: str,
    symbols: list[str],
    data_dir: Path,
    refresh: bool = False,
) -> None:
    """Download and save bars for a single period."""
    output_path = data_dir / period.output_filename

    # Check for existing cache
    if not refresh:
        existing = load_existing_cache(output_path)
        if existing is not None:
            logger.info(
                "SKIP %s -- cache exists with %d symbols (use --refresh to re-download)",
                period.label, len(existing),
            )
            return

    logger.info("=" * 70)
    logger.info("Processing %s", period.label)
    logger.info("=" * 70)

    # Download
    start_time = time.time()
    bars_dict = download_bars(api_key, secret_key, symbols, period)
    download_secs = time.time() - start_time

    if not bars_dict:
        logger.error("No bars downloaded for %s -- aborting save", period.label)
        return

    # Filter by minimum bars
    bars_dict, removed = filter_min_bars(bars_dict, MIN_BARS_REQUIRED)
    logger.info(
        "After min-bars filter (%d): %d symbols kept, %d removed",
        MIN_BARS_REQUIRED, len(bars_dict), removed,
    )

    # Report bar count statistics
    bar_counts = [len(bars) for bars in bars_dict.values()]
    if bar_counts:
        logger.info(
            "Bar counts: min=%d, max=%d, avg=%.0f",
            min(bar_counts), max(bar_counts), sum(bar_counts) / len(bar_counts),
        )

    # Report date range from actual data
    all_first = []
    all_last = []
    for bars in bars_dict.values():
        if bars:
            all_first.append(bars[0].timestamp)
            all_last.append(bars[-1].timestamp)
    if all_first and all_last:
        logger.info(
            "Actual date range: %s -> %s",
            min(all_first).strftime("%Y-%m-%d"),
            max(all_last).strftime("%Y-%m-%d"),
        )

    # Save
    save_cache(bars_dict, period, data_dir)
    logger.info(
        "Completed %s in %.1f seconds",
        period.label, download_secs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and cache Alpaca historical bar data for backtesting.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/download_historical_data.py --period 1\n"
            "  python scripts/download_historical_data.py --period 2\n"
            "  python scripts/download_historical_data.py --all\n"
            "  python scripts/download_historical_data.py --all --refresh\n"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--period",
        type=int,
        choices=sorted(PERIODS.keys()),
        help="Period number to download (1 or 2)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Download all defined periods",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download even if cache exists",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------ #
    # Load credentials
    # ------------------------------------------------------------------ #
    load_dotenv(_PROJECT_ROOT / "config" / ".env")
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        logger.error(
            "ALPACA_API_KEY or ALPACA_SECRET_KEY not found in config/.env"
        )
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Fetch S&P 500 symbols
    # ------------------------------------------------------------------ #
    symbols = fetch_symbols()

    # ------------------------------------------------------------------ #
    # Determine which periods to process
    # ------------------------------------------------------------------ #
    if args.all:
        period_ids = sorted(PERIODS.keys())
    else:
        period_ids = [args.period]

    data_dir = _PROJECT_ROOT / "data"

    # ------------------------------------------------------------------ #
    # Process each period
    # ------------------------------------------------------------------ #
    for pid in period_ids:
        period = PERIODS[pid]
        process_period(period, api_key, secret_key, symbols, data_dir, args.refresh)

    logger.info("All done.")


if __name__ == "__main__":
    main()
