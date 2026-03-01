"""19th Backtest: P1 Take-Profit & Short Entry Optimization

Configurations:
  18A Baseline: Pre-P1 parameters (for comparison)
       - rsi_mr TP condition: OR(RSI>50, pct_b>0.50) -- old logic
       - RSI_OVERBOUGHT: 75 -- old threshold (more short entries)
       - batch_simulator TP: OR logic with RSI>50/pct_b>0.50

  19A: P1-optimized (current code defaults in exit_rules.py)
       - P1-1: rsi_mr TP condition: AND(RSI>55, pct_b>0.55) -- stricter TP
       - P1-2: RSI_OVERBOUGHT: 80 -- fewer short entries
       - P1-3: actual stop_distance to allocation (live-only, N/A for backtest)

Reference: 18A: (see 18th backtest output for baseline comparison)

Note: P1-3 only affects main.py (live trading), NOT batch_simulator.py,
so the backtest cannot measure P1-3 impact. Focus is on P1-1 and P1-2.

All tests use real Alpaca cached data, $100,000 initial capital.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import sys
import time
import types
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
logger = logging.getLogger("run_19th_backtest")

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

def _common_bs_config():
    """Apply common batch_simulator settings shared by both runs."""
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
    from autotrader.strategy.consecutive_down import ConsecutiveDown

    bs._STRATEGY_CLASSES = [RsiMeanReversion, ConsecutiveDown]
    bs._GROUP_A = frozenset({"rsi_mean_reversion", "consecutive_down"})
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


def _build_patched_tp_method(rsi_long_target, pct_b_long_target,
                              rsi_short_target, pct_b_short_target,
                              use_and_logic: bool):
    """Build a replacement _check_sl_tp_intraday method with configurable TP thresholds.

    The batch_simulator._check_sl_tp_intraday has hardcoded TP thresholds for
    rsi_mean_reversion (RSI>50, pct_b>0.50 with OR logic). This factory creates
    a patched version that uses the supplied thresholds and AND/OR logic.

    Parameters:
        rsi_long_target: RSI threshold for long TP (e.g. 50.0 or 55.0)
        pct_b_long_target: BB %B threshold for long TP (e.g. 0.50 or 0.55)
        rsi_short_target: RSI threshold for short TP (e.g. 50.0 or 45.0)
        pct_b_short_target: BB %B threshold for short TP (e.g. 0.50 or 0.45)
        use_and_logic: True = AND(RSI, pct_b), False = OR(RSI, pct_b)
    """
    import autotrader.backtest.batch_simulator as bs

    # Capture the original module-level imports needed by the method
    _SL_ATR_MULT_ref = bs._SL_ATR_MULT if hasattr(bs, '_SL_ATR_MULT') else None
    _TP_ATR_MULT_ref = bs._TP_ATR_MULT if hasattr(bs, '_TP_ATR_MULT') else None

    def _check_sl_tp_intraday(
        self,
        held,       # HeldPosition
        bar,        # Bar
        indicators: dict,
        bar_history=None,
    ):
        """Patched SL/TP check with configurable TP thresholds."""
        from autotrader.execution.exit_rules import (
            _SL_ATR_MULT,
            _TP_ATR_MULT,
            _TRAILING_STRATEGIES,
            _TRAILING_ATR_MULT,
            _TRAILING_ACTIVATION_ATR,
            _STAGE1_BE_ACTIVATION_ATR,
            _STAGE2_PROFIT_ACTIVATION_ATR,
            _STAGE2_PROFIT_LOCK_ATR,
        )

        atr = self._get_atr(indicators, held.entry_atr)
        strategy = held.strategy
        direction = held.direction

        # --- Stop Loss check (with 2-stage SL upgrade) ---
        sl_mult = _SL_ATR_MULT.get(strategy, {}).get(direction, 2.0)
        sl_distance = sl_mult * atr
        if direction == "long":
            sl_price = held.entry_price - sl_distance
            # 2-stage SL upgrade
            if held.highest_price >= held.entry_price + _STAGE2_PROFIT_ACTIVATION_ATR * atr:
                sl_price = max(sl_price, held.entry_price + _STAGE2_PROFIT_LOCK_ATR * atr)
            elif held.highest_price >= held.entry_price + _STAGE1_BE_ACTIVATION_ATR * atr:
                sl_price = max(sl_price, held.entry_price)
            sl_hit = bar.low <= sl_price
        else:
            sl_price = held.entry_price + sl_distance
            if held.lowest_price <= held.entry_price - _STAGE2_PROFIT_ACTIVATION_ATR * atr:
                sl_price = min(sl_price, held.entry_price - _STAGE2_PROFIT_LOCK_ATR * atr)
            elif held.lowest_price <= held.entry_price - _STAGE1_BE_ACTIVATION_ATR * atr:
                sl_price = min(sl_price, held.entry_price)
            sl_hit = bar.high >= sl_price

        # --- Take Profit check ---
        tp_price = None
        tp_hit = False
        tp_atr_mult = _TP_ATR_MULT.get(strategy)
        if tp_atr_mult is not None:
            if direction == "long":
                tp_price = held.entry_price + tp_atr_mult * atr
                tp_hit = bar.high >= tp_price
            else:
                tp_price = held.entry_price - tp_atr_mult * atr
                tp_hit = bar.low <= tp_price
        else:
            # Indicator-based TP (rsi/bb) -- PATCHED THRESHOLDS
            rsi = indicators.get("RSI_14")
            bb = indicators.get("BBANDS_20")
            pct_b = bb.get("pct_b", 0.5) if isinstance(bb, dict) else None

            if strategy == "rsi_mean_reversion":
                if direction == "long":
                    if use_and_logic:
                        tp_hit = (rsi is not None and rsi > rsi_long_target) and (pct_b is not None and pct_b > pct_b_long_target)
                    else:
                        tp_hit = (rsi is not None and rsi > rsi_long_target) or (pct_b is not None and pct_b > pct_b_long_target)
                else:
                    if use_and_logic:
                        tp_hit = (rsi is not None and rsi < rsi_short_target) and (pct_b is not None and pct_b < pct_b_short_target)
                    else:
                        tp_hit = (rsi is not None and rsi < rsi_short_target) or (pct_b is not None and pct_b < pct_b_short_target)
            elif strategy == "consecutive_down":
                ema_5 = indicators.get("EMA_5")
                if ema_5 is not None and bar.close > ema_5:
                    tp_hit = True

            if tp_hit:
                tp_price = bar.close

            # Auxiliary ATR TP for rsi_mean_reversion: cap at 2.0 ATR
            if not tp_hit and strategy == "rsi_mean_reversion":
                atr_tp_mult = 2.0
                if direction == "long":
                    atr_tp_price = held.entry_price + atr_tp_mult * atr
                    if bar.high >= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price
                else:
                    atr_tp_price = held.entry_price - atr_tp_mult * atr
                    if bar.low <= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price

        # --- Trailing Stop check ---
        trailing_hit = False
        trailing_price = None
        if strategy in _TRAILING_STRATEGIES and held.bars_held >= 2:
            activation_atr = _TRAILING_ACTIVATION_ATR.get(strategy, 1.5)
            if direction == "long":
                if held.highest_price >= held.entry_price + activation_atr * atr:
                    trail_stop = max(
                        held.entry_price,
                        held.highest_price - _TRAILING_ATR_MULT * atr,
                    )
                    if bar.low <= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop
            else:
                if held.lowest_price <= held.entry_price - activation_atr * atr:
                    trail_stop = min(
                        held.entry_price,
                        held.lowest_price + _TRAILING_ATR_MULT * atr,
                    )
                    if bar.high >= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop

        # --- Resolution: determine which exit triggered ---
        if sl_hit and tp_hit:
            # Both hit on same bar: disambiguate by open proximity
            if direction == "long":
                sl_dist = abs(bar.open - sl_price) if sl_price else float("inf")
                tp_dist = abs(bar.open - tp_price) if tp_price else float("inf")
            else:
                sl_dist = abs(bar.open - sl_price) if sl_price else float("inf")
                tp_dist = abs(bar.open - tp_price) if tp_price else float("inf")
            if sl_dist <= tp_dist:
                return (sl_price, "stop_loss")
            else:
                return (tp_price, "take_profit")
        elif sl_hit:
            return (sl_price, "stop_loss")
        elif tp_hit:
            reason = "take_profit"
            if strategy == "rsi_mean_reversion" and tp_price == bar.close:
                # Indicator-based TP: label with RSI/BB details
                rsi_val = indicators.get("RSI_14", 0)
                bb = indicators.get("BBANDS_20")
                pct_b_val = bb.get("pct_b", 0.5) if isinstance(bb, dict) else 0.5
                reason = f"tp_rsi_{rsi_val:.1f}_bb_{pct_b_val:.2f}"
            elif strategy == "consecutive_down" and tp_price == bar.close:
                reason = "tp_ema5"
            return (tp_price, reason)
        elif trailing_hit:
            return (trailing_price, "trailing_stop")

        return (None, None)

    return _check_sl_tp_intraday


def _patch_for_18a_baseline():
    """Patch for 18A baseline: revert P1 changes for comparison.

    Reverts:
    - P1-1: TP condition back to OR(RSI>50, pct_b>0.50)
    - P1-2: RSI_OVERBOUGHT back to 75
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

    _common_bs_config()

    # P1-2 revert: RSI_OVERBOUGHT 80 -> 75
    RsiMeanReversion.RSI_OVERBOUGHT = 75.0

    # P1-1 revert: TP condition to OR logic with RSI>50, pct_b>0.50
    patched_method = _build_patched_tp_method(
        rsi_long_target=50.0,
        pct_b_long_target=0.50,
        rsi_short_target=50.0,
        pct_b_short_target=0.50,
        use_and_logic=False,  # OR logic (old behavior)
    )
    bs.BatchBacktester._check_sl_tp_intraday = patched_method

    logger.info("Patched for 18A baseline: OR(RSI>50, pct_b>0.50), RSI_OVERBOUGHT=75")


def _patch_for_19a():
    """Patch for 19A: P1-optimized TP and entry thresholds.

    Applies:
    - P1-1: TP condition to AND(RSI>55, pct_b>0.55) / AND(RSI<45, pct_b<0.45) for shorts
    - P1-2: RSI_OVERBOUGHT = 80 (already code default, but ensure it's set)
    """
    import autotrader.backtest.batch_simulator as bs
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

    _common_bs_config()

    # P1-2: RSI_OVERBOUGHT = 80 (restore code default)
    RsiMeanReversion.RSI_OVERBOUGHT = 80.0

    # P1-1: TP condition to AND logic with RSI>55, pct_b>0.55
    patched_method = _build_patched_tp_method(
        rsi_long_target=55.0,
        pct_b_long_target=0.55,
        rsi_short_target=45.0,
        pct_b_short_target=0.45,
        use_and_logic=True,  # AND logic (new behavior, matching exit_rules.py)
    )
    bs.BatchBacktester._check_sl_tp_intraday = patched_method

    logger.info("Patched for 19A: AND(RSI>55, pct_b>0.55), RSI_OVERBOUGHT=80")


def _restore_defaults():
    """Restore all defaults after runs."""
    from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

    RsiMeanReversion.RSI_OVERBOUGHT = 80.0
    logger.info("Restored code defaults")


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
# P1-Specific Analysis
# ---------------------------------------------------------------------------

def _analyze_p1_impact(result_baseline: Any, result_19a: Any):
    """Detailed P1 change impact analysis."""
    print(f"\n\n{'='*65}")
    print("  P1 CHANGE IMPACT ANALYSIS")
    print(f"{'='*65}")

    # --- P1-2: RSI_OVERBOUGHT 75->80 (fewer short entries) ---
    print(f"\n--- P1-2: RSI_OVERBOUGHT Impact (75 -> 80) ---")
    print("  (Higher threshold = fewer short entries)")

    short_base = [t for t in result_baseline.trades
                  if t.strategy == "rsi_mean_reversion" and t.direction == "short"]
    short_19a = [t for t in result_19a.trades
                 if t.strategy == "rsi_mean_reversion" and t.direction == "short"]

    def _short_stats(trades):
        if not trades:
            return 0, 0.0, 0.0, 0.0
        wins = sum(1 for t in trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in trades)
        avg_pnl = total_pnl / len(trades)
        wr = wins / len(trades)
        return len(trades), wr, total_pnl, avg_pnl

    n_b, wr_b, pnl_b, avg_b = _short_stats(short_base)
    n_19, wr_19, pnl_19, avg_19 = _short_stats(short_19a)

    print(f"  Short trade count:    {n_b} -> {n_19} (delta: {n_19 - n_b:+d})")
    print(f"  Short win rate:       {wr_b:.1%} -> {wr_19:.1%}")
    print(f"  Short total PnL:      ${pnl_b:,.2f} -> ${pnl_19:,.2f} (delta: ${pnl_19 - pnl_b:+,.2f})")
    print(f"  Short avg PnL/trade:  ${avg_b:,.2f} -> ${avg_19:,.2f}")

    # --- P1-1: TP condition AND vs OR logic ---
    print(f"\n--- P1-1: TP Condition Impact ---")
    print("  OR(RSI>50, pct_b>0.50) -> AND(RSI>55, pct_b>0.55)")
    print("  (Stricter TP = hold longer, capture more mean reversion)")

    def _tp_analysis(trades, label):
        tp_rsi_bb = [t for t in trades if t.exit_reason.startswith("tp_rsi_")]
        tp_atr = [t for t in trades if t.exit_reason == "take_profit"
                  and t.strategy == "rsi_mean_reversion"]
        tp_ema5 = [t for t in trades if t.exit_reason == "tp_ema5"]
        sl = [t for t in trades if t.exit_reason == "stop_loss"]
        time_exit = [t for t in trades if t.exit_reason == "time_exit"]

        rsi_mr_trades = [t for t in trades if t.strategy == "rsi_mean_reversion"]
        avg_hold = (sum(t.bars_held for t in rsi_mr_trades) / len(rsi_mr_trades)
                    if rsi_mr_trades else 0)

        print(f"\n  [{label}] rsi_mean_reversion exits:")
        print(f"    TP (RSI/BB indicator): {len(tp_rsi_bb)} trades")
        print(f"    TP (ATR cap 2.0):      {len(tp_atr)} trades")
        print(f"    Stop Loss:             {len(sl)} trades (rsi_mr)")
        print(f"    Time Exit:             {len(time_exit)} trades (rsi_mr)")
        print(f"    Avg hold (rsi_mr):     {avg_hold:.1f} bars")

        if tp_rsi_bb:
            tp_pnl = sum(t.pnl for t in tp_rsi_bb)
            tp_avg = tp_pnl / len(tp_rsi_bb)
            print(f"    TP RSI/BB total PnL:   ${tp_pnl:,.2f}  avg: ${tp_avg:,.2f}")

        return {
            "tp_rsi_bb": len(tp_rsi_bb),
            "tp_atr": len(tp_atr),
            "sl": len(sl),
            "time_exit": len(time_exit),
            "avg_hold": avg_hold,
        }

    stats_b = _tp_analysis(result_baseline.trades, "18A Baseline")
    stats_19 = _tp_analysis(result_19a.trades, "19A P1-Opt")

    # TP shift analysis
    print(f"\n  TP Shift Summary:")
    print(f"    TP RSI/BB exits:  {stats_b['tp_rsi_bb']} -> {stats_19['tp_rsi_bb']} "
          f"(delta: {stats_19['tp_rsi_bb'] - stats_b['tp_rsi_bb']:+d})")
    print(f"    TP ATR cap exits: {stats_b['tp_atr']} -> {stats_19['tp_atr']} "
          f"(delta: {stats_19['tp_atr'] - stats_b['tp_atr']:+d})")
    print(f"    Time exits:       {stats_b['time_exit']} -> {stats_19['time_exit']} "
          f"(delta: {stats_19['time_exit'] - stats_b['time_exit']:+d})")
    print(f"    Avg hold shift:   {stats_b['avg_hold']:.1f} -> {stats_19['avg_hold']:.1f} bars")

    # --- Heat captured analysis ---
    print(f"\n--- Heat Captured (MFE Utilization) ---")
    print("  Measures how much of the peak profit was captured at exit")

    def _heat_captured(trades, strategy_filter=None):
        filtered = trades
        if strategy_filter:
            filtered = [t for t in trades if t.strategy == strategy_filter]
        if not filtered:
            return 0.0, 0.0, 0
        total_mfe = sum(t.mfe_pct for t in filtered)
        total_actual = sum(t.pnl_pct for t in filtered)
        avg_capture = (total_actual / total_mfe * 100) if total_mfe > 0 else 0
        return avg_capture, total_mfe, len(filtered)

    cap_b_all, mfe_b_all, n_b_all = _heat_captured(result_baseline.trades)
    cap_19_all, mfe_19_all, n_19_all = _heat_captured(result_19a.trades)

    print(f"\n  Overall heat captured:")
    print(f"    18A: {cap_b_all:.1f}% of MFE ({n_b_all} trades)")
    print(f"    19A: {cap_19_all:.1f}% of MFE ({n_19_all} trades)")

    cap_b_rsi, _, n_b_rsi = _heat_captured(result_baseline.trades, "rsi_mean_reversion")
    cap_19_rsi, _, n_19_rsi = _heat_captured(result_19a.trades, "rsi_mean_reversion")

    print(f"\n  rsi_mean_reversion heat captured:")
    print(f"    18A: {cap_b_rsi:.1f}% of MFE ({n_b_rsi} trades)")
    print(f"    19A: {cap_19_rsi:.1f}% of MFE ({n_19_rsi} trades)")

    # Long vs short heat captured
    for direction in ["long", "short"]:
        base_dir = [t for t in result_baseline.trades
                    if t.strategy == "rsi_mean_reversion" and t.direction == direction]
        opt_dir = [t for t in result_19a.trades
                   if t.strategy == "rsi_mean_reversion" and t.direction == direction]

        if base_dir or opt_dir:
            cap_b_d = (sum(t.pnl_pct for t in base_dir) / sum(t.mfe_pct for t in base_dir) * 100
                       if base_dir and sum(t.mfe_pct for t in base_dir) > 0 else 0)
            cap_19_d = (sum(t.pnl_pct for t in opt_dir) / sum(t.mfe_pct for t in opt_dir) * 100
                        if opt_dir and sum(t.mfe_pct for t in opt_dir) > 0 else 0)
            print(f"\n  rsi_mr {direction} heat captured:")
            print(f"    18A: {cap_b_d:.1f}% ({len(base_dir)} trades)")
            print(f"    19A: {cap_19_d:.1f}% ({len(opt_dir)} trades)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  19th Backtest: P1 Take-Profit & Short Entry Optimization")
    print("=" * 65)

    bars_by_symbol = load_data()

    # --- 18A Baseline (pre-P1 parameters, for comparison) ---
    _patch_for_18a_baseline()
    result_baseline = run_single(bars_by_symbol, 100_000.0, "18A-baseline")
    save_result(result_baseline, "19_18a_baseline.json")
    print_summary("18A Baseline (pre-P1: OR TP, RSI_OB=75)", result_baseline)

    # Restore defaults before running 19A
    _restore_defaults()

    # --- 19A: P1-optimized ---
    _patch_for_19a()
    result_19a = run_single(bars_by_symbol, 100_000.0, "19A")
    save_result(result_19a, "19a_p1_optimized.json")
    print_summary("19A: P1-Optimized (AND TP, RSI_OB=80)", result_19a)

    # Restore after all runs
    _restore_defaults()

    # --- Cross-configuration comparison ---
    print(f"\n\n{'='*65}")
    print("  CROSS-CONFIGURATION COMPARISON")
    print(f"{'='*65}")

    print(f"\n{'Config':<50} {'Return':>8} {'PF':>8} {'MaxDD':>8} {'Trades':>8} {'Sharpe':>8} {'Final$':>12}")
    print("-" * 110)

    for label, r in [
        ("18A (baseline: OR TP, RSI_OB=75)", result_baseline),
        ("19A (P1: AND TP RSI>55/BB>0.55, RSI_OB=80)", result_19a),
    ]:
        m = r.metrics
        print(f"{label:<50} {m.get('total_return_pct', 0):>+7.1f}% {m.get('profit_factor', 0):>8.3f} {m.get('max_drawdown_pct', 0):>7.1f}% {m.get('total_trades', 0):>8} {m.get('sharpe_ratio', 0):>8.3f} ${m.get('final_equity', 0):>11,.2f}")

    # Delta analysis
    m_b = result_baseline.metrics
    m_19 = result_19a.metrics

    print(f"\n--- 18A -> 19A Delta ---")
    dd_delta = m_19.get('max_drawdown_pct', 0) - m_b.get('max_drawdown_pct', 0)
    ret_delta = m_19.get('total_return_pct', 0) - m_b.get('total_return_pct', 0)
    pf_delta = m_19.get('profit_factor', 0) - m_b.get('profit_factor', 0)
    sharpe_delta = m_19.get('sharpe_ratio', 0) - m_b.get('sharpe_ratio', 0)
    print(f"  MaxDD:   {m_b.get('max_drawdown_pct', 0):.1f}% -> {m_19.get('max_drawdown_pct', 0):.1f}% (delta: {dd_delta:+.1f}%)")
    print(f"  Return:  {m_b.get('total_return_pct', 0):+.1f}% -> {m_19.get('total_return_pct', 0):+.1f}% (delta: {ret_delta:+.1f}%)")
    print(f"  PF:      {m_b.get('profit_factor', 0):.3f} -> {m_19.get('profit_factor', 0):.3f} (delta: {pf_delta:+.3f})")
    print(f"  Trades:  {m_b.get('total_trades', 0)} -> {m_19.get('total_trades', 0)}")
    print(f"  Sharpe:  {m_b.get('sharpe_ratio', 0):.3f} -> {m_19.get('sharpe_ratio', 0):.3f} (delta: {sharpe_delta:+.3f})")

    # Per-strategy comparison
    print(f"\n--- Per-Strategy Delta ---")
    for strat in ["rsi_mean_reversion", "consecutive_down"]:
        sm_b = result_baseline.per_strategy_metrics.get(strat, {})
        sm_19 = result_19a.per_strategy_metrics.get(strat, {})
        print(f"\n  [{strat}]")
        print(f"    Trades: {sm_b.get('total_trades', 0)} -> {sm_19.get('total_trades', 0)}")
        print(f"    WR: {sm_b.get('win_rate', 0):.1%} -> {sm_19.get('win_rate', 0):.1%}")
        print(f"    PF: {sm_b.get('profit_factor', 0):.3f} -> {sm_19.get('profit_factor', 0):.3f}")
        print(f"    PnL: ${sm_b.get('total_pnl', 0):,.2f} -> ${sm_19.get('total_pnl', 0):,.2f}")

    # Exit reason distribution
    print(f"\n--- Exit Reason Distribution ---")
    for label, result in [("18A", result_baseline), ("19A", result_19a)]:
        exit_dist = defaultdict(int)
        for t in result.trades:
            exit_dist[t.exit_reason] += 1
        reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(exit_dist.items()))
        print(f"  {label}: {reasons_str}")

    # P1-specific impact analysis
    _analyze_p1_impact(result_baseline, result_19a)

    print("\nDone.")


if __name__ == "__main__":
    main()
