"""AutoTrader v3 - Batch+Intraday Hybrid Architecture.

Architecture overview:
  - 8:00 PM ET:   NightlyScanner.scan()  -> BatchResult (candidates)
  - 9:00 AM ET:   REST API daily bar refresh (pre-market)
  - 9:20 AM ET:   Daily reset (clear daily counters, re-entry blocks)
  - 9:25 AM ET:   GapFilter.filter()     -> filtered Candidate list
  - 9:30 AM ET:   EntryManager.execute_moo()           (Group A)
  - 9:45 AM ET:   EntryManager.execute_confirmation()  (Group B starts)
  - 10:00 AM ET:  EntryManager.close_entry_window()    (discard unconfirmed)
  - Continuous:   Minute bars streamed for held positions only (0~9)

Daily bar source: REST API pre-fetch (not minute->daily aggregation).
Minute bar streaming: held positions only, dynamically subscribed on
entry and unsubscribed on exit.

Architecture note:
  Batch pipeline logic (gap filter, MOO, confirmation, nightly scan) is
  delegated to BatchPipelineOrchestrator in autotrader/orchestration/.
  Historical data loading and regime init is delegated to HistoryManager.
  AutoTrader remains the thin coordinator wiring these components together.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from autotrader.core.config import RotationConfig, Settings, load_settings
from autotrader.core.logger import setup_logging
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal, Timeframe,
)
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.batch.gap_filter import GapFilter
from autotrader.batch.types import Candidate as BatchCandidate, FilteredCandidate
from autotrader.execution.entry_manager import Candidate as EntryCandidate, EntryManager
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.execution.order_ledger import OrderLedger, PENDING_STATES
from autotrader.execution.position_monitor import PositionMonitor
from autotrader.indicators.engine import IndicatorEngine
from autotrader.indicators.base import IndicatorSpec
from autotrader.orchestration.batch_pipeline import (
    BatchPipelineOrchestrator,
    batch_to_entry_candidate as _batch_to_entry_candidate,
)
from autotrader.orchestration.history_manager import HistoryManager
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.position_tracker import OpenPositionTracker
from autotrader.trading.position_book import PositionBook
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.portfolio.regime_position_reviewer import RegimePositionReviewer
from autotrader.portfolio.regime_tracker import RegimeTracker
from autotrader.portfolio.trade_logger import EquitySnapshot, LiveTradeRecord, TradeLogger
from autotrader.risk.gdr_manager import GDRManager
from autotrader.risk.manager import RiskManager
from autotrader.rotation.event_driven import EventDrivenRotation
from autotrader.rotation.manager import RotationManager
from autotrader.scheduling import StartupCatchUpResolver
from autotrader.scheduling.state import SchedulerState
from autotrader.state.runtime_state import RuntimeState, bootstrap_from_broker
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.breakout_momentum import BreakoutMomentum
# TODO: re-enable after backtest validation
# from autotrader.strategy.ema_pullback import EmaPullback
# from autotrader.strategy.volume_divergence import VolumeDivergence

logger = logging.getLogger("autotrader.main")

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Batch module Protocol interfaces (dependency injection)
# ---------------------------------------------------------------------------

@runtime_checkable
class BatchResultProtocol(Protocol):
    """Protocol for the result of a nightly scan.

    The concrete implementation lives in autotrader/batch/ (another agent).
    This protocol is satisfied by any object that exposes ``candidates``.
    Candidates are ``autotrader.batch.types.Candidate`` objects.
    """

    @property
    def candidates(self) -> list[Any]:
        """List of batch Candidate objects from the scan."""
        ...


@runtime_checkable
class NightlyScannerProtocol(Protocol):
    """Protocol for the nightly batch scanner."""

    async def scan(self) -> Any:
        """Run the nightly scan.  Returns an object satisfying BatchResultProtocol."""
        ...


@runtime_checkable
class GapFilterProtocol(Protocol):
    """Protocol for the pre-market gap filter (9:25 AM ET)."""

    async def filter(self, candidates: list[Any]) -> list[Any]:
        """Filter candidates based on overnight gap size.

        Removes candidates where the overnight gap exceeds the configured
        max_gap_pct threshold.

        Args:
            candidates: Raw batch.types.Candidate objects from NightlyScanner.

        Returns:
            List of FilteredCandidate objects.
        """
        ...


@runtime_checkable
class SignalRankerProtocol(Protocol):
    """Protocol for ranking candidates by signal quality."""

    def rank(self, candidates: list[Any]) -> list[Any]:
        """Return candidates sorted from highest to lowest quality.

        Args:
            candidates: Gap-filtered candidates.

        Returns:
            Sorted list (highest quality first).
        """
        ...


class _NightlyScannerAdapter:
    """Wraps NightlyScanner to satisfy NightlyScannerProtocol.

    Bridges between the NightlyScanner.run(symbols, days, regime) interface
    and the NightlyScannerProtocol.scan() expected by AutoTrader.
    """

    def __init__(self, scanner: Any, get_symbols: Any, get_regime: Any) -> None:
        self._scanner = scanner
        self._get_symbols = get_symbols
        self._get_regime = get_regime

    async def scan(self) -> Any:
        symbols = self._get_symbols()
        regime = self._get_regime()
        return await self._scanner.run(symbols, regime=regime)


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

_DAILY_BAR_REFRESH_HOUR: int = 9   # 9:00 AM ET (pre-market daily bar fetch)
_DAILY_BAR_REFRESH_MINUTE: int = 0

_DAILY_RESET_HOUR: int = 9     # 9:20 AM ET (before gap_filter at 9:25)
_DAILY_RESET_MINUTE: int = 20

# Upper bound for market-sensitive events (gap filter, MOO, confirmation).
# These events depend on live market data (pre-market prices, order execution)
# and must NOT fire outside market hours.  16:00 ET = market close.
_MARKET_SESSION_END_HOUR: int = 16


class AutoTrader:
    """Batch+intraday hybrid AutoTrader.

    Integrates nightly batch scanning with real-time intraday execution.
    Supports legacy v2 strategy-engine flow as a fallback when batch
    components are not injected.

    Delegates batch pipeline logic to BatchPipelineOrchestrator and
    historical data management to HistoryManager.

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

        # --- Broker ---
        self._broker = self._create_broker()

        # --- Core engines ---
        self._indicator_engine = IndicatorEngine()
        self._strategy_engine = StrategyEngine()
        self._risk_manager = RiskManager(settings.risk)

        # --- Regime detection ---
        self._regime_detector = RegimeDetector()
        self._allocation_engine = AllocationEngine(self._regime_detector)
        self._current_regime: MarketRegime = MarketRegime.UNCERTAIN
        self._spy_bb_width_history: deque[float] = deque(maxlen=20)
        self._regime_proxy_symbol: str = settings.scheduler.regime_proxy_symbol
        self._regime_tracker = RegimeTracker(confirmation_bars=1)
        self._regime_reviewer = RegimePositionReviewer()

        # --- GDR Manager (initialised with placeholder; reset in start()) ---
        self._gdr_manager: GDRManager | None = None

        # --- Bar history ---
        self._bar_history: dict[str, deque[Bar]] = defaultdict(
            lambda: deque(maxlen=settings.data.bar_history_size)
        )
        self._daily_bar_history: dict[str, deque[Bar]] = defaultdict(
            lambda: deque(maxlen=settings.data.bar_history_size)
        )

        # --- Position tracking (single source of truth) ---
        self._position_book = PositionBook()
        self._open_position_tracker = OpenPositionTracker(position_book=self._position_book)

        # Backward-compat properties: _held_positions and _position_strategy_map
        # are now thin views over PositionBook. Direct dict assignment sites
        # have been migrated to PositionBook.add/remove calls.

        # --- Execution layer (new v3) ---
        self._order_manager: OrderManager | None = None
        self._exit_rule_engine = ExitRuleEngine()
        self._entry_manager: EntryManager | None = None
        self._position_monitor: PositionMonitor | None = None

        # --- Batch pipeline components (injected) ---
        self._nightly_scanner: NightlyScannerProtocol | None = nightly_scanner
        self._gap_filter: GapFilterProtocol | None = gap_filter
        self._signal_ranker: SignalRankerProtocol | None = signal_ranker

        # --- BatchPipelineOrchestrator (delegates batch event handling) ---
        # The pipeline reads all dependencies from self (the host) at call
        # time, so test monkey-patching works transparently.
        self._batch_pipeline = BatchPipelineOrchestrator(host=self)

        # --- HistoryManager (delegates bar loading and regime init) ---
        self._history_manager = HistoryManager(
            broker=self._broker,
            daily_bar_history=self._daily_bar_history,
            bar_history=self._bar_history,
            settings=settings,
            indicator_engine=self._indicator_engine,
            regime_detector=self._regime_detector,
            regime_tracker=self._regime_tracker,
            set_regime=self._set_regime,
        )

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
        self._scheduler_running = False  # Guard against duplicate scheduler instances
        self._stream_task: asyncio.Task | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._batch_scheduler_task: asyncio.Task | None = None
        self._daily_regime_task: asyncio.Task | None = None
        self._reconciliation_task: asyncio.Task | None = None
        self._pending_fill_task: asyncio.Task | None = None
        self._last_regime_update_date: date | None = None

        self._bar_count: int = 0
        self._last_prices: dict[str, float] = {}  # symbol -> last bar close
        self._last_dump_time: float = 0.0  # monotonic time of last _dump_open_positions

    def _set_regime(self, regime: MarketRegime) -> None:
        """Callback for HistoryManager to set the current regime."""
        self._current_regime = regime

    # -----------------------------------------------------------------------
    # Backward-compat views over PositionBook
    # -----------------------------------------------------------------------

    @property
    def _held_positions(self) -> dict[str, HeldPosition]:
        """Read-only view: symbol -> HeldPosition from PositionBook.

        Existing code that reads ``self._held_positions`` (len, keys, get,
        ``in``) works unchanged.  Mutation sites (``[sym] = held``,
        ``pop``, ``del``) have been migrated to PositionBook.add/remove.
        """
        return {sym: p for sym, p in zip(
            self._position_book.symbols,
            self._position_book.all_positions(),
        )}

    @property
    def _position_strategy_map(self) -> dict[str, str]:
        """Read-only view: symbol -> strategy name from PositionBook.

        Existing code that reads ``self._position_strategy_map`` (get,
        values, ``in``) works unchanged.  Mutation sites have been
        migrated to PositionBook.add/remove.
        """
        return self._position_book.strategy_map()

    # -----------------------------------------------------------------------
    # Startup / Shutdown
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise all components and begin trading."""
        logger.info("Starting %s (v3 batch+intraday)", self._settings.system.name)

        await self._broker.connect()

        # Cancel all pending orders from previous session to prevent
        # stale orders (e.g., queued market orders) from filling unexpectedly
        try:
            cancelled = await self._broker.cancel_all_orders()
            logger.info("Startup: cancelled %d pending orders", cancelled)
        except Exception as e:
            logger.warning("Startup: failed to cancel pending orders: %s", e)

        account = await self._broker.get_account()
        logger.info("Account equity: %.2f", account.equity)

        # GDR Manager: per-strategy drawdown response for live trading
        self._gdr_manager = GDRManager(
            strategy_names=["breakout_momentum", "rsi_mean_reversion"],
            initial_capital=account.equity,
        )

        self._register_strategies()
        self._running = True

        # Load historical daily bars for regime and indicator warmup
        await self._warm_up_from_history()

        # Write initial equity snapshot so the dashboard has data immediately
        # (only during market hours to avoid after-hours price distortions)
        if self._trade_logger is not None and self._is_us_market_hours():
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
        elif self._trade_logger is not None:
            logger.info("Skipping initial equity snapshot (outside market hours)")

        # Initialise v3 execution engine
        self._initialise_execution_engine()

        # Load any existing open positions into v3 PositionMonitor
        await self._load_existing_positions()

        # Restore component state from persisted RuntimeState
        snapshots = self._runtime_state.load()
        if snapshots:
            state_components = self._get_state_components()
            # Exclude position_book from generic restore (which calls
            # from_snapshot and would wipe broker-loaded positions).
            # Instead, merge tracking fields after generic restore.
            pb_component = state_components.pop("position_book", None)
            self._runtime_state.restore(state_components, snapshots)
            # Merge position_book tracking fields into broker-loaded positions
            pb_snapshot = snapshots.get("position_book")
            if pb_component is not None and pb_snapshot:
                pb_component.merge_snapshot(pb_snapshot)
                logger.info(
                    "Merged PositionBook snapshot for %d symbols",
                    len(pb_snapshot),
                )
        else:
            # First run or state file missing -- bootstrap from broker
            logger.info("No RuntimeState found, bootstrapping from broker...")
            bootstrapped = await bootstrap_from_broker(
                broker=self._broker,
                ledger=getattr(self, '_order_ledger', None),
            )
            if bootstrapped:
                logger.info("Bootstrapped %d positions from broker", len(bootstrapped))
                for sym, held in bootstrapped.items():
                    self._position_book.add(held)

        # Reconcile any pending orders from ledger (ghost fill detection)
        await self._reconcile_pending_orders()

        # Start daily regime refresh scheduler
        self._daily_regime_task = asyncio.create_task(self._daily_regime_scheduler())

        # Use all symbols loaded during warmup as the trading universe
        warmup_symbols = [s for s in self._daily_bar_history.keys() if self._daily_bar_history[s]]
        if warmup_symbols:
            self._settings.symbols = warmup_symbols
            logger.info("Trading universe set to %d symbols from warmup data", len(warmup_symbols))
        else:
            logger.warning("No warmup data available; using config symbols (%d)", len(self._settings.symbols))

        # Subscribe to minute bars for held positions only (not full universe)
        held_symbols = self._position_book.symbols
        if held_symbols:
            logger.info("Subscribing to minute bars for %d held positions: %s", len(held_symbols), held_symbols)
        else:
            logger.info("No held positions; initializing stream with empty subscription")
        await self._broker.subscribe_bars(held_symbols, self._on_bar)
        if hasattr(self._broker, "run_stream"):
            self._stream_task = asyncio.create_task(self._run_stream_with_retry())

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
        self._scheduler_running = False

        # Stop PositionMonitor
        if self._position_monitor is not None:
            await self._position_monitor.stop()

        # Cancel all background tasks
        for task_attr in (
            "_reconciliation_task",
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

        # Save state on graceful shutdown
        if hasattr(self, "_runtime_state"):
            self._runtime_state.save(self._get_state_components())
            logger.info("RuntimeState saved on shutdown")

        await self._broker.disconnect()
        logger.info("AutoTrader v3 stopped")

    # -----------------------------------------------------------------------
    # Execution engine initialisation
    # -----------------------------------------------------------------------

    def _initialise_execution_engine(self) -> None:
        """Wire up the v3 execution components."""
        if not isinstance(self._broker, type(self._broker)) or not hasattr(self._broker, "submit_order"):
            logger.warning("Broker is not AlpacaAdapter; execution engine may not function correctly")

        # Initialise order ledger for persistent order tracking
        self._order_ledger = OrderLedger()
        self._order_ledger.load()

        # OrderManager wraps the broker (expects AlpacaAdapter)
        if hasattr(self._broker, "_api_key"):
            # It IS an AlpacaAdapter
            self._order_manager = OrderManager(self._broker, ledger=self._order_ledger)  # type: ignore[arg-type]
        else:
            # Fallback: wrap the PaperBroker via a thin adapter shim
            self._order_manager = _PaperOrderManager(self._broker)  # type: ignore[assignment]

        self._entry_manager = EntryManager(
            order_manager=self._order_manager,
            allocation_engine=self._allocation_engine,
            risk_manager=self._risk_manager,
            exit_rule_engine=self._exit_rule_engine,
            gdr_manager=self._gdr_manager,
        )

        self._position_monitor = PositionMonitor(
            order_manager=self._order_manager,
            exit_rule_engine=self._exit_rule_engine,
            indicator_engine=self._indicator_engine,
            position_book=self._position_book,
        )
        self._position_monitor.register_exit_callback(self._on_position_exit)

        # RuntimeState persistence
        self._runtime_state = RuntimeState()

        logger.info("V3 execution engine initialised")

    def _get_state_components(self) -> dict[str, Any]:
        """Collect all snapshottable components for RuntimeState persistence."""
        components: dict[str, Any] = {}
        if hasattr(self, "_gdr_manager") and self._gdr_manager is not None:
            components["gdr_manager"] = self._gdr_manager
        if hasattr(self, "_risk_manager") and self._risk_manager is not None:
            components["risk_manager"] = self._risk_manager
        if hasattr(self, "_entry_manager") and self._entry_manager is not None:
            components["entry_manager"] = self._entry_manager
        if hasattr(self, "_exit_rule_engine") and self._exit_rule_engine is not None:
            components["exit_rules"] = self._exit_rule_engine
        if hasattr(self, "_position_book") and self._position_book is not None:
            components["position_book"] = self._position_book
        return components

    async def _reconcile_positions(self, *, source: str = "startup") -> None:
        """Compare broker positions with internal tracking and reconcile gaps.

        Detects two types of discrepancies:
        1. Broker-only positions: exist at the broker but not tracked internally.
           These are registered into HeldPosition, PositionMonitor, and
           OpenPositionTracker so they receive exit management.
        2. Tracker-only positions: tracked internally but absent from the broker.
           These are logged as WARNINGs but NOT automatically removed, since
           they may represent a transient API delay.

        A LiveTradeRecord with side="reconciliation_entry" is logged for each
        newly discovered broker-only position.

        Args:
            source: Label for log messages ("startup" or "post_moo").
        """
        positions = await self._broker.get_positions()
        broker_symbols = {pos.symbol for pos in positions} if positions else set()

        tracked_symbols = set(self._open_position_tracker.open_symbols)

        # --- Broker-only positions: register into internal tracking ---
        untracked = broker_symbols - tracked_symbols
        if untracked:
            logger.warning(
                "RECONCILIATION[%s]: %d broker position(s) NOT in internal tracking: %s. "
                "Loading into monitor with strategy='unknown'.",
                source, len(untracked), sorted(untracked),
            )

        # --- Tracker-only positions: warn but do not auto-remove ---
        orphaned = tracked_symbols - broker_symbols
        if orphaned:
            logger.warning(
                "RECONCILIATION[%s]: %d internal position(s) NOT at broker: %s. "
                "These may indicate a missed fill or API delay. "
                "NOT auto-removing -- manual review recommended.",
                source, len(orphaned), sorted(orphaned),
            )

        # --- Cross-system consistency check ---
        # With PositionBook as SSOT, tracker/held/monitor/strategy_map are
        # all views of the same underlying store.  We only need to verify
        # that the PositionBook and the broker agree.
        book_syms = set(self._position_book.symbols)
        if book_syms != broker_symbols:
            only_book = book_syms - broker_symbols
            only_broker = broker_symbols - book_syms
            if only_book:
                logger.warning(
                    "RECONCILIATION[%s]: in PositionBook but NOT at broker: %s",
                    source, sorted(only_book),
                )
            if only_broker:
                logger.warning(
                    "RECONCILIATION[%s]: at broker but NOT in PositionBook: %s",
                    source, sorted(only_broker),
                )

        if not untracked:
            return

        today_et = datetime.now(timezone.utc).astimezone(_ET).date()
        account = await self._broker.get_account()

        for pos in positions:
            if pos.symbol not in untracked:
                continue

            logger.warning(
                "RECONCILIATION[%s]: loading untracked position %s "
                "(qty=%.0f, side=%s, entry=%.2f) with strategy='unknown'",
                source, pos.symbol, pos.quantity, pos.side, pos.avg_entry_price,
            )

            # Use ATR from indicator history if available
            history = self._bar_history.get(pos.symbol)
            atr = 1.0
            if history and len(history) >= 14:
                indicators = self._indicator_engine.compute(history)
                atr_raw = indicators.get("ATR_14")
                if isinstance(atr_raw, (int, float)) and atr_raw > 0:
                    atr = float(atr_raw)

            # Use today as entry date for newly discovered positions
            # (we don't know the actual broker fill date at this point)
            # Initialize price extremes using current market price to capture MFE/MAE
            current_price = (pos.market_value / pos.quantity) if pos.quantity > 0 else pos.avg_entry_price
            held = HeldPosition(
                symbol=pos.symbol,
                strategy="unknown",
                direction="long" if pos.side == "long" else "short",
                entry_price=pos.avg_entry_price,
                entry_atr=atr,
                entry_date_et=today_et,
                qty=pos.quantity,
                highest_price=max(pos.avg_entry_price, current_price),
                lowest_price=min(pos.avg_entry_price, current_price),
            )
            # Register into PositionBook (SSOT). PositionMonitor and
            # OpenPositionTracker both delegate to the same book.
            self._position_book.add(held)
            if self._position_monitor is not None:
                self._position_monitor.add_position(held)

            # Log reconciliation entry trade record
            if self._trade_logger is not None:
                try:
                    record = LiveTradeRecord(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        symbol=pos.symbol,
                        strategy="unknown",
                        direction="long" if pos.side == "long" else "short",
                        side="reconciliation_entry",
                        quantity=pos.quantity,
                        price=pos.avg_entry_price,
                        pnl=0.0,
                        regime=self._current_regime.value,
                        equity_after=account.equity,
                        metadata={"reconciliation_source": source},
                    )
                    self._trade_logger.log_trade(record)
                except Exception:
                    logger.exception(
                        "Trade log write failed for reconciliation entry %s",
                        pos.symbol,
                    )

            # Subscribe to minute bars for the newly discovered position
            if source != "startup":
                try:
                    await self._broker.add_bar_subscription(
                        [pos.symbol], self._on_bar,
                    )
                    logger.info(
                        "RECONCILIATION[%s]: subscribed to minute bars for %s",
                        source, pos.symbol,
                    )
                except Exception:
                    logger.exception(
                        "RECONCILIATION[%s]: failed to subscribe bars for %s",
                        source, pos.symbol,
                    )

        self._dump_open_positions()

    def _restore_strategy_map_from_trades(self) -> None:
        """Restore strategy assignments from live_trades.jsonl on startup.

        Reads entry/exit records to determine which positions are currently
        open and what their strategy + metadata was.  The results are stored
        in ``_trades_meta_cache`` and used by ``_load_existing_positions``
        to set the correct strategy when creating HeldPositions in
        PositionBook.
        """
        import json as _json

        trades_path = Path("data/live_trades.jsonl")
        if not trades_path.exists():
            logger.debug("No live_trades.jsonl found for strategy map restoration")
            return

        symbol_meta: dict[str, dict] = {}
        try:
            with open(trades_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = _json.loads(line)
                    except (ValueError, _json.JSONDecodeError):
                        continue

                    side = record.get("side", "")
                    symbol = record.get("symbol", "")
                    if not symbol:
                        continue

                    if side in ("entry", "reconciliation_entry"):
                        symbol_meta[symbol] = {
                            "strategy": record.get("strategy", "unknown"),
                            "direction": record.get("direction", "long"),
                            "entry_price": record.get("price"),
                            "metadata": record.get("metadata") or {},
                            "timestamp": record.get("timestamp"),
                        }
                    elif side == "exit":
                        symbol_meta.pop(symbol, None)
        except OSError:
            logger.warning("Failed to read live_trades.jsonl for strategy restoration")
            return

        if symbol_meta:
            # Strategy assignments are stored in _trades_meta_cache and
            # applied when HeldPositions are created in _load_existing_positions.
            logger.info(
                "Restored strategy map for %d symbols from trades: %s",
                len(symbol_meta),
                {s: m["strategy"] for s, m in symbol_meta.items()},
            )
        self._trades_meta_cache = symbol_meta

    async def _load_existing_positions(self) -> None:
        """Re-register any open positions from a previous session into PositionMonitor.

        Three-phase approach:
          Phase 0 - Restore strategy map from live_trades.jsonl.
          Phase 0b - Load MFE/MAE state from open_positions.json snapshot.
          Phase 1 - Fetch positions from broker (with 1 retry).
          Phase 2 - Per-position registration (individual failures don't block others).
          Phase 3 - Post-registration setup (dump state + start monitor).
        """
        # Phase 0: Restore strategy map from trades file
        self._restore_strategy_map_from_trades()

        # Phase 0b: Load last MFE/MAE snapshot for highest/lowest price restore
        import json as _json

        saved_positions: dict[str, dict] = {}
        try:
            snap_path = Path("data/open_positions.json")
            if snap_path.exists():
                snap_data = _json.loads(snap_path.read_text(encoding="utf-8"))
                for rec in snap_data:
                    saved_positions[rec["symbol"]] = rec
                logger.info(
                    "Loaded MFE/MAE snapshot for %d positions from %s",
                    len(saved_positions), snap_path,
                )
        except Exception:
            logger.warning("Could not load open_positions.json snapshot, MFE/MAE will reset")

        # Phase 1: Fetch from broker with retry
        positions = None
        for attempt in range(2):
            try:
                positions = await self._broker.get_positions()
                break
            except Exception:
                if attempt == 0:
                    logger.warning(
                        "Broker position fetch failed, retrying in 5s..."
                    )
                    await asyncio.sleep(5)
                else:
                    logger.exception(
                        "Broker position fetch failed after retry"
                    )
                    return

        if not positions:
            logger.info("No existing positions at broker")
            self._dump_open_positions()  # Clear stale file
            return

        logger.info("Loading %d existing open positions into monitor", len(positions))

        # Phase 2: Per-position registration
        # For startup, pre-register ALL broker positions (not just untracked)
        # because no positions are tracked yet at startup.
        today_et = datetime.now(timezone.utc).astimezone(_ET).date()
        loaded_count = 0
        trades_cache = getattr(self, "_trades_meta_cache", {})
        recon_account = None  # Lazy-fetch once for reconciliation entries
        for pos in positions:
            try:
                # Look up strategy from trades cache (restored in Phase 0)
                cached_entry = trades_cache.get(pos.symbol, {})
                strategy = cached_entry.get("strategy", "unknown") or "unknown"

                # Restore ATR from trades metadata cache (Phase 0),
                # fall back to indicator history, then default 1.0
                cached = trades_cache.get(pos.symbol, {})
                cached_meta = cached.get("metadata", {})
                atr = 1.0
                if cached_meta.get("entry_atr"):
                    atr = float(cached_meta["entry_atr"])
                else:
                    history = self._bar_history.get(pos.symbol)
                    if history and len(history) >= 14:
                        indicators = self._indicator_engine.compute(history)
                        atr_raw = indicators.get("ATR_14")
                        if isinstance(atr_raw, (int, float)) and atr_raw > 0:
                            atr = float(atr_raw)

                # Restore saved snapshot for this position
                saved = saved_positions.get(pos.symbol, {})

                # Restore entry_date from trades file or snapshot
                entry_date = today_et - timedelta(days=1)  # safe default
                trade_ts_str = cached.get("timestamp")
                if trade_ts_str:
                    try:
                        trade_ts = datetime.fromisoformat(trade_ts_str)
                        if trade_ts.tzinfo is None:
                            trade_ts = trade_ts.replace(tzinfo=timezone.utc)
                        entry_date = trade_ts.astimezone(_ET).date()
                    except (ValueError, TypeError):
                        pass  # keep safe default
                elif saved.get("entry_date_et"):
                    try:
                        entry_date = date.fromisoformat(saved["entry_date_et"])
                    except (ValueError, TypeError):
                        pass  # keep safe default

                # Restore highest/lowest from saved snapshot if available
                restored_highest = saved.get("highest_price", pos.avg_entry_price)
                restored_lowest = saved.get("lowest_price", pos.avg_entry_price)
                # Sanity: highest must be >= entry, lowest must be <= entry
                if restored_highest < pos.avg_entry_price:
                    restored_highest = pos.avg_entry_price
                if restored_lowest > pos.avg_entry_price:
                    restored_lowest = pos.avg_entry_price

                # Restore bar_count from snapshot (sanity: must be < 30 for daily bars)
                restored_bar_count = saved.get("bar_count", 0)
                if not isinstance(restored_bar_count, int) or restored_bar_count > 30:
                    restored_bar_count = 0

                held = HeldPosition(
                    symbol=pos.symbol,
                    strategy=strategy,
                    direction="long" if pos.side == "long" else "short",
                    entry_price=pos.avg_entry_price,
                    entry_atr=atr,
                    entry_date_et=entry_date,
                    qty=pos.quantity,
                    highest_price=restored_highest,
                    lowest_price=restored_lowest,
                )
                held.bars_held = restored_bar_count
                if saved:
                    logger.info(
                        "Restored position state for %s: highest=%.2f, lowest=%.2f, "
                        "bar_count=%d, entry_date=%s",
                        pos.symbol, restored_highest, restored_lowest,
                        restored_bar_count, entry_date,
                    )
                # Register into PositionBook (SSOT). PositionMonitor and
                # OpenPositionTracker both delegate to the same book.
                self._position_book.add(held)
                if self._position_monitor is not None:
                    self._position_monitor.add_position(held)
                    # Seed PositionMonitor's per-symbol bar history from
                    # warmup data so exit evaluation has indicator context
                    # instead of falling back to default ATR on first bar.
                    warmup_bars = self._bar_history.get(pos.symbol)
                    if warmup_bars:
                        pm_history = self._position_monitor._bar_history.get(pos.symbol)
                        if pm_history is not None:
                            pm_history.extend(warmup_bars)
                            logger.debug(
                                "Seeded PositionMonitor bar history for %s with %d warmup bars",
                                pos.symbol, len(warmup_bars),
                            )
                loaded_count += 1

                # Auto-write reconciliation_entry for positions missing from trade log
                if pos.symbol not in trades_cache and self._trade_logger is not None:
                    try:
                        if recon_account is None:
                            recon_account = await self._broker.get_account()
                        record = LiveTradeRecord(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            symbol=pos.symbol,
                            strategy=strategy,
                            direction="long" if pos.side == "long" else "short",
                            side="reconciliation_entry",
                            quantity=pos.quantity,
                            price=pos.avg_entry_price,
                            pnl=0.0,
                            regime=self._current_regime.value,
                            equity_after=recon_account.equity,
                            metadata={
                                "entry_atr": atr,
                                "reconciliation_source": "startup_auto",
                            },
                        )
                        self._trade_logger.log_trade(record)
                        logger.info(
                            "Auto-reconciliation: wrote entry for %s "
                            "(qty=%.0f, price=%.2f, strategy=%s)",
                            pos.symbol, pos.quantity, pos.avg_entry_price, strategy,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to write reconciliation entry for %s",
                            pos.symbol,
                        )
            except Exception:
                logger.exception("Failed to load position %s, skipping", pos.symbol)

        # Note: bar subscription is handled by start() after this method returns.
        # Do NOT call add_bar_subscription here -- _stream is not yet initialized.

        logger.info(
            "Successfully loaded %d / %d positions", loaded_count, len(positions)
        )

        # Phase 3: Post-registration setup
        try:
            self._dump_open_positions()
        except Exception:
            logger.exception("Failed to dump open positions file")

        try:
            if self._position_monitor is not None:
                await self._position_monitor.start()
        except Exception:
            logger.exception("Failed to start position monitor")

    async def _reconcile_pending_orders(self) -> None:
        """Reconcile pending orders from the ledger against broker state.

        On startup, any orders in SUBMITTED/PENDING_FILL state in the ledger
        may have filled or been cancelled at the broker while we were offline.
        Query each pending order and update the ledger accordingly.
        """
        if not hasattr(self, "_order_ledger") or self._order_ledger is None:
            return

        pending_entries = self._order_ledger.get_pending_entries()
        pending_sls = self._order_ledger.get_pending_stop_losses()

        if not pending_entries and not pending_sls:
            logger.info("Order ledger reconciliation: no pending orders")
            return

        logger.info(
            "Order ledger reconciliation: %d pending entries, %d pending SLs",
            len(pending_entries), len(pending_sls),
        )

        _FILL_OK = {"filled", "partially_filled"}
        _TERMINAL = {"cancelled", "canceled", "expired", "rejected"}

        # Reconcile pending entry orders
        for record in pending_entries:
            try:
                broker_status = await self._broker.get_order_status(record.order_id)
                if broker_status is None:
                    logger.warning(
                        "Ledger reconcile: order %s (%s) not found at broker -- marking cancelled",
                        record.order_id, record.symbol,
                    )
                    from autotrader.execution.order_ledger import OrderState
                    self._order_ledger.record_terminal(record.order_id, OrderState.CANCELLED)
                    continue

                if broker_status.status in _FILL_OK:
                    logger.warning(
                        "RECONCILED GHOST FILL: order %s (%s) filled at broker "
                        "(qty=%.0f, price=%.2f) -- was pending in ledger",
                        record.order_id, record.symbol,
                        broker_status.filled_qty, broker_status.filled_price,
                    )
                    partial = broker_status.status == "partially_filled"
                    self._order_ledger.record_fill(
                        record.order_id, broker_status.filled_qty,
                        broker_status.filled_price, partial=partial,
                    )
                    # Check if this position is already tracked
                    existing = self._open_position_tracker.get_position(record.symbol)
                    if existing is None:
                        logger.warning(
                            "Ghost fill %s (%s) has no tracked position -- "
                            "position will be picked up by broker reconciliation",
                            record.order_id, record.symbol,
                        )
                elif broker_status.status in _TERMINAL:
                    from autotrader.execution.order_ledger import OrderState
                    _state_map = {
                        "cancelled": OrderState.CANCELLED, "canceled": OrderState.CANCELLED,
                        "expired": OrderState.EXPIRED, "rejected": OrderState.REJECTED,
                    }
                    self._order_ledger.record_terminal(
                        record.order_id,
                        _state_map.get(broker_status.status, OrderState.CANCELLED),
                    )
                    logger.info(
                        "Ledger reconcile: order %s (%s) terminal at broker: %s",
                        record.order_id, record.symbol, broker_status.status,
                    )
                else:
                    logger.info(
                        "Ledger reconcile: order %s (%s) still pending at broker: %s",
                        record.order_id, record.symbol, broker_status.status,
                    )
            except Exception:
                logger.exception(
                    "Failed to reconcile pending order %s (%s)",
                    record.order_id, record.symbol,
                )

        # Reconcile pending stop-loss orders
        for symbol, record in pending_sls.items():
            try:
                broker_status = await self._broker.get_order_status(record.order_id)
                if broker_status is None:
                    logger.warning(
                        "Ledger reconcile: SL order %s (%s) not found at broker -- marking cancelled",
                        record.order_id, symbol,
                    )
                    from autotrader.execution.order_ledger import OrderState
                    self._order_ledger.record_terminal(record.order_id, OrderState.CANCELLED)
                elif broker_status.status in _FILL_OK:
                    logger.warning(
                        "Ledger reconcile: SL order %s (%s) FILLED at broker -- "
                        "stop loss was triggered while offline",
                        record.order_id, symbol,
                    )
                    self._order_ledger.record_fill(
                        record.order_id, broker_status.filled_qty,
                        broker_status.filled_price,
                    )
                elif broker_status.status in _TERMINAL:
                    from autotrader.execution.order_ledger import OrderState
                    _state_map = {
                        "cancelled": OrderState.CANCELLED, "canceled": OrderState.CANCELLED,
                        "expired": OrderState.EXPIRED, "rejected": OrderState.REJECTED,
                    }
                    self._order_ledger.record_terminal(
                        record.order_id,
                        _state_map.get(broker_status.status, OrderState.CANCELLED),
                    )
            except Exception:
                logger.exception(
                    "Failed to reconcile pending SL order %s (%s)",
                    record.order_id, symbol,
                )

        # Compact old ledger entries (keep 72h)
        try:
            removed = self._order_ledger.compact(keep_hours=72)
            if removed > 0:
                logger.info("Ledger compacted: removed %d old entries", removed)
        except Exception:
            logger.exception("Failed to compact order ledger")

    # -----------------------------------------------------------------------
    # Batch+intraday scheduler
    # -----------------------------------------------------------------------

    async def _run_startup_catchup(
        self,
        fired: dict[str, date | None],
        state: SchedulerState,
    ) -> None:
        """Execute catch-up for events missed due to late system start.

        Uses StartupCatchUpResolver to determine which events should be
        replayed, then executes them in dependency order.  Events already
        recorded in *state* are excluded from catch-up.

        For target_next_day events (nightly_scan), dedup is based on the
        target_date rather than simple fired/not-fired.  Morning catch-up
        targets today; evening catch-up targets tomorrow.
        """
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        today_et = now_et.date()
        today_str = today_et.isoformat()

        # Determine if today is a market day (simple weekday check)
        is_market_day = now_et.weekday() < 5  # Mon-Fri

        # For nightly_scan, use target_date-based dedup instead of simple
        # already_fired filtering.  Remove it from already_fired so the
        # resolver can include it, then check target_date manually below.
        already = state.fired_event_names()
        _nightly_target = self._compute_nightly_target(now_et)
        if state.is_fired_for_date("nightly_scan", _nightly_target):
            # Already fired for this target -- leave it in already_fired
            pass
        else:
            # Not fired for this target -- let the resolver consider it
            already.discard("nightly_scan")

        resolver = StartupCatchUpResolver()
        catchup_events = resolver.resolve(
            now_et,
            today_is_market_day=is_market_day,
            already_fired=already,
        )

        if not catchup_events:
            logger.info("Startup catch-up: no missed events to replay")
            return

        logger.info(
            "Startup catch-up: replaying %d event(s): %s",
            len(catchup_events),
            ", ".join(catchup_events),
        )

        async def _refresh_and_push() -> None:
            await self._refresh_daily_bars()
            await self._push_daily_bars_to_monitor()

        event_handlers: dict[str, Any] = {
            "daily_bar_refresh": _refresh_and_push,
            "daily_reset": lambda: self._on_daily_reset(today_et),
            "gap_filter": self._on_gap_filter,
            "moo": self._on_moo,
            "confirmation": self._on_confirmation_window,
            "entry_close": self._on_entry_window_close,
            "nightly_scan": self._on_nightly_scan,
        }

        # Market-sensitive events must only fire within market hours.
        # Same guard as the main polling loop (_MARKET_SESSION_END_HOUR).
        _MARKET_SENSITIVE_EVENTS = {"gap_filter", "moo", "confirmation", "entry_close"}
        h_now = now_et.hour

        for event_name in catchup_events:
            handler = event_handlers.get(event_name)
            if handler is None:
                logger.warning("No handler for catch-up event: %s", event_name)
                continue

            # Guard: skip market-sensitive events outside market hours
            if event_name in _MARKET_SENSITIVE_EVENTS and h_now >= _MARKET_SESSION_END_HOUR:
                logger.info(
                    "Catch-up: skipping %s (outside market hours, h=%d)",
                    event_name, h_now,
                )
                fired[event_name] = today_et
                state.mark_fired(event_name, result="skipped")
                state.save(self._state_path)
                continue

            try:
                logger.info("Catch-up: executing %s", event_name)
                result = handler()
                if asyncio.iscoroutine(result):
                    await result
                fired[event_name] = today_et
                # For nightly_scan, record target_date for dedup
                if event_name == "nightly_scan":
                    state.mark_fired(
                        event_name, result="success",
                        target_date=_nightly_target,
                    )
                else:
                    state.mark_fired(event_name, result="success")
                state.save(self._state_path)
            except Exception:
                logger.exception("Catch-up failed for event: %s", event_name)
                if event_name == "nightly_scan":
                    state.mark_fired(
                        event_name, result="failed",
                        target_date=_nightly_target,
                    )
                else:
                    state.mark_fired(event_name, result="failed")
                state.save(self._state_path)

    @staticmethod
    def _compute_nightly_target(now_et: datetime) -> str:
        """Compute the target_date for a nightly_scan execution.

        When run at 20:00+ (evening), the scan produces candidates for
        the NEXT day's MOO, so target_date = tomorrow.
        When caught up in the morning (before market open), the scan
        serves TODAY's MOO, so target_date = today.

        Args:
            now_et: Current time in US Eastern.

        Returns:
            ISO date string for the target trading day.
        """
        if now_et.hour >= _NIGHTLY_SCAN_HOUR:
            return (now_et.date() + timedelta(days=1)).isoformat()
        return now_et.date().isoformat()

    def _load_last_batch_result(self) -> None:
        """Load the most recent batch result from disk if still fresh.

        Delegates to BatchPipelineOrchestrator.load_last_batch_result().
        Kept as a method on AutoTrader for backward compatibility with
        tests that call ``app._load_last_batch_result()``.
        """
        self._batch_pipeline.load_last_batch_result()

    @property
    def _last_batch_result(self) -> Any | None:
        """Proxy property for backward compat with tests accessing _last_batch_result."""
        return self._batch_pipeline.last_batch_result

    @_last_batch_result.setter
    def _last_batch_result(self, value: Any) -> None:
        self._batch_pipeline.last_batch_result = value

    async def _batch_intraday_scheduler(self) -> None:
        """Background task that drives the batch+intraday daily workflow.

        Phase 1 (startup): Catch up any events missed due to late start.
        Phase 2 (loop): Poll every 30s and fire events at their scheduled time.
        """
        # Guard against duplicate scheduler instances (Bug 2 fix)
        if self._scheduler_running:
            logger.warning("_batch_intraday_scheduler already running; aborting duplicate")
            return
        self._scheduler_running = True

        try:
            await self.__batch_intraday_scheduler_impl()
        finally:
            self._scheduler_running = False

    async def __batch_intraday_scheduler_impl(self) -> None:
        """Internal implementation of the batch+intraday scheduler loop."""
        # --- Persistent state: know exactly what ran today ---
        self._state_path = Path("data/scheduler_state.json")
        _state = SchedulerState.load(self._state_path)
        _now_et = datetime.now(timezone.utc).astimezone(_ET)
        _today_str = _now_et.date().isoformat()

        if _state.date != _today_str:
            # Preserve nightly_scan if it targets today (run last evening)
            _old_nightly = _state.events.get("nightly_scan")
            _state = SchedulerState.fresh(_today_str)
            if _old_nightly and _old_nightly.target_date == _today_str:
                _state.events["nightly_scan"] = _old_nightly
                logger.info(
                    "Startup: preserved nightly_scan from previous day "
                    "(target_date=%s)", _old_nightly.target_date,
                )

        # Build legacy _fired dict from persistent state
        _fired: dict[str, date | None] = {
            "daily_bar_refresh": None,
            "daily_reset": None,
            "gap_filter": None,
            "moo": None,
            "confirmation": None,
            "entry_close": None,
            "nightly_scan": None,
        }
        _fired.update(_state.to_fired_dict())

        # --- Phase 0: Restore last batch result from disk (survives restart) ---
        if self._last_batch_result is None:
            self._load_last_batch_result()

        # --- Phase 1: Startup catch-up (persistent state filters already-fired) ---
        await self._run_startup_catchup(_fired, _state)

        # Mark past events not caught up as "skipped" so the polling
        # loop does not re-fire them with stale/wrong data.
        # nightly_scan is excluded: it uses target_date-based dedup and
        # must not be marked skipped generically (the 20:00 run targets
        # tomorrow, so a morning skip must not block the evening run).
        _event_schedule = {
            "daily_bar_refresh": (_DAILY_BAR_REFRESH_HOUR, _DAILY_BAR_REFRESH_MINUTE),
            "daily_reset": (_DAILY_RESET_HOUR, _DAILY_RESET_MINUTE),
            "gap_filter": (_GAP_FILTER_HOUR, _GAP_FILTER_MINUTE),
            "moo": (_MOO_HOUR, _MOO_MINUTE),
            "confirmation": (_CONFIRMATION_HOUR, _CONFIRMATION_MINUTE),
            "entry_close": (_ENTRY_WINDOW_CLOSE_HOUR, _ENTRY_WINDOW_CLOSE_MINUTE),
        }
        _today_et = _now_et.date()
        _h, _m = _now_et.hour, _now_et.minute
        for _evt, (_eh, _em) in _event_schedule.items():
            if not _state.is_fired(_evt) and (_h > _eh or (_h == _eh and _m >= _em)):
                _state.mark_fired(_evt, result="skipped")
                _fired[_evt] = _today_et
                logger.info("Marked past event as skipped: %s (h=%d)", _evt, _h)
        _state.save(self._state_path)

        # --- Phase 2: Normal polling loop ---
        _loop_count = 0
        while self._running:
            await asyncio.sleep(30)
            _loop_count += 1
            now_et = datetime.now(timezone.utc).astimezone(_ET)
            today_et = now_et.date()
            h, m = now_et.hour, now_et.minute

            # Day rollover: reset persistent state for the new day.
            # Preserve nightly_scan if it targets today (run last evening).
            if _state.date != today_et.isoformat():
                _old_nightly = _state.events.get("nightly_scan")
                _state = SchedulerState.fresh(today_et.isoformat())
                if (
                    _old_nightly
                    and _old_nightly.target_date == today_et.isoformat()
                ):
                    _state.events["nightly_scan"] = _old_nightly
                    logger.info(
                        "Day rollover: preserved nightly_scan (target_date=%s)",
                        _old_nightly.target_date,
                    )
                for k in _fired:
                    _fired[k] = None
                # If nightly_scan was preserved, mark it in _fired too
                if _state.is_fired("nightly_scan"):
                    _fired["nightly_scan"] = today_et

            # Heartbeat every ~5 minutes (10 iterations x 30s)
            if _loop_count % 10 == 0:
                fired_summary = {k: (str(v) if v else "None") for k, v in _fired.items()}
                logger.debug(
                    "Scheduler heartbeat: h=%d m=%d, positions=%d, state_date=%s, fired=%s",
                    h, m, self._position_book.count, _state.date, fired_summary,
                )

            # 9:00 AM: Pre-market daily bar refresh via REST API
            if h >= _DAILY_BAR_REFRESH_HOUR and (h > _DAILY_BAR_REFRESH_HOUR or m >= _DAILY_BAR_REFRESH_MINUTE) and _fired["daily_bar_refresh"] != today_et:
                _fired["daily_bar_refresh"] = today_et
                await self._refresh_daily_bars()
                # Push latest daily bars to PositionMonitor for exit evaluation
                await self._push_daily_bars_to_monitor()
                _state.mark_fired("daily_bar_refresh")
                _state.save(self._state_path)

            # 9:20 AM: Daily reset (must run before gap_filter and MOO)
            if h >= _DAILY_RESET_HOUR and (h > _DAILY_RESET_HOUR or m >= _DAILY_RESET_MINUTE) and _fired["daily_reset"] != today_et:
                _fired["daily_reset"] = today_et
                await self._on_daily_reset(today_et)
                _state.mark_fired("daily_reset")
                _state.save(self._state_path)

            # 9:25 AM: Gap filter (requires live pre-market prices; skip outside market session)
            if h >= _GAP_FILTER_HOUR and (h > _GAP_FILTER_HOUR or m >= _GAP_FILTER_MINUTE) and _fired["gap_filter"] != today_et:
                if h < _MARKET_SESSION_END_HOUR:
                    logger.info(
                        "[GAP_FILTER] FIRING at h=%d m=%d (market hours OK, "
                        "_fired=%s, state_fired=%s)",
                        h, m, _fired["gap_filter"], _state.is_fired("gap_filter"),
                    )
                    _fired["gap_filter"] = today_et
                    await self._on_gap_filter()
                    _state.mark_fired("gap_filter")
                else:
                    logger.warning(
                        "[GAP_FILTER] SKIPPED: outside market hours h=%d >= %d "
                        "(would have fired with stale prices!)",
                        h, _MARKET_SESSION_END_HOUR,
                    )
                    _fired["gap_filter"] = today_et
                    _state.mark_fired("gap_filter", result="skipped")
                    self._batch_pipeline.mark_candidates_skipped("outside_market_hours")
                _state.save(self._state_path)
            elif _loop_count % 10 == 0 and not _state.is_fired("gap_filter"):
                logger.debug(
                    "[GAP_FILTER] not yet: h=%d m=%d, need h>=%d m>=%d",
                    h, m, _GAP_FILTER_HOUR, _GAP_FILTER_MINUTE,
                )

            # 9:30 AM: Group A MOO entries (requires market to be open; skip outside market session)
            if h >= _MOO_HOUR and (h > _MOO_HOUR or m >= _MOO_MINUTE) and _fired["moo"] != today_et:
                if h < _MARKET_SESSION_END_HOUR:
                    _fired["moo"] = today_et
                    await self._on_moo()
                    _state.mark_fired("moo")
                else:
                    logger.info("MOO entries skipped: outside market hours (h=%d)", h)
                    _fired["moo"] = today_et
                    _state.mark_fired("moo", result="skipped")
                _state.save(self._state_path)

            # 9:45 AM: Group B confirmation window
            if (
                h >= _CONFIRMATION_HOUR
                and (h > _CONFIRMATION_HOUR or m >= _CONFIRMATION_MINUTE)
                and (h < _ENTRY_WINDOW_CLOSE_HOUR or (h == _ENTRY_WINDOW_CLOSE_HOUR and m < _ENTRY_WINDOW_CLOSE_MINUTE))
                and _fired["confirmation"] != today_et
            ):
                _fired["confirmation"] = today_et
                await self._on_confirmation_window()
                _state.mark_fired("confirmation")
                _state.save(self._state_path)

            # 10:00 AM: Close entry window (only meaningful during market session)
            if h >= _ENTRY_WINDOW_CLOSE_HOUR and (h > _ENTRY_WINDOW_CLOSE_HOUR or m >= _ENTRY_WINDOW_CLOSE_MINUTE) and _fired["entry_close"] != today_et:
                if h < _MARKET_SESSION_END_HOUR:
                    _fired["entry_close"] = today_et
                    await self._on_entry_window_close()
                    _state.mark_fired("entry_close")
                else:
                    _fired["entry_close"] = today_et
                    _state.mark_fired("entry_close", result="skipped")
                _state.save(self._state_path)

            # 8:00 PM: Nightly scan (target_date = tomorrow)
            if h >= _NIGHTLY_SCAN_HOUR and (h > _NIGHTLY_SCAN_HOUR or m >= _NIGHTLY_SCAN_MINUTE):
                _nightly_target = (today_et + timedelta(days=1)).isoformat()
                if not _state.is_fired_for_date("nightly_scan", _nightly_target):
                    _fired["nightly_scan"] = today_et
                    await self._on_nightly_scan()
                    _state.mark_fired(
                        "nightly_scan",
                        target_date=_nightly_target,
                    )
                    _state.save(self._state_path)

    # -----------------------------------------------------------------------
    # Scheduled event handlers (delegate to batch pipeline)
    # -----------------------------------------------------------------------

    async def _on_daily_reset(self, today_et: date) -> None:
        """Reset daily state at 9:20 AM ET, before gap_filter and market open."""
        logger.info("Daily reset: %s", today_et)
        self._risk_manager.reset_daily()
        self._exit_rule_engine.on_new_trading_day(today_et)
        if self._entry_manager is not None:
            self._entry_manager.on_new_trading_day(today_et)
        if self._gdr_manager is not None:
            self._gdr_manager.reset_daily_entries()

    async def _on_gap_filter(self) -> None:
        """Apply gap filter to last batch result at 9:25 AM ET."""
        logger.info("[SCHEDULER] _on_gap_filter() -> delegating to batch_pipeline")
        await self._batch_pipeline.on_gap_filter()
        logger.info("[SCHEDULER] _on_gap_filter() complete")

    async def _on_moo(self) -> None:
        """Execute Group A limit orders at 9:30 AM ET."""
        logger.info("[SCHEDULER] _on_moo() -> delegating to batch_pipeline")
        await self._batch_pipeline.on_moo()
        logger.info("[SCHEDULER] _on_moo() complete")
        self._schedule_post_moo_reconciliation()
        self._schedule_pending_fill_polling()

    def _schedule_post_moo_reconciliation(self) -> None:
        """Schedule a position reconciliation 5 minutes after MOO.

        Creates an asyncio task that waits 300 seconds, then runs
        _reconcile_positions() to detect any fills that arrived at the
        broker but were not captured by the internal tracking system
        (e.g., partial fills, race conditions with rapid order execution).

        The task reference is stored in self._reconciliation_task so it
        can be awaited or cancelled during shutdown.
        """
        async def _delayed_reconcile() -> None:
            try:
                await asyncio.sleep(300)
                logger.info("[RECONCILIATION] post-MOO reconciliation starting (T+5min)")
                await self._reconcile_positions(source="post_moo")
                logger.info("[RECONCILIATION] post-MOO reconciliation complete")
            except asyncio.CancelledError:
                logger.info("[RECONCILIATION] post-MOO reconciliation cancelled")
            except Exception:
                logger.exception(
                    "[RECONCILIATION] post-MOO reconciliation failed "
                    "(system continues normally)"
                )

        self._reconciliation_task = asyncio.create_task(_delayed_reconcile())
        logger.info("[SCHEDULER] post-MOO reconciliation scheduled in 300s")

    def _schedule_pending_fill_polling(self) -> None:
        """Poll pending limit orders for fills every 30s until all resolved.

        Limit orders submitted at MOO may take seconds to minutes to fill.
        This polls the broker every 30 seconds, registering filled positions
        into PositionBook/Monitor.  Orders exceeding LIMIT_ORDER_CANCEL_MINUTES
        are auto-cancelled by EntryManager.check_pending_fills().
        """
        async def _poll_loop() -> None:
            try:
                entry_mgr = self._entry_manager
                if entry_mgr is None:
                    return

                today_et = datetime.now(timezone.utc).astimezone(_ET).date()
                poll_count = 0

                while entry_mgr.pending_limit_orders:
                    await asyncio.sleep(30)
                    poll_count += 1
                    logger.debug("[FILL_POLL] polling pending limit orders (attempt %d)", poll_count)

                    try:
                        new_positions = await entry_mgr.check_pending_fills(today_et)
                    except Exception:
                        logger.exception("[FILL_POLL] check_pending_fills failed")
                        continue

                    # Register newly filled positions
                    for held in new_positions:
                        if self._position_book.has(held.symbol):
                            logger.warning(
                                "[FILL_POLL] %s already in PositionBook -- skipping",
                                held.symbol,
                            )
                            continue
                        try:
                            self._position_book.add(held)
                            if self._position_monitor is not None:
                                self._position_monitor.add_position(held)
                            # Log entry trade
                            await self._batch_pipeline._log_entry_trade(
                                held, await self._broker.get_account(),
                            )
                            await self._broker.add_bar_subscription(
                                [held.symbol], self._on_bar,
                            )
                            logger.info(
                                "[FILL_POLL] Registered filled position: %s %s %.0f @ %.2f",
                                held.direction, held.symbol, held.qty, held.entry_price,
                            )
                        except Exception:
                            logger.exception(
                                "[FILL_POLL] Failed to register %s after fill",
                                held.symbol,
                            )

                    if new_positions:
                        self._dump_open_positions()
                        await self._log_equity_snapshot()

                logger.info("[FILL_POLL] All pending limit orders resolved")
            except asyncio.CancelledError:
                logger.info("[FILL_POLL] Polling cancelled")
            except Exception:
                logger.exception("[FILL_POLL] Polling loop failed")

        # Only start if there are pending orders
        if self._entry_manager and self._entry_manager.pending_limit_orders:
            self._pending_fill_task = asyncio.create_task(_poll_loop())
            logger.info(
                "[SCHEDULER] Pending fill polling started for %d order(s)",
                len(self._entry_manager.pending_limit_orders),
            )

    async def _on_confirmation_window(self) -> None:
        """Execute Group B confirmation entries between 9:45 and 10:00 AM ET."""
        logger.info("[SCHEDULER] _on_confirmation_window() -> delegating to batch_pipeline")
        await self._batch_pipeline.on_confirmation_window()
        logger.info("[SCHEDULER] _on_confirmation_window() complete")

    async def _on_entry_window_close(self) -> None:
        """Discard unconfirmed Group B candidates at 10:00 AM ET."""
        logger.info("[SCHEDULER] _on_entry_window_close() -> delegating to batch_pipeline")
        await self._batch_pipeline.on_entry_window_close()
        logger.info("[SCHEDULER] _on_entry_window_close() complete")

    async def _on_nightly_scan(self) -> None:
        """Run the nightly batch scan at 8:00 PM ET."""
        logger.info("[SCHEDULER] _on_nightly_scan() -> delegating to batch_pipeline")
        await self._batch_pipeline.on_nightly_scan(
            refresh_daily_bars=self._refresh_daily_bars,
        )
        logger.info("[SCHEDULER] _on_nightly_scan() complete")

    # -----------------------------------------------------------------------
    # Position exit callback (from PositionMonitor)
    # -----------------------------------------------------------------------

    async def _on_position_exit(
        self, symbol: str, reason: str, fill_price: float, pnl: float,
    ) -> None:
        """Called by PositionMonitor after each exit is executed.

        Updates risk manager, portfolio tracker, trade logger, and
        unsubscribes the symbol from minute bar streaming.

        Args:
            symbol: Closed ticker.
            reason: Exit reason string from ExitRuleEngine.
            fill_price: Actual exit fill price.
            pnl: Realised profit/loss.
        """
        # PositionMonitor already removed the position from PositionBook
        # before calling this callback. Retrieve the cached position
        # reference from the monitor, falling back to a book remove
        # attempt (which returns None if already gone).
        held = (
            getattr(self._position_monitor, '_last_exited_position', None)
            if self._position_monitor is not None
            else None
        )
        if held is None or held.symbol != symbol:
            held = self._position_book.remove(symbol)

        # Unsubscribe from minute bars for this symbol
        try:
            await self._broker.remove_bar_subscription([symbol])
        except Exception:
            logger.warning(
                "Failed to unsubscribe %s from bar stream; continuing exit flow",
                symbol,
            )

        # MFE/MAE data from the removed HeldPosition (already popped
        # from PositionBook above, so close_position would return None)
        mfe = held.mfe if held else 0.0
        mae = held.mae if held else 0.0
        bars_held = held.bar_count if held else 0

        # Update risk manager
        self._risk_manager.record_pnl(pnl)

        # Update GDR manager (per-strategy drawdown tracking)
        if self._gdr_manager is not None and held is not None:
            self._gdr_manager.record_trade_pnl(held.strategy, pnl)

        # Write trade record
        if self._trade_logger is not None and held is not None:
            # Fetch equity separately so broker API failure cannot skip trade log
            equity_after = 0.0
            try:
                account = await self._broker.get_account()
                equity_after = account.equity
            except Exception:
                logger.warning(
                    "get_account() failed during %s exit; using equity_after=0.0 "
                    "as fallback -- trade log will still be written",
                    symbol,
                )
            try:
                record = LiveTradeRecord(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    symbol=symbol,
                    strategy=held.strategy,
                    direction=held.direction,
                    side="exit",
                    quantity=held.qty,
                    price=fill_price,
                    pnl=pnl,
                    regime=self._current_regime.value,
                    equity_after=equity_after,
                    metadata={"exit_reason": reason},
                    exit_reason=reason,
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                )
                self._trade_logger.log_trade(record)
            except Exception:
                logger.exception(
                    "Trade log write failed for %s exit -- CRITICAL TRADE DATA "
                    "for manual recovery: symbol=%s, strategy=%s, direction=%s, "
                    "qty=%.0f, fill_price=%.2f, pnl=%.2f, reason=%s, "
                    "regime=%s, mfe=%.3f, mae=%.3f, bars_held=%d",
                    symbol,
                    symbol,
                    held.strategy,
                    held.direction,
                    held.qty,
                    fill_price,
                    pnl,
                    reason,
                    self._current_regime.value,
                    mfe,
                    mae,
                    bars_held,
                )

        logger.info(
            "Exit recorded: %s, reason=%s, pnl=%.2f, mfe=%.3f, mae=%.3f, bars=%d",
            symbol, reason, pnl, mfe, mae, bars_held,
        )

        # Update open positions file for dashboard
        self._dump_open_positions()

        # Persist runtime state after every exit (GDR tiers, risk peak, etc.)
        if hasattr(self, "_runtime_state"):
            self._runtime_state.save(self._get_state_components())

    # -----------------------------------------------------------------------
    # WebSocket stream with auto-reconnect
    # -----------------------------------------------------------------------

    async def _run_stream_with_retry(self) -> None:
        """Run the WebSocket bar stream with automatic reconnection."""
        _RETRY_DELAYS = [5, 10, 30, 60]  # escalating backoff
        attempt = 0
        while self._running:
            try:
                logger.info("WebSocket stream starting (attempt %d)", attempt + 1)
                await asyncio.to_thread(self._broker.run_stream)
                # run_stream() returned normally (e.g., clean shutdown)
                if not self._running:
                    break
                logger.warning("WebSocket stream ended unexpectedly, reconnecting...")
            except Exception:
                logger.exception("WebSocket stream error (attempt %d)", attempt + 1)
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            logger.info("Reconnecting WebSocket in %ds...", delay)
            await asyncio.sleep(delay)
            # Re-create stream and re-subscribe held symbols
            try:
                held_syms = self._position_book.symbols
                await self._broker.subscribe_bars(held_syms, self._on_bar)
                logger.info("Re-subscribed to %d symbols after reconnect", len(held_syms))
            except Exception:
                logger.exception("Failed to re-subscribe after reconnect")

            # Refresh _last_prices from broker REST API to clear stale values
            try:
                positions = await self._broker.get_positions()
                if positions:
                    refreshed = 0
                    for pos in positions:
                        # Derive current price from market_value / quantity
                        if pos.quantity > 0 and abs(pos.market_value) > 0:
                            current = abs(pos.market_value) / pos.quantity
                            self._last_prices[pos.symbol] = current
                            refreshed += 1
                    logger.info(
                        "Refreshed _last_prices for %d/%d positions after reconnect",
                        refreshed, len(positions),
                    )
            except Exception:
                logger.warning(
                    "Failed to refresh _last_prices after reconnect, "
                    "stale values may persist until next bar"
                )

            attempt += 1

    # -----------------------------------------------------------------------
    # Minute bar handler (held positions only)
    # -----------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        """Handle incoming minute bars from held-position-only stream.

        Used for:
        - MFE/MAE tracking for held positions
        - Forwarding bars to PositionMonitor for exit evaluation
        - Periodic equity snapshot logging
        """
        # Log first bar per symbol for debugging (then every 60th bar ~= 1 hour)
        if self._bar_count <= 2 or self._bar_count % 60 == 0:
            logger.info(
                "Bar received: %s close=%.2f high=%.2f low=%.2f (bar #%d)",
                bar.symbol, bar.close, bar.high, bar.low, self._bar_count,
            )

        # Track last price for unrealized P&L calculation
        self._last_prices[bar.symbol] = bar.close

        # MFE/MAE tracking for open positions
        self._open_position_tracker.update_prices(
            bar.symbol, bar.high, bar.low, bar.close,
        )
        # Dump updated position data at most once every 30s to limit I/O
        _now = time.monotonic()
        if _now - self._last_dump_time >= 30.0:
            self._dump_open_positions()
            self._last_dump_time = _now

        # Forward bar to PositionMonitor for exit evaluation
        if self._position_monitor is not None:
            await self._position_monitor.on_bar(bar)

            # Guard: if PositionMonitor triggered an exit, the position is now
            # removed from PositionBook (SSOT).  Re-dump to clear the stale
            # snapshot written above, and skip further processing for this bar.
            if not self._position_book.has(bar.symbol):
                self._last_prices.pop(bar.symbol, None)
                self._dump_open_positions()
                self._bar_count += 1
                return

        # Periodic equity snapshot
        self._bar_count += 1
        if (
            self._trade_logger is not None
            and self._bar_count % self._settings.performance.equity_snapshot_interval == 0
        ):
            try:
                account = await self._broker.get_account()
                positions = await self._broker.get_positions()
                snap = EquitySnapshot(
                    timestamp=bar.timestamp.isoformat(),
                    equity=account.equity,
                    cash=account.cash,
                    regime=self._current_regime.value,
                    position_count=len(positions),
                    open_positions=[p.symbol for p in positions],
                )
                self._trade_logger.log_equity(snap)
            except Exception:
                logger.exception("Equity snapshot failed during bar processing")

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
                # open_position() delegates to PositionBook.add()
                self._open_position_tracker.open_position(
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    entry_price=result.filled_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=result.filled_qty,
                )
            elif signal.direction == "close":
                self._position_book.remove(signal.symbol)

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
                # Use entry_time if available (legacy path), else entry_date_et
                if tracked.entry_time is not None:
                    entry_date = tracked.entry_time.astimezone(_ET_TZ).date()
                else:
                    entry_date = tracked.entry_date_et
                now_date = datetime.now(timezone.utc).astimezone(_ET_TZ).date()
                if entry_date == now_date:
                    logger.warning(
                        "PDT guard: blocking same-day close for %s (entered %s)",
                        signal.symbol,
                        tracked.entry_time.isoformat() if tracked.entry_time else str(entry_date),
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
            if self._position_book.has(signal.symbol):
                return None
            existing_pos = next((p for p in positions if p.symbol == signal.symbol), None)
            if existing_pos is not None:
                return None

            strategy_count = len(self._position_book.by_strategy(signal.strategy))
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
        """Update market regime from proxy symbol SPY indicators."""
        adx = indicators.get("ADX_14")
        ema_50 = indicators.get("EMA_50")
        bbands = indicators.get("BBANDS_20")
        if any(v is None for v in [adx, ema_50, bbands]):
            return
        history = self._bar_history.get(self._regime_proxy_symbol)
        if not history:
            return
        close = history[-1].close
        bb_upper = bbands.get("upper", 0)
        bb_lower = bbands.get("lower", 0)
        bb_middle = bbands.get("middle", 1.0)
        if bb_middle <= 0:
            bb_middle = 1.0
        bb_ratio = (bb_upper - bb_lower) / bb_middle

        raw_regime = self._regime_detector.classify(
            adx=adx, close=close, ema_50=ema_50, bb_ratio=bb_ratio,
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
            strat_map = self._position_book.strategy_map()
            if strat_map:
                reviews = self._regime_reviewer.review(
                    transition.current, strat_map,
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
                        task = asyncio.create_task(self._process_regime_close(close_sig))
                        task.add_done_callback(self._handle_task_exception)

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
                    task = asyncio.create_task(self._execute_event_rotation(reason))
                    task.add_done_callback(self._handle_task_exception)

    def _handle_task_exception(self, task: asyncio.Task) -> None:
        """Log exceptions from fire-and-forget background tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Background task failed: %s", exc, exc_info=exc)

    async def _process_regime_close(self, signal: Signal) -> None:
        """Process a regime-triggered close signal."""
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            await self._process_legacy_signal(signal, account, positions)
        except Exception:
            logger.exception("Regime close failed for %s", signal.symbol)

    # -----------------------------------------------------------------------
    # Historical warmup (delegates to HistoryManager)
    # -----------------------------------------------------------------------

    async def _warm_up_from_history(self) -> None:
        """Load historical daily bars for regime and indicator warmup.

        Delegates to HistoryManager.warm_up_from_history().
        """
        await self._history_manager.warm_up_from_history()

    async def _refresh_daily_bars(self) -> None:
        """Fetch latest daily bars for the full S&P 500 universe via REST API.

        Delegates to HistoryManager.refresh_daily_bars().
        """
        await self._history_manager.refresh_daily_bars()

    async def _push_daily_bars_to_monitor(self) -> None:
        """Push latest daily bars to PositionMonitor for exit rule evaluation.

        Called after _refresh_daily_bars() completes.  For each monitored
        position, finds the most recent daily bar and forwards it to
        PositionMonitor.on_bar() so exit rules (trailing SL, time exit,
        take-profit, staged profit lock) are evaluated once per trading day.
        """
        if self._position_monitor is None:
            return

        monitored = self._position_monitor.monitored_symbols
        if not monitored:
            return

        pushed = 0
        for symbol in monitored:
            daily_bars = self._daily_bar_history.get(symbol)
            if not daily_bars:
                continue
            latest_bar = daily_bars[-1]
            # Only push if bar has DAILY timeframe (should be true from REST)
            if latest_bar.timeframe != Timeframe.DAILY:
                continue
            await self._position_monitor.on_bar(latest_bar)
            pushed += 1

            # Check if exit was triggered (position removed from PositionBook)
            if not self._position_book.has(symbol):
                self._last_prices.pop(symbol, None)
                self._dump_open_positions()

        if pushed > 0:
            logger.info(
                "Pushed %d daily bar(s) to PositionMonitor for exit evaluation",
                pushed,
            )

        # Periodic state save after daily bar processing
        if hasattr(self, "_runtime_state"):
            self._runtime_state.save(self._get_state_components())

    def _initialize_regime_from_daily(self) -> None:
        """Walk SPY daily bars to classify regime.

        Delegates to HistoryManager.initialize_regime_from_daily().
        """
        self._history_manager.initialize_regime_from_daily()

    # -----------------------------------------------------------------------
    # Utility helpers
    # -----------------------------------------------------------------------

    def _register_strategies(self) -> None:
        """Register active strategies and their indicators.

        Currently 2-strategy BM+MR portfolio matching Iter 29 config.
        ema_pullback / volume_divergence disabled until backtest validation.
        """
        strategies = [
            BreakoutMomentum(),
            RsiMeanReversion(),
        ]
        registered_keys: set[str] = set(self._indicator_engine._indicators.keys())
        for strategy in strategies:
            self._strategy_engine.add_strategy(strategy)
            for spec in strategy.required_indicators:
                if spec.key not in registered_keys:
                    self._indicator_engine.register(spec)
                    registered_keys.add(spec.key)

        # Ensure EMA_50 is registered for SPY regime classification
        ema50_spec = IndicatorSpec(name="EMA", params={"period": 50})
        if ema50_spec.key not in registered_keys:
            self._indicator_engine.register(ema50_spec)
            registered_keys.add(ema50_spec.key)

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
                    qty = pos_by_symbol[symbol].quantity
                    if qty != 0:
                        prices[symbol] = pos_by_symbol[symbol].market_value / qty
                    continue
                # Use last known bar close
                history = self._bar_history.get(symbol)
                if history:
                    prices[symbol] = history[-1].close

        return prices

    @staticmethod
    def _is_us_market_hours() -> bool:
        """Return True if current UTC time falls within US equity market hours.

        Market hours: Mon-Fri 09:30-16:00 ET (14:30-21:00 UTC in EST,
        13:30-20:00 UTC in EDT).  We use a conservative window of
        13:30-21:00 UTC to cover both DST variants.
        """
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:  # Sat/Sun
            return False
        minutes = now.hour * 60 + now.minute
        return 13 * 60 + 30 <= minutes <= 21 * 60

    async def _log_equity_snapshot(self) -> None:
        """Write an equity snapshot and dump open position details to disk."""
        if self._trade_logger is None:
            return
        if not self._is_us_market_hours():
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

        # Dump live position details (MFE/MAE, qty, etc.) for dashboard
        self._dump_open_positions()

    def _dump_open_positions(self) -> None:
        """Write current open position details to data/open_positions.json.

        The dashboard reads this file to show real-time MFE/MAE and
        position sizes for held positions.
        """
        import json as _json

        tracker = self._open_position_tracker
        records = []
        for symbol in tracker.open_symbols:
            held = tracker.get_position(symbol)
            if held is None:
                continue
            current_price = self._last_prices.get(symbol)
            if current_price is None:
                # Fallback: use last daily bar close (available at startup)
                daily_bars = self._daily_bar_history.get(symbol)
                if daily_bars:
                    current_price = daily_bars[-1].close
            if current_price is None:
                current_price = held.entry_price
            if held.direction == "long":
                pnl_per_share = current_price - held.entry_price
            else:
                pnl_per_share = held.entry_price - current_price
            unrealized_pnl = round(pnl_per_share * held.qty, 2)
            unrealized_pnl_pct = round(pnl_per_share / held.entry_price, 6) if held.entry_price > 0 else 0.0
            records.append({
                "symbol": held.symbol,
                "strategy": held.strategy,
                "direction": held.direction,
                "entry_price": held.entry_price,
                "current_price": round(current_price, 2),
                "qty": held.qty,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "highest_price": held.highest_price,
                "lowest_price": held.lowest_price,
                "mfe_pct": round(held.mfe, 6),
                "mae_pct": round(held.mae, 6),
                "mfe_dollar": round(held.mfe * held.entry_price * held.qty, 2),
                "mae_dollar": round(held.mae * held.entry_price * held.qty, 2),
                "bar_count": held.bar_count,
                "entry_atr": held.entry_atr,
                "entry_date_et": held.entry_date_et.isoformat(),
            })

        path = Path("data/open_positions.json")
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(_json.dumps(records, indent=2) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(path))
        except OSError:
            logger.debug("Failed to dump open positions to %s", path)

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
                new_count = 0
                for b in spy_bars:
                    if b.timestamp not in existing_ts:
                        self._daily_bar_history[proxy].append(b)
                        new_count += 1
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
            now = datetime.now(ZoneInfo("America/New_York"))
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

        today = datetime.now(ZoneInfo("America/New_York")).date()
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
        # Pre-check: reject tiny universes before mutating any state
        incoming_symbols = getattr(universe_result, "symbols", []) or []
        if len(incoming_symbols) < 10:
            logger.warning(
                "Rotation universe has only %d symbols (minimum 10); "
                "refusing to overwrite universe of %d symbols",
                len(incoming_symbols), len(self._settings.symbols),
            )
            return

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
        if len(new_symbols) < 10:
            logger.warning(
                "Rotation produced only %d symbols (minimum 10); "
                "refusing to overwrite universe of %d symbols -- "
                "state may be inconsistent, consider restarting",
                len(new_symbols), len(self._settings.symbols),
            )
            return
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

    async def submit_entry(self, symbol, side, qty, order_type="market", limit_price=None, time_in_force="day",
                           *, strategy="unknown", direction="long", entry_atr=0.0, metadata=None):
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

    async def submit_stop_loss(self, symbol, side, qty, stop_price, parent_order_id=None,
                               *, strategy="unknown", direction="long"):
        """No-op for paper trading; SL is handled via signal-based exit."""
        logger.debug("PaperBroker: SL order skipped for %s @ %.2f (paper mode)", symbol, stop_price)
        return None

    async def submit_exit(self, symbol, side, qty, order_type="market", limit_price=None,
                          *, strategy="unknown", direction="long"):
        """Delegate to PaperBroker submit_order and evict from active orders."""
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
            # Clean up active order tracking to prevent memory leak
            self._evict_symbol(symbol)
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

    # Build NightlyScanner after AutoTrader (which loads .env via _create_broker)
    from autotrader.batch.scanner import NightlyScanner as _NightlyScanner
    from autotrader.data.batch_fetcher import BatchFetcher

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    fetcher = BatchFetcher(api_key, secret_key)
    scanner = _NightlyScanner(fetcher)

    # Wire scanner adapter so it can access app's state
    nightly_adapter = _NightlyScannerAdapter(
        scanner=scanner,
        get_symbols=lambda: app._settings.symbols,
        get_regime=lambda: app._current_regime.value if app._current_regime else "UNCERTAIN",
    )
    app._nightly_scanner = nightly_adapter

    # Wire GapFilter (uses same BatchFetcher for pre-market quotes)
    gap_filter = GapFilter(fetcher, gap_threshold=0.03)
    app._gap_filter = gap_filter

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
