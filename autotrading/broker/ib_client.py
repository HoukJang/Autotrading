"""
IB Client - Main interface for Interactive Brokers API
Wraps ib_async and integrates with event bus
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

from ib_async import IB, Trade, Ticker, BarData
from ib_async import MarketOrder, LimitOrder, BracketOrder

from .connection_manager import IBConnectionManager, ConnectionState
from .contracts import ContractFactory
from ..core.events import Event, EventType
from ..core.event_bus import EventBus
from ..core.exceptions import TradingSystemError, ExecutionError
from ..config import get_config

logger = logging.getLogger(__name__)


class TickEvent(Event):
    """Real-time tick event"""

    def __init__(self, symbol: str, timestamp: datetime,
                 bid_price: Optional[Decimal] = None,
                 bid_size: Optional[int] = None,
                 ask_price: Optional[Decimal] = None,
                 ask_size: Optional[int] = None,
                 last_price: Optional[Decimal] = None,
                 last_size: Optional[int] = None,
                 volume: Optional[int] = None):
        super().__init__(event_type=EventType.MARKET_DATA)
        self.symbol = symbol
        self.timestamp = timestamp
        self.bid_price = bid_price
        self.bid_size = bid_size
        self.ask_price = ask_price
        self.ask_size = ask_size
        self.last_price = last_price
        self.last_size = last_size
        self.volume = volume


class IBClient:
    """
    Main IB API client with event bus integration
    """

    def __init__(self, event_bus: EventBus, client_id: Optional[int] = None):
        """
        Initialize IB client

        Args:
            event_bus: Event bus for publishing events
            client_id: Optional client ID override (for multi-connection scenarios)
        """
        self.config = get_config()
        self.event_bus = event_bus
        self.connection_manager = IBConnectionManager(event_bus, client_id=client_id)

        # IB instance (from connection manager)
        self._ib: Optional[IB] = None

        # Active subscriptions
        self._market_data_subscriptions: Dict[str, Ticker] = {}
        self._active_orders: Dict[int, Trade] = {}
        self._positions: Dict[str, Dict] = {}

        # Request ID management
        self._next_order_id = 1

        # Setup callbacks
        self.connection_manager.add_connection_callback(self._on_connected)
        self.connection_manager.add_disconnection_callback(self._on_disconnected)

        logger.info("IBClient initialized")

    async def connect(self) -> bool:
        """
        Connect to IB API

        Returns:
            True if connection successful
        """
        success = await self.connection_manager.connect()

        if success:
            self._ib = self.connection_manager.ib
            await self._setup_event_handlers()

        return success

    async def disconnect(self) -> None:
        """Disconnect from IB API"""
        # Cancel all market data subscriptions
        for symbol in list(self._market_data_subscriptions.keys()):
            await self.unsubscribe_market_data(symbol)

        await self.connection_manager.disconnect()

    # Market Data Methods

    async def subscribe_market_data(self, symbol: str) -> bool:
        """
        Subscribe to real-time market data

        Args:
            symbol: Futures symbol to subscribe to

        Returns:
            True if subscription successful
        """
        if not self._ib or not self.connection_manager.is_connected():
            logger.error("Not connected to IB API")
            return False

        if symbol in self._market_data_subscriptions:
            logger.warning(f"Already subscribed to {symbol}")
            return True

        try:
            # Create front month contract
            contract = ContractFactory.create_futures(symbol).to_ib_contract()

            # Qualify contract to get all available contracts
            qualified_contracts = await self._ib.qualifyContractsAsync(contract)

            if not qualified_contracts or len(qualified_contracts) == 0:
                logger.error(f"Failed to qualify contract for {symbol}")
                return False

            # Sort by expiry date and use the front month (nearest expiry)
            qualified_contracts.sort(key=lambda c: c.lastTradeDateOrContractMonth)
            qualified_contract = qualified_contracts[0]

            logger.info(f"Qualified contract for {symbol}: {qualified_contract.localSymbol} (expires: {qualified_contract.lastTradeDateOrContractMonth}), conId={qualified_contract.conId}")

            # Request market data
            ticker = self._ib.reqMktData(
                qualified_contract,
                genericTickList='',
                snapshot=False,
                regulatorySnapshot=False,
                mktDataOptions=[]
            )

            # Store subscription
            self._market_data_subscriptions[symbol] = ticker

            # Set up ticker callback
            ticker.updateEvent += lambda ticker, _: asyncio.create_task(
                self._on_tick_update(symbol, ticker)
            )

            logger.info(f"Subscribed to market data for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")
            return False

    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """
        Unsubscribe from market data

        Args:
            symbol: Symbol to unsubscribe from

        Returns:
            True if unsubscription successful
        """
        if symbol not in self._market_data_subscriptions:
            return True

        try:
            ticker = self._market_data_subscriptions[symbol]

            # Cancel market data
            self._ib.cancelMktData(ticker.contract)

            # Remove from subscriptions
            del self._market_data_subscriptions[symbol]

            logger.info(f"Unsubscribed from market data for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe from {symbol}: {e}")
            return False

    async def request_historical_bars(self, symbol: str, duration: str = "1 D",
                                     bar_size: str = "1 min",
                                     contract_month: Optional[str] = None,
                                     target_date: Optional[datetime] = None) -> List[BarData]:
        """
        Request historical bar data

        Args:
            symbol: Futures symbol
            duration: Duration string (e.g., "1 D", "1 W")
            bar_size: Bar size (e.g., "1 min", "5 mins")
            contract_month: Specific contract month in YYYYMM format (None for continuous)
            target_date: Target date for historical data (if specified, endDateTime is calculated)

        Returns:
            List of historical bars
        """
        if not self._ib or not self.connection_manager.is_connected():
            raise ConnectionError("Not connected to IB API")

        try:
            # Create contract
            if contract_month:
                # Use specific contract month
                futures_contract = ContractFactory.create_futures(symbol, expiry=contract_month)
                contract = futures_contract.to_ib_contract()
            else:
                # Use continuous contract
                contract = ContractFactory.create_continuous_futures(symbol)

            # Calculate endDateTime if target_date is provided
            if target_date:
                # For full trading day: use next day 17:00 (5 PM)
                # ES trading: 17:00 ~ next day 16:00 (23 hours, excluding 1-hour break)
                from datetime import timedelta
                end_date = target_date + timedelta(days=1)
                end_datetime_str = end_date.strftime('%Y%m%d 17:00:00')
                logger.info(f"Requesting data for {target_date.strftime('%Y-%m-%d')}, endDateTime: {end_datetime_str}")
            else:
                end_datetime_str = ''

            # Request historical data
            bars = await self._ib.reqHistoricalDataAsync(
                contract,
                endDateTime=end_datetime_str,
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=False,
                formatDate=1
            )

            logger.info(f"Retrieved {len(bars)} historical bars for {symbol}")
            return bars

        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            raise TradingSystemError(f"Historical data request failed: {e}")

    # Order Execution Methods

    async def place_market_order(self, symbol: str, quantity: int, action: str = "BUY") -> int:
        """
        Place a market order

        Args:
            symbol: Futures symbol
            quantity: Number of contracts
            action: "BUY" or "SELL"

        Returns:
            Order ID
        """
        if not self._ib or not self.connection_manager.is_connected():
            raise ExecutionError("Not connected to IB API")

        try:
            # Create contract
            contract = ContractFactory.create_futures(symbol).to_ib_contract()

            # Qualify contract to get all available contracts
            qualified_contracts = await self._ib.qualifyContractsAsync(contract)

            if not qualified_contracts or len(qualified_contracts) == 0:
                raise ExecutionError(f"Failed to qualify contract for {symbol}")

            # Sort by expiry date and use the front month (nearest expiry)
            qualified_contracts.sort(key=lambda c: c.lastTradeDateOrContractMonth)
            qualified_contract = qualified_contracts[0]

            logger.info(f"Qualified contract for order: {symbol} {qualified_contract.localSymbol} (expires: {qualified_contract.lastTradeDateOrContractMonth}), conId={qualified_contract.conId}")

            # Create market order
            order = MarketOrder(action=action, totalQuantity=abs(quantity))

            # Place order
            trade = self._ib.placeOrder(qualified_contract, order)

            # Store active order
            self._active_orders[trade.order.orderId] = trade

            # Set up trade callbacks
            trade.statusEvent += lambda trade: asyncio.create_task(
                self._on_order_status(trade)
            )
            trade.fillEvent += lambda trade, fill: asyncio.create_task(
                self._on_order_fill(trade, fill)
            )

            logger.info(f"Placed market order: {action} {quantity} {symbol}, Order ID: {trade.order.orderId}")
            return trade.order.orderId

        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            raise ExecutionError(f"Market order failed: {e}")

    async def place_limit_order(self, symbol: str, quantity: int, price: Decimal,
                               action: str = "BUY") -> int:
        """
        Place a limit order

        Args:
            symbol: Futures symbol
            quantity: Number of contracts
            price: Limit price
            action: "BUY" or "SELL"

        Returns:
            Order ID
        """
        if not self._ib or not self.connection_manager.is_connected():
            raise ExecutionError("Not connected to IB API")

        try:
            # Create contract
            contract = ContractFactory.create_futures(symbol).to_ib_contract()

            # Create limit order
            order = LimitOrder(
                action=action,
                totalQuantity=abs(quantity),
                lmtPrice=float(price)
            )

            # Place order
            trade = self._ib.placeOrder(contract, order)

            # Store active order
            self._active_orders[trade.order.orderId] = trade

            # Set up trade callbacks
            trade.statusEvent += lambda trade: asyncio.create_task(
                self._on_order_status(trade)
            )
            trade.fillEvent += lambda trade, fill: asyncio.create_task(
                self._on_order_fill(trade, fill)
            )

            logger.info(f"Placed limit order: {action} {quantity} {symbol} @ {price}")
            return trade.order.orderId

        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            raise ExecutionError(f"Limit order failed: {e}")

    async def place_bracket_order(self, symbol: str, quantity: int,
                                 entry_price: Decimal, stop_price: Decimal,
                                 target_price: Decimal, action: str = "BUY") -> List[int]:
        """
        Place a bracket order (entry + stop loss + take profit)

        Args:
            symbol: Futures symbol
            quantity: Number of contracts
            entry_price: Entry limit price
            stop_price: Stop loss price
            target_price: Take profit price
            action: "BUY" or "SELL"

        Returns:
            List of order IDs [parent, stop, target]
        """
        if not self._ib or not self.connection_manager.is_connected():
            raise ExecutionError("Not connected to IB API")

        try:
            # Create contract
            contract = ContractFactory.create_futures(symbol).to_ib_contract()

            # Create bracket order
            bracket = BracketOrder(
                action=action,
                quantity=abs(quantity),
                limitPrice=float(entry_price),
                stopPrice=float(stop_price),
                profitTarget=float(target_price)
            )

            # Place bracket order
            trades = []
            for order in bracket:
                trade = self._ib.placeOrder(contract, order)
                trades.append(trade)

                # Store active order
                self._active_orders[trade.order.orderId] = trade

                # Set up trade callbacks
                trade.statusEvent += lambda t=trade: asyncio.create_task(
                    self._on_order_status(t)
                )
                trade.fillEvent += lambda t=trade, f=None: asyncio.create_task(
                    self._on_order_fill(t, f)
                )

            order_ids = [t.order.orderId for t in trades]
            logger.info(
                f"Placed bracket order: {action} {quantity} {symbol} "
                f"@ {entry_price}, stop={stop_price}, target={target_price}"
            )

            return order_ids

        except Exception as e:
            logger.error(f"Failed to place bracket order: {e}")
            raise ExecutionError(f"Bracket order failed: {e}")

    async def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation successful
        """
        if not self._ib or not self.connection_manager.is_connected():
            return False

        if order_id not in self._active_orders:
            logger.warning(f"Order {order_id} not found")
            return False

        try:
            trade = self._active_orders[order_id]
            self._ib.cancelOrder(trade.order)

            logger.info(f"Cancelled order {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions

        Returns:
            List of position dictionaries
        """
        if not self._ib or not self.connection_manager.is_connected():
            return []

        try:
            positions = self._ib.positions()

            position_list = []
            for position in positions:
                position_dict = {
                    'symbol': position.contract.symbol,
                    'quantity': position.position,
                    'average_cost': position.avgCost,
                    'market_value': position.marketValue,
                    'unrealized_pnl': position.unrealizedPNL,
                    'realized_pnl': position.realizedPNL
                }
                position_list.append(position_dict)

                # Update internal positions
                self._positions[position.contract.symbol] = position_dict

            return position_list

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get account summary

        Returns:
            Account summary dictionary
        """
        if not self._ib or not self.connection_manager.is_connected():
            return {}

        try:
            # Get managed accounts
            accounts = self._ib.managedAccounts()
            if not accounts:
                logger.warning("No managed accounts found")
                return {}

            account_id = accounts[0]

            # Request account summary using reqAccountSummary
            summary = await self._ib.reqAccountSummaryAsync()

            account_dict = {}
            for item in summary:
                account_dict[item.tag] = {
                    'value': item.value,
                    'currency': item.currency,
                    'account': item.account
                }

            # Get key values
            result = {
                'account_id': account_id,
                'net_liquidation': float(account_dict.get('NetLiquidation', {}).get('value', 0)),
                'available_funds': float(account_dict.get('AvailableFunds', {}).get('value', 0)),
                'buying_power': float(account_dict.get('BuyingPower', {}).get('value', 0)),
                'excess_liquidity': float(account_dict.get('ExcessLiquidity', {}).get('value', 0)),
                'total_cash': float(account_dict.get('TotalCashValue', {}).get('value', 0)),
                'realized_pnl': float(account_dict.get('RealizedPnL', {}).get('value', 0)),
                'unrealized_pnl': float(account_dict.get('UnrealizedPnL', {}).get('value', 0)),
                'full_init_margin_req': float(account_dict.get('FullInitMarginReq', {}).get('value', 0)),
                'full_maint_margin_req': float(account_dict.get('FullMaintMarginReq', {}).get('value', 0))
            }

            return result

        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
            return {}

    # Private methods

    async def _on_connected(self) -> None:
        """Handle connection established"""
        logger.info("IBClient connected callback")
        self._ib = self.connection_manager.ib

        # Set next order ID (start from 1)
        if self._ib:
            self._next_order_id = 1

    async def _on_disconnected(self) -> None:
        """Handle disconnection"""
        logger.info("IBClient disconnected callback")

        # Clear subscriptions
        self._market_data_subscriptions.clear()
        self._active_orders.clear()

    async def _setup_event_handlers(self) -> None:
        """Set up IB event handlers"""
        if not self._ib:
            return

        # Additional event handlers can be added here

    async def _on_tick_update(self, symbol: str, ticker: Ticker) -> None:
        """Handle tick updates"""
        try:
            # Create tick event
            tick_event = TickEvent(
                symbol=symbol,
                timestamp=datetime.now(),
                bid_price=Decimal(str(ticker.bid)) if ticker.bid != -1 else None,
                bid_size=ticker.bidSize if ticker.bidSize != -1 else None,
                ask_price=Decimal(str(ticker.ask)) if ticker.ask != -1 else None,
                ask_size=ticker.askSize if ticker.askSize != -1 else None,
                last_price=Decimal(str(ticker.last)) if ticker.last != -1 else None,
                last_size=ticker.lastSize if ticker.lastSize != -1 else None,
                volume=ticker.volume if ticker.volume != -1 else None
            )

            # Publish to event bus
            await self.event_bus.publish(tick_event)

        except Exception as e:
            logger.error(f"Error processing tick for {symbol}: {e}")

    async def _on_order_status(self, trade: Trade) -> None:
        """Handle order status updates"""
        try:
            # Log status update
            logger.info(
                f"Order {trade.order.orderId} status: {trade.orderStatus.status}"
            )

            # Create order event
            # This would be expanded to create proper OrderEvent
            # For now, just log the update

        except Exception as e:
            logger.error(f"Error processing order status: {e}")

    async def _on_order_fill(self, trade: Trade, fill) -> None:
        """Handle order fills"""
        try:
            if fill:
                logger.info(
                    f"Order {trade.order.orderId} filled: "
                    f"{fill.execution.shares} @ {fill.execution.price}"
                )

                # Create fill event
                # This would be expanded to create proper FillEvent
                # For now, just log the fill

        except Exception as e:
            logger.error(f"Error processing order fill: {e}")

    def get_subscription_status(self) -> Dict[str, bool]:
        """Get market data subscription status"""
        return {
            symbol: ticker.contract is not None
            for symbol, ticker in self._market_data_subscriptions.items()
        }