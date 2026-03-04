"""Tests for the unified entry constraint checker.

Covers all nine constraint checks, the happy path, and priority order
(first failing check is the reported reason).
"""
from __future__ import annotations

import pytest

from autotrader.trading.entry_checker import EntryCheckResult, EntryConstraintChecker
from autotrader.trading.types import PositionInfo
from autotrader.trading.constants import (
    MAX_DAILY_ENTRIES,
    MAX_TOTAL_POSITIONS,
    MAX_LONG_POSITIONS,
    MAX_SHORT_POSITIONS,
    SOFT_STRATEGY_CAP,
    MAX_PORTFOLIO_HEAT_PCT,
    PORTFOLIO_SAFETY_NET_ENTRIES,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

checker = EntryConstraintChecker()


def _pos(
    symbol: str = "AAPL",
    strategy: str = "breakout_momentum",
    direction: str = "long",
    risk_pct: float = 0.02,
) -> PositionInfo:
    return PositionInfo(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        risk_pct=risk_pct,
    )


def _base_kwargs(**overrides) -> dict:
    """Return baseline kwargs for checker.check() with all constraints passing."""
    defaults = dict(
        symbol="TSLA",
        strategy="breakout_momentum",
        direction="long",
        open_positions=[],
        daily_entries_count=0,
        daily_strategy_entries={},
        closed_today=set(),
        gdr_tier=0,
        gdr_max_entries=1,
        safety_net_active=False,
        safety_net_entries_today=0,
        portfolio_heat=0.0,
    )
    defaults.update(overrides)
    return defaults


# ------------------------------------------------------------------
# 1. Portfolio heat limit (fail-fast)
# ------------------------------------------------------------------


class TestPortfolioHeatLimit:
    def test_blocked_at_heat_limit(self):
        result = checker.check(
            **_base_kwargs(portfolio_heat=MAX_PORTFOLIO_HEAT_PCT)
        )
        assert not result.allowed
        assert result.reason == "portfolio heat limit"

    def test_allowed_below_heat_limit(self):
        result = checker.check(
            **_base_kwargs(portfolio_heat=MAX_PORTFOLIO_HEAT_PCT - 0.01)
        )
        assert result.allowed


# ------------------------------------------------------------------
# 2. Re-entry block
# ------------------------------------------------------------------


class TestReentryBlock:
    def test_blocked_when_closed_today(self):
        result = checker.check(**_base_kwargs(closed_today={"TSLA"}))
        assert not result.allowed
        assert result.reason == "re-entry block"

    def test_allowed_when_different_symbol_closed(self):
        result = checker.check(**_base_kwargs(closed_today={"AAPL"}))
        assert result.allowed


# ------------------------------------------------------------------
# 3. Daily entry limit
# ------------------------------------------------------------------


class TestDailyEntryLimit:
    def test_blocked_at_limit(self):
        result = checker.check(
            **_base_kwargs(daily_entries_count=MAX_DAILY_ENTRIES)
        )
        assert not result.allowed
        assert result.reason == "daily entry limit"

    def test_allowed_below_limit(self):
        result = checker.check(
            **_base_kwargs(daily_entries_count=MAX_DAILY_ENTRIES - 1)
        )
        assert result.allowed


# ------------------------------------------------------------------
# 4. Total position cap
# ------------------------------------------------------------------


class TestTotalPositionCap:
    def test_blocked_at_cap(self):
        positions = [_pos(symbol=f"SYM{i}") for i in range(MAX_TOTAL_POSITIONS)]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert not result.allowed
        assert result.reason == "total position cap"

    def test_allowed_below_cap(self):
        # Mix directions and strategies so no other cap fires
        positions = [
            _pos(symbol="SYM0", direction="long", strategy="breakout_momentum"),
            _pos(symbol="SYM1", direction="long", strategy="rsi_mean_reversion"),
            _pos(symbol="SYM2", direction="short", strategy="rsi_mean_reversion"),
        ]
        assert len(positions) < MAX_TOTAL_POSITIONS
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert result.allowed


# ------------------------------------------------------------------
# 5. GDR daily entry limit
# ------------------------------------------------------------------


class TestGDRDailyEntryLimit:
    def test_blocked_when_strategy_entries_at_gdr_limit(self):
        result = checker.check(
            **_base_kwargs(
                daily_strategy_entries={"breakout_momentum": 1},
                gdr_max_entries=1,
            )
        )
        assert not result.allowed
        assert result.reason == "gdr strategy entry limit"

    def test_allowed_below_gdr_limit(self):
        result = checker.check(
            **_base_kwargs(
                daily_strategy_entries={"breakout_momentum": 0},
                gdr_max_entries=1,
            )
        )
        assert result.allowed

    def test_tier_2_zero_entries_blocks(self):
        result = checker.check(
            **_base_kwargs(
                daily_strategy_entries={"breakout_momentum": 0},
                gdr_max_entries=0,  # Tier 2: halted
            )
        )
        assert not result.allowed
        assert result.reason == "gdr strategy entry limit"


# ------------------------------------------------------------------
# 6. Safety net entry limit
# ------------------------------------------------------------------


class TestSafetyNetEntryLimit:
    def test_blocked_when_safety_net_entry_limit_reached(self):
        result = checker.check(
            **_base_kwargs(
                safety_net_active=True,
                safety_net_entries_today=PORTFOLIO_SAFETY_NET_ENTRIES,
            )
        )
        assert not result.allowed
        assert result.reason == "safety net entry limit"

    def test_allowed_when_safety_net_below_limit(self):
        result = checker.check(
            **_base_kwargs(
                safety_net_active=True,
                safety_net_entries_today=0,
            )
        )
        assert result.allowed

    def test_safety_net_inactive_does_not_block(self):
        """When safety net is inactive, its entry limit is irrelevant."""
        result = checker.check(
            **_base_kwargs(
                safety_net_active=False,
                safety_net_entries_today=999,
            )
        )
        assert result.allowed


# ------------------------------------------------------------------
# 7. Direction caps (max long, max short)
# ------------------------------------------------------------------


class TestDirectionCaps:
    def test_long_blocked_at_cap(self):
        # Spread across strategies so per-strategy cap does not fire first.
        # BM cap=2, MR cap=4 -> use 2 BM + 4 MR + 2 misc = 8 longs
        positions = (
            [_pos(symbol=f"BM{i}", direction="long", strategy="breakout_momentum") for i in range(2)]
            + [_pos(symbol=f"MR{i}", direction="long", strategy="rsi_mean_reversion") for i in range(4)]
            + [_pos(symbol=f"X{i}", direction="long", strategy=f"other_{i}") for i in range(MAX_LONG_POSITIONS - 6)]
        )
        assert len(positions) == MAX_LONG_POSITIONS
        result = checker.check(**_base_kwargs(open_positions=positions, direction="long"))
        assert not result.allowed
        assert result.reason == "max long positions"

    def test_short_blocked_at_cap(self):
        # Use different strategies so per-strategy cap is not hit
        positions = [
            _pos(symbol=f"SYM{i}", direction="short", strategy=f"strat_{i}")
            for i in range(MAX_SHORT_POSITIONS)
        ]
        result = checker.check(
            **_base_kwargs(
                open_positions=positions,
                direction="short",
                strategy="rsi_mean_reversion",
            )
        )
        assert not result.allowed
        assert result.reason == "max short positions"

    def test_long_allowed_when_short_at_cap(self):
        # Use different strategies so per-strategy cap is not hit
        positions = [
            _pos(symbol=f"SYM{i}", direction="short", strategy=f"strat_{i}")
            for i in range(MAX_SHORT_POSITIONS)
        ]
        result = checker.check(**_base_kwargs(open_positions=positions, direction="long"))
        assert result.allowed


# ------------------------------------------------------------------
# 8. Duplicate symbol block
# ------------------------------------------------------------------


class TestDuplicateSymbol:
    def test_blocked_when_already_holding(self):
        positions = [_pos(symbol="TSLA")]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert not result.allowed
        assert result.reason == "duplicate symbol"

    def test_allowed_when_different_symbol(self):
        positions = [_pos(symbol="AAPL")]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert result.allowed


# ------------------------------------------------------------------
# 9. Per-strategy position cap
# ------------------------------------------------------------------


class TestStrategyPositionCap:
    def test_blocked_at_cap(self):
        bm_cap = SOFT_STRATEGY_CAP.get("breakout_momentum", 2)
        positions = [
            _pos(symbol=f"BM{i}", strategy="breakout_momentum")
            for i in range(bm_cap)
        ]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert not result.allowed
        assert result.reason == "strategy position cap"

    def test_allowed_below_cap(self):
        positions = [_pos(symbol="BM0", strategy="breakout_momentum")]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert result.allowed

    def test_different_strategy_does_not_count(self):
        bm_cap = SOFT_STRATEGY_CAP.get("breakout_momentum", 2)
        positions = [
            _pos(symbol=f"MR{i}", strategy="rsi_mean_reversion")
            for i in range(bm_cap + 2)
        ]
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert result.allowed


# ------------------------------------------------------------------
# Happy path: all checks pass
# ------------------------------------------------------------------


class TestHappyPath:
    def test_all_checks_pass(self):
        result = checker.check(**_base_kwargs())
        assert result.allowed
        assert result.reason == ""

    def test_with_some_positions_still_allowed(self):
        positions = [
            _pos(symbol="AAPL", strategy="rsi_mean_reversion"),
            _pos(symbol="MSFT", strategy="breakout_momentum"),
        ]
        result = checker.check(
            **_base_kwargs(
                open_positions=positions,
                daily_entries_count=1,
                portfolio_heat=0.10,
            )
        )
        assert result.allowed


# ------------------------------------------------------------------
# Priority order: first failing check is the reason
# ------------------------------------------------------------------


class TestPriorityOrder:
    def test_heat_before_re_entry_block(self):
        """Heat (check 1) takes priority over re-entry block (check 2)."""
        result = checker.check(
            **_base_kwargs(
                portfolio_heat=MAX_PORTFOLIO_HEAT_PCT + 0.1,
                closed_today={"TSLA"},
            )
        )
        assert result.reason == "portfolio heat limit"

    def test_re_entry_block_before_daily_limit(self):
        """Re-entry (check 2) takes priority over daily limit (check 3)."""
        result = checker.check(
            **_base_kwargs(
                closed_today={"TSLA"},
                daily_entries_count=MAX_DAILY_ENTRIES,
            )
        )
        assert result.reason == "re-entry block"

    def test_daily_limit_before_total_cap(self):
        """Daily limit (check 3) before total cap (check 4)."""
        positions = [_pos(symbol=f"SYM{i}") for i in range(MAX_TOTAL_POSITIONS)]
        result = checker.check(
            **_base_kwargs(
                open_positions=positions,
                daily_entries_count=MAX_DAILY_ENTRIES,
            )
        )
        assert result.reason == "daily entry limit"

    def test_total_cap_before_gdr(self):
        """Total cap (check 4) before GDR entry limit (check 5)."""
        positions = [_pos(symbol=f"SYM{i}") for i in range(MAX_TOTAL_POSITIONS)]
        result = checker.check(
            **_base_kwargs(
                open_positions=positions,
                gdr_max_entries=0,
            )
        )
        assert result.reason == "total position cap"

    def test_gdr_before_safety_net(self):
        """GDR entry limit (check 5) before safety net (check 6)."""
        result = checker.check(
            **_base_kwargs(
                daily_strategy_entries={"breakout_momentum": 1},
                gdr_max_entries=1,
                safety_net_active=True,
                safety_net_entries_today=PORTFOLIO_SAFETY_NET_ENTRIES,
            )
        )
        assert result.reason == "gdr strategy entry limit"

    def test_safety_net_before_direction_cap(self):
        """Safety net (check 6) before direction cap (check 7)."""
        # Spread strategies to avoid strategy cap interference
        positions = (
            [_pos(symbol=f"BM{i}", direction="long", strategy="breakout_momentum") for i in range(2)]
            + [_pos(symbol=f"MR{i}", direction="long", strategy="rsi_mean_reversion") for i in range(4)]
            + [_pos(symbol=f"X{i}", direction="long", strategy=f"other_{i}") for i in range(MAX_LONG_POSITIONS - 6)]
        )
        assert len(positions) == MAX_LONG_POSITIONS
        result = checker.check(
            **_base_kwargs(
                open_positions=positions,
                direction="long",
                safety_net_active=True,
                safety_net_entries_today=PORTFOLIO_SAFETY_NET_ENTRIES,
            )
        )
        assert result.reason == "safety net entry limit"

    def test_direction_cap_before_duplicate(self):
        """Direction cap (check 7) before duplicate (check 8)."""
        # 8 long positions (= MAX_LONG), one of them is TSLA so duplicate
        # would also trigger, but direction cap fires first.
        # Spread strategies to avoid strategy cap.
        positions = (
            [_pos(symbol="TSLA", direction="long", strategy="rsi_mean_reversion")]
            + [_pos(symbol=f"BM{i}", direction="long", strategy="breakout_momentum") for i in range(2)]
            + [_pos(symbol=f"MR{i}", direction="long", strategy="rsi_mean_reversion") for i in range(3)]
            + [_pos(symbol=f"X{i}", direction="long", strategy=f"other_{i}") for i in range(MAX_LONG_POSITIONS - 6)]
        )
        assert len(positions) == MAX_LONG_POSITIONS
        result = checker.check(
            **_base_kwargs(open_positions=positions, direction="long")
        )
        assert result.reason == "max long positions"

    def test_duplicate_before_strategy_cap(self):
        """Duplicate (check 8) before strategy cap (check 9)."""
        bm_cap = SOFT_STRATEGY_CAP.get("breakout_momentum", 2)
        # Fill up strategy positions AND include the candidate symbol
        positions = [
            _pos(symbol="TSLA", strategy="breakout_momentum"),
        ]
        for i in range(bm_cap - 1):
            positions.append(_pos(symbol=f"BM{i}", strategy="breakout_momentum"))
        result = checker.check(**_base_kwargs(open_positions=positions))
        assert result.reason == "duplicate symbol"


# ------------------------------------------------------------------
# EntryCheckResult dataclass
# ------------------------------------------------------------------


class TestEntryCheckResult:
    def test_allowed_result(self):
        r = EntryCheckResult(allowed=True, reason="")
        assert r.allowed
        assert r.reason == ""

    def test_blocked_result(self):
        r = EntryCheckResult(allowed=False, reason="test reason")
        assert not r.allowed
        assert r.reason == "test reason"

    def test_frozen(self):
        r = EntryCheckResult(allowed=True, reason="")
        with pytest.raises(AttributeError):
            r.allowed = False  # type: ignore[misc]
