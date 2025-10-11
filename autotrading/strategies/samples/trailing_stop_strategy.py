"""
Trailing Stop Strategy - Example of Dynamic Exit Management

This strategy demonstrates how to use dynamic TP/SL that updates every bar.

Strategy Logic:
1. Simple MA crossover for entry
2. Fixed take profit
3. **Trailing stop loss** that moves up as price increases (for LONG positions)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import pandas as pd

from ...strategies.base import Strategy, StrategyParams, Bar
from ...backtest.context import Context
from ...backtest.orders import Order, OrderType, OrderSide
from ...backtest.position import Position, PositionSide


@dataclass
class TrailingStopParams(StrategyParams):
    """Parameters for Trailing Stop strategy."""
    fast_period: int = 10
    slow_period: int = 20
    position_size: float = 1.0
    take_profit_pct: float = 0.02       # Fixed TP: 2%
    initial_stop_pct: float = 0.01      # Initial SL: 1%
    trailing_stop_pct: float = 0.015    # Trailing SL: 1.5% from current price
    dynamic_exit: bool = True           # Enable dynamic exit


class TrailingStopStrategy(Strategy):
    """
    Strategy with trailing stop loss.

    - Entry: MA crossover
    - Exit: Fixed TP + Trailing SL that follows price
    """

    def __init__(self, params: TrailingStopParams):
        super().__init__(params)
        self.params: TrailingStopParams = params

        # State for MA crossover
        self.state = {
            'prev_fast_ma': None,
            'prev_slow_ma': None,
            'best_price': None  # Track highest price for trailing stop
        }

    def on_bar(self, bar: Bar, context: Context) -> List[Order]:
        """Generate entry orders (exit managed dynamically)."""
        # Don't trade if we already have a position
        if context.position:
            # Track best price for trailing stop
            if context.position.side == PositionSide.LONG:
                if self.state['best_price'] is None:
                    self.state['best_price'] = bar.close
                else:
                    self.state['best_price'] = max(self.state['best_price'], bar.close)
            return []

        # Get historical data
        lookback = max(self.params.fast_period, self.params.slow_period) + 1
        history = context.get_history(lookback=lookback)

        if len(history) < self.params.slow_period:
            return []

        # Calculate MAs
        fast_ma = history['close'].rolling(self.params.fast_period).mean().iloc[-1]
        slow_ma = history['close'].rolling(self.params.slow_period).mean().iloc[-1]

        # Check for golden cross
        if self.state['prev_fast_ma'] is not None:
            cross_up = (
                self.state['prev_fast_ma'] <= self.state['prev_slow_ma'] and
                fast_ma > slow_ma
            )

            if cross_up:
                # Reset best price
                self.state['best_price'] = None

                # Create entry orders
                orders = self._create_entry_orders(bar)

                # Update state
                self.state['prev_fast_ma'] = fast_ma
                self.state['prev_slow_ma'] = slow_ma

                return orders

        # Update state
        self.state['prev_fast_ma'] = fast_ma
        self.state['prev_slow_ma'] = slow_ma

        return []

    def _create_entry_orders(self, bar: Bar) -> List[Order]:
        """
        Create entry order with INITIAL TP/SL.

        Note: SL will be updated dynamically via calculate_dynamic_exits().
        """
        entry_price = bar.close * (1 - 0.001)  # Slightly below current

        entry_order = Order(
            symbol="SYMBOL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=entry_price
        )

        # Fixed take profit
        take_profit = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=self.params.position_size,
            limit_price=entry_price * (1 + self.params.take_profit_pct),
            parent_id=entry_order.order_id
        )

        # Initial stop loss (will be updated dynamically)
        stop_loss = Order(
            symbol="SYMBOL",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=self.params.position_size,
            stop_price=entry_price * (1 - self.params.initial_stop_pct),
            parent_id=entry_order.order_id
        )

        return [entry_order, take_profit, stop_loss]

    def calculate_dynamic_exits(self, position: Position, bar: Bar,
                               context: Context) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Calculate trailing stop loss.

        TP stays fixed, SL trails the price.
        """
        if position.side == PositionSide.LONG:
            # Trailing stop for LONG
            best_price = self.state['best_price'] or bar.close

            # SL trails: use trailing_stop_pct from best price
            trailing_sl_price = best_price * (1 - self.params.trailing_stop_pct)

            # Never go below initial SL
            initial_sl_price = position.entry_price * (1 - self.params.initial_stop_pct)
            new_sl_price = max(trailing_sl_price, initial_sl_price)

            # Create new SL order
            sl_order = Order(
                symbol=position.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.STOP,
                quantity=position.quantity,
                stop_price=new_sl_price,
                parent_id="dynamic_exit"  # Dummy parent
            )

            # Keep TP fixed (return None to not update)
            return (None, sl_order)

        else:
            # SHORT position trailing stop (mirror logic)
            # TODO: Implement if needed
            return (None, None)

    def on_start(self, context: Context):
        """Initialize strategy."""
        print(f"Starting {self.__class__.__name__} with Trailing Stop")
        print(f"Parameters: {self.params}")

    def on_order_filled(self, order: Order, context: Context):
        """Handle order fills."""
        if order.is_entry_order():
            print(f"Entry filled: {order.side.value} @ {order.filled_price:.2f}")
            # Initialize best price
            self.state['best_price'] = order.filled_price
        else:
            print(f"Exit filled: {order.side.value} @ {order.filled_price:.2f}")
            # Reset best price
            self.state['best_price'] = None

    def on_end(self, context: Context):
        """Cleanup."""
        print(f"Strategy finished. Account: {context.account}")
