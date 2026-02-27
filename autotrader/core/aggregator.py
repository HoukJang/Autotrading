"""Daily bar aggregator for converting minute bars to daily bars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta

from zoneinfo import ZoneInfo

from autotrader.core.types import Bar, Timeframe

_US_EASTERN = ZoneInfo("America/New_York")


def _to_market_date(utc_ts: datetime) -> date:
    """Convert UTC timestamp to US Eastern trading date."""
    return utc_ts.astimezone(_US_EASTERN).date()


@dataclass
class _DayAccumulator:
    """Accumulates OHLCV data for a single trading day."""
    symbol: str
    market_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    first_ts: datetime
    last_ts: datetime
    bar_count: int = 1

    def update(self, bar: Bar) -> None:
        self.high = max(self.high, bar.high)
        self.low = min(self.low, bar.low)
        self.close = bar.close
        self.volume += bar.volume
        self.last_ts = bar.timestamp
        self.bar_count += 1

    def to_daily_bar(self) -> Bar:
        return Bar(
            symbol=self.symbol,
            timestamp=self.last_ts,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            timeframe=Timeframe.DAILY,
        )


class DailyBarAggregator:
    """Aggregates minute bars into daily bars per symbol.

    Call add() with each incoming minute bar. When the trading date
    changes for a symbol, the previous day's accumulated bar is returned.
    Call flush() or flush_all() to force output of current accumulators.
    """

    def __init__(self) -> None:
        self._accumulators: dict[str, _DayAccumulator] = {}

    def add(self, bar: Bar) -> Bar | None:
        """Add a minute bar. Returns completed daily bar if date changed, else None."""
        market_date = _to_market_date(bar.timestamp)
        symbol = bar.symbol
        acc = self._accumulators.get(symbol)

        if acc is None:
            # First bar for this symbol
            self._accumulators[symbol] = _DayAccumulator(
                symbol=symbol,
                market_date=market_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                first_ts=bar.timestamp,
                last_ts=bar.timestamp,
            )
            return None

        if market_date != acc.market_date:
            # New trading day - emit previous day's bar
            daily_bar = acc.to_daily_bar()
            self._accumulators[symbol] = _DayAccumulator(
                symbol=symbol,
                market_date=market_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                first_ts=bar.timestamp,
                last_ts=bar.timestamp,
            )
            return daily_bar

        # Same day - accumulate
        acc.update(bar)
        return None

    def flush(self, symbol: str) -> Bar | None:
        """Force output the current accumulator for a symbol."""
        acc = self._accumulators.pop(symbol, None)
        if acc is None:
            return None
        return acc.to_daily_bar()

    def flush_all(self) -> list[Bar]:
        """Force output all current accumulators."""
        bars = []
        for acc in self._accumulators.values():
            bars.append(acc.to_daily_bar())
        self._accumulators.clear()
        return bars
