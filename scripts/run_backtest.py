"""Backtest runner: fetches Alpaca historical data and runs RegimeDualStrategy.

Usage:
    python scripts/run_backtest.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv


def main() -> None:
    # ------------------------------------------------------------------ #
    # 1. Load environment and validate credentials
    # ------------------------------------------------------------------ #
    load_dotenv(_PROJECT_ROOT / "config" / ".env")

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        print("[ERROR] ALPACA_API_KEY or ALPACA_SECRET_KEY not found in config/.env")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 2. Set up Alpaca historical data client
    # ------------------------------------------------------------------ #
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    client = StockHistoricalDataClient(api_key, secret_key)

    # Date range: ~10 trading days back (14 calendar days to account for weekends)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=14)

    symbols = ["AAPL", "MSFT", "GOOGL"]

    print("=" * 80)
    print("  AutoTrader v2 -- RegimeDualStrategy Backtest")
    print("=" * 80)
    print(f"  Period     : {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"  Timeframe  : 5-minute bars")
    print(f"  Symbols    : {', '.join(symbols)}")
    print(f"  Initial    : $100,000.00")
    print("=" * 80)

    # ------------------------------------------------------------------ #
    # 3. Import autotrader components
    # ------------------------------------------------------------------ #
    from autotrader.core.types import Bar
    from autotrader.core.config import RiskConfig
    from autotrader.backtest.engine import BacktestEngine
    from autotrader.strategy.regime_dual import RegimeDualStrategy

    # ------------------------------------------------------------------ #
    # 4. Fetch data and run backtest per symbol
    # ------------------------------------------------------------------ #
    initial_balance = 100_000.0
    risk_config = RiskConfig()
    results: dict[str, dict] = {}

    for symbol in symbols:
        print(f"\n  Fetching {symbol} ...")

        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(5, TimeFrameUnit.Minute),
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
            print(f"  [WARN] No data returned for {symbol}, skipping.")
            continue

        # Convert Alpaca bars to our Bar type
        bars: list[Bar] = []
        for ab in alpaca_bars:
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=ab.timestamp,
                    open=float(ab.open),
                    high=float(ab.high),
                    low=float(ab.low),
                    close=float(ab.close),
                    volume=float(ab.volume),
                )
            )

        print(f"  Received {len(bars)} bars  ({bars[0].timestamp.strftime('%Y-%m-%d %H:%M')} -> {bars[-1].timestamp.strftime('%Y-%m-%d %H:%M')})")
        print(f"  Running backtest ...")

        # Fresh engine + strategy per symbol
        engine = BacktestEngine(initial_balance, risk_config)
        strategy = RegimeDualStrategy()
        engine.add_strategy(strategy)

        result = engine.run(bars)

        results[symbol] = {
            "total_trades": result.total_trades,
            "metrics": result.metrics,
            "final_equity": result.final_equity,
            "equity_curve": result.equity_curve,
            "num_bars": len(bars),
        }

        print(f"  Done. Trades: {result.total_trades}, Final equity: ${result.final_equity:,.2f}")

    # ------------------------------------------------------------------ #
    # 5. Print results summary
    # ------------------------------------------------------------------ #
    if not results:
        print("\n  No results to display. All symbol fetches failed or returned empty data.")
        sys.exit(0)

    print("\n")
    print("=" * 80)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 80)

    # Header
    header = (
        f"  {'Symbol':<8}"
        f"{'Bars':>7}"
        f"{'Trades':>8}"
        f"{'Win Rate':>10}"
        f"{'PF':>8}"
        f"{'Total PnL':>14}"
        f"{'Max DD':>10}"
        f"{'Final Equity':>16}"
    )
    print(header)
    print("  " + "-" * 76)

    total_pnl_all = 0.0

    for sym, data in results.items():
        m = data["metrics"]
        total_trades = m.get("total_trades", 0)
        win_rate = m.get("win_rate", 0.0)
        profit_factor = m.get("profit_factor", 0.0)
        total_pnl = m.get("total_pnl", 0.0)
        max_dd = m.get("max_drawdown", 0.0)
        final_eq = data["final_equity"]
        num_bars = data["num_bars"]

        total_pnl_all += total_pnl

        pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "inf"

        row = (
            f"  {sym:<8}"
            f"{num_bars:>7}"
            f"{total_trades:>8}"
            f"{win_rate:>9.1%}"
            f"{pf_str:>8}"
            f"  ${total_pnl:>+11,.2f}"
            f"{max_dd:>9.2%}"
            f"  ${final_eq:>13,.2f}"
        )
        print(row)

    print("  " + "-" * 76)
    print(f"  {'TOTAL':<8}{'':>7}{'':>8}{'':>10}{'':>8}  ${total_pnl_all:>+11,.2f}")

    # ------------------------------------------------------------------ #
    # 6. Equity curve summaries
    # ------------------------------------------------------------------ #
    print("\n")
    print("=" * 80)
    print("  EQUITY CURVE SUMMARY")
    print("=" * 80)
    print(f"  {'Symbol':<8}{'Start':>14}{'End':>14}{'Min':>14}{'Max':>14}{'Return':>10}")
    print("  " + "-" * 70)

    for sym, data in results.items():
        curve = data["equity_curve"]
        if not curve:
            continue
        start_eq = curve[0]
        end_eq = curve[-1]
        min_eq = min(curve)
        max_eq = max(curve)
        ret = (end_eq - start_eq) / start_eq if start_eq else 0.0

        row = (
            f"  {sym:<8}"
            f"${start_eq:>12,.2f}"
            f"${end_eq:>12,.2f}"
            f"${min_eq:>12,.2f}"
            f"${max_eq:>12,.2f}"
            f"{ret:>+9.2%}"
        )
        print(row)

    print("  " + "-" * 70)
    print("\n" + "=" * 80)
    print("  Backtest complete.")
    print("=" * 80)


if __name__ == "__main__":
    main()
