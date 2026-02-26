import pytest
from autotrader.analysis.rotation_comparator import RotationComparator, StrategyMetrics


class TestStrategyMetrics:
    def test_create_metrics(self):
        m = StrategyMetrics(
            label="weekly",
            total_trades=100,
            win_rate=0.55,
            profit_factor=1.5,
            total_pnl=500.0,
            max_drawdown=0.08,
            sharpe_ratio=1.2,
            avg_holding_days=3.5,
            rotation_count=12,
        )
        assert m.label == "weekly"
        assert m.total_trades == 100
        assert m.sharpe_ratio == 1.2

    def test_metrics_is_frozen(self):
        m = StrategyMetrics(
            label="weekly", total_trades=100, win_rate=0.55,
            profit_factor=1.5, total_pnl=500.0, max_drawdown=0.08,
            sharpe_ratio=1.2, avg_holding_days=3.5, rotation_count=12,
        )
        with pytest.raises(AttributeError):
            m.total_pnl = 1000.0


class TestRotationComparator:
    def _make_trades(self, count: int, avg_pnl: float):
        """Helper to create simple trade dicts for testing."""
        trades = []
        for i in range(count):
            pnl = avg_pnl + (i % 3 - 1) * 10  # Add some variance
            trades.append({
                "pnl": pnl,
                "equity_after": 10000 + sum(t["pnl"] for t in trades) + pnl,
                "direction": "close",
            })
        return trades

    def test_compute_metrics_basic(self):
        comp = RotationComparator()
        trades = self._make_trades(20, 15.0)
        metrics = comp.compute_metrics("test", trades, rotation_count=5)
        assert metrics.label == "test"
        assert metrics.total_trades == 20
        assert metrics.win_rate > 0.0
        assert metrics.rotation_count == 5

    def test_compare_returns_both_metrics(self):
        comp = RotationComparator()
        weekly_trades = self._make_trades(30, 10.0)
        event_trades = self._make_trades(35, 12.0)
        result = comp.compare(
            weekly_trades=weekly_trades,
            event_trades=event_trades,
            weekly_rotations=10,
            event_rotations=14,
        )
        assert "weekly" in result
        assert "event_driven" in result
        assert isinstance(result["weekly"], StrategyMetrics)
        assert isinstance(result["event_driven"], StrategyMetrics)

    def test_compare_winner_field(self):
        comp = RotationComparator()
        weekly_trades = self._make_trades(30, 5.0)
        event_trades = self._make_trades(35, 15.0)
        result = comp.compare(
            weekly_trades=weekly_trades,
            event_trades=event_trades,
            weekly_rotations=10,
            event_rotations=14,
        )
        assert "winner" in result
        # Event-driven should win with higher avg PnL
        assert result["winner"] in ("weekly", "event_driven", "tie")

    def test_empty_trades_returns_zero_metrics(self):
        comp = RotationComparator()
        metrics = comp.compute_metrics("empty", [], rotation_count=0)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.total_pnl == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_format_comparison(self):
        comp = RotationComparator()
        weekly_trades = self._make_trades(20, 10.0)
        event_trades = self._make_trades(25, 12.0)
        result = comp.compare(
            weekly_trades=weekly_trades,
            event_trades=event_trades,
            weekly_rotations=8,
            event_rotations=12,
        )
        output = comp.format_comparison(result)
        assert isinstance(output, str)
        assert "weekly" in output.lower()
        assert "event" in output.lower()

    def test_single_trade(self):
        comp = RotationComparator()
        trades = [{"pnl": 50.0, "equity_after": 10050.0, "direction": "close"}]
        metrics = comp.compute_metrics("single", trades, rotation_count=1)
        assert metrics.total_trades == 1
        assert metrics.win_rate == 1.0
        assert metrics.total_pnl == 50.0
