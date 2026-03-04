"""Tests for the unified GDR engine.

Covers per-strategy tier assignment, escalation/de-escalation, risk
multipliers, safety net activation/deactivation, effective risk
calculation, and strategy independence.
"""
from __future__ import annotations

import pytest

from autotrader.trading.gdr_engine import GDREngine
from autotrader.trading.constants import (
    STRATEGY_GDR_THRESHOLDS,
    GDR_RISK_MULT,
    GDR_STRATEGY_ENTRIES,
    PORTFOLIO_SAFETY_NET_DD,
    PORTFOLIO_SAFETY_NET_RECOVERY,
    PORTFOLIO_SAFETY_NET_RISK,
    PORTFOLIO_SAFETY_NET_ENTRIES,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

INITIAL_CAPITAL = 10_000.0


def _make_engine(capital: float = INITIAL_CAPITAL) -> GDREngine:
    return GDREngine(initial_capital=capital)


# ------------------------------------------------------------------
# Tier assignment based on drawdown thresholds
# ------------------------------------------------------------------


class TestTierAssignment:
    """Verify correct tier based on per-strategy drawdown."""

    def test_no_drawdown_is_tier_0(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", 100.0)
        assert engine.get_tier("breakout_momentum") == 0

    def test_tier_1_at_threshold(self):
        """BM tier-1 threshold is 4 % of initial capital = $400."""
        engine = _make_engine()
        # Peak at +100, then lose 500 -> dd = 500/10000 = 5 % > 4 %
        engine.record_trade_pnl("breakout_momentum", 100.0)
        engine.record_trade_pnl("breakout_momentum", -500.0)
        assert engine.get_tier("breakout_momentum") == 1

    def test_tier_2_at_threshold(self):
        """BM tier-2 threshold is 8 % = $800."""
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", 100.0)
        engine.record_trade_pnl("breakout_momentum", -1000.0)
        # dd = (100 - (-900)) / 10000 = 1000/10000 = 10 % > 8 %
        assert engine.get_tier("breakout_momentum") == 2

    def test_mr_lower_thresholds(self):
        """MR tier-1 at 2 %, tier-2 at 4 %."""
        engine = _make_engine()
        engine.record_trade_pnl("rsi_mean_reversion", 50.0)
        engine.record_trade_pnl("rsi_mean_reversion", -300.0)
        # dd = 350 / 10000 = 3.5 % > 2 % -> tier 1
        assert engine.get_tier("rsi_mean_reversion") == 1

    def test_mr_tier_2(self):
        engine = _make_engine()
        engine.record_trade_pnl("rsi_mean_reversion", 50.0)
        engine.record_trade_pnl("rsi_mean_reversion", -500.0)
        # dd = 550 / 10000 = 5.5 % > 4 % -> tier 2
        assert engine.get_tier("rsi_mean_reversion") == 2

    def test_unknown_strategy_uses_default_thresholds(self):
        """Unknown strategy gets default (0.04, 0.08) thresholds."""
        engine = _make_engine()
        engine.record_trade_pnl("unknown_strat", 10.0)
        engine.record_trade_pnl("unknown_strat", -500.0)
        # dd = 510/10000 = 5.1% > 4% -> tier 1
        assert engine.get_tier("unknown_strat") == 1

    def test_zero_initial_capital_stays_tier_0(self):
        """Division by zero is safe -- always tier 0."""
        engine = GDREngine(initial_capital=0.0)
        engine.record_trade_pnl("breakout_momentum", -500.0)
        assert engine.get_tier("breakout_momentum") == 0


# ------------------------------------------------------------------
# Tier escalation and de-escalation
# ------------------------------------------------------------------


class TestTierEscalationDeescalation:
    """Verify tier goes up on losses and back down on recovery."""

    def test_escalation_0_to_1_to_2(self):
        engine = _make_engine()
        assert engine.get_tier("breakout_momentum") == 0

        engine.record_trade_pnl("breakout_momentum", -500.0)
        # dd = 500/10000 = 5 % -> tier 1
        assert engine.get_tier("breakout_momentum") == 1

        engine.record_trade_pnl("breakout_momentum", -500.0)
        # dd = 1000/10000 = 10 % -> tier 2
        assert engine.get_tier("breakout_momentum") == 2

    def test_de_escalation_2_to_1_to_0(self):
        engine = _make_engine()
        # Push to tier 2
        engine.record_trade_pnl("breakout_momentum", -1000.0)
        assert engine.get_tier("breakout_momentum") == 2

        # Recover: +600 -> cumulative = -400, peak = 0, dd = 400/10000 = 4 %
        # 4 % == tier-1 threshold exactly, >= means tier 1
        engine.record_trade_pnl("breakout_momentum", 600.0)
        assert engine.get_tier("breakout_momentum") == 1

        # Push back to tier 1 with a small loss to test de-escalation path
        engine.record_trade_pnl("breakout_momentum", -200.0)
        # cumulative = -600, peak = 0, dd = 600/10000 = 6 % > 4 % -> tier 1
        assert engine.get_tier("breakout_momentum") == 1

        # Recover fully: +700 -> cumulative = +100, peak updates to +100, dd = 0 -> tier 0
        engine.record_trade_pnl("breakout_momentum", 700.0)
        assert engine.get_tier("breakout_momentum") == 0


# ------------------------------------------------------------------
# Risk multiplier per tier
# ------------------------------------------------------------------


class TestRiskMultiplier:
    """Verify the risk multiplier at each tier."""

    def test_tier_0_full_risk(self):
        engine = _make_engine()
        assert engine.get_risk_multiplier("breakout_momentum") == 1.0

    def test_tier_1_half_risk(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -500.0)
        assert engine.get_tier("breakout_momentum") == 1
        assert engine.get_risk_multiplier("breakout_momentum") == 0.5

    def test_tier_2_zero_risk(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1000.0)
        assert engine.get_tier("breakout_momentum") == 2
        assert engine.get_risk_multiplier("breakout_momentum") == 0.0

    def test_unknown_strategy_defaults_to_full_risk(self):
        engine = _make_engine()
        assert engine.get_risk_multiplier("nonexistent") == 1.0


# ------------------------------------------------------------------
# Safety net activation at 12 % DD
# ------------------------------------------------------------------


class TestSafetyNetActivation:
    """Portfolio safety net activates at 12 % DD from peak equity."""

    def test_safety_net_activates(self):
        engine = _make_engine()
        assert not engine.safety_net_active

        # Lose 13 % of 10000 = $1300
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        # total_equity = 10000 - 1300 = 8700
        # dd = (10000 - 8700) / 10000 = 13 % > 12 %
        assert engine.safety_net_active

    def test_safety_net_not_activated_below_threshold(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1100.0)
        # dd = 1100/10000 = 11 % < 12 %
        assert not engine.safety_net_active


# ------------------------------------------------------------------
# Safety net deactivation at 8 % DD recovery
# ------------------------------------------------------------------


class TestSafetyNetDeactivation:
    """Safety net deactivates when DD recovers below 8 %."""

    def test_safety_net_deactivates_on_recovery(self):
        engine = _make_engine()
        # Activate
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        assert engine.safety_net_active

        # Recover to DD < 8 %: need total equity > peak * (1 - 0.08)
        # peak = 10000, threshold = 9200.  Current: 10000 - 1300 = 8700.
        # Need to gain 501 to reach 9201 -> DD = (10000-9201)/10000 = 7.99%
        engine.record_trade_pnl("breakout_momentum", 501.0)
        assert not engine.safety_net_active

    def test_safety_net_stays_active_at_boundary(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        assert engine.safety_net_active

        # Recover to exactly 8 %: 10000 - 1300 + 500 = 9200
        # dd = (10000 - 9200)/10000 = 8 % -- NOT below 8 %, stays active
        engine.record_trade_pnl("breakout_momentum", 500.0)
        assert engine.safety_net_active


# ------------------------------------------------------------------
# get_effective_risk with GDR + safety net
# ------------------------------------------------------------------


class TestEffectiveRisk:
    """Test get_effective_risk combining GDR tiers and safety net."""

    def test_tier_0_normal_risk(self):
        engine = _make_engine()
        risk = engine.get_effective_risk("breakout_momentum", 0.02)
        assert risk == pytest.approx(0.02)

    def test_tier_1_reduced_risk(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -500.0)
        risk = engine.get_effective_risk("breakout_momentum", 0.02)
        assert risk == pytest.approx(0.01)

    def test_tier_2_zero_risk(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1000.0)
        risk = engine.get_effective_risk("breakout_momentum", 0.02)
        assert risk == pytest.approx(0.0)

    def test_safety_net_overrides_all(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        assert engine.safety_net_active
        risk = engine.get_effective_risk("breakout_momentum", 0.02)
        assert risk == pytest.approx(PORTFOLIO_SAFETY_NET_RISK)

    def test_safety_net_risk_regardless_of_strategy(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        assert engine.safety_net_active
        risk_bm = engine.get_effective_risk("breakout_momentum", 0.02)
        risk_mr = engine.get_effective_risk("rsi_mean_reversion", 0.015)
        assert risk_bm == risk_mr == PORTFOLIO_SAFETY_NET_RISK


# ------------------------------------------------------------------
# Per-strategy independence
# ------------------------------------------------------------------


class TestStrategyIndependence:
    """BM tier changes must NOT affect MR and vice versa."""

    def test_bm_tier_change_does_not_affect_mr(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -500.0)
        assert engine.get_tier("breakout_momentum") == 1
        assert engine.get_tier("rsi_mean_reversion") == 0

    def test_mr_tier_change_does_not_affect_bm(self):
        engine = _make_engine()
        engine.record_trade_pnl("rsi_mean_reversion", -500.0)
        # MR: dd = 500/10000 = 5 % > 4 % -> tier 2
        assert engine.get_tier("rsi_mean_reversion") == 2
        assert engine.get_tier("breakout_momentum") == 0

    def test_independent_recovery(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -500.0)
        engine.record_trade_pnl("rsi_mean_reversion", -250.0)
        assert engine.get_tier("breakout_momentum") == 1
        assert engine.get_tier("rsi_mean_reversion") == 1

        # Recover BM only
        engine.record_trade_pnl("breakout_momentum", 600.0)
        assert engine.get_tier("breakout_momentum") == 0
        assert engine.get_tier("rsi_mean_reversion") == 1


# ------------------------------------------------------------------
# Max entries per tier
# ------------------------------------------------------------------


class TestMaxEntries:
    """Verify get_max_entries honours tier limits and safety net."""

    def test_tier_0_normal_entries(self):
        engine = _make_engine()
        assert engine.get_max_entries("breakout_momentum") == GDR_STRATEGY_ENTRIES[0]

    def test_tier_2_zero_entries(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1000.0)
        assert engine.get_max_entries("breakout_momentum") == GDR_STRATEGY_ENTRIES[2]
        assert engine.get_max_entries("breakout_momentum") == 0

    def test_safety_net_overrides_max_entries(self):
        engine = _make_engine()
        engine.record_trade_pnl("breakout_momentum", -1300.0)
        assert engine.safety_net_active
        assert engine.get_max_entries("breakout_momentum") == PORTFOLIO_SAFETY_NET_ENTRIES
        assert engine.get_max_entries("rsi_mean_reversion") == PORTFOLIO_SAFETY_NET_ENTRIES


# ------------------------------------------------------------------
# update() (equity-snapshot API)
# ------------------------------------------------------------------


class TestUpdateAPI:
    """Test the bulk equity-snapshot update path."""

    def test_update_assigns_tiers(self):
        engine = _make_engine()
        # Simulate BM at +100, MR at -300 (peak auto-tracks)
        engine.update(
            strategy_equities={"breakout_momentum": 100.0, "rsi_mean_reversion": -300.0},
            total_equity=9800.0,
        )
        assert engine.get_tier("breakout_momentum") == 0
        # MR: peak=0 (init), set to -300, dd = 0 - (-300) = 300?
        # Actually _update_strategy_tier stores equity as cumulative_pnl.
        # Peak starts 0. equity=-300 < peak=0, so dd = (0-(-300))/10000 = 3% > 2% -> tier 1
        assert engine.get_tier("rsi_mean_reversion") == 1

    def test_update_activates_safety_net(self):
        engine = _make_engine()
        engine.update(
            strategy_equities={"breakout_momentum": -500.0},
            total_equity=8700.0,  # dd = 13% from peak of 10000
        )
        assert engine.safety_net_active
