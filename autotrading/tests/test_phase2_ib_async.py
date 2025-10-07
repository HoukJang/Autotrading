#!/usr/bin/env python3
"""
Phase 2 IB API Integration Tests - Async Version
Comprehensive testing for IB connection, contracts, and client
"""

import asyncio
import sys
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker.connection_manager import IBConnectionManager, ConnectionState, ConnectionEvent
from broker.contracts import ContractFactory, FuturesContract
from broker.ib_client import IBClient, TickEvent
from core.event_bus import EventBus
from core.events import EventType
from core.exceptions import ConnectionError, ExecutionError


class MockIB:
    """Mock IB API for testing"""

    def __init__(self):
        self.connected = False
        self.disconnectedEvent = AsyncMock()
        self.errorEvent = AsyncMock()

    def isConnected(self):
        return self.connected

    async def connectAsync(self, host, port, clientId):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    async def reqCurrentTimeAsync(self):
        return datetime.now()

    def reqMktData(self, contract, **kwargs):
        ticker = Mock()
        ticker.contract = contract
        ticker.bid = 4500.25
        ticker.ask = 4500.50
        ticker.last = 4500.25
        ticker.volume = 12345
        ticker.bidSize = 10
        ticker.askSize = 12
        ticker.lastSize = 5
        ticker.updateEvent = AsyncMock()
        return ticker

    def cancelMktData(self, contract):
        pass

    async def reqHistoricalDataAsync(self, contract, **kwargs):
        # Return mock historical bars
        bars = []
        for i in range(10):
            bar = Mock()
            bar.date = datetime.now()
            bar.open = 4500.0 + i
            bar.high = 4502.0 + i
            bar.low = 4499.0 + i
            bar.close = 4501.0 + i
            bar.volume = 1000 + i * 100
            bars.append(bar)
        return bars

    def placeOrder(self, contract, order):
        trade = Mock()
        trade.order = Mock()
        trade.order.orderId = 123
        trade.orderStatus = Mock()
        trade.orderStatus.status = "Submitted"
        trade.statusEvent = AsyncMock()
        trade.fillEvent = AsyncMock()
        return trade

    def cancelOrder(self, order):
        pass

    def positions(self):
        position = Mock()
        position.contract = Mock()
        position.contract.symbol = "ES"
        position.position = 2
        position.avgCost = 4500.0
        position.marketValue = 9010.0
        position.unrealizedPNL = 10.0
        position.realizedPNL = 50.0
        return [position]

    def accountSummary(self):
        summary = []
        tags = {
            'NetLiquidation': '100000',
            'BuyingPower': '50000',
            'TotalCashValue': '20000',
            'RealizedPnL': '500',
            'UnrealizedPnL': '100',
            'InitMarginReq': '10000'
        }
        for tag, value in tags.items():
            item = Mock()
            item.tag = tag
            item.value = value
            item.currency = 'USD'
            summary.append(item)
        return summary

    async def reqAllOrdersAsync(self):
        return 1


class AsyncTestCase(unittest.TestCase):
    """Base class for async tests with proper event loop management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = None

    def setUp(self):
        """Set up event loop for async tests"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

    def tearDown(self):
        """Clean up event loop"""
        # Cancel all tasks
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()

        # Run until all tasks are cancelled
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        # Close the loop
        self._loop.close()
        self._loop = None
        asyncio.set_event_loop(None)

    def run_async(self, coro):
        """Helper to run async coroutine"""
        return self._loop.run_until_complete(coro)


class TestIBConnectionManager(AsyncTestCase):
    """Test IB Connection Manager"""

    def setUp(self):
        super().setUp()
        self.event_bus = EventBus()
        self.run_async(self.event_bus.start())
        self.manager = IBConnectionManager(self.event_bus)

    def tearDown(self):
        if self.manager.is_connected():
            self.run_async(self.manager.disconnect())
        self.run_async(self.event_bus.stop())
        super().tearDown()

    @patch('broker.connection_manager.IB', MockIB)
    def test_connect_success(self):
        """Test successful connection"""
        # Connect
        result = self.run_async(self.manager.connect())
        self.assertTrue(result)
        self.assertEqual(self.manager.state, ConnectionState.CONNECTED)
        self.assertTrue(self.manager.is_connected())

        # Disconnect
        self.run_async(self.manager.disconnect())
        self.assertEqual(self.manager.state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.manager.is_connected())

    @patch('broker.connection_manager.IB')
    def test_connect_failure(self, mock_ib_class):
        """Test connection failure and retry"""
        mock_ib = Mock()
        mock_ib.isConnected.return_value = False
        mock_ib.connectAsync = AsyncMock(side_effect=Exception("Connection failed"))
        mock_ib_class.return_value = mock_ib

        with self.assertRaises(ConnectionError):
            self.run_async(self.manager.connect())

        self.assertEqual(self.manager.state, ConnectionState.ERROR)
        self.assertFalse(self.manager.is_connected())

    @patch('broker.connection_manager.IB', MockIB)
    def test_health_check(self):
        """Test health check mechanism"""
        # Connect first
        self.run_async(self.manager.connect())

        # Health check should pass
        is_healthy = self.run_async(self.manager.health_check())
        self.assertTrue(is_healthy)

        # Simulate disconnection
        self.manager.ib.connected = False
        is_healthy = self.run_async(self.manager.health_check())
        self.assertFalse(is_healthy)

    @patch('broker.connection_manager.IB', MockIB)
    def test_reconnection(self):
        """Test automatic reconnection"""
        # Connect
        self.run_async(self.manager.connect())

        # Simulate disconnection
        self.manager.ib.connected = False
        self.manager.state = ConnectionState.DISCONNECTED

        # Try reconnection
        result = self.run_async(self.manager.reconnect())
        self.assertTrue(result)
        self.assertEqual(self.manager.state, ConnectionState.CONNECTED)

    def test_connection_callbacks(self):
        """Test connection/disconnection callbacks"""
        connection_called = False
        disconnection_called = False

        def on_connect():
            nonlocal connection_called
            connection_called = True

        def on_disconnect():
            nonlocal disconnection_called
            disconnection_called = True

        self.manager.add_connection_callback(on_connect)
        self.manager.add_disconnection_callback(on_disconnect)

        with patch('broker.connection_manager.IB', MockIB):
            # Connect should trigger callback
            self.run_async(self.manager.connect())
            self.assertTrue(connection_called)

            # Disconnect should trigger callback
            self.run_async(self.manager.disconnect())
            self.assertTrue(disconnection_called)


class TestContractFactory(unittest.TestCase):
    """Test Contract Factory and Definitions"""

    def test_create_es_futures(self):
        """Test ES futures creation"""
        contract = ContractFactory.create_es_futures()
        self.assertEqual(contract.symbol, 'ES')
        self.assertEqual(contract.exchange, 'CME')
        self.assertEqual(contract.currency, 'USD')
        self.assertEqual(contract.multiplier, 50)
        self.assertEqual(contract.tick_size, Decimal('0.25'))

    def test_create_futures_with_expiry(self):
        """Test futures creation with expiry"""
        contract = ContractFactory.create_futures('NQ', '202312')
        self.assertEqual(contract.symbol, 'NQ')
        self.assertEqual(contract.expiry, '202312')
        self.assertEqual(contract.multiplier, 20)

    def test_unknown_symbol(self):
        """Test unknown symbol handling"""
        with self.assertRaises(ValueError):
            ContractFactory.create_futures('UNKNOWN')

    def test_continuous_futures(self):
        """Test continuous futures contract"""
        contract = ContractFactory.create_continuous_futures('ES')
        self.assertEqual(contract.symbol, 'ES')
        self.assertEqual(contract.exchange, 'CME')
        self.assertFalse(contract.includeExpired)

    def test_tick_value_calculation(self):
        """Test tick value calculations"""
        # ES: $12.50 per tick
        value = ContractFactory.calculate_tick_value('ES', Decimal('4500'), 2)
        self.assertEqual(value, Decimal('25.00'))

        # MES: $1.25 per tick
        value = ContractFactory.calculate_tick_value('MES', Decimal('4500'), 4)
        self.assertEqual(value, Decimal('5.00'))

    def test_position_value_calculation(self):
        """Test position value calculation"""
        # ES: 2 contracts at 4500 = 4500 * 2 * 50 = $450,000
        value = ContractFactory.calculate_position_value('ES', Decimal('4500'), 2)
        self.assertEqual(value, Decimal('450000'))

    def test_margin_requirements(self):
        """Test margin requirement calculations"""
        # Day trading margin
        day_margin = ContractFactory.get_margin_requirement('ES', is_day_trading=True)
        self.assertEqual(day_margin, Decimal('500'))

        # Overnight margin
        overnight_margin = ContractFactory.get_margin_requirement('ES', is_day_trading=False)
        self.assertEqual(overnight_margin, Decimal('13200'))


class TestIBClient(AsyncTestCase):
    """Test IB Client wrapper"""

    def setUp(self):
        super().setUp()
        self.event_bus = EventBus()
        self.run_async(self.event_bus.start())
        self.client = IBClient(self.event_bus)

    def tearDown(self):
        self.run_async(self.client.disconnect())
        self.run_async(self.event_bus.stop())
        super().tearDown()

    @patch('broker.connection_manager.IB', MockIB)
    def test_connect_disconnect(self):
        """Test client connection and disconnection"""
        # Connect
        result = self.run_async(self.client.connect())
        self.assertTrue(result)
        self.assertTrue(self.client.connection_manager.is_connected())

        # Disconnect
        self.run_async(self.client.disconnect())
        self.assertFalse(self.client.connection_manager.is_connected())

    @patch('broker.connection_manager.IB', MockIB)
    def test_market_data_subscription(self):
        """Test market data subscription"""
        # Connect first
        self.run_async(self.client.connect())

        # Subscribe to ES
        result = self.run_async(self.client.subscribe_market_data('ES'))
        self.assertTrue(result)
        self.assertIn('ES', self.client._market_data_subscriptions)

        # Unsubscribe
        result = self.run_async(self.client.unsubscribe_market_data('ES'))
        self.assertTrue(result)
        self.assertNotIn('ES', self.client._market_data_subscriptions)

    @patch('broker.connection_manager.IB', MockIB)
    def test_historical_data_request(self):
        """Test historical data request"""
        # Connect first
        self.run_async(self.client.connect())

        # Request historical data
        bars = self.run_async(self.client.request_historical_bars('ES', '1 D', '1 min'))
        self.assertIsNotNone(bars)
        self.assertEqual(len(bars), 10)  # Mock returns 10 bars

    @patch('broker.connection_manager.IB', MockIB)
    def test_place_market_order(self):
        """Test placing market order"""
        # Connect first
        self.run_async(self.client.connect())

        # Place market order
        order_id = self.run_async(self.client.place_market_order('ES', 2, 'BUY'))
        self.assertEqual(order_id, 123)  # Mock returns 123
        self.assertIn(order_id, self.client._active_orders)

    @patch('broker.connection_manager.IB', MockIB)
    def test_place_limit_order(self):
        """Test placing limit order"""
        # Connect first
        self.run_async(self.client.connect())

        # Place limit order
        order_id = self.run_async(self.client.place_limit_order('ES', 1, Decimal('4500.00'), 'SELL'))
        self.assertEqual(order_id, 123)
        self.assertIn(order_id, self.client._active_orders)

    @patch('broker.connection_manager.IB', MockIB)
    def test_cancel_order(self):
        """Test order cancellation"""
        # Connect first
        self.run_async(self.client.connect())

        # Place order first
        order_id = self.run_async(self.client.place_market_order('ES', 1, 'BUY'))

        # Cancel order
        result = self.run_async(self.client.cancel_order(order_id))
        self.assertTrue(result)

    @patch('broker.connection_manager.IB', MockIB)
    def test_get_positions(self):
        """Test getting positions"""
        # Connect first
        self.run_async(self.client.connect())

        # Get positions
        positions = self.run_async(self.client.get_positions())
        self.assertIsNotNone(positions)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]['symbol'], 'ES')
        self.assertEqual(positions[0]['quantity'], 2)

    @patch('broker.connection_manager.IB', MockIB)
    def test_get_account_summary(self):
        """Test getting account summary"""
        # Connect first
        self.run_async(self.client.connect())

        # Get account summary
        summary = self.run_async(self.client.get_account_summary())
        self.assertIsNotNone(summary)
        self.assertEqual(summary['net_liquidation'], 100000)
        self.assertEqual(summary['buying_power'], 50000)
        self.assertEqual(summary['realized_pnl'], 500)


class TestEdgeCases(AsyncTestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        super().setUp()
        self.event_bus = EventBus()
        self.run_async(self.event_bus.start())

    def tearDown(self):
        self.run_async(self.event_bus.stop())
        super().tearDown()

    @patch('broker.connection_manager.IB')
    def test_connection_timeout(self, mock_ib_class):
        """Test connection timeout handling"""
        mock_ib = Mock()
        mock_ib.connectAsync = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_ib_class.return_value = mock_ib

        manager = IBConnectionManager(self.event_bus)
        with self.assertRaises(ConnectionError):
            self.run_async(manager.connect())

    def test_invalid_contract_specs(self):
        """Test invalid contract specifications"""
        # Invalid tick calculation
        with self.assertRaises(ValueError):
            ContractFactory.calculate_tick_value('INVALID', Decimal('100'), 1)

        # Invalid position calculation
        with self.assertRaises(ValueError):
            ContractFactory.calculate_position_value('INVALID', Decimal('100'), 1)

    @patch('broker.connection_manager.IB', MockIB)
    def test_order_without_connection(self):
        """Test placing order without connection"""
        client = IBClient(self.event_bus)
        # Don't connect

        with self.assertRaises(ExecutionError):
            self.run_async(client.place_market_order('ES', 1, 'BUY'))


def run_all_tests():
    """Run all test suites"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestIBConnectionManager))
    suite.addTests(loader.loadTestsFromTestCase(TestContractFactory))
    suite.addTests(loader.loadTestsFromTestCase(TestIBClient))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED!")
        print("Phase 2 IB API components are working correctly.")
    else:
        print("\n❌ SOME TESTS FAILED")
        if result.failures:
            print("\nFAILURES:")
            for test, trace in result.failures:
                print(f"- {test}: {trace[:200]}...")
        if result.errors:
            print("\nERRORS:")
            for test, trace in result.errors:
                print(f"- {test}: {trace[:200]}...")

    return result.wasSuccessful()


if __name__ == "__main__":
    print("="*60)
    print("Phase 2 IB API Integration Tests")
    print("="*60)
    print("Testing IB Connection Manager, Contracts, and Client...")
    print()

    success = run_all_tests()
    sys.exit(0 if success else 1)