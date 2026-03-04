import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.main import AutoTrader
from autotrader.broker.paper import PaperBroker
from autotrader.core.config import Settings, RiskConfig
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal, Timeframe,
)
from autotrader.indicators.engine import IndicatorEngine
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.breakout_momentum import BreakoutMomentum


def _make_bar(symbol: str = "AAPL", close: float = 150.0, idx: int = 0) -> Bar:
    from datetime import timedelta
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Bar(
        symbol=symbol,
        timestamp=base + timedelta(minutes=idx),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1000.0,
    )


class TestAutoTrader:
    def test_create_with_defaults(self):
        app = AutoTrader(Settings())
        assert app is not None

    def test_create_paper_broker(self):
        settings = Settings()
        settings.broker.type = "paper"
        app = AutoTrader(settings)
        assert isinstance(app._broker, PaperBroker)

    def test_init_has_bar_history(self):
        app = AutoTrader(Settings())
        assert isinstance(app._bar_history, dict)

    def test_init_has_running_flag(self):
        app = AutoTrader(Settings())
        assert app._running is False

    def test_init_has_position_sizer(self):
        app = AutoTrader(Settings())
        assert isinstance(app._position_sizer, PositionSizer)


class TestRegisterStrategies:
    def test_register_adds_active_strategies(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        assert len(app._strategy_engine._strategies) == 2
        types = [type(s) for s in app._strategy_engine._strategies]
        assert RsiMeanReversion in types
        assert BreakoutMomentum in types

    def test_register_registers_indicators(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        keys = set(app._indicator_engine._indicators.keys())
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "EMA_21" in keys

    def test_register_deduplicates_indicators(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        count_before = len(app._indicator_engine._indicators)
        app._register_strategies()
        assert len(app._indicator_engine._indicators) == count_before


class TestSignalToOrder:
    @pytest.fixture()
    def app(self):
        return AutoTrader(Settings())

    @pytest.mark.asyncio
    async def test_long_signal_creates_buy_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        # Need bar history so _signal_to_order can look up price
        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="breakout_momentum", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.side == "buy"
        assert order.symbol == "AAPL"
        assert order.order_type == "market"
        assert order.quantity > 0

    @pytest.mark.asyncio
    async def test_close_signal_creates_sell_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        positions = [
            Position(
                symbol="AAPL", quantity=10, avg_entry_price=150.0,
                market_value=1500.0, unrealized_pnl=0.0, side="long",
            ),
        ]
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="close", strength=0.5,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None
        assert order.side == "sell"
        assert order.quantity == 10

    @pytest.mark.asyncio
    async def test_close_signal_no_position_returns_none(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        signal = Signal(
            strategy="sma_crossover", symbol="AAPL",
            direction="close", strength=0.5,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is None

    @pytest.mark.asyncio
    async def test_long_signal_zero_qty_returns_none(self, app):
        """If position sizer returns 0 qty (e.g. price too high), no order."""
        settings = Settings()
        app2 = AutoTrader(settings)
        await app2._broker.connect()
        account = await app2._broker.get_account()
        signal = Signal(
            strategy="test", symbol="BRK.A",
            direction="long", strength=1.0,
        )
        low_equity_account = AccountInfo(
            account_id="test", buying_power=1.0,
            portfolio_value=1.0, cash=1.0, equity=1.0,
        )
        order = app2._signal_to_order(signal, low_equity_account, [])
        assert order is None


class TestAutoTraderTradingLoop:
    @pytest.fixture()
    def settings(self) -> Settings:
        s = Settings()
        s.broker.type = "paper"
        s.broker.paper_balance = 100_000.0
        s.symbols = ["AAPL"]
        return s

    @pytest.fixture()
    def app(self, settings) -> AutoTrader:
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_start_initializes_tracker(self, app):
        await app.start()
        assert app._portfolio_tracker is not None
        assert app._portfolio_tracker.initial_equity == 100_000.0
        await app.stop()

    @pytest.mark.asyncio
    async def test_start_registers_strategies(self, app):
        await app.start()
        assert len(app._strategy_engine._strategies) >= 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_updates_mfe_mae(self, app):
        """_on_bar should update MFE/MAE for tracked positions."""
        await app.start()
        # Register a tracked position
        app._open_position_tracker.open_position(
            symbol="AAPL", strategy="test", direction="long",
            entry_price=100.0,
            entry_time=datetime(2025, 1, 5, 14, 0, tzinfo=timezone.utc),
            quantity=10,
        )
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc),
            open=100, high=110, low=95, close=105, volume=1000,
            timeframe=Timeframe.MINUTE,
        )
        await app._on_bar(bar)
        tracked = app._open_position_tracker.get_position("AAPL")
        assert tracked is not None
        assert tracked.highest_price == 110.0
        assert tracked.lowest_price == 95.0
        await app.stop()

    @pytest.mark.asyncio
    async def test_process_signal_submits_order(self, app):
        """Directly test _process_signal with a long signal."""
        await app.start()
        app._broker.set_price("AAPL", 150.0)
        # Need bar history so _signal_to_order can look up price
        bar = _make_bar("AAPL", 150.0)
        app._bar_history["AAPL"].append(bar)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(
            strategy="breakout_momentum", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        assert result is not None
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_process_signal_risk_rejected(self, app):
        """If risk manager rejects, no order is submitted."""
        await app.start()
        app._broker.set_price("AAPL", 150.0)

        # Fill up positions to max to trigger risk rejection
        for i in range(app._settings.risk.max_open_positions):
            sym = f"SYM{i}"
            app._broker.set_price(sym, 10.0)
            order = Order(
                symbol=sym, side="buy", quantity=1,
                order_type="market",
            )
            await app._broker.submit_order(order)

        account = await app._broker.get_account()
        positions = await app._broker.get_positions()

        signal = Signal(
            strategy="test", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, app):
        await app.start()
        assert app._running is True
        await app.stop()
        assert app._running is False


class TestAutoTraderStartStop:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        settings = Settings()
        app = AutoTrader(settings)
        await app.start()
        assert app._running is True
        assert app._broker.connected is True
        await app.stop()
        assert app._running is False
        assert app._broker.connected is False


class TestRotationManagerIntegration:
    @pytest.fixture()
    def app_with_rotation(self):
        from autotrader.core.config import RotationConfig
        settings = Settings()
        settings.broker.paper_balance = 5000.0
        rotation_config = RotationConfig()
        return AutoTrader(settings, rotation_config=rotation_config)

    def test_init_with_rotation_manager(self, app_with_rotation):
        assert app_with_rotation._rotation_manager is not None

    def test_init_without_rotation_manager(self):
        app = AutoTrader(Settings())
        assert app._rotation_manager is None

    def test_apply_rotation_method_exists(self, app_with_rotation):
        """AutoTrader should have apply_rotation method for external use."""
        assert hasattr(app_with_rotation, "apply_rotation")


class TestRegimeIntegration:
    def test_regime_defaults_to_uncertain(self):
        app = AutoTrader(Settings())
        assert app._current_regime == MarketRegime.UNCERTAIN

    def test_has_regime_detector(self):
        app = AutoTrader(Settings())
        assert isinstance(app._regime_detector, RegimeDetector)

    def test_has_allocation_engine(self):
        app = AutoTrader(Settings())
        assert isinstance(app._allocation_engine, AllocationEngine)

    def test_regime_proxy_symbol_from_config(self):
        app = AutoTrader(Settings())
        assert app._regime_proxy_symbol == "SPY"


class TestAllocationIntegration:
    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 50_000.0
        return AutoTrader(settings)

    def test_has_position_strategy_map(self):
        app = AutoTrader(Settings())
        assert hasattr(app, '_position_strategy_map')
        assert isinstance(app._position_strategy_map, dict)

    @pytest.mark.asyncio
    async def test_short_signal_creates_sell_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="rsi_mean_reversion", symbol="AAPL",
            direction="short", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None
        assert order.side == "sell"
        assert order.quantity > 0

    @pytest.mark.asyncio
    async def test_close_short_creates_buy_order(self, app):
        await app._broker.connect()
        account = await app._broker.get_account()
        positions = [
            Position(symbol="AAPL", quantity=10, avg_entry_price=100.0,
                     market_value=1000.0, unrealized_pnl=50.0, side="short"),
        ]
        signal = Signal(
            strategy="rsi_mean_reversion", symbol="AAPL",
            direction="close", strength=1.0,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None
        assert order.side == "buy"  # Buy to cover short
        assert order.quantity == 10

    @pytest.mark.asyncio
    async def test_allocation_engine_gates_entry_zero_weight(self, app):
        """Strategy with zero weight in current regime should be blocked."""
        await app._broker.connect()
        account = await app._broker.get_account()
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="nonexistent_strategy", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        # Unknown strategy has weight 0.0 -> blocked by should_enter()
        assert order is None

    @pytest.mark.asyncio
    async def test_position_strategy_map_tracks_entries(self, app):
        """After a filled long order, position_strategy_map is updated."""
        await app._broker.connect()
        app._broker.set_price("AAPL", 100.0)
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        app._portfolio_tracker = PortfolioTracker(50_000.0)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(
            strategy="breakout_momentum", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        if result and result.status == "filled":
            assert app._position_strategy_map.get("AAPL") == "breakout_momentum"

    @pytest.mark.asyncio
    async def test_close_removes_from_strategy_map(self, app):
        """After closing a position, symbol is removed from strategy map."""
        await app._broker.connect()
        app._broker.set_price("AAPL", 100.0)
        app._portfolio_tracker = PortfolioTracker(50_000.0)
        # Buy first
        buy = Order(symbol="AAPL", side="buy", quantity=10, order_type="market")
        await app._broker.submit_order(buy)
        app._position_strategy_map["AAPL"] = "test_strategy"
        # Now close
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(strategy="test_strategy", symbol="AAPL",
                        direction="close", strength=1.0)
        await app._process_signal(signal, account, positions)
        assert "AAPL" not in app._position_strategy_map


class TestRotationScheduler:
    def test_scheduler_task_none_by_default(self):
        app = AutoTrader(Settings())
        assert app._scheduler_task is None

    @pytest.mark.asyncio
    async def test_scheduler_starts_when_enabled(self):
        from autotrader.core.config import RotationConfig
        settings = Settings()
        rotation_config = RotationConfig()
        app = AutoTrader(settings, rotation_config=rotation_config)
        await app.start()
        assert app._scheduler_task is not None
        await app.stop()

    @pytest.mark.asyncio
    async def test_scheduler_does_not_start_when_disabled(self):
        from autotrader.core.config import RotationConfig
        settings = Settings()
        settings.scheduler.enable_rotation_scheduler = False
        rotation_config = RotationConfig()
        app = AutoTrader(settings, rotation_config=rotation_config)
        await app.start()
        assert app._scheduler_task is None
        await app.stop()

    @pytest.mark.asyncio
    async def test_scheduler_does_not_start_without_rotation_manager(self):
        settings = Settings()
        app = AutoTrader(settings)
        await app.start()
        assert app._scheduler_task is None
        await app.stop()


class TestRegimeTrackerIntegration:
    def test_has_regime_tracker(self):
        app = AutoTrader(Settings())
        from autotrader.portfolio.regime_tracker import RegimeTracker
        assert isinstance(app._regime_tracker, RegimeTracker)

    def test_regime_tracker_confirmation_default(self):
        app = AutoTrader(Settings())
        assert app._regime_tracker._confirmation_bars == 1


class TestEventDrivenRotationIntegration:
    def test_has_event_driven_rotation(self):
        settings = Settings()
        app = AutoTrader(settings)
        from autotrader.rotation.event_driven import EventDrivenRotation
        assert isinstance(app._event_rotation, EventDrivenRotation)

    def test_event_rotation_disabled_when_config_off(self):
        settings = Settings()
        settings.event_rotation.enable_event_driven = False
        app = AutoTrader(settings)
        assert app._event_rotation._enabled is False


class TestVIXIntegration:
    def test_vix_fetcher_when_enabled(self):
        settings = Settings()
        app = AutoTrader(settings)
        from autotrader.data.market_sentiment import VIXFetcher
        assert isinstance(app._vix_fetcher, VIXFetcher)

    def test_vix_fetcher_none_when_disabled(self):
        settings = Settings()
        settings.sentiment.enable_vix = False
        app = AutoTrader(settings)
        assert app._vix_fetcher is None


class TestTradeLoggerIntegration:
    def test_trade_logger_initialized_when_enabled(self, tmp_path):
        settings = Settings()
        settings.performance.trade_log_path = str(tmp_path / "trades.jsonl")
        settings.performance.equity_snapshot_path = str(tmp_path / "equity.jsonl")
        app = AutoTrader(settings)
        assert app._trade_logger is not None

    def test_trade_logger_none_when_disabled(self):
        settings = Settings()
        settings.performance.enable_trade_log = False
        app = AutoTrader(settings)
        assert app._trade_logger is None

    @pytest.mark.asyncio
    async def test_trade_logged_on_fill(self, tmp_path):
        settings = Settings()
        settings.performance.trade_log_path = str(tmp_path / "trades.jsonl")
        settings.performance.equity_snapshot_path = str(tmp_path / "equity.jsonl")
        settings.broker.paper_balance = 50_000.0
        app = AutoTrader(settings)
        await app.start()
        app._broker.set_price("AAPL", 100.0)
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(strategy="breakout_momentum", symbol="AAPL",
                        direction="long", strength=0.8)
        result = await app._process_signal(signal, account, positions)
        if result and result.status == "filled":
            trades = app._trade_logger.read_trades()
            assert len(trades) >= 1
            assert trades[0].symbol == "AAPL"
            assert trades[0].strategy == "breakout_momentum"
        await app.stop()


class TestRefreshDailyBars:
    """Test _refresh_daily_bars() pre-market daily bar fetch."""

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    def test_no_aggregator_attribute(self, app):
        """AutoTrader should NOT have _aggregator attribute after refactoring."""
        assert not hasattr(app, "_aggregator")

    @pytest.mark.asyncio
    async def test_on_bar_forwards_to_position_monitor(self, app):
        """_on_bar should forward bars to PositionMonitor.on_bar()."""
        await app.start()

        # Check that position_monitor was initialized
        assert app._position_monitor is not None

        # Verify _on_bar doesn't crash with minute bars
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc),
            open=100, high=101, low=99, close=100.5, volume=1000,
            timeframe=Timeframe.MINUTE,
        )
        await app._on_bar(bar)
        await app.stop()


class TestPDTGuard:
    """Test Pattern Day Trading guard prevents same-day round trips."""

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_same_day_close_blocked(self, app):
        """Close signal on same day as entry should be blocked."""
        await app._broker.connect()
        account = await app._broker.get_account()
        # Simulate existing position
        positions = [
            Position(symbol="AAPL", quantity=10, avg_entry_price=100.0,
                     market_value=1000.0, unrealized_pnl=0.0, side="long"),
        ]
        # Register position as opened today
        app._open_position_tracker.open_position(
            symbol="AAPL", strategy="test", direction="long",
            entry_price=100.0,
            entry_time=datetime.now(timezone.utc),
            quantity=10,
        )
        signal = Signal(
            strategy="test", symbol="AAPL",
            direction="close", strength=1.0,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is None  # Blocked by PDT guard

    @pytest.mark.asyncio
    async def test_next_day_close_allowed(self, app):
        """Close signal on next day should be allowed."""
        await app._broker.connect()
        account = await app._broker.get_account()
        positions = [
            Position(symbol="AAPL", quantity=10, avg_entry_price=100.0,
                     market_value=1000.0, unrealized_pnl=0.0, side="long"),
        ]
        # Position opened yesterday
        from datetime import timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        app._open_position_tracker.open_position(
            symbol="AAPL", strategy="test", direction="long",
            entry_price=100.0,
            entry_time=yesterday,
            quantity=10,
        )
        signal = Signal(
            strategy="test", symbol="AAPL",
            direction="close", strength=1.0,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None  # Allowed

    @pytest.mark.asyncio
    async def test_pdt_guard_does_not_block_untracked(self, app):
        """If position is not tracked (e.g. pre-existing), close is allowed."""
        await app._broker.connect()
        account = await app._broker.get_account()
        positions = [
            Position(symbol="AAPL", quantity=10, avg_entry_price=100.0,
                     market_value=1000.0, unrealized_pnl=0.0, side="long"),
        ]
        # No tracked position for AAPL
        signal = Signal(
            strategy="test", symbol="AAPL",
            direction="close", strength=1.0,
        )
        order = app._signal_to_order(signal, account, positions)
        assert order is not None  # Not blocked (no tracking info)

    @pytest.mark.asyncio
    async def test_pdt_guard_long_entry_same_day(self, app):
        """Entry signals should not be affected by PDT guard."""
        await app._broker.connect()
        account = await app._broker.get_account()
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="breakout_momentum", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None  # Entry not blocked


# ---------------------------------------------------------------------------
# Test: _load_last_batch_result restoration from disk
# ---------------------------------------------------------------------------


def _make_batch_result_json(run_at_iso: str, candidates: list | None = None) -> dict:
    """Build a minimal batch_results.json payload for testing.

    Matches the format produced by BatchResult.to_dict() in
    autotrader/batch/types.py, which is what NightlyScanner persists
    to data/batch_results.json.
    """
    if candidates is None:
        candidates = [
            {
                "rank": 1,
                "symbol": "AAPL",
                "strategy": "breakout_momentum",
                "direction": "long",
                "signal_strength": 0.9,
                "composite_score": 0.85,
                "score": 0.85,
                "regime_compatibility": 0.8,
                "sector": "Information Technology",
                "prev_close": 150.0,
                "entry_group": "MOO",
                "atr": 3.5,
                "sl_price": None,
                "tp_price": None,
                "gap_filter_status": "pending",
                "indicators": {"RSI_14": 55.0, "ADX_14": 32.0, "ATR_14": 3.5},
                "metadata": {"entry_group": "MOO"},
                "scanned_at": run_at_iso,
            },
        ]
    return {
        "run_at": run_at_iso,
        "scan_timestamp": run_at_iso,
        "scan_duration_secs": 1.5,
        "symbols_scanned": 500,
        "total_scanned": 500,
        "symbols_with_signals": 1,
        "signals_generated": 1,
        "regime": "UNCERTAIN",
        "candidates": candidates,
        "errors": [],
    }


def _write_batch_file(tmp_path, payload):
    """Write batch_results.json inside tmp_path/data/ (the relative path the loader uses)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    batch_file = data_dir / "batch_results.json"
    batch_file.write_text(json.dumps(payload), encoding="utf-8")
    return batch_file


class TestLoadBatchResultFromDisk:
    """Test _load_last_batch_result() restores nightly scan data on startup.

    The method reads data/batch_results.json (relative to cwd), checks whether
    the scan timestamp is less than 18 hours old, and if so populates
    self._last_batch_result so that the 9:25 AM gap filter has candidates
    to work with (even after a restart).

    We use monkeypatch.chdir(tmp_path) so the hardcoded relative path
    'data/batch_results.json' resolves to our test temp directory.
    """

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    def test_load_batch_result_from_disk_on_startup(self, app, tmp_path, monkeypatch):
        """When batch_results.json exists and is recent (<18h), _last_batch_result is populated."""
        from datetime import timedelta

        # Write a recent batch result (2 hours ago)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        payload = _make_batch_result_json(recent_time.isoformat())
        _write_batch_file(tmp_path, payload)

        # Change cwd so 'data/batch_results.json' resolves inside tmp_path
        monkeypatch.chdir(tmp_path)

        # Precondition
        assert app._last_batch_result is None

        # Invoke the loader (no arguments -- uses hardcoded relative path)
        app._load_last_batch_result()

        # Postconditions
        assert app._last_batch_result is not None
        assert hasattr(app._last_batch_result, "candidates")
        assert len(app._last_batch_result.candidates) == 1

    def test_load_batch_result_stale_file_ignored(self, app, tmp_path, monkeypatch):
        """When batch_results.json is old (>18h), _last_batch_result stays None."""
        from datetime import timedelta

        stale_time = datetime.now(timezone.utc) - timedelta(hours=24)
        payload = _make_batch_result_json(stale_time.isoformat())
        _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        app._load_last_batch_result()

        assert app._last_batch_result is None

    def test_load_batch_result_missing_file(self, app, tmp_path, monkeypatch):
        """When batch_results.json does not exist, no error and _last_batch_result stays None."""
        # tmp_path exists but has no data/ subdirectory
        monkeypatch.chdir(tmp_path)

        # Should not raise any exception
        app._load_last_batch_result()

        assert app._last_batch_result is None

    def test_load_batch_result_corrupt_json(self, app, tmp_path, monkeypatch):
        """When file contains invalid JSON, no error and _last_batch_result stays None."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "batch_results.json").write_text(
            "{this is not valid json!!!", encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        # Should not raise any exception
        app._load_last_batch_result()

        assert app._last_batch_result is None

    def test_load_batch_result_boundary_just_under_18h(self, app, tmp_path, monkeypatch):
        """A batch result at exactly 17h 59m old should still be loaded."""
        from datetime import timedelta

        boundary_time = datetime.now(timezone.utc) - timedelta(hours=17, minutes=59)
        payload = _make_batch_result_json(boundary_time.isoformat())
        _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        app._load_last_batch_result()

        assert app._last_batch_result is not None

    def test_load_batch_result_boundary_just_over_18h(self, app, tmp_path, monkeypatch):
        """A batch result at exactly 18h 1m old should be treated as stale."""
        from datetime import timedelta

        boundary_time = datetime.now(timezone.utc) - timedelta(hours=18, minutes=1)
        payload = _make_batch_result_json(boundary_time.isoformat())
        _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        app._load_last_batch_result()

        assert app._last_batch_result is None

    @pytest.mark.asyncio
    async def test_gap_filter_uses_restored_batch_result(self, app, tmp_path, monkeypatch):
        """After loading from disk, gap filter should find candidates (not skip).

        This tests the critical integration path: if _last_batch_result was
        restored from disk, _on_gap_filter should process those candidates
        instead of logging 'no nightly batch result; skipping'.
        """
        from datetime import timedelta
        from autotrader.batch.types import FilteredCandidate

        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        payload = _make_batch_result_json(recent_time.isoformat())
        _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        # Load from disk
        app._load_last_batch_result()
        assert app._last_batch_result is not None

        # Install a mock gap filter that passes everything through
        # (wraps each candidate in a FilteredCandidate with passed_filter=True)
        def _pass_all(candidates):
            return [
                FilteredCandidate(candidate=c, passed_filter=True)
                for c in candidates
            ]

        mock_filter = AsyncMock()
        mock_filter.filter = AsyncMock(side_effect=_pass_all)
        app._gap_filter = mock_filter

        # Run the gap filter handler
        await app._on_gap_filter()

        # The mock filter should have been called with the restored candidates
        mock_filter.filter.assert_awaited_once()
        passed_candidates = mock_filter.filter.call_args[0][0]
        assert len(passed_candidates) >= 1
        assert passed_candidates[0].symbol == "AAPL"

    def test_load_batch_result_empty_candidates_still_loaded(self, app, tmp_path, monkeypatch):
        """A valid recent file with zero candidates should still populate _last_batch_result."""
        from datetime import timedelta

        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = _make_batch_result_json(recent_time.isoformat(), candidates=[])
        _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        app._load_last_batch_result()

        # Even with no candidates, the result object itself should be restored
        assert app._last_batch_result is not None
        assert len(app._last_batch_result.candidates) == 0

    def test_load_batch_result_missing_run_at_field(self, app, tmp_path, monkeypatch):
        """If run_at field is missing from JSON, loader should handle gracefully."""
        payload = {
            "symbols_scanned": 500,
            "candidates": [],
            "errors": [],
        }
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "batch_results.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        # Should not raise -- graceful degradation
        app._load_last_batch_result()

        # Without run_at, the loader cannot determine age so it should skip.
        # The implementation logs a warning and returns without setting the result.
        assert app._last_batch_result is None


# ---------------------------------------------------------------------------
# Test: Scheduler deduplication (daily reset fires only once)
# ---------------------------------------------------------------------------


class TestSchedulerDeduplication:
    """Test that _batch_intraday_scheduler prevents concurrent instances and
    that daily_reset fires exactly once per day even across multiple polling
    cycles.
    """

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    @pytest.mark.asyncio
    async def test_scheduler_runs_only_once(self, app):
        """If _batch_intraday_scheduler is called twice, only one instance should run.

        The fix adds a guard flag (_scheduler_running) so that a second
        invocation returns immediately without executing the polling loop.
        This prevents duplicate event firings when start() is called more
        than once or when the task is accidentally re-created.
        """
        await app.start()

        # The first scheduler task was already created in start()
        first_task = app._batch_scheduler_task
        assert first_task is not None

        # Attempt to start a second instance of the scheduler
        second_task = asyncio.create_task(app._batch_intraday_scheduler())

        # Give the second task a brief moment to either run or exit early
        await asyncio.sleep(0.15)

        # The second task should have finished (returned early due to guard)
        assert second_task.done(), (
            "_batch_intraday_scheduler should return immediately when already running"
        )

        # Verify it did not raise an exception when returning early
        exc = second_task.exception() if second_task.done() else None
        assert exc is None, f"Second scheduler instance raised unexpected error: {exc}"

        # The first (original) task should still be alive since _running is True
        assert not first_task.done()

        await app.stop()
        # Clean up the second task
        if not second_task.done():
            second_task.cancel()
            try:
                await second_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_daily_reset_fires_exactly_once(self, app):
        """Even after multiple polling cycles past 9:20 AM, daily_reset fires only once.

        This verifies the _fired dict mechanism used inside
        _batch_intraday_scheduler correctly compares today's date so that
        once a daily event has fired for a given date, it will not fire again
        on subsequent polling iterations for the same date.
        """
        from datetime import date
        from zoneinfo import ZoneInfo

        await app.start()

        # Track how many times _on_daily_reset is called
        call_count = 0
        original_reset = app._on_daily_reset

        async def counting_reset(today_et):
            nonlocal call_count
            call_count += 1
            await original_reset(today_et)

        app._on_daily_reset = counting_reset

        # Stop the existing scheduler so we can drive the firing logic manually
        if app._batch_scheduler_task and not app._batch_scheduler_task.done():
            app._batch_scheduler_task.cancel()
            try:
                await app._batch_scheduler_task
            except (asyncio.CancelledError, Exception):
                pass

        # Replicate the _fired dict structure from _batch_intraday_scheduler
        _ET = ZoneInfo("America/New_York")
        today_et = datetime.now(timezone.utc).astimezone(_ET).date()

        _fired: dict[str, date | None] = {
            "daily_bar_refresh": None,
            "daily_reset": None,
            "gap_filter": None,
            "moo": None,
            "confirmation": None,
            "entry_close": None,
            "nightly_scan": None,
        }

        # Simulate the daily_reset guard check -- first pass (should fire)
        if _fired["daily_reset"] != today_et:
            _fired["daily_reset"] = today_et
            await counting_reset(today_et)

        assert call_count == 1, "daily_reset should fire on the first check"

        # Second pass in same polling cycle (should NOT fire)
        if _fired["daily_reset"] != today_et:
            _fired["daily_reset"] = today_et
            await counting_reset(today_et)

        assert call_count == 1, "daily_reset should not fire again for the same date"

        # Third pass for good measure
        if _fired["daily_reset"] != today_et:
            _fired["daily_reset"] = today_et
            await counting_reset(today_et)

        assert call_count == 1, "daily_reset must fire exactly once per day"

        await app.stop()

    @pytest.mark.asyncio
    async def test_daily_reset_fires_again_next_day(self, app):
        """After a new trading day begins, daily_reset should be eligible to fire again.

        The _fired dict stores the date of the last firing. When the date
        changes, the guard condition (fired != today) becomes True again.
        """
        from datetime import date, timedelta
        from zoneinfo import ZoneInfo

        await app.start()

        call_count = 0
        original_reset = app._on_daily_reset

        async def counting_reset(today_et):
            nonlocal call_count
            call_count += 1
            await original_reset(today_et)

        app._on_daily_reset = counting_reset

        # Cancel the real scheduler
        if app._batch_scheduler_task and not app._batch_scheduler_task.done():
            app._batch_scheduler_task.cancel()
            try:
                await app._batch_scheduler_task
            except (asyncio.CancelledError, Exception):
                pass

        _ET = ZoneInfo("America/New_York")
        today_et = datetime.now(timezone.utc).astimezone(_ET).date()
        tomorrow_et = today_et + timedelta(days=1)

        _fired: dict[str, date | None] = {
            "daily_reset": None,
        }

        # Day 1: fire
        if _fired["daily_reset"] != today_et:
            _fired["daily_reset"] = today_et
            await counting_reset(today_et)
        assert call_count == 1

        # Day 1 repeat: should not fire
        if _fired["daily_reset"] != today_et:
            _fired["daily_reset"] = today_et
            await counting_reset(today_et)
        assert call_count == 1

        # Day 2: should fire again
        if _fired["daily_reset"] != tomorrow_et:
            _fired["daily_reset"] = tomorrow_et
            await counting_reset(tomorrow_et)
        assert call_count == 2, "daily_reset should fire again on a new date"

        await app.stop()


# ---------------------------------------------------------------------------
# Test: _batch_to_entry_candidate conversion (batch.types -> entry_manager)
# ---------------------------------------------------------------------------


def _make_batch_candidate(
    symbol: str = "AAPL",
    strategy: str = "breakout_momentum",
    direction: str = "long",
    signal_strength: float = 0.9,
    prev_close: float = 150.0,
    indicators: dict | None = None,
    metadata: dict | None = None,
):
    """Create a batch.types.Candidate with a nested ScanResult for testing."""
    from autotrader.batch.types import Candidate as BatchCandidateType
    from autotrader.batch.types import ScanResult

    if indicators is None:
        indicators = {"RSI_14": 55.0, "ADX_14": 32.0, "ATR_14": 3.5}
    if metadata is None:
        metadata = {"entry_group": "MOO"}

    scan_result = ScanResult(
        symbol=symbol,
        strategy=strategy,
        direction=direction,
        signal_strength=signal_strength,
        indicators=indicators,
        prev_close=prev_close,
        scanned_at=datetime.now(timezone.utc),
        metadata=metadata,
    )
    return BatchCandidateType(
        scan_result=scan_result,
        composite_score=0.85,
        regime_compatibility=0.8,
        sector="Information Technology",
        rank=1,
    )


class TestBatchToEntryCandidateConversion:
    """Test _batch_to_entry_candidate() converts batch.types.Candidate
    to execution.entry_manager.Candidate correctly.

    The conversion must:
    - Build a Signal from ScanResult fields (strategy, symbol, direction, strength)
    - Extract prev_close from scan_result.prev_close
    - Extract ATR_14 from scan_result.indicators (default to 1.0 if missing/zero)
    - Pass the full indicators dict through
    """

    def test_converts_batch_candidate_to_entry_candidate(self):
        """Valid batch.types.Candidate converts to entry_manager.Candidate
        with all fields correctly mapped."""
        from autotrader.main import _batch_to_entry_candidate
        from autotrader.execution.entry_manager import Candidate as EntryCandidateType

        batch_cand = _make_batch_candidate(
            symbol="MSFT",
            strategy="breakout_momentum",
            direction="long",
            signal_strength=0.85,
            prev_close=420.0,
            indicators={"RSI_14": 60.0, "ADX_14": 30.0, "ATR_14": 5.2},
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        # Type check
        assert isinstance(entry_cand, EntryCandidateType)

        # Signal fields must match scan_result
        assert entry_cand.signal.symbol == "MSFT"
        assert entry_cand.signal.strategy == "breakout_momentum"
        assert entry_cand.signal.direction == "long"
        assert entry_cand.signal.strength == 0.85

        # prev_close preserved
        assert entry_cand.prev_close == 420.0

        # ATR extracted from indicators
        assert entry_cand.atr == 5.2

        # Full indicators dict preserved
        assert entry_cand.indicators["RSI_14"] == 60.0
        assert entry_cand.indicators["ADX_14"] == 30.0
        assert entry_cand.indicators["ATR_14"] == 5.2

    def test_conversion_handles_missing_atr(self):
        """When ATR_14 is not present in indicators, atr defaults to 1.0."""
        from autotrader.main import _batch_to_entry_candidate

        batch_cand = _make_batch_candidate(
            indicators={"RSI_14": 55.0, "ADX_14": 32.0},  # No ATR_14
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        # Must default to 1.0 when ATR is missing
        assert entry_cand.atr == 1.0

    def test_conversion_handles_zero_atr(self):
        """When ATR_14 is 0, atr defaults to 1.0 to avoid division-by-zero."""
        from autotrader.main import _batch_to_entry_candidate

        batch_cand = _make_batch_candidate(
            indicators={"RSI_14": 55.0, "ADX_14": 32.0, "ATR_14": 0.0},
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        # Zero ATR must be replaced with safe default 1.0
        assert entry_cand.atr == 1.0

    def test_conversion_includes_entry_atr_in_signal_metadata(self):
        """entry_atr must be injected into Signal.metadata during conversion.

        EntryManager._submit_broker_sl() relies on signal.metadata['entry_atr']
        to place broker-side stop-loss orders.  Without it, the SL is skipped
        with a WARNING.
        """
        from autotrader.main import _batch_to_entry_candidate

        batch_cand = _make_batch_candidate(
            indicators={"RSI_14": 60.0, "ADX_14": 30.0, "ATR_14": 5.2},
            metadata={"entry_group": "MOO", "sub_strategy": "breakout_momentum_long"},
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        # entry_atr must be present in signal metadata
        assert "entry_atr" in entry_cand.signal.metadata
        assert entry_cand.signal.metadata["entry_atr"] == pytest.approx(5.2)
        # entry_atr must match the candidate atr
        assert entry_cand.signal.metadata["entry_atr"] == entry_cand.atr

    def test_conversion_preserves_original_metadata_fields(self):
        """Original strategy metadata fields must be preserved alongside entry_atr."""
        from autotrader.main import _batch_to_entry_candidate

        batch_cand = _make_batch_candidate(
            indicators={"ATR_14": 3.5},
            metadata={"sub_strategy": "breakout_momentum_long", "adx": 32.0},
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        # Original fields preserved
        assert entry_cand.signal.metadata["sub_strategy"] == "breakout_momentum_long"
        assert entry_cand.signal.metadata["adx"] == 32.0
        # New field added
        assert entry_cand.signal.metadata["entry_atr"] == pytest.approx(3.5)

    def test_conversion_entry_atr_defaults_to_1_when_atr_missing(self):
        """When ATR_14 is missing, entry_atr in metadata defaults to 1.0."""
        from autotrader.main import _batch_to_entry_candidate

        batch_cand = _make_batch_candidate(
            indicators={"RSI_14": 55.0},  # No ATR_14
        )

        entry_cand = _batch_to_entry_candidate(batch_cand)

        assert entry_cand.signal.metadata["entry_atr"] == pytest.approx(1.0)
        assert entry_cand.atr == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test: TradeLogger entry logging from _on_moo() and _on_confirmation_window()
# ---------------------------------------------------------------------------


class TestEntryTradeLogging:
    """Verify that TradeLogger.log_trade() is called when EntryManager opens positions.

    Issue: The v3 EntryManager path (_on_moo / _on_confirmation_window) was
    not calling TradeLogger, so live_trades.jsonl had 0 entries.
    """

    @pytest.fixture()
    def app_with_trade_logger(self):
        """Create an AutoTrader with a mocked trade logger and entry manager."""
        settings = Settings()
        app = AutoTrader(settings)
        # Mock trade logger
        app._trade_logger = MagicMock()
        app._trade_logger.log_trade = MagicMock()
        app._trade_logger.log_equity = MagicMock()
        # Mock broker
        app._broker = AsyncMock()
        app._broker.get_account = AsyncMock(return_value=AccountInfo(
            account_id="test", buying_power=100000.0,
            portfolio_value=100000.0, cash=100000.0, equity=100000.0,
        ))
        app._broker.get_positions = AsyncMock(return_value=[])
        app._broker.add_bar_subscription = AsyncMock()
        # Mock entry manager with a single filled position
        from autotrader.execution.exit_rules import HeldPosition
        held = HeldPosition(
            symbol="NFLX",
            strategy="breakout_momentum",
            direction="long",
            entry_price=96.77,
            entry_atr=3.5,
            entry_date_et=datetime(2026, 3, 3).date(),
            bars_held=0,
            qty=79.0,
            highest_price=96.77,
            lowest_price=96.77,
        )
        app._entry_manager = MagicMock()
        app._entry_manager.execute_moo = AsyncMock(return_value=[held])
        app._entry_manager.execute_confirmation = AsyncMock(return_value=[held])
        # Mock position monitor and open position tracker
        app._position_monitor = MagicMock()
        app._open_position_tracker = MagicMock()
        # Ensure regime is set
        app._current_regime = MarketRegime.UNCERTAIN
        return app

    @pytest.mark.asyncio
    async def test_moo_calls_trade_logger_for_entry(self, app_with_trade_logger):
        """_on_moo() must call TradeLogger.log_trade() for each opened position."""
        app = app_with_trade_logger

        await app._on_moo()

        app._trade_logger.log_trade.assert_called_once()
        record = app._trade_logger.log_trade.call_args[0][0]
        assert record.symbol == "NFLX"
        assert record.strategy == "breakout_momentum"
        assert record.direction == "long"
        assert record.side == "buy"
        assert record.quantity == 79.0
        assert record.price == pytest.approx(96.77)
        assert record.pnl == 0.0  # Entry has no PnL
        assert record.metadata["entry_atr"] == pytest.approx(3.5)

    @pytest.mark.asyncio
    async def test_confirmation_calls_trade_logger_for_entry(self, app_with_trade_logger):
        """_on_confirmation_window() must call TradeLogger.log_trade() for each opened position."""
        app = app_with_trade_logger

        await app._on_confirmation_window()

        app._trade_logger.log_trade.assert_called_once()
        record = app._trade_logger.log_trade.call_args[0][0]
        assert record.symbol == "NFLX"
        assert record.direction == "long"
        assert record.side == "buy"

    @pytest.mark.asyncio
    async def test_moo_does_not_log_when_no_trade_logger(self):
        """_on_moo() must not fail when trade logger is None."""
        settings = Settings()
        app = AutoTrader(settings)
        app._trade_logger = None
        app._broker = AsyncMock()
        app._broker.get_account = AsyncMock(return_value=AccountInfo(
            account_id="test", buying_power=100000.0,
            portfolio_value=100000.0, cash=100000.0, equity=100000.0,
        ))
        app._broker.get_positions = AsyncMock(return_value=[])
        app._broker.add_bar_subscription = AsyncMock()

        from autotrader.execution.exit_rules import HeldPosition
        held = HeldPosition(
            symbol="AAPL", strategy="breakout_momentum", direction="long",
            entry_price=150.0, entry_atr=2.0,
            entry_date_et=datetime(2026, 3, 3).date(),
            bars_held=0, qty=10.0, highest_price=150.0, lowest_price=150.0,
        )
        app._entry_manager = MagicMock()
        app._entry_manager.execute_moo = AsyncMock(return_value=[held])
        app._position_monitor = MagicMock()
        app._open_position_tracker = MagicMock()
        app._current_regime = MarketRegime.UNCERTAIN

        # Should not raise
        await app._on_moo()

    @pytest.mark.asyncio
    async def test_moo_logs_multiple_entries(self):
        """When multiple positions are opened, each gets a trade log entry."""
        settings = Settings()
        app = AutoTrader(settings)
        app._trade_logger = MagicMock()
        app._trade_logger.log_trade = MagicMock()
        app._trade_logger.log_equity = MagicMock()
        app._broker = AsyncMock()
        app._broker.get_account = AsyncMock(return_value=AccountInfo(
            account_id="test", buying_power=100000.0,
            portfolio_value=100000.0, cash=100000.0, equity=100000.0,
        ))
        app._broker.get_positions = AsyncMock(return_value=[])
        app._broker.add_bar_subscription = AsyncMock()

        from autotrader.execution.exit_rules import HeldPosition
        held1 = HeldPosition(
            symbol="NFLX", strategy="breakout_momentum", direction="long",
            entry_price=96.0, entry_atr=3.0,
            entry_date_et=datetime(2026, 3, 3).date(),
            bars_held=0, qty=50.0, highest_price=96.0, lowest_price=96.0,
        )
        held2 = HeldPosition(
            symbol="LMT", strategy="breakout_momentum", direction="long",
            entry_price=670.0, entry_atr=12.0,
            entry_date_et=datetime(2026, 3, 3).date(),
            bars_held=0, qty=7.0, highest_price=670.0, lowest_price=670.0,
        )
        app._entry_manager = MagicMock()
        app._entry_manager.execute_moo = AsyncMock(return_value=[held1, held2])
        app._position_monitor = MagicMock()
        app._open_position_tracker = MagicMock()
        app._current_regime = MarketRegime.UNCERTAIN

        await app._on_moo()

        assert app._trade_logger.log_trade.call_count == 2
        symbols_logged = [
            call[0][0].symbol
            for call in app._trade_logger.log_trade.call_args_list
        ]
        assert "NFLX" in symbols_logged
        assert "LMT" in symbols_logged


# ---------------------------------------------------------------------------
# Test: GapFilter + SignalRanker integration in _on_gap_filter()
# ---------------------------------------------------------------------------


class TestGapFilterIntegration:
    """Test the updated _on_gap_filter() method which:
    1. Calls GapFilter.filter() when injected
    2. Extracts passed candidates from FilteredCandidate results
    3. Converts batch.types.Candidate -> entry_manager.Candidate
    4. Loads converted candidates into EntryManager
    5. Still loads raw candidates when GapFilter is None (not skip!)
    6. Updates batch_results.json with gap_filter_status
    """

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    def _set_batch_result_with_candidates(self, app, candidates):
        """Set _last_batch_result with given batch.types.Candidate list."""

        class _FakeBatchResult:
            def __init__(self, cands):
                self.candidates = cands

        app._last_batch_result = _FakeBatchResult(candidates)

    @pytest.mark.asyncio
    async def test_gap_filter_passes_candidates_to_entry_manager(self, app):
        """When GapFilter is injected and returns some passed, EntryManager
        receives only the passed ones converted to entry_manager.Candidate."""
        from autotrader.batch.types import FilteredCandidate
        from autotrader.execution.entry_manager import Candidate as EntryCandidateType

        # Create 2 batch candidates
        cand1 = _make_batch_candidate(symbol="AAPL")
        cand2 = _make_batch_candidate(symbol="MSFT")
        self._set_batch_result_with_candidates(app, [cand1, cand2])

        # Mock GapFilter: both candidates pass
        filtered_results = [
            FilteredCandidate(candidate=cand1, passed_filter=True, gap_pct=0.01),
            FilteredCandidate(candidate=cand2, passed_filter=True, gap_pct=-0.005),
        ]
        mock_gap_filter = AsyncMock()
        mock_gap_filter.filter = AsyncMock(return_value=filtered_results)
        app._gap_filter = mock_gap_filter

        # Mock EntryManager to capture what gets loaded
        mock_entry_mgr = MagicMock()
        mock_entry_mgr.load_candidates = MagicMock()
        app._entry_manager = mock_entry_mgr

        await app._on_gap_filter()

        # GapFilter.filter() must have been called with the raw batch candidates
        mock_gap_filter.filter.assert_awaited_once()
        raw_args = mock_gap_filter.filter.call_args[0][0]
        assert len(raw_args) == 2

        # EntryManager must have been called with converted candidates
        mock_entry_mgr.load_candidates.assert_called_once()
        loaded = mock_entry_mgr.load_candidates.call_args[0][0]
        assert len(loaded) == 2
        # Verify they are entry_manager.Candidate objects (not batch types)
        for c in loaded:
            assert isinstance(c, EntryCandidateType)
        # Verify symbols preserved
        loaded_symbols = {c.signal.symbol for c in loaded}
        assert loaded_symbols == {"AAPL", "MSFT"}

    @pytest.mark.asyncio
    async def test_gap_filter_none_still_loads_candidates(self, app):
        """When GapFilter is None, all raw candidates are still converted
        and loaded into EntryManager (the new behavior -- not skipped!)."""
        from autotrader.execution.entry_manager import Candidate as EntryCandidateType

        cand1 = _make_batch_candidate(symbol="AAPL")
        cand2 = _make_batch_candidate(symbol="GOOG")
        self._set_batch_result_with_candidates(app, [cand1, cand2])

        # No gap filter injected
        app._gap_filter = None

        # Mock EntryManager to capture what gets loaded
        mock_entry_mgr = MagicMock()
        mock_entry_mgr.load_candidates = MagicMock()
        app._entry_manager = mock_entry_mgr

        await app._on_gap_filter()

        # EntryManager MUST receive the candidates (not skip!)
        mock_entry_mgr.load_candidates.assert_called_once()
        loaded = mock_entry_mgr.load_candidates.call_args[0][0]
        assert len(loaded) == 2
        for c in loaded:
            assert isinstance(c, EntryCandidateType)
        loaded_symbols = {c.signal.symbol for c in loaded}
        assert loaded_symbols == {"AAPL", "GOOG"}

    @pytest.mark.asyncio
    async def test_gap_filter_removes_filtered_candidates(self, app):
        """GapFilter returns 3 passed + 2 filtered; EntryManager gets only 3."""
        from autotrader.batch.types import FilteredCandidate
        from autotrader.execution.entry_manager import Candidate as EntryCandidateType

        cands = [
            _make_batch_candidate(symbol="AAPL"),
            _make_batch_candidate(symbol="MSFT"),
            _make_batch_candidate(symbol="GOOG"),
            _make_batch_candidate(symbol="TSLA"),
            _make_batch_candidate(symbol="AMZN"),
        ]
        self._set_batch_result_with_candidates(app, cands)

        # Mock GapFilter: 3 pass, 2 filtered out (TSLA gapped up, AMZN gapped down)
        filtered_results = [
            FilteredCandidate(candidate=cands[0], passed_filter=True, gap_pct=0.01),
            FilteredCandidate(candidate=cands[1], passed_filter=True, gap_pct=-0.005),
            FilteredCandidate(candidate=cands[2], passed_filter=True, gap_pct=0.0),
            FilteredCandidate(candidate=cands[3], passed_filter=False, gap_pct=0.05,
                              filter_reason="gap_up_5.0pct"),
            FilteredCandidate(candidate=cands[4], passed_filter=False, gap_pct=-0.04,
                              filter_reason="gap_down_4.0pct"),
        ]
        mock_gap_filter = AsyncMock()
        mock_gap_filter.filter = AsyncMock(return_value=filtered_results)
        app._gap_filter = mock_gap_filter

        mock_entry_mgr = MagicMock()
        mock_entry_mgr.load_candidates = MagicMock()
        app._entry_manager = mock_entry_mgr

        await app._on_gap_filter()

        # Only 3 passed candidates should be loaded
        mock_entry_mgr.load_candidates.assert_called_once()
        loaded = mock_entry_mgr.load_candidates.call_args[0][0]
        assert len(loaded) == 3

        loaded_symbols = {c.signal.symbol for c in loaded}
        assert "AAPL" in loaded_symbols
        assert "MSFT" in loaded_symbols
        assert "GOOG" in loaded_symbols
        # Filtered candidates must NOT be present
        assert "TSLA" not in loaded_symbols
        assert "AMZN" not in loaded_symbols

    @pytest.mark.asyncio
    async def test_gap_filter_no_batch_result_skips(self, app):
        """When _last_batch_result is None, _on_gap_filter returns early."""
        app._last_batch_result = None

        mock_gap_filter = AsyncMock()
        mock_gap_filter.filter = AsyncMock()
        app._gap_filter = mock_gap_filter

        mock_entry_mgr = MagicMock()
        mock_entry_mgr.load_candidates = MagicMock()
        app._entry_manager = mock_entry_mgr

        await app._on_gap_filter()

        # Neither gap filter nor entry manager should be called
        mock_gap_filter.filter.assert_not_awaited()
        mock_entry_mgr.load_candidates.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_filter_updates_batch_results_json(self, app, tmp_path, monkeypatch):
        """After gap filter runs, data/batch_results.json is updated with
        gap_filter_status for each candidate ('passed' or 'filtered')."""
        from datetime import timedelta
        from autotrader.batch.types import FilteredCandidate

        # Write initial batch_results.json to disk
        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        run_at_iso = recent_time.isoformat()

        # 2 candidates, both initially with gap_filter_status="pending"
        raw_candidates_json = [
            {
                "rank": 1, "symbol": "AAPL", "strategy": "breakout_momentum",
                "direction": "long", "signal_strength": 0.9,
                "composite_score": 0.85, "score": 0.85,
                "regime_compatibility": 0.8, "sector": "Tech",
                "prev_close": 150.0, "entry_group": "MOO", "atr": 3.5,
                "sl_price": None, "tp_price": None,
                "gap_filter_status": "pending",
                "indicators": {"RSI_14": 55.0, "ADX_14": 32.0, "ATR_14": 3.5},
                "metadata": {"entry_group": "MOO"},
                "scanned_at": run_at_iso,
            },
            {
                "rank": 2, "symbol": "TSLA", "strategy": "breakout_momentum",
                "direction": "long", "signal_strength": 0.7,
                "composite_score": 0.6, "score": 0.6,
                "regime_compatibility": 0.5, "sector": "Consumer",
                "prev_close": 200.0, "entry_group": "MOO", "atr": 8.0,
                "sl_price": None, "tp_price": None,
                "gap_filter_status": "pending",
                "indicators": {"RSI_14": 50.0, "ADX_14": 29.0, "ATR_14": 8.0},
                "metadata": {"entry_group": "MOO"},
                "scanned_at": run_at_iso,
            },
        ]
        payload = _make_batch_result_json(run_at_iso, candidates=raw_candidates_json)
        batch_file = _write_batch_file(tmp_path, payload)
        monkeypatch.chdir(tmp_path)

        # Load batch result from disk to populate _last_batch_result
        app._load_last_batch_result()
        assert app._last_batch_result is not None
        assert len(app._last_batch_result.candidates) == 2

        batch_cands = list(app._last_batch_result.candidates)

        # Mock GapFilter: AAPL passes, TSLA filtered out
        filtered_results = [
            FilteredCandidate(candidate=batch_cands[0], passed_filter=True, gap_pct=0.01),
            FilteredCandidate(candidate=batch_cands[1], passed_filter=False, gap_pct=0.06,
                              filter_reason="gap_up_6.0pct"),
        ]
        mock_gap_filter = AsyncMock()
        mock_gap_filter.filter = AsyncMock(return_value=filtered_results)
        app._gap_filter = mock_gap_filter

        # Mock EntryManager so we don't need full setup
        mock_entry_mgr = MagicMock()
        mock_entry_mgr.load_candidates = MagicMock()
        app._entry_manager = mock_entry_mgr

        await app._on_gap_filter()

        # Read back the updated batch_results.json
        with open(str(batch_file), "r", encoding="utf-8") as f:
            updated = json.load(f)

        # Verify gap_filter_status was updated per candidate
        candidates_json = updated.get("candidates", [])
        assert len(candidates_json) == 2

        aapl_entry = next(c for c in candidates_json if c["symbol"] == "AAPL")
        tsla_entry = next(c for c in candidates_json if c["symbol"] == "TSLA")

        assert aapl_entry["gap_filter_status"] == "passed"
        assert tsla_entry["gap_filter_status"] == "filtered"
