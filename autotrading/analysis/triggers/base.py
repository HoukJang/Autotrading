"""
Base Trigger Class

Defines the interface for all trading triggers.
Triggers detect technical conditions and generate entry signals
based on regime context.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd

from ..regime_detector import RegimeResult, RegimeType
from ..energy_accumulator import EnergyResult


@dataclass
class TriggerSignal:
    """
    Trading signal from a trigger.

    Attributes:
        signal: 'LONG' or 'SHORT'
        reason: Why this signal was generated
        entry_price: Suggested entry price
        tp: Take profit price
        sl: Stop loss price
        position_size: Number of contracts
        regime: Current regime
        regime_confidence: Regime confidence
        energy: Expected move size
        metadata: Additional trigger-specific info
    """
    signal: str  # 'LONG' or 'SHORT'
    reason: str
    entry_price: float
    tp: float
    sl: float
    position_size: int
    regime: str
    regime_confidence: float
    energy: float
    energy_confidence: float
    metadata: Dict[str, Any]


class BaseTrigger(ABC):
    """
    Base class for all trading triggers.

    A trigger:
    1. Detects technical conditions (BB touch, MA cross, etc.)
    2. Interprets the condition based on current regime
    3. Generates entry signals with TP/SL

    Subclasses must implement:
    - detect_condition(): Detect technical setup
    - interpret_signal(): Generate signal based on regime
    """

    def __init__(
        self,
        name: str,
        min_confidence: float = 0.7,
        base_position_size: float = 1.0,
        max_position_size: float = 3.0,
    ):
        """
        Initialize base trigger.

        Args:
            name: Trigger name for logging
            min_confidence: Minimum regime confidence to enter
            base_position_size: Base contract size
            max_position_size: Maximum contract size
        """
        self.name = name
        self.min_confidence = min_confidence
        self.base_position_size = base_position_size
        self.max_position_size = max_position_size

    def check_entry(
        self,
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        Check for entry signal.

        Process:
        1. Check regime confidence
        2. Detect technical condition
        3. Interpret signal based on regime
        4. Calculate TP/SL and position size

        Args:
            history: OHLCV data
            regime_result: Current regime
            energy_result: Energy accumulation result

        Returns:
            TriggerSignal if entry condition met, None otherwise
        """
        # 1. Confidence check
        if regime_result.confidence < self.min_confidence:
            return None

        # 2. NEUTRAL regime → no entry
        if regime_result.regime == RegimeType.NEUTRAL:
            return None

        # 3. Detect technical condition
        condition = self.detect_condition(history)
        if condition is None:
            return None

        # 4. Interpret signal based on regime
        signal = self.interpret_signal(
            condition=condition,
            history=history,
            regime_result=regime_result,
            energy_result=energy_result
        )

        return signal

    @abstractmethod
    def detect_condition(self, history: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect technical condition.

        Examples:
        - BB touch: {'type': 'upper_touch', 'price': 100.5}
        - MA cross: {'type': 'golden_cross', 'fast_ma': 100, 'slow_ma': 99}

        Args:
            history: OHLCV data

        Returns:
            Condition dict if detected, None otherwise
        """
        pass

    @abstractmethod
    def interpret_signal(
        self,
        condition: Dict[str, Any],
        history: pd.DataFrame,
        regime_result: RegimeResult,
        energy_result: EnergyResult
    ) -> Optional[TriggerSignal]:
        """
        Interpret condition based on regime and generate signal.

        Same condition can mean different things:
        - TREND: Breakout/Continuation
        - RANGE: Reversal

        Args:
            condition: Detected technical condition
            history: OHLCV data
            regime_result: Current regime
            energy_result: Energy result

        Returns:
            TriggerSignal if valid, None otherwise
        """
        pass

    def calculate_position_size(self, regime_confidence: float) -> int:
        """
        Calculate position size based on regime confidence.

        Formula: position_size = base_size * regime_confidence

        Args:
            regime_confidence: 0.0 to 1.0

        Returns:
            Position size in contracts (integer)
        """
        position_size = self.base_position_size * regime_confidence
        position_size = min(position_size, self.max_position_size)
        position_size = round(position_size)

        return max(1, position_size)

    def _create_signal(
        self,
        signal: str,
        reason: str,
        entry_price: float,
        tp: float,
        sl: float,
        regime_result: RegimeResult,
        energy_result: EnergyResult,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TriggerSignal:
        """
        Helper to create TriggerSignal.

        Args:
            signal: 'LONG' or 'SHORT'
            reason: Signal reason
            entry_price: Entry price
            tp: Take profit
            sl: Stop loss
            regime_result: Regime result
            energy_result: Energy result
            metadata: Additional info

        Returns:
            TriggerSignal
        """
        position_size = self.calculate_position_size(regime_result.confidence)

        return TriggerSignal(
            signal=signal,
            reason=reason,
            entry_price=entry_price,
            tp=tp,
            sl=sl,
            position_size=position_size,
            regime=regime_result.regime.value,
            regime_confidence=regime_result.confidence,
            energy=energy_result.expected_move,
            energy_confidence=energy_result.confidence,
            metadata=metadata or {}
        )
