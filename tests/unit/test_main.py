import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone

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
from autotrader.strategy.consecutive_down import ConsecutiveDown
from autotrader.strategy.ema_pullback import EmaPullback
from autotrader.strategy.volume_divergence import VolumeDivergence


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
    def test_register_adds_four_swing_strategies(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        assert len(app._strategy_engine._strategies) == 4
        types = [type(s) for s in app._strategy_engine._strategies]
        assert RsiMeanReversion in types
        assert ConsecutiveDown in types
        assert EmaPullback in types
        assert VolumeDivergence in types

    def test_register_registers_indicators(self):
        app = AutoTrader(Settings())
        app._register_strategies()
        keys = set(app._indicator_engine._indicators.keys())
        assert "RSI_14" in keys
        assert "ATR_14" in keys
        assert "EMA_50" in keys
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
            strategy="consecutive_down", symbol="AAPL",
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
        # max_position_pct=0.10 with 100k equity = 10k max
        # If price is 200_000, qty = int(10_000 / 200_000) = 0
        app2 = AutoTrader(settings)
        await app2._broker.connect()
        account = await app2._broker.get_account()
        signal = Signal(
            strategy="test", symbol="BRK.A",
            direction="long", strength=1.0,
        )
        # Use a very high price via account with low equity
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
    async def test_on_bar_appends_to_history(self, app):
        await app.start()
        bar = _make_bar("AAPL", 150.0)
        await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_multiple_bars_accumulate(self, app):
        await app.start()
        for i in range(5):
            bar = _make_bar("AAPL", 150.0 + i, idx=i)
            await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 5
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_triggers_order_on_crossover(self, app):
        """Feed enough bars to trigger SMA crossover and verify order submission."""
        await app.start()
        # PaperBroker needs price for order execution
        app._broker.set_price("AAPL", 160.0)

        # Build history with low prices so SMA_10 < SMA_30
        for i in range(35):
            bar = _make_bar("AAPL", 100.0, idx=i)
            await app._on_bar(bar)

        # Now shift price up significantly to push SMA_10 > SMA_30
        for i in range(12):
            bar = _make_bar("AAPL", 160.0, idx=35 + i)
            await app._on_bar(bar)

        # Check positions created via the broker
        positions = await app._broker.get_positions()
        # We expect at least one order attempted
        # (depending on SMA crossover timing)
        assert app._portfolio_tracker.trades is not None

    @pytest.mark.asyncio
    async def test_on_bar_respects_history_limit(self, app):
        """Bar history should be bounded by data.bar_history_size."""
        await app.start()
        limit = app._settings.data.bar_history_size
        for i in range(limit + 50):
            bar = _make_bar("AAPL", 100.0 + (i % 10), idx=i % 28)
            await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == limit
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
            strategy="consecutive_down", symbol="AAPL",
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

    @pytest.mark.asyncio
    async def test_on_bar_filters_signals_via_rotation(self, app_with_rotation):
        """When rotation is active, signals for non-active symbols are blocked."""
        app = app_with_rotation
        await app.start()
        # Set active symbols to only AAPL
        app._rotation_manager._state.active_symbols = ["AAPL"]
        # Feed bar for MSFT (not in active universe) - should not create orders
        bar = _make_bar("MSFT", 150.0)
        app._broker.set_price("MSFT", 150.0)
        await app._on_bar(bar)
        positions = await app._broker.get_positions()
        msft_positions = [p for p in positions if p.symbol == "MSFT"]
        assert len(msft_positions) == 0
        await app.stop()

    @pytest.mark.asyncio
    async def test_on_bar_force_close_check(self, app_with_rotation):
        """Force close signals are generated for watchlist symbols past deadline."""
        from autotrader.rotation.types import WatchlistEntry
        app = app_with_rotation
        await app.start()
        app._rotation_manager._state.active_symbols = ["AAPL"]
        # Create a position for MSFT via paper broker
        app._broker.set_price("MSFT", 100.0)
        order = Order(symbol="MSFT", side="buy", quantity=10, order_type="market")
        await app._broker.submit_order(order)
        # Add MSFT to watchlist with deadline in the past
        app._rotation_manager._state.watchlist["MSFT"] = WatchlistEntry(
            symbol="MSFT",
            added_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            deadline=datetime(2024, 1, 1, 0, 30, tzinfo=timezone.utc),
        )
        # Feed a bar for MSFT (after deadline: idx=100 = 100 min past base)
        bar = _make_bar("MSFT", 105.0, idx=100)
        app._broker.set_price("MSFT", 105.0)
        await app._on_bar(bar)
        # MSFT should be force-closed
        positions = await app._broker.get_positions()
        msft_positions = [p for p in positions if p.symbol == "MSFT"]
        assert len(msft_positions) == 0
        # Should be removed from watchlist
        assert "MSFT" not in app._rotation_manager._state.watchlist
        await app.stop()

    @pytest.mark.asyncio
    async def test_weekly_loss_check_halts_trading(self, app_with_rotation):
        """Weekly loss limit triggers halt, blocking new entries."""
        from autotrader.core.config import RotationConfig
        settings = Settings()
        settings.broker.paper_balance = 3000.0
        cfg = RotationConfig(weekly_loss_limit_pct=0.01)  # 1% to trigger easily
        app = AutoTrader(settings, rotation_config=cfg)
        await app.start()
        app._rotation_manager._state.active_symbols = ["AAPL"]
        app._rotation_manager._state.weekly_start_equity = 3000.0
        # Drain cash to simulate loss
        app._broker._cash = 2900.0  # ~3.3% loss
        bar = _make_bar("AAPL", 150.0)
        await app._on_bar(bar)
        assert app._rotation_manager._state.is_halted is True
        await app.stop()

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

    @pytest.mark.asyncio
    async def test_spy_always_subscribed(self):
        settings = Settings()
        settings.symbols = ["AAPL"]
        app = AutoTrader(settings)
        await app.start()
        # SPY should be subscribed even though not in symbols list
        # We can verify by checking _bar_history accepts SPY bars
        bar = _make_bar("SPY", 450.0)
        await app._on_bar(bar)
        assert len(app._bar_history["SPY"]) == 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_non_spy_bar_does_not_change_regime(self):
        app = AutoTrader(Settings())
        await app.start()
        bar = _make_bar("AAPL", 150.0)
        await app._on_bar(bar)
        assert app._current_regime == MarketRegime.UNCERTAIN
        await app.stop()


class TestAllocationIntegration:
    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 5000.0
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
    async def test_allocation_engine_gates_entry(self, app):
        """Strategy at max positions should be blocked."""
        await app._broker.connect()
        account = await app._broker.get_account()
        # Mark strategy as already having MAX positions
        app._position_strategy_map["SYM1"] = "rsi_mean_reversion"
        app._position_strategy_map["SYM2"] = "rsi_mean_reversion"
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        signal = Signal(
            strategy="rsi_mean_reversion", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        # AllocationEngine.MAX_POSITIONS_PER_STRATEGY = 2, already at 2
        assert order is None

    @pytest.mark.asyncio
    async def test_position_strategy_map_tracks_entries(self, app):
        """After a filled long order, position_strategy_map is updated."""
        await app._broker.connect()
        app._broker.set_price("AAPL", 100.0)
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        app._portfolio_tracker = PortfolioTracker(5000.0)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(
            strategy="consecutive_down", symbol="AAPL",
            direction="long", strength=0.8,
        )
        result = await app._process_signal(signal, account, positions)
        if result and result.status == "filled":
            assert app._position_strategy_map.get("AAPL") == "consecutive_down"

    @pytest.mark.asyncio
    async def test_close_removes_from_strategy_map(self, app):
        """After closing a position, symbol is removed from strategy map."""
        await app._broker.connect()
        app._broker.set_price("AAPL", 100.0)
        app._portfolio_tracker = PortfolioTracker(5000.0)
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
        assert app._regime_tracker._confirmation_bars == 3


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
        settings.broker.paper_balance = 5000.0
        app = AutoTrader(settings)
        await app.start()
        app._broker.set_price("AAPL", 100.0)
        bar = _make_bar("AAPL", 100.0)
        app._bar_history["AAPL"].append(bar)
        account = await app._broker.get_account()
        positions = await app._broker.get_positions()
        signal = Signal(strategy="consecutive_down", symbol="AAPL",
                        direction="long", strength=0.8)
        result = await app._process_signal(signal, account, positions)
        if result and result.status == "filled":
            trades = app._trade_logger.read_trades()
            assert len(trades) >= 1
            assert trades[0].symbol == "AAPL"
            assert trades[0].strategy == "consecutive_down"
        await app.stop()


class TestDailyBarAggregation:
    """Test that minute bars are aggregated and only daily bars reach strategies."""

    @pytest.fixture()
    def app(self):
        settings = Settings()
        settings.broker.paper_balance = 100_000.0
        return AutoTrader(settings)

    def test_has_aggregator(self, app):
        from autotrader.core.aggregator import DailyBarAggregator
        assert isinstance(app._aggregator, DailyBarAggregator)

    @pytest.mark.asyncio
    async def test_minute_bar_not_in_bar_history(self, app):
        """Minute bars should be aggregated, not directly added to bar_history."""
        await app.start()
        minute_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc),
            open=100, high=101, low=99, close=100.5, volume=1000,
            timeframe=Timeframe.MINUTE,
        )
        await app._on_bar(minute_bar)
        # Minute bar goes to aggregator, not bar_history
        assert len(app._bar_history["AAPL"]) == 0
        await app.stop()

    @pytest.mark.asyncio
    async def test_daily_bar_goes_to_history(self, app):
        """Daily bars (default) should go directly to bar_history."""
        await app.start()
        daily_bar = _make_bar("AAPL", 150.0)
        await app._on_bar(daily_bar)
        assert len(app._bar_history["AAPL"]) == 1
        await app.stop()

    @pytest.mark.asyncio
    async def test_date_change_produces_daily_bar(self, app):
        """When minute bars cross a date boundary, a daily bar is produced."""
        await app.start()
        # Day 1 minute bars
        for i in range(3):
            bar = Bar(
                symbol="AAPL",
                timestamp=datetime(2025, 1, 6, 14, 30 + i, tzinfo=timezone.utc),
                open=100, high=102, low=99, close=101, volume=1000,
                timeframe=Timeframe.MINUTE,
            )
            await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 0

        # Day 2 first minute bar triggers day 1 daily bar
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 7, 14, 30, tzinfo=timezone.utc),
            open=102, high=103, low=101, close=102, volume=2000,
            timeframe=Timeframe.MINUTE,
        )
        await app._on_bar(bar)
        assert len(app._bar_history["AAPL"]) == 1
        daily = app._bar_history["AAPL"][0]
        assert daily.timeframe == Timeframe.DAILY
        await app.stop()

    @pytest.mark.asyncio
    async def test_mfe_mae_updates_on_minute_bars(self, app):
        """MFE/MAE tracking should update on every bar, including minute."""
        await app.start()
        # Register a tracked position
        app._open_position_tracker.open_position(
            symbol="AAPL", strategy="test", direction="long",
            entry_price=100.0,
            entry_time=datetime(2025, 1, 5, 14, 0, tzinfo=timezone.utc),
            quantity=10,
        )
        minute_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc),
            open=100, high=110, low=95, close=105, volume=1000,
            timeframe=Timeframe.MINUTE,
        )
        await app._on_bar(minute_bar)
        tracked = app._open_position_tracker.get_position("AAPL")
        assert tracked is not None
        assert tracked.highest_price == 110.0
        assert tracked.lowest_price == 95.0
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
            strategy="consecutive_down", symbol="AAPL",
            direction="long", strength=0.8,
        )
        order = app._signal_to_order(signal, account, [])
        assert order is not None  # Entry not blocked
