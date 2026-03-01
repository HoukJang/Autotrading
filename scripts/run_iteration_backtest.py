"""Iteration Backtest Runner -- reusable driver for strategy optimization loop.

Runs BatchBacktester on cached historical bars, fetches S&P 500 benchmark via
yfinance for the same date range, and prints a side-by-side comparison table
with a PASS/FAIL judgment.

Success criteria:  Sharpe >= 1.0  OR  Calmar >= 1.0

Usage:
    # Single period run:
    python scripts/run_iteration_backtest.py --iteration 0 --period 2

    # Validate on both periods (out-of-sample check):
    python scripts/run_iteration_backtest.py --iteration 5 --validate-all
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import pickle
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Project root setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_iteration_backtest")

# Suppress verbose submodule logs during backtest
logging.getLogger("autotrader.batch.ranking").setLevel(logging.WARNING)
logging.getLogger("autotrader.execution.exit_rules").setLevel(logging.WARNING)
logging.getLogger("autotrader.backtest.batch_simulator").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERIOD_FILES = {
    1: os.path.join(_PROJECT_ROOT, "data", "historical_bars_period1.pkl"),
    2: os.path.join(_PROJECT_ROOT, "data", "historical_bars.pkl"),
}

_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "data", "backtest_results", "iterations")

_PASS_SHARPE = 1.0
_PASS_CALMAR = 1.0

_TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(period: int) -> dict:
    """Load cached historical bars from the pickle file for a given period.

    Returns:
        Dictionary mapping symbol -> list[Bar].
    """
    path = _PERIOD_FILES.get(period)
    if path is None:
        raise ValueError(f"Unknown period {period}. Valid periods: {list(_PERIOD_FILES.keys())}")

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            f"Run the data download script first to populate period {period} data."
        )

    logger.info("Loading bars from %s", path)
    with open(path, "rb") as f:
        cached = pickle.load(f)

    bars_by_symbol = cached.get("bars", {})
    meta_days = cached.get("_meta_days", "?")
    logger.info("Loaded %d symbols, meta_days=%s", len(bars_by_symbol), meta_days)
    return bars_by_symbol


def extract_date_range(bars_by_symbol: dict) -> tuple[date, date]:
    """Determine the earliest and latest bar dates across all symbols."""
    all_dates: list[date] = []
    for bars in bars_by_symbol.values():
        for bar in bars:
            d = bar.date if hasattr(bar, "date") else bar.timestamp.date()
            all_dates.append(d)

    if not all_dates:
        raise ValueError("No bar data found -- cannot determine date range.")

    return min(all_dates), max(all_dates)


# ---------------------------------------------------------------------------
# Backtest execution
# ---------------------------------------------------------------------------

def run_backtest(bars_by_symbol: dict, capital: float = 100_000.0) -> Any:
    """Execute a single BatchBacktester run and return the result."""
    from autotrader.backtest.batch_simulator import BatchBacktester

    bt = BatchBacktester(
        initial_capital=capital,
        use_per_strategy_gdr=True,
    )

    t0 = time.time()
    result = bt.run(bars_by_symbol)
    elapsed = time.time() - t0

    n_trades = result.metrics.get("total_trades", 0)
    logger.info("Backtest completed in %.1fs -- %d trades", elapsed, n_trades)
    return result


# ---------------------------------------------------------------------------
# S&P 500 benchmark
# ---------------------------------------------------------------------------

def fetch_sp500_benchmark(start: date, end: date) -> dict:
    """Fetch S&P 500 data via yfinance and compute benchmark metrics.

    Returns a dict with: total_return_pct, max_drawdown_pct, sharpe_ratio,
    calmar_ratio, annualised_return_pct.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed -- skipping S&P 500 benchmark.")
        return _empty_benchmark("yfinance not installed")

    # Extend end by 1 day because yf.download end is exclusive
    end_dl = end + timedelta(days=1)
    logger.info("Fetching S&P 500 (^GSPC) from %s to %s", start, end_dl)

    try:
        df = yf.download("^GSPC", start=str(start), end=str(end_dl), progress=False)
    except Exception as exc:
        logger.warning("yfinance download failed: %s", exc)
        return _empty_benchmark(f"download error: {exc}")

    if df is None or df.empty:
        logger.warning("No S&P 500 data returned for the requested range.")
        return _empty_benchmark("no data")

    # Handle MultiIndex columns from yfinance
    close_col = df["Close"]
    if hasattr(close_col, "columns"):
        # MultiIndex: take the first (and only) ticker column
        close_col = close_col.iloc[:, 0]

    closes = close_col.dropna().values.tolist()

    if len(closes) < 2:
        return _empty_benchmark("insufficient data points")

    # Total return
    total_return_pct = (closes[-1] / closes[0] - 1.0) * 100.0

    # Daily returns
    daily_returns = []
    for i in range(1, len(closes)):
        daily_returns.append(closes[i] / closes[i - 1] - 1.0)

    # Annualised return
    n_days = len(daily_returns)
    years = n_days / _TRADING_DAYS_PER_YEAR
    if years > 0 and closes[-1] > 0 and closes[0] > 0:
        annualised_return_pct = ((closes[-1] / closes[0]) ** (1.0 / years) - 1.0) * 100.0
    else:
        annualised_return_pct = 0.0

    # Sharpe ratio (annualised, risk-free = 0)
    if daily_returns:
        mean_r = sum(daily_returns) / len(daily_returns)
        var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0
        sharpe = (mean_r / std_r * math.sqrt(_TRADING_DAYS_PER_YEAR)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = max_dd * 100.0

    # Calmar ratio
    calmar = (annualised_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "annualised_return_pct": round(annualised_return_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_ratio": round(sharpe, 3),
        "calmar_ratio": round(calmar, 3),
        "trading_days": n_days,
        "error": None,
    }


def _empty_benchmark(reason: str) -> dict:
    """Return a benchmark dict with zeroed metrics when data is unavailable."""
    return {
        "total_return_pct": 0.0,
        "annualised_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "calmar_ratio": 0.0,
        "trading_days": 0,
        "error": reason,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_comparison_table(
    iteration: int,
    period: int,
    strategy_metrics: dict,
    benchmark: dict,
    start_date: date,
    end_date: date,
) -> None:
    """Print a side-by-side comparison table: Strategy vs S&P 500."""
    m = strategy_metrics

    header = f"  Iteration {iteration} | Period {period} | {start_date} to {end_date}"
    print(f"\n{'=' * 75}")
    print(header)
    print(f"{'=' * 75}")

    row_fmt = "  {metric:<25} {strategy:>15} {benchmark:>15}"
    print(row_fmt.format(metric="Metric", strategy="Strategy", benchmark="S&P 500"))
    print(f"  {'-' * 25} {'-' * 15} {'-' * 15}")

    def _fmt(val, fmt_str=".2f", suffix=""):
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        return f"{val:{fmt_str}}{suffix}"

    rows = [
        ("Total Return", _fmt(m.get("total_return_pct"), "+.1f", "%"), _fmt(benchmark["total_return_pct"], "+.1f", "%")),
        ("Annualised Return", _fmt(m.get("annualised_return_pct"), "+.1f", "%"), _fmt(benchmark["annualised_return_pct"], "+.1f", "%")),
        ("Max Drawdown", _fmt(m.get("max_drawdown_pct"), ".1f", "%"), _fmt(benchmark["max_drawdown_pct"], ".1f", "%")),
        ("Sharpe Ratio", _fmt(m.get("sharpe_ratio"), ".3f"), _fmt(benchmark["sharpe_ratio"], ".3f")),
        ("Calmar Ratio", _fmt(m.get("calmar_ratio"), ".3f"), _fmt(benchmark["calmar_ratio"], ".3f")),
        ("Sortino Ratio", _fmt(m.get("sortino_ratio"), ".3f"), "---"),
        ("Profit Factor", _fmt(m.get("profit_factor"), ".3f"), "---"),
        ("Win Rate", _fmt(m.get("win_rate", 0) * 100 if m.get("win_rate") is not None else None, ".1f", "%"), "---"),
        ("Total Trades", str(m.get("total_trades", 0)), "---"),
        ("Final Equity", f"${m.get('final_equity', 0):,.2f}", "---"),
    ]

    for metric_name, strat_val, bench_val in rows:
        print(row_fmt.format(metric=metric_name, strategy=strat_val, benchmark=bench_val))

    if benchmark.get("error"):
        print(f"\n  [!] Benchmark note: {benchmark['error']}")


def print_per_strategy_metrics(per_strategy: dict) -> None:
    """Print per-strategy breakdown table."""
    if not per_strategy:
        return

    print(f"\n  {'--- Per-Strategy Breakdown ---':^75}")
    hdr = "  {name:<22} {trades:>7} {wr:>7} {pf:>8} {pnl:>12} {hold:>8} {mcl:>5}"
    print(hdr.format(name="Strategy", trades="Trades", wr="WR", pf="PF", pnl="PnL", hold="AvgHold", mcl="MCL"))
    print(f"  {'-' * 22} {'-' * 7} {'-' * 7} {'-' * 8} {'-' * 12} {'-' * 8} {'-' * 5}")

    for strat_name, sm in sorted(per_strategy.items()):
        wr_str = f"{sm.get('win_rate', 0):.1%}"
        pf_str = f"{sm.get('profit_factor', 0):.3f}"
        pnl_str = f"${sm.get('total_pnl', 0):,.2f}"
        hold_str = f"{sm.get('avg_hold_days', 0):.1f}d"
        mcl_str = str(sm.get("max_consec_loss", 0))

        print(hdr.format(
            name=strat_name,
            trades=sm.get("total_trades", 0),
            wr=wr_str,
            pf=pf_str,
            pnl=pnl_str,
            hold=hold_str,
            mcl=mcl_str,
        ))

        # Exit reasons
        exit_reasons = sm.get("exit_reasons", {})
        if exit_reasons:
            reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(exit_reasons.items()))
            print(f"    Exits: {reasons_str}")


def print_judgment(strategy_metrics: dict) -> bool:
    """Print PASS/FAIL based on success criteria. Returns True if passed."""
    sharpe = strategy_metrics.get("sharpe_ratio", 0) or 0
    calmar = strategy_metrics.get("calmar_ratio", 0) or 0

    passed = sharpe >= _PASS_SHARPE or calmar >= _PASS_CALMAR

    print(f"\n  {'=' * 50}")
    if passed:
        print(f"  RESULT: PASS")
    else:
        print(f"  RESULT: FAIL")
    print(f"  {'=' * 50}")
    print(f"  Criteria:  Sharpe >= {_PASS_SHARPE}  OR  Calmar >= {_PASS_CALMAR}")
    print(f"  Achieved:  Sharpe = {sharpe:.3f}  |  Calmar = {calmar:.3f}")

    if not passed:
        sharpe_gap = max(0, _PASS_SHARPE - sharpe)
        calmar_gap = max(0, _PASS_CALMAR - calmar)
        print(f"  Gap:       Sharpe needs +{sharpe_gap:.3f}  |  Calmar needs +{calmar_gap:.3f}")

    return passed


# ---------------------------------------------------------------------------
# Result serialisation
# ---------------------------------------------------------------------------

def build_result_json(
    iteration: int,
    period: int,
    result: Any,
    benchmark: dict,
    start_date: date,
    end_date: date,
    passed: bool,
    elapsed_sec: float,
) -> dict:
    """Build the full JSON-serialisable result dictionary."""
    trades_list = []
    for t in result.trades:
        trades_list.append({
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "strategy": t.strategy,
            "direction": t.direction,
            "entry_date": str(t.entry_date),
            "exit_date": str(t.exit_date),
            "entry_price": round(t.entry_price, 4),
            "exit_price": round(t.exit_price, 4),
            "qty": t.qty,
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct, 6),
            "bars_held": t.bars_held,
            "exit_reason": t.exit_reason,
            "mfe_pct": round(t.mfe_pct, 6),
            "mae_pct": round(t.mae_pct, 6),
            "entry_atr": round(t.entry_atr, 4),
            "signal_strength": round(t.signal_strength, 4),
            "gap_pct": round(t.gap_pct, 6),
        })

    return {
        "iteration": iteration,
        "period": period,
        "date_range": {
            "start": str(start_date),
            "end": str(end_date),
        },
        "passed": passed,
        "pass_criteria": {
            "sharpe_threshold": _PASS_SHARPE,
            "calmar_threshold": _PASS_CALMAR,
            "logic": "sharpe >= threshold OR calmar >= threshold",
        },
        "strategy_metrics": result.metrics,
        "per_strategy_metrics": result.per_strategy_metrics,
        "benchmark_sp500": benchmark,
        "config": result.config,
        "elapsed_sec": round(elapsed_sec, 1),
        "equity_curve": [(str(d), round(e, 2)) for d, e in result.equity_curve],
        "trades": trades_list,
    }


def save_result(data: dict, iteration: int, period: int) -> str:
    """Save result JSON to the iterations directory. Returns the file path."""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    filename = f"iter_{iteration:02d}_period{period}.json"
    filepath = os.path.join(_OUTPUT_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info("Saved result: %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Single iteration run
# ---------------------------------------------------------------------------

def run_single_period(
    iteration: int,
    period: int,
    capital: float = 100_000.0,
) -> tuple[bool, str]:
    """Run backtest for one iteration/period combo.

    Returns:
        (passed, filepath) -- whether it met success criteria, and the output path.
    """
    print(f"\n{'#' * 75}")
    print(f"  ITERATION {iteration} -- PERIOD {period}")
    print(f"{'#' * 75}")

    # 1. Load data
    bars_by_symbol = load_bars(period)

    # 2. Determine date range
    start_date, end_date = extract_date_range(bars_by_symbol)
    logger.info("Date range: %s to %s", start_date, end_date)

    # 3. Run backtest
    t0 = time.time()
    result = run_backtest(bars_by_symbol, capital)
    elapsed = time.time() - t0

    # 4. Fetch S&P 500 benchmark
    benchmark = fetch_sp500_benchmark(start_date, end_date)

    # 5. Print comparison table
    print_comparison_table(iteration, period, result.metrics, benchmark, start_date, end_date)

    # 6. Print per-strategy breakdown
    print_per_strategy_metrics(result.per_strategy_metrics)

    # 7. Print PASS/FAIL judgment
    passed = print_judgment(result.metrics)

    # 8. Build and save JSON
    data = build_result_json(
        iteration=iteration,
        period=period,
        result=result,
        benchmark=benchmark,
        start_date=start_date,
        end_date=end_date,
        passed=passed,
        elapsed_sec=elapsed,
    )
    filepath = save_result(data, iteration, period)

    return passed, filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Iteration Backtest Runner -- strategy optimization loop driver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_iteration_backtest.py --iteration 0 --period 2
  python scripts/run_iteration_backtest.py --iteration 5 --validate-all
  python scripts/run_iteration_backtest.py --iteration 3 --period 1 --capital 50000
        """,
    )
    parser.add_argument(
        "--iteration", "-i",
        type=int,
        required=True,
        help="Iteration number (0, 1, 2, ...). Used in output filename.",
    )
    parser.add_argument(
        "--period", "-p",
        type=int,
        choices=[1, 2],
        default=None,
        help="Data period to test on (1 or 2). Required unless --validate-all.",
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        default=False,
        help="Run on both period 1 and period 2 (out-of-sample validation).",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100_000.0,
        help="Initial capital for the backtest (default: 100000).",
    )

    args = parser.parse_args()

    # Validation: need either --period or --validate-all
    if not args.validate_all and args.period is None:
        parser.error("Either --period or --validate-all is required.")

    return args


def main() -> None:
    args = parse_args()

    print("=" * 75)
    print("  Iteration Backtest Runner")
    print(f"  Iteration: {args.iteration}  |  Capital: ${args.capital:,.0f}")
    if args.validate_all:
        print("  Mode: validate-all (period 1 + period 2)")
    else:
        print(f"  Mode: single period ({args.period})")
    print("=" * 75)

    results: list[tuple[int, bool, str]] = []

    if args.validate_all:
        periods_to_run = [1, 2]
    else:
        periods_to_run = [args.period]

    all_passed = True
    for period in periods_to_run:
        try:
            passed, filepath = run_single_period(
                iteration=args.iteration,
                period=period,
                capital=args.capital,
            )
            results.append((period, passed, filepath))
            if not passed:
                all_passed = False
        except FileNotFoundError as exc:
            logger.error("Skipping period %d: %s", period, exc)
            results.append((period, False, "SKIPPED"))
            all_passed = False
        except Exception as exc:
            logger.exception("Period %d failed with error: %s", period, exc)
            results.append((period, False, "ERROR"))
            all_passed = False

    # Final summary for validate-all
    if args.validate_all:
        print(f"\n\n{'=' * 75}")
        print("  VALIDATION SUMMARY (ALL PERIODS)")
        print(f"{'=' * 75}")
        for period, passed, filepath in results:
            status = "PASS" if passed else "FAIL"
            if filepath in ("SKIPPED", "ERROR"):
                status = filepath
            print(f"  Period {period}: {status}  ->  {filepath}")

        print(f"\n  Overall: {'PASS' if all_passed else 'FAIL'}")
        print(f"{'=' * 75}")

    # Exit code: 0 if all passed, 1 otherwise
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
