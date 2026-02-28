"""AutoTrader v3 - Batch+Intraday Hybrid Architecture.

Architecture overview:
  - 8:00 PM ET:   NightlyScanner.scan()  -> BatchResult (candidates)
  - 9:25 AM ET:   GapFilter.filter()     -> filtered Candidate list
  - 9:30 AM ET:   EntryManager.execute_moo()           (Group A)
  - 9:45 AM ET:   EntryManager.execute_confirmation()  (Group B starts)
  - 10:00 AM ET:  EntryManager.close_entry_window()    (discard unconfirmed)
  - Continuous:   PositionMonitor streams bars, evaluates exits

Integration with existing v2 modules:
  - AlpacaAdapter (broker/alpaca_adapter.py)  - unchanged
  - RiskManager (risk/manager.py)             - unchanged
  - AllocationEngine (portfolio/allocation_engine.py) - unchanged
  - RegimeDetector (portfolio/regime_detector.py)    - unchanged
  - IndicatorEngine (indicators/engine.py)           - unchanged
  - TradeLogger (portfolio/trade_logger.py)          - unchanged

Batch module integration (autotrader/batch/ - developed by another agent):
  - NightlyScanner, GapFilter, SignalRanker are injected via Protocol
    interfaces defined in this file.
  - If batch components are not provided, the system falls back to
    the legacy v2 direct-signal strategy flow.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from autotrader.core.aggregator import DailyBarAggregator
from autotrader.core.config import RotationConfig, Settings, load_settings
from autotrader.core.event_bus import EventBus
from autotrader.core.logger import setup_logging
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal, Timeframe,
)
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.execution.entry_manager import Candidate, EntryManager
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.execution.position_monitor import PositionMonitor
from autotrader.indicators.engine import IndicatorEngine
from autotrader.indicators.base import IndicatorSpec
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.position_tracker import OpenPositionTracker
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.portfolio.regime_position_reviewer import RegimePositionReviewer
from autotrader.portfolio.regime_tracker import RegimeTracker
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.portfolio.trade_logger import EquitySnapshot, LiveTradeRecord, TradeLogger
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.rotation.event_driven import EventDrivenRotation
from autotrader.rotation.manager import RotationManager
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.consecutive_down import ConsecutiveDown
from autotrader.strategy.ema_pullback import EmaPullback
from autotrader.strategy.volume_divergence import VolumeDivergence

logger = logging.getLogger("autotrader.main")

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Batch module Protocol interfaces (dependency injection)
# ---------------------------------------------------------------------------

@runtime_checkable
class BatchResult(Protocol):
    """Protocol for the result of a nightly scan.

    The concrete implementation lives in autotrader/batch/ (another agent).
    This protocol is satisfied by any object that exposes ``candidates``.
    """

    @property
    def candidates(self) -> list[Candidate]:
        """List of Candidate objects from the scan."""
        ...


@runtime_checkable
class NightlyScannerProtocol(Protocol):
    """Protocol for the nightly batch scanner."""

    async def scan(self) -> Any:
        """Run the nightly scan.  Returns an object satisfying BatchResult."""
        ...


@runtime_checkable
class GapFilterProtocol(Protocol):
    """Protocol for the pre-market gap filter (9:25 AM ET)."""

    async def filter(self, candidates: list[Candidate]) -> list[Candidate]:
        """Filter candidates based on overnight gap size.

        Removes candidates where the overnight gap exceeds the configured
        max_gap_pct threshold.

        Args:
            candidates: Raw candidates from NightlyScanner.

        Returns:
            Filtered list of Candidate objects.
        """
        ...


@runtime_checkable
class SignalRankerProtocol(Protocol):
    """Protocol for ranking candidates by signal quality."""

    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        """Return candidates sorted from highest to lowest quality.

        Args:
            candidates: Gap-filtered candidates.

        Returns:
            Sorted list (highest quality first).
        """
        ...


# ---------------------------------------------------------------------------
# Scheduled task times (US Eastern)
# ---------------------------------------------------------------------------

_NIGHTLY_SCAN_HOUR: int = 20   # 8:00 PM ET
_NIGHTLY_SCAN_MINUTE: int = 0

_GAP_FILTER_HOUR: int = 9      # 9:25 AM ET
_GAP_FILTER_MINUTE: int = 25

_MOO_HOUR: int = 9             # 9:30 AM ET
_MOO_MINUTE: int = 30

_CONFIRMATION_HOUR: int = 9    # 9:45 AM ET
_CONFIRMATION_MINUTE: int = 45

_ENTRY_WINDOW_CLOSE_HOUR: int = 10   # 10:00 AM ET
_ENTRY_WINDOW_CLOSE_MINUTE: int = 0

_DAILY_RESET_HOUR: int = 9     # 9:29 AM ET (just before MOO)
_DAILY_RESET_MINUTE: int = 29


class AutoTrader:
    """Batch+intraday hybrid AutoTrader.

    Integrates nightly batch scanning with real-time intraday execution.
    Supports legacy v2 strategy-engine flow as a fallback when batch
    components are not injected.

    Args:
        settings: Loaded Settings instance.
        rotation_config: Optional weekly rotation configuration.
        nightly_scanner: Optional NightlyScannerProtocol implementation.
        gap_filter: Optional GapFilterProtocol implementation.
        signal_ranker: Optional SignalRankerProtocol implementation.
        earnings_cal: Optional earnings calendar for blackout filtering.
    """

    def __init__(
        self,
        settings: Settings,
        rotation_config: RotationConfig | None = None,
        nightly_scanner: NightlyScannerProtocol | None = None,
        gap_filter: GapFilterProtocol | None = None,
        signal_ranker: SignalRankerProtocol | None = None,
        earnings_cal: object | None = None,
    ) -> None:
        self._settings = settings
        self._bus = EventBus()

        # --- Broker ---
        self._broker = self._create_broker()

        # --- Core engines ---
        self._indicator_engine = IndicatorEngine()
        self._strategy_engine = StrategyEngine()
        self._risk_manager = RiskManager(settings.risk)
        self._position_sizer = PositionSizer(settings.risk)

        # --- Regime detection ---
        self._regime_detector = RegimeDetector()
        self._allocation_engine = AllocationEngine(self._regime_detector)
        self._current_regime: MarketRegime = MarketRegime.UNCERTAIN
        self._spy_bb_width_history: deque[float] = deque(maxlen=20)
        self._regime_proxy_symbol: str = settings.scheduler.regime_proxy_symbol
        self._regime_tracker = RegimeTracker(confirmation_bars=3)
        self._regime_reviewer = RegimePositionReviewer()

        # --- Bar history ---
        self._bar_history: dict[str, deque[Bar]] = defaultdict(
            lambda: deque(maxlen=settings.data.bar_history_size)
        )
        self._daily_bar_history: dict[str, deque[Bar]] = defaultdict(
            lambda: deque(maxlen=settings.data.bar_history_size)
        )
        self._aggregator = DailyBarAggregator()

        # --- Position tracking ---
        self._portfolio_tracker: PortfolioTracker | None = None
        self._open_position_tracker = OpenPositionTracker()
        self._position_strategy_map: dict[str, str] = {}

        # --- Execution layer (new v3) ---
        self._order_manager: OrderManager | None = None
        self._exit_rule_engine = ExitRuleEngine()
        self._entry_manager: EntryManager | None = None
        self._position_monitor: PositionMonitor | None = None

        # Map from symbol -> HeldPosition for positions managed by v3 execution
        self._held_positions: dict[str, HeldPosition] = {}

        # --- Batch pipeline components (injected) ---
        self._nightly_scanner: NightlyScannerProtocol | None = nightly_scanner
        self._gap_filter: GapFilterProtocol | None = gap_filter
        self._signal_ranker: SignalRankerProtocol | None = signal_ranker
        self._last_batch_result: Any | None = None  # BatchResult from nightly scan

        # --- Rotation ---
        self._rotation_manager: RotationManager | None = None
        if rotation_config is not None:
            self._rotation_manager = RotationManager(rotation_config, earnings_cal)

        # --- Event-driven rotation ---
        self._event_rotation = EventDrivenRotation(
            cooldown_hours=settings.event_rotation.cooldown_hours,
            vix_spike_trigger=settings.event_rotation.vix_spike_trigger,
            regime_triggers=settings.event_rotation.regime_triggers,
            enabled=settings.event_rotation.enable_event_driven,
        )

        # --- VIX sentiment ---
        self._vix_fetcher = None
        if settings.sentiment.enable_vix:
            from autotrader.data.market_sentiment import VIXFetcher
            self._vix_fetcher = VIXFetcher(
                symbol=settings.sentiment.vix_symbol,
                cache_ttl_seconds=settings.sentiment.cache_ttl_seconds,
            )

        # --- Trade logging ---
        self._trade_logger: TradeLogger | None = None
        if settings.performance.enable_trade_log:
            self._trade_logger = TradeLogger(
                settings.performance.trade_log_path,
                settings.performance.equity_snapshot_path,
            )

        # --- Scheduler tasks ---
        self._running = False
        self._stream_task: asyncio.Task | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._batch_scheduler_task: asyncio.Task | None = None
        self._daily_regime_task: asyncio.Task | None = None
        self._last_regime_update_date: date | None = None

        self._bar_count: int = 0

    # -----------------------------------------------------------------------
    # Startup / Shutdown
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise all components and begin trading."""
        logger.info("Starting %s (v3 batch+intraday)", self._settings.system.name)

        await self._broker.connect()
        account = await self._broker.get_account()
        logger.info("Account equity: %.2f", account.equity)

        self._portfolio_tracker = PortfolioTracker(account.equity)
        self._register_strategies()
        self._running = True

        # Load historical daily bars for regime and indicator warmup
        await self._warm_up_from_history()

        # Write initial equity snapshot so the dashboard has data immediately
        if self._trade_logger is not None:
            try:
                positions = await self._broker.get_positions()
                snap = EquitySnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    equity=account.equity,
                    cash=account.cash,
                    regime=self._current_regime.value,
                    position_count=len(positions),
                    open_positions=[p.symbol for p in positions],
                )
                self._trade_logger.log_equity(snap)
                logger.info("Initial equity snapshot written: %.2f", account.equity)
            except Exception:
                logger.exception("Failed to write initial equity snapshot")

        # Initialise v3 execution engine
        self._initialise_execution_engine()

        # Load any existing open positions into v3 PositionMonitor
        await self._load_existing_positions()

        # Start daily regime refresh scheduler
        self._daily_regime_task = asyncio.create_task(self._daily_regime_scheduler())

        # Start legacy symbol stream (for regime monitoring via SPY etc.)
        symbols = list(set(self._settings.symbols + [self._regime_proxy_symbol]))
        await self._broker.subscribe_bars(symbols, self._on_bar)
        if hasattr(self._broker, "run_stream"):
            self._stream_task = asyncio.create_task(
                asyncio.to_thread(self._broker.run_stream)
            )

        # Start batch+intraday scheduler
        self._batch_scheduler_task = asyncio.create_task(self._batch_intraday_scheduler())

        # Legacy rotation scheduler (still active for weekly rotation)
        if self._rotation_manager and self._settings.scheduler.enable_rotation_scheduler:
            self._scheduler_task = asyncio.create_task(self._rotation_scheduler())

        logger.info("AutoTrader v3 started successfully")

    async def stop(self) -> None:
        """Gracefully shutdown all components."""
        logger.info("Stopping %s", self._settings.system.name)
        self._running = False

        # Stop PositionMonitor
        if self._position_monitor is not None:
            await self._position_monitor.stop()

        # Cancel all background tasks
        for task_attr in (
            "_daily_regime_task",
            "_batch_scheduler_task",
            "_scheduler_task",
            "_stream_task",
        ):
            task: asyncio.Task | None = getattr(self, task_attr, None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                setattr(self, task_attr, None)

        await self._broker.disconnect()
        logger.info("AutoTrader v3 stopped")

    # -----------------------------------------------------------------------
    # Execution engine initialisation
    # -----------------------------------------------------------------------

    def _initialise_execution_engine(self) -> None:
        """Wire up the v3 execution components."""
        if not isinstance(self._broker, type(self._broker)) or not hasattr(self._broker, "submit_order"):
            logger.warning("Broker is not AlpacaAdapter; execution engine may not function correctly")

        # OrderManager wraps the broker (expects AlpacaAdapter)
        if hasattr(self._broker, "_api_key"):
            # It IS an AlpacaAdapter
            self._order_manager = OrderManager(self._broker)  # type: ignore[arg-type]
        else:
            # Fallback: wrap the PaperBroker via a thin adapter shim
            self._order_manager = _PaperOrderManager(self._broker)  # type: ignore[assignment]

        self._entry_manager = EntryManager(
            order_manager=self._order_manager,
            allocation_engine=self._allocation_engine,
            risk_manager=self._risk_manager,
            exit_rule_engine=self._exit_rule_engine,
        )

        self._position_monitor = PositionMonitor(
            adapter=self._broker,  # type: ignore[arg-type]
            order_manager=self._order_manager,
            exit_rule_engine=self._exit_rule_engine,
            indicator_engine=self._indicator_engine,
        )
        self._position_monitor.register_exit_callback(self._on_position_exit)

        logger.info("V3 execution engine initialised")

    async def _load_existing_positions(self) -> None:
        """Re-register any open positions from a previous session into PositionMonitor."""
        try:
            positions = await self._broker.get_positions()
            if not positions:
                return

            account = await self._broker.get_account()
            logger.info("Loading %d existing open positions into monitor", len(positions))

            today_et = datetime.now(timezone.utc).astimezone(_ET).date()
            for pos in positions:
                strategy = self._position_strategy_map.get(pos.symbol, "unknown")
                # Use ATR from indicator history if available
                history = self._bar_history.get(pos.symbol)
                atr = 1.0
                if history and len(history) >= 14:
                    indicators = self._indicator_engine.compute(history)
                    atr_raw = indicators.get("ATR_14")
                    if isinstance(atr_raw, (int, float)) and atr_raw > 0:
                        atr = float(atr_raw)

                held = HeldPosition(
                    symbol=pos.symbol,
                    strategy=strategy,
                    direction="long" if pos.side == "long" else "short",
                    entry_price=pos.avg_entry_price,
                    entry_atr=atr,
                    entry_date_et=today_et,  # Conservative: treat as entry day
                    qty=pos.quantity,
                    highest_price=pos.avg_entry_price,
                    lowest_price=pos.avg_entry_price,
                )
                self._held_positions[pos.symbol] = held
                if self._position_monitor is not None:
                    self._position_monitor.add_position(held)

            # Start the position monitor stream
            if self._position_monitor is not None:
                await self._position_monitor.start()

        except Exception:
            logger.exception("Failed to load existing positions")

    # -----------------------------------------------------------------------
    # Batch+intraday scheduler
    # -----------------------------------------------------------------------

    async def _batch_intraday_scheduler(self) -> None:
        """Background task that drives the batch+intraday daily workflow.

        Checks current US Eastern time every 30 seconds and fires
        the appropriate action when the time window is reached.
        """
        _fired: dict[str, date | None] = {
            "daily_reset": None,
            "gap_filter": None,
            "moo": None,
            "confirmation": None,
            "entry_close": None,
            "nightly_scan": None,
        }

        while self._running:
            await asyncio.sleep(30)
            now_et = datetime.now(timezone.utc).astimezone(_ET)
            today_et = now_et.date()
            h, m = now_et.hour, now_et.minute

            # 9:29 AM: Daily reset (must run before MOO)
            if h == _DAILY_RESET_HOUR and m >= _DAILY_RESET_MINUTE and _fired["daily_reset"] != today_et:
                _fired["daily_reset"] = today_et
                await self._on_daily_reset(today_et)

            # 9:25 AM: Gap filter
            if h == _GAP_FILTER_HOUR and m >= _GAP_FILTER_MINUTE and _fired["gap_filter"] != today_et:
                _fired["gap_filter"] = today_et
                await self._on_gap_filter()

            # 9:30 AM: Group A MOO entries
            if h == _MOO_HOUR and m >= _MOO_MINUTE and _fired["moo"] != today_et:
                _fired["moo"] = today_et
                await self._on_moo()

            # 9:45 AM: Group B confirmation window
            if (
                h == _CONFIRMATION_HOUR
                and m >= _CONFIRMATION_MINUTE
                and (h < _ENTRY_WINDOW_CLOSE_HOUR or (h == _ENTRY_WINDOW_CLOSE_HOUR and m < _ENTRY_WINDOW_CLOSE_MINUTE))
                and _fired["confirmation"] != today_et
            ):
                _fired["confirmation"] = today_et
                await self._on_confirmation_window()

            # 10:00 AM: Close entry window
            if h == _ENTRY_WINDOW_CLOSE_HOUR and m >= _ENTRY_WINDOW_CLOSE_MINUTE and _fired["entry_close"] != today_et:
                _fired["entry_close"] = today_et
                await self._on_entry_window_close()

            # 8:00 PM: Nightly scan
            if h == _NIGHTLY_SCAN_HOUR and m >= _NIGHTLY_SCAN_MINUTE and _fired["nightly_scan"] != today_et:
                _fired["nightly_scan"] = today_et
                await self._on_nightly_scan()

    # -----------------------------------------------------------------------
    # Scheduled event handlers
    # -----------------------------------------------------------------------

    async def _on_daily_reset(self, today_et: date) -> None:
        """Reset daily state at 9:29 AM ET, just before market open."""
        logger.info("Daily reset: %s", today_et)
        self._risk_manager.reset_daily_pnl()
        self._exit_rule_engine.on_new_trading_day(today_et)
        if self._entry_manager is not None:
            self._entry_manager.on_new_trading_day(today_et)

    async def _on_gap_filter(self) -> None:
        """Apply gap filter to last batch result at 9:25 AM ET."""
        if self._last_batch_result is None:
            logger.info("Gap filter: no nightly batch result; skipping")
            return
        if self._gap_filter is None:
            logger.info("Gap filter: no GapFilter injected; using raw candidates")
            return

        try:
            candidates = list(self._last_batch_result.candidates)
            filtered = await self._gap_filter.filter(candidates)
            # Rank if ranker available
            if self._signal_ranker is not None:
                filtered = self._signal_ranker.rank(filtered)
            # Reload into EntryManager
            if self._entry_manager is not None:
                self._entry_manager.load_candidates(filtered)
            logger.info(
                "Gap filter complete: %d -> %d candidates",
                len(candidates), len(filtered),
            )
        except Exception:
            logger.exception("Gap filter failed")

    async def _on_moo(self) -> None:
        """Execute Group A market-on-open orders at 9:30 AM ET."""
        if self._entry_manager is None:
            return
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            today_et = datetime.now(timezone.utc).astimezone(_ET).date()

            new_positions = await self._entry_manager.execute_moo(
                account=account,
                positions=positions,
                regime=self._current_regime,
                current_date_et=today_et,
            )
            for held in new_positions:
                self._held_positions[held.symbol] = held
                self._position_strategy_map[held.symbol] = held.strategy
                if self._position_monitor is not None:
                    self._position_monitor.add_position(held)
                # Register with MFE/MAE tracker
                self._open_position_tracker.open_position(
                    symbol=held.symbol,
                    strategy=held.strategy,
                    direction=held.direction,
                    entry_price=held.entry_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=held.qty,
                )

            if new_positions:
                logger.info("MOO entries: %d positions opened", len(new_positions))
                await self._log_equity_snapshot()
        except Exception:
            logger.exception("MOO execution failed")

    async def _on_confirmation_window(self) -> None:
        """Execute Group B confirmation entries between 9:45 and 10:00 AM ET."""
        if self._entry_manager is None:
            return
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            today_et = datetime.now(timezone.utc).astimezone(_ET).date()

            # Fetch current intraday prices for all pending Group B symbols
            current_prices = await self._fetch_current_prices()

            new_positions = await self._entry_manager.execute_confirmation(
                account=account,
                positions=positions,
                regime=self._current_regime,
                current_date_et=today_et,
                current_prices=current_prices,
            )
            for held in new_positions:
                self._held_positions[held.symbol] = held
                self._position_strategy_map[held.symbol] = held.strategy
                if self._position_monitor is not None:
                    self._position_monitor.add_position(held)
                self._open_position_tracker.open_position(
                    symbol=held.symbol,
                    strategy=held.strategy,
                    direction=held.direction,
                    entry_price=held.entry_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=held.qty,
                )

            if new_positions:
                logger.info("Confirmation entries: %d positions opened", len(new_positions))
                await self._log_equity_snapshot()
        except Exception:
            logger.exception("Confirmation window execution failed")

    async def _on_entry_window_close(self) -> None:
        """Discard unconfirmed Group B candidates at 10:00 AM ET."""
        if self._entry_manager is None:
            return
        discarded = self._entry_manager.close_entry_window()
        if discarded:
            logger.info("Entry window closed: %d candidates discarded", discarded)

    async def _on_nightly_scan(self) -> None:
        """Run the nightly batch scan at 8:00 PM ET."""
        if self._nightly_scanner is None:
            logger.debug("Nightly scan: no NightlyScanner injected; skipping")
            return
        try:
            logger.info("Nightly scan starting...")
            result = await self._nightly_scanner.scan()
            self._last_batch_result = result
            candidate_count = len(result.candidates) if hasattr(result, "candidates") else 0
            logger.info("Nightly scan complete: %d candidates", candidate_count)
        except Exception:
            logger.exception("Nightly scan failed")

    # -----------------------------------------------------------------------
    # Position exit callback (from PositionMonitor)
    # -----------------------------------------------------------------------

    async def _on_position_exit(
        self, symbol: str, reason: str, fill_price: float, pnl: float,
    ) -> None:
        """Called by PositionMonitor after each exit is executed.

        Updates risk manager, portfolio tracker, and trade logger.

        Args:
            symbol: Closed ticker.
            reason: Exit reason string from ExitRuleEngine.
            fill_price: Actual exit fill price.
            pnl: Realised profit/loss.
        """
        held = self._held_positions.pop(symbol, None)
        self._position_strategy_map.pop(symbol, None)

        # Update MFE/MAE tracker
        tracked = self._open_position_tracker.close_position(symbol)
        mfe = tracked.mfe if tracked else 0.0
        mae = tracked.mae if tracked else 0.0
        bars_held = tracked.bar_count if tracked else 0

        # Update risk manager
        self._risk_manager.record_pnl(pnl)

        # Update portfolio tracker
        if self._portfolio_tracker is not None and held is not None:
            side = "sell" if held.direction == "long" else "buy"
            self._portfolio_tracker.record_trade(
                symbol=symbol,
                side=side,
                qty=held.qty,
                price=fill_price,
                pnl=pnl,
            )

        # Write trade record
        if self._trade_logger is not None and held is not None:
            try:
                account = await self._broker.get_account()
                record = LiveTradeRecord(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    symbol=symbol,
                    strategy=held.strategy,
                    direction="close",
                    side="sell" if held.direction == "long" else "buy",
                    quantity=held.qty,
                    price=fill_price,
                    pnl=pnl,
                    regime=self._current_regime.value,
                    equity_after=account.equity,
                    metadata={"exit_reason": reason},
                    exit_reason=reason,
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                )
                self._trade_logger.log_trade(record)
            except Exception:
                logger.exception("Trade log write failed for %s exit", symbol)

        logger.info(
            "Exit recorded: %s, reason=%s, pnl=%.2f, mfe=%.3f, mae=%.3f, bars=%d",
            symbol, reason, pnl, mfe, mae, bars_held,
        )

    # -----------------------------------------------------------------------
    # Legacy bar handler (regime monitoring + v2 fallback)
    # -----------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        """Handle incoming bars from the subscription stream.

        Used for:
        - SPY regime monitoring
        - MFE/MAE tracking for non-v3 positions
        - Legacy v2 strategy fallback when no batch components injected
        - Equity snapshot logging
        """
        # MFE/MAE tracking for open positions
        self._open_position_tracker.update_prices(
            bar.symbol, bar.high, bar.low, bar.close,
        )

        account = await self._broker.get_account()
        positions = await self._broker.get_positions()

        # Rotation manager: force close, weekly loss
        if self._rotation_manager:
            open_syms = [p.symbol for p in positions]
            force_close = self._rotation_manager.get_force_close_symbols(
                bar.timestamp, open_syms,
            )
            for sym in force_close:
                close_sig = Signal(
                    strategy="rotation_manager",
                    symbol=sym,
                    direction="close",
                    strength=1.0,
                    metadata={"exit_reason": "force_close"},
                )
                await self._process_legacy_signal(close_sig, account, positions)
                self._rotation_manager.on_position_closed(sym)
                positions = await self._broker.get_positions()
            self._rotation_manager.check_weekly_loss_limit(account.equity)

        # Equity snapshot
        self._bar_count += 1
        if (
            self._trade_logger is not None
            and self._bar_count % self._settings.performance.equity_snapshot_interval == 0
        ):
            snap = EquitySnapshot(
                timestamp=bar.timestamp.isoformat(),
                equity=account.equity,
                cash=account.cash,
                regime=self._current_regime.value,
                position_count=len(positions),
                open_positions=[p.symbol for p in positions],
            )
            self._trade_logger.log_equity(snap)

        # Route bar for aggregation and processing
        if bar.timeframe == Timeframe.MINUTE:
            daily_bar = self._aggregator.add(bar)
            if daily_bar is not None:
                await self._on_daily_bar(daily_bar)
        else:
            await self._on_daily_bar(bar)

    async def _on_daily_bar(self, bar: Bar) -> None:
        """Process a confirmed daily bar for regime and legacy signal flow."""
        history = self._bar_history[bar.symbol]
        history.append(bar)

        indicators = self._indicator_engine.compute(history)

        # Regime update from proxy symbol
        if bar.symbol == self._regime_proxy_symbol:
            self._update_regime(indicators)

        ctx = MarketContext(
            symbol=bar.symbol,
            bar=bar,
            indicators=indicators,
            history=history,
        )

        # V2 legacy fallback: run strategies directly when no batch components
        if self._nightly_scanner is None:
            signals = await self._strategy_engine.process(ctx)
            if not signals:
                return
            if self._rotation_manager:
                signals = self._rotation_manager.filter_signals(signals)
                if not signals:
                    return
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            for signal in signals:
                await self._process_legacy_signal(signal, account, positions)

    async def _process_signal(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> OrderResult | None:
        """Alias for _process_legacy_signal for backward compatibility with tests."""
        return await self._process_legacy_signal(signal, account, positions)

    async def _process_legacy_signal(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> OrderResult | None:
        """Process a strategy signal through the legacy v2 order pipeline.

        This path is used:
        - When no NightlyScanner is injected (pure v2 mode).
        - For rotation manager force-close signals regardless of mode.
        """
        if not self._risk_manager.validate(signal, account, positions):
            logger.info("Risk rejected signal: %s %s", signal.direction, signal.symbol)
            return None

        order = self._signal_to_order(signal, account, positions)
        if order is None:
            return None

        result = await self._broker.submit_order(order)
        logger.info(
            "Order %s: %s %s %.0f @ %.2f",
            result.status, order.side, order.symbol,
            result.filled_qty, result.filled_price,
        )

        if result.status == "filled":
            if signal.direction in ("long", "short"):
                self._position_strategy_map[signal.symbol] = signal.strategy
                self._open_position_tracker.open_position(
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    entry_price=result.filled_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=result.filled_qty,
                )
            elif signal.direction == "close":
                self._position_strategy_map.pop(signal.symbol, None)

            pnl = 0.0
            exit_reason = signal.metadata.get("exit_reason", "") if signal.metadata else ""
            mfe = mae = bars_held = 0
            if signal.direction == "close":
                pos = next((p for p in positions if p.symbol == order.symbol), None)
                if pos is not None:
                    if pos.side == "long":
                        pnl = (result.filled_price - pos.avg_entry_price) * result.filled_qty
                    else:
                        pnl = (pos.avg_entry_price - result.filled_price) * result.filled_qty
                tracked = self._open_position_tracker.close_position(signal.symbol)
                if tracked is not None:
                    mfe = tracked.mfe
                    mae = tracked.mae
                    bars_held = tracked.bar_count

            if self._portfolio_tracker is not None:
                self._portfolio_tracker.record_trade(
                    symbol=order.symbol,
                    side=order.side,
                    qty=result.filled_qty,
                    price=result.filled_price,
                    pnl=pnl,
                )
            self._risk_manager.record_pnl(pnl)

            if self._trade_logger is not None:
                account_after = await self._broker.get_account()
                record = LiveTradeRecord(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    side=order.side,
                    quantity=result.filled_qty,
                    price=result.filled_price,
                    pnl=pnl,
                    regime=self._current_regime.value,
                    equity_after=account_after.equity,
                    metadata=signal.metadata,
                    exit_reason=exit_reason,
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                )
                self._trade_logger.log_trade(record)

        return result

    def _signal_to_order(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> Order | None:
        """Convert a Signal to an Order for the legacy v2 flow."""
        _ET_TZ = ZoneInfo("America/New_York")

        if signal.direction == "close":
            pos = next((p for p in positions if p.symbol == signal.symbol), None)
            if pos is None:
                return None

            # PDT guard: block same-day close
            tracked = self._open_position_tracker.get_position(signal.symbol)
            if tracked is not None:
                entry_date = tracked.entry_time.astimezone(_ET_TZ).date()
                now_date = datetime.now(timezone.utc).astimezone(_ET_TZ).date()
                if entry_date == now_date:
                    logger.warning(
                        "PDT guard: blocking same-day close for %s (entered %s)",
                        signal.symbol, tracked.entry_time.isoformat(),
                    )
                    return None

            side = "sell" if pos.side == "long" else "buy"
            return Order(
                symbol=signal.symbol,
                side=side,
                quantity=pos.quantity,
                order_type="market",
            )

        if signal.direction in ("long", "short"):
            if signal.symbol in self._position_strategy_map:
                return None
            existing_pos = next((p for p in positions if p.symbol == signal.symbol), None)
            if existing_pos is not None:
                return None

            strategy_count = sum(
                1 for s in self._position_strategy_map.values()
                if s == signal.strategy
            )
            if not self._allocation_engine.should_enter(
                signal.strategy, self._current_regime, strategy_count,
            ):
                return None

            history = self._bar_history.get(signal.symbol)
            if not history:
                return None
            price = history[-1].close

            if account.cash < price:
                return None

            indicators = self._indicator_engine.compute(history)
            atr = indicators.get("ATR_14")

            qty = self._allocation_engine.get_position_size(
                signal.strategy, price, account.equity, self._current_regime,
                atr=atr, direction=signal.direction,
            )
            if qty <= 0:
                return None

            side = "buy" if signal.direction == "long" else "sell"
            order_type = "market"
            if signal.limit_price is not None:
                order_type = "limit"
            return Order(
                symbol=signal.symbol,
                side=side,
                quantity=qty,
                order_type=order_type,
                limit_price=signal.limit_price,
            )

        return None

    # -----------------------------------------------------------------------
    # Regime management
    # -----------------------------------------------------------------------

    def _update_regime(self, indicators: dict) -> None:
        """Update market regime from proxy symbol indicators."""
        adx = indicators.get("ADX_14")
        bbands = indicators.get("BBANDS_20")
        atr = indicators.get("ATR_14")
        if any(v is None for v in [adx, bbands, atr]):
            return
        bb_width = bbands["width"]
        self._spy_bb_width_history.append(bb_width)
        bb_width_avg = sum(self._spy_bb_width_history) / len(self._spy_bb_width_history)
        history = self._bar_history.get(self._regime_proxy_symbol)
        if not history:
            return
        close = history[-1].close
        atr_ratio = atr / close if close > 0 else 0.0

        raw_regime = self._regime_detector.classify(
            adx=adx,
            bb_width=bb_width,
            bb_width_avg=bb_width_avg,
            atr_ratio=atr_ratio,
        )

        timestamp = history[-1].timestamp
        transition = self._regime_tracker.update(raw_regime, timestamp)
        if transition is not None:
            logger.info(
                "Regime confirmed: %s -> %s (after %d bars)",
                transition.previous.value,
                transition.current.value,
                transition.bars_in_new_regime,
            )
            self._current_regime = transition.current

            # Review positions for regime compatibility
            if self._position_strategy_map:
                reviews = self._regime_reviewer.review(
                    transition.current, self._position_strategy_map,
                )
                close_reviews = [r for r in reviews if r.action == "close"]
                if close_reviews:
                    logger.info(
                        "Regime review: closing %d incompatible positions",
                        len(close_reviews),
                    )
                    for review in close_reviews:
                        close_sig = Signal(
                            strategy=review.strategy,
                            symbol=review.symbol,
                            direction="close",
                            strength=1.0,
                            metadata={"exit_reason": f"regime_{review.reason}"},
                        )
                        asyncio.ensure_future(self._process_regime_close(close_sig))

            # Check event-driven rotation
            vix_value = None
            if self._vix_fetcher is not None:
                try:
                    sentiment = self._vix_fetcher.get_sentiment()
                    vix_value = sentiment.vix_value
                except Exception:
                    logger.warning("VIX fetch failed during regime transition check")

            should_trigger, reason = self._event_rotation.should_trigger_rotation(
                transition=transition, vix_value=vix_value,
            )
            if should_trigger:
                logger.info("Event-driven rotation triggered: %s", reason)
                self._event_rotation.mark_triggered()
                if self._rotation_manager is not None:
                    asyncio.ensure_future(self._execute_event_rotation(reason))

    async def _process_regime_close(self, signal: Signal) -> None:
        """Process a regime-triggered close signal."""
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            await self._process_legacy_signal(signal, account, positions)
        except Exception:
            logger.exception("Regime close failed for %s", signal.symbol)

    # -----------------------------------------------------------------------
    # Historical warmup
    # -----------------------------------------------------------------------

    async def _warm_up_from_history(self) -> None:
        """Load historical daily bars for regime and indicator warmup."""
        if not hasattr(self._broker, "get_historical_bars"):
            logger.info("Broker does not support historical bars; skipping warmup")
            return

        proxy = self._regime_proxy_symbol
        symbols = list(set(self._settings.symbols + [proxy]))
        logger.info("Loading historical daily bars for %d symbols...", len(symbols))

        try:
            hist = await self._broker.get_historical_bars(
                symbols, days=self._settings.scheduler.universe_history_days,
            )
        except Exception:
            logger.exception("Failed to load historical bars")
            return

        for sym, bars in hist.items():
            for bar in bars:
                self._daily_bar_history[sym].append(bar)
                self._bar_history[sym].append(bar)

        loaded_count = {s: len(b) for s, b in hist.items() if b}
        logger.info("Loaded daily bars: %s", loaded_count)
        self._initialize_regime_from_daily()

    def _initialize_regime_from_daily(self) -> None:
        """Walk SPY daily bars to build bb_width_history and classify regime."""
        proxy = self._regime_proxy_symbol
        spy_history = self._daily_bar_history.get(proxy)
        if not spy_history or len(spy_history) < 30:
            logger.warning(
                "Insufficient %s daily bars for regime init (%d bars)",
                proxy, len(spy_history) if spy_history else 0,
            )
            return

        self._spy_bb_width_history.clear()
        temp: deque[Bar] = deque(maxlen=self._settings.data.bar_history_size)
        for bar in spy_history:
            temp.append(bar)
            indicators = self._indicator_engine.compute(temp)
            bbands = indicators.get("BBANDS_20")
            if bbands is not None:
                self._spy_bb_width_history.append(bbands["width"])

        indicators = self._indicator_engine.compute(spy_history)
        adx = indicators.get("ADX_14")
        bbands = indicators.get("BBANDS_20")
        atr = indicators.get("ATR_14")
        if any(v is None for v in [adx, bbands, atr]):
            logger.warning("Indicators still None after warmup")
            return

        bb_width_avg = sum(self._spy_bb_width_history) / len(self._spy_bb_width_history)
        close = list(spy_history)[-1].close
        atr_ratio = atr / close if close > 0 else 0.0

        regime = self._regime_detector.classify(
            adx=adx, bb_width=bbands["width"],
            bb_width_avg=bb_width_avg, atr_ratio=atr_ratio,
        )
        self._current_regime = regime
        self._regime_tracker._confirmed_regime = regime
        logger.info(
            "Regime initialised: %s (ADX=%.1f, BB_ratio=%.2f, ATR_ratio=%.3f, %d bars)",
            regime.value, adx, bbands["width"] / bb_width_avg, atr_ratio, len(spy_history),
        )

    # -----------------------------------------------------------------------
    # Utility helpers
    # -----------------------------------------------------------------------

    def _register_strategies(self) -> None:
        """Register all 4 strategies and their indicators."""
        strategies = [
            RsiMeanReversion(),
            ConsecutiveDown(),
            EmaPullback(),
            VolumeDivergence(),
        ]
        registered_keys: set[str] = set(self._indicator_engine._indicators.keys())
        for strategy in strategies:
            self._strategy_engine.add_strategy(strategy)
            for spec in strategy.required_indicators:
                if spec.key not in registered_keys:
                    self._indicator_engine.register(spec)
                    registered_keys.add(spec.key)

    async def _fetch_current_prices(self) -> dict[str, float]:
        """Fetch latest prices for all pending Group B symbols.

        Falls back to the last known bar close if live price unavailable.

        Returns:
            Mapping of symbol -> current price.
        """
        prices: dict[str, float] = {}
        try:
            positions = await self._broker.get_positions()
            pos_by_symbol = {p.symbol: p for p in positions}
        except Exception:
            pos_by_symbol = {}

        if self._entry_manager is not None:
            for candidate in self._entry_manager._group_b:
                symbol = candidate.signal.symbol
                # Use position market value if in position
                if symbol in pos_by_symbol:
                    prices[symbol] = pos_by_symbol[symbol].market_value / pos_by_symbol[symbol].quantity
                    continue
                # Use last known bar close
                history = self._bar_history.get(symbol)
                if history:
                    prices[symbol] = history[-1].close

        return prices

    async def _log_equity_snapshot(self) -> None:
        """Write an equity snapshot to the trade logger."""
        if self._trade_logger is None:
            return
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            snap = EquitySnapshot(
                timestamp=datetime.now(timezone.utc).isoformat(),
                equity=account.equity,
                cash=account.cash,
                regime=self._current_regime.value,
                position_count=len(positions),
                open_positions=[p.symbol for p in positions],
            )
            self._trade_logger.log_equity(snap)
        except Exception:
            logger.exception("Equity snapshot write failed")

    async def _daily_regime_scheduler(self) -> None:
        """Refresh regime from latest SPY daily bar once per day after 9 PM ET."""
        while self._running:
            await asyncio.sleep(300)
            now = datetime.now(timezone.utc)
            today = now.date()
            if self._last_regime_update_date == today:
                continue
            if now.hour < 21:
                continue
            if not hasattr(self._broker, "get_historical_bars"):
                continue
            try:
                proxy = self._regime_proxy_symbol
                hist = await self._broker.get_historical_bars([proxy], days=30)
                spy_bars = hist.get(proxy, [])
                if not spy_bars:
                    continue
                existing_ts = {b.timestamp for b in self._daily_bar_history[proxy]}
                new_count = sum(
                    1 for b in spy_bars
                    if b.timestamp not in existing_ts
                    and not self._daily_bar_history[proxy].append(b)  # type: ignore[func-returns-value]
                )
                if new_count > 0:
                    self._initialize_regime_from_daily()
                    self._last_regime_update_date = today
                    logger.info("Daily regime refresh: added %d bars", new_count)
            except Exception:
                logger.exception("Daily regime refresh failed")

    async def _rotation_scheduler(self) -> None:
        """Background task for weekly rotation day check."""
        last_rotation_date = None
        interval = self._settings.scheduler.rotation_check_interval_seconds
        while self._running:
            await asyncio.sleep(interval)
            now = datetime.now(timezone.utc)
            rotation_day = 5
            if self._rotation_manager is not None:
                rotation_day = getattr(
                    self._rotation_manager._config, "rotation_day", 5,
                )
            if now.weekday() == rotation_day and last_rotation_date != now.date():
                try:
                    logger.info("Rotation scheduler: triggering weekly rotation")
                    await self._run_universe_selection()
                    last_rotation_date = now.date()
                except Exception:
                    logger.exception("Rotation scheduler failed")

    async def _run_universe_selection(self) -> None:
        """Run the full universe selection pipeline and apply rotation."""
        from autotrader.universe.provider import SP500Provider
        from autotrader.universe.selector import UniverseSelector
        from autotrader.universe.earnings import EarningsCalendar

        logger.info("Starting universe selection pipeline...")
        provider = SP500Provider()
        infos = await asyncio.to_thread(provider.fetch)
        logger.info("Fetched %d S&P 500 constituents", len(infos))

        earnings_cal = EarningsCalendar()
        all_symbols = [i.symbol for i in infos]
        max_candidates = self._settings.scheduler.universe_max_candidates
        try:
            await asyncio.to_thread(earnings_cal.fetch, all_symbols[:max_candidates])
        except Exception:
            logger.warning("Earnings calendar fetch partially failed")

        today = datetime.now(timezone.utc).date()
        blackout = earnings_cal.blackout_symbols(all_symbols, today)
        active_candidates = [s for s in all_symbols if s not in blackout][:max_candidates]

        if not hasattr(self._broker, "get_historical_bars"):
            logger.warning("Broker does not support historical bars; skipping rotation")
            return

        days = self._settings.scheduler.universe_history_days
        bars_by_symbol = await self._broker.get_historical_bars(active_candidates, days=days)
        if not bars_by_symbol:
            logger.warning("No historical bars received; skipping rotation")
            return

        account = await self._broker.get_account()
        positions = await self._broker.get_positions()
        current_pool = list(self._rotation_manager.active_symbols) if self._rotation_manager else []
        open_syms = [p.symbol for p in positions]

        selector = UniverseSelector(
            initial_balance=account.equity,
            target_size=self._settings.risk.max_open_positions * 3,
        )
        result = selector.select(
            infos, bars_by_symbol,
            current_pool=current_pool,
            open_positions=open_syms,
        )
        logger.info(
            "Universe selection complete: %d symbols (in: %s, out: %s)",
            len(result.symbols),
            result.rotation_in or "none",
            result.rotation_out or "none",
        )
        await self.apply_rotation(result)

    async def _execute_event_rotation(self, reason: str) -> None:
        """Execute an event-driven mid-week rotation."""
        try:
            logger.info("Executing event-driven rotation: %s", reason)
            await self._run_universe_selection()
        except Exception:
            logger.exception("Event-driven rotation execution failed")

    async def apply_rotation(self, universe_result: Any) -> None:
        """Apply a new universe rotation."""
        if self._rotation_manager is None:
            logger.warning("apply_rotation called but no rotation manager configured")
            return
        account = await self._broker.get_account()
        positions = await self._broker.get_positions()
        open_syms = [p.symbol for p in positions]
        self._rotation_manager.apply_rotation(
            universe_result,
            open_position_symbols=open_syms,
            new_equity=account.equity,
        )
        self._risk_manager.reset_peak_equity(account.equity)
        logger.info("Peak equity reset to %.2f on rotation", account.equity)

        new_symbols = list(
            set(self._rotation_manager.active_symbols)
            | set(self._rotation_manager.watchlist_symbols)
        )
        self._settings.symbols = new_symbols
        logger.info(
            "Rotation applied: %d active, %d watchlist",
            len(self._rotation_manager.active_symbols),
            len(self._rotation_manager.watchlist_symbols),
        )

    def _create_broker(self) -> BrokerAdapter:
        if self._settings.broker.type == "paper":
            return PaperBroker(self._settings.broker.paper_balance)
        elif self._settings.broker.type == "alpaca":
            from autotrader.broker.alpaca_adapter import AlpacaAdapter
            load_dotenv(Path("config/.env"))
            return AlpacaAdapter(
                api_key=os.environ["ALPACA_API_KEY"],
                secret_key=os.environ["ALPACA_SECRET_KEY"],
                paper=self._settings.alpaca.paper,
                feed=self._settings.alpaca.feed,
            )
        raise ValueError(f"Unknown broker type: {self._settings.broker.type}")


# ---------------------------------------------------------------------------
# PaperBroker shim for execution engine
# ---------------------------------------------------------------------------

class _PaperOrderManager(OrderManager):
    """OrderManager subclass that works with PaperBroker.

    PaperBroker does not inherit from AlpacaAdapter, so we override
    the constructor to accept a generic BrokerAdapter.

    Note: stop-loss order submission is a no-op for paper trading
    (the PaperBroker handles SL through signal-based exit, not broker orders).
    """

    def __init__(self, broker: BrokerAdapter) -> None:
        # Bypass OrderManager.__init__ which expects AlpacaAdapter
        self._broker_adapter = broker
        self._active_orders: dict = {}

    async def submit_entry(self, symbol, side, qty, order_type="market", limit_price=None, time_in_force="day"):
        """Delegate to PaperBroker submit_order."""
        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
        )
        try:
            result = await self._broker_adapter.submit_order(order)
            return result
        except Exception:
            logger.exception("PaperBroker entry submission failed for %s", symbol)
            return None

    async def submit_stop_loss(self, symbol, side, qty, stop_price, parent_order_id=None):
        """No-op for paper trading; SL is handled via signal-based exit."""
        logger.debug("PaperBroker: SL order skipped for %s @ %.2f (paper mode)", symbol, stop_price)
        return None

    async def submit_exit(self, symbol, side, qty, order_type="market", limit_price=None):
        """Delegate to PaperBroker submit_order."""
        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force="day",
        )
        try:
            result = await self._broker_adapter.submit_order(order)
            return result
        except Exception:
            logger.exception("PaperBroker exit submission failed for %s", symbol)
            return None

    async def cancel_order(self, order_id):
        return await self._broker_adapter.cancel_order(order_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for AutoTrader v3."""
    config_path = Path("config/default.yaml")
    if config_path.exists():
        settings = load_settings(config_path)
    else:
        settings = Settings()

    setup_logging("autotrader", level=settings.system.log_level, log_dir=settings.system.log_dir)

    # Optionally load strategy_params.yaml and merge into settings
    strategy_params_path = Path("config/strategy_params.yaml")
    if strategy_params_path.exists():
        import yaml
        with open(strategy_params_path, encoding="utf-8") as f:
            _strategy_params = yaml.safe_load(f)
        logger.info("Strategy params loaded from %s", strategy_params_path)

    app = AutoTrader(settings, rotation_config=settings.rotation)

    async def run() -> None:
        await app.start()
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await app.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
