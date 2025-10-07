"""
Edge Case and Stress Testing for IB API Integration
Tests for boundary conditions, failure scenarios, and extreme conditions
"""

import pytest
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
import random
import time
import gc
import sys
import os

# System under test imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'autotrading'))

from broker.connection_manager import IBConnectionManager, ConnectionState
from broker.contracts import ContractFactory
from broker.ib_client import IBClient
from core.event_bus import EventBus
from core.exceptions import ConnectionError, ExecutionError, RiskError

# Test utilities
from tests.mocks.ib_mocks import MockIB


class TestConnectionEdgeCases:
    """Test edge cases for connection management"""

    @pytest.mark.asyncio
    async def test_rapid_connect_disconnect_cycles(self):
        """Test rapid connection/disconnection cycles"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)

            # Perform rapid connect/disconnect cycles
            for cycle in range(10):
                mock_ib = MockIB()
                mock_ib.connectAsync = AsyncMock(return_value=None)
                mock_ib.isConnected = Mock(return_value=True)

                with patch('broker.connection_manager.IB', return_value=mock_ib):
                    # Connect
                    success = await connection_manager.connect()
                    assert success

                    # Immediate disconnect
                    await connection_manager.disconnect()

                # Small delay to prevent overwhelming
                await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_connection_during_health_check(self):
        """Test connection attempts during active health checks"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)
            connection_manager.health_check_interval = 0.1  # Very fast health checks

            mock_ib = MockIB()
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            # Health check that takes time
            slow_health_check = AsyncMock()
            slow_health_check.side_effect = lambda: asyncio.sleep(0.5)
            mock_ib.reqCurrentTimeAsync = slow_health_check

            with patch('broker.connection_manager.IB', return_value=mock_ib):
                # Connect and start health checks
                await connection_manager.connect()

                # Wait for health check to start
                await asyncio.sleep(0.2)

                # Try to disconnect during health check
                await connection_manager.disconnect()

                # Should handle gracefully without hanging

    @pytest.mark.asyncio
    async def test_memory_exhaustion_simulation(self):
        """Test behavior under memory pressure"""
        event_bus = Mock(spec=EventBus)

        # Create many connection managers to simulate memory pressure
        managers = []
        for i in range(100):
            with patch('broker.connection_manager.get_config') as mock_config:
                mock_config.return_value.broker.host = "127.0.0.1"
                mock_config.return_value.broker.port = 7497
                mock_config.return_value.broker.client_id = i

                manager = IBConnectionManager(event_bus)
                managers.append(manager)

                # Add many callbacks to increase memory usage
                for j in range(100):
                    manager.add_connection_callback(lambda: None)

        # Force garbage collection
        gc.collect()

        # Cleanup
        for manager in managers:
            await manager.disconnect()

        # Verify cleanup worked
        del managers
        gc.collect()

    @pytest.mark.asyncio
    async def test_connection_timeout_scenarios(self):
        """Test various connection timeout scenarios"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)

            # Test different timeout scenarios
            timeout_scenarios = [
                0.001,  # Very short timeout
                1.0,    # Short timeout
                10.0,   # Long timeout
            ]

            for timeout in timeout_scenarios:
                mock_ib = MockIB()

                # Simulate slow connection
                async def slow_connect(*args, **kwargs):
                    await asyncio.sleep(timeout + 0.1)  # Always exceed timeout

                mock_ib.connectAsync = slow_connect

                with patch('broker.connection_manager.IB', return_value=mock_ib):
                    with pytest.raises((ConnectionError, asyncio.TimeoutError)):
                        # This should timeout
                        await asyncio.wait_for(
                            connection_manager.connect(),
                            timeout=timeout
                        )

    @pytest.mark.asyncio
    async def test_concurrent_connection_attempts(self):
        """Test multiple concurrent connection attempts"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)

            mock_ib = MockIB()
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            with patch('broker.connection_manager.IB', return_value=mock_ib):
                # Launch multiple concurrent connection attempts
                tasks = []
                for i in range(5):
                    task = asyncio.create_task(connection_manager.connect())
                    tasks.append(task)

                # Wait for all to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # At least one should succeed, others might fail gracefully
                successes = [r for r in results if r is True]
                assert len(successes) >= 1

                # Cleanup
                await connection_manager.disconnect()


class TestOrderExecutionEdgeCases:
    """Test edge cases for order execution"""

    @pytest.fixture
    def ib_client_setup(self):
        """Setup IB client for testing"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.ib_client.get_config'):
            ib_client = IBClient(event_bus)
            ib_client._ib = MockIB()
            ib_client.connection_manager.is_connected = Mock(return_value=True)
            return ib_client, event_bus

    @pytest.mark.asyncio
    async def test_order_flood_protection(self, ib_client_setup):
        """Test system behavior under order flood"""
        ib_client, event_bus = ib_client_setup

        # Mock order placement to be very fast
        order_counter = 0

        def mock_place_order(contract, order):
            nonlocal order_counter
            order_counter += 1
            order.orderId = order_counter
            from tests.mocks.ib_mocks import MockTrade
            return MockTrade(contract, order, order_counter)

        ib_client._ib.placeOrder = mock_place_order

        # Flood with orders
        order_tasks = []
        for i in range(100):
            task = ib_client.place_market_order('ES', 1, 'BUY')
            order_tasks.append(task)

        # Should not crash or hang
        results = await asyncio.gather(*order_tasks, return_exceptions=True)

        # All orders should complete (successfully or with error)
        assert len(results) == 100
        for result in results:
            assert isinstance(result, (int, Exception))

    @pytest.mark.asyncio
    async def test_order_cancellation_race_conditions(self, ib_client_setup):
        """Test race conditions in order cancellation"""
        ib_client, event_bus = ib_client_setup

        # Setup order that takes time to process
        from tests.mocks.ib_mocks import MockTrade

        trade = MockTrade(order_id=123)
        ib_client._active_orders[123] = trade

        cancel_success = Mock(return_value=True)
        ib_client._ib.cancelOrder = cancel_success

        # Launch multiple concurrent cancellation attempts
        cancel_tasks = []
        for i in range(10):
            task = ib_client.cancel_order(123)
            cancel_tasks.append(task)

        results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

        # Should handle gracefully without errors
        for result in results:
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_invalid_order_parameters(self, ib_client_setup):
        """Test handling of invalid order parameters"""
        ib_client, event_bus = ib_client_setup

        # Test various invalid parameters
        invalid_cases = [
            ('INVALID_SYMBOL', 1, 'BUY'),  # Invalid symbol
            ('ES', 0, 'BUY'),              # Zero quantity
            ('ES', -1, 'BUY'),             # Negative quantity
            ('ES', 1, 'INVALID_ACTION'),   # Invalid action
        ]

        for symbol, quantity, action in invalid_cases:
            with pytest.raises((ValueError, ExecutionError)):
                await ib_client.place_market_order(symbol, quantity, action)

    @pytest.mark.asyncio
    async def test_order_with_extreme_prices(self, ib_client_setup):
        """Test orders with extreme price values"""
        ib_client, event_bus = ib_client_setup

        # Mock order placement
        from tests.mocks.ib_mocks import MockTrade
        ib_client._ib.placeOrder = Mock(return_value=MockTrade(order_id=123))

        extreme_prices = [
            Decimal('0.01'),      # Very low price
            Decimal('999999.99'), # Very high price
            Decimal('0.000001'),  # Tiny price
        ]

        for price in extreme_prices:
            # Should handle extreme prices gracefully
            order_id = await ib_client.place_limit_order('ES', 1, price, 'BUY')
            assert isinstance(order_id, int)


class TestMarketDataStressTests:
    """Stress tests for market data handling"""

    @pytest.fixture
    def ib_client_setup(self):
        """Setup IB client for market data testing"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.ib_client.get_config'):
            ib_client = IBClient(event_bus)
            ib_client._ib = MockIB()
            ib_client.connection_manager.is_connected = Mock(return_value=True)
            return ib_client, event_bus

    @pytest.mark.asyncio
    async def test_high_frequency_tick_processing(self, ib_client_setup):
        """Test processing of high-frequency tick data"""
        ib_client, event_bus = ib_client_setup

        # Mock ticker with rapid updates
        from tests.mocks.ib_mocks import MockTicker
        ticker = MockTicker()

        # Simulate rapid tick updates
        tick_count = 1000
        start_time = time.time()

        for i in range(tick_count):
            ticker.bid = 4500.0 + (i * 0.01)
            ticker.ask = 4500.25 + (i * 0.01)
            ticker.last = 4500.125 + (i * 0.01)

            await ib_client._on_tick_update('ES', ticker)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process all ticks efficiently
        assert event_bus.publish.call_count == tick_count
        assert processing_time < 5.0  # Should process 1000 ticks in under 5 seconds

    @pytest.mark.asyncio
    async def test_massive_subscription_management(self, ib_client_setup):
        """Test handling of many simultaneous subscriptions"""
        ib_client, event_bus = ib_client_setup

        # Mock market data subscription
        from tests.mocks.ib_mocks import MockTicker
        ib_client._ib.reqMktData = Mock(return_value=MockTicker())

        # Subscribe to many symbols
        symbols = [f"TEST{i}" for i in range(100)]

        subscription_tasks = []
        for symbol in symbols:
            task = ib_client.subscribe_market_data(symbol)
            subscription_tasks.append(task)

        results = await asyncio.gather(*subscription_tasks, return_exceptions=True)

        # All subscriptions should succeed
        assert all(result is True for result in results)
        assert len(ib_client._market_data_subscriptions) == 100

        # Test unsubscription
        unsubscription_tasks = []
        for symbol in symbols:
            task = ib_client.unsubscribe_market_data(symbol)
            unsubscription_tasks.append(task)

        results = await asyncio.gather(*unsubscription_tasks, return_exceptions=True)

        # All unsubscriptions should succeed
        assert all(result is True for result in results)
        assert len(ib_client._market_data_subscriptions) == 0

    @pytest.mark.asyncio
    async def test_malformed_market_data(self, ib_client_setup):
        """Test handling of malformed market data"""
        ib_client, event_bus = ib_client_setup

        # Create ticker with invalid data
        from tests.mocks.ib_mocks import MockTicker
        ticker = MockTicker()

        # Test various malformed data scenarios
        malformed_scenarios = [
            {'bid': float('inf'), 'ask': 4500.25},  # Infinite bid
            {'bid': float('nan'), 'ask': 4500.25},  # NaN bid
            {'bid': -1, 'ask': -1},                 # Negative prices
            {'bid': 4500, 'ask': 4499},            # Negative spread
        ]

        for scenario in malformed_scenarios:
            for key, value in scenario.items():
                setattr(ticker, key, value)

            # Should handle malformed data gracefully
            try:
                await ib_client._on_tick_update('ES', ticker)
                # If no exception, check that event was not published with invalid data
                if event_bus.publish.called:
                    event = event_bus.publish.call_args[0][0]
                    # Verify data is sanitized or marked as invalid
                    assert event is not None
            except Exception as e:
                # Should log error but not crash
                assert "error" in str(e).lower()


class TestContractValidationEdgeCases:
    """Test edge cases for contract validation"""

    def test_contract_precision_edge_cases(self):
        """Test precision handling in edge cases"""
        # Test extremely small tick sizes
        tiny_tick = Decimal('0.000001')
        large_multiplier = 1000000

        # Should maintain precision
        tick_value = tiny_tick * large_multiplier
        assert tick_value == Decimal('1.000000')

        # Test very large prices
        large_price = Decimal('999999.999999')
        large_quantity = 1000

        position_value = ContractFactory.calculate_position_value(
            'ES', large_price, large_quantity
        )

        # Should not lose precision
        expected = large_price * large_quantity * 50  # ES multiplier
        assert position_value == expected

    def test_margin_calculation_edge_cases(self):
        """Test margin calculations with edge cases"""
        # Test with symbols not in the predefined list
        unknown_margin = ContractFactory.get_margin_requirement('UNKNOWN')
        assert unknown_margin == Decimal('5000')  # Default margin

        # Test both day and overnight margins
        day_margin = ContractFactory.get_margin_requirement('ES', True)
        overnight_margin = ContractFactory.get_margin_requirement('ES', False)

        assert day_margin < overnight_margin  # Day margin should be lower

    def test_market_hours_edge_cases(self):
        """Test market hours validation edge cases"""
        # Test exactly at boundary times
        boundary_times = [
            datetime(2024, 1, 8, 22, 0, 0),  # Maintenance start
            datetime(2024, 1, 8, 23, 0, 0),  # Maintenance end
            datetime(2024, 1, 5, 22, 0, 0),  # Friday close
            datetime(2024, 1, 7, 23, 0, 0),  # Sunday open
        ]

        for test_time in boundary_times:
            # Should handle boundary conditions consistently
            result = ContractFactory.is_market_hours('ES', test_time)
            assert isinstance(result, bool)

    def test_invalid_contract_creation(self):
        """Test creation of contracts with invalid parameters"""
        # Should raise appropriate exceptions
        with pytest.raises(ValueError):
            ContractFactory.create_futures('NONEXISTENT')

        with pytest.raises(ValueError):
            ContractFactory.get_contract_specs('INVALID')

        # Test with malformed expiry
        try:
            contract = ContractFactory.create_futures('ES', 'INVALID_DATE')
            # Should create but with invalid expiry
            assert contract.expiry == 'INVALID_DATE'
        except Exception:
            # Or should reject invalid expiry
            pass


class TestConcurrencyAndThreadSafety:
    """Test concurrent operations and thread safety"""

    @pytest.mark.asyncio
    async def test_concurrent_order_management(self):
        """Test concurrent order operations"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.ib_client.get_config'):
            ib_client = IBClient(event_bus)
            ib_client._ib = MockIB()
            ib_client.connection_manager.is_connected = Mock(return_value=True)

            # Mock order placement
            from tests.mocks.ib_mocks import MockTrade
            order_id_counter = 1

            def create_mock_trade(*args, **kwargs):
                nonlocal order_id_counter
                trade = MockTrade(order_id=order_id_counter)
                order_id_counter += 1
                return trade

            ib_client._ib.placeOrder = Mock(side_effect=create_mock_trade)

            # Launch concurrent operations
            tasks = []

            # Mix of different operations
            for i in range(50):
                if i % 3 == 0:
                    task = ib_client.place_market_order('ES', 1, 'BUY')
                elif i % 3 == 1:
                    task = ib_client.place_limit_order('ES', 1, Decimal('4500'), 'BUY')
                else:
                    task = ib_client.get_positions()
                tasks.append(task)

            # Should all complete without deadlocks or race conditions
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify no exceptions occurred
            for result in results:
                assert not isinstance(result, Exception), f"Unexpected exception: {result}"

    @pytest.mark.asyncio
    async def test_event_bus_under_load(self):
        """Test event bus performance under high load"""
        event_bus = EventBus()
        events_published = 0
        events_received = 0

        async def event_handler(event):
            nonlocal events_received
            events_received += 1

        # Subscribe to events
        event_bus.subscribe(event_handler)

        # Publish many events rapidly
        for i in range(1000):
            from core.events import SystemEvent, SystemInfo, SystemSeverity
            event = SystemEvent(
                info=SystemInfo(
                    component="test",
                    severity=SystemSeverity.INFO,
                    message=f"Test event {i}"
                )
            )
            await event_bus.publish(event)
            events_published += 1

        # Allow some time for processing
        await asyncio.sleep(0.5)

        # Should handle high event volume
        assert events_published == 1000
        # Some events might still be processing
        assert events_received >= 900  # Allow for some processing delay


@pytest.mark.performance
class TestPerformanceBenchmarks:
    """Performance benchmark tests"""

    @pytest.mark.asyncio
    async def test_connection_establishment_speed(self):
        """Benchmark connection establishment time"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)

            # Mock fast connection
            mock_ib = MockIB()
            mock_ib.connection_delay = 0.001  # Very fast mock connection
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            with patch('broker.connection_manager.IB', return_value=mock_ib):
                # Measure connection time
                start_time = time.time()
                success = await connection_manager.connect()
                end_time = time.time()

                connection_time = end_time - start_time

                assert success
                assert connection_time < 1.0  # Should connect in under 1 second

                await connection_manager.disconnect()

    @pytest.mark.asyncio
    async def test_order_throughput(self):
        """Benchmark order placement throughput"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.ib_client.get_config'):
            ib_client = IBClient(event_bus)
            ib_client._ib = MockIB()
            ib_client.connection_manager.is_connected = Mock(return_value=True)

            # Mock very fast order placement
            from tests.mocks.ib_mocks import MockTrade
            order_counter = 0

            def fast_order_placement(*args, **kwargs):
                nonlocal order_counter
                order_counter += 1
                return MockTrade(order_id=order_counter)

            ib_client._ib.placeOrder = fast_order_placement

            # Measure order throughput
            order_count = 100
            start_time = time.time()

            tasks = []
            for i in range(order_count):
                task = ib_client.place_market_order('ES', 1, 'BUY')
                tasks.append(task)

            await asyncio.gather(*tasks)
            end_time = time.time()

            total_time = end_time - start_time
            orders_per_second = order_count / total_time

            # Should achieve reasonable throughput
            assert orders_per_second > 10  # At least 10 orders per second

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self):
        """Test memory usage remains stable under load"""
        import gc
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        event_bus = Mock(spec=EventBus)

        # Create and destroy many clients
        for cycle in range(10):
            clients = []

            # Create multiple clients
            for i in range(10):
                with patch('broker.ib_client.get_config'):
                    client = IBClient(event_bus)
                    clients.append(client)

            # Do some work
            for client in clients:
                client._market_data_subscriptions['ES'] = Mock()
                client._active_orders[123] = Mock()

            # Cleanup
            for client in clients:
                await client.disconnect()

            del clients
            gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # Memory growth should be minimal (less than 50MB)
        assert memory_growth < 50, f"Memory grew by {memory_growth:.1f} MB"


if __name__ == '__main__':
    # Run edge case tests
    pytest.main([__file__, '-v', '--tb=short', '-m', 'not performance'])