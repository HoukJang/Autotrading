"""Core event bus module for pub-sub pattern."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Simple async event bus implementing pub-sub pattern.

    This class provides a basic but robust event bus for decoupled
    communication between components using async/await.

    Example:
        >>> bus = EventBus()
        >>> async def on_tick(data):
        ...     print(f"Tick: {data}")
        >>> bus.subscribe("tick", on_tick)
        >>> await bus.emit("tick", {"symbol": "AAPL"})
    """

    def __init__(self) -> None:
        """Initialize the event bus with empty handlers dictionary."""
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        """Subscribe a handler to an event.

        Args:
            event: Event name to subscribe to.
            handler: Async callable that receives event data.

        Raises:
            TypeError: If handler is not callable.
        """
        if not callable(handler):
            raise TypeError(f"Handler must be callable, got {type(handler)}")

        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        """Unsubscribe a handler from an event.

        If the handler is not subscribed to this event, does nothing.

        Args:
            event: Event name to unsubscribe from.
            handler: Handler to remove.
        """
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: str, data: Any = None) -> None:
        """Emit an event to all subscribed handlers.

        If a handler raises an exception, it is logged and execution
        continues with the next handler.

        Args:
            event: Event name to emit.
            data: Data to pass to handlers.
        """
        handlers = self._handlers.get(event, [])

        # Execute all handlers, catching individual exceptions
        tasks = []
        for handler in handlers:
            tasks.append(self._safe_call_handler(handler, event, data))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)

    async def _safe_call_handler(self, handler: Handler, event: str, data: Any) -> None:
        """Safely call a handler, logging any exceptions.

        Args:
            handler: Handler to call.
            event: Event name being handled.
            data: Event data.
        """
        try:
            await handler(data)
        except Exception:
            logger.exception("Handler %s failed for event '%s'", handler.__name__, event)
