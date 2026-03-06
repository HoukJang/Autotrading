"""Per-strategy Graduated Drawdown Response (GDR) manager.

Thin wrapper around ``GDREngine`` from the unified trading core.
Preserves the existing public interface for the live trading system
while delegating all state management and tier computation to the
unified engine.

Matches Iter 29 backtest configuration exactly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# GDR constants imported from the SSOT module.
from autotrader.trading.constants import (
    GDR_STRATEGY_ENTRIES as _GDR_STRATEGY_ENTRIES,
    PORTFOLIO_SAFETY_NET_ENTRIES as _PORTFOLIO_SAFETY_NET_ENTRIES,
    PORTFOLIO_SAFETY_NET_RISK as _PORTFOLIO_SAFETY_NET_RISK,
)
from autotrader.trading.gdr_engine import GDREngine


class GDRManager:
    """Manages per-strategy drawdown tiers and portfolio safety net.

    Delegates all GDR logic to ``GDREngine`` from the unified trading
    core.  This wrapper adds live-specific daily entry tracking (which
    the unified engine does not manage).

    Tracks cumulative PnL per strategy independently. When a strategy's
    drawdown from its peak PnL exceeds tier thresholds, risk is reduced
    or entries are halted entirely.

    Portfolio Safety Net activates when total portfolio DD exceeds 12%,
    overriding all per-strategy GDR with ultra-conservative settings.
    """

    def __init__(self, strategy_names: list[str], initial_capital: float) -> None:
        self._initial_capital = initial_capital
        self._strategy_names = list(strategy_names)

        # Unified GDR engine handles tier computation and safety net
        self._engine = GDREngine(initial_capital=initial_capital)

        # Daily entry tracking (live-specific; not in unified engine)
        self._entries_today: dict[str, int] = {s: 0 for s in strategy_names}
        self._total_entries_today: int = 0

        # Per-strategy cumulative PnL (kept for get_strategy_pnl() accessor)
        self._cumulative_pnl: dict[str, float] = {s: 0.0 for s in strategy_names}

    def record_trade_pnl(self, strategy: str, pnl: float) -> None:
        """Update GDR state after a trade closes.

        Args:
            strategy: Name of the strategy that closed a trade.
            pnl: Realized PnL of the closed trade (positive = profit).
        """
        # Track cumulative PnL locally for the accessor
        if strategy in self._cumulative_pnl:
            self._cumulative_pnl[strategy] += pnl

        # Delegate tier computation and safety net to unified engine
        self._engine.record_trade_pnl(strategy, pnl)

    def get_risk_multiplier(self, strategy: str) -> float:
        """Get the GDR risk multiplier for a strategy.

        Returns 1.0 if safety net is active (safety net uses fixed risk,
        not a multiplier -- the AllocationEngine handles the override).
        """
        if self._engine.safety_net_active:
            return 1.0  # safety net uses fixed risk, not multiplier
        return self._engine.get_risk_multiplier(strategy)

    def can_enter_strategy(self, strategy: str) -> bool:
        """Check if strategy can enter based on GDR state and daily limits."""
        if self._engine.safety_net_active:
            return self._total_entries_today < _PORTFOLIO_SAFETY_NET_ENTRIES

        tier = self._engine.get_tier(strategy)
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
        return self._engine.safety_net_active

    @property
    def safety_net_risk(self) -> float:
        return _PORTFOLIO_SAFETY_NET_RISK

    def get_tier(self, strategy: str) -> int:
        return self._engine.get_tier(strategy)

    @property
    def _realized_pnl(self) -> float:
        """Expose realized PnL for backward compatibility (tests access this)."""
        return self._engine._realized_pnl

    @property
    def entries_today(self) -> dict[str, int]:
        return dict(self._entries_today)

    @property
    def total_entries_today(self) -> int:
        return self._total_entries_today

    def get_strategy_pnl(self, strategy: str) -> float:
        return self._cumulative_pnl.get(strategy, 0.0)
