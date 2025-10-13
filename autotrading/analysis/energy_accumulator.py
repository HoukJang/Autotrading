"""
Energy Accumulation Module

Measures expected move size (energy) for dynamic TP/SL adjustment.
Uses regime-specific indicators to predict how far the market will move.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from .regime_detector import RegimeResult, RegimeType


@dataclass
class EnergyResult:
    """
    Energy accumulation result.

    Attributes:
        expected_move: Expected move size in points
        confidence: Prediction confidence (0.0 to 1.0)
        components: Breakdown of each indicator's contribution
        metadata: Additional analysis information
    """
    expected_move: float
    confidence: float
    components: Dict[str, float]
    metadata: Dict[str, Any]


class EnergyAccumulator:
    """
    Market energy accumulator for dynamic TP/SL sizing.

    Measures expected move size using regime-specific indicators:
    - TREND: ATR + Momentum + Volume + Trend Strength
    - RANGE: Range Width + Compression + Volume Buildup

    Usage:
        accumulator = EnergyAccumulator(
            trend_momentum_strong_threshold=1.5,
            trend_volume_strong_threshold=1.3,
        )

        energy_result = accumulator.calculate(history, regime_result)

        # Use for TP/SL
        tp_distance = energy_result.expected_move * 0.7
        sl_distance = tp_distance / 2.0
    """

    def __init__(
        self,
        # TREND energy parameters
        trend_atr_window: int = 14,
        trend_momentum_window: int = 20,
        trend_volume_window: int = 20,
        trend_momentum_strong_threshold: float = 1.5,  # momentum_factor > 1.5 = strong
        trend_volume_strong_threshold: float = 1.3,    # volume_factor > 1.3 = strong

        # RANGE energy parameters
        range_width_window: int = 60,
        range_compression_window: int = 20,
        range_volume_window: int = 20,
        range_compression_strong_threshold: float = 2.0,  # compression > 2.0 = strong

        # TREND weights
        trend_weight_atr: float = 0.4,
        trend_weight_momentum: float = 0.3,
        trend_weight_volume: float = 0.2,
        trend_weight_strength: float = 0.1,

        # RANGE weights
        range_weight_width: float = 0.4,
        range_weight_compression: float = 0.3,
        range_weight_volume: float = 0.3,
    ):
        """
        Initialize energy accumulator.

        Args:
            trend_atr_window: ATR calculation period
            trend_momentum_window: Momentum calculation period
            trend_volume_window: Volume average period
            trend_momentum_strong_threshold: Threshold for strong momentum signal
            trend_volume_strong_threshold: Threshold for strong volume signal
            range_width_window: Range width measurement period
            range_compression_window: Compression measurement period
            range_volume_window: Volume trend period
            range_compression_strong_threshold: Threshold for strong compression
            trend_weight_atr: Weight for ATR component
            trend_weight_momentum: Weight for momentum component
            trend_weight_volume: Weight for volume component
            trend_weight_strength: Weight for trend strength component
            range_weight_width: Weight for range width component
            range_weight_compression: Weight for compression component
            range_weight_volume: Weight for volume component
        """
        # TREND config
        self.trend_atr_window = trend_atr_window
        self.trend_momentum_window = trend_momentum_window
        self.trend_volume_window = trend_volume_window
        self.trend_momentum_strong_threshold = trend_momentum_strong_threshold
        self.trend_volume_strong_threshold = trend_volume_strong_threshold

        # RANGE config
        self.range_width_window = range_width_window
        self.range_compression_window = range_compression_window
        self.range_volume_window = range_volume_window
        self.range_compression_strong_threshold = range_compression_strong_threshold

        # TREND weights
        self.trend_weight_atr = trend_weight_atr
        self.trend_weight_momentum = trend_weight_momentum
        self.trend_weight_volume = trend_weight_volume
        self.trend_weight_strength = trend_weight_strength

        # RANGE weights
        self.range_weight_width = range_weight_width
        self.range_weight_compression = range_weight_compression
        self.range_weight_volume = range_weight_volume

    def calculate(
        self,
        history: pd.DataFrame,
        regime_result: RegimeResult
    ) -> EnergyResult:
        """
        Calculate energy based on regime type.

        Args:
            history: OHLCV data
            regime_result: Regime detection result

        Returns:
            EnergyResult with expected move and confidence
        """
        # Validate input
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in history.columns for col in required_cols):
            raise ValueError(f"History must contain columns: {required_cols}")

        # Route to regime-specific calculation
        if regime_result.regime in [RegimeType.TREND_UP, RegimeType.TREND_DOWN]:
            return self._calculate_trend_energy(history, regime_result)

        elif regime_result.regime == RegimeType.RANGE:
            return self._calculate_range_energy(history, regime_result)

        else:  # NEUTRAL
            # Uncertain regime = low energy, no trading
            return EnergyResult(
                expected_move=0.0,
                confidence=0.0,
                components={},
                metadata={'reason': 'neutral_regime'}
            )

    def _calculate_trend_energy(
        self,
        history: pd.DataFrame,
        regime_result: RegimeResult
    ) -> EnergyResult:
        """
        Calculate energy for TREND regime.

        Indicators:
        1. ATR (base energy)
        2. Momentum (acceleration)
        3. Volume confirmation
        4. Trend strength (R² from regime)

        Returns:
            EnergyResult
        """
        # Check minimum data
        min_required = max(self.trend_atr_window, self.trend_momentum_window, self.trend_volume_window)
        if len(history) < min_required:
            return EnergyResult(
                expected_move=0.0,
                confidence=0.0,
                components={},
                metadata={'error': 'insufficient_data', 'required': min_required}
            )

        # 1. ATR base
        atr = self._calculate_atr(history, self.trend_atr_window)

        # 2. Momentum factor
        momentum = self._calculate_momentum(history, self.trend_momentum_window)
        momentum_factor = 1.0 + np.clip(momentum / atr, -0.5, 1.0)

        # 3. Volume factor
        volume_factor = self._calculate_volume_factor(history, self.trend_volume_window)

        # 4. Trend strength (from regime detector)
        r2_value = regime_result.components.get('r2_value', 0.5)
        strength_factor = 0.5 + r2_value * 0.5  # Map 0~1 to 0.5~1.0

        # Composite expected move
        expected_move = (
            self.trend_weight_atr * atr * momentum_factor +
            self.trend_weight_momentum * atr * momentum_factor +
            self.trend_weight_volume * atr * volume_factor +
            self.trend_weight_strength * atr * strength_factor
        )

        # Normalize by weights
        total_weight = (
            self.trend_weight_atr +
            self.trend_weight_momentum +
            self.trend_weight_volume +
            self.trend_weight_strength
        )
        expected_move = expected_move / total_weight if total_weight > 0 else atr

        # Calculate confidence
        confidence = self._calculate_confidence(
            momentum_factor=momentum_factor,
            volume_factor=volume_factor,
            strength_factor=strength_factor,
            momentum_threshold=self.trend_momentum_strong_threshold,
            volume_threshold=self.trend_volume_strong_threshold,
        )

        return EnergyResult(
            expected_move=expected_move,
            confidence=confidence,
            components={
                'atr': atr,
                'momentum_factor': momentum_factor,
                'volume_factor': volume_factor,
                'strength_factor': strength_factor,
            },
            metadata={
                'regime': regime_result.regime.value,
                'r2': r2_value,
            }
        )

    def _calculate_range_energy(
        self,
        history: pd.DataFrame,
        regime_result: RegimeResult
    ) -> EnergyResult:
        """
        Calculate energy for RANGE regime.

        Indicators:
        1. Range width (base)
        2. Compression ratio (squeeze energy)
        3. Volume buildup

        Returns:
            EnergyResult
        """
        # Check minimum data
        min_required = max(self.range_width_window, self.range_compression_window, self.range_volume_window)
        if len(history) < min_required:
            return EnergyResult(
                expected_move=0.0,
                confidence=0.0,
                components={},
                metadata={'error': 'insufficient_data', 'required': min_required}
            )

        # 1. Range width
        recent_high = history['high'].iloc[-self.range_width_window:].max()
        recent_low = history['low'].iloc[-self.range_width_window:].min()
        range_width = recent_high - recent_low

        # 2. Compression ratio
        current_high = history['high'].iloc[-self.range_compression_window:].max()
        current_low = history['low'].iloc[-self.range_compression_window:].min()
        current_width = current_high - current_low

        compression_ratio = range_width / max(current_width, 0.001)  # Higher = more compressed

        # 3. Volume buildup
        volume_ma = history['volume'].rolling(self.range_volume_window).mean()
        volume_trend = volume_ma.iloc[-1] / volume_ma.iloc[-self.range_volume_window] if len(volume_ma) >= self.range_volume_window else 1.0
        volume_buildup = np.clip(volume_trend, 0.8, 1.5)

        # Composite expected move
        # Range breakout typically goes 50% of range width
        base_move = range_width * 0.5

        expected_move = (
            self.range_weight_width * base_move +
            self.range_weight_compression * base_move * (compression_ratio / 2.0) +
            self.range_weight_volume * base_move * volume_buildup
        )

        # Normalize
        total_weight = (
            self.range_weight_width +
            self.range_weight_compression +
            self.range_weight_volume
        )
        expected_move = expected_move / total_weight if total_weight > 0 else base_move

        # Calculate confidence
        confidence = self._calculate_confidence(
            compression_ratio=compression_ratio,
            volume_buildup=volume_buildup,
            compression_threshold=self.range_compression_strong_threshold,
        )

        return EnergyResult(
            expected_move=expected_move,
            confidence=confidence,
            components={
                'range_width': range_width,
                'current_width': current_width,
                'compression_ratio': compression_ratio,
                'volume_buildup': volume_buildup,
            },
            metadata={
                'regime': regime_result.regime.value,
            }
        )

    def _calculate_atr(self, history: pd.DataFrame, window: int) -> float:
        """Calculate Average True Range."""
        high = history['high']
        low = history['low']
        close = history['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=window).mean().iloc[-1]

        return atr if not pd.isna(atr) else 0.0

    def _calculate_momentum(self, history: pd.DataFrame, window: int) -> float:
        """
        Calculate momentum (price change acceleration).

        Returns absolute momentum value.
        """
        close = history['close']

        if len(close) < window:
            return 0.0

        # Simple momentum: current price - price N bars ago
        momentum = close.iloc[-1] - close.iloc[-window]

        return abs(momentum)  # Use absolute value

    def _calculate_volume_factor(self, history: pd.DataFrame, window: int) -> float:
        """
        Calculate volume factor.

        Returns:
            volume_factor: current_volume / avg_volume
        """
        volume = history['volume']

        if len(volume) < window:
            return 1.0

        current_volume = volume.iloc[-1]
        avg_volume = volume.iloc[-window:].mean()

        if avg_volume == 0:
            return 1.0

        volume_ratio = current_volume / avg_volume

        # Convert to factor (1.0 + delta * 0.3)
        volume_factor = 1.0 + (volume_ratio - 1.0) * 0.3

        return volume_factor

    def _calculate_confidence(self, **factors) -> float:
        """
        Calculate confidence from indicator strengths.

        Process:
        1. Convert each factor to 0~1 strength
        2. Calculate mean (how strong) and std (how consistent)
        3. Confidence = mean * (1 - std)

        Args:
            **factors: Named factors with their thresholds
                      e.g., momentum_factor=1.5, momentum_threshold=1.5

        Returns:
            confidence: 0.0 to 1.0
        """
        strengths = []

        # Process TREND factors
        if 'momentum_factor' in factors:
            momentum_strength = self._factor_to_strength(
                factors['momentum_factor'],
                neutral=1.0,
                strong_threshold=factors.get('momentum_threshold', 1.5)
            )
            strengths.append(momentum_strength)

        if 'volume_factor' in factors:
            volume_strength = self._factor_to_strength(
                factors['volume_factor'],
                neutral=1.0,
                strong_threshold=factors.get('volume_threshold', 1.3)
            )
            strengths.append(volume_strength)

        if 'strength_factor' in factors:
            # strength_factor is already 0~1 (from R²)
            strengths.append(factors['strength_factor'])

        # Process RANGE factors
        if 'compression_ratio' in factors:
            compression_strength = self._factor_to_strength(
                factors['compression_ratio'],
                neutral=1.0,
                strong_threshold=factors.get('compression_threshold', 2.0)
            )
            strengths.append(compression_strength)

        if 'volume_buildup' in factors:
            buildup_strength = self._factor_to_strength(
                factors['volume_buildup'],
                neutral=1.0,
                strong_threshold=1.2
            )
            strengths.append(buildup_strength)

        # Calculate confidence
        if len(strengths) == 0:
            return 0.0

        mean_strength = np.mean(strengths)
        std_strength = np.std(strengths)

        # Confidence: strong and consistent
        confidence = mean_strength * (1.0 - std_strength)

        return np.clip(confidence, 0.0, 1.0)

    def _factor_to_strength(
        self,
        value: float,
        neutral: float = 1.0,
        strong_threshold: float = 1.5
    ) -> float:
        """
        Convert factor value to 0~1 strength.

        Args:
            value: Factor value
            neutral: Neutral point (e.g., 1.0)
            strong_threshold: Strong signal threshold (e.g., 1.5)

        Returns:
            0.0 (weak) to 1.0 (strong)
        """
        if value >= neutral:
            # Strong direction
            strength = (value - neutral) / (strong_threshold - neutral)
            return min(1.0, strength)
        else:
            # Weak direction (below neutral)
            return 0.0
