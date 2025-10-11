"""
Phase 3 Data Pipeline Tests
Tests for bar building, data validation, and storage
"""

import pytest
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Phase 3 components
from data.bar_builder import BarState, BarBuilder
from data.data_validator import DataValidator
from data.bar_storage import BarStorage
from core.events import MarketBar
from core.event_bus import EventBus
from broker.ib_client import TickEvent


class TestBarState:
    """Test BarState class for bar aggregation"""

    def test_bar_state_initialization(self):
        """Test bar state creation"""
        timestamp = datetime.now()
        bar = BarState("ES", timestamp)

        assert bar.symbol == "ES"
        assert bar.timestamp == timestamp
        assert bar.open_price is None
        assert bar.tick_count == 0
        assert bar.volume == 0

    def test_add_tick(self):
        """Test adding ticks to bar"""
        bar = BarState("ES", datetime.now())

        # Add first tick
        bar.add_tick(Decimal("4500.00"), 10)
        assert bar.open_price == Decimal("4500.00")
        assert bar.high_price == Decimal("4500.00")
        assert bar.low_price == Decimal("4500.00")
        assert bar.close_price == Decimal("4500.00")
        assert bar.volume == 10
        assert bar.tick_count == 1

        # Add second tick (higher)
        bar.add_tick(Decimal("4501.00"), 20)
        assert bar.open_price == Decimal("4500.00")  # Open doesn't change
        assert bar.high_price == Decimal("4501.00")
        assert bar.low_price == Decimal("4500.00")
        assert bar.close_price == Decimal("4501.00")  # Close updates
        assert bar.volume == 30
        assert bar.tick_count == 2

        # Add third tick (lower)
        bar.add_tick(Decimal("4499.00"), 15)
        assert bar.low_price == Decimal("4499.00")
        assert bar.close_price == Decimal("4499.00")
        assert bar.volume == 45
        assert bar.tick_count == 3

    def test_to_market_bar(self):
        """Test conversion to MarketBar"""
        timestamp = datetime.now()
        bar = BarState("ES", timestamp)

        # Empty bar should return None
        market_bar = bar.to_market_bar()
        assert market_bar is None

        # Add tick and convert
        bar.add_tick(Decimal("4500.00"), 10)
        bar.add_tick(Decimal("4501.00"), 20)

        market_bar = bar.to_market_bar()
        assert market_bar is not None
        assert market_bar.symbol == "ES"
        assert market_bar.timestamp == timestamp
        assert market_bar.open_price == Decimal("4500.00")
        assert market_bar.high_price == Decimal("4501.00")
        assert market_bar.volume == 30
        assert market_bar.tick_count == 2


class TestDataValidator:
    """Test DataValidator class"""

    def test_valid_bar(self):
        """Test validation of a valid bar"""
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("4500.00"),
            high_price=Decimal("4505.00"),
            low_price=Decimal("4495.00"),
            close_price=Decimal("4502.00"),
            volume=1000,
            vwap=Decimal("4500.50"),
            tick_count=100
        )

        validator = DataValidator()
        is_valid, errors = validator.validate_bar(bar)
        assert is_valid
        assert len(errors) == 0

    def test_invalid_ohlc_relationship(self):
        """Test detection of invalid OHLC relationships"""
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("4500.00"),
            high_price=Decimal("4490.00"),  # High < Low (invalid!)
            low_price=Decimal("4495.00"),
            close_price=Decimal("4502.00"),
            volume=1000,
            tick_count=100
        )

        validator = DataValidator()
        is_valid, errors = validator.validate_bar(bar)
        assert not is_valid
        assert len(errors) > 0

    def test_invalid_prices(self):
        """Test detection of invalid prices"""
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("-100.00"),  # Negative price (invalid!)
            high_price=Decimal("4505.00"),
            low_price=Decimal("4495.00"),
            close_price=Decimal("4502.00"),
            volume=1000,
            tick_count=100
        )

        validator = DataValidator()
        is_valid, errors = validator.validate_bar(bar)
        assert not is_valid

    def test_detect_anomalies_zero_volume(self):
        """Test detection of zero volume anomaly"""
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("4500.00"),
            high_price=Decimal("4505.00"),
            low_price=Decimal("4495.00"),
            close_price=Decimal("4502.00"),
            volume=0,  # Zero volume
            tick_count=100
        )

        validator = DataValidator()
        anomalies = validator.detect_anomalies(bar)
        assert len(anomalies) > 0
        assert any("volume" in a.lower() for a in anomalies)


@pytest.mark.asyncio
class TestBarBuilder:
    """Test BarBuilder class"""

    async def test_bar_builder_initialization(self):
        """Test bar builder creation"""
        event_bus = EventBus()
        builder = BarBuilder(event_bus, bar_interval_seconds=60)

        assert builder.bar_interval == timedelta(seconds=60)
        assert len(builder._current_bars) == 0

    async def test_tick_to_bar_aggregation(self):
        """Test tick aggregation into bars"""
        event_bus = EventBus()
        builder = BarBuilder(event_bus, bar_interval_seconds=60)

        bars_created = []

        async def on_bar(bar: MarketBar):
            bars_created.append(bar)

        builder.add_bar_callback(on_bar)
        await builder.start()

        # Simulate ticks - all within same minute
        base_timestamp = datetime.now().replace(second=0, microsecond=0)

        for i in range(5):
            tick = TickEvent(
                symbol="ES",
                timestamp=base_timestamp + timedelta(seconds=i),
                last_price=Decimal(f"{4500 + i}.00"),
                last_size=10
            )
            await builder._on_tick_event(tick)

        # Check internal bar state directly
        assert "ES" in builder._current_bars
        internal_bar = builder._current_bars["ES"]
        assert internal_bar.tick_count == 5
        assert internal_bar.volume == 50  # 5 ticks * 10 size each

        # Get current bar via method
        current_bar = builder.get_current_bar("ES")
        assert current_bar is not None
        assert current_bar.symbol == "ES"
        assert current_bar.tick_count == 5
        assert current_bar.open_price == Decimal("4500.00")
        assert current_bar.high_price == Decimal("4504.00")
        assert current_bar.low_price == Decimal("4500.00")
        assert current_bar.close_price == Decimal("4504.00")
        assert current_bar.volume == 50

        await builder.stop()


@pytest.mark.asyncio
class TestBarStorage:
    """Test BarStorage class (requires database)"""

    async def test_bar_storage_initialization(self):
        """Test bar storage creation"""
        storage = BarStorage()
        assert storage.db is not None

    # Note: Full database tests require a running PostgreSQL instance
    # and are better suited for integration testing


def test_import_all_modules():
    """Test that all Phase 3 modules can be imported"""
    from data import (
        BarBuilder,
        BarState,
        DataValidator,
        BarStorage
    )

    # Verify classes are accessible
    assert BarBuilder is not None
    assert BarState is not None
    assert DataValidator is not None
    assert BarStorage is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
