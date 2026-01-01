"""
Moving Average Cross Trigger

Detects MA crossovers (Golden Cross / Dead Cross):
- TREND: Cross confirms trend direction
- RANGE: Weak signal (ignored due to frequent whipsaws)
"""

from typing import Optional, Dict, Any
import pandas as pd

from .base import BaseTrigger, TriggerSignal
from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


class MACrossTrigger(BaseTrigger):
    """
    Moving Average crossover trigger.

    TREND regime:
    - Golden Cross (fast > slow) + TREND_UP → Trend confirmation → LONG
    - Dead Cross (fast < slow) + TREND_DOWN → Trend confirmation → SHORT
    - TP/SL: Energy-based

    RANGE regime:
    - Ignored (MA crosses too frequent in ranging markets)
    """

    def __init__(
        self,
        fast_window: int = 10,
        slow_window: int = 20,
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize MA cross trigger.

        Args:
            fast_window: Fast MA period
            slow_window: Slow MA period
            min_confidence: Minimum regime confidence
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        super().__init__(
            name='MACrossTrigger',
            min_confidence=min_confidence,
            base_position_size=base_position_size,
            max_position_size=max_position_size
        )
        self.fast_window = fast_window
        self.slow_window = slow_window

    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect MA crossover.

        Returns:
            {'type': 'golden_cross' | 'dead_cross', 'fast_ma': float, 'slow_ma': float}
            or None
        """
        if len(history) < self.slow_window + 1:
            return None

        close = history['close']

        # Calculate MAs
        fast_ma = close.rolling(self.fast_window).mean()
        slow_ma = close.rolling(self.slow_window).mean()

        # Current and previous values
        fast_now = fast_ma.iloc[-1]
        slow_now = slow_ma.iloc[-1]
        fast_prev = fast_ma.iloc[-2]
        slow_prev = slow_ma.iloc[-2]

        # Detect crossover (happened in last bar)
        golden_cross = (fast_prev <= slow_prev) and (fast_now > slow_now)
        dead_cross = (fast_prev >= slow_prev) and (fast_now < slow_now)

        if golden_cross:
            return {
                'type': 'golden_cross',
                'fast_ma': fast_now,
                'slow_ma': slow_now,
            }
        elif dead_cross:
            return {
                'type': 'dead_cross',
                'fast_ma': fast_now,
                'slow_ma': slow_now,
            }

        return None

    def interpret_signal(
        self,
        condition: Dict[str, Any],
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        Interpret MA cross based on regime.

        TREND: Cross confirms trend
        RANGE: Ignored
        """
        regime = regime_result.regime
        cross_type = condition['type']
        fast_ma = condition['fast_ma']
        slow_ma = condition['slow_ma']

        # RANGE regime: Ignore MA crosses (too noisy)
        if regime == RegimeType.RANGE:
            return None

        # TREND regime: Cross confirms trend direction
        current_price = history['close'].iloc[-1]

        if regime == RegimeType.TREND_UP and cross_type == 'golden_cross':
            # Golden cross in uptrend → Trend confirmation → LONG
            expected_move = energy_result.expected_move

            tp = current_price + (expected_move * 0.7)
            sl = current_price - (expected_move * 0.35)

            return self._create_signal(
                signal='LONG',
                reason='ma_golden_cross_uptrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'ma_cross',
                    'cross_type': 'golden_cross',
                    'fast_ma': fast_ma,
                    'slow_ma': slow_ma,
                }
            )

        elif regime == RegimeType.TREND_DOWN and cross_type == 'dead_cross':
            # Dead cross in downtrend → Trend confirmation → SHORT
            expected_move = energy_result.expected_move

            tp = current_price - (expected_move * 0.7)
            sl = current_price + (expected_move * 0.35)

            return self._create_signal(
                signal='SHORT',
                reason='ma_dead_cross_downtrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'ma_cross',
                    'cross_type': 'dead_cross',
                    'fast_ma': fast_ma,
                    'slow_ma': slow_ma,
                }
            )

        return None
