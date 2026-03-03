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
from autotrader.execution.exit_rules import ExitRuleEngine, HeldPosition
from autotrader.execution.order_manager import OrderManager
from autotrader.indicators.engine import IndicatorEngine

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger("autotrader.execution.position_monitor")

MAX_POSITIONS: int = 8


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
    ) -> None:
        self._order_manager = order_manager
        self._exit_rules = exit_rule_engine
        self._indicator_engine = indicator_engine

        # symbol -> HeldPosition
        self._positions: dict[str, HeldPosition] = {}

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
        return self._positions.pop(symbol, None)

    @property
    def monitored_symbols(self) -> list[str]:
        """Currently monitored ticker symbols."""
        return list(self._positions.keys())

    async def start(self) -> None:
        """Start the position monitoring (sets running flag)."""
        if self._running:
            logger.warning("PositionMonitor.start() called while already running")
            return
        self._running = True
        logger.info("PositionMonitor started (monitoring %d positions)", len(self._positions))

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
        if symbol not in self._positions:
            return

        position = self._positions[symbol]

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
