"""Backtest runner with dashboard data export.

Fetches Alpaca historical data, runs RegimeDualStrategy backtest,
exports results to JSON, and optionally launches Streamlit dashboard.

Usage:
    python scripts/run_backtest_dashboard.py              # run + export JSON
    python scripts/run_backtest_dashboard.py --launch      # run + export + open dashboard
"""
from __future__ import annotations

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv


def main() -> None:
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
    from autotrader.strategy.regime_dual import RegimeDualStrategy
    from autotrader.backtest.dashboard_data import BacktestDashboardData

    client = StockHistoricalDataClient(api_key, secret_key)

    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=14)
    symbols = ["AAPL", "MSFT", "GOOGL"]
    initial_balance = 100_000.0
    risk_config = RiskConfig()

    print("=" * 70)
    print("  AutoTrader v2 -- Backtest Dashboard Runner")
    print("=" * 70)
    print(f"  Period  : {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}")
    print(f"  Symbols : {', '.join(symbols)}")
    print(f"  Initial : ${initial_balance:,.2f}")
    print("=" * 70)

    results = {}

    for symbol in symbols:
        print(f"\n  [{symbol}] Fetching data...")
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                start=start_date,
                end=end_date,
            )
            raw = client.get_stock_bars(request)
        except Exception as exc:
            print(f"  [ERROR] {symbol}: {exc}")
            continue

        try:
            alpaca_bars = raw[symbol]
        except (KeyError, IndexError):
            alpaca_bars = []
        if not alpaca_bars:
            print(f"  [WARN] No data for {symbol}, skipping.")
            continue

        bars: list[Bar] = [
            Bar(
                symbol=symbol,
                timestamp=ab.timestamp,
                open=float(ab.open),
                high=float(ab.high),
                low=float(ab.low),
                close=float(ab.close),
                volume=float(ab.volume),
            )
            for ab in alpaca_bars
        ]

        print(f"  [{symbol}] {len(bars)} bars, running backtest...")

        engine = BacktestEngine(initial_balance, risk_config)
        engine.add_strategy(RegimeDualStrategy())
        result = engine.run(bars)
        results[symbol] = result

        print(
            f"  [{symbol}] Trades: {result.total_trades}, "
            f"Final: ${result.final_equity:,.2f}, "
            f"Detail trades: {len(result.trades)}"
        )

    if not results:
        print("\n  No results. Exiting.")
        sys.exit(0)

    # Export to JSON
    config = {
        "initial_balance": initial_balance,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "symbols": symbols,
        "timeframe": "5min",
        "strategy": "RegimeDualStrategy",
    }

    dashboard_data = BacktestDashboardData.from_results(results, config)

    output_dir = _PROJECT_ROOT / "data" / "backtest_results"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_path = output_dir / f"{timestamp}.json"

    dashboard_data.to_json(output_path)
    print(f"\n  Dashboard data saved: {output_path}")

    # Print summary
    agg = dashboard_data.aggregate_metrics
    print(f"\n  Aggregate: {agg['total_trades']} trades, "
          f"PnL: ${agg['total_pnl']:+,.2f}, "
          f"Win Rate: {agg['win_rate']:.1%}")

    for ss, m in dashboard_data.per_substrategy_metrics.items():
        print(f"  {ss}: {m['trade_count']} trades, "
              f"PnL: ${m['total_pnl']:+,.2f}, "
              f"Win Rate: {m['win_rate']:.1%}")

    # Optional: launch dashboard
    if "--launch" in sys.argv:
        app_path = _PROJECT_ROOT / "autotrader" / "dashboard" / "app.py"
        print(f"\n  Launching dashboard...")
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            cwd=str(_PROJECT_ROOT),
        )


if __name__ == "__main__":
    main()
