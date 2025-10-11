"""
Order models and OCO (One-Cancels-Other) group management for backtesting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
from decimal import Decimal
import uuid


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"       # Order placed, waiting for trigger
    ACTIVE = "ACTIVE"         # Order active and waiting for fill
    FILLED = "FILLED"         # Order executed
    CANCELLED = "CANCELLED"   # Order cancelled
    REJECTED = "REJECTED"     # Order rejected


@dataclass
class Order:
    """
    Represents a trading order with support for LIMIT and STOP orders.

    Attributes:
        symbol: Trading symbol (e.g., "ES", "NQ")
        side: BUY or SELL
        order_type: MARKET, LIMIT, STOP, or STOP_LIMIT
        quantity: Number of contracts/shares
        limit_price: Price for LIMIT orders (optional)
        stop_price: Trigger price for STOP orders (optional)
        parent_id: Parent order ID for OCO relationships (optional)
        oco_group_id: OCO group identifier (optional)
        order_id: Unique order identifier (auto-generated)
        status: Current order status
        created_time: Order creation timestamp
        filled_time: Order fill timestamp (optional)
        filled_price: Actual fill price (optional)
        commission: Commission paid (optional)
    """
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    parent_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    created_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    filled_price: Optional[float] = None
    commission: Optional[float] = None

    def __post_init__(self):
        """Validate order parameters."""
        if self.created_time is None:
            self.created_time = datetime.now()

        # Validation
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if self.limit_price is None:
                raise ValueError(f"{self.order_type.value} order requires limit_price")

        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if self.stop_price is None:
                raise ValueError(f"{self.order_type.value} order requires stop_price")

        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")

    def is_entry_order(self) -> bool:
        """Check if this is an entry order (no parent)."""
        return self.parent_id is None

    def is_exit_order(self) -> bool:
        """Check if this is an exit order (has parent)."""
        return self.parent_id is not None

    def __repr__(self) -> str:
        """String representation of the order."""
        price_info = []
        if self.limit_price:
            price_info.append(f"limit={self.limit_price:.2f}")
        if self.stop_price:
            price_info.append(f"stop={self.stop_price:.2f}")
        price_str = ", ".join(price_info) if price_info else ""

        return (f"Order({self.order_id[:8]}, {self.side.value} {self.quantity} "
                f"{self.symbol} {self.order_type.value}, {price_str}, {self.status.value})")


class OrderGroup:
    """
    OCO (One-Cancels-Other) order group.

    When one order in the group is filled, all other orders are automatically cancelled.
    Typically used for take-profit and stop-loss orders.
    """

    def __init__(self, orders: List[Order], group_id: Optional[str] = None):
        """
        Initialize OCO order group.

        Args:
            orders: List of orders in the OCO group
            group_id: Optional group identifier (auto-generated if not provided)
        """
        self.group_id = group_id or str(uuid.uuid4())
        self.orders = orders

        # Set group_id for all orders
        for order in self.orders:
            order.oco_group_id = self.group_id

    def on_fill(self, filled_order: Order) -> List[Order]:
        """
        Handle order fill event - cancel all other orders in the group.

        Args:
            filled_order: The order that was filled

        Returns:
            List of cancelled orders
        """
        cancelled_orders = []
        for order in self.orders:
            if order.order_id != filled_order.order_id:
                if order.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]:
                    order.status = OrderStatus.CANCELLED
                    cancelled_orders.append(order)

        return cancelled_orders

    def get_active_orders(self) -> List[Order]:
        """Get all active orders in the group."""
        return [o for o in self.orders if o.status in [OrderStatus.PENDING, OrderStatus.ACTIVE]]

    def __repr__(self) -> str:
        """String representation of the OCO group."""
        active_count = len(self.get_active_orders())
        return f"OrderGroup({self.group_id[:8]}, {active_count}/{len(self.orders)} active)"
