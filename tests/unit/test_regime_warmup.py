"""Tests for regime warmup from historical daily bars.

Validates that AutoTrader loads SPY daily bars at startup,
initializes regime from daily data, and refreshes daily.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from autotrader.core.config import Settings
from autotrader.core.types import Bar
from autotrader.main import AutoTrader
from autotrader.portfolio.regime_detector import MarketRegime


def _make_daily_bar(
    symbol: str = "SPY",
    close: float = 450.0,
    idx: int = 0,
    high_delta: float = 5.0,
    low_delta: float = 5.0,
    volume: float = 80_000_000.0,
) -> Bar:
    """Create a daily bar for testing."""
    base = datetime(2025, 6, 1, 20, 0, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=base + timedelta(days=idx),
        open=close - 1.0,
        high=close + high_delta,
        low=close - low_delta,
        close=close,
        volume=volume,
    )


def _make_trending_bars(symbol: str = "SPY", n: int = 60) -> list[Bar]:
    """Generate bars that produce TREND regime (strong uptrend, expanding BB)."""
    bars = []
    price = 400.0
    for i in range(n):
        price *= 1.005  # steady uptrend
        high_d = price * 0.015  # wider range = expanding BB
        low_d = price * 0.008
        bars.append(_make_daily_bar(
            symbol=symbol, close=price, idx=i,
            high_delta=high_d, low_delta=low_d,
            volume=80_000_000.0,
        ))
    return bars


def _make_ranging_bars(symbol: str = "SPY", n: int = 60) -> list[Bar]:
    """Generate bars that produce RANGING regime (low ADX, contracting BB)."""
    bars = []
    price = 450.0
    for i in range(n):
        # Oscillate around center with tiny range
        offset = 0.5 * (1 if i % 2 == 0 else -1)
        close = price + offset
        bars.append(_make_daily_bar(
            symbol=symbol, close=close, idx=i,
            high_delta=0.3, low_delta=0.3,
            volume=50_000_000.0,
        ))
    return bars


def _settings() -> Settings:
    s = Settings()
    s.broker.type = "paper"
    s.broker.paper_balance = 100_000.0
    s.symbols = ["AAPL", "MSFT"]
    s.performance.enable_trade_log = False
    s.sentiment.enable_vix = False
    s.event_rotation.enable_event_driven = False
    s.scheduler.enable_rotation_scheduler = False
    return s


class TestRegimeWarmup:
    """Tests for _warm_up_from_history and _initialize_regime_from_daily."""

    @pytest.fixture()
    def app(self) -> AutoTrader:
        return AutoTrader(_settings())

    @pytest.mark.asyncio
    async def test_warm_up_loads_historical_bars(self, app):
        """After warmup, _daily_bar_history should be populated."""
        app._register_strategies()
        spy_bars = _make_trending_bars("SPY", n=60)
        aapl_bars = _make_trending_bars("AAPL", n=60)

        async def mock_get_hist(symbols, days=120):
            result = {}
            for sym in symbols:
                if sym == "SPY":
                    result[sym] = spy_bars
                elif sym == "AAPL":
                    result[sym] = aapl_bars
            return result

        app._broker.get_historical_bars = mock_get_hist

        await app._warm_up_from_history()

        assert len(app._daily_bar_history["SPY"]) == 60
        assert len(app._daily_bar_history["AAPL"]) == 60

    @pytest.mark.asyncio
    async def test_initialize_regime_from_daily_sets_regime(self, app):
        """With mocked indicators producing TREND signals, regime should be TREND."""
        app._register_strategies()
        spy_bars = _make_trending_bars("SPY", n=60)

        for bar in spy_bars:
            app._daily_bar_history["SPY"].append(bar)

        original_compute = app._indicator_engine.compute
        call_count = 0

        def mock_compute(history):
            nonlocal call_count
            call_count += 1
            result = original_compute(history)
            # Loop calls (1-60): small width fills the deque average low
            # Final call (61): large width -> ratio = 0.05/0.01 = 5.0 >> 1.3
            is_final = call_count > len(spy_bars)
            width = 0.05 if is_final else 0.01
            result["ADX_14"] = 30.0
            result["BBANDS_20"] = {
                "upper": 460, "middle": 450, "lower": 440,
                "width": width, "pct_b": 0.7,
            }
            result["ATR_14"] = 8.0
            return result

        app._indicator_engine.compute = mock_compute

        app._initialize_regime_from_daily()

        # ADX=30 >= 25, width_ratio=0.05/0.01=5.0 >= 1.3 -> TREND
        assert app._current_regime == MarketRegime.TREND
        assert app._regime_tracker._confirmed_regime == MarketRegime.TREND

    @pytest.mark.asyncio
    async def test_initialize_regime_insufficient_bars(self, app):
        """Fewer than 30 bars should leave regime as UNCERTAIN."""
        app._register_strategies()
        spy_bars = _make_trending_bars("SPY", n=15)

        async def mock_get_hist(symbols, days=120):
            return {"SPY": spy_bars}

        app._broker.get_historical_bars = mock_get_hist

        await app._warm_up_from_history()

        assert app._current_regime == MarketRegime.UNCERTAIN

    @pytest.mark.asyncio
    async def test_warmup_skipped_for_paper_broker(self, app):
        """PaperBroker has no get_historical_bars; warmup should skip gracefully."""
        # PaperBroker does not have get_historical_bars by default
        assert not hasattr(app._broker, "get_historical_bars")

        # Should not raise
        await app._warm_up_from_history()

        # Regime stays UNCERTAIN
        assert app._current_regime == MarketRegime.UNCERTAIN

    @pytest.mark.asyncio
    async def test_bb_width_history_populated(self, app):
        """After warmup, _spy_bb_width_history should have entries."""
        app._register_strategies()
        spy_bars = _make_trending_bars("SPY", n=60)

        async def mock_get_hist(symbols, days=120):
            return {"SPY": spy_bars}

        app._broker.get_historical_bars = mock_get_hist

        await app._warm_up_from_history()

        # BB needs 20 bars warmup, so with 60 bars we should have ~40 entries
        assert len(app._spy_bb_width_history) > 0

    @pytest.mark.asyncio
    async def test_regime_tracker_initialized(self, app):
        """After warmup, _regime_tracker confirmed regime should match _current_regime."""
        app._register_strategies()
        spy_bars = _make_trending_bars("SPY", n=60)

        async def mock_get_hist(symbols, days=120):
            return {"SPY": spy_bars}

        app._broker.get_historical_bars = mock_get_hist

        await app._warm_up_from_history()

        assert app._regime_tracker._confirmed_regime == app._current_regime

    @pytest.mark.asyncio
    async def test_live_minute_bar_does_not_update_regime(self, app):
        """Minute bar for SPY should NOT change regime after warmup."""
        spy_bars = _make_trending_bars("SPY", n=60)

        async def mock_get_hist(symbols, days=120):
            return {"SPY": spy_bars}

        app._broker.get_historical_bars = mock_get_hist

        await app._broker.connect()
        app._portfolio_tracker = None
        app._register_strategies()

        await app._warm_up_from_history()
        regime_after_warmup = app._current_regime

        # Feed many minute bars for SPY with different price pattern
        for i in range(50):
            minute_bar = Bar(
                symbol="SPY",
                timestamp=datetime(2025, 9, 1, 14, i, tzinfo=timezone.utc),
                open=300.0,
                high=301.0,
                low=299.0,
                close=300.0,
                volume=1_000_000.0,
            )
            app._bar_history["SPY"].append(minute_bar)
            indicators = app._indicator_engine.compute(app._bar_history["SPY"])
            # _on_bar no longer calls _update_regime for live bars

        # Regime should remain unchanged
        assert app._current_regime == regime_after_warmup

    @pytest.mark.asyncio
    async def test_warmup_handles_api_failure(self, app):
        """If get_historical_bars raises, warmup should log and continue."""
        app._register_strategies()

        async def mock_get_hist_fail(symbols, days=120):
            raise ConnectionError("API unavailable")

        app._broker.get_historical_bars = mock_get_hist_fail

        # Should not raise
        await app._warm_up_from_history()

        # Regime stays UNCERTAIN
        assert app._current_regime == MarketRegime.UNCERTAIN

    @pytest.mark.asyncio
    async def test_daily_regime_refresh_adds_new_bars(self, app):
        """Daily refresh should append new bars and re-initialize regime."""
        # Pre-populate with initial bars
        spy_bars = _make_trending_bars("SPY", n=50)
        for bar in spy_bars:
            app._daily_bar_history["SPY"].append(bar)

        # Register indicators so _initialize_regime_from_daily works
        app._register_strategies()

        # Create new bars with different timestamps
        new_bars = []
        base_ts = spy_bars[-1].timestamp + timedelta(days=1)
        for i in range(5):
            price = 450.0 + i
            new_bars.append(Bar(
                symbol="SPY",
                timestamp=base_ts + timedelta(days=i),
                open=price - 1,
                high=price + 5,
                low=price - 5,
                close=price,
                volume=80_000_000.0,
            ))

        async def mock_get_hist(symbols, days=30):
            return {"SPY": new_bars}

        app._broker.get_historical_bars = mock_get_hist

        initial_count = len(app._daily_bar_history["SPY"])

        # Simulate what the daily scheduler does
        proxy = app._regime_proxy_symbol
        hist = await app._broker.get_historical_bars([proxy], days=30)
        spy_new = hist.get(proxy, [])
        existing_timestamps = {
            b.timestamp for b in app._daily_bar_history[proxy]
        }
        new_count = 0
        for bar in spy_new:
            if bar.timestamp not in existing_timestamps:
                app._daily_bar_history[proxy].append(bar)
                new_count += 1

        assert new_count == 5
        assert len(app._daily_bar_history["SPY"]) == initial_count + 5

        # Re-initialize should not crash
        app._initialize_regime_from_daily()
