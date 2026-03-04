"""Unified entry constraint checker.

Pure-logic evaluation of all pre-entry constraints.  No IO, no broker
calls, no async.  Designed to replace the scattered constraint checks in:

- Live:     autotrader.execution.entry_manager._can_enter
- Backtest: batch_simulator._execute_pending_entries (constraint section)

Both systems can call ``EntryConstraintChecker.check()`` with lightweight
data and receive a deterministic allow/deny verdict.
"""
from __future__ import annotations

from dataclasses import dataclass

from autotrader.trading.constants import (
    MAX_DAILY_ENTRIES,
    MAX_LONG_POSITIONS,
    MAX_SHORT_POSITIONS,
    MAX_TOTAL_POSITIONS,
    MAX_PORTFOLIO_HEAT_PCT,
    SOFT_STRATEGY_CAP,
    DEFAULT_STRATEGY_CAP,
)
from autotrader.trading.types import PositionInfo


@dataclass(frozen=True, slots=True)
class EntryCheckResult:
    """Outcome of an entry constraint evaluation.

    Attributes:
        allowed: ``True`` if the entry may proceed.
        reason: Empty string when allowed; a short descriptive reason
            when blocked (e.g. ``"re-entry block"``).
    """

    allowed: bool
    reason: str


class EntryConstraintChecker:
    """Pure-logic entry constraint evaluation.

    Stateless -- all state is passed in via the ``check`` call.  This
    makes it trivially testable and safe to share across live and
    backtest contexts.

    Constraint evaluation order (first failure wins):

    1. Portfolio heat limit (``MAX_PORTFOLIO_HEAT_PCT``) -- fail-fast on overexposure.
    2. Re-entry block (symbol closed today).
    3. Portfolio daily entry limit (``MAX_DAILY_ENTRIES``).
    4. Total position cap (``MAX_TOTAL_POSITIONS``).
    5. GDR per-strategy daily entry limit.
    6. Safety net entry limit.
    7. Direction caps (``MAX_LONG_POSITIONS`` / ``MAX_SHORT_POSITIONS``).
    8. Already holding the symbol.
    9. Per-strategy position cap (``SOFT_STRATEGY_CAP``).
    """

    def check(
        self,
        symbol: str,
        strategy: str,
        direction: str,
        # Current portfolio state
        open_positions: list[PositionInfo],
        daily_entries_count: int,
        daily_strategy_entries: dict[str, int],
        closed_today: set[str],
        # GDR state
        gdr_tier: int,
        gdr_max_entries: int,
        safety_net_active: bool,
        safety_net_entries_today: int,
        # Portfolio metrics
        portfolio_heat: float,
    ) -> EntryCheckResult:
        """Evaluate all entry constraints in priority order.

        Args:
            symbol: Ticker symbol of the candidate entry.
            strategy: Name of the strategy generating the signal.
            direction: ``"long"`` or ``"short"``.
            open_positions: List of lightweight position snapshots.
            daily_entries_count: Total entries executed so far today.
            daily_strategy_entries: Per-strategy entry counts today.
            closed_today: Set of symbols that were closed today
                (for re-entry blocking).
            gdr_tier: Current GDR tier for the strategy (0/1/2).
            gdr_max_entries: Max daily entries allowed by GDR for
                this strategy at its current tier.
            safety_net_active: Whether the portfolio safety net is on.
            safety_net_entries_today: Total entries made while the
                safety net has been active today.
            portfolio_heat: Current portfolio heat as a fraction of
                equity (0.0 -- 1.0).

        Returns:
            ``EntryCheckResult`` with ``allowed=True`` if all checks
            pass, or ``allowed=False`` with a descriptive ``reason``
            for the first failing constraint.
        """

        # 1. Portfolio heat limit (fail-fast: skip all other checks when
        #    the portfolio is already overexposed)
        if portfolio_heat >= MAX_PORTFOLIO_HEAT_PCT:
            return EntryCheckResult(False, "portfolio heat limit")

        # 2. Re-entry block: symbol was closed today
        if symbol in closed_today:
            return EntryCheckResult(False, "re-entry block")

        # 3. Portfolio daily entry limit
        if daily_entries_count >= MAX_DAILY_ENTRIES:
            return EntryCheckResult(False, "daily entry limit")

        # 4. Total position cap
        total_count = len(open_positions)
        if total_count >= MAX_TOTAL_POSITIONS:
            return EntryCheckResult(False, "total position cap")

        # 5. GDR per-strategy daily entry limit
        strat_entries = daily_strategy_entries.get(strategy, 0)
        if strat_entries >= gdr_max_entries:
            return EntryCheckResult(False, "gdr strategy entry limit")

        # 6. Safety net entry limit
        if safety_net_active:
            from autotrader.trading.constants import PORTFOLIO_SAFETY_NET_ENTRIES

            if safety_net_entries_today >= PORTFOLIO_SAFETY_NET_ENTRIES:
                return EntryCheckResult(False, "safety net entry limit")

        # 7. Direction caps
        long_count = sum(1 for p in open_positions if p.direction == "long")
        short_count = sum(1 for p in open_positions if p.direction == "short")
        if direction == "long" and long_count >= MAX_LONG_POSITIONS:
            return EntryCheckResult(False, "max long positions")
        if direction == "short" and short_count >= MAX_SHORT_POSITIONS:
            return EntryCheckResult(False, "max short positions")

        # 8. Already holding symbol
        if any(p.symbol == symbol for p in open_positions):
            return EntryCheckResult(False, "duplicate symbol")

        # 9. Per-strategy position cap
        strategy_count = sum(
            1 for p in open_positions if p.strategy == strategy
        )
        cap = SOFT_STRATEGY_CAP.get(strategy, DEFAULT_STRATEGY_CAP)
        if strategy_count >= cap:
            return EntryCheckResult(False, "strategy position cap")

        return EntryCheckResult(True, "")
