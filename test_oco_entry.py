"""
Test OCO Entry functionality with Breakout strategy.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.backtest import BacktestEngine
from autotrading.strategies.samples.breakout_oco import BreakoutOCOStrategy, BreakoutOCOParams


def generate_breakout_data(n_bars: int = 500) -> pd.DataFrame:
    """
    Generate sample data with consolidation and breakout patterns.
    """
    np.random.seed(42)

    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    prices = []
    base_price = 100.0

    # Phase 1: Consolidation (200 bars)
    for i in range(200):
        price = base_price + np.random.uniform(-1, 1)
        prices.append(price)

    # Phase 2: Bullish breakout (150 bars)
    for i in range(150):
        base_price += 0.05 + np.random.uniform(0, 0.1)
        price = base_price + np.random.uniform(-0.5, 0.5)
        prices.append(price)

    # Phase 3: Consolidation again (150 bars)
    for i in range(150):
        price = base_price + np.random.uniform(-1, 1)
        prices.append(price)

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
    print("OCO ENTRY BACKTEST TEST")
    print("="*80)
    print()

    # 1. Generate data
    print("1. Generating breakout pattern data...")
    data = generate_breakout_data(n_bars=500)
    print(f"   Generated {len(data)} bars")
    print(f"   Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print()

    # 2. Initialize strategy
    print("2. Initializing Breakout OCO strategy...")
    params = BreakoutOCOParams(
        lookback=20,
        breakout_offset_pct=0.002,
        position_size=1.0,
        take_profit_pct=0.02,
        stop_loss_pct=0.01
    )
    strategy = BreakoutOCOStrategy(params)
    print(f"   Strategy: {strategy}")
    print()

    # 3. Initialize engine
    print("3. Initializing backtest engine...")
    engine = BacktestEngine(
        initial_balance=10000.0,
        commission_rate=0.0004,
        verbose=True
    )
    print()

    # 4. Run backtest
    print("4. Running backtest with OCO Entry...")
    print()
    result = engine.run(strategy, data)
    print()

    # 5. Display results
    print("5. Results:")
    print()
    print(result.summary())
    print()

    # 6. Show trades
    if len(result.account.trades) > 0:
        print("6. Trade Details:")
        print("-" * 80)
        for i, trade in enumerate(result.account.trades):
            print(f"Trade {i+1}: {trade}")
        print("-" * 80)
        print()
    else:
        print("6. No trades executed")
        print()

    print("="*80)
    print("OCO ENTRY TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
