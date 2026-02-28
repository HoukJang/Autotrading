"""14th Backtest: rsi_mr Defense + adx_breakout Strategy

Configurations:
  14A: rsi_mr defense only (ADX<20 + slope filter + regime guard, 2 strategies)
       -> measures combined defense effect vs 13A baseline
  14B: Full portfolio (rsi_mr defense + adx_breakout, 3 strategies)
       -> tests trend-following diversification

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
logger = logging.getLogger("run_14th_backtest")

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

def _patch_for_14a():
    """Patch for 14A: rsi_mr defense only (2 strategies).

    rsi_mr already has ADX<20, slope filter, and regime guard baked in.
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

    # Ensure EMA_10 and EMA_21 are in required indicators check
    # (already added by Dev-3 to _has_required_indicators)

    logger.info("Patched for 14A: 2 strategies, rsi_mr defense (ADX<20 + slope + regime guard)")


def _patch_for_14b():
    """Patch for 14B: Full portfolio with adx_breakout (3 strategies)."""
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown
    from autotrader.strategy.adx_breakout import AdxBreakout

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown, AdxBreakout]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down", "adx_breakout"})
    bs._STRATEGY_BASE_RISK = {
        "rsi_mean_reversion": 0.01,
        "consecutive_down": 0.02,
        "adx_breakout": 0.015,
    }
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.03, 0.06),
        "consecutive_down": (0.04, 0.08),
        "adx_breakout": (0.04, 0.08),
    }
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down", "adx_breakout"]
    bs._PER_STRATEGY_GDR = True
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3

    logger.info("Patched for 14B: 3 strategies (rsi_mr defense + adx_breakout)")


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
    print("  14th Backtest: rsi_mr Defense + adx_breakout Strategy")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 14A: rsi_mr defense only ---
    _patch_for_14a()
    result_14a = run_single(bars_by_symbol, 100_000.0, "14A")
    save_result(result_14a, "14a_rsi_mr_defense.json")
    print_summary("14A: rsi_mr Defense Only (2 strategies)", result_14a)

    # --- 14B: Full portfolio ---
    _patch_for_14b()
    result_14b = run_single(bars_by_symbol, 100_000.0, "14B")
    save_result(result_14b, "14b_full_portfolio.json")
    print_summary("14B: Full Portfolio (3 strategies)", result_14b)

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    # Reference: 13A best result (from memory)
    print(f"\n{'Config':<35} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 95)

    # 13A reference (manual entry from 13th report)
    print(f"{'13A (ref: vol_div removed)':<35} {'7.5%':>8} {'1.309':>8} {'41.3%':>8} {'155':>8} {'0.676':>8} {'$107,503':>12}")

    for label, r in [("14A (rsi_mr defense)", result_14a), ("14B (full portfolio)", result_14b)]:
        m = r.metrics
        print(f"{label:<35} {m.get('total_return_pct', 0):>7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # Regime guard analysis
    print(f"\n--- Regime Guard Analysis ---")
    for label, r in [("14A", result_14a), ("14B", result_14b)]:
        regime_guard_trades = [t for t in r.trades if t.exit_reason == "regime_guard"]
        rsi_trades = [t for t in r.trades if t.strategy == "rsi_mean_reversion"]
        print(f"  {label}: regime_guard exits = {len(regime_guard_trades)}, rsi_mr total = {len(rsi_trades)}")
        if regime_guard_trades:
            rg_pnls = [t.pnl for t in regime_guard_trades]
            print(f"    regime_guard avg PnL: ${sum(rg_pnls)/len(rg_pnls):,.2f}, total: ${sum(rg_pnls):,.2f}")

    # adx_breakout analysis (14B only)
    adx_trades = [t for t in result_14b.trades if t.strategy == "adx_breakout"]
    if adx_trades:
        print(f"\n--- adx_breakout Analysis (14B) ---")
        print(f"  Trades: {len(adx_trades)}")
        print(f"  Win Rate: {sum(1 for t in adx_trades if t.pnl > 0)/len(adx_trades):.1%}")
        wins = sum(t.pnl for t in adx_trades if t.pnl > 0)
        losses = abs(sum(t.pnl for t in adx_trades if t.pnl < 0))
        print(f"  PF: {wins/losses:.3f}" if losses > 0 else "  PF: inf")
        print(f"  Total PnL: ${sum(t.pnl for t in adx_trades):,.2f}")
        exit_dist = defaultdict(int)
        for t in adx_trades:
            exit_dist[t.exit_reason] += 1
        print(f"  Exit reasons: {dict(exit_dist)}")
    else:
        print(f"\n--- adx_breakout: NO TRADES in 14B ---")

    print("\nDone.")


if __name__ == "__main__":
    main()
