"""
Test Energy Accumulation - Phase 2

Tests the EnergyAccumulator with RegimeDetector integration.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.analysis import RegimeDetector, EnergyAccumulator


def generate_test_data(n_bars: int = 500) -> pd.DataFrame:
    """
    Generate synthetic market data with different regimes.

    Sequence:
    - Bars 0-100: Range (sideways)
    - Bars 100-250: Uptrend (strong momentum)
    - Bars 250-350: Range (consolidation + compression)
    - Bars 350-500: Downtrend (strong momentum)
    """
    np.random.seed(42)

    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    prices = []
    volumes = []
    base_price = 100.0

    for i in range(n_bars):
        if i < 100:
            # Range regime - low momentum
            trend = 0.0
            noise = np.random.normal(0, 0.003)
            volume = np.random.randint(100, 200)  # Low volume
        elif i < 250:
            # Uptrend - high momentum + high volume
            trend = 0.004
            noise = np.random.normal(0, 0.002)
            volume = np.random.randint(200, 400)  # High volume
        elif i < 350:
            # Range regime - compression
            trend = 0.0
            noise = np.random.normal(0, 0.001)  # Lower noise = compression
            volume = np.random.randint(150, 250)  # Building volume
        else:
            # Downtrend - high momentum + high volume
            trend = -0.004
            noise = np.random.normal(0, 0.002)
            volume = np.random.randint(250, 450)  # High volume

        base_price *= (1 + trend + noise)
        prices.append(base_price)
        volumes.append(volume)

    # Generate OHLCV
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

    df = pd.DataFrame(data, index=timestamps)
    return df


def main():
    print("=" * 80)
    print("ENERGY ACCUMULATION TEST - Phase 2")
    print("=" * 80)
    print()

    # 1. Generate test data
    print("1. Generating test data...")
    data = generate_test_data(n_bars=500)
    print(f"   Generated {len(data)} bars")
    print(f"   Expected patterns:")
    print(f"   - Bars 0-100: RANGE (low energy)")
    print(f"   - Bars 100-250: TREND_UP (high energy)")
    print(f"   - Bars 250-350: RANGE (compressed, high energy)")
    print(f"   - Bars 350-500: TREND_DOWN (high energy)")
    print()

    # 2. Create detectors
    print("2. Creating RegimeDetector and EnergyAccumulator...")
    regime_detector = RegimeDetector(
        atr_window=14,
        r2_window=60,
        cvd_window=60,
        bb_window=20,
        snr_window=120,
        confirmation_bars=3,
    )

    energy_accumulator = EnergyAccumulator(
        trend_atr_window=14,
        trend_momentum_window=20,
        trend_volume_window=20,
        trend_momentum_strong_threshold=1.5,
        trend_volume_strong_threshold=1.3,
        range_width_window=60,
        range_compression_window=20,
    )
    print("   Detectors created")
    print()

    # 3. Run detection for sample points
    print("3. Analyzing sample points...")
    print("-" * 80)

    sample_points = [100, 200, 300, 400, 490]

    for idx in sample_points:
        if idx < 120:  # Need minimum data
            continue

        history = data.iloc[:idx+1]

        # Detect regime
        regime_result = regime_detector.detect(history)

        # Calculate energy
        energy_result = energy_accumulator.calculate(history, regime_result)

        print(f"\nBar {idx}:")
        print(f"  Price: ${data['close'].iloc[idx]:.2f}")
        print(f"  Regime: {regime_result.regime.value} (conf: {regime_result.confidence:.2f})")
        print(f"  Energy: {energy_result.expected_move:.2f} points (conf: {energy_result.confidence:.2f})")

        # Show components
        if regime_result.regime in ['TREND_UP', 'TREND_DOWN']:
            print(f"  TREND Components:")
            print(f"    - ATR: {energy_result.components.get('atr', 0):.2f}")
            print(f"    - Momentum factor: {energy_result.components.get('momentum_factor', 0):.2f}")
            print(f"    - Volume factor: {energy_result.components.get('volume_factor', 0):.2f}")
            print(f"    - Strength factor: {energy_result.components.get('strength_factor', 0):.2f}")
        elif regime_result.regime == 'RANGE':
            print(f"  RANGE Components:")
            print(f"    - Range width: {energy_result.components.get('range_width', 0):.2f}")
            print(f"    - Compression ratio: {energy_result.components.get('compression_ratio', 0):.2f}")
            print(f"    - Volume buildup: {energy_result.components.get('volume_buildup', 0):.2f}")

        # Show TP/SL suggestion
        if energy_result.expected_move > 0:
            tp_distance = energy_result.expected_move * 0.7
            sl_distance = tp_distance / 2.0
            print(f"  Suggested TP/SL:")
            print(f"    - TP: {tp_distance:.2f} points")
            print(f"    - SL: {sl_distance:.2f} points")
            print(f"    - Risk/Reward: 1:{tp_distance/sl_distance:.1f}")

    print()
    print("-" * 80)

    # 4. Statistics
    print("\n4. Full Analysis Statistics:")
    print("-" * 80)

    results = []
    min_bars = 120

    for i in range(min_bars, len(data)):
        history = data.iloc[:i+1]
        regime_result = regime_detector.detect(history)
        energy_result = energy_accumulator.calculate(history, regime_result)

        results.append({
            'index': i,
            'regime': regime_result.regime.value,
            'regime_conf': regime_result.confidence,
            'expected_move': energy_result.expected_move,
            'energy_conf': energy_result.confidence,
        })

    results_df = pd.DataFrame(results)

    # Group by regime
    for regime in ['TREND_UP', 'TREND_DOWN', 'RANGE', 'NEUTRAL']:
        regime_data = results_df[results_df['regime'] == regime]

        if len(regime_data) > 0:
            print(f"\n{regime}:")
            print(f"  Count: {len(regime_data)} bars")
            print(f"  Avg expected move: {regime_data['expected_move'].mean():.2f} points")
            print(f"  Avg energy confidence: {regime_data['energy_conf'].mean():.2f}")
            print(f"  Max expected move: {regime_data['expected_move'].max():.2f} points")
            print(f"  Min expected move: {regime_data['expected_move'].min():.2f} points")

    print()
    print("=" * 80)
    print("ENERGY ACCUMULATION TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
