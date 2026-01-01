"""
Bollinger Band Trigger

Detects BB upper/lower band touches and interprets based on regime:
- TREND: Band touch → Breakout/Continuation
- RANGE: Band touch → Mean Reversion
"""

from typing import Optional, Dict, Any
import pandas as pd

from .base import BaseTrigger, TriggerSignal
from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


class BollingerTrigger(BaseTrigger):
    """
    Bollinger Band boundary trigger.

    TREND regime:
    - Upper band touch → Breakout upward → LONG
    - Lower band touch → Breakout downward → SHORT
    - TP/SL: Band expansion expected

    RANGE regime:
    - Upper band touch + reversal → Mean reversion → SHORT
    - Lower band touch + reversal → Mean reversion → LONG
    - TP/SL: Middle band (MA) target
    """

    def __init__(
        self,
        bb_window: int = 20,
        bb_num_std: float = 2.0,
        touch_threshold: float = 0.98,  # 98% of distance to band
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize Bollinger trigger.

        Args:
            bb_window: BB calculation period
            bb_num_std: Number of standard deviations
            touch_threshold: How close to band counts as "touch" (0-1)
            min_confidence: Minimum regime confidence
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        super().__init__(
            name='BollingerTrigger',
            min_confidence=min_confidence,
            base_position_size=base_position_size,
            max_position_size=max_position_size
        )
        self.bb_window = bb_window
        self.bb_num_std = bb_num_std
        self.touch_threshold = touch_threshold

    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect BB band touch.

        Returns:
            {'type': 'upper_touch' | 'lower_touch', 'upper': float, 'middle': float, 'lower': float}
            or None
        """
        if len(history) < self.bb_window:
            return None

        # Calculate Bollinger Bands
        close = history['close']
        ma = close.rolling(self.bb_window).mean().iloc[-1]
        std = close.rolling(self.bb_window).std().iloc[-1]

        upper = ma + (std * self.bb_num_std)
        lower = ma - (std * self.bb_num_std)

        current_price = close.iloc[-1]

        # Check touch
        band_range = upper - lower
        upper_distance = (upper - current_price) / band_range
        lower_distance = (current_price - lower) / band_range

        if upper_distance <= (1 - self.touch_threshold):
            return {
                'type': 'upper_touch',
                'upper': upper,
                'middle': ma,
                'lower': lower,
                'std': std,
            }
        elif lower_distance <= (1 - self.touch_threshold):
            return {
                'type': 'lower_touch',
                'upper': upper,
                'middle': ma,
                'lower': lower,
                'std': std,
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
        Interpret BB touch based on regime.

        TREND: Breakout
        RANGE: Reversal (with confirmation)
        """
        current_price = history['close'].iloc[-1]
        touch_type = condition['type']
        upper = condition['upper']
        middle = condition['middle']
        lower = condition['lower']
        std = condition['std']

        regime = regime_result.regime

        # TREND regime: Breakout interpretation
        if regime in [RegimeType.TREND_UP, RegimeType.TREND_DOWN]:
            return self._interpret_trend(
                touch_type, current_price, upper, middle, lower, std,
                regime, regime_result, energy_result
            )

        # RANGE regime: Reversal interpretation
        elif regime == RegimeType.RANGE:
            return self._interpret_range(
                touch_type, current_price, upper, middle, lower, std,
                history, regime_result, energy_result
            )

        return None

    def _interpret_trend(
        self,
        touch_type: str,
        current_price: float,
        upper: float,
        middle: float,
        lower: float,
        std: float,
        regime: RegimeType,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        TREND regime: Band touch = Breakout/Continuation.
        """
        if regime == RegimeType.TREND_UP and touch_type == 'upper_touch':
            # Uptrend + upper band touch → Strong momentum → LONG
            band_width = upper - middle
            tp = upper + band_width  # Expect band expansion
            sl = middle  # Middle band as support

            return self._create_signal(
                signal='LONG',
                reason='bb_breakout_uptrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'bollinger',
                    'interpretation': 'breakout',
                    'bb_upper': upper,
                    'bb_middle': middle,
                    'bb_lower': lower,
                }
            )

        elif regime == RegimeType.TREND_DOWN and touch_type == 'lower_touch':
            # Downtrend + lower band touch → Strong momentum → SHORT
            band_width = middle - lower
            tp = lower - band_width  # Expect band expansion
            sl = middle  # Middle band as resistance

            return self._create_signal(
                signal='SHORT',
                reason='bb_breakout_downtrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'bollinger',
                    'interpretation': 'breakout',
                    'bb_upper': upper,
                    'bb_middle': middle,
                    'bb_lower': lower,
                }
            )

        return None

    def _interpret_range(
        self,
        touch_type: str,
        current_price: float,
        upper: float,
        middle: float,
        lower: float,
        std: float,
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        RANGE regime: Band touch = Mean Reversion (with reversal confirmation).
        """
        # Check reversal (1 bar confirmation)
        current_close = history['close'].iloc[-1]
        prev_close = history['close'].iloc[-2]

        if touch_type == 'upper_touch':
            # Upper band touch → Need downward reversal
            reversal = current_close < prev_close

            if reversal:
                # Mean reversion → SHORT
                tp = middle  # Target middle band
                sl = upper + (std * 0.5)  # SL outside band

                return self._create_signal(
                    signal='SHORT',
                    reason='bb_reversal_range_top',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'bollinger',
                        'interpretation': 'reversal',
                        'bb_upper': upper,
                        'bb_middle': middle,
                        'bb_lower': lower,
                    }
                )

        elif touch_type == 'lower_touch':
            # Lower band touch → Need upward reversal
            reversal = current_close > prev_close

            if reversal:
                # Mean reversion → LONG
                tp = middle  # Target middle band
                sl = lower - (std * 0.5)  # SL outside band

                return self._create_signal(
                    signal='LONG',
                    reason='bb_reversal_range_bottom',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'bollinger',
                        'interpretation': 'reversal',
                        'bb_upper': upper,
                        'bb_middle': middle,
                        'bb_lower': lower,
                    }
                )

        return None
