from __future__ import annotations

from autotrader.universe import StockCandidate


class ProxyScorer:
    """6-factor proxy scoring for stock candidates.

    Factors (weights):
        LIQUIDITY (0.10): dollar volume percentile rank across candidates
        VOL_QUALITY (0.15): ATR ratio closeness to 2% ideal
        STRATEGY_COVERAGE (0.15): balance of trend_pct and range_pct
        GAP_SAFETY (0.20): low gap frequency
        EXECUTION_QUALITY (0.15): volume consistency (vol_cycle as CV)
        INCUMBENT_BONUS (0.15): existing pool membership
    """

    W_LIQUIDITY = 0.10
    W_VOL_QUALITY = 0.15
    W_STRATEGY_COVERAGE = 0.15
    W_GAP_SAFETY = 0.20
    W_EXECUTION_QUALITY = 0.15
    W_INCUMBENT = 0.15

    def score(
        self,
        candidates: list[StockCandidate],
        current_pool: list[str],
    ) -> list[float]:
        """Score candidates using 6-factor proxy model.

        Args:
            candidates: List of StockCandidate objects to score.
            current_pool: List of symbols currently in the portfolio.

        Returns:
            List of float scores in the same order as candidates.
        """
        if not candidates:
            return []

        dv_values = [c.avg_dollar_volume for c in candidates]
        dv_min = min(dv_values)
        dv_range = max(dv_values) - dv_min if len(dv_values) > 1 else 1.0

        scores: list[float] = []
        for c in candidates:
            liquidity = (c.avg_dollar_volume - dv_min) / dv_range if dv_range > 0 else 0.5

            vol_quality = max(0.0, 1.0 - abs(c.atr_ratio - 0.02) / 0.02)

            trend_s = min(1.0, c.trend_pct / 0.50)
            range_s = min(1.0, c.range_pct / 0.60)
            strategy_coverage = (trend_s + range_s) / 2

            gap_safety = max(0.0, 1.0 - c.gap_frequency / 0.15)

            vol_cv = c.vol_cycle
            execution = max(0.0, 1.0 - vol_cv / 1.5)

            incumbent = 1.0 if c.symbol in current_pool else 0.0

            total = (
                self.W_LIQUIDITY * liquidity
                + self.W_VOL_QUALITY * vol_quality
                + self.W_STRATEGY_COVERAGE * strategy_coverage
                + self.W_GAP_SAFETY * gap_safety
                + self.W_EXECUTION_QUALITY * execution
                + self.W_INCUMBENT * incumbent
            )
            scores.append(round(total, 6))

        return scores


class BacktestScorer:
    """Score candidates using backtest results from 5 strategies.

    Factors:
        activity (0.20): did strategies generate trades? min(1.0, total_trades / 10.0)
        win_rate (0.30): weighted average win rate, clamped to [0, 1]
        profit_factor (0.30): normalized profit factor, inf capped at 1.0
        diversity (0.20): how many strategies were active? strategies_active / 5.0
    """

    def score_from_metrics(
        self,
        total_trades: int,
        win_rate: float,
        profit_factor: float,
        strategies_active: int,
    ) -> float:
        """Compute backtest score from aggregated metrics.

        Args:
            total_trades: Total number of closed trades.
            win_rate: Win rate as a decimal (0.0 to 1.0).
            profit_factor: Ratio of gross profit to gross loss.
            strategies_active: Number of strategies that generated trades.

        Returns:
            Float score between 0.0 and 1.0.
        """
        if total_trades == 0:
            return 0.0

        activity = min(1.0, total_trades / 10.0)
        wr = max(0.0, min(1.0, win_rate))
        pf = min(1.0, profit_factor / 3.0) if profit_factor != float("inf") else 1.0
        diversity = strategies_active / 5.0

        return round(
            0.20 * activity + 0.30 * wr + 0.30 * pf + 0.20 * diversity,
            6,
        )
