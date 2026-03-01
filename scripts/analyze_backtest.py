#!/usr/bin/env python
"""CLI for MFE/MAE trade analysis.

Usage:
    python scripts/analyze_backtest.py 17a_risk_optimized.json
    python scripts/analyze_backtest.py 17a.json --compare 16a.json
    python scripts/analyze_backtest.py 17a.json --strategy rsi_mean_reversion
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autotrader.analysis.report_generator import ABComparisonReport, ReportGenerator
from autotrader.analysis.trade_analyzer import TradeAnalyzer

_RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_results"


def _resolve_path(filename: str) -> Path:
    """Resolve file path: try as-is first, then in data/backtest_results/."""
    p = Path(filename)
    if p.exists():
        return p
    fallback = _RESULTS_DIR / filename
    if fallback.exists():
        return fallback
    print(f"Error: file not found: {filename}", file=sys.stderr)
    print(f"  Searched: {p.resolve()}", file=sys.stderr)
    print(f"  Searched: {fallback}", file=sys.stderr)
    sys.exit(1)


def _load_trades(path: Path) -> list[dict]:
    """Load trades from a backtest JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if "trades" in data:
        return data["trades"]
    print(f"Error: no 'trades' key found in {path}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="MFE/MAE Trade Analysis")
    parser.add_argument("file", help="Backtest result JSON file")
    parser.add_argument("--compare", help="Second file for A/B comparison")
    parser.add_argument("--strategy", help="Filter to single strategy")
    parser.add_argument("-o", "--output", help="Save report to file")
    args = parser.parse_args()

    path = _resolve_path(args.file)
    trades = _load_trades(path)
    analyzer = TradeAnalyzer(trades)
    result = analyzer.analyze(strategy_filter=args.strategy)

    if args.compare:
        compare_path = _resolve_path(args.compare)
        compare_trades = _load_trades(compare_path)
        compare_analyzer = TradeAnalyzer(compare_trades)
        compare_result = compare_analyzer.analyze(strategy_filter=args.strategy)

        report = ReportGenerator(result).generate()
        comparison = ABComparisonReport(
            compare_result,
            result,
            baseline_label=Path(args.compare).stem,
            variant_label=Path(args.file).stem,
        ).generate()
        output = report + "\n\n" + comparison
    else:
        output = ReportGenerator(result).generate()

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"Report saved to {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
