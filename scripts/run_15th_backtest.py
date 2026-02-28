"""15th Backtest: rsi_mr Recalibration + ema_cross_trend Strategy

Configurations:
  15A: rsi_mr recalibrated + consecutive_down (2 strategies, mean reversion only)
       -> measures ADX<23 and slope>1.5 recalibration effect
  15B: Full portfolio (rsi_mr + consecutive_down + ema_cross_trend, 3 strategies)
       -> tests EMA crossover trend-following diversification

Reference: 14A: +1.9%, PF 1.146, DD 4.2%, 86 trades, Sharpe 0.354

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
logger = logging.getLogger("run_15th_backtest")

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

def _patch_for_15a():
    """Patch for 15A: rsi_mr recalibrated + consecutive_down (2 strategies).

    rsi_mr now has ADX<23 (relaxed) and slope threshold > 1.5 (relaxed).
    This runs the 2-strategy portfolio (rsi_mr + consecutive_down).
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

    logger.info("Patched for 15A: 2 strategies, rsi_mr recalibrated (ADX<23 + slope>1.5)")


def _patch_for_15b():
    """Patch for 15B: Full portfolio with ema_cross_trend (3 strategies)."""
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

    logger.info("Patched for 15B: 3 strategies (rsi_mr recalibrated + ema_cross_trend)")


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
    print("  15th Backtest: rsi_mr Recalibration + ema_cross_trend Strategy")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 15A: rsi_mr recalibrated + consecutive_down ---
    _patch_for_15a()
    result_15a = run_single(bars_by_symbol, 100_000.0, "15A")
    save_result(result_15a, "15a_rsi_mr_recalibrated.json")
    print_summary("15A: rsi_mr Recalibrated (2 strategies)", result_15a)

    # --- 15B: Full portfolio ---
    _patch_for_15b()
    result_15b = run_single(bars_by_symbol, 100_000.0, "15B")
    save_result(result_15b, "15b_full_portfolio.json")
    print_summary("15B: Full Portfolio (3 strategies)", result_15b)

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    # Reference: 14A result
    print(f"\n{'Config':<40} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 100)

    # 14A reference (manual entry from 14th report)
    print(f"{'14A (ref: rsi_mr defense only)':<40} {'+1.9%':>8} {'1.146':>8} {'4.2%':>8} {'86':>8} {'0.354':>8} {'$101,900':>12}")

    for label, r in [("15A (rsi_mr recalibrated)", result_15a), ("15B (full portfolio)", result_15b)]:
        m = r.metrics
        print(f"{label:<40} {m.get('total_return_pct', 0):>+7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # Regime guard analysis
    print(f"\n--- Regime Guard Analysis ---")
    for label, r in [("15A", result_15a), ("15B", result_15b)]:
        regime_guard_trades = [t for t in r.trades if t.exit_reason == "regime_guard"]
        rsi_trades = [t for t in r.trades if t.strategy == "rsi_mean_reversion"]
        print(f"  {label}: regime_guard exits = {len(regime_guard_trades)}, rsi_mr total = {len(rsi_trades)}")
        if regime_guard_trades:
            rg_pnls = [t.pnl for t in regime_guard_trades]
            print(f"    regime_guard avg PnL: ${sum(rg_pnls)/len(rg_pnls):,.2f}, total: ${sum(rg_pnls):,.2f}")

    # ema_cross_trend analysis (15B only)
    ema_trades = [t for t in result_15b.trades if t.strategy == "ema_cross_trend"]
    if ema_trades:
        print(f"\n--- ema_cross_trend Analysis (15B) ---")
        print(f"  Trades: {len(ema_trades)}")
        long_trades = [t for t in ema_trades if t.direction == "long"]
        short_trades = [t for t in ema_trades if t.direction == "short"]
        print(f"  Long: {len(long_trades)}, Short: {len(short_trades)}")
        print(f"  Win Rate: {sum(1 for t in ema_trades if t.pnl > 0)/len(ema_trades):.1%}")
        wins = sum(t.pnl for t in ema_trades if t.pnl > 0)
        losses = abs(sum(t.pnl for t in ema_trades if t.pnl < 0))
        print(f"  PF: {wins/losses:.3f}" if losses > 0 else "  PF: inf")
        print(f"  Total PnL: ${sum(t.pnl for t in ema_trades):,.2f}")
        avg_hold = sum(t.bars_held for t in ema_trades) / len(ema_trades) if ema_trades else 0
        print(f"  Avg Hold: {avg_hold:.1f} days")
        exit_dist = defaultdict(int)
        for t in ema_trades:
            exit_dist[t.exit_reason] += 1
        print(f"  Exit reasons: {dict(exit_dist)}")

        # MFE/MAE analysis
        if any(hasattr(t, 'mfe_pct') for t in ema_trades):
            avg_mfe = sum(t.mfe_pct for t in ema_trades) / len(ema_trades) * 100
            avg_mae = sum(t.mae_pct for t in ema_trades) / len(ema_trades) * 100
            print(f"  Avg MFE: {avg_mfe:.2f}%, Avg MAE: {avg_mae:.2f}%")
    else:
        print(f"\n--- ema_cross_trend: NO TRADES in 15B ---")

    # rsi_mr recalibration analysis
    print(f"\n--- rsi_mr Recalibration Effect ---")
    rsi_15a = [t for t in result_15a.trades if t.strategy == "rsi_mean_reversion"]
    print(f"  15A rsi_mr trades: {len(rsi_15a)}")
    if rsi_15a:
        rsi_wins = sum(1 for t in rsi_15a if t.pnl > 0)
        rsi_pnl = sum(t.pnl for t in rsi_15a)
        print(f"  WR: {rsi_wins/len(rsi_15a):.1%}, Total PnL: ${rsi_pnl:,.2f}")
        rsi_losses = abs(sum(t.pnl for t in rsi_15a if t.pnl < 0))
        rsi_profit = sum(t.pnl for t in rsi_15a if t.pnl > 0)
        if rsi_losses > 0:
            print(f"  PF: {rsi_profit/rsi_losses:.3f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
