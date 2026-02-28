"""Multi-Timeframe Universe Selection + 5-Strategy Backtest + Dashboard pipeline.

MTF approach (expert panel consensus):
  - Daily bars for universe selection (filters calibrated for daily data)
  - 1-hour bars for backtest execution (more data points for swing trading)

Data split to prevent look-ahead bias:
  - SELECTION (older): days N ~ test-days for universe selection scoring (daily)
  - TEST (recent): last test-days for backtest evaluation on unseen data (1-hour)

Example with --days 120 --test-days 7:
  |---- 113d ago (selection, daily) ----|---- recent 7d (backtest, 1hour) ----|

Usage:
    python scripts/run_swing_dashboard.py
    python scripts/run_swing_dashboard.py --days 120 --test-days 7 --launch
    python scripts/run_swing_dashboard.py --max-candidates 100 --balance 5000
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="S&P 500 Universe Selection + 5-Strategy Backtest + Dashboard",
    )
    parser.add_argument(
        "--days", type=int, default=120,
        help="Total calendar days of history to fetch (default: 120)",
    )
    parser.add_argument(
        "--test-days", type=int, default=7,
        help="Recent days reserved for backtest evaluation (default: 7, one week)",
    )
    parser.add_argument(
        "--target", type=int, default=15,
        help="Target universe size (default: 15)",
    )
    parser.add_argument(
        "--balance", type=float, default=3000.0,
        help="Initial balance for backtest (default: 3000)",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=50,
        help="Max candidates to fetch from S&P 500 (default: 50)",
    )
    parser.add_argument(
        "--bt-timeframe", choices=["1day", "1hour"], default="1hour",
        help="Backtest bar timeframe (default: 1hour). Selection always uses daily.",
    )
    parser.add_argument(
        "--launch", action="store_true",
        help="Launch Streamlit dashboard after export",
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
    from autotrader.backtest.dashboard_data import BacktestDashboardData
    from autotrader.universe.provider import SP500Provider
    from autotrader.universe.selector import UniverseSelector
    from autotrader.universe.earnings import EarningsCalendar
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown
    from autotrader.strategy.ema_pullback import EmaPullback
    from autotrader.strategy.volume_divergence import VolumeDivergence

    tf_map = {
        "1day": TimeFrame.Day,
        "1hour": TimeFrame(1, TimeFrameUnit.Hour),
    }

    client = StockHistoricalDataClient(api_key, secret_key)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=args.days)

    # Split: selection uses older data, test uses recent data
    test_days = args.test_days
    selection_days = args.days - test_days
    split_date = end_date - timedelta(days=test_days)
    # Make split_date timezone-aware for comparison with bar timestamps
    split_date_aware = split_date.replace(tzinfo=timezone.utc)

    # MTF: selection always daily, backtest uses bt_timeframe
    bt_timeframe = args.bt_timeframe

    strategy_names = [
        "RsiMeanReversion", "ConsecutiveDown", "EmaPullback",
        "VolumeDivergence",
    ]

    print("=" * 80)
    print("  AutoTrader v2 -- MTF Swing Trading Pipeline")
    print("=" * 80)
    print(f"  Total Period : {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d} ({args.days}d)")
    print(f"  SELECTION    : {start_date:%Y-%m-%d} to {split_date:%Y-%m-%d} ({selection_days}d, daily)")
    print(f"  TEST (unseen): {split_date:%Y-%m-%d} to {end_date:%Y-%m-%d} ({test_days}d, {bt_timeframe})")
    print(f"  Target Pool  : {args.target} stocks")
    print(f"  Candidates   : top {args.max_candidates} from S&P 500")
    print(f"  Strategies   : {', '.join(strategy_names)}")
    print(f"  Initial      : ${args.balance:,.2f}")
    print("=" * 80)

    # ── Step 1: Fetch S&P 500 list ──────────────────────────────────────
    print("\n  [1/7] Fetching S&P 500 constituents from Wikipedia...")
    provider = SP500Provider()
    infos = provider.fetch()
    print(f"  Found {len(infos)} constituents")

    # ── Step 2: Earnings blackout check ─────────────────────────────────
    print("\n  [2/7] Checking earnings blackout periods...")
    earnings_cal = EarningsCalendar()
    all_symbols = [i.symbol for i in infos]
    try:
        earnings_cal.fetch(all_symbols[: args.max_candidates])
    except Exception as exc:
        print(f"  [WARN] Earnings fetch partial failure: {exc}")
    today = datetime.now().date()
    blackout = earnings_cal.blackout_symbols(all_symbols, today)
    print(f"  {len(blackout)} symbols in earnings blackout (excluded)")

    # ── Step 3: Fetch daily bars for SELECTION period ───────────────────
    print(f"\n  [3/8] Fetching daily bars for selection ({selection_days}d)...")
    active_symbols = [s for s in all_symbols if s not in blackout][: args.max_candidates]

    def fetch_bars(symbols: list[str], tf: TimeFrame, start: datetime, end: datetime,
                   label: str) -> dict[str, list[Bar]]:
        result_bars: dict[str, list[Bar]] = {}
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            n_batches = (len(symbols) - 1) // batch_size + 1
            print(f"    {label} batch {i // batch_size + 1}/{n_batches}: {len(batch)} symbols...")
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch, timeframe=tf,
                    start=start, end=end,
                )
                raw = client.get_stock_bars(request)
                for sym in batch:
                    try:
                        alpaca_bars = raw[sym]
                    except (KeyError, IndexError):
                        continue
                    if not alpaca_bars:
                        continue
                    result_bars[sym] = [
                        Bar(
                            symbol=sym, timestamp=ab.timestamp,
                            open=float(ab.open), high=float(ab.high),
                            low=float(ab.low), close=float(ab.close),
                            volume=float(ab.volume),
                        )
                        for ab in alpaca_bars
                    ]
            except Exception as exc:
                print(f"    [ERROR] {label} batch fetch failed: {exc}")
        return result_bars

    batch_size = 50

    # Fetch DAILY bars for selection (full period, split later)
    daily_bars_by_symbol = fetch_bars(
        active_symbols, TimeFrame.Day, start_date, end_date, "Daily",
    )
    print(f"  Received daily data for {len(daily_bars_by_symbol)} symbols")

    # ── Step 4: Split daily bars into TRAIN (selection only) ──────────
    print(f"\n  [4/8] Splitting daily data at {split_date:%Y-%m-%d}...")
    train_bars_by_symbol: dict[str, list[Bar]] = {}
    for sym, bars in daily_bars_by_symbol.items():
        train = [b for b in bars if b.timestamp < split_date_aware]
        if train:
            train_bars_by_symbol[sym] = train

    sample_sym = next(iter(daily_bars_by_symbol), None)
    if sample_sym:
        total = len(daily_bars_by_symbol[sample_sym])
        train_n = len(train_bars_by_symbol.get(sample_sym, []))
        print(f"  Example ({sample_sym}): {total} daily total -> {train_n} train bars")
    print(f"  Train symbols: {len(train_bars_by_symbol)}")

    # ── Step 5: Run Universe Selection on TRAIN data (daily) ─────────────
    print(f"\n  [5/8] Running universe selection on SELECTION data (daily, target: {args.target})...")
    selector = UniverseSelector(
        initial_balance=args.balance,
        target_size=args.target,
    )
    universe = selector.select(infos, train_bars_by_symbol)

    selected_symbols = universe.symbols
    print(f"  Selected {len(selected_symbols)} stocks (based on daily SELECTION data):")

    print(f"\n  {'#':<4}{'Symbol':<8}{'Sector':<25}{'Score':>8}{'Proxy':>8}{'BT':>8}")
    print("  " + "-" * 60)
    for i, sc in enumerate(universe.scored, 1):
        c = sc.candidate
        print(
            f"  {i:<4}{c.symbol:<8}{c.sector:<25}"
            f"{sc.final_score:>8.3f}{sc.proxy_score:>8.3f}{sc.backtest_score:>8.3f}"
        )

    if not selected_symbols:
        print("\n  [ERROR] No stocks selected. Check filter thresholds.")
        sys.exit(1)

    # ── Step 6: Fetch backtest-timeframe bars for selected symbols ─────
    print(f"\n  [6/8] Fetching {bt_timeframe} bars for {len(selected_symbols)} "
          f"selected symbols (test period + warmup)...")

    # For backtest bars, include some warmup data before split_date
    # ADX needs 29 bars warmup, so fetch extra days before test period
    warmup_days = 14 if bt_timeframe == "1hour" else 60
    bt_start = split_date - timedelta(days=warmup_days)

    test_bars_by_symbol: dict[str, list[Bar]] = fetch_bars(
        selected_symbols, tf_map[bt_timeframe], bt_start, end_date, bt_timeframe,
    )
    print(f"  Received {bt_timeframe} data for {len(test_bars_by_symbol)} symbols")

    if test_bars_by_symbol:
        sample = next(iter(test_bars_by_symbol))
        n_bars = len(test_bars_by_symbol[sample])
        warmup_bars = len([b for b in test_bars_by_symbol[sample]
                          if b.timestamp < split_date_aware])
        test_only = n_bars - warmup_bars
        print(f"  Example ({sample}): {n_bars} total ({warmup_bars} warmup + {test_only} test)")

    # ── Step 7: Run 5-strategy backtest on TEST data (unseen) ───────────
    print(f"\n  [7/8] Running 5-strategy backtest on {bt_timeframe} data "
          f"({split_date:%Y-%m-%d} ~ {end_date:%Y-%m-%d})...")
    risk_config = RiskConfig(
        max_position_pct=0.30,
        daily_loss_limit_pct=0.05,
        max_drawdown_pct=0.30,
        max_open_positions=5,
    )

    results: dict[str, object] = {}
    for sym in selected_symbols:
        bars = test_bars_by_symbol.get(sym, [])
        if not bars:
            print(f"  [{sym}] No TEST data, skipping.")
            continue

        engine = BacktestEngine(args.balance, risk_config)
        engine.add_strategy(RsiMeanReversion())
        engine.add_strategy(ConsecutiveDown())
        engine.add_strategy(EmaPullback())
        engine.add_strategy(VolumeDivergence())

        result = engine.run(bars)
        results[sym] = result

        strat_breakdown: dict[str, int] = {}
        for t in result.trades:
            strat_breakdown[t.strategy] = strat_breakdown.get(t.strategy, 0) + 1

        pnl = result.metrics.get("total_pnl", 0.0)
        print(
            f"  [{sym}] {len(bars)} bars, {result.total_trades} trades, "
            f"PnL: ${pnl:+,.2f}, Final: ${result.final_equity:,.2f}"
        )

    if not results:
        print("\n  [ERROR] No backtest results. Exiting.")
        sys.exit(1)

    # ── Step 8: Export to dashboard JSON ────────────────────────────────
    print(f"\n  [8/8] Exporting dashboard data...")

    config = {
        "initial_balance": args.balance,
        "total_period": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "selection_period": f"{start_date.isoformat()} to {split_date.isoformat()}",
        "test_period": f"{split_date.isoformat()} to {end_date.isoformat()}",
        "selection_days": selection_days,
        "test_days": test_days,
        "symbols": selected_symbols,
        "selection_timeframe": "1day",
        "backtest_timeframe": bt_timeframe,
        "strategies": strategy_names,
        "target_pool": args.target,
        "max_candidates": args.max_candidates,
        "pipeline": "universe_selection(daily) + backtest({})".format(bt_timeframe),
        "data_split": f"{selection_days}d selection(daily) / {test_days}d test({bt_timeframe})",
    }

    dashboard_data = BacktestDashboardData.from_results(results, config)

    output_dir = _PROJECT_ROOT / "data" / "backtest_results"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_path = output_dir / f"swing_{timestamp}.json"
    dashboard_data.to_json(output_path)
    print(f"  Dashboard data saved: {output_path}")

    # ── Summary ─────────────────────────────────────────────────────────
    agg = dashboard_data.aggregate_metrics
    print("\n\n" + "=" * 80)
    print("  BACKTEST RESULTS SUMMARY (evaluated on unseen TEST data)")
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
        m = data.metrics
        total_pnl = m.get("total_pnl", 0.0)
        total_pnl_all += total_pnl
        pf = m.get("profit_factor", 0.0)
        pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
        bars_count = len(test_bars_by_symbol.get(sym, []))

        row = (
            f"  {sym:<8}{bars_count:>7}{m.get('total_trades', 0):>8}"
            f"{m.get('win_rate', 0.0):>9.1%}{pf_str:>8}"
            f"  ${total_pnl:>+11,.2f}{m.get('max_drawdown', 0.0):>9.2%}"
            f"  ${data.final_equity:>13,.2f}"
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
        for t in data.trades:
            all_strategies[t.strategy] = all_strategies.get(t.strategy, 0) + 1

    for strat in sorted(all_strategies.keys()):
        print(f"  {strat:<25} {all_strategies[strat]:>5} trades")

    print(f"\n  Aggregate: {agg['total_trades']} trades, "
          f"PnL: ${agg['total_pnl']:+,.2f}, "
          f"Win Rate: {agg['win_rate']:.1%}")

    # Sub-strategy breakdown
    if dashboard_data.per_substrategy_metrics:
        print("\n  Sub-Strategy Performance:")
        for ss, m in dashboard_data.per_substrategy_metrics.items():
            print(f"  {ss:<30} {m['trade_count']:>4} trades, "
                  f"PnL: ${m['total_pnl']:+,.2f}, "
                  f"Win Rate: {m['win_rate']:.1%}")

    print("\n" + "=" * 80)
    print("  Pipeline complete.")
    print("=" * 80)

    # Launch dashboard
    if args.launch:
        app_path = _PROJECT_ROOT / "autotrader" / "dashboard" / "app.py"
        print(f"\n  Launching Streamlit dashboard...")
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            cwd=str(_PROJECT_ROOT),
        )


if __name__ == "__main__":
    main()
