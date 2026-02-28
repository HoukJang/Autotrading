"""13th Backtest Series Runner: 13A (vol_div removal), 13B (safety net), 13C (rsi_mr risk).

Runs four backtest configurations programmatically by monkey-patching module
constants in batch_simulator before instantiating BatchBacktester.

Configurations:
  12A (baseline): Restore original 12A defaults for comparison.
  13A: Remove VolumeDivergence (now the permanent default).
  13B: 13A + widened portfolio safety net (DD 20%->25%, recovery 15%->18%).
  13C: 13B + reduced rsi_mr risk (base 1%->0.75%, thresholds tightened).

Usage:
    python scripts/run_13th_backtest.py
    python scripts/run_13th_backtest.py --only-13a
    python scripts/run_13th_backtest.py --skip-baseline
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# Ensure project root is on path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_13th_backtest")

# Suppress verbose logs
logging.getLogger("autotrader.batch.ranking").setLevel(logging.WARNING)
logging.getLogger("autotrader.execution.exit_rules").setLevel(logging.WARNING)
logging.getLogger("autotrader.backtest.batch_simulator").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_CACHE_PATH = os.path.join(_PROJECT_ROOT, "data", "historical_bars.pkl")
_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "data", "backtest_results")


def load_data() -> dict:
    """Load cached real data from Alpaca, or generate synthetic if unavailable."""
    if os.path.exists(_CACHE_PATH):
        logger.info("Loading cached historical bars from %s", _CACHE_PATH)
        with open(_CACHE_PATH, "rb") as f:
            cached = pickle.load(f)
        bars_by_symbol = cached.get("bars", {})
        logger.info("Loaded %d symbols from cache", len(bars_by_symbol))
        return bars_by_symbol

    # No cache -- generate synthetic data
    logger.warning("Cache not found at %s, generating synthetic data", _CACHE_PATH)
    from autotrader.backtest.batch_simulator import SyntheticDataGenerator

    gen = SyntheticDataGenerator(seed=42)
    symbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "META", "TSLA", "JPM", "V", "UNH",
        "JNJ", "WMT", "PG", "MA", "HD",
        "DIS", "BAC", "ADBE", "CRM", "NFLX",
    ]
    bars_by_symbol = gen.generate_universe(symbols, num_bars=504)
    logger.info("Generated synthetic data for %d symbols (504 bars each)", len(symbols))
    return bars_by_symbol


# ---------------------------------------------------------------------------
# Monkey-patch helpers
# ---------------------------------------------------------------------------

def _patch_for_12a_baseline():
    """Restore 12A baseline: per-strategy GDR with vol_div included.

    This re-adds VolumeDivergence temporarily for the baseline comparison.
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.volume_divergence import VolumeDivergence
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown, VolumeDivergence]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down", "volume_divergence"})
    bs._STRATEGY_BASE_RISK = {
        "rsi_mean_reversion": 0.01,
        "consecutive_down": 0.02,
        "volume_divergence": 0.02,
    }
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.03, 0.06),
        "consecutive_down": (0.04, 0.08),
        "volume_divergence": (0.04, 0.08),
    }
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down", "volume_divergence"]
    bs._PER_STRATEGY_GDR = True
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3

    logger.info("Patched for 12A baseline: 3 strategies, per-strategy GDR, safety net 20%%/15%%")


def _patch_for_13a():
    """Patch for 13A: vol_div removal only (matches the new permanent defaults).

    Since vol_div has been permanently removed from the module, this just
    restores the current defaults to ensure a clean state.
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down"})
    bs._STRATEGY_BASE_RISK = {
        "rsi_mean_reversion": 0.01,
        "consecutive_down": 0.02,
    }
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.03, 0.06),
        "consecutive_down": (0.04, 0.08),
    }
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down"]
    bs._PER_STRATEGY_GDR = True
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3

    logger.info("Patched for 13A: 2 strategies (vol_div removed), per-strategy GDR")


def _patch_for_13b():
    """Patch for 13B: 13A + widened safety net thresholds.

    Changes from 13A:
    - _PORTFOLIO_SAFETY_NET_DD: 0.20 -> 0.25
    - _PORTFOLIO_SAFETY_NET_RECOVERY: 0.15 -> 0.18
    """
    _patch_for_13a()  # Start from 13A base

    import autotrader.backtest.batch_simulator as bs

    bs._PORTFOLIO_SAFETY_NET_DD = 0.25
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.18

    logger.info("Patched for 13B: 13A + safety net DD=25%%, recovery=18%%")


def _patch_for_13c():
    """Patch for 13C: 13B + reduced rsi_mr risk.

    Changes from 13B:
    - rsi_mean_reversion base risk: 0.01 -> 0.0075
    - rsi_mean_reversion GDR thresholds: (0.03, 0.06) -> (0.02, 0.04)
      (proportionally tighter since base risk is smaller)
    """
    _patch_for_13b()  # Start from 13B base

    import autotrader.backtest.batch_simulator as bs

    bs._STRATEGY_BASE_RISK["rsi_mean_reversion"] = 0.0075
    bs._STRATEGY_GDR_THRESHOLDS["rsi_mean_reversion"] = (0.02, 0.04)

    logger.info(
        "Patched for 13C: 13B + rsi_mr base_risk=0.75%%, GDR thresholds=(2%%/4%%)"
    )


# ---------------------------------------------------------------------------
# Single backtest run
# ---------------------------------------------------------------------------

def run_single(
    bars_by_symbol: dict,
    capital: float,
    label: str,
) -> "BatchBacktestResult":
    """Run a single backtest and return the result."""
    from autotrader.backtest.batch_simulator import BatchBacktester

    bt = BatchBacktester(
        initial_capital=capital,
        top_n=12,
        max_daily_entries=3,
        max_hold_days_override=None,
        gap_threshold=0.05,
        entry_day_skip=True,
        apply_gap_filter=True,
        apply_slippage=True,
        apply_commission=True,
        use_per_strategy_gdr=True,
    )

    logger.info("Running: %s", label)
    t0 = time.time()
    result = bt.run(bars_by_symbol)
    elapsed = time.time() - t0
    m = result.metrics
    logger.info(
        "  [%s] done in %.1fs: %d trades, ret=%.1f%%, PF=%.3f, DD=%.1f%%, sharpe=%.3f",
        label, elapsed,
        m.get("total_trades", 0),
        m.get("total_return_pct", 0.0),
        m.get("profit_factor", 0.0),
        m.get("max_drawdown_pct", 0.0),
        m.get("sharpe_ratio", 0.0),
    )
    return result


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _extract_strategy_metrics(result: "BatchBacktestResult") -> dict:
    """Extract per-strategy metrics summary."""
    ps = result.per_strategy_metrics
    summary = {}
    for strat, m in ps.items():
        summary[strat] = {
            "trades": m.get("total_trades", 0),
            "win_rate": m.get("win_rate", 0) * 100,
            "pnl": m.get("total_pnl", 0),
            "pf": m.get("profit_factor", 0),
            "avg_hold": m.get("avg_hold_days", 0),
            "max_cl": m.get("max_consec_loss", 0),
        }
    return summary


def _extract_exit_reasons(result: "BatchBacktestResult") -> dict:
    """Extract exit reason distribution."""
    counts = defaultdict(int)
    pnls = defaultdict(float)
    for t in result.trades:
        counts[t.exit_reason] += 1
        pnls[t.exit_reason] += t.pnl
    return {
        reason: {"count": counts[reason], "pnl": pnls[reason]}
        for reason in sorted(counts.keys(), key=lambda r: -counts[r])
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _result_to_json(result: "BatchBacktestResult", label: str) -> dict:
    """Convert a BatchBacktestResult to a JSON-serializable dict."""
    return {
        "label": label,
        "metrics": result.metrics,
        "per_strategy_metrics": result.per_strategy_metrics,
        "config": result.config,
        "trade_count": len(result.trades),
    }


def _save_result(result: "BatchBacktestResult", label: str, filename: str) -> str:
    """Save result to JSON file."""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(_OUTPUT_DIR, filename)
    data = _result_to_json(result, label)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Saved: %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Report / comparison table
# ---------------------------------------------------------------------------

def _pct(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}%"


def _fmt(v: float, d: int = 2) -> str:
    return f"{v:,.{d}f}"


def print_comparison_table(results: dict[str, Any]) -> None:
    """Print a comparison table of all configurations to stdout."""
    print("\n" + "=" * 100)
    print("  13th Backtest Comparison Table")
    print("=" * 100)

    # Header
    header = f"{'Config':<16} {'Trades':>7} {'Return':>9} {'PF':>7} {'MaxDD':>8} {'Sharpe':>8} {'Sortino':>8} {'Final Eq':>12}"
    print(header)
    print("-" * 100)

    for label, result in results.items():
        m = result.metrics
        print(
            f"{label:<16} "
            f"{m.get('total_trades', 0):>7} "
            f"{_pct(m.get('total_return_pct', 0)):>9} "
            f"{m.get('profit_factor', 0):>7.3f} "
            f"{_pct(m.get('max_drawdown_pct', 0)):>8} "
            f"{m.get('sharpe_ratio', 0):>8.3f} "
            f"{m.get('sortino_ratio', 0):>8.3f} "
            f"${_fmt(m.get('final_equity', 0)):>11}"
        )

    print("-" * 100)

    # Per-strategy breakdown
    print("\n  Per-Strategy Breakdown:")
    print("-" * 100)
    for label, result in results.items():
        ps = _extract_strategy_metrics(result)
        print(f"\n  [{label}]")
        for strat, sm in sorted(ps.items()):
            print(
                f"    {strat:<25} "
                f"trades={sm['trades']:>4}  "
                f"WR={sm['win_rate']:>5.1f}%  "
                f"PnL=${sm['pnl']:>10,.2f}  "
                f"PF={sm['pf']:>6.2f}  "
                f"hold={sm['avg_hold']:.1f}d  "
                f"maxCL={sm['max_cl']}"
            )

    print("\n" + "=" * 100)


def generate_report(results: dict[str, Any]) -> str:
    """Generate the 13th backtest report in Markdown."""
    lines = []
    L = lines.append

    L("# 13th Backtest Report")
    L("")
    L(f"**Date**: {date.today()}")
    L("**Data**: Real Alpaca data (S&P 500, cached) or synthetic fallback")
    L("**Capital**: $100,000 initial")
    L("")
    L("---")
    L("")

    # Configuration descriptions
    L("## Configurations")
    L("")
    L("| Config | Description |")
    L("|--------|-------------|")
    L("| 12A (baseline) | 3 strategies (incl vol_div), per-strategy GDR, safety net 20%/15% |")
    L("| 13A | 2 strategies (vol_div removed), per-strategy GDR, safety net 20%/15% |")
    L("| 13B | 13A + safety net widened (25%/18%) |")
    L("| 13C | 13B + rsi_mr risk reduced (0.75%, GDR 2%/4%) |")
    L("")

    # Main comparison table
    L("## Portfolio Metrics Comparison")
    L("")
    L("| Metric | 12A (baseline) | 13A | 13B | 13C |")
    L("|--------|:--------------:|:---:|:---:|:---:|")

    configs = ["12A (baseline)", "13A", "13B", "13C"]
    metric_rows = [
        ("Trades", "total_trades", "{:.0f}"),
        ("Return", "total_return_pct", "{:.1f}%"),
        ("Profit Factor", "profit_factor", "{:.3f}"),
        ("Max Drawdown", "max_drawdown_pct", "{:.1f}%"),
        ("Sharpe", "sharpe_ratio", "{:.3f}"),
        ("Sortino", "sortino_ratio", "{:.3f}"),
        ("Calmar", "calmar_ratio", "{:.3f}"),
        ("Final Equity", "final_equity", "${:,.2f}"),
        ("Win Rate", "win_rate", "{:.1%}"),
        ("Avg PnL/Trade", "avg_pnl_per_trade", "${:,.2f}"),
    ]

    for metric_name, metric_key, fmt_str in metric_rows:
        vals = []
        for cfg in configs:
            r = results.get(cfg)
            if r is None:
                vals.append("N/A")
            else:
                v = r.metrics.get(metric_key, 0)
                vals.append(fmt_str.format(v))
        L(f"| {metric_name} | {' | '.join(vals)} |")

    L("")

    # Per-strategy breakdown per config
    for cfg in configs:
        r = results.get(cfg)
        if r is None:
            continue
        L(f"### {cfg} Per-Strategy")
        L("")
        L("| Strategy | Trades | WR | PnL | PF | Avg Hold | MaxCL |")
        L("|----------|-------:|---:|----:|---:|---------:|------:|")
        ps = _extract_strategy_metrics(r)
        for strat, sm in sorted(ps.items()):
            L(f"| {strat} | {sm['trades']} | {sm['win_rate']:.1f}% | ${sm['pnl']:,.2f} | {sm['pf']:.2f} | {sm['avg_hold']:.1f}d | {sm['max_cl']} |")
        L("")

    # Exit reasons
    L("## Exit Reason Comparison")
    L("")
    for cfg in configs:
        r = results.get(cfg)
        if r is None:
            continue
        L(f"### {cfg}")
        L("")
        L("| Exit Reason | Count | Total PnL | Avg PnL |")
        L("|-------------|------:|----------:|--------:|")
        exits = _extract_exit_reasons(r)
        for reason, data in exits.items():
            avg = data["pnl"] / data["count"] if data["count"] else 0
            L(f"| {reason} | {data['count']} | ${data['pnl']:,.2f} | ${avg:,.2f} |")
        L("")

    # Delta analysis
    L("## Delta Analysis (vs 12A Baseline)")
    L("")

    baseline = results.get("12A (baseline)")
    if baseline:
        L("| Metric | 13A vs 12A | 13B vs 12A | 13C vs 12A |")
        L("|--------|:----------:|:----------:|:----------:|")

        delta_configs = ["13A", "13B", "13C"]
        delta_metrics = [
            ("Return (pp)", "total_return_pct"),
            ("Max DD (pp)", "max_drawdown_pct"),
            ("PF delta", "profit_factor"),
            ("Sharpe delta", "sharpe_ratio"),
            ("Trade count", "total_trades"),
        ]

        for metric_name, metric_key in delta_metrics:
            base_val = baseline.metrics.get(metric_key, 0)
            deltas = []
            for cfg in delta_configs:
                r = results.get(cfg)
                if r is None:
                    deltas.append("N/A")
                else:
                    v = r.metrics.get(metric_key, 0)
                    diff = v - base_val
                    sign = "+" if diff >= 0 else ""
                    deltas.append(f"{sign}{diff:.2f}")
            L(f"| {metric_name} | {' | '.join(deltas)} |")

        L("")

    L("---")
    L("")
    L("## File Paths")
    L("")
    L("| File | Description |")
    L("|------|-------------|")
    for cfg in configs:
        safe_name = cfg.lower().replace(" ", "_").replace("(", "").replace(")", "")
        L(f"| `data/backtest_results/{safe_name}.json` | {cfg} results |")
    L(f"| `data/backtest_results/13th_backtest_report.md` | This report |")
    L("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="13th Backtest Series Runner")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip 12A baseline")
    parser.add_argument("--skip-13a", action="store_true", help="Skip 13A")
    parser.add_argument("--skip-13b", action="store_true", help="Skip 13B")
    parser.add_argument("--skip-13c", action="store_true", help="Skip 13C")
    parser.add_argument("--only-13a", action="store_true", help="Run only 13A")
    parser.add_argument("--only-13b", action="store_true", help="Run only 13B")
    parser.add_argument("--only-13c", action="store_true", help="Run only 13C")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    args = parser.parse_args()

    # Determine what to run
    run_baseline = True
    run_13a = True
    run_13b = True
    run_13c = True

    if args.only_13a:
        run_baseline = run_13b = run_13c = False
    elif args.only_13b:
        run_baseline = run_13a = run_13c = False
    elif args.only_13c:
        run_baseline = run_13a = run_13b = False

    if args.skip_baseline:
        run_baseline = False
    if args.skip_13a:
        run_13a = False
    if args.skip_13b:
        run_13b = False
    if args.skip_13c:
        run_13c = False

    # Load data
    bars_by_symbol = load_data()
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    total_start = time.time()
    results: dict[str, Any] = {}

    # ===================================================================
    # 12A Baseline: with vol_div (monkey-patched back in)
    # ===================================================================
    if run_baseline:
        print("\n" + "=" * 70)
        print("  12A Baseline (3 strategies including vol_div)")
        print("=" * 70)

        _patch_for_12a_baseline()
        result = run_single(bars_by_symbol, args.capital, label="12A (baseline)")
        results["12A (baseline)"] = result
        _save_result(result, "12A (baseline)", "12a_baseline.json")

    # ===================================================================
    # 13A: vol_div removed (permanent default)
    # ===================================================================
    if run_13a:
        print("\n" + "=" * 70)
        print("  13A: vol_div Removal Only")
        print("=" * 70)

        _patch_for_13a()
        result = run_single(bars_by_symbol, args.capital, label="13A")
        results["13A"] = result
        _save_result(result, "13A", "13a.json")

    # ===================================================================
    # 13B: 13A + safety net adjustment
    # ===================================================================
    if run_13b:
        print("\n" + "=" * 70)
        print("  13B: 13A + Safety Net Adjustment (DD=25%, Recovery=18%)")
        print("=" * 70)

        _patch_for_13b()
        result = run_single(bars_by_symbol, args.capital, label="13B")
        results["13B"] = result
        _save_result(result, "13B", "13b.json")

    # ===================================================================
    # 13C: 13B + rsi_mr risk reduction
    # ===================================================================
    if run_13c:
        print("\n" + "=" * 70)
        print("  13C: 13B + rsi_mr Risk Reduction (0.75%, GDR 2%/4%)")
        print("=" * 70)

        _patch_for_13c()
        result = run_single(bars_by_symbol, args.capital, label="13C")
        results["13C"] = result
        _save_result(result, "13C", "13c.json")

    # ===================================================================
    # Comparison and report
    # ===================================================================
    total_elapsed = time.time() - total_start

    if results:
        print_comparison_table(results)

        # Generate markdown report
        report = generate_report(results)
        report_path = os.path.join(_OUTPUT_DIR, "13th_backtest_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info("Report saved: %s", report_path)
        print(f"\n  Report: {report_path}")

    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    print(f"{'=' * 70}")
    print("  13th Backtest Series complete.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
