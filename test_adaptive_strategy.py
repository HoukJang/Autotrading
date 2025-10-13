"""
Test Adaptive Strategy Manager - Phase 4

Tests the complete adaptive strategy system with:
- Backtest initialization
- Real-time simulation
- Performance reporting
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from autotrading.strategy import AdaptiveStrategyManager
from autotrading.analysis import (
    BollingerTrigger,
    MACrossTrigger,
    RangeBreakoutTrigger,
)


def generate_market_data(n_bars: int = 1000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic market data with regime changes.

    Args:
        n_bars: Number of bars to generate
        seed: Random seed

    Returns:
        OHLCV DataFrame with datetime index
    """
    np.random.seed(seed)

    # Start time: 09:30
    start_time = datetime(2024, 1, 1, 9, 30)
    timestamps = [start_time + timedelta(minutes=i) for i in range(n_bars)]

    # Price with regime changes
    base_price = 100.0
    prices = []
    volumes = []

    for i in range(n_bars):
        # Regime changes every 200 bars
        regime = (i // 200) % 3

        if regime == 0:
            # TREND UP
            trend = 0.003
            noise = np.random.normal(0, 0.001)
            volume = np.random.randint(250, 400)
        elif regime == 1:
            # RANGE
            trend = 0.0
            noise = np.random.normal(0, 0.003)
            volume = np.random.randint(100, 200)
        else:
            # TREND DOWN
            trend = -0.003
            noise = np.random.normal(0, 0.001)
            volume = np.random.randint(250, 400)

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
    print("ADAPTIVE STRATEGY MANAGER TEST - Phase 4")
    print("=" * 80)

    # 1. Generate test data
    print("\n1. Generating market data...")
    full_data = generate_market_data(n_bars=1000)
    print(f"   Generated {len(full_data)} bars")
    print(f"   Date range: {full_data.index[0]} to {full_data.index[-1]}")

    # Split: 70% backtest initialization, 30% live simulation
    split_idx = int(len(full_data) * 0.7)
    backtest_data = full_data.iloc[:split_idx]
    live_data = full_data.iloc[split_idx:]

    print(f"   Backtest data: {len(backtest_data)} bars")
    print(f"   Live data: {len(live_data)} bars")

    # 2. Initialize triggers
    print("\n2. Initializing triggers...")
    triggers = [
        BollingerTrigger(),
        MACrossTrigger(),
        RangeBreakoutTrigger(),
    ]
    print(f"   Initialized {len(triggers)} triggers")

    # 3. Create Adaptive Strategy Manager
    print("\n3. Creating Adaptive Strategy Manager...")
    manager = AdaptiveStrategyManager(
        triggers=triggers,
        account_balance=100000.0,  # $100k account
        risk_percentage=0.02,  # 2% risk
        contract_value=15000.0,  # $15k per contract (NQ)
        window_minutes=30,
        decay_days=30,
        decay_lambda=0.1,
        max_consecutive_losses=3,
        pause_minutes=30,
    )
    print("   Manager created")

    # 4. Backtest initialization
    print("\n4. Running backtest initialization...")
    manager.initialize_from_backtest(backtest_data)

    # 5. Show initial scores
    print("\n5. Initial scores (from backtest):")
    initial_time = live_data.index[0]
    # Get first regime for scoring
    initial_history = backtest_data
    regime_result = manager.regime_detector.detect(initial_history)

    scores = manager.get_current_scores(
        current_time=initial_time,
        current_regime=regime_result.regime.value,
    )
    for trigger_name, score in scores.items():
        print(f"   {trigger_name}: {score:.4f}")

    # 6. Simulate live trading
    print("\n6. Simulating live trading...")
    execution_log = []

    for i in range(120, len(live_data)):
        # Build history (backtest + live up to current)
        history_end_idx = split_idx + i + 1
        history = full_data.iloc[:history_end_idx]
        current_bar = full_data.iloc[history_end_idx - 1]

        # Process bar
        decisions = manager.process_bar(current_bar, history)

        # Log executions
        for decision in decisions:
            if decision.execute:
                execution_log.append({
                    'time': current_bar.name,
                    'trigger': decision.trigger_name,
                    'signal': decision.signal.signal,
                    'size': decision.position_size,
                    'entry': decision.signal.entry_price,
                })

    print(f"   Processed {len(live_data) - 120} live bars")
    print(f"   Executed {len(execution_log)} signals")

    # 7. Final status
    print("\n7. Final Status:")
    final_time = live_data.index[-1]
    manager.print_status(final_time)

    # 8. Show execution examples
    if len(execution_log) > 0:
        print("\n8. Execution Examples (first 10):")
        for i, exec_entry in enumerate(execution_log[:10]):
            print(f"\n   Execution {i+1}:")
            print(f"     Time: {exec_entry['time']}")
            print(f"     Trigger: {exec_entry['trigger']}")
            print(f"     Signal: {exec_entry['signal']}")
            print(f"     Size: {exec_entry['size']} contracts")
            print(f"     Entry: ${exec_entry['entry']:.2f}")

    # 9. Generate daily report
    print("\n9. Generating daily report...")
    report_date = live_data.index[-1]
    report = manager.generate_daily_report(report_date)
    manager.reporter.print_summary(report)

    # 10. Final scores
    print("\n10. Final scores (after live trading):")
    final_history = full_data
    final_regime = manager.regime_detector.detect(final_history)

    final_scores = manager.get_current_scores(
        current_time=final_time,
        current_regime=final_regime.regime.value,
    )
    for trigger_name, score in final_scores.items():
        print(f"   {trigger_name}: {score:.4f}")

    # Compare initial vs final scores
    print("\n11. Score Changes:")
    for trigger_name in scores.keys():
        initial = scores[trigger_name]
        final = final_scores[trigger_name]
        change = final - initial
        print(f"   {trigger_name}: {initial:.4f} -> {final:.4f} ({change:+.4f})")

    print("\n" + "=" * 80)
    print("ADAPTIVE STRATEGY MANAGER TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
