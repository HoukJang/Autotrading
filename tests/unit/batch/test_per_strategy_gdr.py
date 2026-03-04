"""Unit tests for Per-Strategy GDR in BatchBacktester.

Tests cover:
- Per-strategy cumulative PnL tracking and drawdown calculation
- Per-strategy GDR tier transitions (Tier 0 -> 1 -> 2)
- Per-strategy entry limits enforcement
- Strategy-specific base risk sizing
- Portfolio safety net activation and deactivation
- Backward compatibility with legacy portfolio-level GDR
- _calculate_qty integration with per-strategy risk
- GDR risk multiplier application per strategy
"""
from __future__ import annotations

from collections import deque
from datetime import date

import pytest

from autotrader.backtest.batch_simulator import (
    BatchBacktester,
    _DEFAULT_BASE_RISK,
    _GDR_LEGACY_RISK_MULT,
    _GDR_MAX_ENTRIES,
    _GDR_RISK_MULT,
    _GDR_STRATEGY_ENTRIES,
    _GDR_TIER1_DD,
    _GDR_TIER2_DD,
    _MAX_DAILY_ENTRIES,
    _PER_STRATEGY_GDR,
    _PORTFOLIO_SAFETY_NET_DD,
    _PORTFOLIO_SAFETY_NET_ENTRIES,
    _PORTFOLIO_SAFETY_NET_RECOVERY,
    _PORTFOLIO_SAFETY_NET_RISK,
    _RISK_PER_TRADE_PCT,
    _STRATEGY_BASE_RISK,
    _STRATEGY_GDR_THRESHOLDS,
    _STRATEGY_NAMES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backtester(
    initial_capital: float = 100_000.0,
    use_per_strategy_gdr: bool = True,
) -> BatchBacktester:
    """Create a BatchBacktester with default settings for testing."""
    return BatchBacktester(
        initial_capital=initial_capital,
        use_per_strategy_gdr=use_per_strategy_gdr,
    )


# ---------------------------------------------------------------------------
# Test class: Constants validation
# ---------------------------------------------------------------------------

class TestPerStrategyGDRConstants:
    """Validate per-strategy GDR configuration constants."""

    def test_per_strategy_gdr_enabled_by_default(self):
        """_PER_STRATEGY_GDR should default to True."""
        assert _PER_STRATEGY_GDR is True

    def test_strategy_names_list(self):
        """_STRATEGY_NAMES should contain breakout_momentum and rsi_mean_reversion (Iter 29: 2-strategy)."""
        assert "breakout_momentum" in _STRATEGY_NAMES
        assert "rsi_mean_reversion" in _STRATEGY_NAMES
        assert "trend_pullback" not in _STRATEGY_NAMES
        assert "adaptive_mean_reversion" not in _STRATEGY_NAMES
        assert "consecutive_down" not in _STRATEGY_NAMES
        assert "ema_cross_trend" not in _STRATEGY_NAMES
        assert len(_STRATEGY_NAMES) == 2

    def test_strategy_base_risk_values(self):
        """Per-strategy base risk should match spec values (BM + MR, Iter 29)."""
        assert _STRATEGY_BASE_RISK["breakout_momentum"] == 0.020
        assert _STRATEGY_BASE_RISK["rsi_mean_reversion"] == 0.015
        assert "trend_pullback" not in _STRATEGY_BASE_RISK
        assert "adaptive_mean_reversion" not in _STRATEGY_BASE_RISK

    def test_default_base_risk(self):
        """Default base risk for unknown strategies should be 2%."""
        assert _DEFAULT_BASE_RISK == 0.02

    def test_strategy_gdr_thresholds(self):
        """Per-strategy GDR thresholds should match BM + MR spec (Iter 29)."""
        assert _STRATEGY_GDR_THRESHOLDS["breakout_momentum"] == (0.04, 0.08)
        assert _STRATEGY_GDR_THRESHOLDS["rsi_mean_reversion"] == (0.02, 0.04)
        assert "trend_pullback" not in _STRATEGY_GDR_THRESHOLDS
        assert "adaptive_mean_reversion" not in _STRATEGY_GDR_THRESHOLDS

    def test_gdr_risk_multipliers(self):
        """GDR risk multipliers: Tier 2 should halt (0.0)."""
        assert _GDR_RISK_MULT[0] == 1.0
        assert _GDR_RISK_MULT[1] == 0.5
        assert _GDR_RISK_MULT[2] == 0.0

    def test_gdr_strategy_entries(self):
        """Per-strategy entry limits per tier."""
        assert _GDR_STRATEGY_ENTRIES[0] == 1
        assert _GDR_STRATEGY_ENTRIES[1] == 1
        assert _GDR_STRATEGY_ENTRIES[2] == 0

    def test_max_daily_entries(self):
        """Portfolio-level daily cap should be 3 (2-strategy portfolio, Iter 29)."""
        assert _MAX_DAILY_ENTRIES == 3

    def test_portfolio_safety_net_thresholds(self):
        """Portfolio safety net config values (Iteration #26: reverted to Iter 23: 12% / 8%)."""
        assert _PORTFOLIO_SAFETY_NET_DD == 0.12
        assert _PORTFOLIO_SAFETY_NET_RECOVERY == 0.08
        assert _PORTFOLIO_SAFETY_NET_ENTRIES == 1
        assert _PORTFOLIO_SAFETY_NET_RISK == 0.005

    def test_legacy_gdr_risk_multipliers(self):
        """Legacy GDR risk multipliers: Tier 2 should be 0.25 (not halt)."""
        assert _GDR_LEGACY_RISK_MULT[0] == 1.0
        assert _GDR_LEGACY_RISK_MULT[1] == 0.5
        assert _GDR_LEGACY_RISK_MULT[2] == 0.25

    def test_legacy_gdr_max_entries(self):
        """Legacy GDR entry limits."""
        assert _GDR_MAX_ENTRIES[0] == 2
        assert _GDR_MAX_ENTRIES[1] == 1
        assert _GDR_MAX_ENTRIES[2] == 1


# ---------------------------------------------------------------------------
# Test class: Per-Strategy GDR state initialization
# ---------------------------------------------------------------------------

class TestPerStrategyGDRInit:
    """Test initial state of per-strategy GDR tracking."""

    def test_initial_cumulative_pnl_all_zero(self):
        """All strategies should start with 0 cumulative PnL."""
        bt = _make_backtester()
        for s in _STRATEGY_NAMES:
            assert bt._strategy_cumulative_pnl[s] == 0.0

    def test_initial_peak_pnl_all_zero(self):
        """All strategies should start with 0 peak PnL."""
        bt = _make_backtester()
        for s in _STRATEGY_NAMES:
            assert bt._strategy_peak_pnl[s] == 0.0

    def test_initial_gdr_tier_all_zero(self):
        """All strategies should start at Tier 0."""
        bt = _make_backtester()
        for s in _STRATEGY_NAMES:
            assert bt._strategy_gdr_tier[s] == 0

    def test_initial_entries_today_all_zero(self):
        """All strategies should start with 0 entries today."""
        bt = _make_backtester()
        for s in _STRATEGY_NAMES:
            assert bt._strategy_entries_today[s] == 0

    def test_initial_safety_net_inactive(self):
        """Portfolio safety net should start inactive."""
        bt = _make_backtester()
        assert bt._portfolio_safety_net_active is False

    def test_reset_clears_per_strategy_state(self):
        """_reset() should reinitialize all per-strategy GDR state."""
        bt = _make_backtester()
        # Mutate state
        bt._strategy_cumulative_pnl["breakout_momentum"] = -5000.0
        bt._strategy_peak_pnl["breakout_momentum"] = 2000.0
        bt._strategy_gdr_tier["breakout_momentum"] = 2
        bt._strategy_entries_today["breakout_momentum"] = 1
        bt._portfolio_safety_net_active = True
        # Reset
        bt._reset()
        for s in _STRATEGY_NAMES:
            assert bt._strategy_cumulative_pnl[s] == 0.0
            assert bt._strategy_peak_pnl[s] == 0.0
            assert bt._strategy_gdr_tier[s] == 0
            assert bt._strategy_entries_today[s] == 0
        assert bt._portfolio_safety_net_active is False


# ---------------------------------------------------------------------------
# Test class: _update_per_strategy_gdr
# ---------------------------------------------------------------------------

class TestUpdatePerStrategyGDR:
    """Test per-strategy GDR tier transitions based on cumulative PnL drawdown."""

    def test_positive_pnl_stays_tier0(self):
        """Winning trades should keep strategy at Tier 0."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("breakout_momentum", 500.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0
        assert bt._strategy_cumulative_pnl["breakout_momentum"] == 500.0
        assert bt._strategy_peak_pnl["breakout_momentum"] == 500.0

    def test_small_loss_stays_tier0(self):
        """Small loss within Tier 1 threshold stays Tier 0."""
        bt = _make_backtester(initial_capital=100_000)
        # breakout_momentum: Tier 1 threshold is 4% of 100K = $4000 DD
        bt._update_per_strategy_gdr("breakout_momentum", -3500.0)
        # DD = (0 - (-3500)) / 100K = 3.5% < 4% -> Tier 0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

    def test_breakout_momentum_tier1_at_4pct_dd(self):
        """Breakout Momentum: Tier 1 at 4% DD (Iter 25 threshold)."""
        bt = _make_backtester(initial_capital=100_000)
        # Lose $4100 -> DD = 4.1% > 4% threshold
        bt._update_per_strategy_gdr("breakout_momentum", -4100.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1

    def test_breakout_momentum_tier2_at_8pct_dd(self):
        """Breakout Momentum: Tier 2 (HALT) at 8% DD (Iter 25 threshold)."""
        bt = _make_backtester(initial_capital=100_000)
        # Lose $8100 -> DD = 8.1% > 8% threshold
        bt._update_per_strategy_gdr("breakout_momentum", -8100.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 2

    def test_dd_from_peak_not_from_zero(self):
        """Drawdown should be calculated from the peak PnL, not from zero."""
        bt = _make_backtester(initial_capital=100_000)
        # Win first, then lose: peak at +5000, then drop
        bt._update_per_strategy_gdr("breakout_momentum", 5000.0)
        assert bt._strategy_peak_pnl["breakout_momentum"] == 5000.0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

        # Now lose $11100: cum_pnl = -6100, peak = 5000, DD = 11100/100K = 11.1%
        bt._update_per_strategy_gdr("breakout_momentum", -11100.0)
        # DD = (5000 - (-6100)) / 100K = 11.1% > 6% -> Tier 2
        assert bt._strategy_cumulative_pnl["breakout_momentum"] == -6100.0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 2

    def test_recovery_back_to_tier0(self):
        """Strategy should recover to Tier 0 when losses are recouped."""
        bt = _make_backtester(initial_capital=100_000)
        # Drop to Tier 1 (loss $4100 = 4.1% DD > 4% threshold)
        bt._update_per_strategy_gdr("breakout_momentum", -4100.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1

        # Win enough to recover: cum_pnl = -4100 + 4100 = 0, peak stays at 0
        # DD = (0 - 0) / 100K = 0% -> Tier 0
        bt._update_per_strategy_gdr("breakout_momentum", 4100.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

    def test_independent_strategy_tracking(self):
        """GDR tracks independently per strategy; unknown strategy doesn't affect BM."""
        bt = _make_backtester(initial_capital=100_000)
        # Halt an unknown strategy (Tier 2 via default thresholds 4%/8%):
        # loss $8100 = 8.1% DD > 8% threshold -> Tier 2
        bt._update_per_strategy_gdr("some_other_strategy", -8100.0)
        assert bt._strategy_gdr_tier["some_other_strategy"] == 2

        # breakout_momentum should still be Tier 0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

        # Give breakout_momentum a win
        bt._update_per_strategy_gdr("breakout_momentum", 1000.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

    def test_unknown_strategy_initializes_on_fly(self):
        """An unknown strategy name should be initialized on the fly."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("unknown_strategy", -5000.0)
        assert "unknown_strategy" in bt._strategy_cumulative_pnl
        assert bt._strategy_cumulative_pnl["unknown_strategy"] == -5000.0


# ---------------------------------------------------------------------------
# Test class: Portfolio Safety Net
# ---------------------------------------------------------------------------

class TestPortfolioSafetyNet:
    """Test portfolio-level safety net activation/deactivation.

    NOTE: PSN now uses realized equity (initial_capital + realized_pnl) instead
    of MTM equity. Tests set _realized_pnl to simulate realized drawdowns.
    Safety net activates at 8% DD and deactivates when DD recovers below 5%.
    """

    @staticmethod
    def _seed_equity_history(bt: BatchBacktester, peak: float = 100_000.0) -> None:
        """Seed the equity history with a peak value so DD can be measured.

        For realized equity = peak, set _realized_pnl = peak - initial_capital.
        """
        bt._realized_pnl = peak - bt._initial_capital
        bt._update_portfolio_safety_net()  # records peak in history

    def test_safety_net_activates_at_12pct_dd(self):
        """Safety net should activate when realized DD exceeds 12% (Iter 26: reverted to Iter 23)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        self._seed_equity_history(bt, 100_000.0)
        # Simulate realized equity dropping to 87000 (13% below peak of 100K)
        bt._realized_pnl = -13_000.0  # realized_eq = 100K - 13K = 87K
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is True

    def test_safety_net_not_active_below_threshold(self):
        """Safety net should NOT activate below 12% DD (Iter 26: reverted to Iter 23)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        self._seed_equity_history(bt, 100_000.0)
        bt._realized_pnl = -11_000.0  # realized_eq = 89K, 11% DD < 12%
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is False

    def test_safety_net_deactivates_on_recovery(self):
        """Safety net should deactivate when realized DD recovers below 8% (Iter 26: reverted to Iter 23)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        self._seed_equity_history(bt, 100_000.0)
        # First activate it
        bt._realized_pnl = -13_000.0  # realized_eq = 87K, 13% DD > 12%
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is True

        # Recover to 7% DD (realized_eq = 93000, rolling peak is 100K)
        bt._realized_pnl = -7_000.0  # realized_eq = 93K, 7% < 8%
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is False

    def test_safety_net_stays_active_between_thresholds(self):
        """Safety net should stay active between 8% and 12% DD (hysteresis, Iter 26: reverted to Iter 23)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        self._seed_equity_history(bt, 100_000.0)
        # Activate at 13% DD
        bt._realized_pnl = -13_000.0  # realized_eq = 87K
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is True

        # Partially recover to 9% DD -- still above 8% recovery threshold
        bt._realized_pnl = -9_000.0  # realized_eq = 91K
        bt._update_portfolio_safety_net()
        assert bt._portfolio_safety_net_active is True


# ---------------------------------------------------------------------------
# Test class: _calculate_qty with per-strategy risk
# ---------------------------------------------------------------------------

class TestCalculateQtyPerStrategy:
    """Test position sizing with per-strategy base risk and GDR multipliers.

    NOTE: _MAX_POSITION_PCT = 25% caps qty at (equity * 0.25) / fill_price.
    To test the risk formula without hitting the position cap, use a low
    fill_price ($1) so the cap is very high (20,000 shares at $1 fill).
    """

    def test_breakout_momentum_uses_regime_risk(self):
        """Breakout Momentum should use regime-based risk (UNCERTAIN default = 0.8%)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        # UNCERTAIN regime: breakout_momentum = 0.008
        # risk = 100K * 0.8% * 1.0 = $800; qty = 800 / 2.0 = 400
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 400

    def test_gdr_tier1_halves_risk(self):
        """GDR Tier 1 multiplier (0.5) should halve position size."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        # UNCERTAIN regime: breakout_momentum = 0.008
        # risk = 100K * 0.8% * 0.5 = $400; qty = 400 / 2.0 = 200
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=0.5,
            strategy="breakout_momentum",
        )
        assert qty == 200

    def test_gdr_tier2_halts_entries(self):
        """GDR Tier 2 multiplier (0.0) should produce qty = 0."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=0.0,
            strategy="breakout_momentum",
        )
        assert qty == 0

    def test_safety_net_overrides_to_05pct_risk(self):
        """When safety net is active, risk should be 0.5% regardless of strategy."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        bt._portfolio_safety_net_active = True
        # risk = 100K * 0.5% = $500; qty = 500 / 2.0 = 250
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 250

    def test_safety_net_overrides_even_with_high_gdr_mult(self):
        """Safety net risk should ignore the GDR multiplier."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        bt._portfolio_safety_net_active = True
        # Safety net always uses 0.5% regardless of gdr_risk_mult
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=0.0,  # Would normally mean no entries
            strategy="breakout_momentum",
        )
        # risk = 100K * 0.5% = $500; qty = 500 / 2.0 = 250
        assert qty == 250

    def test_unknown_strategy_uses_default_base_risk(self):
        """An unknown strategy should use the default 2% base risk."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        # risk = 100K * 2% * 1.0 = $2000; qty = 2000 / 2.0 = 1000
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="unknown_strategy",
        )
        assert qty == 1000

    def test_position_cap_limits_large_risk_qty(self):
        """Position cap (25% of equity) should limit qty when risk formula gives more."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        # UNCERTAIN regime: breakout_momentum = 0.008
        # risk = 100K * 0.8% * 1.0 = $800; qty_by_risk = 800 / 2.0 = 400
        # pos cap = 100K * 25% / 100.0 = 250 (binding)
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=100.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 250  # capped by max position size


# ---------------------------------------------------------------------------
# Test class: Legacy portfolio-level GDR backward compatibility
# ---------------------------------------------------------------------------

class TestLegacyGDRBackwardCompat:
    """Test backward compatibility when _PER_STRATEGY_GDR is disabled."""

    @staticmethod
    def _seed_legacy_history(bt: BatchBacktester, peak: float = 100_000.0) -> None:
        """Seed equity history with peak so DD can be computed in legacy mode."""
        bt._equity = peak
        bt._update_gdr()  # appends peak to history

    def test_legacy_mode_uses_portfolio_gdr(self):
        """In legacy mode, _update_gdr should use portfolio-level tiers."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        self._seed_legacy_history(bt, 100_000.0)
        # Simulate 16% drawdown (> 15% Tier 1 threshold)
        bt._equity = 84_000.0
        bt._update_gdr()
        assert bt._gdr_tier == 1

    def test_legacy_mode_tier2_at_25pct_dd(self):
        """Legacy mode: Tier 2 at 25% DD."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        self._seed_legacy_history(bt, 100_000.0)
        bt._equity = 74_000.0
        bt._update_gdr()
        assert bt._gdr_tier == 2

    def test_legacy_mode_calculate_qty_uses_strategy_base_risk(self):
        """Legacy mode should still use per-strategy base risk for sizing."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        # Even in legacy mode, uses STRATEGY_BASE_RISK for the strategy
        # breakout_momentum base risk = 2.0%
        # risk = 100K * 2.0% * 1.0 = $2000; qty = 2000 / 2.0 = 1000
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 1000

    def test_legacy_mode_tier2_uses_025_multiplier(self):
        """Legacy Tier 2 multiplier should be 0.25, not 0.0 (not halted)."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        # With legacy mode, Tier 2 risk mult = 0.25
        # breakout_momentum base risk = 2.0%
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=1.0,
            stop_distance=2.0,
            gdr_risk_mult=_GDR_LEGACY_RISK_MULT[2],  # 0.25
            strategy="breakout_momentum",
        )
        # risk = 100K * 2.0% * 0.25 = $500; qty = 500 / 2.0 = 250
        assert qty == 250

    def test_legacy_mode_no_safety_net(self):
        """Legacy mode should not activate the portfolio safety net."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        self._seed_legacy_history(bt, 100_000.0)
        bt._equity = 79_000.0  # 21% DD
        bt._update_gdr()
        # Safety net is only for per-strategy mode; in legacy, just tiers
        assert bt._portfolio_safety_net_active is False
        assert bt._gdr_tier == 1  # Between 15% and 25%


# ---------------------------------------------------------------------------
# Test class: _update_gdr dispatch
# ---------------------------------------------------------------------------

class TestUpdateGDRDispatch:
    """Test that _update_gdr dispatches correctly based on mode."""

    def test_per_strategy_mode_dispatches_to_safety_net(self):
        """Per-strategy mode should call _update_portfolio_safety_net."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=True)
        # Seed history with peak (realized_pnl=0 -> realized_eq=100K)
        bt._realized_pnl = 0.0
        bt._update_gdr()
        # Now simulate realized loss that drops below safety net threshold (12%, Iter 26: reverted to Iter 23)
        bt._realized_pnl = -13_000.0  # realized_eq = 87K, 13% DD > 12%
        bt._update_gdr()
        # Should activate safety net (per-strategy mode checks portfolio DD)
        assert bt._portfolio_safety_net_active is True

    def test_legacy_mode_dispatches_to_legacy_gdr(self):
        """Legacy mode should call _update_legacy_gdr."""
        bt = _make_backtester(initial_capital=100_000, use_per_strategy_gdr=False)
        # Seed history with peak
        bt._equity = 100_000.0
        bt._update_gdr()
        # Now drop to 16% DD
        bt._equity = 84_000.0
        bt._update_gdr()
        assert bt._gdr_tier == 1
        assert bt._portfolio_safety_net_active is False


# ---------------------------------------------------------------------------
# Test class: Edge cases
# ---------------------------------------------------------------------------

class TestPerStrategyGDREdgeCases:
    """Edge cases for per-strategy GDR."""

    def test_zero_initial_capital_no_crash(self):
        """Zero initial capital should not cause division by zero."""
        bt = _make_backtester(initial_capital=0.0)
        bt._update_per_strategy_gdr("breakout_momentum", -100.0)
        # DD = 0 / 0 -> should be handled gracefully
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

    def test_very_small_loss_stays_tier0(self):
        """A $1 loss on 100K capital should stay at Tier 0."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("breakout_momentum", -1.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0

    def test_exact_threshold_boundary_tier1(self):
        """Exactly at the Tier 1 boundary should trigger Tier 1 (>= comparison)."""
        bt = _make_backtester(initial_capital=100_000)
        # breakout_momentum Tier 1 threshold = 4% of 100K = $4000 DD exactly
        bt._update_per_strategy_gdr("breakout_momentum", -4000.0)
        # DD = 4000/100K = 0.04, threshold is >= 0.04 -> Tier 1
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1

    def test_just_above_threshold_triggers_tier1(self):
        """Just above Tier 1 threshold should trigger Tier 1."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("breakout_momentum", -4001.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1

    def test_calculate_qty_zero_stop_distance(self):
        """Zero stop distance should return qty = 0."""
        bt = _make_backtester()
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=100.0,
            stop_distance=0.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 0

    def test_calculate_qty_zero_fill_price(self):
        """Zero fill price should return qty = 0."""
        bt = _make_backtester()
        qty = bt._calculate_qty(
            equity=100_000,
            fill_price=0.0,
            stop_distance=2.0,
            gdr_risk_mult=1.0,
            strategy="breakout_momentum",
        )
        assert qty == 0

    def test_multiple_losses_accumulate(self):
        """Multiple losses should accumulate in cumulative PnL."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("breakout_momentum", -2100.0)
        bt._update_per_strategy_gdr("breakout_momentum", -2000.0)
        # Total: -4100, DD = 4.1% > 4% -> Tier 1
        assert bt._strategy_cumulative_pnl["breakout_momentum"] == -4100.0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1

    def test_win_after_loss_reduces_dd(self):
        """A win after losses should reduce the drawdown."""
        bt = _make_backtester(initial_capital=100_000)
        bt._update_per_strategy_gdr("breakout_momentum", -4100.0)
        assert bt._strategy_gdr_tier["breakout_momentum"] == 1  # 4.1% DD > 4%

        bt._update_per_strategy_gdr("breakout_momentum", 3600.0)
        # cum_pnl = -500, peak = 0, DD = 500/100K = 0.5% -> Tier 0
        assert bt._strategy_cumulative_pnl["breakout_momentum"] == -500.0
        assert bt._strategy_gdr_tier["breakout_momentum"] == 0
