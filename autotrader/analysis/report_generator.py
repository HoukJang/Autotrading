"""Text report generation for MFE/MAE trade analysis.

Produces structured plain-text reports from AnalysisResult objects,
including single-run reports and A/B comparison reports.
"""
from __future__ import annotations

from autotrader.analysis.trade_analyzer import AnalysisResult, DistributionStats


def _pct(v: float) -> str:
    """Format ratio as percentage string (0.03 -> '3.00%')."""
    return f"{v * 100:.2f}%"


def _f2(v: float) -> str:
    """Format to 2 decimal places."""
    return f"{v:.2f}"


class ReportGenerator:
    """Generate a text report from MFE/MAE analysis results."""

    def __init__(self, result: AnalysisResult) -> None:
        self._r = result

    def generate(self) -> str:
        """Generate complete multi-section report."""
        sections = [
            self._header(),
            self._overview(),
            self._strategy_mfe_mae(),
            self._edge_ratio(),
            self._heat_captured(),
            self._sltp_efficiency(),
            self._optimal_sltp(),
            self._exit_reason(),
            self._hold_duration(),
            self._win_loss_profile(),
        ]
        return "\n\n".join(sections)

    def _header(self) -> str:
        title = "MFE/MAE TRADE ANALYSIS REPORT"
        if self._r.strategy_filter:
            title += f" [{self._r.strategy_filter}]"
        return f"{'=' * 64}\n  {title}\n{'=' * 64}"

    def _overview(self) -> str:
        r = self._r
        lines = [
            "  1. OVERVIEW",
            f"  Total Trades:          {r.total_trades}",
            f"  Overall Edge Ratio:    {_f2(r.overall_edge_ratio)} (MFE/MAE)",
            f"  Overall Heat Captured: {_pct(r.overall_heat_captured)}",
            f"  Avg MFE:               {_pct(r.overall_mfe.mean)}",
            f"  Avg MAE:               {_pct(r.overall_mae.mean)}",
        ]
        return "\n".join(lines)

    def _strategy_mfe_mae(self) -> str:
        lines = [
            "  2. MFE/MAE BY STRATEGY",
            f"  {'Strategy':<25} {'Trades':>6} {'MFE Mean':>9} "
            f"{'MAE Mean':>9} {'Edge':>6} {'Heat':>7}",
            f"  {'-' * 25} {'-' * 6} {'-' * 9} "
            f"{'-' * 9} {'-' * 6} {'-' * 7}",
        ]
        for s in self._r.by_strategy.values():
            lines.append(
                f"  {s.strategy:<25} {s.trade_count:>6} "
                f"{_pct(s.mfe.mean):>9} {_pct(s.mae.mean):>9} "
                f"{_f2(s.edge_ratio):>6} {_pct(s.heat_captured):>7}"
            )
        return "\n".join(lines)

    def _dist_detail(self, label: str, d: DistributionStats) -> str:
        return (
            f"  {label}: "
            f"min={_pct(d.min)} p25={_pct(d.p25)} med={_pct(d.median)} "
            f"p75={_pct(d.p75)} max={_pct(d.max)} std={_pct(d.std_dev)}"
        )

    def _edge_ratio(self) -> str:
        lines = ["  3. EDGE RATIO ANALYSIS"]
        for s in self._r.by_strategy.values():
            if s.edge_ratio >= 1.5:
                grade = "Excellent"
            elif s.edge_ratio >= 1.0:
                grade = "Good"
            else:
                grade = "Poor"
            lines.append(f"  {s.strategy}: {_f2(s.edge_ratio)} ({grade})")
            lines.append(self._dist_detail("    MFE", s.mfe))
            lines.append(self._dist_detail("    MAE", s.mae))
        return "\n".join(lines)

    def _heat_captured(self) -> str:
        lines = [
            "  4. HEAT CAPTURED (realized profit / max available)",
            f"  Overall: {_pct(self._r.overall_heat_captured)}",
        ]
        for s in self._r.by_strategy.values():
            lines.append(f"  {s.strategy}: {_pct(s.heat_captured)}")
        return "\n".join(lines)

    def _sltp_efficiency(self) -> str:
        lines = ["  5. SL/TP EFFICIENCY"]
        if not self._r.sltp_efficiency:
            lines.append("  No SL/TP config data available for matched strategies.")
            return "\n".join(lines)

        lines.append(
            f"  {'Strategy':<22} {'Dir':<6} "
            f"{'SL ATR':>7} {'MAE Med':>8} {'MAE p75':>8} {'SL Util':>8} "
            f"{'TP ATR':>7} {'MFE Med':>8} {'MFE p75':>8}"
        )
        lines.append(
            f"  {'-' * 22} {'-' * 6} "
            f"{'-' * 7} {'-' * 8} {'-' * 8} {'-' * 8} "
            f"{'-' * 7} {'-' * 8} {'-' * 8}"
        )
        for e in self._r.sltp_efficiency:
            tp_str = _f2(e.tp_atr_mult) if e.tp_atr_mult is not None else "ind."
            lines.append(
                f"  {e.strategy:<22} {e.direction:<6} "
                f"{_f2(e.sl_atr_mult):>7} {_f2(e.mae_median_atr):>8} "
                f"{_f2(e.mae_p75_atr):>8} {_pct(e.sl_utilization):>8} "
                f"{tp_str:>7} {_f2(e.mfe_median_atr):>8} {_f2(e.mfe_p75_atr):>8}"
            )
        return "\n".join(lines)

    def _optimal_sltp(self) -> str:
        lines = ["  6. OPTIMAL SL/TP SUGGESTIONS (ATR multiples)"]
        if not self._r.optimal_sltp:
            lines.append("  No trade data with entry_atr available.")
            return "\n".join(lines)

        for o in self._r.optimal_sltp:
            lines.append(f"  {o.strategy} ({o.direction}):")
            lines.append(
                f"    MAE: p50={_f2(o.mae_p50_atr)} p75={_f2(o.mae_p75_atr)} "
                f"p90={_f2(o.mae_p90_atr)} -> SL={_f2(o.suggested_sl_atr)} ATR"
            )
            if o.suggested_tp_atr is not None:
                lines.append(
                    f"    MFE: p50={_f2(o.mfe_p50_atr)} p75={_f2(o.mfe_p75_atr)} "
                    f"p90={_f2(o.mfe_p90_atr)} -> TP={_f2(o.suggested_tp_atr)} ATR"
                )
            else:
                lines.append(
                    f"    MFE: p50={_f2(o.mfe_p50_atr)} p75={_f2(o.mfe_p75_atr)} "
                    f"p90={_f2(o.mfe_p90_atr)} (indicator-based TP)"
                )
        return "\n".join(lines)

    def _exit_reason(self) -> str:
        lines = [
            "  7. EXIT REASON ANALYSIS",
            f"  {'Reason':<18} {'Count':>6} {'Avg PnL':>9} "
            f"{'WR':>7} {'Avg MFE':>9} {'Avg MAE':>9}",
            f"  {'-' * 18} {'-' * 6} {'-' * 9} "
            f"{'-' * 7} {'-' * 9} {'-' * 9}",
        ]
        for e in self._r.by_exit_reason:
            lines.append(
                f"  {e.exit_reason:<18} {e.count:>6} "
                f"{_pct(e.avg_pnl_pct):>9} {_pct(e.win_rate):>7} "
                f"{_pct(e.avg_mfe_pct):>9} {_pct(e.avg_mae_pct):>9}"
            )
        return "\n".join(lines)

    def _hold_duration(self) -> str:
        lines = [
            "  8. HOLD DURATION ANALYSIS",
            f"  {'Bars':<6} {'Count':>6} {'Avg MFE':>9} "
            f"{'Avg MAE':>9} {'WR':>7} {'Edge':>6}",
            f"  {'-' * 6} {'-' * 6} {'-' * 9} "
            f"{'-' * 9} {'-' * 7} {'-' * 6}",
        ]
        for b in self._r.by_hold_duration:
            lines.append(
                f"  {b.bucket:<6} {b.count:>6} "
                f"{_pct(b.avg_mfe_pct):>9} {_pct(b.avg_mae_pct):>9} "
                f"{_pct(b.win_rate):>7} {_f2(b.edge_ratio):>6}"
            )
        return "\n".join(lines)

    def _win_loss_profile(self) -> str:
        wl = self._r.win_loss_profile
        lines = [
            "  9. WIN/LOSS PROFILE",
            f"  Winners: {wl.win_count}  |  Losers: {wl.loss_count}",
            f"  Win Edge Ratio:  {_f2(wl.win_edge_ratio)}  |  "
            f"Loss Edge Ratio:  {_f2(wl.loss_edge_ratio)}",
            "",
            "  Winners:",
            self._dist_detail("    MFE", wl.win_mfe),
            self._dist_detail("    MAE", wl.win_mae),
            "",
            "  Losers:",
            self._dist_detail("    MFE", wl.loss_mfe),
            self._dist_detail("    MAE", wl.loss_mae),
        ]
        return "\n".join(lines)


class ABComparisonReport:
    """Generate A/B comparison report between two analysis results."""

    def __init__(
        self,
        baseline: AnalysisResult,
        variant: AnalysisResult,
        baseline_label: str = "Baseline",
        variant_label: str = "Variant",
    ) -> None:
        self._a = baseline
        self._b = variant
        self._a_label = baseline_label
        self._b_label = variant_label

    def generate(self) -> str:
        """Generate A/B comparison report."""
        sections = [
            self._header(),
            self._overview_comparison(),
            self._strategy_comparison(),
            self._exit_comparison(),
        ]
        return "\n\n".join(sections)

    def _header(self) -> str:
        return (
            f"{'=' * 64}\n"
            f"  A/B COMPARISON: {self._a_label} vs {self._b_label}\n"
            f"{'=' * 64}"
        )

    def _delta_str(self, a: float, b: float, as_pct: bool = False) -> str:
        d = b - a
        if as_pct:
            return f"{d * 100:+.2f}pp"
        return f"{d:+.2f}"

    def _overview_comparison(self) -> str:
        a, b = self._a, self._b
        lines = [
            "  OVERVIEW COMPARISON",
            f"  {'Metric':<25} {self._a_label:>12} {self._b_label:>12} {'Delta':>10}",
            f"  {'-' * 25} {'-' * 12} {'-' * 12} {'-' * 10}",
            f"  {'Total Trades':<25} {a.total_trades:>12} "
            f"{b.total_trades:>12} {b.total_trades - a.total_trades:>+10}",
            f"  {'Edge Ratio':<25} {_f2(a.overall_edge_ratio):>12} "
            f"{_f2(b.overall_edge_ratio):>12} "
            f"{self._delta_str(a.overall_edge_ratio, b.overall_edge_ratio):>10}",
            f"  {'Heat Captured':<25} {_pct(a.overall_heat_captured):>12} "
            f"{_pct(b.overall_heat_captured):>12} "
            f"{self._delta_str(a.overall_heat_captured, b.overall_heat_captured, True):>10}",
            f"  {'Avg MFE':<25} {_pct(a.overall_mfe.mean):>12} "
            f"{_pct(b.overall_mfe.mean):>12} "
            f"{self._delta_str(a.overall_mfe.mean, b.overall_mfe.mean, True):>10}",
            f"  {'Avg MAE':<25} {_pct(a.overall_mae.mean):>12} "
            f"{_pct(b.overall_mae.mean):>12} "
            f"{self._delta_str(a.overall_mae.mean, b.overall_mae.mean, True):>10}",
        ]
        return "\n".join(lines)

    def _strategy_comparison(self) -> str:
        lines = ["  STRATEGY COMPARISON"]
        all_strategies = sorted(
            set(list(self._a.by_strategy.keys()) + list(self._b.by_strategy.keys()))
        )

        lines.append(
            f"  {'Strategy':<22} {'Edge A':>7} {'Edge B':>7} {'Delta':>7} "
            f"{'Heat A':>7} {'Heat B':>7} {'Delta':>8}"
        )
        lines.append(
            f"  {'-' * 22} {'-' * 7} {'-' * 7} {'-' * 7} "
            f"{'-' * 7} {'-' * 7} {'-' * 8}"
        )

        for s in all_strategies:
            a_s = self._a.by_strategy.get(s)
            b_s = self._b.by_strategy.get(s)
            a_edge = a_s.edge_ratio if a_s else 0.0
            b_edge = b_s.edge_ratio if b_s else 0.0
            a_heat = a_s.heat_captured if a_s else 0.0
            b_heat = b_s.heat_captured if b_s else 0.0
            lines.append(
                f"  {s:<22} {_f2(a_edge):>7} {_f2(b_edge):>7} "
                f"{self._delta_str(a_edge, b_edge):>7} "
                f"{_pct(a_heat):>7} {_pct(b_heat):>7} "
                f"{self._delta_str(a_heat, b_heat, True):>8}"
            )
        return "\n".join(lines)

    def _exit_comparison(self) -> str:
        lines = ["  EXIT REASON COMPARISON"]
        a_map = {e.exit_reason: e for e in self._a.by_exit_reason}
        b_map = {e.exit_reason: e for e in self._b.by_exit_reason}
        all_reasons = sorted(set(list(a_map.keys()) + list(b_map.keys())))

        lines.append(
            f"  {'Reason':<18} {'WR A':>7} {'WR B':>7} {'Delta':>8} "
            f"{'PnL A':>9} {'PnL B':>9} {'Delta':>10}"
        )
        lines.append(
            f"  {'-' * 18} {'-' * 7} {'-' * 7} {'-' * 8} "
            f"{'-' * 9} {'-' * 9} {'-' * 10}"
        )

        for reason in all_reasons:
            a_e = a_map.get(reason)
            b_e = b_map.get(reason)
            a_wr = a_e.win_rate if a_e else 0.0
            b_wr = b_e.win_rate if b_e else 0.0
            a_pnl = a_e.avg_pnl_pct if a_e else 0.0
            b_pnl = b_e.avg_pnl_pct if b_e else 0.0
            lines.append(
                f"  {reason:<18} {_pct(a_wr):>7} {_pct(b_wr):>7} "
                f"{self._delta_str(a_wr, b_wr, True):>8} "
                f"{_pct(a_pnl):>9} {_pct(b_pnl):>9} "
                f"{self._delta_str(a_pnl, b_pnl, True):>10}"
            )
        return "\n".join(lines)
