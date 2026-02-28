"""Batch Backtest Runner CLI script.

Runs the BatchBacktester over synthetic (or real) historical data and
generates a performance report.

Usage examples:
    # Basic run with synthetic data (2 years, 30 symbols):
    python scripts/run_batch_backtest.py

    # Custom date range and capital:
    python scripts/run_batch_backtest.py --start 2024-01-01 --end 2025-12-31 --capital 100000

    # Run a single strategy only:
    python scripts/run_batch_backtest.py --strategy consecutive_down

    # Compare entry day skip ON vs OFF:
    python scripts/run_batch_backtest.py --compare-entry-skip

    # Compare max hold days (5 vs 7):
    python scripts/run_batch_backtest.py --compare-hold-days

    # Full comparison matrix (slower):
    python scripts/run_batch_backtest.py --full-comparison

    # Save JSON results:
    python scripts/run_batch_backtest.py --output results/backtest.json

    # Real historical data from Alpaca (S&P 500, 1 year):
    python scripts/run_batch_backtest.py --real-data

    # Real data with custom period and forced refresh:
    python scripts/run_batch_backtest.py --real-data --data-days 730 --refresh-data
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import pickle
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure project root is on path when running as a script
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from autotrader.backtest.batch_simulator import (
    BatchBacktester,
    BatchBacktestResult,
    BatchTradeRecord,
    SyntheticDataGenerator,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_batch_backtest")

# Suppress verbose scanner/ranker logs during backtest
logging.getLogger("autotrader.batch.ranking").setLevel(logging.WARNING)
logging.getLogger("autotrader.execution.exit_rules").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Symbol universe for synthetic data generation
# ---------------------------------------------------------------------------

_DEFAULT_SYMBOLS = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "TSLA",
    # Financials
    "JPM", "BAC", "GS", "MS",
    # Healthcare
    "JNJ", "LLY", "ABBV", "MRK",
    # Consumer
    "HD", "MCD", "NKE", "COST",
    # Industrials / Energy
    "CAT", "DE", "XOM", "CVX",
    # Miscellaneous
    "BLK", "SPGI", "TMO", "LIN", "NEE", "AVGO",
]

# ---------------------------------------------------------------------------
# Helper: data loading / generation
# ---------------------------------------------------------------------------

_CACHE_PATH = os.path.join(_PROJECT_ROOT, "data", "historical_bars.pkl")


def _fetch_real_data(
    data_days: int = 365,
    refresh: bool = False,
    min_bars: int = 60,
) -> dict:
    """Fetch real daily bars from Alpaca for all S&P 500 symbols.

    Downloads via AlpacaAdapter.get_historical_bars() and caches the result
    to data/historical_bars.pkl. Subsequent runs reuse the cache unless
    --refresh-data is passed.
    """
    # Check cache first
    if not refresh and os.path.exists(_CACHE_PATH):
        logger.info("Loading cached historical bars from %s", _CACHE_PATH)
        with open(_CACHE_PATH, "rb") as f:
            cached = pickle.load(f)
        # Validate cache has the right data_days (stored as metadata)
        cached_days = cached.get("_meta_days", 0)
        bars_by_symbol = cached.get("bars", {})
        if cached_days == data_days and bars_by_symbol:
            logger.info(
                "Cache hit: %d symbols, %d-day data",
                len(bars_by_symbol), cached_days,
            )
            return bars_by_symbol
        logger.info("Cache stale (days=%d vs requested=%d), re-downloading", cached_days, data_days)

    # Load Alpaca credentials from config/.env
    env_path = os.path.join(_PROJECT_ROOT, "config", ".env")
    if not os.path.exists(env_path):
        logger.error("config/.env not found. Cannot fetch real data.")
        sys.exit(1)

    api_key = None
    secret_key = None
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("ALPACA_API_KEY="):
                api_key = line.split("=", 1)[1]
            elif line.startswith("ALPACA_SECRET_KEY="):
                secret_key = line.split("=", 1)[1]

    if not api_key or not secret_key:
        logger.error("ALPACA_API_KEY or ALPACA_SECRET_KEY not found in config/.env")
        sys.exit(1)

    # Fetch S&P 500 symbols
    from autotrader.universe.provider import SP500Provider

    logger.info("Fetching S&P 500 symbol list...")
    provider = SP500Provider()
    stocks = provider.fetch()
    symbols = [s.symbol for s in stocks]
    logger.info("Got %d S&P 500 symbols", len(symbols))

    # Fetch historical bars via AlpacaAdapter
    from autotrader.broker.alpaca_adapter import AlpacaAdapter

    adapter = AlpacaAdapter(api_key=api_key, secret_key=secret_key, paper=True, feed="iex")

    async def _do_fetch() -> dict:
        await adapter.connect()
        try:
            return await adapter.get_historical_bars(symbols, days=data_days)
        finally:
            await adapter.disconnect()

    logger.info(
        "Downloading %d-day historical bars for %d symbols (batch_size=50)...",
        data_days, len(symbols),
    )
    bars_by_symbol = asyncio.run(_do_fetch())

    # Filter symbols with insufficient bars for warmup
    filtered: dict = {}
    for sym, bars in bars_by_symbol.items():
        if len(bars) >= min_bars:
            filtered[sym] = bars

    dropped = len(bars_by_symbol) - len(filtered)
    if dropped:
        logger.info("Dropped %d symbols with < %d bars", dropped, min_bars)
    logger.info("Real data ready: %d symbols", len(filtered))

    # Save to cache
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    cache_data = {"_meta_days": data_days, "bars": filtered}
    with open(_CACHE_PATH, "wb") as f:
        pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    cache_size_mb = os.path.getsize(_CACHE_PATH) / (1024 * 1024)
    logger.info("Cached to %s (%.1f MB)", _CACHE_PATH, cache_size_mb)

    return filtered


def _generate_synthetic_data(
    symbols: list[str],
    start_date: date,
    end_date: date,
    seed: int = 42,
) -> dict:
    """Generate synthetic daily bars for all symbols over the date range."""
    num_bars = int((end_date - start_date).days * 252 / 365) + 1
    num_bars = max(num_bars, 100)

    logger.info(
        "Generating synthetic data: %d symbols x ~%d bars (seed=%d)",
        len(symbols), num_bars, seed,
    )

    gen = SyntheticDataGenerator(seed=seed)
    bars_by_symbol = gen.generate_universe(
        symbols=symbols,
        num_bars=num_bars,
        start_date=start_date,
    )

    # Trim to requested date range
    trimmed: dict = {}
    for sym, bars in bars_by_symbol.items():
        filtered = [b for b in bars if start_date <= b.timestamp.date() <= end_date]
        if len(filtered) >= 65:  # enough for warmup
            trimmed[sym] = filtered

    logger.info("Synthetic data ready: %d symbols with sufficient bars", len(trimmed))
    return trimmed


# ---------------------------------------------------------------------------
# Printing / formatting utilities
# ---------------------------------------------------------------------------

def _pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def _fmt(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def _print_separator(char: str = "-", width: int = 70) -> None:
    print(char * width)


def _print_portfolio_metrics(metrics: dict, title: str = "Portfolio Metrics") -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")

    rows = [
        ("Total Trades", str(metrics.get("total_trades", 0))),
        ("Winning Trades", str(metrics.get("winning_trades", 0))),
        ("Losing Trades", str(metrics.get("losing_trades", 0))),
        ("Win Rate", _pct(metrics.get("win_rate", 0.0) * 100)),
        ("Profit Factor", f"{metrics.get('profit_factor', 0.0):.3f}"),
        ("Total PnL", f"${_fmt(metrics.get('total_pnl', 0.0))}"),
        ("Total Return", _pct(metrics.get("total_return_pct", 0.0))),
        ("Annualised Return", _pct(metrics.get("annualised_return_pct", 0.0))),
        ("Avg PnL / Trade", f"${_fmt(metrics.get('avg_pnl_per_trade', 0.0))}"),
        ("Avg Win", f"${_fmt(metrics.get('avg_win', 0.0))}"),
        ("Avg Loss", f"${_fmt(metrics.get('avg_loss', 0.0))}"),
        ("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0.0):.3f}"),
        ("Sortino Ratio", f"{metrics.get('sortino_ratio', 0.0):.3f}"),
        ("Max Drawdown", _pct(metrics.get("max_drawdown_pct", 0.0))),
        ("Calmar Ratio", f"{metrics.get('calmar_ratio', 0.0):.3f}"),
        ("Final Equity", f"${_fmt(metrics.get('final_equity', 0.0))}"),
    ]

    for label, value in rows:
        print(f"  {label:<25} {value:>15}")


def _print_strategy_table(per_strategy: dict[str, dict]) -> None:
    if not per_strategy:
        print("  (no trades recorded)")
        return

    header = f"{'Strategy':<22} {'Trades':>6} {'WinRate':>8} {'TotPnL':>10} {'AvgPnL':>8} {'PF':>6} {'AvgHold':>8} {'MaxCL':>6}"
    print(f"\n  {header}")
    _print_separator()

    for strat, m in sorted(per_strategy.items()):
        if not m:
            continue
        row = (
            f"  {strat:<22}"
            f" {m.get('total_trades', 0):>6}"
            f" {m.get('win_rate', 0) * 100:>7.1f}%"
            f" {m.get('total_pnl', 0):>10.2f}"
            f" {m.get('avg_pnl', 0):>8.2f}"
            f" {m.get('profit_factor', 0):>6.2f}"
            f" {m.get('avg_hold_days', 0):>8.1f}"
            f" {m.get('max_consec_loss', 0):>6}"
        )
        print(row)


def _print_exit_reason_table(trades: list[BatchTradeRecord]) -> None:
    """Print a breakdown of exit reasons across all trades."""
    reason_counts: dict[str, int] = {}
    reason_pnl: dict[str, float] = {}
    for t in trades:
        reason_counts[t.exit_reason] = reason_counts.get(t.exit_reason, 0) + 1
        reason_pnl[t.exit_reason] = reason_pnl.get(t.exit_reason, 0.0) + t.pnl

    if not reason_counts:
        return

    print(f"\n  {'Exit Reason':<25} {'Count':>6} {'Total PnL':>12} {'Avg PnL':>10}")
    _print_separator()
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        total = reason_pnl.get(reason, 0.0)
        avg = total / count if count else 0.0
        print(f"  {reason:<25} {count:>6} {total:>12.2f} {avg:>10.2f}")


def _print_mfe_mae_table(trades: list[BatchTradeRecord]) -> None:
    """Print MFE/MAE statistics per strategy."""
    by_strat: dict[str, list[BatchTradeRecord]] = {}
    for t in trades:
        by_strat.setdefault(t.strategy, []).append(t)

    print(f"\n  {'Strategy':<22} {'AvgMFE%':>8} {'AvgMAE%':>8} {'MFE/MAE':>8} {'OptSL_ATR':>10} {'OptTP_ATR':>10}")
    _print_separator()

    for strat, strat_trades in sorted(by_strat.items()):
        if not strat_trades:
            continue
        avg_mfe = sum(t.mfe_pct for t in strat_trades) / len(strat_trades) * 100
        avg_mae = sum(t.mae_pct for t in strat_trades) / len(strat_trades) * 100
        ratio = avg_mfe / avg_mae if avg_mae > 0 else float("inf")

        # Estimate optimal SL/TP in ATR multiples
        # Use average ATR-to-price ratio to convert % to ATR multiples
        atr_pcts = [t.entry_atr / t.entry_price * 100 for t in strat_trades if t.entry_price > 0]
        avg_atr_pct = sum(atr_pcts) / len(atr_pcts) if atr_pcts else 2.0

        opt_sl = avg_mae / avg_atr_pct if avg_atr_pct > 0 else 0.0
        opt_tp = avg_mfe / avg_atr_pct if avg_atr_pct > 0 else 0.0

        print(
            f"  {strat:<22} {avg_mfe:>8.2f} {avg_mae:>8.2f} {ratio:>8.2f}"
            f" {opt_sl:>10.2f} {opt_tp:>10.2f}"
        )


def _print_comparison_table(
    results: dict[str, BatchBacktestResult],
    title: str,
) -> None:
    """Print a side-by-side comparison of multiple backtest configurations."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")

    keys = list(results.keys())
    header_row = f"  {'Metric':<28}" + "".join(f" {k:>12}" for k in keys)
    print(header_row)
    _print_separator()

    metric_rows = [
        ("Total Trades", "total_trades", str),
        ("Win Rate", "win_rate", lambda x: _pct(x * 100)),
        ("Profit Factor", "profit_factor", lambda x: f"{x:.3f}"),
        ("Total Return %", "total_return_pct", lambda x: _pct(x)),
        ("Sharpe Ratio", "sharpe_ratio", lambda x: f"{x:.3f}"),
        ("Sortino Ratio", "sortino_ratio", lambda x: f"{x:.3f}"),
        ("Max Drawdown %", "max_drawdown_pct", lambda x: _pct(x)),
        ("Calmar Ratio", "calmar_ratio", lambda x: f"{x:.3f}"),
        ("Total PnL $", "total_pnl", lambda x: f"${x:,.2f}"),
        ("Final Equity $", "final_equity", lambda x: f"${x:,.2f}"),
    ]

    for label, key, fmt in metric_rows:
        row = f"  {label:<28}"
        for k in keys:
            m = results[k].metrics
            val = m.get(key, 0.0)
            row += f" {fmt(val):>12}"
        print(row)


# ---------------------------------------------------------------------------
# Run a single backtest configuration
# ---------------------------------------------------------------------------

def run_backtest(
    bars_by_symbol: dict,
    capital: float,
    strategy_filter: list[str] | None,
    entry_day_skip: bool,
    max_hold_days_override: int | None,
    top_n: int = 12,
    gap_threshold: float = 0.03,
    label: str = "",
) -> BatchBacktestResult:
    """Run a single backtest configuration and return the result."""
    backtester = BatchBacktester(
        initial_capital=capital,
        top_n=top_n,
        max_daily_entries=3,
        max_hold_days_override=max_hold_days_override,
        gap_threshold=gap_threshold,
        entry_day_skip=entry_day_skip,
        apply_gap_filter=True,
        apply_slippage=True,
        apply_commission=True,
    )

    log_label = label or "default"
    logger.info("Running backtest: %s", log_label)
    result = backtester.run(bars_by_symbol, strategy_filter=strategy_filter)
    logger.info(
        "Completed [%s]: %d trades, return=%.1f%%, sharpe=%.2f, maxdd=%.1f%%",
        log_label,
        result.metrics.get("total_trades", 0),
        result.metrics.get("total_return_pct", 0.0),
        result.metrics.get("sharpe_ratio", 0.0),
        result.metrics.get("max_drawdown_pct", 0.0),
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch Backtest Runner for AutoTrader v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--start", default="2024-01-01",
        help="Backtest start date YYYY-MM-DD (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end", default="2025-12-31",
        help="Backtest end date YYYY-MM-DD (default: 2025-12-31)",
    )
    parser.add_argument(
        "--capital", type=float, default=100_000.0,
        help="Initial capital in USD (default: 100000)",
    )
    parser.add_argument(
        "--strategy",
        choices=["rsi_mean_reversion", "consecutive_down", "ema_pullback",
                 "volume_divergence"],
        default=None,
        help="Run a single strategy only (default: all strategies)",
    )
    parser.add_argument(
        "--compare-entry-skip", action="store_true",
        help="Compare entry day skip ON vs OFF",
    )
    parser.add_argument(
        "--compare-hold-days", action="store_true",
        help="Compare max hold days 5 vs 7 per strategy",
    )
    parser.add_argument(
        "--compare-gap-threshold", action="store_true",
        help="Compare gap filter 2%% vs 3%% vs 5%%",
    )
    parser.add_argument(
        "--full-comparison", action="store_true",
        help="Run all comparison scenarios (slower)",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Space-separated list of symbols (default: 30-stock universe)",
    )
    parser.add_argument(
        "--num-symbols", type=int, default=30,
        help="Number of symbols from default universe to use (default: 30)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for synthetic data generation (default: 42)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Save JSON results to this path",
    )
    parser.add_argument(
        "--real-data", action="store_true",
        help="Use real Alpaca historical bars instead of synthetic data",
    )
    parser.add_argument(
        "--data-days", type=int, default=365,
        help="Number of calendar days of real data to fetch (default: 365)",
    )
    parser.add_argument(
        "--refresh-data", action="store_true",
        help="Force re-download of real data (ignore cache)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable DEBUG logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as e:
        parser.error(f"Invalid date format: {e}")
        return

    if start_date >= end_date:
        parser.error("--start must be before --end")
        return

    # Load data: real Alpaca bars or synthetic generation
    if args.real_data:
        data_source = "real (Alpaca)"
        bars_by_symbol = _fetch_real_data(
            data_days=args.data_days,
            refresh=args.refresh_data,
        )
    else:
        data_source = "synthetic"
        symbols = args.symbols or _DEFAULT_SYMBOLS[: args.num_symbols]
        bars_by_symbol = _generate_synthetic_data(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            seed=args.seed,
        )

    if not bars_by_symbol:
        logger.error("No data available. Exiting.")
        sys.exit(1)

    strategy_filter = [args.strategy] if args.strategy else None

    # ---------------------------------------------------------------------------
    # Primary run
    # ---------------------------------------------------------------------------

    print(f"\n{'=' * 70}")
    print("  AUTOTRADER V2 - BATCH BACKTEST")
    print(f"  Data source: {data_source}")
    print(f"  Period: {start_date} to {end_date}")
    print(f"  Capital: ${args.capital:,.0f}")
    print(f"  Symbols: {len(bars_by_symbol)}")
    print(f"  Strategy filter: {strategy_filter or 'all'}")
    print(f"{'=' * 70}")

    primary = run_backtest(
        bars_by_symbol=bars_by_symbol,
        capital=args.capital,
        strategy_filter=strategy_filter,
        entry_day_skip=True,
        max_hold_days_override=None,
        label="primary",
    )

    # Print primary results
    _print_portfolio_metrics(primary.metrics, "Primary Run - Portfolio Metrics")

    print(f"\n{'=' * 70}")
    print("  Per-Strategy Performance")
    print(f"{'=' * 70}")
    _print_strategy_table(primary.per_strategy_metrics)

    print(f"\n{'=' * 70}")
    print("  Exit Reason Breakdown")
    print(f"{'=' * 70}")
    _print_exit_reason_table(primary.trades)

    print(f"\n{'=' * 70}")
    print("  MFE/MAE Analysis (Optimal SL/TP in ATR Multiples)")
    print(f"{'=' * 70}")
    _print_mfe_mae_table(primary.trades)

    # ---------------------------------------------------------------------------
    # Comparisons
    # ---------------------------------------------------------------------------

    do_entry_skip = args.compare_entry_skip or args.full_comparison
    do_hold_days = args.compare_hold_days or args.full_comparison
    do_gap = args.compare_gap_threshold or args.full_comparison

    if do_entry_skip:
        entry_skip_results = {
            "skip_ON": primary,
            "skip_OFF": run_backtest(
                bars_by_symbol=bars_by_symbol,
                capital=args.capital,
                strategy_filter=strategy_filter,
                entry_day_skip=False,
                max_hold_days_override=None,
                label="entry_skip_OFF",
            ),
        }
        _print_comparison_table(entry_skip_results, "Comparison: Entry Day Skip ON vs OFF")

    if do_hold_days:
        hold_day_results = {
            "hold_5d": run_backtest(
                bars_by_symbol=bars_by_symbol,
                capital=args.capital,
                strategy_filter=strategy_filter,
                entry_day_skip=True,
                max_hold_days_override=5,
                label="hold_5d",
            ),
            "hold_7d": run_backtest(
                bars_by_symbol=bars_by_symbol,
                capital=args.capital,
                strategy_filter=strategy_filter,
                entry_day_skip=True,
                max_hold_days_override=7,
                label="hold_7d",
            ),
            "hold_default": primary,
        }
        _print_comparison_table(hold_day_results, "Comparison: Max Hold Days 5d vs 7d vs Default")

    if do_gap:
        gap_results = {
            "gap_2pct": run_backtest(
                bars_by_symbol=bars_by_symbol,
                capital=args.capital,
                strategy_filter=strategy_filter,
                entry_day_skip=True,
                max_hold_days_override=None,
                gap_threshold=0.02,
                label="gap_2pct",
            ),
            "gap_3pct": primary,
            "gap_5pct": run_backtest(
                bars_by_symbol=bars_by_symbol,
                capital=args.capital,
                strategy_filter=strategy_filter,
                entry_day_skip=True,
                max_hold_days_override=None,
                gap_threshold=0.05,
                label="gap_5pct",
            ),
        }
        _print_comparison_table(gap_results, "Comparison: Gap Filter Threshold 2% vs 3% vs 5%")

    # ---------------------------------------------------------------------------
    # JSON output
    # ---------------------------------------------------------------------------

    if args.output:
        output_data = {
            "run_config": {
                "data_source": data_source,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "capital": args.capital,
                "num_symbols": len(bars_by_symbol),
                "strategy_filter": strategy_filter,
            },
            "primary_metrics": primary.metrics,
            "per_strategy_metrics": primary.per_strategy_metrics,
            "trade_count": len(primary.trades),
        }

        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str)
        logger.info("Results saved to %s", args.output)
        print(f"\n  Results saved to: {args.output}")

    print(f"\n{'=' * 70}")
    print("  Backtest complete.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
