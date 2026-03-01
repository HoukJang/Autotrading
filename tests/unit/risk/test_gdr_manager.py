"""Tests for GDRManager - per-strategy graduated drawdown response."""
import pytest
from autotrader.risk.gdr_manager import GDRManager


class TestGDRManagerInit:
    def test_initial_tiers_are_zero(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        assert gdr.get_tier("breakout_momentum") == 0
        assert gdr.get_tier("rsi_mean_reversion") == 0

    def test_initial_pnl_is_zero(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        assert gdr.get_strategy_pnl("breakout_momentum") == 0.0

    def test_safety_net_initially_inactive(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        assert not gdr.is_safety_net_active

    def test_unknown_strategy_returns_defaults(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        assert gdr.get_tier("unknown") == 0
        assert gdr.get_strategy_pnl("unknown") == 0.0
        assert gdr.get_risk_multiplier("unknown") == 1.0

    def test_can_enter_initially(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        assert gdr.can_enter_strategy("breakout_momentum")
        assert gdr.can_enter_strategy("rsi_mean_reversion")


class TestPerStrategyGDR:
    def test_tier1_activation(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        # BM tier1 threshold = 4% of initial capital = $4,000 DD from peak
        gdr.record_trade_pnl("breakout_momentum", 1000)  # peak = 1000
        gdr.record_trade_pnl("breakout_momentum", -5000)  # pnl = -4000, dd = 5000/100000 = 5%
        assert gdr.get_tier("breakout_momentum") == 1
        assert gdr.get_risk_multiplier("breakout_momentum") == 0.5

    def test_tier2_halts_entries(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -8000)  # dd = 8% = tier2
        assert gdr.get_tier("breakout_momentum") == 2
        assert not gdr.can_enter_strategy("breakout_momentum")

    def test_tier2_risk_multiplier_is_zero(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -8000)
        assert gdr.get_risk_multiplier("breakout_momentum") == 0.0

    def test_mr_tighter_thresholds(self):
        gdr = GDRManager(["rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("rsi_mean_reversion", -2000)  # dd = 2% = tier1
        assert gdr.get_tier("rsi_mean_reversion") == 1

    def test_mr_tier2(self):
        gdr = GDRManager(["rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("rsi_mean_reversion", -4000)  # dd = 4% = tier2
        assert gdr.get_tier("rsi_mean_reversion") == 2
        assert not gdr.can_enter_strategy("rsi_mean_reversion")

    def test_recovery_to_tier0(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -5000)  # tier1 (5% dd)
        assert gdr.get_tier("breakout_momentum") == 1
        gdr.record_trade_pnl("breakout_momentum", 5000)   # back to 0, dd = 0%
        assert gdr.get_tier("breakout_momentum") == 0

    def test_profit_raises_peak(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", 5000)  # pnl = 5000, peak = 5000
        gdr.record_trade_pnl("breakout_momentum", -3000)  # pnl = 2000, dd from peak = 3000/100000 = 3%
        assert gdr.get_tier("breakout_momentum") == 0  # < 4% tier1 threshold

    def test_cumulative_pnl_tracking(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", 500)
        gdr.record_trade_pnl("breakout_momentum", -200)
        assert gdr.get_strategy_pnl("breakout_momentum") == 300.0

    def test_independent_strategy_tracking(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -5000)  # BM tier1
        gdr.record_trade_pnl("rsi_mean_reversion", 1000)   # MR fine
        assert gdr.get_tier("breakout_momentum") == 1
        assert gdr.get_tier("rsi_mean_reversion") == 0


class TestSafetyNet:
    def test_activation_at_12pct(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)  # 12% DD
        assert gdr.is_safety_net_active

    def test_no_activation_below_threshold(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -11000)  # 11% DD
        assert not gdr.is_safety_net_active

    def test_deactivation_below_8pct(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)  # activate
        assert gdr.is_safety_net_active
        gdr.record_trade_pnl("breakout_momentum", 5000)    # pnl = -7000, equity = 93000
        # DD = (100000 - 93000) / 100000 = 7% < 8%
        assert not gdr.is_safety_net_active

    def test_safety_net_stays_active_above_recovery(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)  # activate
        assert gdr.is_safety_net_active
        gdr.record_trade_pnl("breakout_momentum", 3000)    # pnl = -9000, equity = 91000
        # DD = (100000 - 91000) / 100000 = 9% > 8%, still active
        assert gdr.is_safety_net_active

    def test_safety_net_limits_entries(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)
        assert gdr.is_safety_net_active
        # First entry allowed
        assert gdr.can_enter_strategy("breakout_momentum")
        gdr.record_entry("breakout_momentum")
        # Second entry blocked (safety net = 1 total)
        assert not gdr.can_enter_strategy("rsi_mean_reversion")

    def test_safety_net_risk_value(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        assert gdr.safety_net_risk == 0.005

    def test_safety_net_risk_multiplier_is_one(self):
        """When safety net is active, multiplier returns 1.0
        because AllocationEngine handles the 0.5% override directly."""
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)
        assert gdr.is_safety_net_active
        assert gdr.get_risk_multiplier("breakout_momentum") == 1.0

    def test_cross_strategy_pnl_aggregates_for_safety_net(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -7000)
        assert not gdr.is_safety_net_active
        gdr.record_trade_pnl("rsi_mean_reversion", -5000)  # total = -12000
        assert gdr.is_safety_net_active


class TestDailyReset:
    def test_reset_clears_entries(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_entry("breakout_momentum")
        assert not gdr.can_enter_strategy("breakout_momentum")
        gdr.reset_daily_entries()
        assert gdr.can_enter_strategy("breakout_momentum")

    def test_reset_clears_total_entries(self):
        gdr = GDRManager(["breakout_momentum", "rsi_mean_reversion"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -12000)  # activate safety net
        gdr.record_entry("breakout_momentum")
        assert not gdr.can_enter_strategy("rsi_mean_reversion")  # blocked by safety net total
        gdr.reset_daily_entries()
        assert gdr.can_enter_strategy("rsi_mean_reversion")

    def test_reset_does_not_affect_tiers(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        gdr.record_trade_pnl("breakout_momentum", -8000)  # tier2
        assert gdr.get_tier("breakout_momentum") == 2
        gdr.reset_daily_entries()
        assert gdr.get_tier("breakout_momentum") == 2  # tier persists
        assert not gdr.can_enter_strategy("breakout_momentum")  # still halted


class TestEdgeCases:
    def test_zero_initial_capital(self):
        gdr = GDRManager(["breakout_momentum"], 0.0)
        gdr.record_trade_pnl("breakout_momentum", -100)
        assert gdr.get_tier("breakout_momentum") == 0  # dd=0 when capital=0

    def test_unknown_strategy_pnl_ignored(self):
        gdr = GDRManager(["breakout_momentum"], 100_000)
        # Recording PnL for unknown strategy should not crash
        gdr.record_trade_pnl("unknown_strategy", -5000)
        # But portfolio-level tracking still updates
        assert gdr._realized_pnl == -5000

    def test_empty_strategy_list(self):
        gdr = GDRManager([], 100_000)
        assert not gdr.is_safety_net_active
        gdr.record_trade_pnl("some_strategy", -12000)
        assert gdr.is_safety_net_active
