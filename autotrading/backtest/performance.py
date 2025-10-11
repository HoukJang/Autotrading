"""
Performance tracking and metrics calculation.
"""

from datetime import datetime
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

from .position import Position, Account
from .orders import Order, OrderStatus


class TradeLog:
    """
    Detailed event logging for backtesting.

    Logs all significant events:
    - Order placement
    - Order fills
    - OCO setup
    - Position open/close
    """

    def __init__(self):
        self.events: List[Dict] = []

    def log_order_placed(self, timestamp: datetime, order: Order):
        """Log order placement event."""
        detail = f"{order.side.value} {order.quantity} {order.order_type.value}"
        if order.limit_price:
            detail += f" @ LIMIT {order.limit_price:.2f}"
        if order.stop_price:
            detail += f" @ STOP {order.stop_price:.2f}"

        self.events.append({
            'timestamp': timestamp,
            'event': 'ORDER_PLACED',
            'order_id': order.order_id[:8],
            'detail': detail,
            'parent_id': order.parent_id[:8] if order.parent_id else None
        })

    def log_order_filled(self, timestamp: datetime, order: Order):
        """Log order fill event."""
        detail = (f"{order.side.value} {order.quantity} @ {order.filled_price:.2f} "
                  f"(commission: ${order.commission:.2f})")

        self.events.append({
            'timestamp': timestamp,
            'event': 'ORDER_FILLED',
            'order_id': order.order_id[:8],
            'detail': detail,
            'price': order.filled_price
        })

    def log_oco_setup(self, timestamp: datetime, entry_order: Order,
                      take_profit: Optional[Order], stop_loss: Optional[Order]):
        """Log OCO (bracket) order setup."""
        detail_parts = []
        if take_profit:
            detail_parts.append(f"TP @ {take_profit.limit_price:.2f}")
        if stop_loss:
            detail_parts.append(f"SL @ {stop_loss.stop_price:.2f}")

        detail = " | ".join(detail_parts)

        self.events.append({
            'timestamp': timestamp,
            'event': 'OCO_SETUP',
            'order_id': entry_order.order_id[:8],
            'detail': f"Bracket: {detail}"
        })

    def log_position_opened(self, timestamp: datetime, position: Position):
        """Log position open event."""
        self.events.append({
            'timestamp': timestamp,
            'event': 'POSITION_OPENED',
            'order_id': None,
            'detail': (f"{position.side.value} {position.quantity} {position.symbol} "
                       f"@ {position.entry_price:.2f}")
        })

    def log_position_closed(self, timestamp: datetime, position: Position, pnl: float, pnl_pct: float):
        """Log position close event."""
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        self.events.append({
            'timestamp': timestamp,
            'event': 'POSITION_CLOSED',
            'order_id': None,
            'detail': f"Exit @ {position.current_price:.2f}, PnL: {pnl_str} ({pnl_pct:+.2f}%)"
        })

    def to_dataframe(self) -> pd.DataFrame:
        """Convert log to DataFrame for analysis."""
        if not self.events:
            return pd.DataFrame(columns=['timestamp', 'event', 'order_id', 'detail'])

        df = pd.DataFrame(self.events)
        df = df.set_index('timestamp')
        return df

    def print_log(self, limit: Optional[int] = None):
        """
        Print formatted event log.

        Args:
            limit: Maximum number of events to print (None = all)
        """
        events_to_print = self.events[-limit:] if limit else self.events

        print("\n" + "="*80)
        print("BACKTEST EVENT LOG")
        print("="*80)

        for event in events_to_print:
            timestamp = event['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            event_type = event['event'].ljust(20)
            detail = event['detail']
            print(f"{timestamp} | {event_type} | {detail}")

        print("="*80 + "\n")


class PerformanceTracker:
    """
    Tracks performance metrics during backtesting.
    """

    def __init__(self):
        self.equity_series: List[float] = []
        self.timestamp_series: List[datetime] = []
        self.trade_log = TradeLog()

    def record_bar(self,
                   timestamp: datetime,
                   equity: float,
                   position: Optional[Position],
                   pending_orders: List[Order]):
        """
        Record state for current bar.

        Args:
            timestamp: Current time
            equity: Current account equity
            position: Current position (if any)
            pending_orders: List of pending orders
        """
        self.equity_series.append(equity)
        self.timestamp_series.append(timestamp)

    def calculate_metrics(self, account: Account, data: pd.DataFrame) -> 'BacktestResult':
        """
        Calculate performance metrics from recorded data.

        Args:
            account: Final account state
            data: Original market data (for period calculation)

        Returns:
            BacktestResult object with all metrics
        """
        from .engine import BacktestResult  # Import here to avoid circular import

        # Create equity curve
        equity_curve = pd.Series(self.equity_series, index=self.timestamp_series)

        # Create trade log DataFrame
        trade_log_df = self.trade_log.to_dataframe()

        # Calculate metrics
        metrics = self._calculate_all_metrics(account, equity_curve, data)

        return BacktestResult(
            account=account,
            equity_curve=equity_curve,
            trade_log=trade_log_df,
            metrics=metrics
        )

    def _calculate_all_metrics(self,
                                account: Account,
                                equity_curve: pd.Series,
                                data: pd.DataFrame) -> dict:
        """Calculate all performance metrics."""
        metrics = {}

        # Basic metrics
        metrics['total_return'] = account.total_return
        metrics['total_trades'] = account.total_trades
        metrics['win_rate'] = account.win_rate
        metrics['total_commission'] = account.total_commission

        # Trade statistics
        if account.trades:
            profits = [t.pnl for t in account.trades if t.pnl > 0]
            losses = [t.pnl for t in account.trades if t.pnl < 0]

            metrics['avg_profit'] = np.mean(profits) if profits else 0.0
            metrics['avg_loss'] = np.mean(losses) if losses else 0.0

            gross_profit = sum(profits)
            gross_loss = abs(sum(losses))
            metrics['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else 0.0
        else:
            metrics['avg_profit'] = 0.0
            metrics['avg_loss'] = 0.0
            metrics['profit_factor'] = 0.0

        # Risk metrics
        metrics['max_drawdown'] = self._calculate_max_drawdown(equity_curve)
        metrics['sharpe_ratio'] = self._calculate_sharpe_ratio(equity_curve, data)

        return metrics

    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """
        Calculate maximum drawdown percentage.

        Args:
            equity_curve: Time series of equity

        Returns:
            Maximum drawdown as percentage
        """
        if len(equity_curve) == 0:
            return 0.0

        # Calculate running maximum
        running_max = equity_curve.expanding().max()

        # Calculate drawdown at each point
        drawdown = (equity_curve - running_max) / running_max * 100

        # Return maximum (most negative) drawdown
        max_dd = abs(drawdown.min())

        return max_dd if not np.isnan(max_dd) else 0.0

    def _calculate_sharpe_ratio(self, equity_curve: pd.Series,
                                 data: pd.DataFrame, risk_free_rate: float = 0.0) -> float:
        """
        Calculate Sharpe ratio.

        Args:
            equity_curve: Time series of equity
            data: Market data (for period estimation)
            risk_free_rate: Annual risk-free rate (default 0%)

        Returns:
            Sharpe ratio
        """
        if len(equity_curve) < 2:
            return 0.0

        # Calculate returns
        returns = equity_curve.pct_change().dropna()

        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        # Estimate periods per year (assume 1-minute bars)
        # Trading days per year: 252
        # Trading hours per day: 6.5 (typical)
        # Minutes per hour: 60
        # periods_per_year = 252 * 6.5 * 60 = 98,280

        # For simplicity, use the data timespan to estimate
        time_diff = (equity_curve.index[-1] - equity_curve.index[0]).days
        if time_diff == 0:
            periods_per_year = 252 * 6.5 * 60  # Default assumption
        else:
            periods_per_year = len(equity_curve) / time_diff * 365

        # Annualized return and volatility
        mean_return = returns.mean() * periods_per_year
        std_return = returns.std() * np.sqrt(periods_per_year)

        # Sharpe ratio
        sharpe = (mean_return - risk_free_rate) / std_return

        return sharpe if not np.isnan(sharpe) else 0.0

    def __repr__(self) -> str:
        return f"PerformanceTracker(bars={len(self.equity_series)}, events={len(self.trade_log.events)})"
