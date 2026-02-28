"""16th Backtest: Conservative ema_cross_trend Filters

Configurations:
  16A: Same as 15A (rsi_mr recalibrated + consecutive_down, 2 strategies baseline)
       -> measures baseline without trend strategy
  16B: Full portfolio with conservative ema_cross_trend (3 strategies)
       -> tests ADX>28, ADX rising +2.0/3bars, 2 consecutive closes, SL 3.0 ATR, TP 5.0 ATR

Reference: 15A: +4.4%, PF 1.241, DD 30.0%, 109 trades

Red line check: if ema_cross_trend WR < 30% or PF < 1.0 -> FAIL

All tests use real Alpaca cached data, $100,000 initial capital.
"""
from __future__ import annotations

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
logger = logging.getLogger("run_16th_backtest")

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

def _patch_for_16a():
    """Patch for 16A: rsi_mr recalibrated + consecutive_down (2 strategies baseline).

    Same as 15A for comparison baseline.
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

    logger.info("Patched for 16A: 2 strategies baseline (same as 15A)")


def _patch_for_16b():
    """Patch for 16B: Full portfolio with conservative ema_cross_trend (3 strategies)."""
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown
    from autotrader.strategy.ema_cross_trend import EmaCrossTrend

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown, EmaCrossTrend]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down", "ema_cross_trend"})
    bs._STRATEGY_BASE_RISK = {
        "rsi_mean_reversion": 0.01,
        "consecutive_down": 0.02,
        "ema_cross_trend": 0.015,
    }
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.03, 0.06),
        "consecutive_down": (0.04, 0.08),
        "ema_cross_trend": (0.04, 0.08),
    }
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down", "ema_cross_trend"]
    bs._PER_STRATEGY_GDR = True
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3

    logger.info("Patched for 16B: 3 strategies (conservative ema_cross_trend)")


# ---------------------------------------------------------------------------
# Single backtest run
# ---------------------------------------------------------------------------

def run_single(
    bars_by_symbol: dict,
    capital: float,
    label: str,
) -> Any:
    """Run a single backtest and return the result."""
    from autotrader.backtest.batch_simulator import BatchBacktester

    bt = BatchBacktester(
        initial_capital=capital,
        use_per_strategy_gdr=True,
    )

    t0 = time.time()
    result = bt.run(bars_by_symbol)
    elapsed = time.time() - t0
    logger.info("[%s] Completed in %.1fs: %d trades", label, elapsed, result.metrics.get("total_trades", 0))

    return result


def save_result(result: Any, filename: str):
    """Save backtest result to JSON."""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    trades = []
    for t in result.trades:
        trades.append({
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "strategy": t.strategy,
            "direction": t.direction,
            "entry_date": str(t.entry_date),
            "exit_date": str(t.exit_date),
            "entry_price": round(t.entry_price, 4),
            "exit_price": round(t.exit_price, 4),
            "qty": t.qty,
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct, 6),
            "bars_held": t.bars_held,
            "exit_reason": t.exit_reason,
            "mfe_pct": round(t.mfe_pct, 6),
            "mae_pct": round(t.mae_pct, 6),
            "entry_atr": round(t.entry_atr, 4),
            "signal_strength": round(t.signal_strength, 4),
            "gap_pct": round(t.gap_pct, 6),
        })

    data = {
        "config": result.config,
        "metrics": result.metrics,
        "per_strategy_metrics": result.per_strategy_metrics,
        "trades": trades,
        "equity_curve": [(str(d), round(e, 2)) for d, e in result.equity_curve],
    }

    outpath = os.path.join(_OUTPUT_DIR, filename)
    with open(outpath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Saved result: %s", outpath)


def print_summary(label: str, result: Any):
    """Print a concise summary of backtest results."""
    m = result.metrics
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    print(f"  Total Trades:    {m.get('total_trades', 0)}")
    print(f"  Win Rate:        {m.get('win_rate', 0):.1%}")
    print(f"  Profit Factor:   {m.get('profit_factor', 0):.3f}")
    print(f"  Total Return:    {m.get('total_return_pct', 0):.1f}%")
    print(f"  Sharpe Ratio:    {m.get('sharpe_ratio', 0):.3f}")
    print(f"  Sortino Ratio:   {m.get('sortino_ratio', 0):.3f}")
    print(f"  Max Drawdown:    {m.get('max_drawdown_pct', 0):.1f}%")
    print(f"  Calmar Ratio:    {m.get('calmar_ratio', 0):.3f}")
    print(f"  Total PnL:       ${m.get('total_pnl', 0):,.2f}")
    print(f"  Final Equity:    ${m.get('final_equity', 0):,.2f}")

    # Per-strategy breakdown
    for strat_name, sm in result.per_strategy_metrics.items():
        print(f"\n  [{strat_name}]")
        print(f"    Trades: {sm.get('total_trades', 0)}  WR: {sm.get('win_rate', 0):.1%}  PF: {sm.get('profit_factor', 0):.3f}  PnL: ${sm.get('total_pnl', 0):,.2f}  AvgHold: {sm.get('avg_hold_days', 0):.1f}d  MaxCL: {sm.get('max_consec_loss', 0)}")
        exit_reasons = sm.get("exit_reasons", {})
        if exit_reasons:
            reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(exit_reasons.items()))
            print(f"    Exits: {reasons_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  16th Backtest: Conservative ema_cross_trend Filters")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 16A: Baseline (same as 15A) ---
    _patch_for_16a()
    result_16a = run_single(bars_by_symbol, 100_000.0, "16A")
    save_result(result_16a, "16a_baseline_2strategy.json")
    print_summary("16A: Baseline (2 strategies, same as 15A)", result_16a)

    # --- 16B: Full portfolio with conservative ema_cross_trend ---
    _patch_for_16b()
    result_16b = run_single(bars_by_symbol, 100_000.0, "16B")
    save_result(result_16b, "16b_conservative_ema_cross.json")
    print_summary("16B: Conservative ema_cross_trend (3 strategies)", result_16b)

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    # Reference: 15A result
    print(f"\n{'Config':<45} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 105)

    # 15A reference (manual entry from 15th report)
    print(f"{'15A (ref: rsi_mr recalibrated, 2 strat)':<45} {'+4.4%':>8} {'1.241':>8} {'30.0%':>8} {'109':>8} {'---':>8} {'$104,400':>12}")

    for label, r in [("16A (baseline 2-strat)", result_16a), ("16B (conservative ema_cross)", result_16b)]:
        m = r.metrics
        print(f"{label:<45} {m.get('total_return_pct', 0):>+7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # ema_cross_trend analysis (16B only)
    ema_trades = [t for t in result_16b.trades if t.strategy == "ema_cross_trend"]
    if ema_trades:
        print(f"\n--- ema_cross_trend Analysis (16B) ---")
        print(f"  Trades: {len(ema_trades)}")
        long_trades = [t for t in ema_trades if t.direction == "long"]
        short_trades = [t for t in ema_trades if t.direction == "short"]
        print(f"  Long: {len(long_trades)}, Short: {len(short_trades)}")
        ema_wr = sum(1 for t in ema_trades if t.pnl > 0) / len(ema_trades)
        print(f"  Win Rate: {ema_wr:.1%}")
        wins = sum(t.pnl for t in ema_trades if t.pnl > 0)
        losses = abs(sum(t.pnl for t in ema_trades if t.pnl < 0))
        ema_pf = wins / losses if losses > 0 else float("inf")
        print(f"  PF: {ema_pf:.3f}" if losses > 0 else "  PF: inf")
        print(f"  Total PnL: ${sum(t.pnl for t in ema_trades):,.2f}")
        avg_hold = sum(t.bars_held for t in ema_trades) / len(ema_trades)
        print(f"  Avg Hold: {avg_hold:.1f} days")
        exit_dist = defaultdict(int)
        for t in ema_trades:
            exit_dist[t.exit_reason] += 1
        print(f"  Exit reasons: {dict(exit_dist)}")

        # MFE/MAE analysis
        if any(hasattr(t, "mfe_pct") for t in ema_trades):
            avg_mfe = sum(t.mfe_pct for t in ema_trades) / len(ema_trades) * 100
            avg_mae = sum(t.mae_pct for t in ema_trades) / len(ema_trades) * 100
            print(f"  Avg MFE: {avg_mfe:.2f}%, Avg MAE: {avg_mae:.2f}%")

        # Red line check
        print(f"\n--- RED LINE CHECK ---")
        if ema_wr < 0.30 or ema_pf < 1.0:
            print(f"  FAIL: ema_cross_trend WR={ema_wr:.1%}, PF={ema_pf:.3f}")
            print(f"  RECOMMENDATION: Drop trend strategy, optimize 15A (2-strategy MR)")
        else:
            print(f"  PASS: ema_cross_trend WR={ema_wr:.1%}, PF={ema_pf:.3f}")
            print(f"  Trend strategy viable with conservative filters")
    else:
        print(f"\n--- ema_cross_trend: NO TRADES in 16B ---")
        print(f"\n--- RED LINE CHECK ---")
        print(f"  FAIL: ema_cross_trend generated 0 trades")
        print(f"  RECOMMENDATION: Relax conservative filters or drop trend strategy")

    # Conservative filter impact
    print(f"\n--- Conservative Filter Impact ---")
    print(f"  ADX threshold: 25 -> 28 (higher bar for trending confirmation)")
    print(f"  ADX rising: +2.0 over 3 bars (new filter)")
    print(f"  Momentum: 2 consecutive closes in direction (new filter)")
    print(f"  SL: 2.5 -> 3.0 ATR (wider stop loss)")
    print(f"  TP: 4.0 -> 5.0 ATR (wider take profit)")

    # Compare 16A vs 16B
    m_a = result_16a.metrics
    m_b = result_16b.metrics
    print(f"\n--- 16A vs 16B Delta ---")
    print(f"  Return: {m_a.get('total_return_pct', 0):+.1f}% -> {m_b.get('total_return_pct', 0):+.1f}% (delta: {m_b.get('total_return_pct', 0) - m_a.get('total_return_pct', 0):+.1f}%)")
    print(f"  PF: {m_a.get('profit_factor', 0):.3f} -> {m_b.get('profit_factor', 0):.3f}")
    print(f"  MaxDD: {m_a.get('max_drawdown_pct', 0):.1f}% -> {m_b.get('max_drawdown_pct', 0):.1f}%")
    print(f"  Trades: {m_a.get('total_trades', 0)} -> {m_b.get('total_trades', 0)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
