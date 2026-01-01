"""
Standard Deviation Envelope Trigger

Detects touches of MA ± N×std envelope:
- TREND: Envelope touch signals trend continuation
- RANGE: Envelope touch signals mean reversion opportunity
"""

from typing import Optional, Dict, Any
import pandas as pd

from .base import BaseTrigger, TriggerSignal
from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


class StdEnvelopeTrigger(BaseTrigger):
    """
    Standard deviation envelope trigger.

    TREND regime:
    - Upper envelope touch + TREND_UP → Continuation → LONG
    - Lower envelope touch + TREND_DOWN → Continuation → SHORT
    - TP/SL: Envelope expansion expected

    RANGE regime:
    - Upper envelope touch + reversal → Mean reversion → SHORT
    - Lower envelope touch + reversal → Mean reversion → LONG
    - TP/SL: MA (center) target
    """

    def __init__(
        self,
        ma_window: int = 60,
        num_std: float = 1.5,
        touch_threshold: float = 0.95,  # 95% of distance to envelope
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize std envelope trigger.

        Args:
            ma_window: MA calculation period
            num_std: Number of standard deviations for envelope
            touch_threshold: How close to envelope counts as "touch" (0-1)
            min_confidence: Minimum regime confidence
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        super().__init__(
            name='StdEnvelopeTrigger',
            min_confidence=min_confidence,
            base_position_size=base_position_size,
            max_position_size=max_position_size
        )
        self.ma_window = ma_window
        self.num_std = num_std
        self.touch_threshold = touch_threshold

    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect envelope touch.

        Returns:
            {'type': 'upper_touch' | 'lower_touch',
             'ma': float, 'upper': float, 'lower': float, 'std': float}
            or None
        """
        if len(history) < self.ma_window:
            return None

        # Calculate envelope
        close = history['close']
        ma = close.rolling(self.ma_window).mean().iloc[-1]
        std = close.rolling(self.ma_window).std().iloc[-1]

        upper = ma + (std * self.num_std)
        lower = ma - (std * self.num_std)

        current_price = close.iloc[-1]

        # Check touch
        envelope_range = upper - lower
        upper_distance = (upper - current_price) / envelope_range
        lower_distance = (current_price - lower) / envelope_range

        if upper_distance <= (1 - self.touch_threshold):
            return {
                'type': 'upper_touch',
                'ma': ma,
                'upper': upper,
                'lower': lower,
                'std': std,
            }
        elif lower_distance <= (1 - self.touch_threshold):
            return {
                'type': 'lower_touch',
                'ma': ma,
                'upper': upper,
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
        Interpret envelope touch based on regime.

        TREND: Continuation
        RANGE: Reversal
        """
        current_price = history['close'].iloc[-1]
        touch_type = condition['type']
        ma = condition['ma']
        upper = condition['upper']
        lower = condition['lower']
        std = condition['std']

        regime = regime_result.regime

        # TREND regime: Envelope touch = Continuation
        if regime in [RegimeType.TREND_UP, RegimeType.TREND_DOWN]:
            return self._interpret_trend(
                touch_type, current_price, ma, upper, lower, std,
                regime, regime_result, energy_result
            )

        # RANGE regime: Envelope touch = Reversal
        elif regime == RegimeType.RANGE:
            return self._interpret_range(
                touch_type, current_price, ma, upper, lower, std,
                history, regime_result, energy_result
            )

        return None

    def _interpret_trend(
        self,
        touch_type: str,
        current_price: float,
        ma: float,
        upper: float,
        lower: float,
        std: float,
        regime: RegimeType,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        TREND regime: Envelope touch = Trend continuation.
        """
        if regime == RegimeType.TREND_UP and touch_type == 'upper_touch':
            # Uptrend + upper envelope touch → Strong momentum → LONG
            envelope_width = upper - ma
            tp = upper + envelope_width  # Envelope expansion
            sl = ma  # MA as support

            return self._create_signal(
                signal='LONG',
                reason='envelope_continuation_uptrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'std_envelope',
                    'interpretation': 'continuation',
                    'ma': ma,
                    'upper': upper,
                    'lower': lower,
                }
            )

        elif regime == RegimeType.TREND_DOWN and touch_type == 'lower_touch':
            # Downtrend + lower envelope touch → Strong momentum → SHORT
            envelope_width = ma - lower
            tp = lower - envelope_width  # Envelope expansion
            sl = ma  # MA as resistance

            return self._create_signal(
                signal='SHORT',
                reason='envelope_continuation_downtrend',
                entry_price=current_price,
                tp=tp,
                sl=sl,
                regime_result=regime_result,
                energy_result=energy_result,
                metadata={
                    'trigger': 'std_envelope',
                    'interpretation': 'continuation',
                    'ma': ma,
                    'upper': upper,
                    'lower': lower,
                }
            )

        return None

    def _interpret_range(
        self,
        touch_type: str,
        current_price: float,
        ma: float,
        upper: float,
        lower: float,
        std: float,
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        RANGE regime: Envelope touch = Mean reversion.
        """
        # Check reversal (1 bar confirmation)
        current_close = history['close'].iloc[-1]
        prev_close = history['close'].iloc[-2]

        if touch_type == 'upper_touch':
            # Upper envelope touch → Need downward reversal
            reversal = current_close < prev_close

            if reversal:
                # Mean reversion → SHORT
                tp = ma  # Target MA (center)
                sl = upper + (std * 0.5)  # Outside envelope

                return self._create_signal(
                    signal='SHORT',
                    reason='envelope_reversal_range_top',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'std_envelope',
                        'interpretation': 'reversal',
                        'ma': ma,
                        'upper': upper,
                        'lower': lower,
                    }
                )

        elif touch_type == 'lower_touch':
            # Lower envelope touch → Need upward reversal
            reversal = current_close > prev_close

            if reversal:
                # Mean reversion → LONG
                tp = ma  # Target MA (center)
                sl = lower - (std * 0.5)  # Outside envelope

                return self._create_signal(
                    signal='LONG',
                    reason='envelope_reversal_range_bottom',
                    entry_price=current_price,
                    tp=tp,
                    sl=sl,
                    regime_result=regime_result,
                    energy_result=energy_result,
                    metadata={
                        'trigger': 'std_envelope',
                        'interpretation': 'reversal',
                        'ma': ma,
                        'upper': upper,
                        'lower': lower,
                    }
                )

        return None
