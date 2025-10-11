"""
Base strategy class and parameter definitions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Any, Dict
import pandas as pd

# Forward declaration to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..backtest.context import Context
    from ..backtest.orders import Order
    from ..backtest.position import Position


@dataclass
class StrategyParams:
    """
    Base class for strategy parameters.

    Subclass this to define strategy-specific parameters.

    Example:
        @dataclass
        class MyStrategyParams(StrategyParams):
            lookback: int = 20
            entry_threshold: float = 0.02
            take_profit_pct: float = 0.02
            stop_loss_pct: float = 0.01
            dynamic_exit: bool = False  # Enable trailing stop
    """
    # Exit management mode
    dynamic_exit: bool = False  # If True, strategy updates TP/SL every bar


class Bar:
    """
    Represents a single bar (candle) of market data.
    """
    def __init__(self, timestamp: datetime, open: float, high: float,
                 low: float, close: float, volume: float):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume

    @classmethod
    def from_series(cls, series: pd.Series) -> 'Bar':
        """Create Bar from pandas Series."""
        return cls(
            timestamp=series.name if isinstance(series.name, datetime) else datetime.now(),
            open=series['open'],
            high=series['high'],
            low=series['low'],
            close=series['close'],
            volume=series['volume']
        )

    def __repr__(self) -> str:
        return (f"Bar({self.timestamp}, O={self.open:.2f}, H={self.high:.2f}, "
                f"L={self.low:.2f}, C={self.close:.2f}, V={self.volume:.0f})")


class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    Strategies must implement the on_bar() method which is called for each bar.
    The strategy can maintain internal state and return orders based on market conditions.

    Usage:
        class MyStrategy(Strategy):
            def __init__(self, params: MyStrategyParams):
                super().__init__(params)
                self.state = {'position_count': 0}

            def on_bar(self, bar: Bar, context: Context) -> List[Order]:
                # Strategy logic here
                if entry_signal:
                    return [entry_order, take_profit_order, stop_loss_order]
                return []
    """

    def __init__(self, params: StrategyParams):
        """
        Initialize strategy with parameters.

        Args:
            params: Strategy parameters (dataclass)
        """
        self.params = params
        self.state: Dict[str, Any] = {}

    @abstractmethod
    def on_bar(self, bar: Bar, context: 'Context') -> List['Order']:
        """
        Called for each bar of market data.

        This is the main entry point for strategy logic. Implement your
        trading logic here and return a list of orders to place.

        Args:
            bar: Current market bar (OHLCV + timestamp)
            context: Execution context providing access to:
                - history: Historical market data (PIT guaranteed)
                - position: Current position (if any)
                - account: Account information
                - current_time: Current simulation time

        Returns:
            List of orders to place (can include entry + OCO exit orders)

        Example:
            def on_bar(self, bar, context):
                # Check if we have a position
                if context.position:
                    return []  # Already in position

                # Get historical data
                history = context.get_history(lookback=20)

                # Calculate signal
                if self._entry_signal(history, bar):
                    # Entry order
                    entry = Order(
                        symbol=bar.symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        quantity=self._calculate_size(context.account.balance),
                        limit_price=bar.close * 0.999
                    )

                    # Take profit (OCO 1)
                    take_profit = Order(
                        symbol=bar.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=entry.quantity,
                        limit_price=entry.limit_price * 1.02,
                        parent_id=entry.order_id
                    )

                    # Stop loss (OCO 2)
                    stop_loss = Order(
                        symbol=bar.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=entry.quantity,
                        stop_price=entry.limit_price * 0.99,
                        parent_id=entry.order_id
                    )

                    return [entry, take_profit, stop_loss]

                return []
        """
        pass

    def on_start(self, context: 'Context'):
        """
        Called once at the start of backtesting or live trading.

        Use this to initialize strategy state, load external data, etc.

        Args:
            context: Execution context
        """
        pass

    def on_order_filled(self, order: 'Order', context: 'Context'):
        """
        Called when an order is filled.

        Optional callback for strategies that need to react to order fills.

        Args:
            order: The filled order
            context: Execution context
        """
        pass

    def on_position_closed(self, position: 'Position', pnl: float, context: 'Context'):
        """
        Called when a position is closed.

        Optional callback for strategies that need to track trade outcomes.

        Args:
            position: The closed position
            pnl: Profit/loss from the trade
            context: Execution context
        """
        pass

    def on_end(self, context: 'Context'):
        """
        Called at the end of backtesting or when live trading stops.

        Use this for cleanup, final calculations, etc.

        Args:
            context: Execution context
        """
        pass

    def should_update_exits(self, position: 'Position', context: 'Context') -> bool:
        """
        Check if exit orders should be updated (for dynamic exit management).

        Override this method to implement custom update conditions.
        Default: Update every bar if dynamic_exit is enabled.

        Args:
            position: Current position
            context: Execution context

        Returns:
            True if exits should be updated

        Example:
            def should_update_exits(self, position, context):
                # Only update if price moved significantly
                price_change = abs(context.bar.close - position.entry_price)
                return price_change > self.params.update_threshold
        """
        return self.params.dynamic_exit

    def calculate_dynamic_exits(self, position: 'Position', bar: 'Bar',
                               context: 'Context') -> tuple[Optional['Order'], Optional['Order']]:
        """
        Calculate new TP/SL orders for dynamic exit management.

        Override this method to implement custom dynamic exit logic.

        Args:
            position: Current position
            bar: Current bar
            context: Execution context

        Returns:
            Tuple of (take_profit_order, stop_loss_order)
            Either can be None to skip that order.

        Example:
            def calculate_dynamic_exits(self, position, bar, context):
                # Trailing stop: move SL up as price increases
                current_price = bar.close
                new_sl_price = max(
                    position.entry_price * 0.99,  # Initial SL
                    current_price * 0.98           # Trailing SL
                )

                sl_order = Order(
                    symbol=position.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.STOP,
                    quantity=position.quantity,
                    stop_price=new_sl_price,
                    parent_id="virtual_parent"  # Dummy parent
                )

                return (None, sl_order)  # Only update SL
        """
        raise NotImplementedError(
            "Strategies with dynamic_exit=True must implement calculate_dynamic_exits()"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.params})"
