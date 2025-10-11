"""
Test Trailing Stop functionality.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.backtest import BacktestEngine
from autotrading.strategies.samples.trailing_stop_strategy import TrailingStopStrategy, TrailingStopParams


def generate_trending_data(n_bars: int = 1000) -> pd.DataFrame:
    """Generate trending market data to test trailing stop."""
    np.random.seed(42)

    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    prices = []
    base_price = 100.0

    # Create uptrend with pullbacks
    for i in range(n_bars):
        # Uptrend with noise
        trend = 0.005 if i < n_bars * 0.8 else -0.003  # Up then down
        noise = np.random.normal(0, 0.002)

        base_price *= (1 + trend + noise)
        prices.append(base_price)

    # Generate OHLCV
    data = []
    for i, close in enumerate(prices):
        high = close * (1 + abs(np.random.normal(0, 0.002)))
        low = close * (1 - abs(np.random.normal(0, 0.002)))
        open_price = prices[i-1] if i > 0 else 100.0
        volume = np.random.randint(100, 1000)

        data.append({
            'open': open_price,
            'high': max(open_price, high, close),
            'low': min(open_price, low, close),
            'close': close,
            'volume': volume
        })

    df = pd.DataFrame(data, index=timestamps)
    return df


def main():
    print("="*80)
    print("TRAILING STOP BACKTEST TEST")
    print("="*80)
    print()

    # 1. Generate data
    print("1. Generating trending market data...")
    data = generate_trending_data(n_bars=1000)
    print(f"   Generated {len(data)} bars")
    print(f"   Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print()

    # 2. Test Fixed Exit Strategy (baseline)
    print("2. Testing Fixed Exit (baseline)...")
    fixed_params = TrailingStopParams(
        fast_period=10,
        slow_period=20,
        position_size=1.0,
        take_profit_pct=0.02,
        initial_stop_pct=0.01,
        trailing_stop_pct=0.015,
        dynamic_exit=False  # Fixed exits
    )
    fixed_strategy = TrailingStopStrategy(fixed_params)

    engine = BacktestEngine(
        initial_balance=10000.0,
        commission_rate=0.0004,
        verbose=False
    )

    fixed_result = engine.run(fixed_strategy, data)
    print(f"   Fixed Exit Return: {fixed_result.total_return:.2f}%")
    print(f"   Fixed Exit Sharpe: {fixed_result.sharpe_ratio:.2f}")
    print(f"   Fixed Exit Trades: {fixed_result.total_trades}")
    print()

    # 3. Test Trailing Stop Strategy
    print("3. Testing Trailing Stop...")
    trailing_params = TrailingStopParams(
        fast_period=10,
        slow_period=20,
        position_size=1.0,
        take_profit_pct=0.02,
        initial_stop_pct=0.01,
        trailing_stop_pct=0.015,  # 1.5% trailing
        dynamic_exit=True  # Dynamic exits
    )
    trailing_strategy = TrailingStopStrategy(trailing_params)

    engine = BacktestEngine(
        initial_balance=10000.0,
        commission_rate=0.0004,
        verbose=True
    )

    print()
    trailing_result = engine.run(trailing_strategy, data)
    print()

    # 4. Compare results
    print("4. Comparison:")
    print()
    print(f"{'Metric':<20} {'Fixed Exit':<15} {'Trailing Stop':<15} {'Improvement':<15}")
    print("-" * 65)

    metrics = [
        ('Total Return %', fixed_result.total_return, trailing_result.total_return),
        ('Sharpe Ratio', fixed_result.sharpe_ratio, trailing_result.sharpe_ratio),
        ('Max Drawdown %', fixed_result.max_drawdown, trailing_result.max_drawdown),
        ('Win Rate %', fixed_result.win_rate, trailing_result.win_rate),
        ('Total Trades', fixed_result.total_trades, trailing_result.total_trades),
        ('Avg Profit $', fixed_result.avg_profit, trailing_result.avg_profit),
    ]

    for name, fixed_val, trailing_val in metrics:
        improvement = trailing_val - fixed_val
        improvement_str = f"+{improvement:.2f}" if improvement > 0 else f"{improvement:.2f}"
        print(f"{name:<20} {fixed_val:<15.2f} {trailing_val:<15.2f} {improvement_str:<15}")

    print()

    # 5. Show sample trades
    if len(trailing_result.account.trades) > 0:
        print("5. Sample Trailing Stop Trades (first 5):")
        print("-" * 80)
        for i, trade in enumerate(trailing_result.account.trades[:5]):
            print(f"Trade {i+1}: {trade}")
        print("-" * 80)
    print()

    print("="*80)
    print("TRAILING STOP TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
