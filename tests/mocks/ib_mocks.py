"""
Mock Interactive Brokers API Components
Provides comprehensive mocks for testing without actual TWS/Gateway connection
"""

from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Callable
import asyncio
import random
import uuid


class MockIB:
    """Mock IB API client that simulates real IB behavior"""

    def __init__(self):
        self.connected = False
        self.connection_id = None
        self.host = None
        self.port = None
        self.client_id = None

        # Event handlers
        self.disconnectedEvent = MockEventHandler()
        self.errorEvent = MockEventHandler()

        # Mock data storage
        self._positions = []
        self._orders = {}
        self._account_summary = {}
        self._market_data = {}

        # Request tracking
        self._next_order_id = 1
        self._request_id = 1

        # Simulation controls
        self.connection_delay = 0.1
        self.order_fill_delay = 0.5
        self.should_fail_connection = False
        self.should_fail_orders = False

    async def connectAsync(self, host: str, port: int, clientId: int, timeout: float = 4.0):
        """Mock async connection to TWS/Gateway"""
        self.host = host
        self.port = port
        self.client_id = clientId

        # Simulate connection delay
        await asyncio.sleep(self.connection_delay)

        if self.should_fail_connection:
            raise Exception(f"Failed to connect to {host}:{port}")

        self.connected = True
        self.connection_id = str(uuid.uuid4())

        # Initialize default account data
        self._initialize_default_data()

    def disconnect(self):
        """Disconnect from TWS/Gateway"""
        if self.connected:
            self.connected = False
            # Trigger disconnection event
            self.disconnectedEvent.emit()

    def isConnected(self) -> bool:
        """Check if connected"""
        return self.connected

    async def reqCurrentTimeAsync(self) -> datetime:
        """Request current server time"""
        if not self.connected:
            raise Exception("Not connected")
        return datetime.now()

    def reqMktData(self, contract, genericTickList: str = '', snapshot: bool = False,
                   regulatorySnapshot: bool = False, mktDataOptions: List = None) -> 'MockTicker':
        """Request market data"""
        if not self.connected:
            raise Exception("Not connected")

        ticker = MockTicker(contract)
        ticker.start_simulation()
        self._market_data[contract.symbol] = ticker
        return ticker

    def cancelMktData(self, contract):
        """Cancel market data"""
        if contract.symbol in self._market_data:
            ticker = self._market_data[contract.symbol]
            ticker.stop_simulation()
            del self._market_data[contract.symbol]

    async def reqHistoricalDataAsync(self, contract, endDateTime: str, durationStr: str,
                                   barSizeSetting: str, whatToShow: str, useRTH: bool,
                                   formatDate: int) -> List['MockBarData']:
        """Request historical data"""
        if not self.connected:
            raise Exception("Not connected")

        # Generate mock historical bars
        bars = []
        base_price = 4500.0 if contract.symbol == 'ES' else 15000.0

        # Parse duration to determine number of bars
        duration_parts = durationStr.split()
        if len(duration_parts) == 2:
            amount = int(duration_parts[0])
            unit = duration_parts[1].upper()

            if unit.startswith('D'):
                num_bars = amount * 390  # Assume 390 minutes per day
            elif unit.startswith('H'):
                num_bars = amount * 60
            else:
                num_bars = amount
        else:
            num_bars = 100

        # Generate bars with realistic price movement
        current_time = datetime.now()
        for i in range(num_bars):
            bar_time = current_time - timedelta(minutes=num_bars - i)

            # Simulate price movement
            price_change = random.uniform(-0.5, 0.5)
            open_price = base_price + (i * 0.1) + price_change
            close_price = open_price + random.uniform(-0.25, 0.25)
            high_price = max(open_price, close_price) + random.uniform(0, 0.5)
            low_price = min(open_price, close_price) - random.uniform(0, 0.5)

            bar = MockBarData(
                time=bar_time,
                open_=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=random.randint(100, 1000)
            )
            bars.append(bar)

        return bars

    def placeOrder(self, contract, order) -> 'MockTrade':
        """Place an order"""
        if not self.connected:
            raise Exception("Not connected")

        if self.should_fail_orders:
            raise Exception("Order placement failed")

        # Assign order ID
        if order.orderId == 0:
            order.orderId = self._next_order_id
            self._next_order_id += 1

        # Create mock trade
        trade = MockTrade(contract, order)
        self._orders[order.orderId] = trade

        # Simulate order processing
        asyncio.create_task(self._process_order(trade))

        return trade

    def cancelOrder(self, order):
        """Cancel an order"""
        if order.orderId in self._orders:
            trade = self._orders[order.orderId]
            trade.orderStatus.status = 'Cancelled'
            trade.statusEvent.emit(trade)

    def positions(self) -> List['MockPosition']:
        """Get current positions"""
        return self._positions.copy()

    def accountSummary(self) -> List['MockAccountValue']:
        """Get account summary"""
        return list(self._account_summary.values())

    async def reqAllOrdersAsync(self) -> int:
        """Request all orders and return next valid order ID"""
        return self._next_order_id

    def _initialize_default_data(self):
        """Initialize default account data"""
        # Default account summary
        self._account_summary = {
            'NetLiquidation': MockAccountValue('NetLiquidation', '100000.00', 'USD'),
            'BuyingPower': MockAccountValue('BuyingPower', '400000.00', 'USD'),
            'TotalCashValue': MockAccountValue('TotalCashValue', '50000.00', 'USD'),
            'RealizedPnL': MockAccountValue('RealizedPnL', '0.00', 'USD'),
            'UnrealizedPnL': MockAccountValue('UnrealizedPnL', '0.00', 'USD'),
            'InitMarginReq': MockAccountValue('InitMarginReq', '0.00', 'USD'),
        }

        # No initial positions
        self._positions = []

    async def _process_order(self, trade: 'MockTrade'):
        """Simulate order processing and fills"""
        # Simulate order acknowledgment
        await asyncio.sleep(0.1)
        trade.orderStatus.status = 'Submitted'
        trade.statusEvent.emit(trade)

        # Simulate order fill delay
        await asyncio.sleep(self.order_fill_delay)

        # Simulate fill
        if trade.orderStatus.status == 'Submitted':
            fill_price = self._get_realistic_fill_price(trade)

            # Create fill
            fill = MockFill(
                execution=MockExecution(
                    orderId=trade.order.orderId,
                    shares=trade.order.totalQuantity,
                    price=fill_price,
                    time=datetime.now()
                ),
                commissionReport=MockCommissionReport(
                    commission=2.50  # Typical futures commission
                )
            )

            # Update order status
            trade.orderStatus.status = 'Filled'
            trade.orderStatus.filled = trade.order.totalQuantity
            trade.orderStatus.remaining = 0
            trade.orderStatus.avgFillPrice = fill_price

            # Emit events
            trade.statusEvent.emit(trade)
            trade.fillEvent.emit(trade, fill)

            # Update positions
            self._update_position(trade, fill)

    def _get_realistic_fill_price(self, trade: 'MockTrade') -> float:
        """Get realistic fill price based on order type"""
        # Use market data if available
        symbol = trade.contract.symbol
        if symbol in self._market_data:
            ticker = self._market_data[symbol]
            if trade.order.action == 'BUY':
                return ticker.ask if ticker.ask > 0 else 4500.25
            else:
                return ticker.bid if ticker.bid > 0 else 4500.00

        # Default prices by symbol
        default_prices = {
            'ES': 4500.25,
            'NQ': 15000.50,
            'YM': 35000.00,
            'RTY': 2200.00,
            'MES': 4500.25,
            'MNQ': 15000.50,
        }

        base_price = default_prices.get(symbol, 4500.25)

        # Add small random slippage
        slippage = random.uniform(-0.25, 0.25)
        return base_price + slippage

    def _update_position(self, trade: 'MockTrade', fill: 'MockFill'):
        """Update position based on fill"""
        symbol = trade.contract.symbol

        # Find existing position
        position = None
        for pos in self._positions:
            if pos.contract.symbol == symbol:
                position = pos
                break

        if position is None:
            # Create new position
            position = MockPosition(
                contract=trade.contract,
                position=0,
                avgCost=0.0
            )
            self._positions.append(position)

        # Update position
        if trade.order.action == 'BUY':
            new_quantity = position.position + fill.execution.shares
        else:
            new_quantity = position.position - fill.execution.shares

        if new_quantity == 0:
            # Position closed
            self._positions.remove(position)
        else:
            # Update average cost
            if position.position == 0:
                position.avgCost = fill.execution.price
            else:
                total_cost = (position.avgCost * abs(position.position) +
                            fill.execution.price * fill.execution.shares)
                position.avgCost = total_cost / abs(new_quantity)

            position.position = new_quantity

        # Update unrealized P&L
        if position in self._positions:
            position.unrealizedPNL = self._calculate_unrealized_pnl(position)


class MockEventHandler:
    """Mock event handler that can register callbacks"""

    def __init__(self):
        self._callbacks = []

    def __iadd__(self, callback):
        """Add callback using += operator"""
        self._callbacks.append(callback)
        return self

    def emit(self, *args, **kwargs):
        """Emit event to all callbacks"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(*args, **kwargs))
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in event callback: {e}")


class MockTicker:
    """Mock ticker that simulates real-time market data"""

    def __init__(self, contract=None):
        self.contract = contract
        self.bid = -1
        self.ask = -1
        self.last = -1
        self.bidSize = -1
        self.askSize = -1
        self.lastSize = -1
        self.volume = -1

        # Event handler for updates
        self.updateEvent = MockEventHandler()

        # Simulation control
        self._simulation_task = None
        self._running = False

    def start_simulation(self):
        """Start simulating market data updates"""
        if not self._running:
            self._running = True
            self._simulation_task = asyncio.create_task(self._simulate_data())

    def stop_simulation(self):
        """Stop simulating market data"""
        self._running = False
        if self._simulation_task:
            self._simulation_task.cancel()

    async def _simulate_data(self):
        """Simulate realistic market data updates"""
        # Initialize with base values
        base_price = 4500.0 if self.contract and self.contract.symbol == 'ES' else 15000.0
        spread = 0.25

        self.bid = base_price
        self.ask = base_price + spread
        self.last = base_price
        self.bidSize = random.randint(5, 50)
        self.askSize = random.randint(5, 50)
        self.volume = 0

        try:
            while self._running:
                # Simulate price movement
                price_change = random.uniform(-0.5, 0.5)

                self.bid += price_change
                self.ask = self.bid + spread

                # Simulate trade
                if random.random() < 0.3:  # 30% chance of trade
                    if random.random() < 0.5:
                        self.last = self.bid
                    else:
                        self.last = self.ask
                    self.lastSize = random.randint(1, 10)
                    self.volume += self.lastSize

                # Update sizes
                self.bidSize = random.randint(5, 50)
                self.askSize = random.randint(5, 50)

                # Emit update event
                self.updateEvent.emit(self, None)

                # Wait before next update
                await asyncio.sleep(random.uniform(0.1, 1.0))

        except asyncio.CancelledError:
            pass


class MockContract:
    """Mock contract object"""

    def __init__(self, symbol: str = "ES", exchange: str = "CME", currency: str = "USD"):
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.lastTradeDateOrContractMonth = None
        self.localSymbol = None
        self.includeExpired = False


class MockOrder:
    """Mock order object"""

    def __init__(self, action: str = "BUY", totalQuantity: int = 1, orderType: str = "MKT"):
        self.orderId = 0
        self.action = action
        self.totalQuantity = totalQuantity
        self.orderType = orderType
        self.lmtPrice = 0.0
        self.auxPrice = 0.0  # Stop price


class MockOrderStatus:
    """Mock order status object"""

    def __init__(self):
        self.status = 'Pending'
        self.filled = 0
        self.remaining = 0
        self.avgFillPrice = 0.0


class MockTrade:
    """Mock trade object representing an order and its status"""

    def __init__(self, contract=None, order=None, order_id: int = None):
        self.contract = contract or MockContract()
        self.order = order or MockOrder()
        if order_id:
            self.order.orderId = order_id
        elif self.order.orderId == 0:
            self.order.orderId = random.randint(1000, 9999)

        self.orderStatus = MockOrderStatus()

        # Event handlers
        self.statusEvent = MockEventHandler()
        self.fillEvent = MockEventHandler()


class MockExecution:
    """Mock execution object"""

    def __init__(self, orderId: int, shares: int, price: float, time: datetime):
        self.orderId = orderId
        self.shares = shares
        self.price = price
        self.time = time


class MockCommissionReport:
    """Mock commission report"""

    def __init__(self, commission: float):
        self.commission = commission


class MockFill:
    """Mock fill object"""

    def __init__(self, execution: MockExecution, commissionReport: MockCommissionReport):
        self.execution = execution
        self.commissionReport = commissionReport


class MockPosition:
    """Mock position object"""

    def __init__(self, contract: MockContract, position: int, avgCost: float):
        self.contract = contract
        self.position = position
        self.avgCost = avgCost
        self.marketValue = 0.0
        self.unrealizedPNL = 0.0
        self.realizedPNL = 0.0


class MockAccountValue:
    """Mock account value object"""

    def __init__(self, tag: str, value: str, currency: str):
        self.tag = tag
        self.value = value
        self.currency = currency


class MockBarData:
    """Mock historical bar data"""

    def __init__(self, time=None, open_=None, high=None, low=None, close=None, volume=None):
        self.time = time or datetime.now()
        self.open_ = open_ or 4500.0
        self.high = high or 4500.25
        self.low = low or 4499.75
        self.close = close or 4500.00
        self.volume = volume or 100


class MockBracketOrder:
    """Mock bracket order generator"""

    def __init__(self, action: str, quantity: int, limitPrice: float,
                 stopPrice: float, profitTarget: float):
        # Parent order
        parent = MockOrder(action, quantity, "LMT")
        parent.lmtPrice = limitPrice
        parent.orderId = random.randint(1000, 9999)

        # Stop loss order
        stop_action = "SELL" if action == "BUY" else "BUY"
        stop_order = MockOrder(stop_action, quantity, "STP")
        stop_order.auxPrice = stopPrice
        stop_order.orderId = parent.orderId + 1

        # Take profit order
        profit_order = MockOrder(stop_action, quantity, "LMT")
        profit_order.lmtPrice = profitTarget
        profit_order.orderId = parent.orderId + 2

        self._orders = [parent, stop_order, profit_order]

    def __iter__(self):
        return iter(self._orders)


# Patch imports for easier testing
def patch_ib_imports():
    """Patch IB imports to use mocks"""
    import sys

    # Create mock modules
    mock_ib_async = Mock()
    mock_ib_async.IB = MockIB
    mock_ib_async.Contract = MockContract
    mock_ib_async.MarketOrder = MockOrder
    mock_ib_async.LimitOrder = MockOrder
    mock_ib_async.StopOrder = MockOrder
    mock_ib_async.BracketOrder = MockBracketOrder
    mock_ib_async.ConnectionError = Exception

    sys.modules['ib_async'] = mock_ib_async

    return mock_ib_async


if __name__ == '__main__':
    # Example usage for testing
    async def test_mock_ib():
        ib = MockIB()

        # Test connection
        await ib.connectAsync("127.0.0.1", 7497, 1)
        print(f"Connected: {ib.isConnected()}")

        # Test market data
        contract = MockContract("ES")
        ticker = ib.reqMktData(contract)
        ticker.start_simulation()

        # Wait a bit for simulated data
        await asyncio.sleep(2)

        print(f"Bid: {ticker.bid}, Ask: {ticker.ask}")

        # Test order placement
        order = MockOrder("BUY", 1)
        trade = ib.placeOrder(contract, order)

        # Wait for fill
        await asyncio.sleep(1)

        print(f"Order status: {trade.orderStatus.status}")

        # Cleanup
        ticker.stop_simulation()
        ib.disconnect()

    # Run test
    asyncio.run(test_mock_ib())