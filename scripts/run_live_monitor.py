"""Live trading performance monitor.

Reads JSONL trade logs and equity snapshots to compute
and display performance metrics.

Usage:
    python scripts/run_live_monitor.py
    python scripts/run_live_monitor.py --trades data/live_trades.jsonl --equity data/equity_snapshots.jsonl
    python scripts/run_live_monitor.py --since 2026-01-01
    python scripts/run_live_monitor.py --strategy adx_pullback
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autotrader.portfolio.trade_logger import LiveTradeRecord, TradeLogger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live trading performance monitor")
    parser.add_argument(
        "--trades",
        default="data/live_trades.jsonl",
        help="Path to trade log JSONL file",
    )
    parser.add_argument(
        "--equity",
        default="data/equity_snapshots.jsonl",
        help="Path to equity snapshot JSONL file",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only show trades since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--strategy",
        default=None,
        help="Filter by strategy name",
    )
    return parser.parse_args()


def compute_metrics(trades: list[LiveTradeRecord]) -> dict:
    """Compute overall performance metrics from trade records."""
    if not trades:
        return {}

    # Only consider close trades for PnL metrics
    close_trades = [t for t in trades if t.direction == "close"]
    if not close_trades:
        return {
            "total_trades": len(trades),
            "close_trades": 0,
        }

    pnls = [t.pnl for t in close_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    win_rate = len(wins) / len(pnls) if pnls else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown from equity curve
    equities = [t.equity_after for t in trades if t.equity_after > 0]
    max_dd = 0.0
    peak = equities[0] if equities else 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Simple Sharpe approximation (daily PnL std)
    if len(pnls) > 1:
        mean_pnl = total_pnl / len(pnls)
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_pnl = variance**0.5
        sharpe = (mean_pnl / std_pnl) * (252**0.5) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades": len(trades),
        "close_trades": len(close_trades),
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
    }


def per_strategy_breakdown(trades: list[LiveTradeRecord]) -> dict[str, dict]:
    """Compute per-strategy metrics."""
    strategies: dict[str, list[LiveTradeRecord]] = {}
    for t in trades:
        strategies.setdefault(t.strategy, []).append(t)

    result = {}
    for name, strades in sorted(strategies.items()):
        close_trades = [t for t in strades if t.direction == "close"]
        pnls = [t.pnl for t in close_trades]
        wins = [p for p in pnls if p > 0]
        result[name] = {
            "total": len(strades),
            "closes": len(close_trades),
            "pnl": sum(pnls),
            "win_rate": len(wins) / len(pnls) if pnls else 0.0,
            "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
        }
    return result


def per_regime_breakdown(trades: list[LiveTradeRecord]) -> dict[str, dict]:
    """Compute per-regime metrics."""
    regimes: dict[str, list[LiveTradeRecord]] = {}
    for t in trades:
        regimes.setdefault(t.regime, []).append(t)

    result = {}
    for name, rtrades in sorted(regimes.items()):
        close_trades = [t for t in rtrades if t.direction == "close"]
        pnls = [t.pnl for t in close_trades]
        wins = [p for p in pnls if p > 0]
        result[name] = {
            "total": len(rtrades),
            "closes": len(close_trades),
            "pnl": sum(pnls),
            "win_rate": len(wins) / len(pnls) if pnls else 0.0,
        }
    return result


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_overall(metrics: dict) -> None:
    print_header("OVERALL PERFORMANCE")
    if not metrics:
        print("  No trades found.")
        return
    print(f"  Total trades:    {metrics.get('total_trades', 0)}")
    print(f"  Closed trades:   {metrics.get('close_trades', 0)}")
    if metrics.get("close_trades", 0) == 0:
        return
    print(f"  Total PnL:       ${metrics['total_pnl']:,.2f}")
    print(f"  Win Rate:        {metrics['win_rate']:.1%}")
    print(f"  Avg Win:         ${metrics['avg_win']:,.2f}")
    print(f"  Avg Loss:        ${metrics['avg_loss']:,.2f}")
    pf = metrics["profit_factor"]
    pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
    print(f"  Profit Factor:   {pf_str}")
    print(f"  Max Drawdown:    {metrics['max_drawdown']:.1%}")
    print(f"  Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")


def print_strategy_breakdown(breakdown: dict[str, dict]) -> None:
    print_header("PER-STRATEGY BREAKDOWN")
    if not breakdown:
        print("  No data.")
        return
    print(
        f"  {'Strategy':<25} {'Trades':>7} {'Closes':>7} "
        f"{'PnL':>10} {'Win%':>7} {'Avg PnL':>10}"
    )
    print(f"  {'-' * 25} {'-' * 7} {'-' * 7} {'-' * 10} {'-' * 7} {'-' * 10}")
    for name, m in breakdown.items():
        print(
            f"  {name:<25} {m['total']:>7} {m['closes']:>7} "
            f"${m['pnl']:>9,.2f} {m['win_rate']:>6.1%} ${m['avg_pnl']:>9,.2f}"
        )


def print_regime_breakdown(breakdown: dict[str, dict]) -> None:
    print_header("PER-REGIME BREAKDOWN")
    if not breakdown:
        print("  No data.")
        return
    print(
        f"  {'Regime':<20} {'Trades':>7} {'Closes':>7} "
        f"{'PnL':>10} {'Win%':>7}"
    )
    print(f"  {'-' * 20} {'-' * 7} {'-' * 7} {'-' * 10} {'-' * 7}")
    for name, m in breakdown.items():
        print(
            f"  {name:<20} {m['total']:>7} {m['closes']:>7} "
            f"${m['pnl']:>9,.2f} {m['win_rate']:>6.1%}"
        )


def main() -> None:
    args = parse_args()

    trade_logger = TradeLogger(args.trades, args.equity)
    trades = trade_logger.read_trades()

    # Filter by date
    if args.since:
        trades = [t for t in trades if t.timestamp >= args.since]

    # Filter by strategy
    if args.strategy:
        trades = [t for t in trades if t.strategy == args.strategy]

    if not trades:
        print("No trades found.")
        if args.since:
            print(f"  (filtered since: {args.since})")
        if args.strategy:
            print(f"  (filtered strategy: {args.strategy})")
        return

    print(f"\n  Loaded {len(trades)} trade records")
    if args.since:
        print(f"  Filtered since: {args.since}")
    if args.strategy:
        print(f"  Filtered strategy: {args.strategy}")

    metrics = compute_metrics(trades)
    print_overall(metrics)
    print_strategy_breakdown(per_strategy_breakdown(trades))
    print_regime_breakdown(per_regime_breakdown(trades))


if __name__ == "__main__":
    main()
