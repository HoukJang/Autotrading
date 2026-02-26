from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from autotrader.universe.earnings import EarningsCalendar


class TestEarningsCalendar:
    """Earnings blackout tests use 2026-04-23 (Thursday) as earnings date.

    Business day map around 2026-04-23:
      04/16 Thu = E-5, 04/17 Fri = E-4, 04/20 Mon = E-3,
      04/21 Tue = E-2, 04/22 Wed = E-1, 04/23 Thu = E day,
      04/24 Fri = E+1, 04/27 Mon = E+2
    """

    def test_is_blackout_before_earnings(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 23)  # Thursday
        cal._cache = {"AAPL": earnings_date}
        # E-5 through E+1 = blackout
        assert cal.is_blackout("AAPL", date(2026, 4, 16)) is True   # E-5 (Thursday)
        assert cal.is_blackout("AAPL", date(2026, 4, 22)) is True   # E-1 (Wednesday)
        assert cal.is_blackout("AAPL", date(2026, 4, 23)) is True   # E day (Thursday)

    def test_is_blackout_after_earnings(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 23)  # Thursday
        cal._cache = {"AAPL": earnings_date}
        assert cal.is_blackout("AAPL", date(2026, 4, 24)) is True   # E+1 (Friday)
        assert cal.is_blackout("AAPL", date(2026, 4, 27)) is False  # E+2 (Monday)

    def test_not_blackout_before_window(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 23)  # Thursday
        cal._cache = {"AAPL": earnings_date}
        # E-6 should NOT be blackout
        assert cal.is_blackout("AAPL", date(2026, 4, 15)) is False  # E-6 (Wednesday)

    def test_no_earnings_not_blackout(self):
        cal = EarningsCalendar()
        cal._cache = {}
        assert cal.is_blackout("AAPL", date(2026, 3, 1)) is False

    def test_should_force_close(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 23)  # Thursday
        cal._cache = {"AAPL": earnings_date}
        # E-3 = force close (Monday 04/20)
        assert cal.should_force_close("AAPL", date(2026, 4, 20)) is True
        # E-4 = NOT force close (Friday 04/17)
        assert cal.should_force_close("AAPL", date(2026, 4, 17)) is False

    def test_unknown_symbol_not_blackout(self):
        cal = EarningsCalendar()
        cal._cache = {}
        assert cal.is_blackout("UNKNOWN", date(2026, 3, 1)) is False
        assert cal.should_force_close("UNKNOWN", date(2026, 3, 1)) is False

    def test_fetch_earnings_calls_yfinance(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [date(2026, 4, 23)]}
        with patch("yfinance.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            cal.fetch(["AAPL"])
        assert "AAPL" in cal._cache

    def test_fetch_earnings_handles_missing(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        with patch("yfinance.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            cal.fetch(["AAPL"])
        assert "AAPL" not in cal._cache

    def test_blackout_symbols_filters_list(self):
        cal = EarningsCalendar()
        cal._cache = {
            "AAPL": date(2026, 4, 23),   # Thursday - check_date 04/20 is E-3 -> blackout
            "MSFT": date(2026, 5, 15),    # Far away -> not blackout
            "GOOGL": date(2026, 4, 27),   # Monday - check_date 04/20 is E-5 -> blackout
        }
        check_date = date(2026, 4, 20)  # Monday
        blackout = cal.blackout_symbols(["AAPL", "MSFT", "GOOGL"], check_date)
        assert "AAPL" in blackout
        assert "MSFT" not in blackout
