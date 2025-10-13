"""
Test Trigger System - Phase 3

Tests all 5 triggers with different regime scenarios.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.analysis import (
    RegimeDetector,
    EnergyAccumulator,
    BollingerTrigger,
    MACrossTrigger,
    RangeBreakoutTrigger,
    FibonacciTrigger,
    StdEnvelopeTrigger,
)


def generate_trend_data(n_bars: int = 200, direction: str = 'up') -> pd.DataFrame:
    """
    Generate synthetic trending data.

    Args:
        n_bars: Number of bars
        direction: 'up' or 'down'

    Returns:
        OHLCV DataFrame
    """
    np.random.seed(42)
    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    trend_factor = 0.003 if direction == 'up' else -0.003
    base_price = 100.0

    prices = []
    volumes = []

    for i in range(n_bars):
        noise = np.random.normal(0, 0.001)
        base_price *= (1 + trend_factor + noise)
        prices.append(base_price)
        volumes.append(np.random.randint(200, 400))

    data = []
    for i, close in enumerate(prices):
        high = close * (1 + abs(np.random.normal(0, 0.002)))
        low = close * (1 - abs(np.random.normal(0, 0.002)))
        open_price = prices[i-1] if i > 0 else 100.0

        data.append({
            'open': open_price,
            'high': max(open_price, high, close),
            'low': min(open_price, low, close),
            'close': close,
            'volume': volumes[i]
        })

    return pd.DataFrame(data, index=timestamps)


def generate_range_data(n_bars: int = 200) -> pd.DataFrame:
    """
    Generate synthetic ranging data.

    Returns:
        OHLCV DataFrame
    """
    np.random.seed(42)
    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    base_price = 100.0
    prices = []
    volumes = []

    for i in range(n_bars):
        # Oscillate around base price
        noise = np.random.normal(0, 0.003)
        prices.append(base_price + noise * 10)
        volumes.append(np.random.randint(100, 200))

    data = []
    for i, close in enumerate(prices):
        high = close * (1 + abs(np.random.normal(0, 0.002)))
        low = close * (1 - abs(np.random.normal(0, 0.002)))
        open_price = prices[i-1] if i > 0 else 100.0

        data.append({
            'open': open_price,
            'high': max(open_price, high, close),
            'low': min(open_price, low, close),
            'close': close,
            'volume': volumes[i]
        })

    return pd.DataFrame(data, index=timestamps)


def test_trigger(trigger_name, trigger, data, scenario):
    """
    Test a single trigger on data.

    Args:
        trigger_name: Name of trigger
        trigger: Trigger instance
        data: OHLCV data
        scenario: Scenario description
    """
    print(f"\n{'='*80}")
    print(f"Testing {trigger_name} - {scenario}")
    print(f"{'='*80}")

    # Initialize detectors
    regime_detector = RegimeDetector()
    energy_accumulator = EnergyAccumulator()

    signals = []
    min_bars = 120

    for i in range(min_bars, len(data)):
        history = data.iloc[:i+1]

        # Detect regime and energy
        regime_result = regime_detector.detect(history)
        energy_result = energy_accumulator.calculate(history, regime_result)

        # Check trigger
        signal = trigger.check_entry(history, regime_result, energy_result)

        if signal:
            signals.append({
                'bar': i,
                'price': signal.entry_price,
                'signal': signal.signal,
                'reason': signal.reason,
                'regime': signal.regime,
                'regime_conf': signal.regime_confidence,
                'tp': signal.tp,
                'sl': signal.sl,
                'position_size': signal.position_size,
            })

    # Display results
    print(f"\nTotal signals: {len(signals)}")

    if len(signals) > 0:
        print(f"\nFirst 5 signals:")
        for i, sig in enumerate(signals[:5]):
            print(f"\nSignal {i+1}:")
            print(f"  Bar: {sig['bar']}")
            print(f"  Price: ${sig['price']:.2f}")
            print(f"  Signal: {sig['signal']}")
            print(f"  Reason: {sig['reason']}")
            print(f"  Regime: {sig['regime']} (conf: {sig['regime_conf']:.2f})")
            print(f"  TP: ${sig['tp']:.2f} | SL: ${sig['sl']:.2f}")
            print(f"  Position size: {sig['position_size']}")

        # Statistics
        long_signals = [s for s in signals if s['signal'] == 'LONG']
        short_signals = [s for s in signals if s['signal'] == 'SHORT']

        print(f"\nStatistics:")
        print(f"  LONG signals: {len(long_signals)}")
        print(f"  SHORT signals: {len(short_signals)}")
        print(f"  Avg position size: {np.mean([s['position_size'] for s in signals]):.2f}")
    else:
        print("\nNo signals generated")


def main():
    print("="*80)
    print("TRIGGER SYSTEM TEST - Phase 3")
    print("="*80)

    # Generate test data
    print("\n1. Generating test data...")
    uptrend_data = generate_trend_data(200, 'up')
    downtrend_data = generate_trend_data(200, 'down')
    range_data = generate_range_data(200)
    print("   Data generated")

    # Initialize triggers
    print("\n2. Initializing triggers...")
    triggers = {
        'BollingerTrigger': BollingerTrigger(),
        'MACrossTrigger': MACrossTrigger(),
        'RangeBreakoutTrigger': RangeBreakoutTrigger(),
        'FibonacciTrigger': FibonacciTrigger(),
        'StdEnvelopeTrigger': StdEnvelopeTrigger(),
    }
    print("   Triggers initialized")

    # Test scenarios
    scenarios = [
        ('uptrend_data', uptrend_data, 'Uptrend Market'),
        ('downtrend_data', downtrend_data, 'Downtrend Market'),
        ('range_data', range_data, 'Range-Bound Market'),
    ]

    # Test each trigger on each scenario
    for trigger_name, trigger in triggers.items():
        for data_name, data, scenario in scenarios:
            test_trigger(trigger_name, trigger, data, scenario)

    print(f"\n{'='*80}")
    print("TRIGGER SYSTEM TEST COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
