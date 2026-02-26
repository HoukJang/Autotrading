"""Tests for TradeCollector and TradeDetail."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autotrader.backtest.trade_collector import TradeCollector, TradeDetail
from autotrader.core.types import Bar, Signal


def _bar(symbol: str = "AAPL", close: float = 150.0, ts: datetime | None = None) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts or datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc),
        open=149.0,
        high=151.0,
        low=148.0,
        close=close,
        volume=1000.0,
    )


def _entry_signal(
    symbol: str = "AAPL",
    sub_strategy: str = "trend_following",
) -> Signal:
    return Signal(
        strategy="regime_dual",
        symbol=symbol,
        direction="long",
        strength=0.8,
        metadata={
            "sub_strategy": sub_strategy,
            "regime": "TREND",
            "adx": 35.0,
            "rsi": 55.0,
        },
    )


def _exit_signal(
    symbol: str = "AAPL",
    exit_reason: str = "take_profit",
    bars_held: int = 5,
) -> Signal:
    return Signal(
        strategy="regime_dual",
        symbol=symbol,
        direction="close",
        strength=0.6,
        metadata={
            "exit_reason": exit_reason,
            "bars_held": bars_held,
            "entry_price": 150.0,
            "exit_price": 155.0,
            "pnl_pct": 0.033,
        },
    )


class TestTradeCollector:
    def test_empty_collector(self):
        collector = TradeCollector()
        assert collector.trades == []

    def test_on_entry_records_pending(self):
        collector = TradeCollector()
        signal = _entry_signal()
        bar = _bar()
        collector.on_entry(signal, bar, quantity=10.0)
        # No completed trade yet
        assert collector.trades == []

    def test_on_exit_returns_trade_detail(self):
        collector = TradeCollector()
        entry_bar = _bar(close=150.0, ts=datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc))
        exit_bar = _bar(close=155.0, ts=datetime(2025, 1, 10, 15, 0, tzinfo=timezone.utc))

        collector.on_entry(_entry_signal(), entry_bar, quantity=10.0)
        detail = collector.on_exit(_exit_signal(), exit_bar, pnl=50.0)

        assert detail is not None
        assert isinstance(detail, TradeDetail)
        assert detail.trade_id == 1
        assert detail.symbol == "AAPL"
        assert detail.strategy == "regime_dual"
        assert detail.sub_strategy == "trend_following"
        assert detail.direction == "long"
        assert detail.entry_time == entry_bar.timestamp
        assert detail.exit_time == exit_bar.timestamp
        assert detail.entry_price == 150.0
        assert detail.exit_price == 155.0
        assert detail.quantity == 10.0
        assert detail.pnl == 50.0
        assert detail.bars_held == 5
        assert detail.exit_reason == "take_profit"

    def test_on_exit_pnl_pct_calculated_from_prices(self):
        collector = TradeCollector()
        entry_bar = _bar(close=100.0)
        exit_bar = _bar(close=110.0)

        collector.on_entry(_entry_signal(), entry_bar, quantity=5.0)
        detail = collector.on_exit(_exit_signal(), exit_bar, pnl=50.0)

        assert detail is not None
        assert detail.pnl_pct == pytest.approx(0.1, abs=1e-6)

    def test_on_exit_nonexistent_symbol_returns_none(self):
        collector = TradeCollector()
        exit_bar = _bar(symbol="MSFT")
        result = collector.on_exit(
            _exit_signal(symbol="MSFT"), exit_bar, pnl=0.0
        )
        assert result is None

    def test_multiple_trades_increments_id(self):
        collector = TradeCollector()

        for i in range(3):
            entry_bar = _bar(close=100.0 + i)
            exit_bar = _bar(close=105.0 + i)
            collector.on_entry(_entry_signal(), entry_bar, quantity=1.0)
            collector.on_exit(_exit_signal(), exit_bar, pnl=5.0)

        trades = collector.trades
        assert len(trades) == 3
        assert trades[0].trade_id == 1
        assert trades[1].trade_id == 2
        assert trades[2].trade_id == 3

    def test_trades_returns_copy(self):
        collector = TradeCollector()
        entry_bar = _bar()
        exit_bar = _bar(close=155.0)

        collector.on_entry(_entry_signal(), entry_bar, quantity=1.0)
        collector.on_exit(_exit_signal(), exit_bar, pnl=5.0)

        trades1 = collector.trades
        trades2 = collector.trades
        assert trades1 == trades2
        assert trades1 is not trades2

    def test_entry_indicators_captured(self):
        collector = TradeCollector()
        bar = _bar()
        collector.on_entry(_entry_signal(), bar, quantity=1.0)
        exit_bar = _bar(close=155.0)
        detail = collector.on_exit(_exit_signal(), exit_bar, pnl=5.0)

        assert detail is not None
        assert "regime" in detail.entry_indicators
        assert "adx" in detail.entry_indicators
        assert "rsi" in detail.entry_indicators
        # sub_strategy should NOT be in entry_indicators (it's a top-level field)
        assert "sub_strategy" not in detail.entry_indicators

    def test_mean_reversion_sub_strategy(self):
        collector = TradeCollector()
        signal = _entry_signal(sub_strategy="mean_reversion")
        bar = _bar()
        collector.on_entry(signal, bar, quantity=2.0)
        exit_bar = _bar(close=152.0)
        detail = collector.on_exit(_exit_signal(exit_reason="mr_target"), exit_bar, pnl=4.0)

        assert detail is not None
        assert detail.sub_strategy == "mean_reversion"
        assert detail.exit_reason == "mr_target"

    def test_multi_symbol_concurrent(self):
        collector = TradeCollector()

        collector.on_entry(
            _entry_signal(symbol="AAPL"),
            _bar(symbol="AAPL", close=150.0),
            quantity=10.0,
        )
        collector.on_entry(
            _entry_signal(symbol="MSFT"),
            _bar(symbol="MSFT", close=300.0),
            quantity=5.0,
        )

        detail1 = collector.on_exit(
            _exit_signal(symbol="AAPL"),
            _bar(symbol="AAPL", close=155.0),
            pnl=50.0,
        )
        detail2 = collector.on_exit(
            _exit_signal(symbol="MSFT"),
            _bar(symbol="MSFT", close=310.0),
            pnl=50.0,
        )

        assert detail1 is not None
        assert detail2 is not None
        assert detail1.symbol == "AAPL"
        assert detail2.symbol == "MSFT"
        assert len(collector.trades) == 2
