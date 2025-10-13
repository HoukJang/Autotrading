"""
Triggers Module

Trading triggers that detect technical conditions and generate
entry signals based on regime context.

Available triggers:
- BollingerTrigger: Bollinger Band boundary touches
- MACrossTrigger: Moving average crossovers
- RangeBreakoutTrigger: Range high/low breakouts
- FibonacciTrigger: Fibonacci retracement levels
- StdEnvelopeTrigger: Standard deviation envelope touches
"""

from .base import BaseTrigger, TriggerSignal
from .bollinger_trigger import BollingerTrigger
from .ma_cross_trigger import MACrossTrigger
from .range_breakout_trigger import RangeBreakoutTrigger
from .fibonacci_trigger import FibonacciTrigger
from .std_envelope_trigger import StdEnvelopeTrigger

__all__ = [
    'BaseTrigger',
    'TriggerSignal',
    'BollingerTrigger',
    'MACrossTrigger',
    'RangeBreakoutTrigger',
    'FibonacciTrigger',
    'StdEnvelopeTrigger',
]
