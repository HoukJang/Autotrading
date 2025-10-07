"""
Pytest configuration and fixtures for IB API testing
Provides common fixtures and test configuration
"""

import pytest
import asyncio
import sys
import os
import logging
from unittest.mock import Mock, patch
from typing import AsyncGenerator, Generator

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'autotrading'))

# Import test mocks
from tests.mocks.ib_mocks import MockIB, patch_ib_imports

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def mock_ib_imports():
    """Automatically mock IB imports for all tests"""
    with patch.dict('sys.modules', {
        'ib_async': Mock(),
        'ib_async.IB': MockIB,
        'ib_async.Contract': Mock(),
        'ib_async.MarketOrder': Mock(),
        'ib_async.LimitOrder': Mock(),
        'ib_async.BracketOrder': Mock(),
    }):
        yield


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    config = Mock()
    config.broker.host = "127.0.0.1"
    config.broker.port = 7497
    config.broker.client_id = 1
    config.logging.level = "DEBUG"
    return config


@pytest.fixture
def mock_event_bus():
    """Mock event bus for testing"""
    return Mock()


@pytest.fixture
async def clean_environment():
    """Ensure clean test environment"""
    # Clean up any existing connections or resources
    yield
    # Cleanup after test
    await asyncio.sleep(0.1)  # Allow async cleanup


@pytest.fixture
def financial_precision_validator():
    """Validator for financial precision requirements"""
    from decimal import Decimal

    def validate_precision(value, expected_places=2):
        """Validate that value maintains expected decimal precision"""
        if isinstance(value, (int, float)):
            value = Decimal(str(value))

        assert isinstance(value, Decimal), f"Expected Decimal, got {type(value)}"

        # Check that value has correct precision
        sign, digits, exponent = value.as_tuple()
        if exponent < 0:
            actual_places = -exponent
            assert actual_places <= expected_places, \
                f"Value {value} has {actual_places} decimal places, expected max {expected_places}"

        return True

    return validate_precision


@pytest.fixture
def performance_monitor():
    """Monitor performance metrics during tests"""
    import time
    import psutil
    import os

    class PerformanceMonitor:
        def __init__(self):
            self.process = psutil.Process(os.getpid())
            self.start_time = None
            self.start_memory = None
            self.peak_memory = None

        def start(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = self.start_memory

        def checkpoint(self, name=""):
            current_memory = self.process.memory_info().rss / 1024 / 1024
            self.peak_memory = max(self.peak_memory, current_memory)
            elapsed = time.time() - self.start_time if self.start_time else 0
            logger.debug(f"Performance checkpoint {name}: {elapsed:.3f}s, {current_memory:.1f}MB")

        def stop(self):
            if self.start_time:
                elapsed = time.time() - self.start_time
                final_memory = self.process.memory_info().rss / 1024 / 1024
                memory_delta = final_memory - self.start_memory

                logger.info(f"Performance summary: {elapsed:.3f}s, "
                          f"memory: {self.start_memory:.1f}MB -> {final_memory:.1f}MB "
                          f"(peak: {self.peak_memory:.1f}MB, delta: {memory_delta:.1f}MB)")

                return {
                    'elapsed_time': elapsed,
                    'start_memory': self.start_memory,
                    'final_memory': final_memory,
                    'peak_memory': self.peak_memory,
                    'memory_delta': memory_delta
                }

    return PerformanceMonitor()


@pytest.fixture
def market_data_simulator():
    """Simulate realistic market data for testing"""
    from decimal import Decimal
    import random
    from datetime import datetime, timedelta

    class MarketDataSimulator:
        def __init__(self, base_price=4500.0, volatility=0.5):
            self.base_price = Decimal(str(base_price))
            self.volatility = volatility
            self.current_price = self.base_price
            self.tick_count = 0

        def generate_tick(self):
            """Generate realistic tick data"""
            # Simulate price movement
            change = Decimal(str(random.uniform(-self.volatility, self.volatility)))
            self.current_price += change

            # Ensure price doesn't go negative
            if self.current_price < Decimal('1.0'):
                self.current_price = Decimal('1.0')

            spread = Decimal('0.25')
            bid = self.current_price - (spread / 2)
            ask = self.current_price + (spread / 2)

            self.tick_count += 1

            return {
                'timestamp': datetime.now(),
                'bid': bid,
                'ask': ask,
                'last': self.current_price,
                'bid_size': random.randint(5, 50),
                'ask_size': random.randint(5, 50),
                'volume': self.tick_count * random.randint(1, 10)
            }

        def generate_bars(self, count=100, interval_minutes=1):
            """Generate historical bar data"""
            bars = []
            current_time = datetime.now()

            for i in range(count):
                bar_time = current_time - timedelta(minutes=(count - i) * interval_minutes)

                # Generate OHLC
                open_price = self.current_price
                close_change = Decimal(str(random.uniform(-1.0, 1.0)))
                close_price = open_price + close_change

                high_price = max(open_price, close_price) + Decimal(str(random.uniform(0, 0.5)))
                low_price = min(open_price, close_price) - Decimal(str(random.uniform(0, 0.5)))

                bars.append({
                    'timestamp': bar_time,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': random.randint(100, 1000)
                })

                self.current_price = close_price

            return bars

    return MarketDataSimulator


@pytest.fixture
def risk_scenario_generator():
    """Generate various risk scenarios for testing"""

    class RiskScenarioGenerator:
        def __init__(self):
            self.scenarios = {
                'normal': {'volatility': 0.25, 'trend': 0.0},
                'high_volatility': {'volatility': 2.0, 'trend': 0.0},
                'bull_market': {'volatility': 0.5, 'trend': 1.0},
                'bear_market': {'volatility': 0.75, 'trend': -1.0},
                'flash_crash': {'volatility': 5.0, 'trend': -10.0},
                'gap_up': {'volatility': 0.25, 'gap': 5.0},
                'gap_down': {'volatility': 0.25, 'gap': -5.0},
            }

        def get_scenario(self, name):
            """Get predefined scenario parameters"""
            return self.scenarios.get(name, self.scenarios['normal'])

        def simulate_scenario(self, name, duration_minutes=60):
            """Simulate a risk scenario over time"""
            scenario = self.get_scenario(name)
            ticks = []

            base_price = 4500.0
            current_price = base_price

            # Apply gap if specified
            if 'gap' in scenario:
                current_price += scenario['gap']

            for minute in range(duration_minutes):
                # Apply trend
                trend_effect = scenario.get('trend', 0) * 0.1
                current_price += trend_effect

                # Apply volatility
                volatility_effect = random.uniform(
                    -scenario['volatility'],
                    scenario['volatility']
                )
                current_price += volatility_effect

                ticks.append({
                    'minute': minute,
                    'price': current_price,
                    'scenario': name
                })

            return ticks

    return RiskScenarioGenerator()


@pytest.fixture
def test_data_factory():
    """Factory for creating various test data objects"""
    from decimal import Decimal

    class TestDataFactory:
        @staticmethod
        def create_tick_data(symbol="ES", price=4500.0):
            """Create realistic tick data"""
            return {
                'symbol': symbol,
                'timestamp': asyncio.get_event_loop().time(),
                'bid_price': Decimal(str(price - 0.125)),
                'ask_price': Decimal(str(price + 0.125)),
                'last_price': Decimal(str(price)),
                'bid_size': 25,
                'ask_size': 30,
                'volume': 1500
            }

        @staticmethod
        def create_order_data(symbol="ES", action="BUY", quantity=1, order_type="MKT"):
            """Create order data"""
            return {
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'order_type': order_type,
                'limit_price': Decimal('4500.00') if order_type == "LMT" else None,
                'stop_price': Decimal('4495.00') if order_type == "STP" else None
            }

        @staticmethod
        def create_position_data(symbol="ES", quantity=2, avg_cost=4500.0):
            """Create position data"""
            return {
                'symbol': symbol,
                'quantity': quantity,
                'avg_cost': Decimal(str(avg_cost)),
                'market_price': Decimal(str(avg_cost + 1.0)),
                'unrealized_pnl': Decimal('100.00'),
                'realized_pnl': Decimal('50.00')
            }

    return TestDataFactory()


# Pytest markers for test categorization
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "reliability: Reliability tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_tws: Tests requiring actual TWS connection")


# Test collection modifiers
def pytest_collection_modifyitems(config, items):
    """Modify test collection based on command line options"""
    if config.getoption("--no-slow"):
        skip_slow = pytest.mark.skip(reason="--no-slow option given")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--no-slow", action="store_true", default=False,
        help="Skip slow running tests"
    )
    parser.addoption(
        "--performance", action="store_true", default=False,
        help="Run performance tests"
    )
    parser.addoption(
        "--with-tws", action="store_true", default=False,
        help="Run tests that require actual TWS connection"
    )