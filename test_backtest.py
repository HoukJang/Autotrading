"""
Test script for backtesting framework.

This script demonstrates how to use the backtesting engine with a simple MA crossover strategy.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import backtesting framework
from autotrading.backtest import BacktestEngine
from autotrading.strategies.samples.ma_crossover import MACrossoverStrategy, MACrossoverParams


def generate_sample_data(n_bars: int = 1000, start_price: float = 100.0) -> pd.DataFrame:
    """
    Generate sample 1-minute OHLCV data for testing.

    Args:
        n_bars: Number of bars to generate
        start_price: Starting price

    Returns:
        DataFrame with OHLCV columns and datetime index
    """
    # Generate timestamps (1-minute bars)
    start_time = datetime(2024, 1, 1, 9, 30)  # 9:30 AM
    timestamps = [start_time + timedelta(minutes=i) for i in range(n_bars)]

    # Generate random walk price data
    np.random.seed(42)
    returns = np.random.normal(0.0001, 0.002, n_bars)  # Small returns with volatility
    prices = start_price * (1 + returns).cumprod()

    # Generate OHLCV
    data = []
    for i, price in enumerate(prices):
        # Add some randomness to OHLC
        high = price * (1 + abs(np.random.normal(0, 0.001)))
        low = price * (1 - abs(np.random.normal(0, 0.001)))
        open_price = prices[i-1] if i > 0 else start_price
        close = price
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
    """Run backtest demonstration."""
    print("="*80)
    print("BACKTESTING FRAMEWORK TEST")
    print("="*80)
    print()

    # 1. Generate sample data
    print("1. Generating sample data...")
    data = generate_sample_data(n_bars=1000, start_price=100.0)
    print(f"   Generated {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    print(f"   Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print()

    # 2. Initialize strategy
    print("2. Initializing strategy...")
    params = MACrossoverParams(
        fast_period=10,
        slow_period=20,
        position_size=1.0,
        take_profit_pct=0.02,  # 2% profit target
        stop_loss_pct=0.01     # 1% stop loss
    )
    strategy = MACrossoverStrategy(params)
    print(f"   Strategy: {strategy}")
    print()

    # 3. Initialize backtest engine
    print("3. Initializing backtest engine...")
    engine = BacktestEngine(
        initial_balance=10000.0,
        commission_rate=0.0004,  # 0.04% commission
        verbose=True
    )
    print(f"   Initial balance: $10,000")
    print(f"   Commission rate: 0.04%")
    print()

    # 4. Run backtest
    print("4. Running backtest...")
    print()
    result = engine.run(strategy, data)
    print()

    # 5. Display results
    print("5. Results:")
    print()
    print(result.summary())
    print()

    # 6. Show sample trades
    if len(result.account.trades) > 0:
        print("6. Sample Trades (first 5):")
        print("-" * 80)
        for i, trade in enumerate(result.account.trades[:5]):
            print(f"Trade {i+1}: {trade}")
        print("-" * 80)
        print()

    # 7. Show trade log (last 20 events)
    print("7. Event Log (last 20 events):")
    result.trade_log.tail(20) if len(result.trade_log) > 0 else print("No events logged")
    print()

    # 8. Save results (optional)
    # result.equity_curve.to_csv('equity_curve.csv')
    # result.trade_log.to_csv('trade_log.csv')

    print("="*80)
    print("BACKTEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
