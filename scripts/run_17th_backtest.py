"""17th Backtest: MaxDD Risk Parameter Optimization

Configurations:
  17A: 2-strategy MR portfolio with risk improvements
       - Realized equity-based DD (no MTM spike contamination)
       - max_loss_per_trade 3% hard cap
       - GDR thresholds tightened (rsi_mr: 2.5%/5%, cons_down: 3%/6%)
       - Gap filter 3% (from 5%)
       - ema_cross_trend disabled

Reference: 16A: +4.4%, PF 1.241, MaxDD 30.0%, 109 trades, Sharpe 0.404

Target: MaxDD < 20%

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
logger = logging.getLogger("run_17th_backtest")

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

def _patch_for_17a():
    """Patch for 17A: 2-strategy MR with risk improvements.

    Changes from 16A:
    - Realized equity-based DD tracking (no MTM spikes)
    - max_loss_per_trade 3% hard cap (new)
    - GDR thresholds tightened: rsi_mr (0.025, 0.05), cons_down (0.03, 0.06)
    - Gap filter 3% (was 5%)
    - ema_cross_trend disabled
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

    logger.info("Patched for 17A: 2 strategies + risk improvements")


def _patch_for_16a_baseline():
    """Patch for 16A baseline (for comparison): original parameters."""
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
    bs._DEFAULT_GAP_THRESHOLD = 0.05
    bs._MAX_LOSS_PER_TRADE_PCT = 1.0  # effectively no cap (legacy)

    logger.info("Patched for 16A baseline: original risk parameters")


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
    print("  17th Backtest: MaxDD Risk Parameter Optimization")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 16A Baseline (for comparison) ---
    _patch_for_16a_baseline()
    result_16a = run_single(bars_by_symbol, 100_000.0, "16A-baseline")
    save_result(result_16a, "17_16a_baseline.json")
    print_summary("16A Baseline (original risk params, for comparison)", result_16a)

    # --- 17A: Risk improvements ---
    _patch_for_17a()
    result_17a = run_single(bars_by_symbol, 100_000.0, "17A")
    save_result(result_17a, "17a_risk_optimized.json")
    print_summary("17A: Risk Optimized (realized equity + hard cap + GDR + gap)", result_17a)

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    print(f"\n{'Config':<50} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 110)

    for label, r in [
        ("16A (baseline, gap 5%, old GDR)", result_16a),
        ("17A (realized eq, gap 3%, tight GDR, cap 3%)", result_17a),
    ]:
        m = r.metrics
        print(f"{label:<50} {m.get('total_return_pct', 0):>+7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # Delta analysis
    m_16a = result_16a.metrics
    m_17a = result_17a.metrics

    print(f"\n--- 16A -> 17A Delta ---")
    dd_delta = m_17a.get('max_drawdown_pct', 0) - m_16a.get('max_drawdown_pct', 0)
    ret_delta = m_17a.get('total_return_pct', 0) - m_16a.get('total_return_pct', 0)
    print(f"  MaxDD:   {m_16a.get('max_drawdown_pct', 0):.1f}% -> {m_17a.get('max_drawdown_pct', 0):.1f}% (delta: {dd_delta:+.1f}%)")
    print(f"  Return:  {m_16a.get('total_return_pct', 0):+.1f}% -> {m_17a.get('total_return_pct', 0):+.1f}% (delta: {ret_delta:+.1f}%)")
    print(f"  PF:      {m_16a.get('profit_factor', 0):.3f} -> {m_17a.get('profit_factor', 0):.3f}")
    print(f"  Trades:  {m_16a.get('total_trades', 0)} -> {m_17a.get('total_trades', 0)}")
    print(f"  Sharpe:  {m_16a.get('sharpe_ratio', 0):.3f} -> {m_17a.get('sharpe_ratio', 0):.3f}")

    # max_loss_cap exit analysis
    max_loss_cap_trades = [t for t in result_17a.trades if t.exit_reason == "max_loss_cap"]
    if max_loss_cap_trades:
        print(f"\n--- max_loss_cap Exits (17A) ---")
        print(f"  Count: {len(max_loss_cap_trades)}")
        total_cap_pnl = sum(t.pnl for t in max_loss_cap_trades)
        print(f"  Total PnL: ${total_cap_pnl:,.2f}")
        avg_cap_loss = total_cap_pnl / len(max_loss_cap_trades)
        print(f"  Avg Loss: ${avg_cap_loss:,.2f}")
        for t in max_loss_cap_trades:
            print(f"    {t.symbol} {t.strategy} {t.direction} entry={t.entry_date} "
                  f"exit={t.exit_date} pnl=${t.pnl:,.2f} mae={t.mae_pct:.2%}")
    else:
        print(f"\n--- max_loss_cap: No trades hit the 3% hard cap ---")

    # GDR tier activation analysis
    print(f"\n--- Exit Reason Distribution ---")
    for label, result in [("16A", result_16a), ("17A", result_17a)]:
        exit_dist = defaultdict(int)
        for t in result.trades:
            exit_dist[t.exit_reason] += 1
        reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(exit_dist.items()))
        print(f"  {label}: {reasons_str}")

    # Target check
    print(f"\n--- TARGET CHECK ---")
    target_dd = 20.0
    actual_dd = m_17a.get('max_drawdown_pct', 0)
    if actual_dd <= target_dd:
        print(f"  PASS: MaxDD {actual_dd:.1f}% <= {target_dd:.0f}% target")
    else:
        print(f"  FAIL: MaxDD {actual_dd:.1f}% > {target_dd:.0f}% target")
        print(f"  Additional measures may be needed")

    print("\nDone.")


if __name__ == "__main__":
    main()
