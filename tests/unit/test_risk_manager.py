import pytest

from autotrader.core.config import RiskConfig
from autotrader.core.types import AccountInfo, Signal
from autotrader.risk.manager import RiskManager


@pytest.fixture
def default_config():
    """Default RiskConfig with the new 15% max drawdown."""
    return RiskConfig(
        max_position_pct=0.10,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.15,
        max_open_positions=5,
    )


@pytest.fixture
def strict_config():
    """Strict config with 5% drawdown for precise threshold testing."""
    return RiskConfig(
        max_position_pct=0.10,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.05,
        max_open_positions=5,
    )


def _make_account(equity: float) -> AccountInfo:
    """Create an AccountInfo with all monetary fields set to the given equity."""
    return AccountInfo(
        account_id="test",
        buying_power=equity,
        portfolio_value=equity,
        cash=equity,
        equity=equity,
    )


def _make_long_signal() -> Signal:
    return Signal(strategy="test", symbol="AAPL", direction="long", strength=0.8)


class TestResetPeakEquity:
    """test_reset_peak_equity - after reset, drawdown check passes again."""

    def test_reset_peak_equity_clears_drawdown_lockout(self, strict_config):
        rm = RiskManager(strict_config)
        # Establish peak at 100k
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        # Drawdown to 94k = 6% > 5% limit -> should reject
        account_94k = _make_account(94_000.0)
        assert rm.validate(_make_long_signal(), account_94k, positions=[]) is False

        # Reset peak equity to current level
        rm.reset_peak_equity(94_000.0)

        # Now 94k is the new peak, so 0% drawdown -> should pass
        assert rm.validate(_make_long_signal(), account_94k, positions=[]) is True

    def test_reset_peak_equity_also_resets_daily_pnl(self, default_config):
        rm = RiskManager(default_config)
        rm.record_pnl(-5000.0)
        rm.reset_peak_equity(90_000.0)
        # daily_pnl should be 0 after reset
        assert rm._daily_pnl == 0.0


class TestResetDailyPnl:
    """test_reset_daily_pnl - daily PnL resets to zero."""

    def test_reset_daily_pnl_zeroes_accumulator(self, default_config):
        rm = RiskManager(default_config)
        rm.record_pnl(-1000.0)
        rm.record_pnl(-500.0)
        assert rm._daily_pnl == pytest.approx(-1500.0)

        rm.reset_daily_pnl()
        assert rm._daily_pnl == 0.0

    def test_reset_daily_pnl_allows_trading_again(self, default_config):
        rm = RiskManager(default_config)
        account = _make_account(100_000.0)
        # Establish peak
        rm.validate(_make_long_signal(), account, positions=[])

        # Exceed daily loss limit: 2% of 100k = 2000
        rm.record_pnl(-2500.0)
        assert rm.validate(_make_long_signal(), account, positions=[]) is False

        # Reset daily PnL
        rm.reset_daily_pnl()
        assert rm.validate(_make_long_signal(), account, positions=[]) is True


class TestDrawdown15PctDefault:
    """test_drawdown_15pct_default - default config allows up to 15% drawdown."""

    def test_default_config_has_15pct_max_drawdown(self):
        config = RiskConfig()
        assert config.max_drawdown_pct == pytest.approx(0.15)

    def test_10pct_drawdown_passes_with_default(self, default_config):
        rm = RiskManager(default_config)
        # Establish peak at 100k
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        # 10% drawdown: 90k -> should still pass (10% < 15%)
        account_90k = _make_account(90_000.0)
        assert rm.validate(_make_long_signal(), account_90k, positions=[]) is True

    def test_14pct_drawdown_passes_with_default(self, default_config):
        rm = RiskManager(default_config)
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        # 14% drawdown -> should still pass (14% < 15%)
        account_86k = _make_account(86_000.0)
        assert rm.validate(_make_long_signal(), account_86k, positions=[]) is True

    def test_16pct_drawdown_rejected_with_default(self, default_config):
        rm = RiskManager(default_config)
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        # 16% drawdown -> should reject (16% > 15%)
        account_84k = _make_account(84_000.0)
        assert rm.validate(_make_long_signal(), account_84k, positions=[]) is False


class TestDrawdownRecoveryAfterReset:
    """test_drawdown_recovery_after_reset - simulate: drawdown hit -> reset -> can trade again."""

    def test_full_recovery_cycle(self, strict_config):
        rm = RiskManager(strict_config)

        # Phase 1: Establish peak at 100k
        account_100k = _make_account(100_000.0)
        assert rm.validate(_make_long_signal(), account_100k, positions=[]) is True

        # Phase 2: Equity drops to 94k (6% > 5% limit) -> blocked
        account_94k = _make_account(94_000.0)
        assert rm.validate(_make_long_signal(), account_94k, positions=[]) is False

        # Phase 3: Weekly rotation resets peak to current equity
        rm.reset_peak_equity(94_000.0)

        # Phase 4: Can trade again at 94k (0% drawdown from new peak)
        assert rm.validate(_make_long_signal(), account_94k, positions=[]) is True

        # Phase 5: Equity rises to 96k -> peak updates
        account_96k = _make_account(96_000.0)
        assert rm.validate(_make_long_signal(), account_96k, positions=[]) is True

        # Phase 6: Equity drops to 91.5k from 96k peak = ~4.7% -> still passes
        account_915k = _make_account(91_500.0)
        assert rm.validate(_make_long_signal(), account_915k, positions=[]) is True

        # Phase 7: Equity drops to 90.5k from 96k peak = ~5.7% -> blocked again
        account_905k = _make_account(90_500.0)
        assert rm.validate(_make_long_signal(), account_905k, positions=[]) is False

    def test_close_signals_always_pass_even_during_drawdown(self, strict_config):
        rm = RiskManager(strict_config)
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        # Hit drawdown limit
        account_94k = _make_account(94_000.0)
        close_signal = Signal(strategy="test", symbol="AAPL", direction="close", strength=1.0)
        # Close signals must always pass, even in drawdown
        assert rm.validate(close_signal, account_94k, positions=[]) is True


class TestGetDrawdownProperty:
    """test_get_drawdown_property - returns correct drawdown percentage."""

    def test_no_drawdown_at_peak(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        assert rm.get_drawdown == pytest.approx(0.0)

    def test_10pct_drawdown(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        # Simulate equity dropping to 90k
        rm._current_equity = 90_000.0
        assert rm.get_drawdown == pytest.approx(0.10)

    def test_drawdown_after_validate_updates(self, default_config):
        rm = RiskManager(default_config)
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])

        account_85k = _make_account(85_000.0)
        rm.validate(_make_long_signal(), account_85k, positions=[])
        assert rm.get_drawdown == pytest.approx(0.15)

    def test_drawdown_zero_when_uninitialized(self, default_config):
        rm = RiskManager(default_config)
        # peak_equity is 0 at init, should return 0.0
        assert rm.get_drawdown == pytest.approx(0.0)

    def test_drawdown_after_reset(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        rm._current_equity = 90_000.0
        assert rm.get_drawdown == pytest.approx(0.10)

        rm.reset_peak_equity(90_000.0)
        assert rm.get_drawdown == pytest.approx(0.0)


class TestPeakEquityUpdatesUpward:
    """test_peak_equity_updates_upward - peak tracks new highs."""

    def test_peak_increases_with_rising_equity(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        assert rm._peak_equity == pytest.approx(100_000.0)

        rm.update_peak(105_000.0)
        assert rm._peak_equity == pytest.approx(105_000.0)

        rm.update_peak(110_000.0)
        assert rm._peak_equity == pytest.approx(110_000.0)

    def test_peak_does_not_decrease(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        rm.update_peak(95_000.0)
        # Peak should remain at 100k, not decrease
        assert rm._peak_equity == pytest.approx(100_000.0)

    def test_peak_updates_via_validate(self, default_config):
        rm = RiskManager(default_config)
        # First call sets peak to 100k
        account_100k = _make_account(100_000.0)
        rm.validate(_make_long_signal(), account_100k, positions=[])
        assert rm._peak_equity == pytest.approx(100_000.0)

        # Higher equity updates peak
        account_110k = _make_account(110_000.0)
        rm.validate(_make_long_signal(), account_110k, positions=[])
        assert rm._peak_equity == pytest.approx(110_000.0)

        # Lower equity does not decrease peak
        account_105k = _make_account(105_000.0)
        rm.validate(_make_long_signal(), account_105k, positions=[])
        assert rm._peak_equity == pytest.approx(110_000.0)

    def test_current_equity_always_tracks(self, default_config):
        rm = RiskManager(default_config)
        rm.update_peak(100_000.0)
        assert rm._current_equity == pytest.approx(100_000.0)

        rm.update_peak(90_000.0)
        # current_equity tracks even when peak stays high
        assert rm._current_equity == pytest.approx(90_000.0)
        assert rm._peak_equity == pytest.approx(100_000.0)
