import pytest
from autotrader.portfolio.performance import calculate_metrics


class TestPerformanceMetrics:
    def test_win_rate(self):
        trades = [100.0, -50.0, 75.0, -25.0, 200.0]
        metrics = calculate_metrics(trades, initial_equity=100_000.0)
        assert metrics["win_rate"] == pytest.approx(0.6)  # 3/5

    def test_profit_factor(self):
        trades = [100.0, -50.0, 200.0]
        metrics = calculate_metrics(trades, initial_equity=100_000.0)
        assert metrics["profit_factor"] == pytest.approx(6.0)  # 300/50

    def test_empty_trades(self):
        metrics = calculate_metrics([], initial_equity=100_000.0)
        assert metrics["win_rate"] == 0.0
        assert metrics["total_trades"] == 0
