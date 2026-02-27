"""Tests for DailyBarAggregator."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from autotrader.core.aggregator import DailyBarAggregator, _to_market_date
from autotrader.core.types import Bar, Timeframe


def _make_minute_bar(
    symbol: str = "AAPL",
    ts: datetime | None = None,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 1000.0,
) -> Bar:
    if ts is None:
        ts = datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timeframe=Timeframe.MINUTE,
    )


class TestToMarketDate:
    def test_utc_morning_is_previous_eastern_date(self):
        # 2025-01-06 04:00 UTC = 2025-01-05 23:00 ET (previous day)
        ts = datetime(2025, 1, 6, 4, 0, tzinfo=timezone.utc)
        assert _to_market_date(ts).isoformat() == "2025-01-05"

    def test_utc_afternoon_is_same_eastern_date(self):
        # 2025-01-06 15:00 UTC = 2025-01-06 10:00 ET (same day)
        ts = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
        assert _to_market_date(ts).isoformat() == "2025-01-06"


class TestDailyBarAggregator:
    def test_first_bar_returns_none(self):
        agg = DailyBarAggregator()
        bar = _make_minute_bar()
        assert agg.add(bar) is None

    def test_same_day_bars_accumulate(self):
        agg = DailyBarAggregator()
        ts1 = datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 6, 14, 31, tzinfo=timezone.utc)
        ts3 = datetime(2025, 1, 6, 14, 32, tzinfo=timezone.utc)

        agg.add(_make_minute_bar(ts=ts1, open_=100, high=102, low=99, close=101, volume=1000))
        agg.add(_make_minute_bar(ts=ts2, open_=101, high=105, low=100, close=103, volume=2000))
        result = agg.add(_make_minute_bar(ts=ts3, open_=103, high=104, low=98, close=102, volume=1500))
        assert result is None  # Still same day

        daily = agg.flush("AAPL")
        assert daily is not None
        assert daily.open == 100.0  # First bar's open
        assert daily.high == 105.0  # Max across all bars
        assert daily.low == 98.0   # Min across all bars
        assert daily.close == 102.0  # Last bar's close
        assert daily.volume == 4500.0  # Sum
        assert daily.timeframe == Timeframe.DAILY

    def test_date_change_emits_previous_day(self):
        agg = DailyBarAggregator()
        # Day 1: Jan 6
        day1_bar = _make_minute_bar(
            ts=datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc),
            open_=100, high=105, low=95, close=102, volume=5000,
        )
        agg.add(day1_bar)

        # Day 2: Jan 7
        day2_bar = _make_minute_bar(
            ts=datetime(2025, 1, 7, 14, 30, tzinfo=timezone.utc),
            open_=103, high=106, low=101, close=104, volume=3000,
        )
        daily = agg.add(day2_bar)

        assert daily is not None
        assert daily.open == 100.0
        assert daily.high == 105.0
        assert daily.low == 95.0
        assert daily.close == 102.0
        assert daily.volume == 5000.0
        assert daily.symbol == "AAPL"
        assert daily.timeframe == Timeframe.DAILY

    def test_flush_returns_accumulated_bar(self):
        agg = DailyBarAggregator()
        agg.add(_make_minute_bar(open_=100, high=110, low=90, close=105, volume=7000))
        daily = agg.flush("AAPL")
        assert daily is not None
        assert daily.open == 100.0
        assert daily.volume == 7000.0

    def test_flush_empty_returns_none(self):
        agg = DailyBarAggregator()
        assert agg.flush("AAPL") is None

    def test_flush_all(self):
        agg = DailyBarAggregator()
        ts = datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)
        agg.add(_make_minute_bar(symbol="AAPL", ts=ts))
        agg.add(_make_minute_bar(symbol="MSFT", ts=ts))
        bars = agg.flush_all()
        assert len(bars) == 2
        symbols = {b.symbol for b in bars}
        assert symbols == {"AAPL", "MSFT"}

    def test_multiple_symbols_independent(self):
        agg = DailyBarAggregator()
        ts1 = datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 7, 14, 30, tzinfo=timezone.utc)

        agg.add(_make_minute_bar(symbol="AAPL", ts=ts1, close=150))
        agg.add(_make_minute_bar(symbol="MSFT", ts=ts1, close=300))

        # Only AAPL gets new day bar
        aapl_daily = agg.add(_make_minute_bar(symbol="AAPL", ts=ts2, close=155))
        assert aapl_daily is not None
        assert aapl_daily.symbol == "AAPL"

        # MSFT still accumulating day 1
        msft_daily = agg.flush("MSFT")
        assert msft_daily is not None
        assert msft_daily.symbol == "MSFT"

    def test_ohlcv_accumulation_correctness(self):
        agg = DailyBarAggregator()
        base_ts = datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)

        # Simulate 5 minute bars
        bars_data = [
            (100, 102, 99, 101, 1000),
            (101, 108, 100, 107, 2000),
            (107, 109, 105, 106, 1500),
            (106, 107, 93, 95, 3000),
            (95, 96, 92, 94, 2500),
        ]
        for i, (o, h, l, c, v) in enumerate(bars_data):
            agg.add(_make_minute_bar(
                ts=base_ts + timedelta(minutes=i),
                open_=o, high=h, low=l, close=c, volume=v,
            ))

        daily = agg.flush("AAPL")
        assert daily is not None
        assert daily.open == 100.0   # First bar's open
        assert daily.high == 109.0   # Max high across all bars
        assert daily.low == 92.0     # Min low across all bars
        assert daily.close == 94.0   # Last bar's close
        assert daily.volume == 10000.0  # Sum of all volumes

    def test_daily_bar_has_daily_timeframe(self):
        agg = DailyBarAggregator()
        ts1 = datetime(2025, 1, 6, 20, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 7, 14, 30, tzinfo=timezone.utc)
        agg.add(_make_minute_bar(ts=ts1))
        daily = agg.add(_make_minute_bar(ts=ts2))
        assert daily is not None
        assert daily.timeframe == Timeframe.DAILY

    def test_flush_all_clears_state(self):
        agg = DailyBarAggregator()
        agg.add(_make_minute_bar(symbol="AAPL"))
        agg.flush_all()
        assert agg.flush("AAPL") is None
