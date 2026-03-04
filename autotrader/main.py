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
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from autotrader.core.config import RotationConfig, Settings, load_settings
from autotrader.core.event_bus import EventBus
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
from autotrader.risk.gdr_manager import GDRManager
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.rotation.event_driven import EventDrivenRotation
from autotrader.rotation.manager import RotationManager
from autotrader.scheduling import StartupCatchUpResolver
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


def _batch_to_entry_candidate(batch_cand: BatchCandidate) -> EntryCandidate:
    """Convert a batch pipeline Candidate to an EntryManager Candidate.

    The batch pipeline produces ``autotrader.batch.types.Candidate`` objects
    (with a nested ``ScanResult``), while the execution layer expects
    ``autotrader.execution.entry_manager.Candidate`` objects (with a
    ``Signal``).  This helper bridges the two representations.
    """
    sr = batch_cand.scan_result
    atr = sr.indicators.get("ATR_14", 1.0)
    if not isinstance(atr, (int, float)) or atr <= 0:
        atr = 1.0
    atr = float(atr)

    # Merge strategy metadata with entry_atr so that EntryManager can
    # place broker-side stop-loss orders using the actual ATR value.
    merged_metadata = dict(sr.metadata)
    merged_metadata["entry_atr"] = atr

    signal = Signal(
        strategy=sr.strategy,
        symbol=sr.symbol,
        direction=sr.direction,
        strength=sr.signal_strength,
        metadata=merged_metadata,
    )
    return EntryCandidate(
        signal=signal,
        prev_close=sr.prev_close,
        atr=atr,
        indicators=sr.indicators,
    )


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
        self._scheduler_running = False  # Guard against duplicate scheduler instances
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

        # Use all symbols loaded during warmup as the trading universe
        warmup_symbols = [s for s in self._daily_bar_history.keys() if self._daily_bar_history[s]]
        if warmup_symbols:
            self._settings.symbols = warmup_symbols
            logger.info("Trading universe set to %d symbols from warmup data", len(warmup_symbols))
        else:
            logger.warning("No warmup data available; using config symbols (%d)", len(self._settings.symbols))

        # Subscribe to minute bars for held positions only (not full universe)
        held_symbols = list(self._held_positions.keys())
        if held_symbols:
            logger.info("Subscribing to minute bars for %d held positions: %s", len(held_symbols), held_symbols)
            await self._broker.subscribe_bars(held_symbols, self._on_bar)
            if hasattr(self._broker, "run_stream"):
                self._stream_task = asyncio.create_task(
                    asyncio.to_thread(self._broker.run_stream)
                )
        else:
            logger.info("No held positions; minute bar stream not started (will start on first entry)")
            # Initialize stream with empty subscription so it's ready for dynamic adds
            await self._broker.subscribe_bars([], self._on_bar)
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
        self._scheduler_running = False

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
            gdr_manager=self._gdr_manager,
        )

        self._position_monitor = PositionMonitor(
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

            # Subscribe to minute bars for held positions
            if held_symbols := list(self._held_positions.keys()):
                await self._broker.add_bar_subscription(held_symbols, self._on_bar)
                logger.info("Subscribed to minute bars for %d existing positions", len(held_symbols))

            # Start the position monitor
            if self._position_monitor is not None:
                await self._position_monitor.start()

        except Exception:
            logger.exception("Failed to load existing positions")

    # -----------------------------------------------------------------------
    # Batch+intraday scheduler
    # -----------------------------------------------------------------------

    async def _run_startup_catchup(self, fired: dict[str, date | None]) -> None:
        """Execute catch-up for events missed due to late system start.

        Uses StartupCatchUpResolver to determine which events should be
        replayed, then executes them in dependency order.
        """
        now_et = datetime.now(timezone.utc).astimezone(_ET)
        today_et = now_et.date()

        # Determine if today is a market day (simple weekday check)
        is_market_day = now_et.weekday() < 5  # Mon-Fri

        resolver = StartupCatchUpResolver()
        catchup_events = resolver.resolve(now_et, today_is_market_day=is_market_day)

        if not catchup_events:
            logger.info("Startup catch-up: no missed events to replay")
            return

        logger.info(
            "Startup catch-up: replaying %d event(s): %s",
            len(catchup_events),
            ", ".join(catchup_events),
        )

        event_handlers: dict[str, Any] = {
            "daily_bar_refresh": self._refresh_daily_bars,
            "daily_reset": lambda: self._on_daily_reset(today_et),
            "gap_filter": self._on_gap_filter,
            "moo": self._on_moo,
            "confirmation": self._on_confirmation_window,
            "entry_close": self._on_entry_window_close,
            "nightly_scan": self._on_nightly_scan,
        }

        for event_name in catchup_events:
            handler = event_handlers.get(event_name)
            if handler is None:
                logger.warning("No handler for catch-up event: %s", event_name)
                continue
            try:
                logger.info("Catch-up: executing %s", event_name)
                result = handler()
                if asyncio.iscoroutine(result):
                    await result
                fired[event_name] = today_et
            except Exception:
                logger.exception("Catch-up failed for event: %s", event_name)

    def _load_last_batch_result(self) -> None:
        """Load the most recent batch result from disk if still fresh.

        On process restart, the in-memory ``_last_batch_result`` is lost.
        This method reconstructs it from ``data/batch_results.json`` when the
        file exists and was produced within the last 18 hours (nightly scan at
        8 PM, gap filter at 9:25 AM = ~13 h gap; 18 h provides safe margin).
        """
        results_path = os.path.join("data", "batch_results.json")
        if not os.path.exists(results_path):
            logger.debug("No batch_results.json found; skipping load")
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read batch_results.json: %s", exc)
            return

        # Check freshness: run_at must be within 18 hours of now
        run_at_str = data.get("run_at")
        if not run_at_str:
            logger.warning("batch_results.json missing run_at; skipping load")
            return

        try:
            run_at = datetime.fromisoformat(run_at_str)
            # Ensure timezone-aware comparison
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - run_at).total_seconds() / 3600
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid run_at in batch_results.json: %s", exc)
            return

        if age_hours > 18:
            logger.info(
                "batch_results.json is %.1f hours old (>18h); not loading stale result",
                age_hours,
            )
            return

        # Reconstruct minimal BatchResult-like object with .candidates
        raw_candidates = data.get("candidates", [])

        class _RestoredBatchResult:
            """Minimal stand-in satisfying the BatchResultProtocol (.candidates)."""

            def __init__(self, candidates: list[BatchCandidate]) -> None:
                self.candidates = candidates

        from autotrader.batch.types import ScanResult as _ScanResult

        candidates: list[BatchCandidate] = []
        for c in raw_candidates:
            try:
                scan_result = _ScanResult(
                    symbol=c["symbol"],
                    strategy=c["strategy"],
                    direction=c["direction"],
                    signal_strength=c.get("signal_strength", 0.0),
                    indicators=c.get("indicators", {}),
                    prev_close=c.get("prev_close", 0.0),
                    scanned_at=datetime.fromisoformat(c["scanned_at"]) if c.get("scanned_at") else datetime.now(timezone.utc),
                    metadata=c.get("metadata", {}),
                )
                candidate = BatchCandidate(
                    scan_result=scan_result,
                    composite_score=c.get("composite_score", 0.0),
                    regime_compatibility=c.get("regime_compatibility", 0.0),
                    sector=c.get("sector", "Unknown"),
                    rank=c.get("rank", 0),
                )
                candidates.append(candidate)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Skipping malformed candidate in batch_results.json: %s", exc)
                continue

        self._last_batch_result = _RestoredBatchResult(candidates)
        logger.info(
            "Loaded %d candidates from batch_results.json (%.1f hours old)",
            len(candidates),
            age_hours,
        )

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
        _fired: dict[str, date | None] = {
            "daily_bar_refresh": None,
            "daily_reset": None,
            "gap_filter": None,
            "moo": None,
            "confirmation": None,
            "entry_close": None,
            "nightly_scan": None,
        }

        # --- Phase 0: Restore last batch result from disk (survives restart) ---
        if self._last_batch_result is None:
            self._load_last_batch_result()

        # --- Phase 1: Startup catch-up ---
        await self._run_startup_catchup(_fired)

        # --- Phase 2: Normal polling loop ---
        while self._running:
            await asyncio.sleep(30)
            now_et = datetime.now(timezone.utc).astimezone(_ET)
            today_et = now_et.date()
            h, m = now_et.hour, now_et.minute

            # 9:00 AM: Pre-market daily bar refresh via REST API
            if h >= _DAILY_BAR_REFRESH_HOUR and (h > _DAILY_BAR_REFRESH_HOUR or m >= _DAILY_BAR_REFRESH_MINUTE) and _fired["daily_bar_refresh"] != today_et:
                _fired["daily_bar_refresh"] = today_et
                await self._refresh_daily_bars()

            # 9:20 AM: Daily reset (must run before gap_filter and MOO)
            if h >= _DAILY_RESET_HOUR and (h > _DAILY_RESET_HOUR or m >= _DAILY_RESET_MINUTE) and _fired["daily_reset"] != today_et:
                _fired["daily_reset"] = today_et
                await self._on_daily_reset(today_et)

            # 9:25 AM: Gap filter
            if h >= _GAP_FILTER_HOUR and (h > _GAP_FILTER_HOUR or m >= _GAP_FILTER_MINUTE) and _fired["gap_filter"] != today_et:
                _fired["gap_filter"] = today_et
                await self._on_gap_filter()

            # 9:30 AM: Group A MOO entries
            if h >= _MOO_HOUR and (h > _MOO_HOUR or m >= _MOO_MINUTE) and _fired["moo"] != today_et:
                _fired["moo"] = today_et
                await self._on_moo()

            # 9:45 AM: Group B confirmation window
            if (
                h >= _CONFIRMATION_HOUR
                and (h > _CONFIRMATION_HOUR or m >= _CONFIRMATION_MINUTE)
                and (h < _ENTRY_WINDOW_CLOSE_HOUR or (h == _ENTRY_WINDOW_CLOSE_HOUR and m < _ENTRY_WINDOW_CLOSE_MINUTE))
                and _fired["confirmation"] != today_et
            ):
                _fired["confirmation"] = today_et
                await self._on_confirmation_window()

            # 10:00 AM: Close entry window
            if h >= _ENTRY_WINDOW_CLOSE_HOUR and (h > _ENTRY_WINDOW_CLOSE_HOUR or m >= _ENTRY_WINDOW_CLOSE_MINUTE) and _fired["entry_close"] != today_et:
                _fired["entry_close"] = today_et
                await self._on_entry_window_close()

            # 8:00 PM: Nightly scan
            if h >= _NIGHTLY_SCAN_HOUR and (h > _NIGHTLY_SCAN_HOUR or m >= _NIGHTLY_SCAN_MINUTE) and _fired["nightly_scan"] != today_et:
                _fired["nightly_scan"] = today_et
                await self._on_nightly_scan()

    # -----------------------------------------------------------------------
    # Scheduled event handlers
    # -----------------------------------------------------------------------

    async def _on_daily_reset(self, today_et: date) -> None:
        """Reset daily state at 9:20 AM ET, before gap_filter and market open."""
        logger.info("Daily reset: %s", today_et)
        self._risk_manager.reset_daily_pnl()
        self._exit_rule_engine.on_new_trading_day(today_et)
        if self._entry_manager is not None:
            self._entry_manager.on_new_trading_day(today_et)
        if self._gdr_manager is not None:
            self._gdr_manager.reset_daily_entries()

    async def _on_gap_filter(self) -> None:
        """Apply gap filter to last batch result at 9:25 AM ET.

        Converts batch pipeline Candidates to EntryManager Candidates and
        loads them into the EntryManager for MOO execution at 9:30 AM.

        When no GapFilter is injected, all raw candidates pass through.
        When a GapFilter is present, only candidates with acceptable
        pre-market gaps are kept.  In both cases the surviving batch
        Candidates are converted to EntryManager Candidates and loaded.
        """
        if self._last_batch_result is None:
            logger.info("Gap filter: no nightly batch result; skipping")
            return

        batch_candidates: list[BatchCandidate] = list(self._last_batch_result.candidates)
        if not batch_candidates:
            logger.info("Gap filter: no candidates in batch result")
            return

        # Track filtered results for dashboard update
        filtered_results: list[FilteredCandidate] | None = None

        # Apply gap filter if available
        if self._gap_filter is not None:
            try:
                filtered_results = await self._gap_filter.filter(batch_candidates)
                passed = [fr.candidate for fr in filtered_results if fr.passed_filter]
                logger.info(
                    "Gap filter: %d -> %d passed",
                    len(batch_candidates), len(passed),
                )
            except Exception:
                logger.exception("Gap filter execution failed; using all raw candidates")
                passed = batch_candidates
        else:
            logger.info(
                "Gap filter: no GapFilter injected; using all %d raw candidates",
                len(batch_candidates),
            )
            passed = batch_candidates

        # Convert batch candidates to entry manager candidates
        entry_candidates: list[EntryCandidate] = []
        for bc in passed:
            try:
                entry_candidates.append(_batch_to_entry_candidate(bc))
            except Exception:
                logger.warning("Failed to convert candidate %s; skipping", bc.symbol)

        # Load into EntryManager
        if self._entry_manager is not None and entry_candidates:
            self._entry_manager.load_candidates(entry_candidates)
            logger.info(
                "Gap filter complete: %d candidates loaded into EntryManager",
                len(entry_candidates),
            )
        elif not entry_candidates:
            logger.info("Gap filter: no candidates survived; nothing to load")

        # Update batch_results.json with gap filter status for dashboard
        self._update_batch_results_gap_status(
            passed_symbols={bc.symbol for bc in passed},
            filtered_results=filtered_results,
        )

    def _update_batch_results_gap_status(
        self,
        passed_symbols: set[str],
        filtered_results: list[FilteredCandidate] | None,
    ) -> None:
        """Update gap_filter_status in data/batch_results.json for the dashboard.

        Each candidate entry gets one of:
          - "passed"   -- kept by gap filter or no gap filter injected
          - "filtered" -- removed by gap filter (gap too large)
          - "pending"  -- unchanged (should not happen after this runs)

        If ``filtered_results`` is available (gap filter ran), the
        ``gap_pct`` field is also written for each candidate.
        """
        results_path = os.path.join("data", "batch_results.json")
        if not os.path.exists(results_path):
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read batch_results.json for gap status update")
            return

        # Build a lookup from filtered_results for gap_pct info
        gap_info: dict[str, FilteredCandidate] = {}
        if filtered_results is not None:
            for fr in filtered_results:
                gap_info[fr.symbol] = fr

        candidates_list = data.get("candidates", [])
        for cand_dict in candidates_list:
            sym = cand_dict.get("symbol", "")
            if sym in passed_symbols:
                cand_dict["gap_filter_status"] = "passed"
            else:
                cand_dict["gap_filter_status"] = "filtered"
            # Add gap percentage if available
            fr_info = gap_info.get(sym)
            if fr_info is not None and fr_info.gap_pct is not None:
                cand_dict["gap_pct"] = round(fr_info.gap_pct * 100, 2)
                if fr_info.pre_market_price is not None:
                    cand_dict["pre_market_price"] = round(fr_info.pre_market_price, 2)

        try:
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("Updated gap_filter_status in batch_results.json")
        except OSError:
            logger.warning("Could not write gap status to batch_results.json")

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
            new_symbols = []
            for held in new_positions:
                self._held_positions[held.symbol] = held
                self._position_strategy_map[held.symbol] = held.strategy
                new_symbols.append(held.symbol)
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
                # Log entry trade to live_trades.jsonl
                await self._log_entry_trade(held, account)

            # Subscribe to minute bars for newly opened positions
            if new_symbols:
                await self._broker.add_bar_subscription(new_symbols, self._on_bar)
                logger.info("MOO entries: %d positions opened, subscribed: %s", len(new_positions), new_symbols)
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
            new_symbols = []
            for held in new_positions:
                self._held_positions[held.symbol] = held
                self._position_strategy_map[held.symbol] = held.strategy
                new_symbols.append(held.symbol)
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
                # Log entry trade to live_trades.jsonl
                await self._log_entry_trade(held, account)

            # Subscribe to minute bars for newly opened positions
            if new_symbols:
                await self._broker.add_bar_subscription(new_symbols, self._on_bar)
                logger.info("Confirmation entries: %d positions opened, subscribed: %s", len(new_positions), new_symbols)
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
        # Refresh daily bars before running the scan for latest data
        await self._refresh_daily_bars()

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

        Updates risk manager, portfolio tracker, trade logger, and
        unsubscribes the symbol from minute bar streaming.

        Args:
            symbol: Closed ticker.
            reason: Exit reason string from ExitRuleEngine.
            fill_price: Actual exit fill price.
            pnl: Realised profit/loss.
        """
        held = self._held_positions.pop(symbol, None)
        self._position_strategy_map.pop(symbol, None)

        # Unsubscribe from minute bars for this symbol
        await self._broker.remove_bar_subscription([symbol])

        # Update MFE/MAE tracker
        tracked = self._open_position_tracker.close_position(symbol)
        mfe = tracked.mfe if tracked else 0.0
        mae = tracked.mae if tracked else 0.0
        bars_held = tracked.bar_count if tracked else 0

        # Update risk manager
        self._risk_manager.record_pnl(pnl)

        # Update GDR manager (per-strategy drawdown tracking)
        if self._gdr_manager is not None and held is not None:
            self._gdr_manager.record_trade_pnl(held.strategy, pnl)

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
    # Minute bar handler (held positions only)
    # -----------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        """Handle incoming minute bars from held-position-only stream.

        Used for:
        - MFE/MAE tracking for held positions
        - Forwarding bars to PositionMonitor for exit evaluation
        - Periodic equity snapshot logging
        """
        # MFE/MAE tracking for open positions
        self._open_position_tracker.update_prices(
            bar.symbol, bar.high, bar.low, bar.close,
        )

        # Forward bar to PositionMonitor for exit evaluation
        if self._position_monitor is not None:
            await self._position_monitor.on_bar(bar)

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

        # Fetch full S&P 500 universe for warmup
        try:
            from autotrader.universe.provider import SP500Provider
            provider = SP500Provider()
            infos = await asyncio.to_thread(provider.fetch)
            all_symbols = [i.symbol for i in infos]
            logger.info("Fetched %d S&P 500 symbols for warmup", len(all_symbols))
        except Exception:
            logger.warning("Failed to fetch S&P 500 list; falling back to config symbols")
            all_symbols = list(self._settings.symbols)

        proxy = self._regime_proxy_symbol
        symbols = list(set(all_symbols + [proxy]))
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
        logger.info("Loaded daily bars for %d symbols (total bars: %d)",
                    len(loaded_count), sum(loaded_count.values()))
        self._initialize_regime_from_daily()

    async def _refresh_daily_bars(self) -> None:
        """Fetch latest daily bars for the full S&P 500 universe via REST API.

        Called at 9:00 AM ET (pre-market) and before nightly scan (8:00 PM ET).
        Updates _daily_bar_history and _bar_history with any new bars,
        then refreshes regime classification.
        """
        if not hasattr(self._broker, "get_historical_bars"):
            logger.info("Broker does not support historical bars; skipping daily refresh")
            return

        symbols = list(set(self._settings.symbols + [self._regime_proxy_symbol]))
        logger.info("Refreshing daily bars for %d symbols via REST API...", len(symbols))

        try:
            hist = await self._broker.get_historical_bars(symbols, days=5)
        except Exception:
            logger.exception("Daily bar refresh failed")
            return

        new_bar_count = 0
        for sym, bars in hist.items():
            if not bars:
                continue
            existing_ts = {b.timestamp for b in self._daily_bar_history[sym]}
            for bar in bars:
                if bar.timestamp not in existing_ts:
                    self._daily_bar_history[sym].append(bar)
                    self._bar_history[sym].append(bar)
                    new_bar_count += 1

        if new_bar_count > 0:
            self._initialize_regime_from_daily()
            logger.info("Daily bar refresh complete: %d new bars added", new_bar_count)
        else:
            logger.info("Daily bar refresh: no new bars (already up to date)")

    def _initialize_regime_from_daily(self) -> None:
        """Walk SPY daily bars to classify regime using SPY-based 5-regime system."""
        proxy = self._regime_proxy_symbol
        spy_history = self._daily_bar_history.get(proxy)
        if not spy_history or len(spy_history) < 50:
            logger.warning(
                "Insufficient %s daily bars for regime init (%d bars)",
                proxy, len(spy_history) if spy_history else 0,
            )
            return

        indicators = self._indicator_engine.compute(list(spy_history))
        adx = indicators.get("ADX_14")
        ema_50 = indicators.get("EMA_50")
        bbands = indicators.get("BBANDS_20")

        if any(v is None for v in [adx, ema_50, bbands]):
            logger.warning("Indicators still None after warmup")
            return

        close = list(spy_history)[-1].close
        bb_upper = bbands.get("upper", 0)
        bb_lower = bbands.get("lower", 0)
        bb_middle = bbands.get("middle", 1.0)
        if bb_middle <= 0:
            bb_middle = 1.0
        bb_ratio = (bb_upper - bb_lower) / bb_middle

        regime = self._regime_detector.update(
            adx=adx, close=close, ema_50=ema_50, bb_ratio=bb_ratio,
        )
        self._current_regime = regime
        self._regime_tracker._confirmed_regime = regime
        logger.info(
            "Regime initialised: %s (ADX=%.1f, BB_ratio=%.2f, %d bars)",
            regime.value, adx, bb_ratio, len(spy_history),
        )

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
                    prices[symbol] = pos_by_symbol[symbol].market_value / pos_by_symbol[symbol].quantity
                    continue
                # Use last known bar close
                history = self._bar_history.get(symbol)
                if history:
                    prices[symbol] = history[-1].close

        return prices

    async def _log_entry_trade(self, held: Any, account: AccountInfo) -> None:
        """Record an entry (open) trade in the trade logger.

        Called from ``_on_moo()`` and ``_on_confirmation_window()`` after
        a position has been successfully opened via EntryManager.

        Args:
            held: HeldPosition object from EntryManager.
            account: Account snapshot at the time of entry.
        """
        if self._trade_logger is None:
            return
        try:
            record = LiveTradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=held.symbol,
                strategy=held.strategy,
                direction=held.direction,
                side="buy" if held.direction == "long" else "sell",
                quantity=held.qty,
                price=held.entry_price,
                pnl=0.0,
                regime=self._current_regime.value,
                equity_after=account.equity,
                metadata={"entry_atr": held.entry_atr},
            )
            self._trade_logger.log_trade(record)
        except Exception:
            logger.exception("Trade log write failed for %s entry", held.symbol)

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
