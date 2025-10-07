"""
Event Bus Implementation
Async event processing with publish/subscribe pattern
"""

import asyncio
from collections import defaultdict
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging
from .events import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class EventStats:
    """Statistics for event processing"""
    total_events: int = 0
    events_by_type: Dict[str, int] = field(default_factory=dict)
    processing_time_ms: List[float] = field(default_factory=list)
    errors: int = 0
    last_event_time: Optional[datetime] = None

    def add_event(self, event_type: str, processing_time_ms: float):
        """Update statistics with new event"""
        self.total_events += 1
        self.events_by_type[event_type] = self.events_by_type.get(event_type, 0) + 1
        self.processing_time_ms.append(processing_time_ms)
        self.last_event_time = datetime.now()

        # Keep only last 1000 processing times to avoid memory issues
        if len(self.processing_time_ms) > 1000:
            self.processing_time_ms = self.processing_time_ms[-1000:]

    def get_avg_processing_time(self) -> float:
        """Get average processing time in milliseconds"""
        if not self.processing_time_ms:
            return 0.0
        return sum(self.processing_time_ms) / len(self.processing_time_ms)


class EventBus:
    """
    Asynchronous event bus for publish/subscribe pattern
    """

    def __init__(self, queue_size: int = 10000):
        """
        Initialize event bus

        Args:
            queue_size: Maximum size of event queue
        """
        self.subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.stats = EventStats()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self.error_handler: Optional[Callable] = None

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """
        Subscribe to an event type

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to handle the event
        """
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError(f"Handler {handler.__name__} must be an async function")

        self.subscribers[event_type].append(handler)
        logger.info(f"Subscribed {handler.__name__} to {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """
        Unsubscribe from an event type

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if handler in self.subscribers[event_type]:
            self.subscribers[event_type].remove(handler)
            logger.info(f"Unsubscribed {handler.__name__} from {event_type.value}")

    async def publish(self, event: Event) -> None:
        """
        Publish an event to the bus

        Args:
            event: Event to publish
        """
        try:
            await self.event_queue.put(event)
            logger.debug(f"Published event: {event.event_type.value} (ID: {event.event_id})")
        except asyncio.QueueFull:
            logger.error(f"Event queue full! Dropping event: {event.event_id}")
            self.stats.errors += 1

    async def publish_many(self, events: List[Event]) -> None:
        """
        Publish multiple events

        Args:
            events: List of events to publish
        """
        for event in events:
            await self.publish(event)

    async def start(self) -> None:
        """Start the event processor"""
        if self._running:
            logger.warning("Event bus already running")
            return

        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the event processor"""
        self._running = False

        if self._processor_task:
            # Wait for queue to be empty
            await self.event_queue.join()

            # Cancel processor task
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

            self._processor_task = None
            logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Process events from the queue"""
        while self._running:
            try:
                # Wait for event with timeout to allow checking _running flag
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                # Process event
                start_time = datetime.now()
                await self._handle_event(event)
                processing_time = (datetime.now() - start_time).total_seconds() * 1000

                # Update statistics
                self.stats.add_event(event.event_type.value, processing_time)

                # Mark task as done
                self.event_queue.task_done()

            except asyncio.TimeoutError:
                # Timeout is normal, just check if we should continue
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
                self.stats.errors += 1
                if self.error_handler:
                    try:
                        await self.error_handler(e)
                    except Exception as handler_error:
                        logger.error(f"Error in error handler: {handler_error}")

    async def _handle_event(self, event: Event) -> None:
        """
        Handle a single event by calling all subscribers

        Args:
            event: Event to handle
        """
        handlers = self.subscribers.get(event.event_type, [])

        if not handlers:
            logger.debug(f"No handlers for event type: {event.event_type.value}")
            return

        # Call handlers in parallel
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._call_handler(handler, event))
            tasks.append(task)

        # Wait for all handlers to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                handler_name = handlers[i].__name__
                logger.error(
                    f"Handler {handler_name} failed for event {event.event_id}: {result}",
                    exc_info=result
                )
                self.stats.errors += 1

    async def _call_handler(self, handler: Callable, event: Event) -> None:
        """
        Call a handler with error handling

        Args:
            handler: Handler function to call
            event: Event to pass to handler
        """
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"Handler {handler.__name__} failed for event {event.event_id}: {e}",
                exc_info=True
            )
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        return {
            'total_events': self.stats.total_events,
            'events_by_type': dict(self.stats.events_by_type),
            'avg_processing_time_ms': self.stats.get_avg_processing_time(),
            'queue_size': self.event_queue.qsize(),
            'max_queue_size': self.event_queue.maxsize,
            'errors': self.stats.errors,
            'last_event_time': self.stats.last_event_time.isoformat() if self.stats.last_event_time else None,
            'running': self._running,
            'subscribers': {
                event_type.value: len(handlers)
                for event_type, handlers in self.subscribers.items()
            }
        }

    def clear_stats(self) -> None:
        """Clear statistics"""
        self.stats = EventStats()

    def set_error_handler(self, handler: Callable) -> None:
        """
        Set a custom error handler

        Args:
            handler: Async function to handle errors
        """
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError("Error handler must be an async function")
        self.error_handler = handler

    async def wait_until_empty(self) -> None:
        """Wait until event queue is empty"""
        await self.event_queue.join()

    def is_running(self) -> bool:
        """Check if event bus is running"""
        return self._running