"""Tests for MFE/MAE trade analysis engine."""
from __future__ import annotations

import pytest

from autotrader.analysis.trade_analyzer import (
    AnalysisResult,
    DistributionStats,
    TradeAnalyzer,
    _compute_dist,
    _percentile,
    _safe_div,
    _std_dev,
)


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


class TestStatHelpers:
    def test_percentile_empty(self):
        assert _percentile([], 50) == 0.0

    def test_percentile_single(self):
        assert _percentile([5.0], 50) == 5.0

    def test_percentile_median_odd(self):
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_percentile_median_even(self):
        result = _percentile([1.0, 2.0, 3.0, 4.0], 50)
        assert abs(result - 2.5) < 0.001

    def test_percentile_p25(self):
        vals = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        result = _percentile(vals, 25)
        assert result == 20.0

    def test_percentile_p75(self):
        vals = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        result = _percentile(vals, 75)
        assert result == 40.0

    def test_std_dev_single(self):
        assert _std_dev([5.0], 5.0) == 0.0

    def test_std_dev_known(self):
        # Sample std dev of [2,4,4,4,5,5,7,9]: mean=5, var=32/7, std~2.138
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        mean = sum(vals) / len(vals)
        result = _std_dev(vals, mean)
        assert abs(result - 2.138) < 0.01

    def test_compute_dist_empty(self):
        d = _compute_dist([])
        assert d.count == 0
        assert d.mean == 0.0

    def test_compute_dist_values(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        d = _compute_dist(vals)
        assert d.count == 5
        assert d.mean == 3.0
        assert d.median == 3.0
        assert d.min == 1.0
        assert d.max == 5.0

    def test_safe_div_normal(self):
        assert _safe_div(10.0, 2.0) == 5.0

    def test_safe_div_zero(self):
        assert _safe_div(10.0, 0.0) == 0.0


class TestDistributionFrozen:
    def test_immutable(self):
        d = _compute_dist([1.0, 2.0, 3.0])
        with pytest.raises(AttributeError):
            d.mean = 99.0  # type: ignore[misc]


class TestTradeAnalyzer:
    def test_empty_trades(self):
        result = TradeAnalyzer([]).analyze()
        assert result.total_trades == 0
        assert result.overall_edge_ratio == 0.0

    def test_single_trade(self):
        trades = [_make_trade(mfe_pct=0.05, mae_pct=0.02, pnl_pct=0.03)]
        result = TradeAnalyzer(trades).analyze()
        assert result.total_trades == 1
        assert abs(result.overall_edge_ratio - 2.5) < 0.01

    def test_strategy_filter(self):
        trades = [
            _make_trade(strategy="rsi_mean_reversion"),
            _make_trade(strategy="consecutive_down"),
            _make_trade(strategy="rsi_mean_reversion"),
        ]
        result = TradeAnalyzer(trades).analyze(
            strategy_filter="rsi_mean_reversion"
        )
        assert result.total_trades == 2
        assert "rsi_mean_reversion" in result.by_strategy
        assert "consecutive_down" not in result.by_strategy
        assert result.strategy_filter == "rsi_mean_reversion"

    def test_strategy_filter_no_match(self):
        trades = [_make_trade(strategy="rsi_mean_reversion")]
        result = TradeAnalyzer(trades).analyze(strategy_filter="nonexistent")
        assert result.total_trades == 0

    def test_edge_ratio(self):
        trades = [
            _make_trade(mfe_pct=0.04, mae_pct=0.02),
            _make_trade(mfe_pct=0.06, mae_pct=0.02),
        ]
        result = TradeAnalyzer(trades).analyze()
        # mean MFE = 0.05, mean MAE = 0.02 -> edge = 2.5
        assert abs(result.overall_edge_ratio - 2.5) < 0.01

    def test_heat_captured_winners_only(self):
        trades = [
            _make_trade(pnl_pct=0.02, mfe_pct=0.04),  # heat = 0.5
            _make_trade(pnl_pct=-0.01, mfe_pct=0.03),  # loser, excluded
            _make_trade(pnl_pct=0.03, mfe_pct=0.06),  # heat = 0.5
        ]
        result = TradeAnalyzer(trades).analyze()
        assert abs(result.overall_heat_captured - 0.5) < 0.01

    def test_heat_captured_no_winners(self):
        trades = [
            _make_trade(pnl_pct=-0.01, mfe_pct=0.03),
            _make_trade(pnl_pct=-0.02, mfe_pct=0.01),
        ]
        result = TradeAnalyzer(trades).analyze()
        assert result.overall_heat_captured == 0.0

    def test_by_strategy_multiple(self):
        trades = [
            _make_trade(strategy="rsi_mean_reversion", mfe_pct=0.04, mae_pct=0.02),
            _make_trade(strategy="rsi_mean_reversion", mfe_pct=0.06, mae_pct=0.02),
            _make_trade(strategy="consecutive_down", mfe_pct=0.03, mae_pct=0.01),
        ]
        result = TradeAnalyzer(trades).analyze()
        assert len(result.by_strategy) == 2
        rsi = result.by_strategy["rsi_mean_reversion"]
        assert rsi.trade_count == 2
        assert abs(rsi.edge_ratio - 2.5) < 0.01
        cd = result.by_strategy["consecutive_down"]
        assert cd.trade_count == 1

    def test_by_exit_reason(self):
        trades = [
            _make_trade(exit_reason="stop_loss", pnl_pct=-0.02),
            _make_trade(exit_reason="stop_loss", pnl_pct=-0.01),
            _make_trade(exit_reason="take_profit", pnl_pct=0.05),
        ]
        result = TradeAnalyzer(trades).analyze()
        reason_map = {e.exit_reason: e for e in result.by_exit_reason}
        assert reason_map["stop_loss"].count == 2
        assert reason_map["stop_loss"].win_rate == 0.0
        assert reason_map["take_profit"].count == 1
        assert reason_map["take_profit"].win_rate == 1.0

    def test_hold_duration_buckets(self):
        trades = [
            _make_trade(bars_held=2),
            _make_trade(bars_held=2),
            _make_trade(bars_held=3),
            _make_trade(bars_held=5),
            _make_trade(bars_held=7),
        ]
        result = TradeAnalyzer(trades).analyze()
        bucket_map = {b.bucket: b for b in result.by_hold_duration}
        assert bucket_map["2"].count == 2
        assert bucket_map["3"].count == 1
        assert bucket_map["5+"].count == 2

    def test_win_loss_profile(self):
        trades = [
            _make_trade(pnl_pct=0.03, mfe_pct=0.05, mae_pct=0.01),
            _make_trade(pnl_pct=0.02, mfe_pct=0.04, mae_pct=0.01),
            _make_trade(pnl_pct=-0.01, mfe_pct=0.01, mae_pct=0.03),
        ]
        result = TradeAnalyzer(trades).analyze()
        wl = result.win_loss_profile
        assert wl.win_count == 2
        assert wl.loss_count == 1
        assert wl.win_mfe.mean > wl.loss_mfe.mean
        assert wl.win_mae.mean < wl.loss_mae.mean

    def test_win_loss_edge_ratios(self):
        trades = [
            _make_trade(pnl_pct=0.03, mfe_pct=0.06, mae_pct=0.01),
            _make_trade(pnl_pct=-0.01, mfe_pct=0.01, mae_pct=0.04),
        ]
        result = TradeAnalyzer(trades).analyze()
        wl = result.win_loss_profile
        assert wl.win_edge_ratio > 1.0
        assert wl.loss_edge_ratio < 1.0

    def test_sltp_efficiency(self):
        trades = [
            _make_trade(
                strategy="rsi_mean_reversion",
                direction="long",
                entry_price=100.0,
                entry_atr=2.0,
                mae_pct=0.01,
                mfe_pct=0.03,
            ),
        ]
        result = TradeAnalyzer(trades).analyze()
        assert len(result.sltp_efficiency) > 0
        eff = result.sltp_efficiency[0]
        assert eff.strategy == "rsi_mean_reversion"
        assert eff.sl_atr_mult == 1.0
        # MAE in ATR = (0.01 * 100) / 2.0 = 0.5
        assert abs(eff.mae_median_atr - 0.5) < 0.01
        # SL utilization = 0.5 / 1.0 = 50%
        assert abs(eff.sl_utilization - 0.5) < 0.01

    def test_sltp_efficiency_skips_unknown_strategy(self):
        trades = [
            _make_trade(strategy="unknown_strategy", direction="long"),
        ]
        result = TradeAnalyzer(trades).analyze()
        assert len(result.sltp_efficiency) == 0

    def test_optimal_sltp_indicator_based(self):
        trades = [
            _make_trade(strategy="rsi_mean_reversion", direction="long"),
            _make_trade(strategy="rsi_mean_reversion", direction="long"),
        ]
        result = TradeAnalyzer(trades).analyze()
        for o in result.optimal_sltp:
            if o.strategy == "rsi_mean_reversion":
                assert o.suggested_tp_atr is None

    def test_optimal_sltp_atr_based(self):
        trades = [
            _make_trade(
                strategy="ema_cross_trend",
                direction="long",
                entry_price=100.0,
                entry_atr=2.0,
                mfe_pct=0.10,
                mae_pct=0.04,
            ),
            _make_trade(
                strategy="ema_cross_trend",
                direction="long",
                entry_price=100.0,
                entry_atr=2.0,
                mfe_pct=0.08,
                mae_pct=0.03,
            ),
        ]
        sl_config = {"ema_cross_trend": {"long": 3.0, "short": 3.0}}
        tp_config: dict[str, float | None] = {"ema_cross_trend": 5.0}
        result = TradeAnalyzer(trades, sl_config, tp_config).analyze()
        for o in result.optimal_sltp:
            if o.strategy == "ema_cross_trend":
                assert o.suggested_tp_atr is not None

    def test_missing_entry_atr_skips_atr_calcs(self):
        trades = [
            {
                "strategy": "test",
                "direction": "long",
                "pnl_pct": 0.01,
                "mfe_pct": 0.03,
                "mae_pct": 0.02,
                "bars_held": 3,
                "exit_reason": "stop_loss",
                "entry_price": 0.0,
                "entry_atr": 0.0,
            }
        ]
        result = TradeAnalyzer(trades).analyze()
        assert result.total_trades == 1
        assert len(result.optimal_sltp) == 0

    def test_analysis_result_frozen(self):
        result = TradeAnalyzer([_make_trade()]).analyze()
        with pytest.raises(AttributeError):
            result.total_trades = 99  # type: ignore[misc]

    def test_multiple_directions(self):
        trades = [
            _make_trade(direction="long", mfe_pct=0.04, mae_pct=0.01),
            _make_trade(direction="short", mfe_pct=0.03, mae_pct=0.02),
        ]
        result = TradeAnalyzer(trades).analyze()
        # rsi_mean_reversion has both long (SL=1.0) and short (SL=1.5)
        assert len(result.sltp_efficiency) == 2
        dirs = {e.direction for e in result.sltp_efficiency}
        assert dirs == {"long", "short"}
