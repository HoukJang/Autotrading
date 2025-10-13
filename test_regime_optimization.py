"""
Test Regime Weight Optimization
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.analysis import RegimeWeightOptimizer, RegimeDetector


def generate_labeled_data(n_bars: int = 500) -> tuple[pd.DataFrame, pd.Series]:
    """
    Generate synthetic market data with known regime labels.

    Returns:
        (data, true_regimes)
    """
    np.random.seed(42)

    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    prices = []
    regimes = []
    base_price = 100.0

    for i in range(n_bars):
        if i < 100:
            # Range regime
            regime = 'RANGE'
            trend = 0.0
            noise = np.random.normal(0, 0.003)
        elif i < 250:
            # Uptrend
            regime = 'TREND_UP'
            trend = 0.004
            noise = np.random.normal(0, 0.002)
        elif i < 350:
            # Range regime
            regime = 'RANGE'
            trend = 0.0
            noise = np.random.normal(0, 0.003)
        else:
            # Downtrend
            regime = 'TREND_DOWN'
            trend = -0.004
            noise = np.random.normal(0, 0.002)

        base_price *= (1 + trend + noise)
        prices.append(base_price)
        regimes.append(regime)

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
    regime_series = pd.Series(regimes, index=timestamps)

    return df, regime_series


def main():
    print("=" * 80)
    print("REGIME WEIGHT OPTIMIZATION TEST")
    print("=" * 80)
    print()

    # 1. Generate labeled data
    print("1. Generating labeled training data...")
    train_data, true_regimes = generate_labeled_data(n_bars=500)
    print(f"   Generated {len(train_data)} bars")
    print(f"   True regime distribution:")
    for regime, count in true_regimes.value_counts().items():
        pct = count / len(true_regimes) * 100
        print(f"     {regime:<12} {count:>3} bars ({pct:>5.1f}%)")
    print()

    # 2. Test with default weights (baseline)
    print("2. Baseline performance with default weights...")
    detector = RegimeDetector(
        atr_window=14,
        atr_lookback=20,
        r2_window=60,
        cvd_window=60,
        bb_window=20,
        snr_window=120,
        confirmation_bars=3,
        # Default weights
        weight_atr=0.2,
        weight_r2=0.25,
        weight_cvd=0.25,
        weight_bb=0.1,
        weight_snr=0.2,
    )

    detector.reset()
    predictions = []
    min_bars = 120

    for i in range(min_bars, len(train_data)):
        history = train_data.iloc[:i+1]
        result = detector.detect(history)
        predictions.append(result.regime.value)

    true_aligned = true_regimes.iloc[min_bars:].values
    baseline_accuracy = (np.array(predictions) == true_aligned).mean()
    print(f"   Baseline accuracy: {baseline_accuracy:.2%}")
    print()

    # 3. Optimize weights
    print("3. Optimizing weights using gradient-based method...")
    optimizer = RegimeWeightOptimizer(
        detector_params={
            'atr_window': 14,
            'atr_lookback': 20,
            'r2_window': 60,
            'cvd_window': 60,
            'bb_window': 20,
            'snr_window': 120,
            'confirmation_bars': 3,
        },
        method='gradient',  # Faster method
    )

    result = optimizer.optimize(
        train_data=train_data,
        true_regimes=true_regimes,
        weight_bounds={
            'weight_atr': (0.0, 0.5),
            'weight_r2': (0.0, 0.5),
            'weight_cvd': (0.0, 0.5),
            'weight_bb': (0.0, 0.3),
            'weight_snr': (0.0, 0.5),
        },
    )

    print(f"   Optimization complete!")
    print()

    # 4. Show results
    print("4. Optimization Results:")
    print("-" * 80)
    print(f"   Optimized accuracy: {result.accuracy:.2%}")
    print(f"   Improvement: {(result.accuracy - baseline_accuracy):.2%}")
    print()
    print(f"   Best weights:")
    total_weight = sum(result.best_weights.values())
    for name, weight in sorted(result.best_weights.items()):
        print(f"     {name:<15} {weight:.4f} ({weight/total_weight*100:.1f}%)")
    print(f"     {'TOTAL':<15} {total_weight:.4f}")
    print()

    # 5. Compare regime distributions
    print("5. Predicted vs True Regime Distribution:")
    print("-" * 80)
    print(f"   {'Regime':<12} {'True':<8} {'Baseline':<10} {'Optimized':<10}")
    print("-" * 80)

    baseline_predictions = predictions
    baseline_counts = pd.Series(baseline_predictions).value_counts().to_dict()

    optimized_counts = result.regime_counts

    all_regimes = set(list(true_regimes.value_counts().index) +
                     list(baseline_counts.keys()) +
                     list(optimized_counts.keys()))

    for regime in sorted(all_regimes):
        true_count = true_regimes.value_counts().get(regime, 0)
        baseline_count = baseline_counts.get(regime, 0)
        optimized_count = optimized_counts.get(regime, 0)
        print(f"   {regime:<12} {true_count:<8} {baseline_count:<10} {optimized_count:<10}")

    print()

    # 6. Show optimization history (top 5)
    print("6. Optimization History (top 5 iterations):")
    print("-" * 80)
    sorted_history = sorted(result.optimization_history, key=lambda x: x['score'], reverse=True)[:5]

    for i, entry in enumerate(sorted_history, 1):
        print(f"\n   Iteration {i}: Score = {entry['score']:.4f}")
        for name, weight in sorted(entry['weights'].items()):
            print(f"     {name:<15} {weight:.4f}")

    print()
    print("=" * 80)
    print("WEIGHT OPTIMIZATION TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
