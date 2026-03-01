"""18th Backtest: P0 Exit Rule Optimization

Configurations:
  18A: P0-optimized exit rules (current code defaults)
       - rsi_mr short SL: 0.75 ATR (was 1.5)
       - cons_down SL: 1.2 ATR (was 1.0), risk 1.5% (was 2%)
       - 2-stage SL upgrade: BE@0.7 ATR, profit lock@1.2 ATR (+0.4 ATR)
       - All other params unchanged from 17A

  17A Baseline: Previous parameters (for comparison)
       - rsi_mr short SL: 1.5 ATR
       - cons_down SL: 1.0 ATR, risk 2%
       - Single breakeven@0.6 ATR

Reference: 17A: +8.7%, PF 1.525, MaxDD 29.1%, 112 trades, Sharpe 0.574

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
logger = logging.getLogger("run_18th_backtest")

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

def _patch_for_18a():
    """Patch for 18A: P0-optimized exit rules (current code defaults).

    P0 changes are already in the codebase defaults:
    - exit_rules.py: rsi_mr short SL=0.75, cons_down SL=1.2, 2-stage BE
    - batch_simulator.py: cons_down risk=1.5%

    Only need to ensure strategy set and GDR config match 17A.
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down"})
    # Risk values are already P0-optimized in code defaults:
    # rsi_mr: 0.01, cons_down: 0.015
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down"]
    bs._PER_STRATEGY_GDR = True
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.025, 0.05),
        "consecutive_down": (0.03, 0.06),
    }
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3
    bs._DEFAULT_GAP_THRESHOLD = 0.03
    bs._MAX_LOSS_PER_TRADE_PCT = 0.03

    logger.info("Patched for 18A: P0-optimized exit rules (using code defaults)")


def _patch_for_17a_baseline():
    """Patch for 17A baseline: revert to pre-P0 parameters for comparison."""
    import autotrader.backtest.batch_simulator as bs
    import autotrader.execution.exit_rules as er
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down"})
    bs._STRATEGY_BASE_RISK = {
        "rsi_mean_reversion": 0.01,
        "consecutive_down": 0.02,        # was 2% before P0-3
    }
    bs._STRATEGY_GDR_THRESHOLDS = {
        "rsi_mean_reversion": (0.025, 0.05),
        "consecutive_down": (0.03, 0.06),
    }
    bs._STRATEGY_NAMES = ["rsi_mean_reversion", "consecutive_down"]
    bs._PER_STRATEGY_GDR = True
    bs._PORTFOLIO_SAFETY_NET_DD = 0.20
    bs._PORTFOLIO_SAFETY_NET_RECOVERY = 0.15
    bs._MAX_DAILY_ENTRIES = 3
    bs._DEFAULT_GAP_THRESHOLD = 0.03
    bs._MAX_LOSS_PER_TRADE_PCT = 0.03

    # Revert exit_rules to pre-P0 values
    er._SL_ATR_MULT["rsi_mean_reversion"]["short"] = 1.5   # was 0.75 (P0-1)
    er._SL_ATR_MULT["consecutive_down"]["long"] = 1.0       # was 1.2 (P0-3)

    # Revert to single-stage breakeven (P0-2)
    er._STAGE1_BE_ACTIVATION_ATR = 0.6
    er._STAGE2_PROFIT_ACTIVATION_ATR = 999.0  # effectively disable Stage 2
    er._STAGE2_PROFIT_LOCK_ATR = 0.0

    logger.info("Patched for 17A baseline: pre-P0 parameters")


def _restore_18a_defaults():
    """Restore P0-optimized defaults after 17A baseline run."""
    import autotrader.execution.exit_rules as er
    import autotrader.backtest.batch_simulator as bs

    er._SL_ATR_MULT["rsi_mean_reversion"]["short"] = 0.75
    er._SL_ATR_MULT["consecutive_down"]["long"] = 1.2
    er._STAGE1_BE_ACTIVATION_ATR = 0.7
    er._STAGE2_PROFIT_ACTIVATION_ATR = 1.2
    er._STAGE2_PROFIT_LOCK_ATR = 0.4
    bs._STRATEGY_BASE_RISK["consecutive_down"] = 0.015

    logger.info("Restored 18A (P0) defaults")


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
    print("  18th Backtest: P0 Exit Rule Optimization")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 17A Baseline (for comparison) ---
    _patch_for_17a_baseline()
    result_17a = run_single(bars_by_symbol, 100_000.0, "17A-baseline")
    save_result(result_17a, "18_17a_baseline.json")
    print_summary("17A Baseline (pre-P0 parameters)", result_17a)

    # Restore P0 defaults before running 18A
    _restore_18a_defaults()

    # --- 18A: P0-optimized ---
    _patch_for_18a()
    result_18a = run_single(bars_by_symbol, 100_000.0, "18A")
    save_result(result_18a, "18a_p0_optimized.json")
    print_summary("18A: P0-Optimized Exit Rules", result_18a)

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    print(f"\n{'Config':<50} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 110)

    for label, r in [
        ("17A (baseline, pre-P0)", result_17a),
        ("18A (P0: SL opt + 2-stage BE + risk adj)", result_18a),
    ]:
        m = r.metrics
        print(f"{label:<50} {m.get('total_return_pct', 0):>+7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # Delta analysis
    m_17a = result_17a.metrics
    m_18a = result_18a.metrics

    print(f"\n--- 17A -> 18A Delta ---")
    dd_delta = m_18a.get('max_drawdown_pct', 0) - m_17a.get('max_drawdown_pct', 0)
    ret_delta = m_18a.get('total_return_pct', 0) - m_17a.get('total_return_pct', 0)
    pf_delta = m_18a.get('profit_factor', 0) - m_17a.get('profit_factor', 0)
    sharpe_delta = m_18a.get('sharpe_ratio', 0) - m_17a.get('sharpe_ratio', 0)
    print(f"  MaxDD:   {m_17a.get('max_drawdown_pct', 0):.1f}% -> {m_18a.get('max_drawdown_pct', 0):.1f}% (delta: {dd_delta:+.1f}%)")
    print(f"  Return:  {m_17a.get('total_return_pct', 0):+.1f}% -> {m_18a.get('total_return_pct', 0):+.1f}% (delta: {ret_delta:+.1f}%)")
    print(f"  PF:      {m_17a.get('profit_factor', 0):.3f} -> {m_18a.get('profit_factor', 0):.3f} (delta: {pf_delta:+.3f})")
    print(f"  Trades:  {m_17a.get('total_trades', 0)} -> {m_18a.get('total_trades', 0)}")
    print(f"  Sharpe:  {m_17a.get('sharpe_ratio', 0):.3f} -> {m_18a.get('sharpe_ratio', 0):.3f} (delta: {sharpe_delta:+.3f})")

    # P0-specific analysis
    print(f"\n--- P0 Change Impact Analysis ---")

    # rsi_mr short SL change impact
    rsi_mr_17a = result_17a.per_strategy_metrics.get("rsi_mean_reversion", {})
    rsi_mr_18a = result_18a.per_strategy_metrics.get("rsi_mean_reversion", {})
    print(f"\n  [rsi_mean_reversion] (P0-1: short SL 1.5->0.75 ATR)")
    print(f"    Trades: {rsi_mr_17a.get('total_trades', 0)} -> {rsi_mr_18a.get('total_trades', 0)}")
    print(f"    WR: {rsi_mr_17a.get('win_rate', 0):.1%} -> {rsi_mr_18a.get('win_rate', 0):.1%}")
    print(f"    PF: {rsi_mr_17a.get('profit_factor', 0):.3f} -> {rsi_mr_18a.get('profit_factor', 0):.3f}")
    print(f"    PnL: ${rsi_mr_17a.get('total_pnl', 0):,.2f} -> ${rsi_mr_18a.get('total_pnl', 0):,.2f}")

    # Short-specific analysis
    short_17a = [t for t in result_17a.trades if t.strategy == "rsi_mean_reversion" and t.direction == "short"]
    short_18a = [t for t in result_18a.trades if t.strategy == "rsi_mean_reversion" and t.direction == "short"]
    if short_17a:
        short_wr_17a = sum(1 for t in short_17a if t.pnl > 0) / len(short_17a) if short_17a else 0
        short_pnl_17a = sum(t.pnl for t in short_17a)
    else:
        short_wr_17a, short_pnl_17a = 0, 0
    if short_18a:
        short_wr_18a = sum(1 for t in short_18a if t.pnl > 0) / len(short_18a) if short_18a else 0
        short_pnl_18a = sum(t.pnl for t in short_18a)
    else:
        short_wr_18a, short_pnl_18a = 0, 0
    print(f"    Short trades: {len(short_17a)} -> {len(short_18a)}")
    print(f"    Short WR: {short_wr_17a:.1%} -> {short_wr_18a:.1%}")
    print(f"    Short PnL: ${short_pnl_17a:,.2f} -> ${short_pnl_18a:,.2f}")

    # cons_down impact
    cd_17a = result_17a.per_strategy_metrics.get("consecutive_down", {})
    cd_18a = result_18a.per_strategy_metrics.get("consecutive_down", {})
    print(f"\n  [consecutive_down] (P0-3: SL 1.0->1.2 ATR, risk 2%->1.5%)")
    print(f"    Trades: {cd_17a.get('total_trades', 0)} -> {cd_18a.get('total_trades', 0)}")
    print(f"    WR: {cd_17a.get('win_rate', 0):.1%} -> {cd_18a.get('win_rate', 0):.1%}")
    print(f"    PF: {cd_17a.get('profit_factor', 0):.3f} -> {cd_18a.get('profit_factor', 0):.3f}")
    print(f"    PnL: ${cd_17a.get('total_pnl', 0):,.2f} -> ${cd_18a.get('total_pnl', 0):,.2f}")

    # Exit reason distribution
    print(f"\n--- Exit Reason Distribution ---")
    for label, result in [("17A", result_17a), ("18A", result_18a)]:
        exit_dist = defaultdict(int)
        for t in result.trades:
            exit_dist[t.exit_reason] += 1
        reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(exit_dist.items()))
        print(f"  {label}: {reasons_str}")

    # 2-stage BE impact: check if any trades benefited from Stage 2
    # (trades that would have been stopped at entry but survived due to profit lock)
    print(f"\n--- 2-Stage SL Upgrade Impact (P0-2) ---")
    for label, result in [("17A", result_17a), ("18A", result_18a)]:
        sl_trades = [t for t in result.trades if t.exit_reason == "stop_loss"]
        sl_winners = [t for t in sl_trades if t.pnl > 0]
        print(f"  {label}: SL exits={len(sl_trades)}, SL winners={len(sl_winners)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
