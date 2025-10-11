"""
Paper Trading Integration Tests
Tests using real IB Gateway Paper Trading connection
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime


@pytest.mark.asyncio
@pytest.mark.paper_trading
class TestPaperTradingConnection:
    """Test Paper Trading connection and basic operations"""

    async def test_connection_lifecycle(self, ib_connection):
        """Test connection and disconnection"""
        assert ib_connection.is_connected()
        assert ib_connection.state.value == "connected"

        conn_info = ib_connection.get_connection_info()
        assert conn_info['state'] == 'connected'
        assert conn_info['host'] == '127.0.0.1'
        assert conn_info['port'] == 4002  # Paper Trading port

    async def test_health_check(self, ib_connection):
        """Test connection health check"""
        is_healthy = await ib_connection.health_check()
        assert is_healthy
        assert ib_connection.last_health_check is not None

    async def test_connection_info(self, ib_connection):
        """Test connection information retrieval"""
        info = ib_connection.get_connection_info()

        assert info['state'] == 'connected'
        assert info['reconnect_attempts'] == 0
        assert info['last_health_check'] is not None


@pytest.mark.unit
class TestContractFactory:
    """Test futures contract creation and validation (no IB connection required)"""

    def test_es_contract_creation(self, contract_factory):
        """Test E-mini S&P 500 contract creation"""
        # Test contract creation with expiry
        contract = contract_factory.create_futures('ES', '202412')

        assert contract.symbol == 'ES'
        assert contract.exchange == 'CME'
        assert contract.currency == 'USD'
        assert contract.expiry == '202412'
        assert contract.multiplier == 50
        assert contract.tick_size == Decimal('0.25')

    def test_contract_specs(self, contract_factory):
        """Test contract specification retrieval"""
        # Get ES specifications
        specs = contract_factory.get_contract_specs('ES')

        assert specs['name'] == 'E-mini S&P 500'
        assert specs['exchange'] == 'CME'
        assert specs['multiplier'] == 50
        assert specs['tick_size'] == Decimal('0.25')
        assert specs['min_tick_value'] == Decimal('12.50')

        # Get NQ specifications
        specs = contract_factory.get_contract_specs('NQ')

        assert specs['name'] == 'E-mini NASDAQ-100'
        assert specs['multiplier'] == 20
        assert specs['min_tick_value'] == Decimal('5.00')

    def test_tick_value_calculation(self, contract_factory):
        """Test tick value calculations"""
        # ES: 0.25 point = $12.50 per tick
        tick_value = contract_factory.calculate_tick_value('ES', Decimal('4500.00'), ticks=1)
        assert tick_value == Decimal('12.50')

        # ES: 4 ticks = $50.00
        tick_value = contract_factory.calculate_tick_value('ES', Decimal('4500.00'), ticks=4)
        assert tick_value == Decimal('50.00')

        # NQ: 0.25 point = $5.00 per tick
        tick_value = contract_factory.calculate_tick_value('NQ', Decimal('15000.00'), ticks=1)
        assert tick_value == Decimal('5.00')

    def test_position_value_calculation(self, contract_factory):
        """Test position value calculations"""
        # ES at 4500.00 with 1 contract
        position_value = contract_factory.calculate_position_value('ES', Decimal('4500.00'), 1)
        assert position_value == Decimal('225000.00')  # 4500 * 50

        # NQ at 15000.00 with 2 contracts
        position_value = contract_factory.calculate_position_value('NQ', Decimal('15000.00'), 2)
        assert position_value == Decimal('600000.00')  # 15000 * 20 * 2

        # MES (micro) at 4500.00 with 10 contracts
        position_value = contract_factory.calculate_position_value('MES', Decimal('4500.00'), 10)
        assert position_value == Decimal('225000.00')  # 4500 * 5 * 10

    def test_margin_requirements(self, contract_factory):
        """Test margin requirement calculations"""
        # ES day trading margin
        margin = contract_factory.get_margin_requirement('ES', is_day_trading=True)
        assert margin == Decimal('500')

        # ES overnight margin
        margin = contract_factory.get_margin_requirement('ES', is_day_trading=False)
        assert margin == Decimal('13200')

        # NQ day trading margin
        margin = contract_factory.get_margin_requirement('NQ', is_day_trading=True)
        assert margin == Decimal('500')

        # MES (micro) margins are lower
        margin = contract_factory.get_margin_requirement('MES', is_day_trading=True)
        assert margin == Decimal('50')

    def test_continuous_futures(self, contract_factory):
        """Test continuous futures contract creation"""
        contract = contract_factory.create_continuous_futures('ES')

        assert contract.symbol == 'ES'
        assert contract.exchange == 'CME'
        assert contract.currency == 'USD'
        assert contract.includeExpired == False


@pytest.mark.asyncio
@pytest.mark.paper_trading
class TestPaperTradingClient:
    """Test IB Client with Paper Trading"""

    async def test_client_connection(self, ib_client):
        """Test IB Client connection"""
        assert ib_client.connection_manager.is_connected()

    async def test_account_summary(self, ib_client):
        """Test account summary retrieval"""
        summary = await ib_client.get_account_summary()

        assert 'account_id' in summary
        # Paper Trading account ID
        assert len(summary['account_id']) > 0

        # These might be 0 for new paper trading account
        assert 'net_liquidation' in summary
        assert 'available_funds' in summary
        assert 'buying_power' in summary

    async def test_positions(self, ib_client):
        """Test position retrieval"""
        positions = await ib_client.get_positions()
        assert isinstance(positions, list)
        # Might be empty for new account

    async def test_market_data_subscription(self, ib_client):
        """Test market data subscription for ES"""
        # Subscribe to market data
        success = await ib_client.subscribe_market_data('ES')
        assert success

        # Wait for data
        await asyncio.sleep(2)

        # Check subscription status
        status = ib_client.get_subscription_status()
        assert 'ES' in status

        # Unsubscribe
        await ib_client.unsubscribe_market_data('ES')

    async def test_historical_data(self, ib_client):
        """Test historical data request"""
        # Request 1 day of 1-minute bars for ES
        bars = await ib_client.request_historical_bars(
            symbol='ES',
            duration='1 D',
            bar_size='1 min'
        )

        assert len(bars) > 0
        assert all(hasattr(bar, 'date') for bar in bars)
        assert all(hasattr(bar, 'open') for bar in bars)
        assert all(hasattr(bar, 'high') for bar in bars)
        assert all(hasattr(bar, 'low') for bar in bars)
        assert all(hasattr(bar, 'close') for bar in bars)


@pytest.mark.asyncio
@pytest.mark.paper_trading
@pytest.mark.slow
class TestPaperTradingOrders:
    """Test order execution with Paper Trading (slow tests)"""

    async def test_market_order_lifecycle(self, ib_client):
        """Test market order placement and cancellation"""
        # Place market order for 1 ES contract
        order_id = await ib_client.place_market_order(
            symbol='ES',
            quantity=1,
            action='BUY'
        )

        assert order_id is not None
        assert isinstance(order_id, int)

        # Wait for order to be submitted
        await asyncio.sleep(1)

        # Cancel the order
        success = await ib_client.cancel_order(order_id)
        assert success

    async def test_limit_order(self, ib_client):
        """Test limit order placement"""
        # Place limit order for ES (far from market)
        order_id = await ib_client.place_limit_order(
            symbol='ES',
            quantity=1,
            limit_price=Decimal('4000.00'),  # Far below market
            action='BUY'
        )

        assert order_id is not None
        await asyncio.sleep(1)

        # Cancel
        await ib_client.cancel_order(order_id)

    async def test_bracket_order(self, ib_client):
        """Test bracket order placement"""
        # Place bracket order for ES
        order_ids = await ib_client.place_bracket_order(
            symbol='ES',
            quantity=1,
            action='BUY',
            entry_price=Decimal('4000.00'),  # Far below market
            stop_price=Decimal('3950.00'),
            target_price=Decimal('4050.00')
        )

        assert len(order_ids) == 3  # Parent, stop, profit
        await asyncio.sleep(1)

        # Cancel parent order
        await ib_client.cancel_order(order_ids[0])


@pytest.mark.asyncio
@pytest.mark.paper_trading
class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_invalid_symbol(self, contract_factory):
        """Test handling of invalid symbol (no IB connection required)"""
        import pytest
        with pytest.raises(ValueError):
            contract_factory.create_futures('INVALID_SYMBOL')

    async def test_duplicate_subscription(self, ib_client):
        """Test duplicate market data subscription"""
        # First subscription
        success1 = await ib_client.subscribe_market_data('ES')
        assert success1

        # Duplicate subscription (should handle gracefully)
        success2 = await ib_client.subscribe_market_data('ES')
        # Should either succeed or fail gracefully
        assert success2  # Already subscribed returns True

        # Cleanup
        await ib_client.unsubscribe_market_data('ES')

    async def test_connection_resilience(self, ib_connection):
        """Test connection health monitoring"""
        # Verify connection is healthy
        assert ib_connection.is_connected()

        # Perform health check
        is_healthy = await ib_connection.health_check()
        assert is_healthy

        # Check connection info
        info = ib_connection.get_connection_info()
        assert info['state'] == 'connected'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
