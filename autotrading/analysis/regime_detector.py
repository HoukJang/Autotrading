"""
Regime Detection Module - Multi-Indicator Regime Detection

Detects market regime (TREND_UP, TREND_DOWN, RANGE) using:
1. ATR-based volatility expansion/compression
2. R²-based trend consistency (linear regression fit)
3. CVD-based flow analysis (cumulative volume delta)
4. Bollinger Band Width
5. SNR (Signal-to-Noise Ratio)
6. Price-CVD divergence
7. Composite scoring system with configurable weights
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np
from scipy import stats


class RegimeType(Enum):
    """Market regime types."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    NEUTRAL = "NEUTRAL"  # Uncertain state


@dataclass
class RegimeResult:
    """
    Detailed regime detection result.

    Attributes:
        regime: Current regime type
        confidence: Confidence score (0.0 to 1.0)
        trend_score: Composite trend score (-1.0 to 1.0)
        components: Breakdown of each indicator's contribution
        metadata: Additional debug/analysis information
    """
    regime: RegimeType
    confidence: float
    trend_score: float
    components: Dict[str, float]
    metadata: Dict[str, Any]


class RegimeDetector:
    """
    Market regime detector using multiple indicators.

    Phase 1 Implementation (ATR + R²):
    - ATR expansion/compression for volatility regime
    - R² (coefficient of determination) for trend consistency
    - Hysteresis to avoid regime flip-flopping

    Usage:
        detector = RegimeDetector(
            atr_window=14,
            atr_expansion_threshold=1.2,
            r2_window=120,
            r2_trend_threshold=0.6,
            r2_range_threshold=0.3,
            confirmation_bars=3
        )

        result = detector.detect(history_df)
        print(f"Regime: {result.regime.value}, Confidence: {result.confidence:.2f}")
    """

    def __init__(
        self,
        # ATR parameters
        atr_window: int = 14,
        atr_lookback: int = 20,  # Compare current ATR to ATR n bars ago
        atr_expansion_threshold: float = 1.2,  # ATR(t)/ATR(t-n) > 1.2 → expansion
        atr_compression_threshold: float = 0.8,  # < 0.8 → compression

        # R² parameters
        r2_window: int = 120,  # Window for linear regression (120 minutes = 2 hours)
        r2_trend_threshold: float = 0.6,  # R² > 0.6 → strong trend
        r2_range_threshold: float = 0.3,  # R² < 0.3 → range

        # CVD parameters
        cvd_window: int = 60,  # Window for CVD slope calculation
        cvd_trend_threshold: float = 2.0,  # |mean/std| > 2.0 → consistent flow

        # Bollinger Band parameters
        bb_window: int = 20,
        bb_std: float = 2.0,
        bb_compression_threshold: float = 0.015,  # Width < 1.5% → compression

        # SNR parameters
        snr_window: int = 120,
        snr_trend_threshold: float = 1.5,  # SNR > 1.5 → trend

        # Hysteresis parameters
        confirmation_bars: int = 3,  # Require N consecutive bars to confirm regime change

        # Composite score weights
        weight_atr: float = 0.2,
        weight_r2: float = 0.25,
        weight_cvd: float = 0.25,
        weight_bb: float = 0.1,
        weight_snr: float = 0.2,
    ):
        """
        Initialize regime detector.

        Args:
            atr_window: ATR calculation period
            atr_lookback: Compare current ATR to N bars ago
            atr_expansion_threshold: Ratio threshold for volatility expansion
            atr_compression_threshold: Ratio threshold for volatility compression
            r2_window: Window for linear regression
            r2_trend_threshold: R² threshold for trend regime
            r2_range_threshold: R² threshold for range regime
            cvd_window: Window for CVD slope calculation
            cvd_trend_threshold: |mean/std| threshold for consistent flow
            bb_window: Bollinger Band period
            bb_std: Bollinger Band standard deviations
            bb_compression_threshold: Band width threshold for compression
            snr_window: SNR calculation window
            snr_trend_threshold: SNR threshold for trend
            confirmation_bars: Bars needed to confirm regime change
            weight_atr: Weight for ATR component
            weight_r2: Weight for R² component
            weight_cvd: Weight for CVD component
            weight_bb: Weight for Bollinger Band component
            weight_snr: Weight for SNR component
        """
        # ATR config
        self.atr_window = atr_window
        self.atr_lookback = atr_lookback
        self.atr_expansion_threshold = atr_expansion_threshold
        self.atr_compression_threshold = atr_compression_threshold

        # R² config
        self.r2_window = r2_window
        self.r2_trend_threshold = r2_trend_threshold
        self.r2_range_threshold = r2_range_threshold

        # CVD config
        self.cvd_window = cvd_window
        self.cvd_trend_threshold = cvd_trend_threshold

        # Bollinger Band config
        self.bb_window = bb_window
        self.bb_std = bb_std
        self.bb_compression_threshold = bb_compression_threshold

        # SNR config
        self.snr_window = snr_window
        self.snr_trend_threshold = snr_trend_threshold

        # Hysteresis config
        self.confirmation_bars = confirmation_bars

        # Weights
        self.weight_atr = weight_atr
        self.weight_r2 = weight_r2
        self.weight_cvd = weight_cvd
        self.weight_bb = weight_bb
        self.weight_snr = weight_snr

        # State for hysteresis
        self._regime_history: list[RegimeType] = []
        self._confirmed_regime: Optional[RegimeType] = None

    def detect(self, history: pd.DataFrame) -> RegimeResult:
        """
        Detect current market regime.

        Args:
            history: DataFrame with OHLCV data (columns: open, high, low, close, volume)
                    Index should be datetime

        Returns:
            RegimeResult with detailed breakdown
        """
        # Validate input
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in history.columns for col in required_cols):
            raise ValueError(f"History must contain columns: {required_cols}")

        # Check minimum data requirement
        min_required = max(
            self.atr_window + self.atr_lookback,
            self.r2_window,
            self.cvd_window,
            self.bb_window,
            self.snr_window
        )

        if len(history) < min_required:
            # Not enough data
            return RegimeResult(
                regime=RegimeType.NEUTRAL,
                confidence=0.0,
                trend_score=0.0,
                components={},
                metadata={'error': 'insufficient_data', 'required': min_required}
            )

        # Calculate all components
        atr_score, atr_meta = self._calculate_atr_component(history)
        r2_score, r2_meta, slope = self._calculate_r2_component(history)
        cvd_score, cvd_meta = self._calculate_cvd_component(history)
        bb_score, bb_meta = self._calculate_bb_component(history)
        snr_score, snr_meta = self._calculate_snr_component(history)

        # Check for price-CVD divergence
        divergence_signal = self._check_divergence(history, cvd_meta['cvd'])

        # Composite score with all components
        trend_score = (
            self.weight_atr * atr_score +
            self.weight_r2 * r2_score +
            self.weight_cvd * cvd_score +
            self.weight_bb * bb_score +
            self.weight_snr * snr_score
        )

        # Apply divergence penalty if detected
        if divergence_signal != 0:
            # Divergence suggests regime transition or range
            trend_score *= 0.5  # Reduce confidence in current trend

        # Determine raw regime (before hysteresis)
        raw_regime = self._score_to_regime(trend_score, slope)

        # Apply hysteresis
        confirmed_regime, confidence = self._apply_hysteresis(raw_regime)

        # Build result
        return RegimeResult(
            regime=confirmed_regime,
            confidence=confidence,
            trend_score=trend_score,
            components={
                'atr_score': atr_score,
                'r2_score': r2_score,
                'cvd_score': cvd_score,
                'bb_score': bb_score,
                'snr_score': snr_score,
                'atr_ratio': atr_meta['atr_ratio'],
                'r2_value': r2_meta['r2'],
                'cvd_consistency': cvd_meta['consistency'],
                'bb_width_pct': bb_meta['width_pct'],
                'snr_value': snr_meta['snr'],
                'slope': slope,
                'divergence': divergence_signal,
            },
            metadata={
                'raw_regime': raw_regime.value,
                'confirmation_count': len([r for r in self._regime_history if r == raw_regime]),
                'atr_meta': atr_meta,
                'r2_meta': r2_meta,
                'cvd_meta': cvd_meta,
                'bb_meta': bb_meta,
                'snr_meta': snr_meta,
            }
        )

    def _calculate_atr_component(self, history: pd.DataFrame) -> tuple[float, dict]:
        """
        Calculate ATR-based volatility component.

        Returns:
            (atr_score, metadata)
            atr_score: -1.0 (compression/range) to 1.0 (expansion/trend)
        """
        # Calculate ATR
        high = history['high']
        low = history['low']
        close = history['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_window).mean()

        # Compare current ATR to past ATR
        current_atr = atr.iloc[-1]
        past_atr = atr.iloc[-self.atr_lookback]

        if past_atr == 0 or pd.isna(past_atr):
            atr_ratio = 1.0
        else:
            atr_ratio = current_atr / past_atr

        # Score calculation
        if atr_ratio >= self.atr_expansion_threshold:
            # Expansion → Trend
            atr_score = min(1.0, (atr_ratio - 1.0) / 0.5)  # Normalize
        elif atr_ratio <= self.atr_compression_threshold:
            # Compression → Range
            atr_score = max(-1.0, (atr_ratio - 1.0) / 0.5)  # Normalize
        else:
            # Neutral
            atr_score = 0.0

        metadata = {
            'atr_ratio': atr_ratio,
            'current_atr': current_atr,
            'past_atr': past_atr,
        }

        return atr_score, metadata

    def _calculate_r2_component(self, history: pd.DataFrame) -> tuple[float, dict, float]:
        """
        Calculate R²-based trend consistency component.

        Returns:
            (r2_score, metadata, slope)
            r2_score: -1.0 (range) to 1.0 (strong trend)
            slope: Linear regression slope (for direction)
        """
        # Get window for regression
        window_data = history['close'].iloc[-self.r2_window:]

        if len(window_data) < self.r2_window:
            return 0.0, {'r2': 0.0, 'slope': 0.0}, 0.0

        # Linear regression
        x = np.arange(len(window_data))
        y = window_data.values

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        r2 = r_value ** 2

        # Score calculation
        if r2 >= self.r2_trend_threshold:
            # Strong trend
            r2_score = min(1.0, (r2 - self.r2_trend_threshold) / (1.0 - self.r2_trend_threshold))
        elif r2 <= self.r2_range_threshold:
            # Range
            r2_score = max(-1.0, (r2 - self.r2_range_threshold) / self.r2_range_threshold)
        else:
            # Neutral zone
            # Linear interpolation between range and trend
            if r2 < (self.r2_range_threshold + self.r2_trend_threshold) / 2:
                # Closer to range
                r2_score = -0.5
            else:
                # Closer to trend
                r2_score = 0.5

        metadata = {
            'r2': r2,
            'slope': slope,
            'intercept': intercept,
            'p_value': p_value,
        }

        return r2_score, metadata, slope

    def _score_to_regime(self, trend_score: float, slope: float) -> RegimeType:
        """
        Convert trend score to regime type.

        Args:
            trend_score: Composite score (-1.0 to 1.0)
            slope: Linear regression slope (for direction)

        Returns:
            RegimeType
        """
        # Thresholds for regime classification
        trend_threshold = 0.2  # |score| > 0.2 → trend (more sensitive)
        range_threshold = -0.3  # score < -0.3 → range

        if trend_score > trend_threshold:
            # Trend regime - use slope to determine direction
            if slope > 0:
                return RegimeType.TREND_UP
            else:
                return RegimeType.TREND_DOWN
        elif trend_score < range_threshold:
            # Range regime
            return RegimeType.RANGE
        else:
            # Neutral (uncertain)
            return RegimeType.NEUTRAL

    def _apply_hysteresis(self, raw_regime: RegimeType) -> tuple[RegimeType, float]:
        """
        Apply hysteresis to avoid regime flip-flopping.

        Requires N consecutive bars of same regime to confirm change.

        Args:
            raw_regime: Current bar's regime

        Returns:
            (confirmed_regime, confidence)
        """
        # Add to history
        self._regime_history.append(raw_regime)

        # Keep only recent history
        max_history = self.confirmation_bars * 2
        if len(self._regime_history) > max_history:
            self._regime_history = self._regime_history[-max_history:]

        # Check if we have enough consecutive bars
        if len(self._regime_history) < self.confirmation_bars:
            # Not enough history - return previous confirmed or NEUTRAL
            confidence = len(self._regime_history) / self.confirmation_bars
            return self._confirmed_regime or RegimeType.NEUTRAL, confidence

        # Count consecutive occurrences of raw_regime
        consecutive_count = 0
        for regime in reversed(self._regime_history):
            if regime == raw_regime:
                consecutive_count += 1
            else:
                break

        # Check if confirmed
        if consecutive_count >= self.confirmation_bars:
            # Regime confirmed
            self._confirmed_regime = raw_regime
            confidence = min(1.0, consecutive_count / self.confirmation_bars)
            return raw_regime, confidence
        else:
            # Not confirmed yet - keep previous
            confidence = consecutive_count / self.confirmation_bars
            return self._confirmed_regime or RegimeType.NEUTRAL, confidence

    def _calculate_cvd_component(self, history: pd.DataFrame) -> tuple[float, dict]:
        """
        Calculate CVD-based flow component.

        CVD approximation: cumsum(volume * sign(close - open))
        Consistency: |mean(ΔCVD)| / std(ΔCVD)

        Returns:
            (cvd_score, metadata)
            cvd_score: -1.0 (mixed flow/range) to 1.0 (consistent flow/trend)
        """
        # Calculate CVD approximation
        price_direction = np.sign(history['close'] - history['open'])
        cvd = (history['volume'] * price_direction).cumsum()

        # Get window for analysis
        if len(cvd) < self.cvd_window:
            return 0.0, {'cvd': cvd, 'consistency': 0.0, 'mean_slope': 0.0}

        cvd_window = cvd.iloc[-self.cvd_window:]

        # Calculate CVD slope (first difference)
        cvd_delta = cvd_window.diff().dropna()

        if len(cvd_delta) == 0:
            return 0.0, {'cvd': cvd, 'consistency': 0.0, 'mean_slope': 0.0}

        # Mean and std of CVD changes
        mean_slope = cvd_delta.mean()
        std_slope = cvd_delta.std()

        # Consistency ratio: |mean| / std
        if std_slope == 0 or pd.isna(std_slope):
            consistency = 0.0
        else:
            consistency = abs(mean_slope) / std_slope

        # Score calculation
        if consistency >= self.cvd_trend_threshold:
            # High consistency → trend
            cvd_score = min(1.0, consistency / (self.cvd_trend_threshold * 2))
        else:
            # Low consistency → range
            cvd_score = max(-1.0, (consistency - self.cvd_trend_threshold) / self.cvd_trend_threshold)

        metadata = {
            'cvd': cvd,
            'consistency': consistency,
            'mean_slope': mean_slope,
            'std_slope': std_slope,
        }

        return cvd_score, metadata

    def _calculate_bb_component(self, history: pd.DataFrame) -> tuple[float, dict]:
        """
        Calculate Bollinger Band Width component.

        Width = (upper - lower) / middle
        Compression → range regime
        Expansion → trend regime

        Returns:
            (bb_score, metadata)
            bb_score: -1.0 (compression/range) to 1.0 (expansion/trend)
        """
        close = history['close']

        if len(close) < self.bb_window:
            return 0.0, {'width_pct': 0.0, 'upper': 0.0, 'lower': 0.0, 'middle': 0.0}

        # Calculate Bollinger Bands
        middle = close.rolling(window=self.bb_window).mean()
        std = close.rolling(window=self.bb_window).std()
        upper = middle + (self.bb_std * std)
        lower = middle - (self.bb_std * std)

        # Current values
        current_middle = middle.iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]

        # Band width as percentage of middle
        if current_middle == 0 or pd.isna(current_middle):
            width_pct = 0.0
        else:
            width_pct = (current_upper - current_lower) / current_middle

        # Score calculation
        if width_pct <= self.bb_compression_threshold:
            # Compression → range
            bb_score = max(-1.0, (width_pct - self.bb_compression_threshold) / self.bb_compression_threshold)
        else:
            # Expansion → trend
            bb_score = min(1.0, (width_pct - self.bb_compression_threshold) / 0.05)  # Normalize to 0.05 width

        metadata = {
            'width_pct': width_pct,
            'upper': current_upper,
            'lower': current_lower,
            'middle': current_middle,
        }

        return bb_score, metadata

    def _calculate_snr_component(self, history: pd.DataFrame) -> tuple[float, dict]:
        """
        Calculate SNR (Signal-to-Noise Ratio) component.

        SNR = |slope| / std(residuals)
        High SNR → consistent trend
        Low SNR → noisy range

        Returns:
            (snr_score, metadata)
            snr_score: -1.0 (low SNR/range) to 1.0 (high SNR/trend)
        """
        window_data = history['close'].iloc[-self.snr_window:]

        if len(window_data) < self.snr_window:
            return 0.0, {'snr': 0.0, 'slope': 0.0, 'resid_std': 0.0}

        # Linear regression
        x = np.arange(len(window_data))
        y = window_data.values

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Calculate residuals
        y_pred = slope * x + intercept
        residuals = y - y_pred
        resid_std = np.std(residuals)

        # SNR calculation
        if resid_std == 0:
            snr = 0.0
        else:
            snr = abs(slope) / resid_std

        # Score calculation
        if snr >= self.snr_trend_threshold:
            # High SNR → trend
            snr_score = min(1.0, snr / (self.snr_trend_threshold * 2))
        else:
            # Low SNR → range
            snr_score = max(-1.0, (snr - self.snr_trend_threshold) / self.snr_trend_threshold)

        metadata = {
            'snr': snr,
            'slope': slope,
            'resid_std': resid_std,
        }

        return snr_score, metadata

    def _check_divergence(self, history: pd.DataFrame, cvd: pd.Series) -> int:
        """
        Check for price-CVD divergence.

        Returns:
            1: Bullish divergence (price down, CVD up) → trend reversal up
            -1: Bearish divergence (price up, CVD down) → trend reversal down
            0: No divergence
        """
        # Need at least 20 bars for divergence check
        if len(history) < 20 or len(cvd) < 20:
            return 0

        # Get recent data
        recent_close = history['close'].iloc[-20:]
        recent_cvd = cvd.iloc[-20:]

        # Calculate trends (simple: first half vs second half)
        close_first_half = recent_close.iloc[:10].mean()
        close_second_half = recent_close.iloc[-10:].mean()
        price_trend = close_second_half - close_first_half

        cvd_first_half = recent_cvd.iloc[:10].mean()
        cvd_second_half = recent_cvd.iloc[-10:].mean()
        cvd_trend = cvd_second_half - cvd_first_half

        # Check for divergence
        if price_trend < 0 and cvd_trend > 0:
            # Bullish divergence
            return 1
        elif price_trend > 0 and cvd_trend < 0:
            # Bearish divergence
            return -1
        else:
            # No divergence
            return 0

    def reset(self):
        """Reset detector state (useful for new backtest runs)."""
        self._regime_history = []
        self._confirmed_regime = None
