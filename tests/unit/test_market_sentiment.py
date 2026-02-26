"""Unit tests for VIX-based market sentiment classification."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from autotrader.data.market_sentiment import (
    SentimentLevel,
    MarketSentiment,
    VIXFetcher,
    classify_vix,
)


class TestSentimentLevel:
    def test_enum_values(self):
        assert SentimentLevel.LOW.value == "LOW"
        assert SentimentLevel.NORMAL.value == "NORMAL"
        assert SentimentLevel.ELEVATED.value == "ELEVATED"
        assert SentimentLevel.HIGH.value == "HIGH"
        assert SentimentLevel.EXTREME.value == "EXTREME"


class TestClassifyVix:
    def test_low_vix(self):
        assert classify_vix(12.0) == SentimentLevel.LOW

    def test_normal_vix(self):
        assert classify_vix(17.0) == SentimentLevel.NORMAL

    def test_elevated_vix(self):
        assert classify_vix(22.0) == SentimentLevel.ELEVATED

    def test_high_vix(self):
        assert classify_vix(30.0) == SentimentLevel.HIGH

    def test_extreme_vix(self):
        assert classify_vix(40.0) == SentimentLevel.EXTREME

    def test_boundary_15(self):
        assert classify_vix(15.0) == SentimentLevel.NORMAL

    def test_boundary_20(self):
        assert classify_vix(20.0) == SentimentLevel.ELEVATED

    def test_boundary_25(self):
        assert classify_vix(25.0) == SentimentLevel.HIGH

    def test_boundary_35(self):
        assert classify_vix(35.0) == SentimentLevel.EXTREME


class TestMarketSentiment:
    def test_create_sentiment(self):
        s = MarketSentiment(
            vix_value=18.5,
            level=SentimentLevel.NORMAL,
            timestamp=datetime.now(timezone.utc),
        )
        assert s.vix_value == 18.5
        assert s.level == SentimentLevel.NORMAL

    def test_sentiment_is_frozen(self):
        s = MarketSentiment(
            vix_value=18.5,
            level=SentimentLevel.NORMAL,
            timestamp=datetime.now(timezone.utc),
        )
        with pytest.raises(AttributeError):
            s.vix_value = 25.0


class TestVIXFetcher:
    def test_default_fallback(self):
        """When fetch fails, return NORMAL."""
        fetcher = VIXFetcher(symbol="^VIX", cache_ttl_seconds=3600)
        with patch("autotrader.data.market_sentiment.yfinance") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("network error")
            sentiment = fetcher.get_sentiment()
            assert sentiment.level == SentimentLevel.NORMAL
            assert sentiment.vix_value == 0.0

    def test_successful_fetch(self):
        fetcher = VIXFetcher(symbol="^VIX", cache_ttl_seconds=3600)
        with patch("autotrader.data.market_sentiment.yfinance") as mock_yf:
            ticker_instance = MagicMock()
            mock_yf.Ticker.return_value = ticker_instance
            hist_df = MagicMock()
            hist_df.empty = False
            # Mock the Close column's last value
            close_col = MagicMock()
            close_col.iloc.__getitem__ = MagicMock(return_value=22.5)
            hist_df.__getitem__ = MagicMock(return_value=close_col)
            ticker_instance.history.return_value = hist_df
            sentiment = fetcher.get_sentiment()
            assert sentiment.level == SentimentLevel.ELEVATED
            assert sentiment.vix_value == 22.5

    def test_cache_returns_previous(self):
        """Second call within TTL returns cached result."""
        fetcher = VIXFetcher(symbol="^VIX", cache_ttl_seconds=3600)
        # Manually set cache
        cached = MarketSentiment(
            vix_value=18.0,
            level=SentimentLevel.NORMAL,
            timestamp=datetime.now(timezone.utc),
        )
        fetcher._cached = cached
        fetcher._cache_time = datetime.now(timezone.utc)
        result = fetcher.get_sentiment()
        assert result.vix_value == 18.0

    def test_empty_history_returns_fallback(self):
        fetcher = VIXFetcher(symbol="^VIX", cache_ttl_seconds=3600)
        with patch("autotrader.data.market_sentiment.yfinance") as mock_yf:
            ticker_instance = MagicMock()
            mock_yf.Ticker.return_value = ticker_instance
            hist_df = MagicMock()
            hist_df.empty = True
            ticker_instance.history.return_value = hist_df
            sentiment = fetcher.get_sentiment()
            assert sentiment.level == SentimentLevel.NORMAL
