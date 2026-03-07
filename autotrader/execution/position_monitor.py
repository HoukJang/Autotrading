"""PositionMonitor: real-time position monitoring with exit evaluation.

Receives bars from the main trading loop (main.py) for held positions.
On each bar:
  1. Update HeldPosition price extremes (MFE/MAE tracking).
  2. On daily bar boundary: increment bars_held, run ExitRuleEngine.
  3. If ExitDecision.action == "exit": submit exit via OrderManager.
  4. After exit: call ExitRuleEngine.record_close() and notify callback.

This monitor does NOT manage its own stream subscription. Bars are
pushed externally via the public on_bar() method.
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any

from zoneinfo import ZoneInfo

from autotrader.core.types import Bar, Timeframe
from autotrader.execution.exit_rules import ExitRuleEngine
from autotrader.trading.types import HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.indicators.engine import IndicatorEngine
from autotrader.trading.position_book import PositionBook

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger("autotrader.execution.position_monitor")


# Callback type: called when a position is closed by exit rules.
ExitCallback = Callable[[str, str, float, float], Coroutine[Any, Any, None]]
# signature: async def callback(symbol, reason, fill_price, pnl) -> None


class PositionMonitor:
    """Monitors held positions and triggers exits when rules fire.

    Usage:
    1. Instantiate with order_manager, exit_rule_engine, and indicator_engine.
    2. Register positions via ``add_position()``.
    3. Call ``start()`` to begin monitoring.
    4. Push bars via ``on_bar()`` from the main trading loop.
    5. Register an exit callback via ``register_exit_callback()``.
    6. Call ``stop()`` for graceful shutdown.

    Args:
        order_manager: OrderManager for submitting exit orders.
        exit_rule_engine: Shared ExitRuleEngine instance.
        indicator_engine: IndicatorEngine for computing bar indicators.
    """

    def __init__(
        self,
        order_manager: OrderManager,
        exit_rule_engine: ExitRuleEngine,
        indicator_engine: IndicatorEngine,
        position_book: PositionBook | None = None,
    ) -> None:
        self._order_manager = order_manager
        self._exit_rules = exit_rule_engine
        self._indicator_engine = indicator_engine

        # Delegate position storage to the shared PositionBook (SSOT).
        # When no PositionBook is injected (backward compat / tests),
        # create a private one so this class still works standalone.
        # Note: cannot use ``or`` because an empty PositionBook is falsy
        # due to __len__ returning 0.
        self._position_book: PositionBook = position_book if position_book is not None else PositionBook()

        # Minimal bar history per symbol for indicator computation
        self._bar_history: dict[str, deque[Bar]] = {}

        # State flag
        self._running: bool = False

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

        Delegates storage to the shared PositionBook. The capacity check
        is handled by PositionBook.add().

        Args:
            position: Newly created HeldPosition from EntryManager.
        """
        # PositionBook.add() handles duplicate and capacity checks.
        # If the position is already in the book (e.g. added by AutoTrader
        # before calling add_position here), add() returns False but the
        # position is still accessible via get(). We only need to ensure
        # bar_history is initialised.
        if not self._position_book.has(position.symbol):
            self._position_book.add(position)
        if position.symbol not in self._bar_history:
            self._bar_history[position.symbol] = deque(maxlen=500)
        logger.info(
            "Monitoring new position: %s %s (strategy=%s, entry=%.2f)",
            position.direction, position.symbol,
            position.strategy, position.entry_price,
        )

    def remove_position(self, symbol: str) -> HeldPosition | None:
        """Remove a position from monitoring (e.g. manually closed externally).

        Args:
            symbol: Ticker to remove.

        Returns:
            The removed HeldPosition, or None if not tracked.
        """
        self._bar_history.pop(symbol, None)
        return self._position_book.remove(symbol)

    @property
    def monitored_symbols(self) -> list[str]:
        """Currently monitored ticker symbols."""
        return self._position_book.symbols

    async def start(self) -> None:
        """Start the position monitoring (sets running flag)."""
        if self._running:
            logger.warning("PositionMonitor.start() called while already running")
            return
        self._running = True
        logger.info("PositionMonitor started (monitoring %d positions)", self._position_book.count)

    async def stop(self) -> None:
        """Gracefully stop monitoring."""
        logger.info("PositionMonitor stopping")
        self._running = False

    async def on_bar(self, bar: Bar) -> None:
        """Public entry point: receive a bar from the main trading loop.

        Called by main.py for every minute bar on a held position's symbol.
        Updates MFE/MAE tracking and, for daily bars, evaluates exit rules.

        Args:
            bar: Incoming bar (MINUTE or DAILY timeframe).
        """
        await self._on_bar(bar)

    # ------------------------------------------------------------------
    # Bar processing
    # ------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        """Handle incoming bar.

        For MINUTE bars: update MFE/MAE tracking only.
        For DAILY bars: evaluate exit rules.
        """
        symbol = bar.symbol
        if not self._position_book.has(symbol):
            return

        position = self._position_book.get(symbol)
        if position is None:
            return

        # Always update MFE/MAE tracking with raw bar extremes
        position.update_price_extremes(bar.high, bar.low)

        # Only evaluate exits on daily bars
        if bar.timeframe == Timeframe.DAILY:
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
            strategy=position.strategy,
            direction=position.direction,
        )

        # Guard: if exit order failed, keep position in tracking
        if result is None:
            logger.error(
                "EXIT ORDER FAILED for %s %s (reason=%s) -- "
                "position remains OPEN at broker and will retry on next daily bar.",
                position.direction, symbol, decision.reason,
            )
            return

        total_filled_qty = result.filled_qty
        # Weighted-average price accumulator: sum(price * qty) / total_qty
        weighted_price_sum = result.filled_price * result.filled_qty

        # ------------------------------------------------------------------
        # Handle partial fills: submit follow-up market order for remainder
        # ------------------------------------------------------------------
        if result.status == "partially_filled" and result.filled_qty < position.qty:
            remaining_qty = position.qty - result.filled_qty
            logger.warning(
                "PARTIAL FILL on exit for %s %s: filled %.0f of %.0f @ %.2f, "
                "submitting follow-up market order for remaining %.0f shares",
                position.direction, symbol,
                result.filled_qty, position.qty, result.filled_price, remaining_qty,
            )

            followup_result = await self._order_manager.submit_exit(
                symbol=symbol,
                side=exit_side,
                qty=remaining_qty,
                order_type="market",
                strategy=position.strategy,
                direction=position.direction,
            )

            if followup_result is not None and followup_result.filled_qty > 0:
                weighted_price_sum += (
                    followup_result.filled_price * followup_result.filled_qty
                )
                total_filled_qty += followup_result.filled_qty

                if followup_result.status == "partially_filled":
                    still_remaining = position.qty - total_filled_qty
                    avg_price = weighted_price_sum / total_filled_qty
                    logger.critical(
                        "FOLLOW-UP EXIT ALSO PARTIAL for %s %s: "
                        "total filled %.0f of %.0f (avg fill %.2f), "
                        "%.0f shares STILL AT BROKER "
                        "with NO stop-loss -- MANUAL INTERVENTION REQUIRED",
                        position.direction, symbol,
                        total_filled_qty, position.qty, avg_price,
                        still_remaining,
                    )
                else:
                    logger.info(
                        "Follow-up exit filled for %s: %.0f shares @ %.2f",
                        symbol, followup_result.filled_qty,
                        followup_result.filled_price,
                    )
            else:
                still_remaining = position.qty - total_filled_qty
                avg_price = (
                    weighted_price_sum / total_filled_qty
                    if total_filled_qty > 0 else result.filled_price
                )
                logger.critical(
                    "FOLLOW-UP EXIT FAILED for %s %s: "
                    "only %.0f of %.0f shares exited (avg fill %.2f), "
                    "%.0f shares STILL AT BROKER "
                    "with NO stop-loss -- MANUAL INTERVENTION REQUIRED",
                    position.direction, symbol,
                    total_filled_qty, position.qty, avg_price,
                    still_remaining,
                )

            # If we could not exit ALL shares, do NOT remove from tracking.
            # The position stays monitored so the next daily bar retries the exit.
            if total_filled_qty < position.qty:
                # Update position qty to reflect only the residual shares
                exited_avg_price = (
                    weighted_price_sum / total_filled_qty
                    if total_filled_qty > 0 else 0.0
                )
                position.qty = position.qty - total_filled_qty
                logger.warning(
                    "Residual position kept in monitoring: %s %s, "
                    "exited %.0f shares @ avg %.2f, %.0f shares remaining",
                    position.direction, symbol,
                    total_filled_qty, exited_avg_price, position.qty,
                )
                return

        # Compute weighted average fill price across all fills
        fill_price = (
            weighted_price_sum / total_filled_qty if total_filled_qty > 0
            else result.filled_price
        )

        # Compute PnL on the total filled quantity
        pnl = self._order_manager.calculate_pnl(
            entry_price=position.entry_price,
            exit_price=fill_price,
            qty=total_filled_qty,
            direction=position.direction,
        )

        # Record close to engage re-entry block
        self._exit_rules.record_close(symbol)

        # Remove from PositionBook and clean up bar history.
        # Store the removed position reference so the exit callback
        # can still access HeldPosition data (strategy, direction, etc.)
        # even though it's been removed from the PositionBook.
        self._last_exited_position: HeldPosition | None = position
        self._position_book.remove(symbol)
        self._bar_history.pop(symbol, None)

        logger.info(
            "Position closed: %s %s, reason=%s, fill=%.2f, qty=%.0f, pnl=%.2f",
            position.direction, symbol, decision.reason,
            fill_price, total_filled_qty, pnl,
        )

        # Notify registered callbacks
        for cb in self._exit_callbacks:
            try:
                await cb(symbol, decision.reason, fill_price, pnl)
            except Exception:
                logger.exception("Exit callback error for %s", symbol)
