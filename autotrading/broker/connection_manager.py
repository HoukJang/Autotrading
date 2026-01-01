"""
IB Connection Manager
Handles connection lifecycle, health monitoring, and automatic reconnection
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from enum import Enum

import ib_async
from ib_async import IB

from ..core.events import Event, EventType
from ..core.event_bus import EventBus
from ..core.exceptions import ConnectionError, TradingSystemError
from ..config import get_config

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ConnectionEvent(Event):
    """IB connection status event"""

    def __init__(self, state: ConnectionState, details: Optional[Dict[str, Any]] = None):
        super().__init__(event_type=EventType.SYSTEM)
        self.state = state
        self.details = details or {}


class IBConnectionManager:
    """
    Manages IB API connection with automatic reconnection and health monitoring
    """

    def __init__(self, event_bus: EventBus = None, client_id: Optional[int] = None):
        """
        Initialize connection manager

        Args:
            event_bus: Event bus for publishing connection events
            client_id: Optional client ID override (for multi-connection scenarios)
        """
        self.config = get_config()
        self.event_bus = event_bus
        self.ib: Optional[IB] = None
        self.state = ConnectionState.DISCONNECTED

        # Connection parameters
        self.host = self.config.broker.host
        self.port = self.config.broker.port
        self.client_id = client_id if client_id is not None else self.config.broker.client_id

        # Reconnection settings
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        self.reconnect_attempts = 0

        # Health check settings
        self.health_check_interval = 30  # seconds
        self.last_health_check = None
        self._health_check_task = None
        self._reconnect_task = None

        # Connection callbacks
        self._connection_callbacks = []
        self._disconnection_callbacks = []

        logger.info(f"IBConnectionManager initialized for {self.host}:{self.port}")

    async def connect(self) -> bool:
        """
        Connect to IB API

        Returns:
            True if connection successful
        """
        if self.state == ConnectionState.CONNECTED:
            logger.warning("Already connected to IB API")
            return True

        try:
            self.state = ConnectionState.CONNECTING
            await self._publish_connection_event()

            # Create IB instance
            self.ib = IB()

            # Set up event handlers
            self._setup_event_handlers()

            # Connect to TWS/Gateway
            logger.info(f"Connecting to IB API at {self.host}:{self.port}")
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id
            )

            # Verify connection
            if self.ib.isConnected():
                self.state = ConnectionState.CONNECTED
                self.last_health_check = datetime.now()

                # Start health check task
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop()
                )

                # Call connection callbacks
                await self._call_callbacks(self._connection_callbacks)

                await self._publish_connection_event()
                logger.info("Successfully connected to IB API")
                return True
            else:
                raise ConnectionError(
                    "Failed to establish connection",
                    host=self.host,
                    port=self.port
                )

        except Exception as e:
            self.state = ConnectionState.ERROR
            await self._publish_connection_event(error=str(e))
            logger.error(f"Connection failed: {e}")

            # Trigger reconnection if needed
            if self.reconnect_attempts < self.max_reconnect_attempts:
                await self._schedule_reconnect()

            raise ConnectionError(
                f"Failed to connect to IB API: {e}",
                host=self.host,
                port=self.port,
                retry_count=self.reconnect_attempts
            )

    async def disconnect(self) -> None:
        """Disconnect from IB API"""
        if self.state == ConnectionState.DISCONNECTED:
            return

        logger.info("Disconnecting from IB API")

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

        # Cancel reconnect task if running
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        # Call disconnection callbacks
        await self._call_callbacks(self._disconnection_callbacks)

        # Disconnect IB
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

        self.state = ConnectionState.DISCONNECTED
        await self._publish_connection_event()
        logger.info("Disconnected from IB API")

    async def reconnect(self) -> bool:
        """
        Reconnect to IB API

        Returns:
            True if reconnection successful
        """
        logger.info(f"Attempting reconnection (attempt {self.reconnect_attempts + 1})")

        self.state = ConnectionState.RECONNECTING
        await self._publish_connection_event()

        # Disconnect first if needed
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

        # Increment attempt counter
        self.reconnect_attempts += 1

        try:
            # Try to reconnect
            result = await self.connect()

            if result:
                logger.info("Reconnection successful")

            return result
        except Exception as e:
            logger.error(f"Reconnection attempt failed: {e}")

            if self.reconnect_attempts < self.max_reconnect_attempts:
                await self._schedule_reconnect()
            else:
                logger.error(
                    f"Max reconnection attempts ({self.max_reconnect_attempts}) reached"
                )
                self.state = ConnectionState.ERROR
                await self._publish_connection_event(
                    error="Max reconnection attempts exceeded"
                )

            return False

    async def health_check(self) -> bool:
        """
        Check connection health

        Returns:
            True if connection is healthy
        """
        if not self.ib or not self.ib.isConnected():
            return False

        try:
            # Request current time to verify connection
            server_time = await self.ib.reqCurrentTimeAsync()
            self.last_health_check = datetime.now()

            logger.debug(f"Health check passed, server time: {server_time}")
            return True

        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def add_connection_callback(self, callback: Callable) -> None:
        """Add callback to be called on connection"""
        self._connection_callbacks.append(callback)

    def add_disconnection_callback(self, callback: Callable) -> None:
        """Add callback to be called on disconnection"""
        self._disconnection_callbacks.append(callback)

    def is_connected(self) -> bool:
        """Check if connected to IB API"""
        return self.ib and self.ib.isConnected()

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information"""
        return {
            'state': self.state.value,
            'host': self.host,
            'port': self.port,
            'client_id': self.client_id,
            'is_tws': self.port == 7497,
            'reconnect_attempts': self.reconnect_attempts,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None
        }

    # Private methods

    def _setup_event_handlers(self) -> None:
        """Set up IB event handlers"""
        if not self.ib:
            return

        # Handle disconnection
        self.ib.disconnectedEvent += self._on_disconnected

        # Handle errors
        self.ib.errorEvent += self._on_error

    async def _on_disconnected(self) -> None:
        """Handle disconnection event"""
        logger.warning("IB API disconnected unexpectedly")

        self.state = ConnectionState.DISCONNECTED
        await self._publish_connection_event()

        # Call disconnection callbacks
        await self._call_callbacks(self._disconnection_callbacks)

        # Schedule reconnection
        if self.reconnect_attempts < self.max_reconnect_attempts:
            await self._schedule_reconnect()

    async def _on_error(self, reqId: int, errorCode: int, errorString: str,
                        contract: Any = None) -> None:
        """Handle error events"""
        # Log error (filter out info messages)
        if errorCode < 2000:  # Errors are < 2000
            logger.error(f"IB Error {errorCode}: {errorString}")
        elif errorCode < 10000:  # Warnings
            logger.warning(f"IB Warning {errorCode}: {errorString}")
        else:  # Info messages
            logger.debug(f"IB Info {errorCode}: {errorString}")

        # Check for critical connection errors
        critical_errors = [504, 502, 1100, 1101, 1102]  # Connection lost codes
        if errorCode in critical_errors:
            logger.error(f"Critical connection error: {errorString}")
            await self._on_disconnected()

    async def _health_check_loop(self) -> None:
        """Background health check loop"""
        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Perform health check
                is_healthy = await self.health_check()

                if not is_healthy:
                    logger.warning("Health check failed, triggering reconnection")
                    await self._on_disconnected()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt"""
        if self._reconnect_task:
            return  # Already scheduled

        delay = self.reconnect_delay * (2 ** min(self.reconnect_attempts, 3))
        logger.info(f"Scheduling reconnection in {delay} seconds")

        self._reconnect_task = asyncio.create_task(
            self._delayed_reconnect(delay)
        )

    async def _delayed_reconnect(self, delay: float) -> None:
        """Delayed reconnection"""
        await asyncio.sleep(delay)
        self._reconnect_task = None
        await self.reconnect()

    async def _call_callbacks(self, callbacks: list) -> None:
        """Call a list of callbacks"""
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Callback error: {e}")

    async def _publish_connection_event(self, error: str = None) -> None:
        """Publish connection event to event bus"""
        if not self.event_bus:
            return

        event = ConnectionEvent(
            state=self.state,
            details={
                'host': self.host,
                'port': self.port,
                'client_id': self.client_id,
                'reconnect_attempts': self.reconnect_attempts,
                'error': error
            }
        )

        await self.event_bus.publish(event)