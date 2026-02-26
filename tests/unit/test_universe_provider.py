from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from autotrader.universe import StockInfo, StockCandidate, ScoredCandidate, UniverseResult
from autotrader.universe.provider import SP500Provider


class TestStockInfo:
    def test_create(self):
        info = StockInfo(symbol="AAPL", sector="Technology", sub_industry="Consumer Electronics")
        assert info.symbol == "AAPL"
        assert info.sector == "Technology"

    def test_equality(self):
        a = StockInfo("AAPL", "Tech", "HW")
        b = StockInfo("AAPL", "Tech", "HW")
        assert a == b


class TestStockCandidate:
    def test_create(self):
        c = StockCandidate(
            symbol="AAPL", sector="Technology", close=150.0,
            avg_dollar_volume=100e6, avg_volume=2e6,
            atr_ratio=0.02, gap_frequency=0.05,
            trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
        )
        assert c.symbol == "AAPL"
        assert c.avg_dollar_volume == 100e6


class TestScoredCandidate:
    def test_create(self):
        c = StockCandidate(
            symbol="AAPL", sector="Technology", close=150.0,
            avg_dollar_volume=100e6, avg_volume=2e6,
            atr_ratio=0.02, gap_frequency=0.05,
            trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
        )
        sc = ScoredCandidate(candidate=c, proxy_score=0.8, backtest_score=0.6, final_score=0.7)
        assert sc.final_score == 0.7


class TestSP500Provider:
    def test_fetch_returns_list_of_stock_info(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT", "GOOGL"],
            "GICS Sector": ["Information Technology", "Information Technology", "Communication Services"],
            "GICS Sub-Industry": ["Technology Hardware", "Systems Software", "Interactive Media"],
        })
        with patch("pandas.read_html", return_value=[fake_df]):
            provider = SP500Provider()
            result = provider.fetch()
        assert len(result) == 3
        assert isinstance(result[0], StockInfo)
        assert result[0].symbol == "AAPL"
        assert result[0].sector == "Information Technology"

    def test_fetch_cleans_dot_symbols(self):
        """BRK.B -> BRK-B for Alpaca compatibility."""
        fake_df = pd.DataFrame({
            "Symbol": ["BRK.B", "BF.B"],
            "GICS Sector": ["Financials", "Consumer Staples"],
            "GICS Sub-Industry": ["Insurance", "Distillers"],
        })
        with patch("pandas.read_html", return_value=[fake_df]):
            provider = SP500Provider()
            result = provider.fetch()
        symbols = [s.symbol for s in result]
        assert "BRK-B" in symbols
        assert "BF-B" in symbols

    def test_fetch_caches_result(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "GICS Sector": ["IT"],
            "GICS Sub-Industry": ["HW"],
        })
        with patch("pandas.read_html", return_value=[fake_df]) as mock_read:
            provider = SP500Provider()
            provider.fetch()
            provider.fetch()
        assert mock_read.call_count == 1

    def test_fetch_force_refresh(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "GICS Sector": ["IT"],
            "GICS Sub-Industry": ["HW"],
        })
        with patch("pandas.read_html", return_value=[fake_df]) as mock_read:
            provider = SP500Provider()
            provider.fetch()
            provider.fetch(force_refresh=True)
        assert mock_read.call_count == 2
