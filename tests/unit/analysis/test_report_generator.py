"""Tests for MFE/MAE report generation."""
from __future__ import annotations

from autotrader.analysis.report_generator import ABComparisonReport, ReportGenerator
from autotrader.analysis.trade_analyzer import TradeAnalyzer


def _make_trade(
    strategy: str = "rsi_mean_reversion",
    direction: str = "long",
    pnl_pct: float = 0.01,
    mfe_pct: float = 0.03,
    mae_pct: float = 0.02,
    bars_held: int = 3,
    exit_reason: str = "stop_loss",
    entry_price: float = 100.0,
    entry_atr: float = 2.0,
) -> dict:
    return {
        "strategy": strategy,
        "direction": direction,
        "pnl": pnl_pct * entry_price * 100,
        "pnl_pct": pnl_pct,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "bars_held": bars_held,
        "exit_reason": exit_reason,
        "entry_price": entry_price,
        "entry_atr": entry_atr,
    }


class TestReportGenerator:
    def _sample_trades(self) -> list[dict]:
        return [
            _make_trade(
                strategy="rsi_mean_reversion",
                pnl_pct=0.03,
                mfe_pct=0.05,
                mae_pct=0.01,
                exit_reason="take_profit",
            ),
            _make_trade(
                strategy="rsi_mean_reversion",
                pnl_pct=-0.02,
                mfe_pct=0.01,
                mae_pct=0.04,
                exit_reason="stop_loss",
            ),
            _make_trade(
                strategy="consecutive_down",
                pnl_pct=0.02,
                mfe_pct=0.04,
                mae_pct=0.015,
                exit_reason="time_exit",
                bars_held=5,
            ),
        ]

    def test_generate_returns_string(self):
        result = TradeAnalyzer(self._sample_trades()).analyze()
        report = ReportGenerator(result).generate()
        assert isinstance(report, str)
        assert len(report) > 100

    def test_report_contains_all_sections(self):
        result = TradeAnalyzer(self._sample_trades()).analyze()
        report = ReportGenerator(result).generate()
        assert "1. OVERVIEW" in report
        assert "2. MFE/MAE BY STRATEGY" in report
        assert "3. EDGE RATIO" in report
        assert "4. HEAT CAPTURED" in report
        assert "5. SL/TP EFFICIENCY" in report
        assert "6. OPTIMAL SL/TP" in report
        assert "7. EXIT REASON" in report
        assert "8. HOLD DURATION" in report
        assert "9. WIN/LOSS PROFILE" in report

    def test_report_with_strategy_filter(self):
        result = TradeAnalyzer(self._sample_trades()).analyze(
            strategy_filter="rsi_mean_reversion"
        )
        report = ReportGenerator(result).generate()
        assert "[rsi_mean_reversion]" in report
        assert "consecutive_down" not in report

    def test_report_empty_trades(self):
        result = TradeAnalyzer([]).analyze()
        report = ReportGenerator(result).generate()
        assert "Total Trades:          0" in report

    def test_report_percentages(self):
        trades = [_make_trade(mfe_pct=0.03, mae_pct=0.02)]
        result = TradeAnalyzer(trades).analyze()
        report = ReportGenerator(result).generate()
        # 0.03 -> "3.00%"
        assert "3.00%" in report

    def test_report_edge_grades(self):
        trades = [
            _make_trade(mfe_pct=0.06, mae_pct=0.02),  # edge 3.0 -> Excellent
        ]
        result = TradeAnalyzer(trades).analyze()
        report = ReportGenerator(result).generate()
        assert "Excellent" in report

    def test_report_poor_edge_grade(self):
        trades = [
            _make_trade(mfe_pct=0.01, mae_pct=0.05),  # edge 0.2 -> Poor
        ]
        result = TradeAnalyzer(trades).analyze()
        report = ReportGenerator(result).generate()
        assert "Poor" in report

    def test_report_indicator_tp_label(self):
        trades = [_make_trade(strategy="rsi_mean_reversion")]
        result = TradeAnalyzer(trades).analyze()
        report = ReportGenerator(result).generate()
        assert "indicator-based TP" in report


class TestABComparisonReport:
    def test_comparison_report(self):
        trades_a = [
            _make_trade(pnl_pct=0.01, mfe_pct=0.03, mae_pct=0.02),
            _make_trade(pnl_pct=-0.01, mfe_pct=0.01, mae_pct=0.03),
        ]
        trades_b = [
            _make_trade(pnl_pct=0.02, mfe_pct=0.05, mae_pct=0.01),
            _make_trade(pnl_pct=0.01, mfe_pct=0.03, mae_pct=0.02),
        ]
        result_a = TradeAnalyzer(trades_a).analyze()
        result_b = TradeAnalyzer(trades_b).analyze()
        report = ABComparisonReport(result_a, result_b, "v16", "v17").generate()
        assert "A/B COMPARISON" in report
        assert "v16" in report
        assert "v17" in report
        assert "OVERVIEW COMPARISON" in report
        assert "STRATEGY COMPARISON" in report
        assert "EXIT REASON COMPARISON" in report

    def test_comparison_delta_format(self):
        trades_a = [_make_trade(pnl_pct=0.01, mfe_pct=0.03, mae_pct=0.02)]
        trades_b = [_make_trade(pnl_pct=0.02, mfe_pct=0.05, mae_pct=0.01)]
        result_a = TradeAnalyzer(trades_a).analyze()
        result_b = TradeAnalyzer(trades_b).analyze()
        report = ABComparisonReport(result_a, result_b).generate()
        assert "+" in report or "-" in report

    def test_comparison_different_strategies(self):
        trades_a = [_make_trade(strategy="rsi_mean_reversion")]
        trades_b = [
            _make_trade(strategy="rsi_mean_reversion"),
            _make_trade(strategy="consecutive_down"),
        ]
        result_a = TradeAnalyzer(trades_a).analyze()
        result_b = TradeAnalyzer(trades_b).analyze()
        report = ABComparisonReport(result_a, result_b).generate()
        assert "rsi_mean_reversion" in report
        assert "consecutive_down" in report
