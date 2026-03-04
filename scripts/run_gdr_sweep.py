"""GDR Tier 0 Parameter Sweep -- find optimal per-strategy daily entry limit.

Runs BatchBacktester with _GDR_STRATEGY_ENTRIES[0] = 1..10,
compares total return, drawdown, trade count, and capital efficiency.

Usage:
    python scripts/run_gdr_sweep.py
    python scripts/run_gdr_sweep.py --period 1
    python scripts/run_gdr_sweep.py --validate-all
"""
from __future__ import annotations

import logging
import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gdr_sweep")

# Suppress verbose sub-module logs
logging.getLogger("autotrader.batch.ranking").setLevel(logging.WARNING)
logging.getLogger("autotrader.execution.exit_rules").setLevel(logging.WARNING)
logging.getLogger("autotrader.backtest.batch_simulator").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)

from scripts.run_iteration_backtest import (
    load_bars,
    extract_date_range,
    load_spy_bars,
    fetch_sp500_benchmark,
    _PERIOD_START,
    _PERIOD_END,
)


def run_sweep(period: int = 2, capital: float = 100_000.0) -> list[dict]:
    """Run backtest for GDR Tier 0 values 1 through 10.

    Returns list of result dicts with key metrics for comparison.
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.backtest.batch_simulator import BatchBacktester

    # Load data once
    bars_by_symbol = load_bars(period)
    data_start, data_end = extract_date_range(bars_by_symbol)
    trade_start_date = _PERIOD_START.get(period)
    period_end = _PERIOD_END.get(period, data_end)
    spy_bars = load_spy_bars(data_start, data_end)

    # Fetch benchmark once
    benchmark = fetch_sp500_benchmark(trade_start_date or data_start, period_end)
    sp500_return = benchmark.get("total_return_pct", 0)

    print(f"\n{'=' * 90}")
    print(f"  GDR TIER 0 PARAMETER SWEEP | Period {period} | {trade_start_date} to {period_end}")
    print(f"  S&P 500 benchmark: {sp500_return:+.2f}%")
    print(f"{'=' * 90}\n")

    # Save originals
    orig_gdr = dict(bs._GDR_STRATEGY_ENTRIES)
    orig_max_daily = bs._MAX_DAILY_ENTRIES

    results = []

    for tier0_limit in range(1, 11):
        # Monkey-patch GDR Tier 0 entry limit
        bs._GDR_STRATEGY_ENTRIES = {0: tier0_limit, 1: 1, 2: 0}
        # Scale MAX_DAILY_ENTRIES so it doesn't bottleneck
        # 2 strategies * tier0_limit, minimum 3
        bs._MAX_DAILY_ENTRIES = max(3, tier0_limit * 2)

        logger.info(
            "--- Tier0=%d  MAX_DAILY=%d ---",
            tier0_limit, bs._MAX_DAILY_ENTRIES,
        )

        t0 = time.time()
        bt = BatchBacktester(initial_capital=capital, use_per_strategy_gdr=True)
        result = bt.run(
            bars_by_symbol,
            spy_bars=spy_bars,
            trade_start_date=trade_start_date,
        )
        elapsed = time.time() - t0

        m = result.metrics
        per_strat = result.per_strategy_metrics

        # Compute capital efficiency (ROIC proxy)
        avg_deployed = m.get("avg_capital_deployed_pct", None)
        total_return = m.get("total_return_pct", 0) or 0

        # Per-strategy trade counts
        bm_trades = per_strat.get("breakout_momentum", {}).get("total_trades", 0)
        mr_trades = per_strat.get("rsi_mean_reversion", {}).get("total_trades", 0)
        bm_pnl = per_strat.get("breakout_momentum", {}).get("total_pnl", 0)
        mr_pnl = per_strat.get("rsi_mean_reversion", {}).get("total_pnl", 0)

        row = {
            "tier0": tier0_limit,
            "max_daily": bs._MAX_DAILY_ENTRIES,
            "total_return_pct": total_return,
            "max_dd_pct": m.get("max_drawdown_pct", 0) or 0,
            "sharpe": m.get("sharpe_ratio", 0) or 0,
            "calmar": m.get("calmar_ratio", 0) or 0,
            "profit_factor": m.get("profit_factor", 0) or 0,
            "win_rate": (m.get("win_rate", 0) or 0) * 100,
            "total_trades": m.get("total_trades", 0),
            "bm_trades": bm_trades,
            "mr_trades": mr_trades,
            "bm_pnl": bm_pnl,
            "mr_pnl": mr_pnl,
            "final_equity": m.get("final_equity", capital),
            "avg_deployed_pct": avg_deployed,
            "elapsed": round(elapsed, 1),
        }
        results.append(row)

        # Progress print
        alpha = total_return - sp500_return
        print(
            f"  Tier0={tier0_limit:2d} | "
            f"Return: {total_return:+7.2f}% | "
            f"MaxDD: {row['max_dd_pct']:5.1f}% | "
            f"Sharpe: {row['sharpe']:5.3f} | "
            f"PF: {row['profit_factor']:5.3f} | "
            f"Trades: {row['total_trades']:3d} (BM:{bm_trades} MR:{mr_trades}) | "
            f"Alpha: {alpha:+.2f}% | "
            f"{elapsed:.0f}s"
        )

    # Restore originals
    bs._GDR_STRATEGY_ENTRIES = orig_gdr
    bs._MAX_DAILY_ENTRIES = orig_max_daily

    return results, sp500_return


def print_summary(results: list[dict], sp500_return: float) -> None:
    """Print a comparison summary table and highlight the best config."""
    print(f"\n\n{'=' * 110}")
    print(f"  SUMMARY TABLE")
    print(f"{'=' * 110}")

    hdr = (
        f"  {'Tier0':>5} | {'Return':>8} | {'Alpha':>7} | "
        f"{'MaxDD':>6} | {'Sharpe':>6} | {'Calmar':>6} | "
        f"{'PF':>6} | {'WR':>5} | {'Trades':>6} | "
        f"{'BM':>4} | {'MR':>4} | {'BM PnL':>10} | {'MR PnL':>10}"
    )
    print(hdr)
    print(f"  {'-' * 5}-+-{'-' * 8}-+-{'-' * 7}-+-"
          f"{'-' * 6}-+-{'-' * 6}-+-{'-' * 6}-+-"
          f"{'-' * 6}-+-{'-' * 5}-+-{'-' * 6}-+-"
          f"{'-' * 4}-+-{'-' * 4}-+-{'-' * 10}-+-{'-' * 10}")

    best_return = max(results, key=lambda r: r["total_return_pct"])
    best_sharpe = max(results, key=lambda r: r["sharpe"])
    best_calmar = max(results, key=lambda r: r["calmar"])

    for r in results:
        alpha = r["total_return_pct"] - sp500_return
        marker = ""
        if r is best_return:
            marker = " <-- BEST RETURN"
        elif r is best_sharpe:
            marker = " <-- BEST SHARPE"

        print(
            f"  {r['tier0']:>5} | "
            f"{r['total_return_pct']:>+7.2f}% | "
            f"{alpha:>+6.2f}% | "
            f"{r['max_dd_pct']:>5.1f}% | "
            f"{r['sharpe']:>6.3f} | "
            f"{r['calmar']:>6.3f} | "
            f"{r['profit_factor']:>6.3f} | "
            f"{r['win_rate']:>4.1f}% | "
            f"{r['total_trades']:>6} | "
            f"{r['bm_trades']:>4} | "
            f"{r['mr_trades']:>4} | "
            f"${r['bm_pnl']:>+9,.0f} | "
            f"${r['mr_pnl']:>+9,.0f}"
            f"{marker}"
        )

    # Highlight winners
    print(f"\n  {'--- WINNERS ---':^110}")
    print(f"  Best Return:  Tier0={best_return['tier0']}  ({best_return['total_return_pct']:+.2f}%)")
    print(f"  Best Sharpe:  Tier0={best_sharpe['tier0']}  ({best_sharpe['sharpe']:.3f})")
    print(f"  Best Calmar:  Tier0={best_calmar['tier0']}  ({best_calmar['calmar']:.3f})")

    # Recommendation based on risk-adjusted return
    # Score = return * 0.4 + sharpe * 30 + calmar * 10 - maxDD * 0.5
    for r in results:
        r["score"] = (
            r["total_return_pct"] * 0.4
            + r["sharpe"] * 30
            + r["calmar"] * 10
            - r["max_dd_pct"] * 0.5
        )
    best_overall = max(results, key=lambda r: r["score"])
    print(f"\n  Recommended (composite score): Tier0={best_overall['tier0']}  "
          f"(return={best_overall['total_return_pct']:+.2f}%, "
          f"sharpe={best_overall['sharpe']:.3f}, "
          f"maxDD={best_overall['max_dd_pct']:.1f}%)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GDR Tier 0 Parameter Sweep")
    parser.add_argument("--period", "-p", type=int, default=2, choices=[1, 2],
                        help="Data period (default: 2)")
    parser.add_argument("--validate-all", action="store_true",
                        help="Run on both periods")
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()

    if args.validate_all:
        for period in [1, 2]:
            results, sp500_return = run_sweep(period, args.capital)
            print_summary(results, sp500_return)
    else:
        results, sp500_return = run_sweep(args.period, args.capital)
        print_summary(results, sp500_return)


if __name__ == "__main__":
    main()
