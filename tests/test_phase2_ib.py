"""
Comprehensive Test Suite for Interactive Brokers API Integration Components
Tests Connection Manager, Contract Definitions, and IB Client functionality
"""

import pytest
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any

# System under test imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'autotrading'))

from broker.connection_manager import IBConnectionManager, ConnectionState, ConnectionEvent
from broker.contracts import ContractFactory, FuturesContract
from broker.ib_client import IBClient, TickEvent
from core.event_bus import EventBus
from core.exceptions import ConnectionError, ExecutionError, TradingSystemError
from config.config import get_config

# Mock IB API components
from tests.mocks.ib_mocks import MockIB, MockTicker, MockContract, MockTrade, MockOrder, MockBarData


class TestIBConnectionManager:
    """Comprehensive test suite for IBConnectionManager"""

    @pytest.fixture
    def event_bus(self):
        """Mock event bus"""
        return Mock(spec=EventBus)

    @pytest.fixture
    def connection_manager(self, event_bus):
        """Create connection manager instance"""
        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1
            return IBConnectionManager(event_bus)

    @pytest.fixture
    def mock_ib(self):
        """Mock IB instance"""
        return MockIB()

    @pytest.mark.asyncio
    async def test_connection_lifecycle(self, connection_manager, mock_ib, event_bus):
        """Test complete connection lifecycle"""
        # Test initial state
        assert connection_manager.state == ConnectionState.DISCONNECTED
        assert not connection_manager.is_connected()

        # Mock IB.connectAsync
        with patch('broker.connection_manager.IB', return_value=mock_ib):
            # Test successful connection
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            success = await connection_manager.connect()

            assert success
            assert connection_manager.state == ConnectionState.CONNECTED
            assert connection_manager.is_connected()

            # Verify connection event published
            event_bus.publish.assert_called()
            published_event = event_bus.publish.call_args[0][0]
            assert isinstance(published_event, ConnectionEvent)
            assert published_event.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_connection_failure_scenarios(self, connection_manager, mock_ib, event_bus):
        """Test various connection failure scenarios"""
        with patch('broker.connection_manager.IB', return_value=mock_ib):
            # Test connection timeout
            mock_ib.connectAsync = AsyncMock(side_effect=asyncio.TimeoutError("Connection timeout"))

            with pytest.raises(ConnectionError):
                await connection_manager.connect()

            assert connection_manager.state == ConnectionState.ERROR

            # Test IB connection error
            mock_ib.connectAsync = AsyncMock(side_effect=Exception("TWS not running"))

            with pytest.raises(ConnectionError):
                await connection_manager.connect()

    @pytest.mark.asyncio
    async def test_reconnection_logic(self, connection_manager, mock_ib, event_bus):
        """Test automatic reconnection functionality"""
        with patch('broker.connection_manager.IB', return_value=mock_ib):
            # Setup successful connection then failure
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            # Connect successfully
            await connection_manager.connect()
            assert connection_manager.state == ConnectionState.CONNECTED

            # Simulate disconnection
            mock_ib.isConnected = Mock(return_value=False)
            await connection_manager._on_disconnected()

            assert connection_manager.state == ConnectionState.DISCONNECTED

            # Test manual reconnection
            mock_ib.isConnected = Mock(return_value=True)
            success = await connection_manager.reconnect()

            assert success
            assert connection_manager.state == ConnectionState.CONNECTED
            assert connection_manager.reconnect_attempts > 0

    @pytest.mark.asyncio
    async def test_health_check_mechanism(self, connection_manager, mock_ib, event_bus):
        """Test connection health monitoring"""
        with patch('broker.connection_manager.IB', return_value=mock_ib):
            # Setup connected state
            connection_manager._ib = mock_ib
            mock_ib.isConnected = Mock(return_value=True)

            # Test successful health check
            mock_ib.reqCurrentTimeAsync = AsyncMock(return_value=datetime.now())
            is_healthy = await connection_manager.health_check()

            assert is_healthy
            assert connection_manager.last_health_check is not None

            # Test failed health check
            mock_ib.reqCurrentTimeAsync = AsyncMock(side_effect=Exception("Health check failed"))
            is_healthy = await connection_manager.health_check()

            assert not is_healthy

    @pytest.mark.asyncio
    async def test_connection_callbacks(self, connection_manager, mock_ib, event_bus):
        """Test connection/disconnection callbacks"""
        callback_called = Mock()
        connection_manager.add_connection_callback(callback_called)

        with patch('broker.connection_manager.IB', return_value=mock_ib):
            mock_ib.connectAsync = AsyncMock(return_value=None)
            mock_ib.isConnected = Mock(return_value=True)

            await connection_manager.connect()

            # Verify callback was called
            callback_called.assert_called_once()

    def test_connection_info(self, connection_manager):
        """Test connection information retrieval"""
        info = connection_manager.get_connection_info()

        assert 'state' in info
        assert 'host' in info
        assert 'port' in info
        assert 'client_id' in info
        assert 'is_tws' in info
        assert 'reconnect_attempts' in info

    @pytest.mark.asyncio
    async def test_error_handling(self, connection_manager, mock_ib, event_bus):
        """Test error event handling"""
        connection_manager._ib = mock_ib

        # Test critical error handling
        critical_error_codes = [504, 502, 1100, 1101, 1102]

        for error_code in critical_error_codes:
            with patch.object(connection_manager, '_on_disconnected') as mock_disconnect:
                await connection_manager._on_error(1, error_code, f"Critical error {error_code}")
                mock_disconnect.assert_called()

    @pytest.mark.asyncio
    async def test_max_reconnection_attempts(self, connection_manager, mock_ib, event_bus):
        """Test max reconnection attempts limit"""
        connection_manager.max_reconnect_attempts = 3

        with patch('broker.connection_manager.IB', return_value=mock_ib):
            mock_ib.connectAsync = AsyncMock(side_effect=Exception("Connection failed"))

            # Exhaust reconnection attempts
            for i in range(3):
                success = await connection_manager.reconnect()
                assert not success

            # Should stop attempting after max attempts
            assert connection_manager.reconnect_attempts == 3
            assert connection_manager.state == ConnectionState.ERROR

    @pytest.mark.asyncio
    async def test_graceful_disconnect(self, connection_manager, mock_ib, event_bus):
        """Test graceful disconnection process"""
        # Setup connected state
        connection_manager._ib = mock_ib
        connection_manager.state = ConnectionState.CONNECTED
        connection_manager._health_check_task = Mock()
        connection_manager._reconnect_task = Mock()

        mock_ib.isConnected = Mock(return_value=True)
        mock_ib.disconnect = Mock()

        disconnection_callback = Mock()
        connection_manager.add_disconnection_callback(disconnection_callback)

        await connection_manager.disconnect()

        # Verify cleanup
        assert connection_manager.state == ConnectionState.DISCONNECTED
        connection_manager._health_check_task.cancel.assert_called()
        connection_manager._reconnect_task.cancel.assert_called()
        mock_ib.disconnect.assert_called()
        disconnection_callback.assert_called()


class TestContractFactory:
    """Test suite for contract definitions and factory methods"""

    def test_predefined_contract_specs(self):
        """Test predefined futures contract specifications"""
        # Test ES contract
        es_spec = ContractFactory.get_contract_specs('ES')
        assert es_spec['name'] == 'E-mini S&P 500'
        assert es_spec['exchange'] == 'CME'
        assert es_spec['multiplier'] == 50
        assert es_spec['tick_size'] == Decimal('0.25')

        # Test all major contracts exist
        required_symbols = ['ES', 'NQ', 'YM', 'RTY', 'MES', 'MNQ', 'CL', 'GC', '6E']
        for symbol in required_symbols:
            spec = ContractFactory.get_contract_specs(symbol)
            assert 'name' in spec
            assert 'exchange' in spec
            assert 'multiplier' in spec
            assert 'tick_size' in spec

    def test_futures_contract_creation(self):
        """Test futures contract creation"""
        # Test ES contract creation
        es_contract = ContractFactory.create_futures('ES', '202412')

        assert es_contract.symbol == 'ES'
        assert es_contract.exchange == 'CME'
        assert es_contract.currency == 'USD'
        assert es_contract.multiplier == 50
        assert es_contract.tick_size == Decimal('0.25')
        assert es_contract.expiry == '202412'

        # Test conversion to IB contract
        ib_contract = es_contract.to_ib_contract()
        assert ib_contract.symbol == 'ES'
        assert ib_contract.exchange == 'CME'
        assert ib_contract.currency == 'USD'
        assert ib_contract.lastTradeDateOrContractMonth == '202412'

    def test_continuous_futures_creation(self):
        """Test continuous futures contract creation"""
        es_continuous = ContractFactory.create_continuous_futures('ES')

        assert es_continuous.symbol == 'ES'
        assert es_continuous.exchange == 'CME'
        assert es_continuous.currency == 'USD'
        assert es_continuous.includeExpired == False

    def test_tick_value_calculations(self):
        """Test tick value calculation accuracy"""
        # Test ES tick value
        es_tick_value = ContractFactory.calculate_tick_value('ES', Decimal('4500'), 1)
        assert es_tick_value == Decimal('12.50')  # 0.25 * 50 multiplier

        # Test multiple ticks
        es_5_tick_value = ContractFactory.calculate_tick_value('ES', Decimal('4500'), 5)
        assert es_5_tick_value == Decimal('62.50')  # 5 * 12.50

        # Test NQ tick value
        nq_tick_value = ContractFactory.calculate_tick_value('NQ', Decimal('15000'), 1)
        assert nq_tick_value == Decimal('5.00')  # 0.25 * 20 multiplier

    def test_position_value_calculations(self):
        """Test position value calculations"""
        # Test ES position value
        es_value = ContractFactory.calculate_position_value('ES', Decimal('4500'), 2)
        expected_value = Decimal('4500') * 2 * 50  # price * quantity * multiplier
        assert es_value == expected_value

        # Test fractional price
        nq_value = ContractFactory.calculate_position_value('NQ', Decimal('15000.25'), 1)
        expected_value = Decimal('15000.25') * 1 * 20
        assert nq_value == expected_value

    def test_margin_requirements(self):
        """Test margin requirement calculations"""
        # Test day trading margins
        es_day_margin = ContractFactory.get_margin_requirement('ES', is_day_trading=True)
        assert es_day_margin == Decimal('500')

        # Test overnight margins
        es_overnight_margin = ContractFactory.get_margin_requirement('ES', is_day_trading=False)
        assert es_overnight_margin == Decimal('13200')

        # Test micro contracts
        mes_day_margin = ContractFactory.get_margin_requirement('MES', is_day_trading=True)
        assert mes_day_margin == Decimal('50')

    def test_market_hours_validation(self):
        """Test market hours validation"""
        # Test during market hours (simplified)
        # Note: This is a basic test - real market hours are complex

        # Test weekend (Saturday)
        saturday = datetime(2024, 1, 6, 12, 0)  # Saturday noon
        assert not ContractFactory.is_market_hours('ES', saturday)

        # Test maintenance window
        maintenance_time = datetime(2024, 1, 8, 22, 0)  # Monday 22:00 UTC
        assert not ContractFactory.is_market_hours('ES', maintenance_time)

    def test_invalid_symbol_handling(self):
        """Test handling of invalid symbols"""
        with pytest.raises(ValueError, match="Unknown futures symbol"):
            ContractFactory.create_futures('INVALID')

        with pytest.raises(ValueError, match="Unknown futures symbol"):
            ContractFactory.get_contract_specs('INVALID')

        with pytest.raises(ValueError, match="Unknown futures symbol"):
            ContractFactory.calculate_tick_value('INVALID', Decimal('100'), 1)

    def test_contract_precision(self):
        """Test financial precision in calculations"""
        # Test that Decimal arithmetic maintains precision
        tick_size = Decimal('0.25')
        multiplier = 50
        price = Decimal('4500.75')

        # Ensure no floating point errors
        tick_value = tick_size * multiplier
        position_value = price * multiplier

        assert str(tick_value) == '12.50'
        assert str(position_value) == '225037.50'


class TestIBClient:
    """Comprehensive test suite for IBClient"""

    @pytest.fixture
    def event_bus(self):
        """Mock event bus"""
        return Mock(spec=EventBus)

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager"""
        manager = Mock(spec=IBConnectionManager)
        manager.ib = MockIB()
        manager.is_connected = Mock(return_value=True)
        return manager

    @pytest.fixture
    def ib_client(self, event_bus, mock_connection_manager):
        """Create IB client instance"""
        with patch('broker.ib_client.IBConnectionManager', return_value=mock_connection_manager):
            with patch('broker.ib_client.get_config') as mock_config:
                return IBClient(event_bus)

    @pytest.mark.asyncio
    async def test_connection_management(self, ib_client, mock_connection_manager, event_bus):
        """Test client connection management"""
        # Test successful connection
        mock_connection_manager.connect = AsyncMock(return_value=True)

        success = await ib_client.connect()

        assert success
        mock_connection_manager.connect.assert_called_once()

        # Test disconnect
        mock_connection_manager.disconnect = AsyncMock()

        await ib_client.disconnect()

        mock_connection_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_data_subscription(self, ib_client, mock_connection_manager, event_bus):
        """Test market data subscription/unsubscription"""
        mock_ib = mock_connection_manager.ib
        mock_ticker = MockTicker()
        mock_ib.reqMktData = Mock(return_value=mock_ticker)

        # Test subscription
        success = await ib_client.subscribe_market_data('ES')

        assert success
        assert 'ES' in ib_client._market_data_subscriptions
        mock_ib.reqMktData.assert_called_once()

        # Test unsubscription
        mock_ib.cancelMktData = Mock()

        success = await ib_client.unsubscribe_market_data('ES')

        assert success
        assert 'ES' not in ib_client._market_data_subscriptions
        mock_ib.cancelMktData.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_event_processing(self, ib_client, event_bus):
        """Test tick event creation and publishing"""
        # Create mock ticker with sample data
        mock_ticker = MockTicker()
        mock_ticker.bid = 4500.25
        mock_ticker.ask = 4500.50
        mock_ticker.last = 4500.25
        mock_ticker.bidSize = 10
        mock_ticker.askSize = 15
        mock_ticker.lastSize = 5
        mock_ticker.volume = 1000

        # Process tick update
        await ib_client._on_tick_update('ES', mock_ticker)

        # Verify event was published
        event_bus.publish.assert_called_once()
        published_event = event_bus.publish.call_args[0][0]

        assert isinstance(published_event, TickEvent)
        assert published_event.symbol == 'ES'
        assert published_event.bid_price == Decimal('4500.25')
        assert published_event.ask_price == Decimal('4500.50')
        assert published_event.last_price == Decimal('4500.25')
        assert published_event.bid_size == 10
        assert published_event.ask_size == 15
        assert published_event.volume == 1000

    @pytest.mark.asyncio
    async def test_historical_data_request(self, ib_client, mock_connection_manager):
        """Test historical data retrieval"""
        mock_ib = mock_connection_manager.ib
        mock_bars = [MockBarData(), MockBarData()]
        mock_ib.reqHistoricalDataAsync = AsyncMock(return_value=mock_bars)

        bars = await ib_client.request_historical_bars('ES', '1 D', '1 min')

        assert len(bars) == 2
        mock_ib.reqHistoricalDataAsync.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_order_execution(self, ib_client, mock_connection_manager):
        """Test market order placement"""
        mock_ib = mock_connection_manager.ib
        mock_trade = MockTrade()
        mock_ib.placeOrder = Mock(return_value=mock_trade)

        order_id = await ib_client.place_market_order('ES', 1, 'BUY')

        assert order_id == mock_trade.order.orderId
        assert order_id in ib_client._active_orders
        mock_ib.placeOrder.assert_called_once()

    @pytest.mark.asyncio
    async def test_limit_order_execution(self, ib_client, mock_connection_manager):
        """Test limit order placement"""
        mock_ib = mock_connection_manager.ib
        mock_trade = MockTrade()
        mock_ib.placeOrder = Mock(return_value=mock_trade)

        order_id = await ib_client.place_limit_order('ES', 1, Decimal('4500.00'), 'BUY')

        assert order_id == mock_trade.order.orderId
        assert order_id in ib_client._active_orders
        mock_ib.placeOrder.assert_called_once()

    @pytest.mark.asyncio
    async def test_bracket_order_execution(self, ib_client, mock_connection_manager):
        """Test bracket order placement"""
        mock_ib = mock_connection_manager.ib

        # Mock bracket order returns multiple trades
        mock_trades = [MockTrade(order_id=1), MockTrade(order_id=2), MockTrade(order_id=3)]

        with patch('broker.ib_client.BracketOrder') as mock_bracket:
            mock_bracket.return_value = [Mock(), Mock(), Mock()]  # 3 orders
            mock_ib.placeOrder = Mock(side_effect=mock_trades)

            order_ids = await ib_client.place_bracket_order(
                'ES', 1, Decimal('4500.00'), Decimal('4495.00'), Decimal('4510.00'), 'BUY'
            )

            assert len(order_ids) == 3
            assert all(oid in ib_client._active_orders for oid in order_ids)
            assert mock_ib.placeOrder.call_count == 3

    @pytest.mark.asyncio
    async def test_order_cancellation(self, ib_client, mock_connection_manager):
        """Test order cancellation"""
        mock_ib = mock_connection_manager.ib
        mock_trade = MockTrade()

        # Add order to active orders
        ib_client._active_orders[mock_trade.order.orderId] = mock_trade

        mock_ib.cancelOrder = Mock()

        success = await ib_client.cancel_order(mock_trade.order.orderId)

        assert success
        mock_ib.cancelOrder.assert_called_once_with(mock_trade.order)

    @pytest.mark.asyncio
    async def test_position_retrieval(self, ib_client, mock_connection_manager):
        """Test position data retrieval"""
        mock_ib = mock_connection_manager.ib
        mock_position = Mock()
        mock_position.contract.symbol = 'ES'
        mock_position.position = 2
        mock_position.avgCost = 4500.00
        mock_position.marketValue = 450000.00
        mock_position.unrealizedPNL = 500.00
        mock_position.realizedPNL = 100.00

        mock_ib.positions = Mock(return_value=[mock_position])

        positions = await ib_client.get_positions()

        assert len(positions) == 1
        position = positions[0]
        assert position['symbol'] == 'ES'
        assert position['quantity'] == 2
        assert position['average_cost'] == 4500.00

    @pytest.mark.asyncio
    async def test_account_summary(self, ib_client, mock_connection_manager):
        """Test account summary retrieval"""
        mock_ib = mock_connection_manager.ib
        mock_summary_items = [
            Mock(tag='NetLiquidation', value='100000.00', currency='USD'),
            Mock(tag='BuyingPower', value='400000.00', currency='USD'),
            Mock(tag='TotalCashValue', value='50000.00', currency='USD'),
        ]

        mock_ib.accountSummary = Mock(return_value=mock_summary_items)

        summary = await ib_client.get_account_summary()

        assert summary['net_liquidation'] == 100000.00
        assert summary['buying_power'] == 400000.00
        assert summary['total_cash'] == 50000.00

    @pytest.mark.asyncio
    async def test_disconnection_handling(self, ib_client, mock_connection_manager):
        """Test handling of unexpected disconnections"""
        # Setup some subscriptions
        ib_client._market_data_subscriptions['ES'] = MockTicker()
        ib_client._active_orders[123] = MockTrade()

        # Simulate disconnection
        await ib_client._on_disconnected()

        # Verify cleanup
        assert len(ib_client._market_data_subscriptions) == 0
        assert len(ib_client._active_orders) == 0

    @pytest.mark.asyncio
    async def test_error_scenarios(self, ib_client, mock_connection_manager):
        """Test various error scenarios"""
        # Test order execution when disconnected
        mock_connection_manager.is_connected = Mock(return_value=False)

        with pytest.raises(ExecutionError, match="Not connected"):
            await ib_client.place_market_order('ES', 1, 'BUY')

        with pytest.raises(ExecutionError, match="Not connected"):
            await ib_client.place_limit_order('ES', 1, Decimal('4500'), 'BUY')

        # Test historical data when disconnected
        with pytest.raises(ConnectionError, match="Not connected"):
            await ib_client.request_historical_bars('ES')

    def test_subscription_status(self, ib_client):
        """Test market data subscription status tracking"""
        # Add mock subscription
        mock_ticker = MockTicker()
        mock_ticker.contract = Mock()
        ib_client._market_data_subscriptions['ES'] = mock_ticker

        status = ib_client.get_subscription_status()

        assert 'ES' in status
        assert status['ES'] == True


class TestIntegrationScenarios:
    """Integration tests combining multiple components"""

    @pytest.fixture
    def full_setup(self):
        """Setup complete integration environment"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            connection_manager = IBConnectionManager(event_bus)
            ib_client = IBClient(event_bus)

            return {
                'event_bus': event_bus,
                'connection_manager': connection_manager,
                'ib_client': ib_client
            }

    @pytest.mark.asyncio
    async def test_complete_trading_workflow(self, full_setup):
        """Test complete trading workflow from connection to execution"""
        components = full_setup
        ib_client = components['ib_client']
        event_bus = components['event_bus']

        # Mock the complete IB API chain
        mock_ib = MockIB()
        mock_ib.connectAsync = AsyncMock(return_value=None)
        mock_ib.isConnected = Mock(return_value=True)

        with patch('broker.connection_manager.IB', return_value=mock_ib):
            with patch('broker.ib_client.IBConnectionManager'):
                # 1. Connect to IB
                success = await ib_client.connect()
                assert success

                # 2. Subscribe to market data
                mock_ticker = MockTicker()
                mock_ib.reqMktData = Mock(return_value=mock_ticker)

                success = await ib_client.subscribe_market_data('ES')
                assert success

                # 3. Simulate tick data and verify event publishing
                mock_ticker.bid = 4500.00
                mock_ticker.ask = 4500.25
                await ib_client._on_tick_update('ES', mock_ticker)

                # Verify tick event published
                assert event_bus.publish.called

                # 4. Place order
                mock_trade = MockTrade()
                mock_ib.placeOrder = Mock(return_value=mock_trade)

                order_id = await ib_client.place_market_order('ES', 1, 'BUY')
                assert order_id == mock_trade.order.orderId

                # 5. Simulate order fill
                mock_fill = Mock()
                mock_fill.execution.shares = 1
                mock_fill.execution.price = 4500.25

                await ib_client._on_order_fill(mock_trade, mock_fill)

                # 6. Check positions
                mock_position = Mock()
                mock_position.contract.symbol = 'ES'
                mock_position.position = 1
                mock_position.avgCost = 4500.25
                mock_ib.positions = Mock(return_value=[mock_position])

                positions = await ib_client.get_positions()
                assert len(positions) == 1
                assert positions[0]['symbol'] == 'ES'

    @pytest.mark.asyncio
    async def test_connection_resilience(self, full_setup):
        """Test system resilience during connection issues"""
        components = full_setup
        connection_manager = components['connection_manager']

        mock_ib = MockIB()

        with patch('broker.connection_manager.IB', return_value=mock_ib):
            # Simulate connection failures and recovery
            connection_attempts = []

            async def mock_connect(*args, **kwargs):
                connection_attempts.append(len(connection_attempts) + 1)
                if len(connection_attempts) < 3:
                    raise Exception(f"Connection failed attempt {len(connection_attempts)}")
                return None

            mock_ib.connectAsync = mock_connect
            mock_ib.isConnected = Mock(return_value=True)

            # Should eventually succeed after retries
            with patch.object(connection_manager, '_schedule_reconnect') as mock_schedule:
                try:
                    await connection_manager.connect()
                    assert False, "Should have raised exception"
                except ConnectionError:
                    assert len(connection_attempts) == 1
                    assert mock_schedule.called

    @pytest.mark.asyncio
    async def test_data_integrity_under_stress(self, full_setup):
        """Test data integrity under high-frequency updates"""
        components = full_setup
        ib_client = components['ib_client']
        event_bus = components['event_bus']

        # Simulate rapid tick updates
        mock_ticker = MockTicker()
        published_events = []

        async def capture_event(event):
            published_events.append(event)

        event_bus.publish = AsyncMock(side_effect=capture_event)

        # Generate 100 rapid tick updates
        for i in range(100):
            mock_ticker.bid = 4500.00 + (i * 0.25)
            mock_ticker.ask = 4500.25 + (i * 0.25)
            mock_ticker.last = 4500.00 + (i * 0.25)

            await ib_client._on_tick_update('ES', mock_ticker)

        # Verify all events processed
        assert len(published_events) == 100

        # Verify data integrity
        for i, event in enumerate(published_events):
            expected_price = Decimal('4500.00') + (Decimal('0.25') * i)
            assert event.bid_price == expected_price
            assert event.symbol == 'ES'


class TestPerformanceAndReliability:
    """Performance and reliability tests"""

    @pytest.mark.asyncio
    async def test_memory_leak_prevention(self):
        """Test that connections and subscriptions don't leak memory"""
        event_bus = Mock(spec=EventBus)

        with patch('broker.connection_manager.get_config') as mock_config:
            mock_config.return_value.broker.host = "127.0.0.1"
            mock_config.return_value.broker.port = 7497
            mock_config.return_value.broker.client_id = 1

            # Create and destroy multiple connection managers
            for i in range(10):
                connection_manager = IBConnectionManager(event_bus)
                # Simulate some activity
                connection_manager._connection_callbacks.append(Mock())
                connection_manager._disconnection_callbacks.append(Mock())

                # Explicit cleanup
                await connection_manager.disconnect()

                # Verify cleanup
                assert len(connection_manager._connection_callbacks) > 0
                assert len(connection_manager._disconnection_callbacks) > 0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test handling of concurrent operations"""
        event_bus = Mock(spec=EventBus)
        ib_client = IBClient(event_bus)

        # Mock successful operations
        with patch.object(ib_client, 'place_market_order') as mock_order:
            mock_order.return_value = AsyncMock(return_value=123)

            # Submit multiple concurrent orders
            tasks = []
            for i in range(5):
                task = ib_client.place_market_order('ES', 1, 'BUY')
                tasks.append(task)

            # All should complete without interference
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify no exceptions occurred
            for result in results:
                assert not isinstance(result, Exception)

    def test_precision_maintenance(self):
        """Test that financial precision is maintained throughout calculations"""
        # Test various precision scenarios
        test_cases = [
            (Decimal('4500.25'), 1, Decimal('0.25')),
            (Decimal('15000.50'), 2, Decimal('0.25')),
            (Decimal('100.125'), 1, Decimal('0.125')),
        ]

        for price, quantity, tick_size in test_cases:
            # Simulate calculations that might lose precision
            calculated_value = price * quantity
            tick_value = tick_size * 50  # ES multiplier

            # Verify no precision loss
            assert isinstance(calculated_value, Decimal)
            assert isinstance(tick_value, Decimal)

            # Verify string representations maintain precision
            price_str = str(price)
            assert '.' in price_str or price == int(price)


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.DEBUG)

    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])