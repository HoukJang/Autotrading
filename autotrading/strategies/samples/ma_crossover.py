"""
Simple Moving Average Crossover Strategy - Example

This is a basic example strategy demonstrating the backtesting framework.

Strategy Logic:
1. Calculate fast and slow moving averages
2. Entry: When fast MA crosses above slow MA (golden cross)
3. Exit: Set take-profit and stop-loss as OCO orders
"""

from dataclasses import dataclass
from typing import List
import pandas as pd

from ...strategies.base import Strategy, StrategyParams, Bar
from ...backtest.context import Context
from ...backtest.orders import Order, OrderType, OrderSide


@dataclass
class MACrossoverParams(StrategyParams):
    """Parameters for MA Crossover strategy."""
    fast_period: int = 10          # Fast MA period
    slow_period: int = 20          # Slow MA period
    position_size: float = 1.0     # Fixed position size (contracts)
    take_profit_pct: float = 0.02  # Take profit percentage (2%)
    stop_loss_pct: float = 0.01    # Stop loss percentage (1%)
    entry_offset_pct: float = 0.001  # Entry price offset (0.1%)


class MACrossoverStrategy(Strategy):
    """
    Moving Average Crossover Strategy.

    Enters LONG when fast MA crosses above slow MA.
    Uses bracket orders (OCO) for risk management.
    """

    def __init__(self, params: MACrossoverParams):
        super().__init__(params)
        self.params: MACrossoverParams = params  # Type hint for IDE

        # State variables
        self.state = {
            'prev_fast_ma': None,
            'prev_slow_ma': None,
            'last_signal_time': None
        }

    def on_bar(self, bar: Bar, context: Context) -> List[Order]:
        """
        Process each bar and generate trading signals.

        Args:
            bar: Current bar
            context: Execution context

        Returns:
            List of orders (entry + OCO exits)
        """
        # Don't trade if we already have a position
        if context.position:
            return []

        # Get historical data
        lookback = max(self.params.fast_period, self.params.slow_period) + 1
        history = context.get_history(lookback=lookback)

        # Need enough data for MAs
        if len(history) < self.params.slow_period:
            return []

        # Calculate moving averages
        fast_ma = history['close'].rolling(self.params.fast_period).mean().iloc[-1]
        slow_ma = history['close'].rolling(self.params.slow_period).mean().iloc[-1]

        # Check for golden cross (fast MA crosses above slow MA)
        if self.state['prev_fast_ma'] is not None and self.state['prev_slow_ma'] is not None:
            # Golden cross: fast was below, now above
            cross_up = (
                self.state['prev_fast_ma'] <= self.state['prev_slow_ma'] and
                fast_ma > slow_ma
            )

            if cross_up:
                # Generate entry and bracket orders
                orders = self._create_entry_orders(bar, context)

                # Update state
                self.state['last_signal_time'] = bar.timestamp

                # Update MAs for next iteration
                self.state['prev_fast_ma'] = fast_ma
                self.state['prev_slow_ma'] = slow_ma

                return orders

        # Update state for next bar
        self.state['prev_fast_ma'] = fast_ma
        self.state['prev_slow_ma'] = slow_ma

        return []

    def _create_entry_orders(self, bar: Bar, context: Context) -> List[Order]:
        """
        Create entry order with OCO bracket (take-profit + stop-loss).

        Args:
            bar: Current bar
            context: Execution context

        Returns:
            List of orders [entry, take_profit, stop_loss]
        """
        # Entry order (LIMIT slightly below current price)
        entry_price = bar.close * (1 - self.params.entry_offset_pct)

        entry_order = Order(
            symbol="SYMBOL",  # Will be set by context in real usage
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=entry_price
        )

        # Take profit order (OCO 1)
        take_profit_price = entry_price * (1 + self.params.take_profit_pct)

        take_profit_order = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=take_profit_price,
            parent_id=entry_order.order_id
        )

        # Stop loss order (OCO 2)
        stop_loss_price = entry_price * (1 - self.params.stop_loss_pct)

        stop_loss_order = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=stop_loss_price,
            parent_id=entry_order.order_id
        )

        return [entry_order, take_profit_order, stop_loss_order]

    def on_start(self, context: Context):
        """Initialize strategy."""
        print(f"Starting {self.__class__.__name__} with params: {self.params}")

    def on_order_filled(self, order: Order, context: Context):
        """Handle order fill notification."""
        if order.is_entry_order():
            print(f"Entry filled: {order.side.value} @ {order.filled_price:.2f}")
        else:
            print(f"Exit filled: {order.side.value} @ {order.filled_price:.2f}")

    def on_end(self, context: Context):
        """Cleanup and final reporting."""
        print(f"Strategy finished. Account: {context.account}")
