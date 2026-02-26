"""Universe selection runner: selects optimal stocks from S&P 500.

Usage:
    python scripts/run_universe_selection.py
    python scripts/run_universe_selection.py --days 120 --target 15
    python scripts/run_universe_selection.py --days 90 --target 10 --balance 5000
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
    parser = argparse.ArgumentParser(description="S&P 500 Universe Selection")
    parser.add_argument(
        "--days", type=int, default=120,
        help="Calendar days of history (default: 120)",
    )
    parser.add_argument(
        "--target", type=int, default=15,
        help="Target universe size (default: 15)",
    )
    parser.add_argument(
        "--balance", type=float, default=3000.0,
        help="Initial balance for backtest scoring (default: 3000)",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=50,
        help="Max candidates to fetch and backtest (default: 50)",
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
    from alpaca.data.timeframe import TimeFrame

    from autotrader.core.types import Bar
    from autotrader.universe.provider import SP500Provider
    from autotrader.universe.selector import UniverseSelector
    from autotrader.universe.earnings import EarningsCalendar

    print("=" * 80)
    print("  AutoTrader v2 -- S&P 500 Universe Selection")
    print("=" * 80)

    # Step 1: Fetch S&P 500 list
    print("\n  [1/5] Fetching S&P 500 constituents...")
    provider = SP500Provider()
    infos = provider.fetch()
    print(f"  Found {len(infos)} constituents")

    # Step 2: Fetch earnings calendar
    print("\n  [2/5] Fetching earnings calendar...")
    earnings_cal = EarningsCalendar()
    symbols = [i.symbol for i in infos]
    try:
        earnings_cal.fetch(symbols[: args.max_candidates])
    except Exception as exc:
        print(f"  [WARN] Earnings fetch partial failure: {exc}")
    today = datetime.now().date()
    blackout = earnings_cal.blackout_symbols(symbols, today)
    print(f"  {len(blackout)} symbols in earnings blackout")

    # Step 3: Fetch historical bars
    print(f"\n  [3/5] Fetching {args.days}-day history (batched)...")
    client = StockHistoricalDataClient(api_key, secret_key)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=args.days)

    # Filter out blackout symbols
    active_symbols = [s for s in symbols if s not in blackout][: args.max_candidates]

    bars_by_symbol: dict[str, list[Bar]] = {}
    batch_size = 50
    for i in range(0, len(active_symbols), batch_size):
        batch = active_symbols[i : i + batch_size]
        print(f"  Fetching batch {i // batch_size + 1}: {len(batch)} symbols...")
        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date,
            )
            raw = client.get_stock_bars(request)
            for sym in batch:
                try:
                    alpaca_bars = raw[sym]
                except (KeyError, IndexError):
                    continue
                if not alpaca_bars:
                    continue
                bars_by_symbol[sym] = [
                    Bar(
                        symbol=sym,
                        timestamp=ab.timestamp,
                        open=float(ab.open),
                        high=float(ab.high),
                        low=float(ab.low),
                        close=float(ab.close),
                        volume=float(ab.volume),
                    )
                    for ab in alpaca_bars
                ]
        except Exception as exc:
            print(f"  [ERROR] Batch fetch failed: {exc}")

    print(f"  Received data for {len(bars_by_symbol)} symbols")

    # Step 4: Run universe selection
    print(f"\n  [4/5] Running universe selection (target: {args.target})...")
    selector = UniverseSelector(
        initial_balance=args.balance,
        target_size=args.target,
    )
    result = selector.select(infos, bars_by_symbol)

    # Step 5: Display results
    print("\n  [5/5] Selection complete!")

    print("\n\n" + "=" * 80)
    print("  SELECTED UNIVERSE")
    print("=" * 80)

    header = (
        f"  {'#':<4}{'Symbol':<8}{'Sector':<25}"
        f"{'Score':>8}{'Proxy':>8}{'BT':>8}{'Trend%':>8}{'Range%':>8}"
    )
    print(header)
    print("  " + "-" * 76)

    for i, sc in enumerate(result.scored, 1):
        c = sc.candidate
        print(
            f"  {i:<4}{c.symbol:<8}{c.sector:<25}"
            f"{sc.final_score:>8.3f}{sc.proxy_score:>8.3f}{sc.backtest_score:>8.3f}"
            f"{c.trend_pct:>7.1%}{c.range_pct:>8.1%}"
        )

    if result.rotation_in:
        print(f"\n  IN:  {', '.join(result.rotation_in)}")
    if result.rotation_out:
        print(f"  OUT: {', '.join(result.rotation_out)}")

    print(f"\n  Symbols: {result.symbols}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
