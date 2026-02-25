import pytest
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.portfolio.performance import calculate_metrics


class TestPortfolioTracker:
    def test_record_trade(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade(symbol="AAPL", side="buy", qty=10, price=150.0, pnl=0.0)
        assert len(tracker.trades) == 1

    def test_equity_curve(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade("AAPL", "sell", 10, 155.0, pnl=50.0)
        tracker.update_equity(100_050.0)
        assert tracker.equity_curve[-1] == 100_050.0

    def test_daily_pnl(self):
        tracker = PortfolioTracker(initial_equity=100_000.0)
        tracker.record_trade("AAPL", "sell", 10, 155.0, pnl=50.0)
        tracker.record_trade("MSFT", "sell", 5, 300.0, pnl=-30.0)
        assert tracker.total_pnl == pytest.approx(20.0)


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
