"""
Test Regime Detection - Phase 1 (ATR + R²)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.analysis import RegimeDetector, RegimeType


def generate_test_data(n_bars: int = 500) -> pd.DataFrame:
    """
    Generate synthetic market data with different regimes.

    Sequence:
    - Bars 0-100: Range (sideways)
    - Bars 100-250: Uptrend (strong trend)
    - Bars 250-350: Range (consolidation)
    - Bars 350-500: Downtrend (strong trend)
    """
    np.random.seed(42)

    timestamps = [datetime(2024, 1, 1, 9, 30) + timedelta(minutes=i) for i in range(n_bars)]

    prices = []
    base_price = 100.0

    for i in range(n_bars):
        if i < 100:
            # Range regime
            trend = 0.0
            noise = np.random.normal(0, 0.003)
        elif i < 250:
            # Uptrend
            trend = 0.004
            noise = np.random.normal(0, 0.002)
        elif i < 350:
            # Range regime
            trend = 0.0
            noise = np.random.normal(0, 0.003)
        else:
            # Downtrend
            trend = -0.004
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
    print("=" * 80)
    print("REGIME DETECTION TEST - Full Multi-Indicator System")
    print("=" * 80)
    print()

    # 1. Generate test data
    print("1. Generating test data with regime changes...")
    data = generate_test_data(n_bars=500)
    print(f"   Generated {len(data)} bars")
    print(f"   Expected regimes:")
    print(f"   - Bars 0-100: RANGE")
    print(f"   - Bars 100-250: TREND_UP")
    print(f"   - Bars 250-350: RANGE")
    print(f"   - Bars 350-500: TREND_DOWN")
    print()

    # 2. Create detector with all indicators
    print("2. Creating regime detector with all indicators...")
    detector = RegimeDetector(
        # ATR
        atr_window=14,
        atr_lookback=20,
        atr_expansion_threshold=1.2,
        atr_compression_threshold=0.8,
        # R²
        r2_window=60,
        r2_trend_threshold=0.6,
        r2_range_threshold=0.3,
        # CVD
        cvd_window=60,
        cvd_trend_threshold=1.0,  # Lower threshold for more sensitivity
        # Bollinger Bands
        bb_window=20,
        bb_std=2.0,
        bb_compression_threshold=0.015,
        # SNR
        snr_window=120,
        snr_trend_threshold=0.5,  # Lower threshold for more sensitivity
        # Hysteresis
        confirmation_bars=3,
        # Weights
        weight_atr=0.2,
        weight_r2=0.25,
        weight_cvd=0.25,
        weight_bb=0.1,
        weight_snr=0.2,
    )
    print("   Detector created with all indicators:")
    print(f"   - ATR, R², CVD, Bollinger Bands, SNR")
    print(f"   - Weights: ATR={detector.weight_atr}, R²={detector.weight_r2}, "
          f"CVD={detector.weight_cvd}, BB={detector.weight_bb}, SNR={detector.weight_snr}")
    print(f"   - Confirmation bars: {detector.confirmation_bars}")
    print()

    # 3. Run detection for each bar
    print("3. Running regime detection...")
    results = []

    # Need minimum data for detection
    min_bars = max(
        detector.atr_window + detector.atr_lookback,
        detector.r2_window,
        detector.cvd_window,
        detector.bb_window,
        detector.snr_window
    )

    for i in range(min_bars, len(data)):
        history = data.iloc[:i+1]  # Up to current bar
        result = detector.detect(history)
        results.append({
            'index': i,
            'timestamp': data.index[i],
            'close': data['close'].iloc[i],
            'regime': result.regime.value,
            'confidence': result.confidence,
            'trend_score': result.trend_score,
            'atr_score': result.components.get('atr_score', 0.0),
            'r2_score': result.components.get('r2_score', 0.0),
            'cvd_score': result.components.get('cvd_score', 0.0),
            'bb_score': result.components.get('bb_score', 0.0),
            'snr_score': result.components.get('snr_score', 0.0),
            'atr_ratio': result.components.get('atr_ratio', 1.0),
            'r2_value': result.components.get('r2_value', 0.0),
            'cvd_consistency': result.components.get('cvd_consistency', 0.0),
            'bb_width_pct': result.components.get('bb_width_pct', 0.0),
            'snr_value': result.components.get('snr_value', 0.0),
            'divergence': result.components.get('divergence', 0),
        })

    results_df = pd.DataFrame(results)
    print(f"   Detected regimes for {len(results_df)} bars")
    print()

    # 4. Analyze results
    print("4. Regime Distribution:")
    print("-" * 80)
    regime_counts = results_df['regime'].value_counts()
    for regime, count in regime_counts.items():
        pct = count / len(results_df) * 100
        print(f"   {regime:<15} {count:>5} bars ({pct:>5.1f}%)")
    print()

    # 5. Show regime transitions
    print("5. Regime Transitions (High Confidence):")
    print("-" * 80)
    transitions = []
    prev_regime = None

    for idx, row in results_df.iterrows():
        if row['confidence'] >= 0.9 and row['regime'] != prev_regime:
            transitions.append({
                'bar': row['index'],
                'time': row['timestamp'],
                'from': prev_regime or 'START',
                'to': row['regime'],
                'confidence': row['confidence'],
                'trend_score': row['trend_score'],
            })
            prev_regime = row['regime']

    for t in transitions:
        print(f"   Bar {t['bar']:>3}: {t['from']:>12} -> {t['to']:<12} "
              f"(conf: {t['confidence']:.2f}, score: {t['trend_score']:>6.2f})")
    print()

    # 6. Show sample detailed results
    print("6. Sample Detailed Results:")
    print("-" * 80)
    sample_indices = [100, 200, 300, 400, 490]  # One from each regime

    for idx in sample_indices:
        if idx < min_bars:
            continue

        row = results_df[results_df['index'] == idx].iloc[0]
        print(f"\n   Bar {idx}:")
        print(f"   Regime: {row['regime']} (confidence: {row['confidence']:.2f})")
        print(f"   Trend Score: {row['trend_score']:.3f}, Divergence: {row['divergence']}")
        print(f"   Components:")
        print(f"     - ATR:  {row['atr_score']:>6.3f} (ratio: {row['atr_ratio']:.2f})")
        print(f"     - R²:   {row['r2_score']:>6.3f} (R²: {row['r2_value']:.2f})")
        print(f"     - CVD:  {row['cvd_score']:>6.3f} (consistency: {row['cvd_consistency']:.2f})")
        print(f"     - BB:   {row['bb_score']:>6.3f} (width: {row['bb_width_pct']:.3f})")
        print(f"     - SNR:  {row['snr_score']:>6.3f} (SNR: {row['snr_value']:.2f})")

    print()

    # 7. Statistics
    print("7. Detection Statistics:")
    print("-" * 80)
    high_conf_regime = results_df[results_df['confidence'] >= 0.8]
    print(f"   High confidence detections (>=0.8): {len(high_conf_regime)} / {len(results_df)} "
          f"({len(high_conf_regime)/len(results_df)*100:.1f}%)")

    avg_scores = {
        'TREND_UP': results_df[results_df['regime'] == 'TREND_UP']['trend_score'].mean(),
        'TREND_DOWN': results_df[results_df['regime'] == 'TREND_DOWN']['trend_score'].mean(),
        'RANGE': results_df[results_df['regime'] == 'RANGE']['trend_score'].mean(),
        'NEUTRAL': results_df[results_df['regime'] == 'NEUTRAL']['trend_score'].mean(),
    }

    print(f"\n   Average trend scores by regime:")
    for regime, score in avg_scores.items():
        if not pd.isna(score):
            print(f"     {regime:<12} {score:>6.3f}")

    print()
    print("=" * 80)
    print("REGIME DETECTION TEST COMPLETE")
    print("=" * 80)

    # Optional: Save results for analysis
    results_df.to_csv('regime_detection_results.csv', index=False)
    print(f"\nResults saved to: regime_detection_results.csv")


if __name__ == "__main__":
    main()
