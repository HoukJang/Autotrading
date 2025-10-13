"""
Regime Detector Weight Optimizer

Optimizes indicator weights for regime detection accuracy.
"""

from typing import Dict, Tuple, List, Optional
import pandas as pd
import numpy as np
from scipy.optimize import minimize, differential_evolution
from dataclasses import dataclass

from .regime_detector import RegimeDetector, RegimeType


@dataclass
class OptimizationResult:
    """Result of weight optimization."""
    best_weights: Dict[str, float]
    best_score: float
    accuracy: float
    regime_counts: Dict[str, int]
    optimization_history: List[Dict]


class RegimeWeightOptimizer:
    """
    Optimize RegimeDetector weights for better accuracy.

    Supports multiple optimization methods:
    - Grid search: Exhaustive search over weight combinations
    - Differential evolution: Evolutionary algorithm for global optimization
    - Gradient-based: Fast local optimization
    """

    def __init__(
        self,
        detector_params: Dict = None,
        method: str = 'differential_evolution',
    ):
        """
        Initialize optimizer.

        Args:
            detector_params: Fixed parameters for RegimeDetector (non-weight params)
            method: Optimization method ('grid', 'differential_evolution', 'gradient')
        """
        self.detector_params = detector_params or {}
        self.method = method
        self.optimization_history = []

    def optimize(
        self,
        train_data: pd.DataFrame,
        true_regimes: pd.Series,
        weight_bounds: Dict[str, Tuple[float, float]] = None,
    ) -> OptimizationResult:
        """
        Optimize weights to match true regimes.

        Args:
            train_data: Historical OHLCV data
            true_regimes: Ground truth regime labels (same length as data)
            weight_bounds: Min/max bounds for each weight
                          e.g., {'weight_atr': (0.0, 1.0)}

        Returns:
            OptimizationResult with best weights and performance
        """
        # Default bounds: each weight between 0 and 1, sum to 1
        if weight_bounds is None:
            weight_bounds = {
                'weight_atr': (0.0, 0.5),
                'weight_r2': (0.0, 0.5),
                'weight_cvd': (0.0, 0.5),
                'weight_bb': (0.0, 0.3),
                'weight_snr': (0.0, 0.5),
            }

        # Select optimization method
        if self.method == 'differential_evolution':
            result = self._optimize_differential_evolution(
                train_data, true_regimes, weight_bounds
            )
        elif self.method == 'gradient':
            result = self._optimize_gradient(
                train_data, true_regimes, weight_bounds
            )
        elif self.method == 'grid':
            result = self._optimize_grid_search(
                train_data, true_regimes, weight_bounds
            )
        else:
            raise ValueError(f"Unknown method: {self.method}")

        return result

    def _optimize_differential_evolution(
        self,
        train_data: pd.DataFrame,
        true_regimes: pd.Series,
        weight_bounds: Dict[str, Tuple[float, float]],
    ) -> OptimizationResult:
        """Optimize using differential evolution (global optimization)."""
        # Prepare bounds for scipy
        weight_names = list(weight_bounds.keys())
        bounds = [weight_bounds[name] for name in weight_names]

        # Objective function
        def objective(weights):
            # Normalize weights to sum to 1
            weights = np.array(weights)
            weights = weights / weights.sum()

            # Create weight dict
            weight_dict = {name: w for name, w in zip(weight_names, weights)}

            # Calculate score (negative because we minimize)
            score = self._calculate_score(train_data, true_regimes, weight_dict)
            self.optimization_history.append({
                'weights': weight_dict.copy(),
                'score': score,
            })
            return -score  # Minimize negative = maximize positive

        # Run optimization
        result = differential_evolution(
            objective,
            bounds,
            maxiter=20,  # Reduced for speed
            popsize=10,  # Reduced for speed
            seed=42,
            workers=1,
        )

        # Extract best weights
        best_weights_array = result.x / result.x.sum()  # Normalize
        best_weights = {name: w for name, w in zip(weight_names, best_weights_array)}
        best_score = -result.fun

        # Calculate final metrics
        accuracy, regime_counts = self._evaluate_weights(
            train_data, true_regimes, best_weights
        )

        return OptimizationResult(
            best_weights=best_weights,
            best_score=best_score,
            accuracy=accuracy,
            regime_counts=regime_counts,
            optimization_history=self.optimization_history,
        )

    def _optimize_gradient(
        self,
        train_data: pd.DataFrame,
        true_regimes: pd.Series,
        weight_bounds: Dict[str, Tuple[float, float]],
    ) -> OptimizationResult:
        """Optimize using gradient-based method (fast local optimization)."""
        weight_names = list(weight_bounds.keys())
        bounds = [weight_bounds[name] for name in weight_names]

        # Initial guess (equal weights)
        x0 = np.ones(len(weight_names)) / len(weight_names)

        # Objective function
        def objective(weights):
            weights = np.array(weights)
            weights = weights / weights.sum()
            weight_dict = {name: w for name, w in zip(weight_names, weights)}
            score = self._calculate_score(train_data, true_regimes, weight_dict)
            self.optimization_history.append({
                'weights': weight_dict.copy(),
                'score': score,
            })
            return -score

        # Constraint: weights sum to 1
        constraints = {'type': 'eq', 'fun': lambda w: w.sum() - 1.0}

        # Run optimization
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
        )

        # Extract best weights
        best_weights_array = result.x / result.x.sum()
        best_weights = {name: w for name, w in zip(weight_names, best_weights_array)}
        best_score = -result.fun

        accuracy, regime_counts = self._evaluate_weights(
            train_data, true_regimes, best_weights
        )

        return OptimizationResult(
            best_weights=best_weights,
            best_score=best_score,
            accuracy=accuracy,
            regime_counts=regime_counts,
            optimization_history=self.optimization_history,
        )

    def _optimize_grid_search(
        self,
        train_data: pd.DataFrame,
        true_regimes: pd.Series,
        weight_bounds: Dict[str, Tuple[float, float]],
    ) -> OptimizationResult:
        """Optimize using grid search (exhaustive but slow)."""
        # Create grid (coarse for speed)
        grid_points = 5  # Points per dimension
        weight_names = list(weight_bounds.keys())

        # Generate grid
        grids = []
        for name in weight_names:
            low, high = weight_bounds[name]
            grids.append(np.linspace(low, high, grid_points))

        # Try all combinations
        best_score = -np.inf
        best_weights = None

        from itertools import product
        for weight_tuple in product(*grids):
            # Normalize to sum to 1
            weights_array = np.array(weight_tuple)
            weights_array = weights_array / weights_array.sum()

            weight_dict = {name: w for name, w in zip(weight_names, weights_array)}
            score = self._calculate_score(train_data, true_regimes, weight_dict)

            self.optimization_history.append({
                'weights': weight_dict.copy(),
                'score': score,
            })

            if score > best_score:
                best_score = score
                best_weights = weight_dict.copy()

        accuracy, regime_counts = self._evaluate_weights(
            train_data, true_regimes, best_weights
        )

        return OptimizationResult(
            best_weights=best_weights,
            best_score=best_score,
            accuracy=accuracy,
            regime_counts=regime_counts,
            optimization_history=self.optimization_history,
        )

    def _calculate_score(
        self,
        data: pd.DataFrame,
        true_regimes: pd.Series,
        weights: Dict[str, float],
    ) -> float:
        """
        Calculate accuracy score for given weights.

        Returns:
            Accuracy score (0.0 to 1.0)
        """
        # Create detector with these weights
        params = {**self.detector_params, **weights}
        detector = RegimeDetector(**params)

        # Reset detector state
        detector.reset()

        # Run detection
        predictions = []
        min_bars = max(
            detector.atr_window + detector.atr_lookback,
            detector.r2_window,
            detector.cvd_window,
            detector.bb_window,
            detector.snr_window,
        )

        for i in range(min_bars, len(data)):
            history = data.iloc[:i+1]
            result = detector.detect(history)
            predictions.append(result.regime.value)

        # Align predictions with true regimes
        true_aligned = true_regimes.iloc[min_bars:].values
        predictions = np.array(predictions)

        if len(predictions) == 0 or len(true_aligned) == 0:
            return 0.0

        # Calculate accuracy
        accuracy = (predictions == true_aligned).mean()

        return accuracy

    def _evaluate_weights(
        self,
        data: pd.DataFrame,
        true_regimes: pd.Series,
        weights: Dict[str, float],
    ) -> Tuple[float, Dict[str, int]]:
        """
        Evaluate weights and return detailed metrics.

        Returns:
            (accuracy, regime_counts)
        """
        params = {**self.detector_params, **weights}
        detector = RegimeDetector(**params)
        detector.reset()

        predictions = []
        min_bars = max(
            detector.atr_window + detector.atr_lookback,
            detector.r2_window,
            detector.cvd_window,
            detector.bb_window,
            detector.snr_window,
        )

        for i in range(min_bars, len(data)):
            history = data.iloc[:i+1]
            result = detector.detect(history)
            predictions.append(result.regime.value)

        true_aligned = true_regimes.iloc[min_bars:].values
        predictions = np.array(predictions)

        accuracy = (predictions == true_aligned).mean()

        # Count regimes
        unique, counts = np.unique(predictions, return_counts=True)
        regime_counts = {regime: count for regime, count in zip(unique, counts)}

        return accuracy, regime_counts
