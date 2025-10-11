"""
Backtesting engine - orchestrates the simulation loop.
"""

from datetime import datetime
from typing import Optional
import pandas as pd
from tqdm import tqdm

from .broker import BacktestBroker
from .context import BacktestContext
from .position import Account
from .performance import PerformanceTracker
from ..strategies.base import Strategy, Bar


class BacktestEngine:
    """
    Backtesting engine that simulates strategy execution over historical data.

    The engine:
    1. Iterates through historical bars in chronological order
    2. Checks for order fills
    3. Calls strategy.on_bar() for each bar
    4. Places new orders
    5. Tracks performance metrics

    Example:
        # Initialize
        account = Account(initial_balance=10000, balance=10000)
        engine = BacktestEngine(
            initial_balance=10000,
            commission_rate=0.0004
        )

        # Run backtest
        result = engine.run(strategy, data)

        # Analyze results
        print(f"Total Return: {result.total_return:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown:.2f}%")
    """

    def __init__(self,
                 initial_balance: float = 10000.0,
                 commission_rate: float = 0.0004,
                 verbose: bool = True):
        """
        Initialize backtesting engine.

        Args:
            initial_balance: Starting account balance
            commission_rate: Commission as a fraction (e.g., 0.0004 = 0.04%)
            verbose: Show progress bar
        """
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.verbose = verbose

    def run(self, strategy: Strategy, data: pd.DataFrame) -> 'BacktestResult':
        """
        Run backtest simulation.

        Args:
            strategy: Trading strategy to backtest
            data: Historical data (DataFrame with OHLCV columns and datetime index)

        Returns:
            BacktestResult with performance metrics and trade log

        Example:
            data = pd.DataFrame({
                'open': [...],
                'high': [...],
                'low': [...],
                'close': [...],
                'volume': [...]
            }, index=pd.date_range('2024-01-01', periods=1000, freq='1min'))

            result = engine.run(my_strategy, data)
        """
        # Validate data
        self._validate_data(data)

        # Initialize components
        account = Account(initial_balance=self.initial_balance, balance=self.initial_balance)
        broker = BacktestBroker(account, self.commission_rate)
        context = BacktestContext(data, account)
        tracker = PerformanceTracker()

        # Initialize strategy
        strategy.on_start(context)

        # Simulation loop
        iterator = tqdm(range(len(data)), desc="Backtesting") if self.verbose else range(len(data))

        for idx in iterator:
            # Get current bar
            bar_series = data.iloc[idx]
            bar = Bar.from_series(bar_series)

            # 1. Check for order fills (from previous orders)
            filled_orders = broker.check_fills(bar)

            # Update context with latest position after fills
            context.update(idx, broker.get_position())

            # Notify strategy of fills
            for order in filled_orders:
                strategy.on_order_filled(order, context)

            # 2. Call strategy to generate new orders
            new_orders = strategy.on_bar(bar, context)

            # 3. Place new orders
            if new_orders:
                for order in new_orders:
                    broker.place_order(order)

            # 4. Track performance
            tracker.record_bar(
                timestamp=bar.timestamp,
                equity=account.equity,
                position=broker.get_position(),
                pending_orders=broker.get_pending_orders()
            )

        # Finalize strategy
        strategy.on_end(context)

        # Calculate final metrics
        result = tracker.calculate_metrics(account, data)

        return result

    def _validate_data(self, data: pd.DataFrame):
        """
        Validate input data format.

        Args:
            data: Data to validate

        Raises:
            ValueError: If data format is invalid
        """
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in data.columns]

        if missing_columns:
            raise ValueError(f"Data missing required columns: {missing_columns}")

        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data index must be DatetimeIndex")

        if len(data) == 0:
            raise ValueError("Data is empty")


class BacktestResult:
    """
    Results from a backtest run.

    Contains performance metrics and detailed trade log.
    """

    def __init__(self,
                 account: Account,
                 equity_curve: pd.Series,
                 trade_log: pd.DataFrame,
                 metrics: dict):
        """
        Initialize backtest result.

        Args:
            account: Final account state
            equity_curve: Time series of account equity
            trade_log: DataFrame with detailed trade information
            metrics: Dictionary of performance metrics
        """
        self.account = account
        self.equity_curve = equity_curve
        self.trade_log = trade_log
        self.metrics = metrics

    @property
    def total_return(self) -> float:
        """Total return percentage."""
        return self.metrics.get('total_return', 0.0)

    @property
    def sharpe_ratio(self) -> float:
        """Sharpe ratio."""
        return self.metrics.get('sharpe_ratio', 0.0)

    @property
    def max_drawdown(self) -> float:
        """Maximum drawdown percentage."""
        return self.metrics.get('max_drawdown', 0.0)

    @property
    def win_rate(self) -> float:
        """Win rate percentage."""
        return self.metrics.get('win_rate', 0.0)

    @property
    def total_trades(self) -> int:
        """Total number of trades."""
        return self.metrics.get('total_trades', 0)

    @property
    def avg_profit(self) -> float:
        """Average profit per trade."""
        return self.metrics.get('avg_profit', 0.0)

    @property
    def avg_loss(self) -> float:
        """Average loss per trade."""
        return self.metrics.get('avg_loss', 0.0)

    @property
    def profit_factor(self) -> float:
        """Profit factor (gross profit / gross loss)."""
        return self.metrics.get('profit_factor', 0.0)

    def summary(self) -> str:
        """
        Generate a summary report.

        Returns:
            Formatted string with key metrics
        """
        return f"""
================================================================
                    BACKTEST RESULTS
================================================================
Initial Balance:     ${self.account.initial_balance:>10,.2f}
Final Balance:       ${self.account.balance:>10,.2f}
Final Equity:        ${self.account.equity:>10,.2f}
Total Return:        {self.total_return:>10.2f}%
----------------------------------------------------------------
Sharpe Ratio:        {self.sharpe_ratio:>10.2f}
Max Drawdown:        {self.max_drawdown:>10.2f}%
Profit Factor:       {self.profit_factor:>10.2f}
----------------------------------------------------------------
Total Trades:        {self.total_trades:>10}
Winning Trades:      {self.account.winning_trades:>10}
Losing Trades:       {self.account.losing_trades:>10}
Win Rate:            {self.win_rate:>10.2f}%
----------------------------------------------------------------
Avg Profit:          ${self.avg_profit:>10,.2f}
Avg Loss:            ${self.avg_loss:>10,.2f}
Total Commission:    ${self.account.total_commission:>10,.2f}
================================================================
        """.strip()

    def __repr__(self) -> str:
        return (f"BacktestResult(return={self.total_return:.2f}%, "
                f"sharpe={self.sharpe_ratio:.2f}, "
                f"trades={self.total_trades})")
