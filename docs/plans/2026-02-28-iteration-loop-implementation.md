# Strategy Iteration Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the infrastructure for team-driven strategy iteration loop, then execute iterations until Sharpe >= 1.0 or Calmar >= 1.0 across 2 time periods.

**Architecture:** Revert P1 uncommitted changes to start clean from P0 (v3.1). Create a multi-period data download script and an iteration backtest runner with S&P 500 benchmark comparison. Then execute the iteration loop: strategy team analyzes -> dev team implements -> test team validates -> repeat.

**Tech Stack:** Python 3.11, Alpaca API (historical bars), yfinance (S&P 500 benchmark), existing BatchBacktester, existing TradeAnalyzer

---

### Task 1: Clean Slate — Revert P1 Uncommitted Changes

**Owner:** Orchestrator (git operations only, no code changes)

**Context:** P1 changes (RSI_OB 75->80, TP AND condition, stop_distance passthrough) are uncommitted on development. The iteration loop should start from the last committed state (P0/v3.1, commit 957129d).

**Step 1: Verify current uncommitted changes**

Run: `git diff --stat`
Expected: Changes in exit_rules.py, rsi_mean_reversion.py, main.py, test files

**Step 2: Revert all uncommitted changes**

Run: `git checkout -- .`
Expected: Working tree clean (except .claude/)

**Step 3: Verify clean state**

Run: `git status`
Expected: Only .claude/ changes (if any)

**Step 4: Run full test suite to confirm baseline**

Run: `python -m pytest tests/ -q`
Expected: All tests pass (1060+ tests)

---

### Task 2: Create Multi-Period Data Download Script

**Owner:** Dev-4 (devops-architect, scripts/)

**Files:**
- Create: `scripts/download_historical_data.py`

**Context:** We need historical bar data for Period 1 (2024-03-01 ~ 2025-02-28) in addition to the existing Period 2 data. The script should download from Alpaca API and cache to pkl files.

**Step 1: Write the download script**

```python
#!/usr/bin/env python3
"""
Download and cache historical bar data for multiple periods.

Usage:
  python scripts/download_historical_data.py --period 1
  python scripts/download_historical_data.py --period 2 --refresh
  python scripts/download_historical_data.py --all
"""

import argparse
import asyncio
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from autotrader.broker.alpaca_adapter import AlpacaAdapter
from autotrader.universe.provider import SP500Provider

load_dotenv(PROJECT_ROOT / "config" / ".env")

PERIODS = {
    1: {
        "label": "Period 1 (2024-03 ~ 2025-02)",
        "days": 365,
        "cache_file": PROJECT_ROOT / "data" / "historical_bars_period1.pkl",
        # Approximate: download 365 days ending around 2025-02-28
        # Alpaca API uses calendar days from "now" — so we need to calculate offset
        "note": "Bull market / AI rally period",
    },
    2: {
        "label": "Period 2 (2025-03 ~ 2026-02)",
        "days": 365,
        "cache_file": PROJECT_ROOT / "data" / "historical_bars.pkl",
        "note": "Mixed market / current period (existing cache)",
    },
}

MIN_BARS = 60  # Warmup requirement


async def download_period(period_num: int, refresh: bool = False) -> None:
    """Download historical bars for a specific period."""
    cfg = PERIODS[period_num]
    cache_path = cfg["cache_file"]

    if not refresh and cache_path.exists():
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        bars = cached.get("bars", {})
        print(f"  Cache hit: {len(bars)} symbols in {cache_path.name}")
        return

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret_key:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY required in config/.env")
        sys.exit(1)

    # Get S&P 500 symbols
    provider = SP500Provider()
    stocks = provider.fetch()
    symbols = [s.symbol for s in stocks]
    print(f"  Fetching {len(symbols)} S&P 500 symbols...")

    # Download bars
    adapter = AlpacaAdapter(api_key=api_key, secret_key=secret_key, paper=True)
    await adapter.connect()

    try:
        bars_by_symbol = await adapter.get_historical_bars(
            symbols, days=cfg["days"]
        )
    finally:
        await adapter.disconnect()

    # Filter symbols with insufficient bars
    filtered = {
        sym: bars
        for sym, bars in bars_by_symbol.items()
        if len(bars) >= MIN_BARS
    }
    dropped = len(bars_by_symbol) - len(filtered)
    print(f"  Downloaded: {len(filtered)} symbols ({dropped} dropped, <{MIN_BARS} bars)")

    # Show date range
    sample_sym = next(iter(filtered))
    sample_bars = filtered[sample_sym]
    print(f"  Date range: {sample_bars[0].timestamp.date()} ~ {sample_bars[-1].timestamp.date()}")

    # Save cache
    os.makedirs(cache_path.parent, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(
            {"_meta_days": cfg["days"], "bars": filtered},
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    print(f"  Saved to {cache_path.name}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download historical bar data")
    parser.add_argument(
        "--period",
        type=int,
        choices=[1, 2],
        help="Period to download (1 or 2)",
    )
    parser.add_argument("--all", action="store_true", help="Download all periods")
    parser.add_argument(
        "--refresh", action="store_true", help="Force re-download even if cached"
    )
    args = parser.parse_args()

    if not args.period and not args.all:
        parser.print_help()
        sys.exit(1)

    periods = [1, 2] if args.all else [args.period]

    for p in periods:
        cfg = PERIODS[p]
        print(f"\n=== {cfg['label']} ===")
        print(f"  Note: {cfg['note']}")
        await download_period(p, refresh=args.refresh)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Test the script (Period 1 download)**

Run: `python scripts/download_historical_data.py --period 1`
Expected: Downloads ~450+ symbols, saves to `data/historical_bars_period1.pkl`

**Step 3: Commit**

```bash
git add scripts/download_historical_data.py
git commit -m "feat: add multi-period historical data download script"
```

---

### Task 3: Create Iteration Backtest Runner

**Owner:** Dev-4 (devops-architect, scripts/)

**Files:**
- Create: `scripts/run_iteration_backtest.py`

**Context:** A reusable script for iteration loop backtests. Runs the current strategy against specified period data, calculates Sharpe/Calmar, compares vs S&P 500 benchmark, and outputs pass/fail judgment. Saves results to `data/backtest_results/iterations/`.

**Step 1: Write the iteration backtest runner**

```python
#!/usr/bin/env python3
"""
Iteration loop backtest runner with S&P 500 benchmark comparison.

Runs the current strategy configuration against cached historical data,
calculates risk-adjusted metrics (Sharpe, Calmar), and compares against
S&P 500 buy-and-hold for the same period.

Usage:
  python scripts/run_iteration_backtest.py --iteration 1
  python scripts/run_iteration_backtest.py --iteration 1 --period 1
  python scripts/run_iteration_backtest.py --iteration 5 --validate-all

Output:
  data/backtest_results/iterations/iter_01_period2.json
  data/backtest_results/iterations/iter_01_period1.json  (with --validate-all)
"""

import argparse
import json
import os
import pickle
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yfinance as yf

from autotrader.backtest.batch_simulator import BatchBacktester

# Period config
PERIOD_DATA = {
    1: PROJECT_ROOT / "data" / "historical_bars_period1.pkl",
    2: PROJECT_ROOT / "data" / "historical_bars.pkl",
}

RESULTS_DIR = PROJECT_ROOT / "data" / "backtest_results" / "iterations"

# Success criteria
TARGET_SHARPE = 1.0
TARGET_CALMAR = 1.0


def load_bars(period: int) -> dict:
    """Load cached historical bars for a period."""
    path = PERIOD_DATA[period]
    if not path.exists():
        print(f"ERROR: Cache file not found: {path}")
        print(f"Run: python scripts/download_historical_data.py --period {period}")
        sys.exit(1)

    with open(path, "rb") as f:
        cached = pickle.load(f)
    bars = cached.get("bars", {})
    print(f"  Loaded {len(bars)} symbols from {path.name}")
    return bars


def get_sp500_benchmark(start_date: str, end_date: str) -> dict:
    """Calculate S&P 500 buy-and-hold metrics for the period."""
    sp = yf.download("^GSPC", start=start_date, end=end_date, progress=False)
    if len(sp) == 0:
        return {"error": "No S&P 500 data available"}

    closes = sp["Close"].values.flatten()
    first = float(closes[0])
    last = float(closes[-1])
    total_return = (last - first) / first
    trading_days = len(closes)
    ann_return = (1 + total_return) ** (252.0 / trading_days) - 1.0

    # Daily returns
    daily_rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    mean_r = sum(daily_rets) / len(daily_rets)
    var_r = sum((r - mean_r) ** 2 for r in daily_rets) / len(daily_rets)
    std_r = var_r ** 0.5
    sharpe = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0

    # Max drawdown
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c - peak) / peak
        if dd < max_dd:
            max_dd = dd

    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0

    return {
        "total_return_pct": total_return * 100,
        "annualised_return_pct": ann_return * 100,
        "max_drawdown_pct": max_dd * 100,
        "sharpe_ratio": sharpe,
        "calmar_ratio": calmar,
        "trading_days": trading_days,
        "start_price": first,
        "end_price": last,
    }


def run_backtest(bars_by_symbol: dict) -> dict:
    """Run backtest and return full result as dict."""
    bt = BatchBacktester(initial_capital=100_000.0, use_per_strategy_gdr=True)
    result = bt.run(bars_by_symbol)

    # Serialize trades
    trades_list = []
    for t in result.trades:
        td = {
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "strategy": t.strategy,
            "direction": t.direction,
            "entry_date": t.entry_date.isoformat(),
            "exit_date": t.exit_date.isoformat(),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "qty": t.qty,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
            "bars_held": t.bars_held,
            "exit_reason": t.exit_reason,
            "mfe_pct": t.mfe_pct,
            "mae_pct": t.mae_pct,
            "entry_atr": t.entry_atr,
            "signal_strength": t.signal_strength,
            "gap_pct": t.gap_pct,
        }
        trades_list.append(td)

    eq_curve = [[d.isoformat(), v] for d, v in result.equity_curve]

    return {
        "metrics": result.metrics,
        "per_strategy_metrics": result.per_strategy_metrics,
        "trades": trades_list,
        "equity_curve": eq_curve,
        "config": result.config,
    }


def print_comparison(iteration: int, period: int, strategy_metrics: dict, benchmark: dict) -> bool:
    """Print comparison table and return True if criteria met."""
    sm = strategy_metrics
    bm = benchmark

    sharpe_ok = sm.get("sharpe_ratio", 0) >= TARGET_SHARPE
    calmar_ok = sm.get("calmar_ratio", 0) >= TARGET_CALMAR
    passed = sharpe_ok or calmar_ok

    print(f"\n{'='*60}")
    print(f"  ITERATION {iteration} — Period {period} Results")
    print(f"{'='*60}")
    print(f"{'Metric':<25} {'Strategy':>12} {'S&P 500':>12} {'Delta':>10}")
    print(f"{'-'*60}")

    def row(name, sv, bv):
        delta = sv - bv
        sign = "+" if delta >= 0 else ""
        print(f"{name:<25} {sv:>11.2f}% {bv:>11.2f}% {sign}{delta:>8.2f}%")

    def row_ratio(name, sv, bv):
        delta = sv - bv
        sign = "+" if delta >= 0 else ""
        print(f"{name:<25} {sv:>12.3f} {bv:>12.3f} {sign}{delta:>9.3f}")

    row("Return", sm.get("total_return_pct", 0), bm.get("total_return_pct", 0))
    row("Max Drawdown", sm.get("max_drawdown_pct", 0), bm.get("max_drawdown_pct", 0))
    row_ratio("Sharpe Ratio", sm.get("sharpe_ratio", 0), bm.get("sharpe_ratio", 0))
    row_ratio("Calmar Ratio", sm.get("calmar_ratio", 0), bm.get("calmar_ratio", 0))

    print(f"{'-'*60}")
    print(f"  Total Trades: {sm.get('total_trades', 0)}")
    print(f"  Win Rate: {sm.get('win_rate', 0)*100:.1f}%")
    print(f"  Profit Factor: {sm.get('profit_factor', 0):.3f}")
    print(f"{'-'*60}")

    status = "PASS" if passed else "FAIL"
    criteria = []
    if sharpe_ok:
        criteria.append(f"Sharpe {sm.get('sharpe_ratio',0):.3f} >= {TARGET_SHARPE}")
    if calmar_ok:
        criteria.append(f"Calmar {sm.get('calmar_ratio',0):.3f} >= {TARGET_CALMAR}")
    if not criteria:
        criteria.append(f"Sharpe {sm.get('sharpe_ratio',0):.3f} < {TARGET_SHARPE}")
        criteria.append(f"Calmar {sm.get('calmar_ratio',0):.3f} < {TARGET_CALMAR}")

    print(f"\n  Judgment: {status}")
    for c in criteria:
        print(f"    {c}")
    print(f"{'='*60}")

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Iteration backtest runner")
    parser.add_argument("--iteration", type=int, required=True, help="Iteration number")
    parser.add_argument(
        "--period", type=int, choices=[1, 2], default=2,
        help="Data period to test (default: 2)",
    )
    parser.add_argument(
        "--validate-all", action="store_true",
        help="Run on all periods for final validation",
    )
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    periods = [1, 2] if args.validate_all else [args.period]
    all_passed = True

    for period in periods:
        print(f"\n=== Running Iteration {args.iteration}, Period {period} ===")

        # Load data
        bars = load_bars(period)

        # Get date range for benchmark
        sample_bars = next(iter(bars.values()))
        start_date = sample_bars[0].timestamp.date().isoformat()
        end_date = sample_bars[-1].timestamp.date().isoformat()
        print(f"  Date range: {start_date} ~ {end_date}")

        # Run backtest
        print("  Running backtest...")
        result = run_backtest(bars)

        # Get benchmark
        print("  Fetching S&P 500 benchmark...")
        benchmark = get_sp500_benchmark(start_date, end_date)

        # Add benchmark to result
        result["benchmark_sp500"] = benchmark

        # Save result
        iter_str = f"{args.iteration:02d}"
        filename = f"iter_{iter_str}_period{period}.json"
        filepath = RESULTS_DIR / filename
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  Saved to {filepath.name}")

        # Print comparison
        passed = print_comparison(args.iteration, period, result["metrics"], benchmark)
        if not passed:
            all_passed = False

    if args.validate_all:
        print(f"\n{'='*60}")
        if all_passed:
            print("  MULTI-PERIOD VALIDATION: ALL PASSED")
            print("  Ready to commit + version bump + merge to beta")
        else:
            print("  MULTI-PERIOD VALIDATION: FAILED")
            print("  Continue iteration loop")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
```

**Step 2: Create results directory**

Run: `mkdir -p data/backtest_results/iterations`

**Step 3: Test the script (dry run with existing Period 2 data)**

Run: `python scripts/run_iteration_backtest.py --iteration 0 --period 2`
Expected: Runs backtest, shows comparison table with Sharpe/Calmar vs S&P 500

**Step 4: Commit**

```bash
git add scripts/run_iteration_backtest.py
git commit -m "feat: add iteration backtest runner with S&P 500 benchmark"
```

---

### Task 4: Download Period 1 Data

**Owner:** Dev-4 (devops-architect, scripts/)

**Step 1: Run the download script**

Run: `python scripts/download_historical_data.py --period 1`
Expected: Downloads ~450 symbols, saves to `data/historical_bars_period1.pkl`

**Step 2: Verify the data**

Run: `python -c "import pickle; d=pickle.load(open('data/historical_bars_period1.pkl','rb')); bars=d['bars']; s=next(iter(bars)); print(f'{len(bars)} symbols, {s}: {bars[s][0].timestamp.date()} ~ {bars[s][-1].timestamp.date()}')"`
Expected: ~450 symbols, date range approximately 2024-03 ~ 2025-02

**Step 3: Run baseline iteration 0 on both periods**

Run: `python scripts/run_iteration_backtest.py --iteration 0 --validate-all`
Expected: Shows Sharpe/Calmar for both periods, likely FAIL (baseline)

---

### Task 5: Execute Iteration Loop

**Owner:** Orchestrator (coordination), all teams involved

This is NOT code — it's the workflow the orchestrator executes repeatedly.

**Per-iteration workflow:**

```
ITERATION #N
─────────────

Step 5.1: Strategy Team Analysis
  - Dispatch: Strat-1~4 (business-panel-experts)
  - Input: data/backtest_results/iterations/iter_{N-1}_period2.json
  - Output: Change proposal (saved to data/backtest_results/iterations/iter_{N}_proposal.md)
  - Proposal type: PARAM_TUNE or NEW_STRATEGY

Step 5.2: Dev Team Implementation
  - Dispatch: Dev-2 (batch/) and/or Dev-3 (execution/, main.py)
  - Input: Proposal from Step 5.1
  - Constraints: File ownership enforced, FROZEN files need Orchestrator approval
  - Output: Code changes applied

Step 5.3: Test Team — Unit Tests
  - Dispatch: Test-1 (quality-engineer)
  - Input: Code changes from Step 5.2
  - Output: All tests passing
  - Run: python -m pytest tests/ -q

Step 5.4: Test Team — Backtest
  - Dispatch: Test-2 (performance-engineer)
  - Run: python scripts/run_iteration_backtest.py --iteration N --period 2
  - Output: iter_{N}_period2.json with Sharpe/Calmar comparison

Step 5.5: Result Evaluation (Orchestrator)
  - If Sharpe >= 1.0 OR Calmar >= 1.0:
      → Run: python scripts/run_iteration_backtest.py --iteration N --validate-all
      → If BOTH periods pass: DONE (commit + bump_version + merge to beta)
      → If only 1 passes: continue loop
  - If criteria not met:
      → Check 3-consecutive-no-improvement rule
      → Back to Step 5.1

Step 5.6: Commit iteration changes
  - git add [changed files]
  - git commit -m "feat: iteration N — [brief description of changes]"
```

**Stopping conditions:**
- Sharpe >= 1.0 OR Calmar >= 1.0 on BOTH periods → SUCCESS
- 15 iterations reached → STOP, user decision
- 3 consecutive no-improvement → force direction change (strategy team)

**Tracking:**
- Maintain a running table of iteration results in terminal output
- All results saved in data/backtest_results/iterations/

---

### Task 6: Final Validation and Release

**Owner:** Orchestrator + all teams

**Triggered when:** Iteration N passes on Period 2 (Sharpe >= 1.0 or Calmar >= 1.0)

**Step 1: Multi-period validation**

Run: `python scripts/run_iteration_backtest.py --iteration N --validate-all`
Expected: PASS on both periods

**Step 2: Full test suite**

Run: `python -m pytest tests/ -q`
Expected: All tests pass

**Step 3: Strategy team final review**

Dispatch: Strat-1~4 — review final parameter set for sanity

**Step 4: Commit + version bump + merge**

```bash
git add -A  # (specific files, not literally -A)
git commit -m "feat: strategy optimization iteration N — beat S&P 500"
python scripts/bump_version.py 3.2
```

---
