"""Backtest runner: 5-strategy swing trading portfolio with regime-based allocation.

Usage:
    python scripts/run_swing_backtest.py
    python scripts/run_swing_backtest.py --symbols AAPL MSFT NVDA --days 30
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swing Trading Portfolio Backtest")
    parser.add_argument(
        "--symbols", nargs="+", default=["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"],
        help="Symbols to backtest (default: AAPL MSFT GOOGL NVDA TSLA)",
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Calendar days of history to fetch (default: 30)",
    )
    parser.add_argument(
        "--balance", type=float, default=3000.0,
        help="Initial balance in dollars (default: 3000)",
    )
    parser.add_argument(
        "--timeframe", choices=["5min", "15min", "1hour", "1day"], default="1day",
        help="Bar timeframe (default: 1day)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(_PROJECT_ROOT / "config" / ".env")
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        print("[ERROR] ALPACA_API_KEY or ALPACA_SECRET_KEY not found in config/.env")
        sys.exit(1)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from autotrader.core.types import Bar
    from autotrader.core.config import RiskConfig
    from autotrader.backtest.engine import BacktestEngine
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
    from autotrader.strategy.adx_pullback import AdxPullback
    from autotrader.strategy.overbought_short import OverboughtShort
    from autotrader.strategy.regime_momentum import RegimeMomentum

    tf_map = {
        "5min": TimeFrame(5, TimeFrameUnit.Minute),
        "15min": TimeFrame(15, TimeFrameUnit.Minute),
        "1hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1day": TimeFrame(1, TimeFrameUnit.Day),
    }

    client = StockHistoricalDataClient(api_key, secret_key)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=args.days)

    strategy_names = [
        "RsiMeanReversion", "BbSqueezeBreakout", "AdxPullback",
        "OverboughtShort", "RegimeMomentum",
    ]

    print("=" * 80)
    print("  AutoTrader v2 -- Swing Trading Portfolio Backtest")
    print("=" * 80)
    print(f"  Period     : {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"  Timeframe  : {args.timeframe}")
    print(f"  Symbols    : {', '.join(args.symbols)}")
    print(f"  Strategies : {', '.join(strategy_names)}")
    print(f"  Initial    : ${args.balance:,.2f}")
    print("=" * 80)

    risk_config = RiskConfig(
        max_position_pct=0.30,
        daily_loss_limit_pct=0.05,
        max_drawdown_pct=0.30,
        max_open_positions=5,
    )

    results: dict[str, dict] = {}

    for symbol in args.symbols:
        print(f"\n  Fetching {symbol} ...")

        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf_map[args.timeframe],
                start=start_date,
                end=end_date,
            )
            raw = client.get_stock_bars(request)
        except Exception as exc:
            print(f"  [ERROR] Failed to fetch {symbol}: {exc}")
            continue

        try:
            alpaca_bars = raw[symbol]
        except (KeyError, IndexError):
            alpaca_bars = []
        if not alpaca_bars:
            print(f"  [WARN] No data for {symbol}, skipping.")
            continue

        bars: list[Bar] = []
        for ab in alpaca_bars:
            bars.append(Bar(
                symbol=symbol,
                timestamp=ab.timestamp,
                open=float(ab.open),
                high=float(ab.high),
                low=float(ab.low),
                close=float(ab.close),
                volume=float(ab.volume),
            ))

        print(f"  Received {len(bars)} bars")
        print(f"  Running 5-strategy backtest ...")

        engine = BacktestEngine(args.balance, risk_config)
        engine.add_strategy(RsiMeanReversion())
        engine.add_strategy(BbSqueezeBreakout())
        engine.add_strategy(AdxPullback())
        engine.add_strategy(OverboughtShort())
        engine.add_strategy(RegimeMomentum())

        result = engine.run(bars)

        strategy_breakdown: dict[str, int] = {}
        for trade in result.trades:
            strategy_breakdown[trade.strategy] = strategy_breakdown.get(trade.strategy, 0) + 1

        results[symbol] = {
            "total_trades": result.total_trades,
            "metrics": result.metrics,
            "final_equity": result.final_equity,
            "equity_curve": result.equity_curve,
            "num_bars": len(bars),
            "strategy_breakdown": strategy_breakdown,
            "trades": result.trades,
        }

        print(f"  Done. Trades: {result.total_trades}, Final equity: ${result.final_equity:,.2f}")
        if strategy_breakdown:
            print(f"  Breakdown: {strategy_breakdown}")

    if not results:
        print("\n  No results. All fetches failed or returned empty.")
        sys.exit(0)

    # Summary
    print("\n\n" + "=" * 80)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 80)

    header = (
        f"  {'Symbol':<8}{'Bars':>7}{'Trades':>8}"
        f"{'Win Rate':>10}{'PF':>8}{'Total PnL':>14}"
        f"{'Max DD':>10}{'Final Equity':>16}"
    )
    print(header)
    print("  " + "-" * 76)

    total_pnl_all = 0.0
    for sym, data in results.items():
        m = data["metrics"]
        total_pnl = m.get("total_pnl", 0.0)
        total_pnl_all += total_pnl
        pf = m.get("profit_factor", 0.0)
        pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"

        row = (
            f"  {sym:<8}{data['num_bars']:>7}{m.get('total_trades', 0):>8}"
            f"{m.get('win_rate', 0.0):>9.1%}{pf_str:>8}"
            f"  ${total_pnl:>+11,.2f}{m.get('max_drawdown', 0.0):>9.2%}"
            f"  ${data['final_equity']:>13,.2f}"
        )
        print(row)

    print("  " + "-" * 76)
    print(f"  {'TOTAL':<8}{'':>7}{'':>8}{'':>10}{'':>8}  ${total_pnl_all:>+11,.2f}")

    # Strategy breakdown
    print("\n\n" + "=" * 80)
    print("  STRATEGY BREAKDOWN (trades per strategy)")
    print("=" * 80)

    all_strategies: dict[str, int] = {}
    for data in results.values():
        for strat, count in data["strategy_breakdown"].items():
            all_strategies[strat] = all_strategies.get(strat, 0) + count

    for strat in sorted(all_strategies.keys()):
        print(f"  {strat:<25} {all_strategies[strat]:>5} trades")

    print("\n" + "=" * 80)
    print("  Backtest complete.")
    print("=" * 80)


if __name__ == "__main__":
    main()
