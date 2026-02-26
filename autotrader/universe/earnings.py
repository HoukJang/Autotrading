from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_BLACKOUT_BEFORE = 5  # business days before earnings
_BLACKOUT_AFTER = 1   # business days after earnings
_FORCE_CLOSE_BEFORE = 3  # business days before earnings


def _business_days_between(d1: date, d2: date) -> int:
    """Count business days from d1 to d2 (d2 > d1 means positive)."""
    if d1 > d2:
        return -_business_days_between(d2, d1)
    days = 0
    current = d1
    while current < d2:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


class EarningsCalendar:
    def __init__(self) -> None:
        self._cache: dict[str, date] = {}

    def fetch(self, symbols: list[str]) -> None:
        import yfinance
        for symbol in symbols:
            try:
                ticker = yfinance.Ticker(symbol)
                cal = ticker.calendar
                if cal is None:
                    continue
                if isinstance(cal, dict):
                    dates = cal.get("Earnings Date", [])
                else:
                    dates = []
                if dates:
                    ear_date = dates[0]
                    if isinstance(ear_date, date):
                        self._cache[symbol] = ear_date
                    else:
                        self._cache[symbol] = (
                            ear_date.date() if hasattr(ear_date, "date") else ear_date
                        )
            except Exception:
                logger.debug("Failed to fetch earnings for %s", symbol)

    def is_blackout(self, symbol: str, check_date: date) -> bool:
        earnings = self._cache.get(symbol)
        if earnings is None:
            return False
        bdays_to_earnings = _business_days_between(check_date, earnings)
        if bdays_to_earnings < 0:
            return abs(bdays_to_earnings) <= _BLACKOUT_AFTER
        return bdays_to_earnings <= _BLACKOUT_BEFORE

    def should_force_close(self, symbol: str, check_date: date) -> bool:
        earnings = self._cache.get(symbol)
        if earnings is None:
            return False
        bdays = _business_days_between(check_date, earnings)
        return bdays == _FORCE_CLOSE_BEFORE

    def blackout_symbols(self, symbols: list[str], check_date: date) -> list[str]:
        return [s for s in symbols if self.is_blackout(s, check_date)]
