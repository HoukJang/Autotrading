"""
Broker interface and backtesting broker implementation.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict
from collections import defaultdict

from .orders import Order, OrderType, OrderSide, OrderStatus, OrderGroup
from .position import Position, PositionSide, Account, Trade
from ..strategies.base import Bar


class Broker(ABC):
    """
    Abstract broker interface for order execution.

    Both backtesting and live trading brokers implement this interface,
    allowing strategies to work seamlessly in both environments.
    """

    @abstractmethod
    def place_order(self, order: Order) -> str:
        """
        Place an order.

        Args:
            order: Order to place

        Returns:
            Order ID
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False otherwise
        """
        pass

    @abstractmethod
    def cancel_exit_orders(self) -> List[Order]:
        """
        Cancel all pending exit orders (for trailing stop support).

        Returns:
            List of cancelled orders
        """
        pass

    @abstractmethod
    def update_exit_orders(self, new_tp_order: Optional[Order] = None,
                          new_sl_order: Optional[Order] = None) -> List[str]:
        """
        Update exit orders (cancel old, place new).

        This supports trailing stop and dynamic TP/SL adjustment.

        Args:
            new_tp_order: New take profit order (None to skip)
            new_sl_order: New stop loss order (None to skip)

        Returns:
            List of new order IDs
        """
        pass

    @abstractmethod
    def get_position(self) -> Optional[Position]:
        """
        Get current position.

        Returns:
            Current position if exists, None otherwise
        """
        pass

    @abstractmethod
    def get_account(self) -> Account:
        """
        Get account information.

        Returns:
            Account object
        """
        pass


class BacktestBroker(Broker):
    """
    Backtesting broker with realistic order execution simulation.

    Features:
    - LIMIT and STOP order execution based on bar high/low
    - OCO (One-Cancels-Other) order support
    - Commission calculation
    - Position management (single position at a time)
    - Order fill tracking and logging
    """

    def __init__(self, account: Account, commission_rate: float = 0.0004):
        """
        Initialize backtest broker.

        Args:
            account: Account to manage
            commission_rate: Commission as a fraction (e.g., 0.0004 = 0.04%)
        """
        self.account = account
        self.commission_rate = commission_rate

        self._position: Optional[Position] = None
        self._pending_orders: List[Order] = []
        self._filled_orders: List[Order] = []
        self._oco_groups: Dict[str, OrderGroup] = {}

        # Track which orders are children of which parents
        self._child_orders: Dict[str, List[Order]] = defaultdict(list)

    def place_order(self, order: Order) -> str:
        """
        Place an order.

        Args:
            order: Order to place

        Returns:
            Order ID
        """
        # Prevent entry orders if we already have a position
        if order.is_entry_order():
            if self._position is not None:
                order.status = OrderStatus.REJECTED
                return order.order_id

        # If order has a parent, track the relationship
        if order.parent_id:
            self._child_orders[order.parent_id].append(order)
            # Child orders start as PENDING (not ACTIVE until parent fills)
            order.status = OrderStatus.PENDING
        else:
            # Entry orders are immediately ACTIVE
            order.status = OrderStatus.ACTIVE

        self._pending_orders.append(order)
        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self._pending_orders:
            if order.order_id == order_id:
                if order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                    order.status = OrderStatus.CANCELLED
                    self._pending_orders.remove(order)
                    return True
        return False

    def cancel_exit_orders(self) -> List[Order]:
        """
        Cancel all pending exit orders (for trailing stop support).

        Returns:
            List of cancelled orders
        """
        cancelled_orders = []

        for order in list(self._pending_orders):
            # Exit orders are those with parent_id (child orders)
            if order.is_exit_order() and order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                order.status = OrderStatus.CANCELLED
                cancelled_orders.append(order)
                self._pending_orders.remove(order)

                # Remove from OCO groups
                if order.oco_group_id and order.oco_group_id in self._oco_groups:
                    del self._oco_groups[order.oco_group_id]

        return cancelled_orders

    def update_exit_orders(self, new_tp_order: Optional[Order] = None,
                          new_sl_order: Optional[Order] = None) -> List[str]:
        """
        Update exit orders (cancel old, place new).

        This supports trailing stop and dynamic TP/SL adjustment.

        Args:
            new_tp_order: New take profit order (None to skip)
            new_sl_order: New stop loss order (None to skip)

        Returns:
            List of new order IDs
        """
        # Cancel existing exit orders
        self.cancel_exit_orders()

        # Place new orders
        new_order_ids = []

        if new_tp_order:
            order_id = self.place_order(new_tp_order)
            new_order_ids.append(order_id)

        if new_sl_order:
            order_id = self.place_order(new_sl_order)
            new_order_ids.append(order_id)

        # Create OCO group if both TP and SL provided
        if new_tp_order and new_sl_order:
            oco_group = OrderGroup([new_tp_order, new_sl_order])
            self._oco_groups[oco_group.group_id] = oco_group

        return new_order_ids

    def get_position(self) -> Optional[Position]:
        """Get current position."""
        return self._position

    def get_account(self) -> Account:
        """Get account information."""
        return self.account

    def check_fills(self, bar: Bar) -> List[Order]:
        """
        Check if any pending orders should be filled based on current bar.

        This is called by the BacktestEngine for each bar.

        Args:
            bar: Current market bar

        Returns:
            List of filled orders
        """
        filled_orders = []

        # Check each pending order
        for order in list(self._pending_orders):
            # Skip PENDING orders (waiting for parent to fill)
            if order.status == OrderStatus.PENDING:
                continue

            if self._should_fill(order, bar):
                self._fill_order(order, bar)
                filled_orders.append(order)
                # Only remove if still in pending orders (may have been cleared by _cancel_all_pending_orders)
                if order in self._pending_orders:
                    self._pending_orders.remove(order)
                self._filled_orders.append(order)

        return filled_orders

    def _should_fill(self, order: Order, bar: Bar) -> bool:
        """
        Determine if an order should be filled based on bar data.

        Args:
            order: Order to check
            bar: Current bar

        Returns:
            True if order should fill
        """
        if order.status != OrderStatus.ACTIVE:
            return False

        if order.order_type == OrderType.MARKET:
            return True

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                # Buy LIMIT fills if bar low reaches limit price
                return bar.low <= order.limit_price
            else:  # SELL
                # Sell LIMIT fills if bar high reaches limit price
                return bar.high >= order.limit_price

        elif order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY:
                # Buy STOP fills if bar high reaches stop price
                return bar.high >= order.stop_price
            else:  # SELL
                # Sell STOP fills if bar low reaches stop price
                return bar.low <= order.stop_price

        elif order.order_type == OrderType.STOP_LIMIT:
            # For simplicity, treat as STOP for now
            # TODO: Implement proper STOP_LIMIT logic
            if order.side == OrderSide.BUY:
                return bar.high >= order.stop_price
            else:
                return bar.low <= order.stop_price

        return False

    def _fill_order(self, order: Order, bar: Bar):
        """
        Execute order fill.

        Args:
            order: Order to fill
            bar: Current bar
        """
        # Determine fill price (conservative assumption)
        if order.order_type == OrderType.MARKET:
            fill_price = bar.close  # Assume fill at close
        elif order.order_type == OrderType.LIMIT:
            fill_price = order.limit_price
        elif order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            fill_price = order.stop_price
        else:
            fill_price = bar.close

        # Calculate commission
        commission = fill_price * order.quantity * self.commission_rate

        # Update order
        order.status = OrderStatus.FILLED
        order.filled_time = bar.timestamp
        order.filled_price = fill_price
        order.commission = commission

        # Add commission to account
        self.account.add_commission(commission)

        # Handle position update
        if order.is_entry_order():
            # Entry order
            if order.side == OrderSide.BUY:
                self._open_long_position(order, bar)
            else:  # SELL
                self._open_short_position(order, bar)
        else:
            # Exit order
            self._close_position(order, bar)

        # If this is an entry order, cancel all other pending entry orders (OCO Entry)
        if order.is_entry_order():
            self._cancel_other_entry_orders(order.order_id)
            self._activate_child_orders(order.order_id)

        # Handle OCO cancellation for exit orders
        if order.oco_group_id and order.oco_group_id in self._oco_groups:
            oco_group = self._oco_groups[order.oco_group_id]
            cancelled = oco_group.on_fill(order)
            # Remove cancelled orders from pending
            for cancelled_order in cancelled:
                if cancelled_order in self._pending_orders:
                    self._pending_orders.remove(cancelled_order)

    def _open_long_position(self, order: Order, bar: Bar):
        """
        Open a long position.

        Args:
            order: Filled buy order
            bar: Current bar
        """
        if self._position is not None:
            raise RuntimeError(f"Cannot open LONG position: position already exists {self._position}")

        self._position = Position(
            symbol=order.symbol,
            side=PositionSide.LONG,
            quantity=order.quantity,
            entry_price=order.filled_price,
            entry_time=bar.timestamp,
            current_price=order.filled_price,
            entry_commission=order.commission
        )

    def _open_short_position(self, order: Order, bar: Bar):
        """
        Open a short position.

        Args:
            order: Filled sell order
            bar: Current bar
        """
        if self._position is not None:
            raise RuntimeError(f"Cannot open SHORT position: position already exists {self._position}")

        self._position = Position(
            symbol=order.symbol,
            side=PositionSide.SHORT,
            quantity=order.quantity,
            entry_price=order.filled_price,
            entry_time=bar.timestamp,
            current_price=order.filled_price,
            entry_commission=order.commission
        )

    def _close_position(self, order: Order, bar: Bar):
        """
        Close current position.

        Args:
            order: Filled sell order
            bar: Current bar
        """
        if self._position is None:
            raise RuntimeError(f"Cannot close position: no position exists")

        if self._position.quantity != order.quantity:
            raise RuntimeError(
                f"Position quantity mismatch: "
                f"position={self._position.quantity}, order={order.quantity}"
            )

        # Calculate PnL
        exit_price = order.filled_price
        exit_commission = order.commission

        if self._position.side == PositionSide.LONG:
            pnl = (exit_price - self._position.entry_price) * order.quantity
        else:  # SHORT
            pnl = (self._position.entry_price - exit_price) * order.quantity

        # Subtract commissions
        total_commission = self._position.entry_commission + exit_commission
        pnl -= total_commission

        # Calculate PnL percentage
        pnl_pct = (pnl / (self._position.entry_price * order.quantity)) * 100

        # Create trade record
        trade = Trade(
            symbol=order.symbol,
            side=self._position.side,
            quantity=order.quantity,
            entry_price=self._position.entry_price,
            entry_time=self._position.entry_time,
            exit_price=exit_price,
            exit_time=bar.timestamp,
            entry_commission=self._position.entry_commission,
            exit_commission=exit_commission,
            pnl=pnl,
            pnl_pct=pnl_pct
        )

        # Update account
        self.account.close_trade(trade)

        # Clear position
        self._position = None

        # Cancel all pending orders (OCO siblings)
        self._cancel_all_pending_orders()

    def _cancel_other_entry_orders(self, filled_entry_order_id: str):
        """
        Cancel all other pending entry orders (OCO Entry support).

        When one entry order fills, cancel all other entry orders and their children.

        Args:
            filled_entry_order_id: ID of the entry order that just filled
        """
        cancelled_orders = []

        for order in list(self._pending_orders):
            # Cancel other entry orders (not the one that just filled)
            if order.is_entry_order() and order.order_id != filled_entry_order_id:
                if order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                    order.status = OrderStatus.CANCELLED
                    cancelled_orders.append(order)

                    # Also cancel their child orders
                    if order.order_id in self._child_orders:
                        for child_order in self._child_orders[order.order_id]:
                            if child_order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                                child_order.status = OrderStatus.CANCELLED
                                if child_order in self._pending_orders:
                                    self._pending_orders.remove(child_order)

                        # Clean up child tracking
                        del self._child_orders[order.order_id]

        # Remove cancelled entry orders from pending list
        for cancelled_order in cancelled_orders:
            if cancelled_order in self._pending_orders:
                self._pending_orders.remove(cancelled_order)

    def _activate_child_orders(self, parent_order_id: str):
        """
        Activate child orders after parent order fills.

        Args:
            parent_order_id: ID of filled parent order
        """
        if parent_order_id in self._child_orders:
            child_orders = self._child_orders[parent_order_id]

            # Create OCO group if multiple children
            if len(child_orders) > 1:
                oco_group = OrderGroup(child_orders)
                self._oco_groups[oco_group.group_id] = oco_group

            # Activate all child orders
            for child_order in child_orders:
                child_order.status = OrderStatus.ACTIVE

    def _cancel_all_pending_orders(self):
        """Cancel all pending orders."""
        for order in list(self._pending_orders):
            if order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                order.status = OrderStatus.CANCELLED
        self._pending_orders.clear()
        self._child_orders.clear()
        self._oco_groups.clear()

    def get_pending_orders(self) -> List[Order]:
        """Get all pending orders (for debugging/logging)."""
        return list(self._pending_orders)

    def get_filled_orders(self) -> List[Order]:
        """Get all filled orders (for debugging/logging)."""
        return list(self._filled_orders)

    def __repr__(self) -> str:
        return (f"BacktestBroker(position={self._position is not None}, "
                f"pending_orders={len(self._pending_orders)}, "
                f"filled_orders={len(self._filled_orders)})")
