"""
Breakout Strategy with OCO Entry - Example

This strategy demonstrates OCO (One-Cancels-Other) Entry orders.

Strategy Logic:
1. Identify support and resistance levels
2. Place TWO entry orders simultaneously:
   - STOP BUY above resistance (bullish breakout)
   - STOP SELL below support (bearish breakout)
3. Whichever triggers first, the other is automatically cancelled
4. Each entry has its own TP/SL bracket

This is useful when direction is uncertain but expecting a breakout.
"""

from dataclasses import dataclass
from typing import List
import pandas as pd
import numpy as np

from ...strategies.base import Strategy, StrategyParams, Bar
from ...backtest.context import Context
from ...backtest.orders import Order, OrderType, OrderSide


@dataclass
class BreakoutOCOParams(StrategyParams):
    """Parameters for Breakout OCO strategy."""
    lookback: int = 20                  # Lookback period for support/resistance
    breakout_offset_pct: float = 0.002  # Breakout trigger offset (0.2%)
    position_size: float = 1.0          # Position size
    take_profit_pct: float = 0.02       # Take profit (2%)
    stop_loss_pct: float = 0.01         # Stop loss (1%)


class BreakoutOCOStrategy(Strategy):
    """
    Breakout strategy with OCO Entry orders.

    Places both LONG and SHORT entry orders simultaneously.
    Whichever breaks out first, the opposite is cancelled.
    """

    def __init__(self, params: BreakoutOCOParams):
        super().__init__(params)
        self.params: BreakoutOCOParams = params

    def on_bar(self, bar: Bar, context: Context) -> List[Order]:
        """
        Process each bar and generate OCO entry orders.

        Args:
            bar: Current bar
            context: Execution context

        Returns:
            List of orders (2 entries + 2 brackets = 6 orders total)
        """
        # Don't trade if we already have a position
        if context.position:
            return []

        # Get historical data
        history = context.get_history(lookback=self.params.lookback + 1)

        # Need enough data
        if len(history) < self.params.lookback:
            return []

        # Calculate support and resistance
        resistance = history['high'].max()
        support = history['low'].min()

        # Current price
        current_price = bar.close

        # Only place orders if price is between support and resistance
        if current_price <= support or current_price >= resistance:
            return []

        # Create OCO entry orders (both LONG and SHORT)
        orders = self._create_oco_entry_orders(bar, resistance, support)

        return orders

    def _create_oco_entry_orders(self, bar: Bar, resistance: float, support: float) -> List[Order]:
        """
        Create OCO entry orders with brackets.

        Args:
            bar: Current bar
            resistance: Resistance level
            support: Support level

        Returns:
            List of 6 orders:
            - LONG entry (STOP BUY) + TP + SL
            - SHORT entry (STOP SELL) + TP + SL
        """
        # LONG Entry: STOP BUY above resistance
        long_entry_price = resistance * (1 + self.params.breakout_offset_pct)

        long_entry = Order(
            symbol="SYMBOL",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=long_entry_price
        )

        # LONG Take Profit
        long_tp = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=long_entry_price * (1 + self.params.take_profit_pct),
            parent_id=long_entry.order_id
        )

        # LONG Stop Loss
        long_sl = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=long_entry_price * (1 - self.params.stop_loss_pct),
            parent_id=long_entry.order_id
        )

        # SHORT Entry: STOP SELL below support
        short_entry_price = support * (1 - self.params.breakout_offset_pct)

        short_entry = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=short_entry_price
        )

        # SHORT Take Profit
        short_tp = Order(
            symbol="SYMBOL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=short_entry_price * (1 - self.params.take_profit_pct),
            parent_id=short_entry.order_id
        )

        # SHORT Stop Loss
        short_sl = Order(
            symbol="SYMBOL",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=short_entry_price * (1 + self.params.stop_loss_pct),
            parent_id=short_entry.order_id
        )

        # Return all 6 orders (OCO Entry + Brackets)
        # When LONG entry fills → SHORT entry + children cancelled
        # When SHORT entry fills → LONG entry + children cancelled
        return [
            long_entry, long_tp, long_sl,
            short_entry, short_tp, short_sl
        ]

    def on_start(self, context: Context):
        """Initialize strategy."""
        print(f"Starting {self.__class__.__name__} with OCO Entry support")
        print(f"Parameters: {self.params}")

    def on_order_filled(self, order: Order, context: Context):
        """Handle order fill notification."""
        if order.is_entry_order():
            print(f"Entry filled: {order.side.value} @ {order.filled_price:.2f}")
        else:
            print(f"Exit filled: {order.side.value} @ {order.filled_price:.2f}")

    def on_end(self, context: Context):
        """Cleanup."""
        print(f"Strategy finished. Account: {context.account}")
