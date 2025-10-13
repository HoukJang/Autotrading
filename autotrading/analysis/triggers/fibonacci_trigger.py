"""
Fibonacci Retracement Trigger

Detects Fibonacci retracement level touches (80%/20%):
- TREND: Level touch signals pullback end and trend resumption
- RANGE: Level touch signals mean reversion opportunity
"""

from typing import Optional, Dict, Any
import pandas as pd
import numpy as np

from .base import BaseTrigger, TriggerSignal
from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


class FibonacciTrigger(BaseTrigger):
    """
    Fibonacci retracement level trigger.

    TREND regime:
    - TREND_UP + 20% level touch → Pullback end → LONG
    - TREND_DOWN + 80% level touch → Pullback end → SHORT
    - TP/SL: Energy-based (trend resumption expected)

    RANGE regime:
    - 80% level touch + reversal → Mean reversion → SHORT
    - 20% level touch + reversal → Mean reversion → LONG
    - TP/SL: Opposite level target
    """

    def __init__(
        self,
        swing_window: int = 100,
        top_level: float = 0.80,
        bottom_level: float = 0.20,
        touch_threshold: float = 0.02,  # 2% distance to level
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize Fibonacci trigger.

        Args:
            swing_window: Window to find swing high/low
            top_level: Upper retracement level (0.80 = 80%)
            bottom_level: Lower retracement level (0.20 = 20%)
            touch_threshold: Distance threshold for "touch" (as fraction of range)
            min_confidence: Minimum regime confidence
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        super().__init__(
            name='FibonacciTrigger',
            min_confidence=min_confidence,
            base_position_size=base_position_size,
            max_position_size=max_position_size
        )
        self.swing_window = swing_window
        self.top_level = top_level
        self.bottom_level = bottom_level
        self.touch_threshold = touch_threshold

    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect Fibonacci level touch.

        Returns:
            {'type': 'top_level_touch' | 'bottom_level_touch',
             'swing_high': float, 'swing_low': float,
             'level_80': float, 'level_20': float}
            or None
        """
        if len(history) < self.swing_window:
            return None

        # Find swing high/low
        swing_high = history['high'].iloc[-self.swing_window:].max()
        swing_low = history['low'].iloc[-self.swing_window:].min()
        range_width = swing_high - swing_low

        # Calculate Fibonacci levels
        level_80 = swing_low + (range_width * self.top_level)
        level_20 = swing_low + (range_width * self.bottom_level)

        # Current price
        current_price = history['close'].iloc[-1]

        # Check touch (within threshold)
        touch_distance_80 = abs(current_price - level_80) / range_width
        touch_distance_20 = abs(current_price - level_20) / range_width

        if touch_distance_80 <= self.touch_threshold:
            return {
                'type': 'top_level_touch',
                'swing_high': swing_high,
                'swing_low': swing_low,
                'level_80': level_80,
                'level_20': level_20,
                'range_width': range_width,
            }
        elif touch_distance_20 <= self.touch_threshold:
            return {
                'type': 'bottom_level_touch',
                'swing_high': swing_high,
                'swing_low': swing_low,
                'level_80': level_80,
                'level_20': level_20,
                'range_width': range_width,
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
        Interpret Fibonacci level touch based on regime.

        TREND: Pullback end
        RANGE: Reversal
        """
        current_price = history['close'].iloc[-1]
        touch_type = condition['type']
        swing_high = condition['swing_high']
        swing_low = condition['swing_low']
        level_80 = condition['level_80']
        level_20 = condition['level_20']
        range_width = condition['range_width']

        regime = regime_result.regime

        # TREND regime: Level touch = Pullback end
        if regime in [RegimeType.TREND_UP, RegimeType.TREND_DOWN]:
            return self._interpret_trend(
                touch_type, current_price, level_80, level_20,
                regime, regime_result, energy_result
            )

        # RANGE regime: Level touch = Reversal
        elif regime == RegimeType.RANGE:
            return self._interpret_range(
                touch_type, current_price, level_80, level_20,
                history, regime_result, energy_result
            )

        return None

    def _interpret_trend(
        self,
        touch_type: str,
        current_price: float,
        level_80: float,
        level_20: float,
        regime: RegimeType,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        TREND regime: Fib level = Pullback end, trend resumption.
        """
        expected_move = energy_result.expected_move

        if regime == RegimeType.TREND_UP and touch_type == 'bottom_level_touch':
            # Uptrend + 20% level touch → Pullback end → LONG
            tp = current_price + (expected_move * 0.7)
            sl = current_price - (expected_move * 0.35)

            return self._create_signal(
                signal='LONG',
                reason='fib_pullback_uptrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'fibonacci',
                    'interpretation': 'pullback_end',
                    'level_touched': level_20,
                    'level_type': '20%',
                }
            )

        elif regime == RegimeType.TREND_DOWN and touch_type == 'top_level_touch':
            # Downtrend + 80% level touch → Pullback end → SHORT
            tp = current_price - (expected_move * 0.7)
            sl = current_price + (expected_move * 0.35)

            return self._create_signal(
                signal='SHORT',
                reason='fib_pullback_downtrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'fibonacci',
                    'interpretation': 'pullback_end',
                    'level_touched': level_80,
                    'level_type': '80%',
                }
            )

        return None

    def _interpret_range(
        self,
        touch_type: str,
        current_price: float,
        level_80: float,
        level_20: float,
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        RANGE regime: Fib level = Reversal opportunity.
        """
        # Check reversal (1 bar confirmation)
        current_close = history['close'].iloc[-1]
        prev_close = history['close'].iloc[-2]

        if touch_type == 'top_level_touch':
            # 80% level touch → Need downward reversal
            reversal = current_close < prev_close

            if reversal:
                # Mean reversion → SHORT
                tp = level_20  # Target 20% level
                sl = level_80 + (level_80 - level_20) * 0.1  # 10% above level

                return self._create_signal(
                    signal='SHORT',
                    reason='fib_reversal_range_top',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'fibonacci',
                        'interpretation': 'reversal',
                        'level_touched': level_80,
                        'level_type': '80%',
                    }
                )

        elif touch_type == 'bottom_level_touch':
            # 20% level touch → Need upward reversal
            reversal = current_close > prev_close

            if reversal:
                # Mean reversion → LONG
                tp = level_80  # Target 80% level
                sl = level_20 - (level_80 - level_20) * 0.1  # 10% below level

                return self._create_signal(
                    signal='LONG',
                    reason='fib_reversal_range_bottom',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'fibonacci',
                        'interpretation': 'reversal',
                        'level_touched': level_20,
                        'level_type': '20%',
                    }
                )

        return None
