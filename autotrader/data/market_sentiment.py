"""VIX-based market sentiment classification.

Fetches VIX data from yfinance and classifies into sentiment levels.
Includes time-based caching and graceful fallback on fetch failure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import yfinance
except ImportError:
    yfinance = None  # type: ignore[assignment]


class SentimentLevel(Enum):
    """Market sentiment classification based on VIX levels."""

    LOW = "LOW"  # VIX < 15
    NORMAL = "NORMAL"  # 15 <= VIX < 20
    ELEVATED = "ELEVATED"  # 20 <= VIX < 25
    HIGH = "HIGH"  # 25 <= VIX < 35
    EXTREME = "EXTREME"  # VIX >= 35


@dataclass(frozen=True)
class MarketSentiment:
    """Point-in-time market sentiment snapshot."""

    vix_value: float
    level: SentimentLevel
    timestamp: datetime


def classify_vix(vix_value: float) -> SentimentLevel:
    """Classify a VIX value into a sentiment level.

    Thresholds:
        < 15  -> LOW
        15-19 -> NORMAL
        20-24 -> ELEVATED
        25-34 -> HIGH
        >= 35 -> EXTREME

    Args:
        vix_value: Current VIX index value.

    Returns:
        Corresponding SentimentLevel.
    """
    if vix_value < 15.0:
        return SentimentLevel.LOW
    if vix_value < 20.0:
        return SentimentLevel.NORMAL
    if vix_value < 25.0:
        return SentimentLevel.ELEVATED
    if vix_value < 35.0:
        return SentimentLevel.HIGH
    return SentimentLevel.EXTREME


class VIXFetcher:
    """Fetches VIX data with caching and graceful fallback.

    Uses yfinance to retrieve VIX closing prices. Results are cached
    for ``cache_ttl_seconds`` to avoid excessive API calls. On any
    fetch failure, returns a NORMAL fallback sentiment so callers
    always receive a valid result.
    """

    def __init__(self, symbol: str = "^VIX", cache_ttl_seconds: int = 3600) -> None:
        self._symbol = symbol
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cached: MarketSentiment | None = None
        self._cache_time: datetime | None = None

    def get_sentiment(self) -> MarketSentiment:
        """Get current market sentiment. Returns cached if within TTL.

        Returns:
            MarketSentiment with current VIX value and classification.
            Falls back to NORMAL with vix_value=0.0 on any failure.
        """
        now = datetime.now(timezone.utc)

        # Return cache if valid
        if (
            self._cached is not None
            and self._cache_time is not None
            and (now - self._cache_time) < self._cache_ttl
        ):
            return self._cached

        # Fetch fresh data
        try:
            return self._fetch(now)
        except Exception:
            logger.warning("VIX fetch failed, returning NORMAL fallback")
            return MarketSentiment(
                vix_value=0.0,
                level=SentimentLevel.NORMAL,
                timestamp=now,
            )

    def _fetch(self, now: datetime) -> MarketSentiment:
        """Fetch VIX data from yfinance.

        Args:
            now: Current UTC timestamp for cache bookkeeping.

        Returns:
            MarketSentiment with fetched VIX value.

        Raises:
            ImportError: If yfinance is not installed.
        """
        if yfinance is None:
            raise ImportError("yfinance not installed")

        ticker = yfinance.Ticker(self._symbol)
        hist = ticker.history(period="5d")

        if hist.empty:
            logger.warning("VIX history is empty, returning NORMAL fallback")
            return MarketSentiment(
                vix_value=0.0,
                level=SentimentLevel.NORMAL,
                timestamp=now,
            )

        vix_value = float(hist["Close"].iloc[-1])
        level = classify_vix(vix_value)

        sentiment = MarketSentiment(
            vix_value=vix_value,
            level=level,
            timestamp=now,
        )

        # Update cache
        self._cached = sentiment
        self._cache_time = now

        return sentiment
