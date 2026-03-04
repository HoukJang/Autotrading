"""Unified Graduated Drawdown Response (GDR) engine.

Provides per-strategy drawdown tracking and portfolio-level safety net
in a single, IO-free, deterministic module.  Designed to replace both:

- Live:     autotrader.risk.gdr_manager.GDRManager
- Backtest: batch_simulator._update_per_strategy_gdr / _update_portfolio_safety_net

All thresholds and multipliers are imported from the constants SSOT.
"""
from __future__ import annotations

import logging
from typing import Dict

from autotrader.trading.constants import (
    STRATEGY_GDR_THRESHOLDS,
    GDR_RISK_MULT,
    GDR_STRATEGY_ENTRIES,
    PORTFOLIO_SAFETY_NET_DD,
    PORTFOLIO_SAFETY_NET_RECOVERY,
    PORTFOLIO_SAFETY_NET_ENTRIES,
    PORTFOLIO_SAFETY_NET_RISK,
)

logger = logging.getLogger(__name__)


class GDREngine:
    """Graduated Drawdown Response -- per-strategy risk management.

    Tracks each strategy's cumulative PnL relative to initial capital and
    assigns drawdown tiers:

    - **Tier 0** -- Normal: full risk multiplier, full daily entries.
    - **Tier 1** -- Reduced: 50 % risk multiplier, 1 entry/day.
    - **Tier 2** -- Halted: 0 % risk, 0 entries.

    Also manages the Portfolio Safety Net which activates when total
    portfolio drawdown exceeds ``PORTFOLIO_SAFETY_NET_DD`` (12 %) and
    deactivates when it recovers below ``PORTFOLIO_SAFETY_NET_RECOVERY``
    (8 %).

    This class is **pure logic** -- no IO, no broker calls, no async.
    Both the live system and the backtester can share a single instance.
    """

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------

    def __init__(self, initial_capital: float = 0.0) -> None:
        """Initialise the engine.

        Args:
            initial_capital: Starting equity used as the denominator for
                per-strategy drawdown calculations.  If zero, drawdown
                fractions are reported as 0.0 (safe division).
        """
        self._initial_capital: float = initial_capital

        # Per-strategy cumulative PnL tracking
        self._strategy_cumulative_pnl: Dict[str, float] = {}
        self._strategy_peak_pnl: Dict[str, float] = {}
        self._strategy_tiers: Dict[str, int] = {}

        # Portfolio-level safety net
        self._portfolio_peak: float = initial_capital
        self._realized_pnl: float = 0.0
        self._safety_net_active: bool = False

    # -----------------------------------------------------------------
    # Core update
    # -----------------------------------------------------------------

    def update(
        self,
        strategy_equities: Dict[str, float],
        total_equity: float,
    ) -> None:
        """Recalculate GDR tiers from current equity levels.

        This is the **equity-snapshot** API: callers supply the current
        cumulative equity per strategy and the total portfolio equity.
        The engine derives drawdowns and assigns tiers.

        Args:
            strategy_equities: Mapping of strategy name to its current
                cumulative equity contribution (e.g. initial_share + PnL).
            total_equity: Current total portfolio equity (cash + positions).
        """
        for strategy, equity in strategy_equities.items():
            self._update_strategy_tier(strategy, equity)
        self._update_safety_net(total_equity)

    def record_trade_pnl(self, strategy: str, pnl: float) -> None:
        """Incremental update after a single trade closes.

        This is the **PnL-delta** API used when processing one trade at
        a time (the common live-trading pattern).

        Args:
            strategy: Name of the strategy that closed the trade.
            pnl: Realised dollar PnL of the closed trade.
        """
        # Ensure strategy is initialised
        if strategy not in self._strategy_cumulative_pnl:
            self._strategy_cumulative_pnl[strategy] = 0.0
            self._strategy_peak_pnl[strategy] = 0.0
            self._strategy_tiers[strategy] = 0

        self._strategy_cumulative_pnl[strategy] += pnl
        current = self._strategy_cumulative_pnl[strategy]

        # Update peak
        if current > self._strategy_peak_pnl[strategy]:
            self._strategy_peak_pnl[strategy] = current

        self._assign_strategy_tier(strategy)

        # Portfolio safety net via realised PnL delta
        self._realized_pnl += pnl
        realized_equity = self._initial_capital + self._realized_pnl
        self._update_safety_net(realized_equity)

    # -----------------------------------------------------------------
    # Query interface
    # -----------------------------------------------------------------

    def get_tier(self, strategy: str) -> int:
        """Return the current GDR tier for *strategy* (0, 1, or 2)."""
        return self._strategy_tiers.get(strategy, 0)

    def get_risk_multiplier(self, strategy: str) -> float:
        """Return the risk multiplier for *strategy* at its current tier.

        - Tier 0 -> 1.0
        - Tier 1 -> 0.5
        - Tier 2 -> 0.0

        When the safety net is active the multiplier is still returned
        per-tier; the caller should use ``get_effective_risk`` to obtain
        the final risk percentage that accounts for the safety-net
        override.
        """
        tier = self.get_tier(strategy)
        return GDR_RISK_MULT.get(tier, 1.0)

    def get_max_entries(self, strategy: str) -> int:
        """Return the max daily entries for *strategy* at its current tier."""
        if self._safety_net_active:
            return PORTFOLIO_SAFETY_NET_ENTRIES
        tier = self.get_tier(strategy)
        return GDR_STRATEGY_ENTRIES.get(tier, 1)

    @property
    def safety_net_active(self) -> bool:
        """Whether the portfolio-level safety net is currently active."""
        return self._safety_net_active

    def get_effective_risk(
        self,
        strategy: str,
        base_risk: float,
    ) -> float:
        """Return the effective risk fraction after GDR and safety-net.

        When the safety net is active, base risk is overridden to
        ``PORTFOLIO_SAFETY_NET_RISK``.  Otherwise, ``base_risk`` is
        scaled by the strategy's GDR tier multiplier.

        Args:
            strategy: Strategy name.
            base_risk: The regime/strategy base risk fraction (e.g. 0.02).

        Returns:
            Effective risk fraction to use for position sizing.
        """
        if self._safety_net_active:
            return PORTFOLIO_SAFETY_NET_RISK
        return base_risk * self.get_risk_multiplier(strategy)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _update_strategy_tier(self, strategy: str, equity: float) -> None:
        """Derive per-strategy tier from an absolute equity snapshot."""
        if strategy not in self._strategy_cumulative_pnl:
            self._strategy_cumulative_pnl[strategy] = 0.0
            self._strategy_peak_pnl[strategy] = 0.0
            self._strategy_tiers[strategy] = 0

        # Treat equity as cumulative PnL relative to an implied start of 0
        self._strategy_cumulative_pnl[strategy] = equity
        if equity > self._strategy_peak_pnl[strategy]:
            self._strategy_peak_pnl[strategy] = equity

        self._assign_strategy_tier(strategy)

    def _assign_strategy_tier(self, strategy: str) -> None:
        """Compute drawdown and assign the correct GDR tier."""
        current = self._strategy_cumulative_pnl[strategy]
        peak = self._strategy_peak_pnl[strategy]
        dd_dollars = peak - current
        dd_pct = (
            dd_dollars / self._initial_capital
            if self._initial_capital > 0
            else 0.0
        )
        dd_pct = max(0.0, dd_pct)

        thresholds = STRATEGY_GDR_THRESHOLDS.get(strategy, (0.04, 0.08))
        tier1_dd, tier2_dd = thresholds

        old_tier = self._strategy_tiers.get(strategy, 0)
        if dd_pct >= tier2_dd:
            new_tier = 2
        elif dd_pct >= tier1_dd:
            new_tier = 1
        else:
            new_tier = 0

        self._strategy_tiers[strategy] = new_tier
        if new_tier != old_tier:
            logger.info(
                "GDR tier change: %s tier %d -> %d "
                "(dd=%.2f%%, peak_pnl=%.0f, cum_pnl=%.0f)",
                strategy, old_tier, new_tier,
                dd_pct * 100, peak, current,
            )

    def _update_safety_net(self, total_equity: float) -> None:
        """Activate or deactivate the portfolio-level safety net."""
        if total_equity > self._portfolio_peak:
            self._portfolio_peak = total_equity

        if self._portfolio_peak <= 0:
            return

        dd = (self._portfolio_peak - total_equity) / self._portfolio_peak

        if not self._safety_net_active and dd >= PORTFOLIO_SAFETY_NET_DD:
            self._safety_net_active = True
            logger.warning(
                "SAFETY NET ACTIVATED: portfolio DD %.2f%% >= %.2f%%",
                dd * 100, PORTFOLIO_SAFETY_NET_DD * 100,
            )
        elif self._safety_net_active and dd < PORTFOLIO_SAFETY_NET_RECOVERY:
            self._safety_net_active = False
            logger.info(
                "Safety net deactivated: portfolio DD %.2f%% < %.2f%%",
                dd * 100, PORTFOLIO_SAFETY_NET_RECOVERY * 100,
            )
