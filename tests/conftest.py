"""
Pytest configuration and fixtures for Paper Trading integration tests
Provides real IB Gateway connection fixtures
"""

import pytest
import pytest_asyncio
import asyncio
import sys
import os
import logging
from typing import AsyncGenerator

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'autotrading'))

from broker import IBConnectionManager, IBClient
from broker.contracts import ContractFactory
from core.event_bus import EventBus
from config import get_config

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def event_loop():
    """
    Create new event loop for each test
    Critical for Windows ProactorEventLoop which cannot be reused
    """
    # Force new event loop creation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    yield loop

    # Clean up all pending tasks
    try:
        pending = asyncio.all_tasks(loop)
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass

    # Close and clean up loop
    try:
        loop.close()
    except Exception:
        pass


@pytest.fixture
def config():
    """Get real configuration (Paper Trading)"""
    return get_config()


@pytest_asyncio.fixture
async def event_bus() -> AsyncGenerator[EventBus, None]:
    """Create event bus for testing"""
    bus = EventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest_asyncio.fixture
async def ib_connection(event_bus) -> AsyncGenerator[IBConnectionManager, None]:
    """
    Create real IB Gateway connection
    Requires IB Gateway Paper Trading running on port 4002
    """
    connection = IBConnectionManager(event_bus)

    try:
        # Connect to IB Gateway
        connected = await connection.connect()
        if not connected:
            pytest.skip("IB Gateway not running - skipping test")

        yield connection

    finally:
        # Disconnect after test
        await connection.disconnect()
        await asyncio.sleep(0.5)  # Allow cleanup


@pytest_asyncio.fixture
async def ib_client(event_bus) -> AsyncGenerator[IBClient, None]:
    """
    Create real IB Client with Paper Trading connection
    Requires IB Gateway Paper Trading running on port 4002
    """
    client = IBClient(event_bus)

    try:
        # Connect to IB Gateway
        connected = await client.connect()
        if not connected:
            pytest.skip("IB Gateway not running - skipping test")

        yield client

    finally:
        # Disconnect after test
        await client.disconnect()
        await asyncio.sleep(0.5)  # Allow cleanup


@pytest.fixture
def contract_factory():
    """Create contract factory for futures contracts"""
    return ContractFactory()


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

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.metrics = {}

        def start(self):
            self.start_time = time.perf_counter()

        def stop(self):
            self.end_time = time.perf_counter()
            return self.elapsed_time

        @property
        def elapsed_time(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

        def record_metric(self, name, value):
            self.metrics[name] = value

        def get_metrics(self):
            return self.metrics

    return PerformanceMonitor()


# Pytest markers configuration
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "paper_trading: Tests requiring Paper Trading connection")
    config.addinivalue_line("markers", "integration: Integration tests with real API")
    config.addinivalue_line("markers", "slow: Slow tests that take more than 5 seconds")
    config.addinivalue_line("markers", "edge_case: Edge case and boundary condition tests")
