"""Per-strategy Graduated Drawdown Response (GDR) manager.

Tracks cumulative PnL per strategy, assigns drawdown tiers,
and manages a portfolio-level safety net for extreme drawdowns.

Extracted from batch_simulator logic for live trading use.
Matches Iter 29 backtest configuration exactly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Per-strategy GDR thresholds: (tier1_dd, tier2_dd)
_STRATEGY_GDR_THRESHOLDS: dict[str, tuple[float, float]] = {
    "breakout_momentum": (0.04, 0.08),   # Tier1: 4% DD, Tier2: 8% DD (HALTED)
    "rsi_mean_reversion": (0.02, 0.04),  # Tier1: 2% DD, Tier2: 4% DD (HALTED)
}

# Risk multiplier per tier
_GDR_RISK_MULT: dict[int, float] = {
    0: 1.0,    # normal
    1: 0.5,    # reduced
    2: 0.0,    # HALTED (no entries)
}

# Entry limit per strategy per day (by tier)
_GDR_STRATEGY_ENTRIES: dict[int, int] = {
    0: 1,   # 1 entry per strategy per day
    1: 1,
    2: 0,   # halted
}

# Portfolio Safety Net
_PORTFOLIO_SAFETY_NET_DD: float = 0.12          # activate at 12% total DD
_PORTFOLIO_SAFETY_NET_RECOVERY: float = 0.08    # deactivate when DD < 8%
_PORTFOLIO_SAFETY_NET_ENTRIES: int = 1           # 1 entry total when active
_PORTFOLIO_SAFETY_NET_RISK: float = 0.005        # 0.5% risk when active


class GDRManager:
    """Manages per-strategy drawdown tiers and portfolio safety net.

    Tracks cumulative PnL per strategy independently. When a strategy's
    drawdown from its peak PnL exceeds tier thresholds, risk is reduced
    or entries are halted entirely.

    Portfolio Safety Net activates when total portfolio DD exceeds 12%,
    overriding all per-strategy GDR with ultra-conservative settings.
    """

    def __init__(self, strategy_names: list[str], initial_capital: float) -> None:
        self._initial_capital = initial_capital
        self._strategy_names = list(strategy_names)

        # Per-strategy PnL tracking
        self._cumulative_pnl: dict[str, float] = {s: 0.0 for s in strategy_names}
        self._peak_pnl: dict[str, float] = {s: 0.0 for s in strategy_names}
        self._gdr_tier: dict[str, int] = {s: 0 for s in strategy_names}

        # Daily entry tracking
        self._entries_today: dict[str, int] = {s: 0 for s in strategy_names}
        self._total_entries_today: int = 0

        # Portfolio safety net
        self._realized_pnl: float = 0.0
        self._peak_equity: float = initial_capital
        self._safety_net_active: bool = False

    def record_trade_pnl(self, strategy: str, pnl: float) -> None:
        """Update GDR state after a trade closes.

        Args:
            strategy: Name of the strategy that closed a trade.
            pnl: Realized PnL of the closed trade (positive = profit).
        """
        # Update per-strategy tracking
        if strategy in self._cumulative_pnl:
            self._cumulative_pnl[strategy] += pnl
            current = self._cumulative_pnl[strategy]

            # Update peak
            if current > self._peak_pnl[strategy]:
                self._peak_pnl[strategy] = current

            # Calculate DD and assign tier
            peak = self._peak_pnl[strategy]
            dd = (peak - current) / self._initial_capital if self._initial_capital > 0 else 0.0

            thresholds = _STRATEGY_GDR_THRESHOLDS.get(strategy, (0.04, 0.08))
            tier1, tier2 = thresholds

            old_tier = self._gdr_tier[strategy]
            if dd >= tier2:
                new_tier = 2
            elif dd >= tier1:
                new_tier = 1
            else:
                new_tier = 0

            self._gdr_tier[strategy] = new_tier
            if new_tier != old_tier:
                logger.info(
                    "GDR tier change: %s tier %d -> %d (dd=%.2f%%, pnl=$%.2f)",
                    strategy, old_tier, new_tier, dd * 100, current,
                )

        # Update portfolio-level tracking
        self._realized_pnl += pnl
        realized_equity = self._initial_capital + self._realized_pnl
        if realized_equity > self._peak_equity:
            self._peak_equity = realized_equity

        self._update_safety_net()

    def _update_safety_net(self) -> None:
        """Check portfolio drawdown for safety net activation/deactivation."""
        realized_equity = self._initial_capital + self._realized_pnl
        if self._peak_equity <= 0:
            return

        dd = (self._peak_equity - realized_equity) / self._peak_equity

        if not self._safety_net_active and dd >= _PORTFOLIO_SAFETY_NET_DD:
            self._safety_net_active = True
            logger.warning(
                "SAFETY NET ACTIVATED: portfolio DD %.2f%% >= %.2f%%",
                dd * 100, _PORTFOLIO_SAFETY_NET_DD * 100,
            )
        elif self._safety_net_active and dd < _PORTFOLIO_SAFETY_NET_RECOVERY:
            self._safety_net_active = False
            logger.info(
                "Safety net deactivated: portfolio DD %.2f%% < %.2f%%",
                dd * 100, _PORTFOLIO_SAFETY_NET_RECOVERY * 100,
            )

    def get_risk_multiplier(self, strategy: str) -> float:
        """Get the GDR risk multiplier for a strategy.

        Returns 1.0 if safety net is active (safety net uses fixed risk,
        not a multiplier -- the AllocationEngine handles the override).
        """
        if self._safety_net_active:
            return 1.0  # safety net uses fixed risk, not multiplier
        return _GDR_RISK_MULT.get(self._gdr_tier.get(strategy, 0), 1.0)

    def can_enter_strategy(self, strategy: str) -> bool:
        """Check if strategy can enter based on GDR state and daily limits."""
        if self._safety_net_active:
            return self._total_entries_today < _PORTFOLIO_SAFETY_NET_ENTRIES

        tier = self._gdr_tier.get(strategy, 0)
        entry_limit = _GDR_STRATEGY_ENTRIES.get(tier, 1)
        entries_so_far = self._entries_today.get(strategy, 0)
        return entries_so_far < entry_limit

    def record_entry(self, strategy: str) -> None:
        """Record that an entry was made for a strategy today."""
        self._entries_today[strategy] = self._entries_today.get(strategy, 0) + 1
        self._total_entries_today += 1

    def reset_daily_entries(self) -> None:
        """Reset daily entry counters (call at start of each trading day)."""
        for s in self._entries_today:
            self._entries_today[s] = 0
        self._total_entries_today = 0

    @property
    def is_safety_net_active(self) -> bool:
        return self._safety_net_active

    @property
    def safety_net_risk(self) -> float:
        return _PORTFOLIO_SAFETY_NET_RISK

    def get_tier(self, strategy: str) -> int:
        return self._gdr_tier.get(strategy, 0)

    def get_strategy_pnl(self, strategy: str) -> float:
        return self._cumulative_pnl.get(strategy, 0.0)
