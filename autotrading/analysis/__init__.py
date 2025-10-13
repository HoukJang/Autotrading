"""
Analysis module for market regime detection, energy calculation, and trading triggers.
"""

from .regime_detector import RegimeDetector, RegimeResult, RegimeType
from .regime_optimizer import RegimeWeightOptimizer, OptimizationResult
from .energy_accumulator import EnergyAccumulator, EnergyResult
from .triggers import (
    BaseTrigger,
    TriggerSignal,
    BollingerTrigger,
    MACrossTrigger,
    RangeBreakoutTrigger,
    FibonacciTrigger,
    StdEnvelopeTrigger,
)

__all__ = [
    'RegimeDetector',
    'RegimeResult',
    'RegimeType',
    'RegimeWeightOptimizer',
    'OptimizationResult',
    'EnergyAccumulator',
    'EnergyResult',
    'BaseTrigger',
    'TriggerSignal',
    'BollingerTrigger',
    'MACrossTrigger',
    'RangeBreakoutTrigger',
    'FibonacciTrigger',
    'StdEnvelopeTrigger',
]
