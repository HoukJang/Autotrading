"""MFE/MAE trade analysis engine.

Computes comprehensive MFE/MAE statistics from backtest trade records:
per-strategy distributions, edge ratios, heat captured, SL/TP efficiency,
optimal parameter suggestions, exit reason breakdowns, and win/loss profiles.

Pure Python implementation (no numpy/pandas) suitable for 100-200 trade sets.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Default SL/TP ATR multipliers (mirrors exit_rules.py)
_DEFAULT_SL_ATR: dict[str, dict[str, float]] = {
    "rsi_mean_reversion": {"long": 1.0, "short": 1.5},
    "consecutive_down": {"long": 1.0},
    "ema_cross_trend": {"long": 3.0, "short": 3.0},
}

_DEFAULT_TP_ATR: dict[str, float | None] = {
    "rsi_mean_reversion": None,
    "consecutive_down": None,
    "ema_cross_trend": 5.0,
}


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DistributionStats:
    """Statistical distribution summary."""

    count: int
    mean: float
    median: float
    p25: float
    p75: float
    min: float
    max: float
    std_dev: float


@dataclass(frozen=True)
class StrategyMFEMAE:
    """Per-strategy MFE/MAE distribution and derived metrics."""

    strategy: str
    trade_count: int
    mfe: DistributionStats
    mae: DistributionStats
    edge_ratio: float  # mean_mfe / mean_mae
    heat_captured: float  # avg(pnl_pct / mfe_pct) for winners with mfe > 0


@dataclass(frozen=True)
class ExitReasonStats:
    """Performance breakdown by exit reason."""

    exit_reason: str
    count: int
    avg_pnl_pct: float
    win_rate: float
    avg_mfe_pct: float
    avg_mae_pct: float


@dataclass(frozen=True)
class HoldDurationBucket:
    """MFE/MAE stats grouped by bars_held duration."""

    bucket: str  # "2", "3", "4", "5+"
    count: int
    avg_mfe_pct: float
    avg_mae_pct: float
    win_rate: float
    edge_ratio: float


@dataclass(frozen=True)
class SLTPEfficiency:
    """Actual MAE/MFE vs configured SL/TP distance comparison."""

    strategy: str
    direction: str
    sl_atr_mult: float
    mae_median_atr: float
    mae_p75_atr: float
    sl_utilization: float  # median_mae / sl_distance
    tp_atr_mult: float | None  # None = indicator-based TP
    mfe_median_atr: float
    mfe_p75_atr: float


@dataclass(frozen=True)
class OptimalSLTP:
    """Percentile-based SL/TP ATR suggestions."""

    strategy: str
    direction: str
    mae_p50_atr: float
    mae_p75_atr: float
    mae_p90_atr: float
    suggested_sl_atr: float  # p75 * 1.1 buffer
    mfe_p50_atr: float
    mfe_p75_atr: float
    mfe_p90_atr: float
    suggested_tp_atr: float | None  # None for indicator-based strategies


@dataclass(frozen=True)
class WinLossProfile:
    """Separate MFE/MAE patterns for winning vs losing trades."""

    win_count: int
    loss_count: int
    win_mfe: DistributionStats
    win_mae: DistributionStats
    loss_mfe: DistributionStats
    loss_mae: DistributionStats
    win_edge_ratio: float
    loss_edge_ratio: float


@dataclass(frozen=True)
class AnalysisResult:
    """Complete MFE/MAE analysis container."""

    total_trades: int
    overall_mfe: DistributionStats
    overall_mae: DistributionStats
    overall_edge_ratio: float
    overall_heat_captured: float
    by_strategy: dict[str, StrategyMFEMAE]
    by_exit_reason: list[ExitReasonStats]
    by_hold_duration: list[HoldDurationBucket]
    sltp_efficiency: list[SLTPEfficiency]
    optimal_sltp: list[OptimalSLTP]
    win_loss_profile: WinLossProfile
    strategy_filter: str | None


# ---------------------------------------------------------------------------
# Pure-Python statistics helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[float], p: float) -> float:
    """Compute p-th percentile (0-100) via linear interpolation."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _std_dev(values: list[float], mean: float) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance**0.5


def _compute_dist(values: list[float]) -> DistributionStats:
    """Compute distribution stats from a list of values."""
    if not values:
        return DistributionStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    s = sorted(values)
    mean = sum(s) / len(s)
    return DistributionStats(
        count=len(s),
        mean=mean,
        median=_percentile(s, 50),
        p25=_percentile(s, 25),
        p75=_percentile(s, 75),
        min=s[0],
        max=s[-1],
        std_dev=_std_dev(s, mean),
    )


def _safe_div(a: float, b: float) -> float:
    """Safe division returning 0.0 on zero denominator."""
    return a / b if b != 0 else 0.0


# ---------------------------------------------------------------------------
# TradeAnalyzer
# ---------------------------------------------------------------------------


class TradeAnalyzer:
    """MFE/MAE trade analysis engine.

    Accepts backtest trade dicts and computes comprehensive MFE/MAE
    statistics, SL/TP efficiency analysis, and optimal parameter suggestions.
    """

    def __init__(
        self,
        trades: list[dict],
        sl_config: dict[str, dict[str, float]] | None = None,
        tp_config: dict[str, float | None] | None = None,
    ) -> None:
        self._trades = trades
        self._sl = sl_config or _DEFAULT_SL_ATR
        self._tp = tp_config or _DEFAULT_TP_ATR

    def analyze(self, strategy_filter: str | None = None) -> AnalysisResult:
        """Run full MFE/MAE analysis pipeline."""
        trades = self._trades
        if strategy_filter:
            trades = [t for t in trades if t.get("strategy") == strategy_filter]

        if not trades:
            empty = _compute_dist([])
            return AnalysisResult(
                total_trades=0,
                overall_mfe=empty,
                overall_mae=empty,
                overall_edge_ratio=0.0,
                overall_heat_captured=0.0,
                by_strategy={},
                by_exit_reason=[],
                by_hold_duration=[],
                sltp_efficiency=[],
                optimal_sltp=[],
                win_loss_profile=WinLossProfile(
                    0, 0, empty, empty, empty, empty, 0.0, 0.0
                ),
                strategy_filter=strategy_filter,
            )

        mfes = [t["mfe_pct"] for t in trades]
        maes = [t["mae_pct"] for t in trades]
        overall_mfe = _compute_dist(mfes)
        overall_mae = _compute_dist(maes)

        return AnalysisResult(
            total_trades=len(trades),
            overall_mfe=overall_mfe,
            overall_mae=overall_mae,
            overall_edge_ratio=_safe_div(overall_mfe.mean, overall_mae.mean),
            overall_heat_captured=self._compute_heat_captured(trades),
            by_strategy=self._analyze_by_strategy(trades),
            by_exit_reason=self._analyze_by_exit_reason(trades),
            by_hold_duration=self._analyze_by_hold_duration(trades),
            sltp_efficiency=self._analyze_sltp_efficiency(trades),
            optimal_sltp=self._analyze_optimal_sltp(trades),
            win_loss_profile=self._analyze_win_loss(trades),
            strategy_filter=strategy_filter,
        )

    # -- private helpers -----------------------------------------------------

    def _compute_heat_captured(self, trades: list[dict]) -> float:
        """Average ratio of realized PnL to MFE for winning trades."""
        ratios: list[float] = []
        for t in trades:
            pnl_pct = t.get("pnl_pct", 0.0)
            mfe_pct = t.get("mfe_pct", 0.0)
            if pnl_pct > 0 and mfe_pct > 0.0001:
                ratios.append(pnl_pct / mfe_pct)
        return sum(ratios) / len(ratios) if ratios else 0.0

    def _analyze_by_strategy(
        self, trades: list[dict]
    ) -> dict[str, StrategyMFEMAE]:
        groups: dict[str, list[dict]] = {}
        for t in trades:
            groups.setdefault(t.get("strategy", "unknown"), []).append(t)

        result: dict[str, StrategyMFEMAE] = {}
        for strategy, group in sorted(groups.items()):
            mfe_dist = _compute_dist([t["mfe_pct"] for t in group])
            mae_dist = _compute_dist([t["mae_pct"] for t in group])
            result[strategy] = StrategyMFEMAE(
                strategy=strategy,
                trade_count=len(group),
                mfe=mfe_dist,
                mae=mae_dist,
                edge_ratio=_safe_div(mfe_dist.mean, mae_dist.mean),
                heat_captured=self._compute_heat_captured(group),
            )
        return result

    def _analyze_by_exit_reason(self, trades: list[dict]) -> list[ExitReasonStats]:
        groups: dict[str, list[dict]] = {}
        for t in trades:
            groups.setdefault(t.get("exit_reason", "unknown"), []).append(t)

        result: list[ExitReasonStats] = []
        for reason, group in sorted(groups.items()):
            pnls = [t.get("pnl_pct", 0.0) for t in group]
            wins = sum(1 for p in pnls if p > 0)
            result.append(
                ExitReasonStats(
                    exit_reason=reason,
                    count=len(group),
                    avg_pnl_pct=sum(pnls) / len(pnls),
                    win_rate=wins / len(group),
                    avg_mfe_pct=sum(t["mfe_pct"] for t in group) / len(group),
                    avg_mae_pct=sum(t["mae_pct"] for t in group) / len(group),
                )
            )
        return result

    def _analyze_by_hold_duration(
        self, trades: list[dict]
    ) -> list[HoldDurationBucket]:
        buckets: dict[str, list[dict]] = {}
        for t in trades:
            bars = t.get("bars_held", 0)
            label = str(bars) if bars <= 4 else "5+"
            buckets.setdefault(label, []).append(t)

        result: list[HoldDurationBucket] = []
        for label in sorted(buckets.keys(), key=lambda x: (len(x), x)):
            group = buckets[label]
            avg_mfe = sum(t["mfe_pct"] for t in group) / len(group)
            avg_mae = sum(t["mae_pct"] for t in group) / len(group)
            wins = sum(1 for t in group if t.get("pnl_pct", 0.0) > 0)
            result.append(
                HoldDurationBucket(
                    bucket=label,
                    count=len(group),
                    avg_mfe_pct=avg_mfe,
                    avg_mae_pct=avg_mae,
                    win_rate=wins / len(group),
                    edge_ratio=_safe_div(avg_mfe, avg_mae),
                )
            )
        return result

    def _to_atr(self, trade: dict, pct_field: str) -> float | None:
        """Convert a percentage field to ATR terms."""
        pct = trade.get(pct_field, 0.0)
        price = trade.get("entry_price", 0.0)
        atr = trade.get("entry_atr", 0.0)
        if price <= 0 or atr <= 0:
            return None
        return (pct * price) / atr

    def _analyze_sltp_efficiency(self, trades: list[dict]) -> list[SLTPEfficiency]:
        groups: dict[tuple[str, str], list[dict]] = {}
        for t in trades:
            key = (t.get("strategy", ""), t.get("direction", ""))
            groups.setdefault(key, []).append(t)

        result: list[SLTPEfficiency] = []
        for (strategy, direction), group in sorted(groups.items()):
            sl_config = self._sl.get(strategy, {})
            sl_mult = sl_config.get(direction)
            if sl_mult is None:
                continue

            mae_atrs: list[float] = []
            mfe_atrs: list[float] = []
            for t in group:
                mae_a = self._to_atr(t, "mae_pct")
                mfe_a = self._to_atr(t, "mfe_pct")
                if mae_a is not None:
                    mae_atrs.append(mae_a)
                if mfe_a is not None:
                    mfe_atrs.append(mfe_a)

            if not mae_atrs:
                continue

            mae_sorted = sorted(mae_atrs)
            mfe_sorted = sorted(mfe_atrs)
            mae_med = _percentile(mae_sorted, 50)
            mae_p75 = _percentile(mae_sorted, 75)
            mfe_med = _percentile(mfe_sorted, 50) if mfe_sorted else 0.0
            mfe_p75 = _percentile(mfe_sorted, 75) if mfe_sorted else 0.0

            result.append(
                SLTPEfficiency(
                    strategy=strategy,
                    direction=direction,
                    sl_atr_mult=sl_mult,
                    mae_median_atr=mae_med,
                    mae_p75_atr=mae_p75,
                    sl_utilization=_safe_div(mae_med, sl_mult),
                    tp_atr_mult=self._tp.get(strategy),
                    mfe_median_atr=mfe_med,
                    mfe_p75_atr=mfe_p75,
                )
            )
        return result

    def _analyze_optimal_sltp(self, trades: list[dict]) -> list[OptimalSLTP]:
        groups: dict[tuple[str, str], list[dict]] = {}
        for t in trades:
            key = (t.get("strategy", ""), t.get("direction", ""))
            groups.setdefault(key, []).append(t)

        result: list[OptimalSLTP] = []
        for (strategy, direction), group in sorted(groups.items()):
            mae_atrs: list[float] = []
            mfe_atrs: list[float] = []
            for t in group:
                mae_a = self._to_atr(t, "mae_pct")
                mfe_a = self._to_atr(t, "mfe_pct")
                if mae_a is not None:
                    mae_atrs.append(mae_a)
                if mfe_a is not None:
                    mfe_atrs.append(mfe_a)

            if not mae_atrs:
                continue

            mae_sorted = sorted(mae_atrs)
            mfe_sorted = sorted(mfe_atrs)

            mae_p50 = _percentile(mae_sorted, 50)
            mae_p75 = _percentile(mae_sorted, 75)
            mae_p90 = _percentile(mae_sorted, 90)
            mfe_p50 = _percentile(mfe_sorted, 50) if mfe_sorted else 0.0
            mfe_p75 = _percentile(mfe_sorted, 75) if mfe_sorted else 0.0
            mfe_p90 = _percentile(mfe_sorted, 90) if mfe_sorted else 0.0

            suggested_sl = round(mae_p75 * 1.1, 2)
            tp_config = self._tp.get(strategy)
            suggested_tp = None if tp_config is None else round(mfe_p50, 2)

            result.append(
                OptimalSLTP(
                    strategy=strategy,
                    direction=direction,
                    mae_p50_atr=mae_p50,
                    mae_p75_atr=mae_p75,
                    mae_p90_atr=mae_p90,
                    suggested_sl_atr=suggested_sl,
                    mfe_p50_atr=mfe_p50,
                    mfe_p75_atr=mfe_p75,
                    mfe_p90_atr=mfe_p90,
                    suggested_tp_atr=suggested_tp,
                )
            )
        return result

    def _analyze_win_loss(self, trades: list[dict]) -> WinLossProfile:
        wins = [t for t in trades if t.get("pnl_pct", 0.0) > 0]
        losses = [t for t in trades if t.get("pnl_pct", 0.0) <= 0]
        win_mfe = _compute_dist([t["mfe_pct"] for t in wins])
        win_mae = _compute_dist([t["mae_pct"] for t in wins])
        loss_mfe = _compute_dist([t["mfe_pct"] for t in losses])
        loss_mae = _compute_dist([t["mae_pct"] for t in losses])

        return WinLossProfile(
            win_count=len(wins),
            loss_count=len(losses),
            win_mfe=win_mfe,
            win_mae=win_mae,
            loss_mfe=loss_mfe,
            loss_mae=loss_mae,
            win_edge_ratio=_safe_div(win_mfe.mean, win_mae.mean),
            loss_edge_ratio=_safe_div(loss_mfe.mean, loss_mae.mean),
        )
