"""A/B comparison of rotation strategies.

Compares weekly-only vs event-driven rotation strategies by computing
side-by-side performance metrics from trade results.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyMetrics:
    """Performance metrics for a rotation strategy."""

    label: str
    total_trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    avg_holding_days: float
    rotation_count: int


class RotationComparator:
    """Compares weekly-only vs event-driven rotation strategies."""

    def compute_metrics(
        self,
        label: str,
        trades: list[dict],
        rotation_count: int = 0,
    ) -> StrategyMetrics:
        """Compute performance metrics from trade records.

        Args:
            label: Strategy label (e.g., "weekly", "event_driven").
            trades: List of trade dicts with keys: pnl, equity_after, direction.
            rotation_count: Number of rotations performed.

        Returns:
            Frozen StrategyMetrics dataclass with computed values.
        """
        if not trades:
            return StrategyMetrics(
                label=label,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                total_pnl=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                avg_holding_days=0.0,
                rotation_count=rotation_count,
            )

        close_trades = [t for t in trades if t.get("direction") == "close"]
        pnls = [t["pnl"] for t in close_trades]

        if not pnls:
            return StrategyMetrics(
                label=label,
                total_trades=len(trades),
                win_rate=0.0,
                profit_factor=0.0,
                total_pnl=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                avg_holding_days=0.0,
                rotation_count=rotation_count,
            )

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) if pnls else 0.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Max drawdown from equity curve
        equities = [
            t["equity_after"]
            for t in trades
            if t.get("equity_after", 0) > 0
        ]
        max_dd = 0.0
        peak = equities[0] if equities else 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Annualized Sharpe ratio from trade PnLs
        if len(pnls) > 1:
            mean_pnl = total_pnl / len(pnls)
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
            std_pnl = variance ** 0.5
            sharpe = (mean_pnl / std_pnl) * (252 ** 0.5) if std_pnl > 0 else 0.0
        else:
            sharpe = 0.0

        return StrategyMetrics(
            label=label,
            total_trades=len(close_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_pnl=total_pnl,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            avg_holding_days=0.0,  # Would need entry/exit timestamps
            rotation_count=rotation_count,
        )

    def compare(
        self,
        weekly_trades: list[dict],
        event_trades: list[dict],
        weekly_rotations: int = 0,
        event_rotations: int = 0,
    ) -> dict:
        """Compare weekly vs event-driven rotation strategies.

        Args:
            weekly_trades: Trade results from weekly-only rotation.
            event_trades: Trade results from event-driven rotation.
            weekly_rotations: Number of weekly rotations performed.
            event_rotations: Number of event-driven rotations performed.

        Returns:
            Dict with 'weekly', 'event_driven' StrategyMetrics and 'winner' string.
        """
        weekly = self.compute_metrics("weekly", weekly_trades, weekly_rotations)
        event = self.compute_metrics("event_driven", event_trades, event_rotations)

        # Determine winner by composite score weighing PnL, Sharpe, and drawdown
        def _score(m: StrategyMetrics) -> float:
            return m.total_pnl * (1 + m.sharpe_ratio) * (1 - m.max_drawdown)

        w_score = _score(weekly)
        e_score = _score(event)

        if abs(w_score - e_score) < 0.01:
            winner = "tie"
        elif w_score > e_score:
            winner = "weekly"
        else:
            winner = "event_driven"

        return {
            "weekly": weekly,
            "event_driven": event,
            "winner": winner,
        }

    def format_comparison(self, result: dict) -> str:
        """Format comparison result as a human-readable table string.

        Args:
            result: Dict returned by compare().

        Returns:
            Formatted multi-line string for display.
        """
        weekly: StrategyMetrics = result["weekly"]
        event: StrategyMetrics = result["event_driven"]
        winner = result["winner"]

        lines = [
            "=" * 60,
            "  ROTATION STRATEGY A/B COMPARISON",
            "=" * 60,
            f"  {'Metric':<25} {'Weekly':>15} {'Event-Driven':>15}",
            f"  {'-' * 25} {'-' * 15} {'-' * 15}",
            f"  {'Total Trades':<25} {weekly.total_trades:>15} {event.total_trades:>15}",
            f"  {'Win Rate':<25} {weekly.win_rate:>14.1%} {event.win_rate:>14.1%}",
            f"  {'Profit Factor':<25} {weekly.profit_factor:>15.2f} {event.profit_factor:>15.2f}",
            f"  {'Total PnL':<25} ${weekly.total_pnl:>13,.2f} ${event.total_pnl:>13,.2f}",
            f"  {'Max Drawdown':<25} {weekly.max_drawdown:>14.1%} {event.max_drawdown:>14.1%}",
            f"  {'Sharpe Ratio':<25} {weekly.sharpe_ratio:>15.2f} {event.sharpe_ratio:>15.2f}",
            f"  {'Rotations':<25} {weekly.rotation_count:>15} {event.rotation_count:>15}",
            "",
            f"  Winner: {winner.upper()}",
            "=" * 60,
        ]
        return "\n".join(lines)
