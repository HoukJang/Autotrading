"""PositionMonitor: real-time position monitoring with exit evaluation.

Streams bars for held positions only (up to MAX_POSITIONS symbols).
On each bar:
  1. Update HeldPosition price extremes (MFE/MAE tracking).
  2. On daily bar boundary: increment bars_held, run ExitRuleEngine.
  3. If ExitDecision.action == "exit": submit exit via OrderManager.
  4. After exit: call ExitRuleEngine.record_close() and notify callback.

Stream subscription is managed dynamically: re-subscribed when the
set of held symbols changes (new entry or exit).

Reconnect logic: if the stream disconnects unexpectedly, the monitor
attempts to reconnect with exponential back-off up to MAX_RECONNECT_ATTEMPTS.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Callable, Coroutine, Any

from zoneinfo import ZoneInfo

from autotrader.broker.alpaca_adapter import AlpacaAdapter
from autotrader.core.aggregator import DailyBarAggregator
from autotrader.core.types import Bar, Timeframe
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.indicators.engine import IndicatorEngine

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger("autotrader.execution.position_monitor")

MAX_POSITIONS: int = 8
MAX_RECONNECT_ATTEMPTS: int = 5
RECONNECT_BASE_DELAY: float = 5.0  # seconds; doubled on each failure


# Callback type: called when a position is closed by exit rules.
ExitCallback = Callable[[str, str, float, float], Coroutine[Any, Any, None]]
# signature: async def callback(symbol, reason, fill_price, pnl) -> None


class PositionMonitor:
    """Monitors held positions in real time and triggers exits when rules fire.

    Usage:
    1. Instantiate with adapter, order_manager, exit_rule_engine, and
       indicator_engine.
    2. Register positions via ``add_position()``.
    3. Call ``start()`` to begin streaming and exit evaluation.
    4. Register an exit callback via ``register_exit_callback()`` to
       receive notifications when a position is closed by this monitor.
    5. Call ``stop()`` for graceful shutdown.

    Args:
        adapter: Connected AlpacaAdapter for bar streaming.
        order_manager: OrderManager for submitting exit orders.
        exit_rule_engine: Shared ExitRuleEngine instance.
        indicator_engine: IndicatorEngine for computing bar indicators.
    """

    def __init__(
        self,
        adapter: AlpacaAdapter,
        order_manager: OrderManager,
        exit_rule_engine: ExitRuleEngine,
        indicator_engine: IndicatorEngine,
    ) -> None:
        self._adapter = adapter
        self._order_manager = order_manager
        self._exit_rules = exit_rule_engine
        self._indicator_engine = indicator_engine

        # symbol -> HeldPosition
        self._positions: dict[str, HeldPosition] = {}

        # Bar aggregators for minute->daily conversion, one per symbol
        self._aggregators: dict[str, DailyBarAggregator] = {}

        # Minimal bar history per symbol for indicator computation
        from collections import deque
        self._bar_history: dict[str, deque[Bar]] = {}

        # Asyncio infrastructure
        self._running: bool = False
        self._stream_task: asyncio.Task | None = None
        self._reconnect_count: int = 0

        # Exit callback: called after successful exit order
        self._exit_callbacks: list[ExitCallback] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_exit_callback(self, cb: ExitCallback) -> None:
        """Register an async callback invoked after each exit.

        The callback receives ``(symbol, reason, fill_price, pnl)``.

        Args:
            cb: Async callable.
        """
        self._exit_callbacks.append(cb)

    def add_position(self, position: HeldPosition) -> None:
        """Register a new position for monitoring.

        Triggers stream resubscription if already running.

        Args:
            position: Newly created HeldPosition from EntryManager.
        """
        if len(self._positions) >= MAX_POSITIONS:
            logger.warning(
                "MAX_POSITIONS (%d) reached; cannot monitor %s",
                MAX_POSITIONS, position.symbol,
            )
            return
        self._positions[position.symbol] = position
        from collections import deque
        if position.symbol not in self._bar_history:
            self._bar_history[position.symbol] = deque(maxlen=500)
        if position.symbol not in self._aggregators:
            self._aggregators[position.symbol] = DailyBarAggregator()
        logger.info(
            "Monitoring new position: %s %s (strategy=%s, entry=%.2f)",
            position.direction, position.symbol,
            position.strategy, position.entry_price,
        )
        if self._running:
            asyncio.ensure_future(self._resubscribe())

    def remove_position(self, symbol: str) -> HeldPosition | None:
        """Remove a position from monitoring (e.g. manually closed externally).

        Args:
            symbol: Ticker to remove.

        Returns:
            The removed HeldPosition, or None if not tracked.
        """
        position = self._positions.pop(symbol, None)
        if position is not None and self._running:
            asyncio.ensure_future(self._resubscribe())
        return position

    @property
    def monitored_symbols(self) -> list[str]:
        """Currently monitored ticker symbols."""
        return list(self._positions.keys())

    async def start(self) -> None:
        """Start the position monitoring stream.

        Subscribes to bars for all currently held symbols.  If no positions
        are held, monitoring starts in idle mode and activates on the first
        ``add_position()`` call.
        """
        if self._running:
            logger.warning("PositionMonitor.start() called while already running")
            return
        self._running = True
        self._reconnect_count = 0
        logger.info("PositionMonitor starting (monitoring %d positions)", len(self._positions))
        if self._positions:
            await self._subscribe()

    async def stop(self) -> None:
        """Gracefully stop the monitoring stream."""
        logger.info("PositionMonitor stopping")
        self._running = False
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stream_task = None

    # ------------------------------------------------------------------
    # Bar processing
    # ------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        """Handle incoming bar from the Alpaca stream.

        For MINUTE bars: pass through DailyBarAggregator; on daily
        boundary trigger ``_on_daily_bar()``.
        For DAILY bars: process directly.
        """
        symbol = bar.symbol
        if symbol not in self._positions:
            return

        position = self._positions[symbol]

        # Always update MFE/MAE tracking with raw minute-bar extremes
        position.update_price_extremes(bar.high, bar.low)

        if bar.timeframe == Timeframe.MINUTE:
            aggregator = self._aggregators.get(symbol)
            if aggregator is None:
                return
            daily_bar = aggregator.add(bar)
            if daily_bar is not None:
                await self._on_daily_bar(daily_bar, position)
        else:
            await self._on_daily_bar(bar, position)

    async def _on_daily_bar(self, bar: Bar, position: HeldPosition) -> None:
        """Process a completed daily bar for an open position.

        Updates bars_held, computes indicators, evaluates exit rules,
        and submits exit order if triggered.

        Args:
            bar: Completed daily bar.
            position: The HeldPosition for this symbol.
        """
        symbol = bar.symbol
        history = self._bar_history.get(symbol)
        if history is None:
            return

        history.append(bar)
        position.bars_held += 1

        # Compute current indicators for exit evaluation
        indicators = self._indicator_engine.compute(history)

        # Get current date in US Eastern
        current_date_et = datetime.now(timezone.utc).astimezone(_ET).date()

        # Evaluate exit rules
        decision = self._exit_rules.evaluate(
            position=position,
            bar_close=bar.close,
            bar_high=bar.high,
            bar_low=bar.low,
            indicators=indicators,
            current_date_et=current_date_et,
        )

        if decision.action != "exit":
            return

        logger.info(
            "Exit triggered for %s %s: reason=%s, bars_held=%d",
            position.direction, symbol, decision.reason, position.bars_held,
        )

        # Determine exit order side
        from typing import Literal
        exit_side: Literal["buy", "sell"] = "sell" if position.direction == "long" else "buy"

        result = await self._order_manager.submit_exit(
            symbol=symbol,
            side=exit_side,
            qty=position.qty,
            order_type="market",
        )

        fill_price = result.filled_price if result else bar.close
        fill_qty = result.filled_qty if result else position.qty

        # Compute PnL
        pnl = self._order_manager.calculate_pnl(
            entry_price=position.entry_price,
            exit_price=fill_price,
            qty=fill_qty,
            direction=position.direction,
        )

        # Record close to engage re-entry block
        self._exit_rules.record_close(symbol)

        # Remove from monitoring
        del self._positions[symbol]

        logger.info(
            "Position closed: %s %s, reason=%s, fill=%.2f, pnl=%.2f",
            position.direction, symbol, decision.reason, fill_price, pnl,
        )

        # Notify registered callbacks
        for cb in self._exit_callbacks:
            try:
                await cb(symbol, decision.reason, fill_price, pnl)
            except Exception:
                logger.exception("Exit callback error for %s", symbol)

        # Resubscribe with updated symbol set
        if self._running and self._positions:
            await self._resubscribe()

    # ------------------------------------------------------------------
    # Stream management
    # ------------------------------------------------------------------

    async def _subscribe(self) -> None:
        """Subscribe to bar stream for currently held symbols."""
        symbols = list(self._positions.keys())
        if not symbols:
            return
        logger.info("Subscribing to bars for: %s", symbols)
        try:
            await self._adapter.subscribe_bars(symbols, self._on_bar)
            # Run the stream in a background thread (Alpaca SDK pattern)
            if hasattr(self._adapter, "run_stream"):
                self._stream_task = asyncio.create_task(
                    asyncio.to_thread(self._adapter.run_stream)
                )
        except Exception:
            logger.exception("Failed to subscribe to bars for positions")

    async def _resubscribe(self) -> None:
        """Cancel existing stream and resubscribe with updated symbol set."""
        # Stop existing stream
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stream_task = None

        if not self._positions:
            logger.info("No positions remaining; stream not restarted")
            return

        symbols = list(self._positions.keys())
        logger.info("Resubscribing to bars: %s", symbols)
        try:
            await self._adapter.subscribe_bars(symbols, self._on_bar)
            if hasattr(self._adapter, "run_stream"):
                self._stream_task = asyncio.create_task(
                    asyncio.to_thread(self._adapter.run_stream)
                )
            self._reconnect_count = 0
        except Exception:
            logger.exception("Resubscription failed")
            await self._handle_reconnect()

    async def _handle_reconnect(self) -> None:
        """Attempt exponential back-off reconnection on stream failure."""
        self._reconnect_count += 1
        if self._reconnect_count > MAX_RECONNECT_ATTEMPTS:
            logger.error(
                "Max reconnect attempts (%d) exceeded; position monitoring suspended",
                MAX_RECONNECT_ATTEMPTS,
            )
            return

        delay = RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1))
        logger.warning(
            "Stream disconnected; reconnecting in %.0fs (attempt %d/%d)",
            delay, self._reconnect_count, MAX_RECONNECT_ATTEMPTS,
        )
        await asyncio.sleep(delay)
        await self._resubscribe()
