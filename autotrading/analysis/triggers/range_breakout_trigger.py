"""
Range Breakout Trigger

Detects breakouts of recent high/low levels:
- TREND: Breakout confirms trend continuation
- RANGE: Breakout signals range exit
"""

from typing import Optional, Dict, Any
import pandas as pd

from .base import BaseTrigger, TriggerSignal
from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


class RangeBreakoutTrigger(BaseTrigger):
    """
    Range high/low breakout trigger.

    TREND regime:
    - High breakout + TREND_UP → Trend continuation → LONG
    - Low breakout + TREND_DOWN → Trend continuation → SHORT
    - TP/SL: Energy-based

    RANGE regime:
    - High breakout → Range upward breakout → LONG
    - Low breakout → Range downward breakout → SHORT
    - TP/SL: Breakout distance (range width)
    """

    def __init__(
        self,
        range_window: int = 20,
        breakout_threshold: float = 1.001,  # 0.1% above/below
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize range breakout trigger.

        Args:
            range_window: Window to calculate recent high/low
            breakout_threshold: Multiplier for breakout (1.001 = 0.1% above)
            min_confidence: Minimum regime confidence
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        super().__init__(
            name='RangeBreakoutTrigger',
            min_confidence=min_confidence,
            base_position_size=base_position_size,
            max_position_size=max_position_size
        )
        self.range_window = range_window
        self.breakout_threshold = breakout_threshold

    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect range high/low breakout.

        Returns:
            {'type': 'high_breakout' | 'low_breakout', 'high': float, 'low': float, 'range_width': float}
            or None
        """
        if len(history) < self.range_window + 1:
            return None

        # Recent high/low (excluding current bar)
        recent_high = history['high'].iloc[-(self.range_window+1):-1].max()
        recent_low = history['low'].iloc[-(self.range_window+1):-1].min()
        range_width = recent_high - recent_low

        # Current price
        current_high = history['high'].iloc[-1]
        current_low = history['low'].iloc[-1]

        # Check breakout
        high_breakout = current_high > (recent_high * self.breakout_threshold)
        low_breakout = current_low < (recent_low / self.breakout_threshold)

        if high_breakout:
            return {
                'type': 'high_breakout',
                'high': recent_high,
                'low': recent_low,
                'range_width': range_width,
            }
        elif low_breakout:
            return {
                'type': 'low_breakout',
                'high': recent_high,
                'low': recent_low,
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
        Interpret breakout based on regime.

        TREND: Continuation
        RANGE: Breakout
        """
        current_price = history['close'].iloc[-1]
        breakout_type = condition['type']
        recent_high = condition['high']
        recent_low = condition['low']
        range_width = condition['range_width']

        regime = regime_result.regime

        # TREND regime: Breakout confirms trend continuation
        if regime in [RegimeType.TREND_UP, RegimeType.TREND_DOWN]:
            return self._interpret_trend(
                breakout_type, current_price, recent_high, recent_low,
                regime, regime_result, energy_result
            )

        # RANGE regime: Breakout signals range exit
        elif regime == RegimeType.RANGE:
            return self._interpret_range(
                breakout_type, current_price, recent_high, recent_low, range_width,
                regime_result, energy_result
            )

        return None

    def _interpret_trend(
        self,
        breakout_type: str,
        current_price: float,
        recent_high: float,
        recent_low: float,
        regime: RegimeType,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        TREND regime: Breakout = Trend continuation.
        """
        expected_move = energy_result.expected_move

        if regime == RegimeType.TREND_UP and breakout_type == 'high_breakout':
            # Uptrend + high breakout → Strong continuation → LONG
            tp = current_price + (expected_move * 0.7)
            sl = current_price - (expected_move * 0.35)

            return self._create_signal(
                signal='LONG',
                reason='range_breakout_uptrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'range_breakout',
                    'breakout_type': 'high',
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                }
            )

        elif regime == RegimeType.TREND_DOWN and breakout_type == 'low_breakout':
            # Downtrend + low breakout → Strong continuation → SHORT
            tp = current_price - (expected_move * 0.7)
            sl = current_price + (expected_move * 0.35)

            return self._create_signal(
                signal='SHORT',
                reason='range_breakout_downtrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'range_breakout',
                    'breakout_type': 'low',
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                }
            )

        return None

    def _interpret_range(
        self,
        breakout_type: str,
        current_price: float,
        recent_high: float,
        recent_low: float,
        range_width: float,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        RANGE regime: Breakout = Range exit.
        """
        if breakout_type == 'high_breakout':
            # Range upward breakout → LONG
            # TP: Range width projection
            tp = current_price + (range_width * 0.5)
            sl = recent_high - (range_width * 0.2)  # Just below breakout level

            return self._create_signal(
                signal='LONG',
                reason='range_breakout_upward',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'range_breakout',
                    'breakout_type': 'high',
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                    'range_width': range_width,
                }
            )

        elif breakout_type == 'low_breakout':
            # Range downward breakout → SHORT
            # TP: Range width projection
            tp = current_price - (range_width * 0.5)
            sl = recent_low + (range_width * 0.2)  # Just above breakout level

            return self._create_signal(
                signal='SHORT',
                reason='range_breakout_downward',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'range_breakout',
                    'breakout_type': 'low',
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                    'range_width': range_width,
                }
            )

        return None
