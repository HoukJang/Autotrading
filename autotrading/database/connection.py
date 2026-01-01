"""
Database Connection Manager
Handles PostgreSQL connection pooling and query execution
"""

import asyncio
import asyncpg
from asyncpg import Pool, Connection
from typing import Optional, List, Dict, Any, Tuple, Union
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from ..config import get_config
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Database connection manager with pooling
    """

    _instance: Optional['DatabaseManager'] = None

    def __new__(cls) -> 'DatabaseManager':
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize database manager"""
        if self._initialized:
            return

        self._initialized = True
        self.config = get_config()
        self.pool: Optional[Pool] = None
        self._connected = False

    async def connect(self) -> None:
        """Create database connection pool"""
        if self._connected:
            logger.warning("Database already connected")
            return

        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.database.host,
                port=self.config.database.port,
                database=self.config.database.name,
                user=self.config.database.user,
                password=self.config.database.password,
                min_size=5,
                max_size=self.config.database.pool_size,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60
            )
            self._connected = True
            logger.info(
                f"Database connection pool created "
                f"(min: 5, max: {self.config.database.pool_size})"
            )

            # Test connection
            await self.test_connection()

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise DatabaseError(
                f"Failed to connect to database: {e}",
                operation='connect'
            )

    async def disconnect(self) -> None:
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            self._connected = False
            logger.info("Database connection pool closed")

    async def test_connection(self) -> bool:
        """Test database connection"""
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                logger.info("Database connection test successful")
                return result == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """
        Execute a query without returning results

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Status string
        """
        try:
            async with self.acquire() as conn:
                result = await conn.execute(query, *args)
                return result
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise DatabaseError(
                f"Query execution failed: {e}",
                query=query,
                operation='execute'
            )

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Fetch multiple rows

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of rows as dictionaries
        """
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Query fetch failed: {e}")
            raise DatabaseError(
                f"Query fetch failed: {e}",
                query=query,
                operation='fetch'
            )

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Row as dictionary or None
        """
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Query fetchrow failed: {e}")
            raise DatabaseError(
                f"Query fetchrow failed: {e}",
                query=query,
                operation='fetchrow'
            )

    async def fetchval(self, query: str, *args) -> Any:
        """
        Fetch a single value

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single value
        """
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Query fetchval failed: {e}")
            raise DatabaseError(
                f"Query fetchval failed: {e}",
                query=query,
                operation='fetchval'
            )

    async def insert_market_data(
        self,
        symbol: str,
        timestamp: datetime,
        open_price: Union[float, Decimal],
        high_price: Union[float, Decimal],
        low_price: Union[float, Decimal],
        close_price: Union[float, Decimal],
        volume: int,
        vwap: Optional[Union[float, Decimal]] = None,
        tick_count: Optional[int] = None
    ) -> int:
        """
        Insert market data bar

        Args:
            symbol: Trading symbol
            timestamp: Bar timestamp
            open_price: Opening price
            high_price: High price
            low_price: Low price
            close_price: Closing price
            volume: Volume
            vwap: Volume-weighted average price
            tick_count: Number of ticks

        Returns:
            Inserted row ID
        """
        query = """
            INSERT INTO market_data_1min
            (symbol, timestamp, open_price, high_price, low_price, close_price, volume, vwap, tick_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                vwap = EXCLUDED.vwap,
                tick_count = EXCLUDED.tick_count
            RETURNING id
        """

        return await self.fetchval(
            query,
            symbol, timestamp, open_price, high_price,
            low_price, close_price, volume, vwap, tick_count
        )

    async def bulk_insert_market_data(self, bars: List[Dict[str, Any]]) -> int:
        """
        Bulk insert market data bars

        Args:
            bars: List of bar dictionaries

        Returns:
            Number of inserted rows
        """
        if not bars:
            return 0

        query = """
            INSERT INTO market_data_1min
            (symbol, timestamp, open_price, high_price, low_price, close_price, volume, vwap, tick_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                vwap = EXCLUDED.vwap,
                tick_count = EXCLUDED.tick_count
        """

        try:
            async with self.acquire() as conn:
                # Convert bars to tuples for executemany
                values = [
                    (
                        bar['symbol'], bar['timestamp'],
                        bar['open_price'], bar['high_price'],
                        bar['low_price'], bar['close_price'],
                        bar['volume'], bar.get('vwap'), bar.get('tick_count')
                    )
                    for bar in bars
                ]

                # Use executemany for bulk insert
                await conn.executemany(query, values)
                return len(values)

        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            raise DatabaseError(
                f"Bulk insert failed: {e}",
                operation='bulk_insert',
                table='market_data_1min'
            )

    async def get_latest_bars(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get latest market data bars

        Args:
            symbol: Trading symbol
            limit: Number of bars to retrieve

        Returns:
            List of bars
        """
        query = """
            SELECT * FROM market_data_1min
            WHERE symbol = $1
            ORDER BY timestamp DESC
            LIMIT $2
        """
        return await self.fetch(query, symbol, limit)

    async def log_event(
        self,
        event_type: str,
        severity: str,
        component: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log system event to database

        Args:
            event_type: Type of event
            severity: Severity level
            component: Component name
            message: Event message
            metadata: Additional metadata
        """
        query = """
            INSERT INTO system_events
            (event_type, severity, component, message, metadata)
            VALUES ($1, $2, $3, $4, $5)
        """

        import json
        await self.execute(
            query,
            event_type, severity, component, message,
            json.dumps(metadata) if metadata else None
        )

    async def get_system_config(self, key: str) -> Optional[str]:
        """
        Get system configuration value

        Args:
            key: Configuration key

        Returns:
            Configuration value or None
        """
        query = "SELECT value FROM system_config WHERE key = $1"
        return await self.fetchval(query, key)

    async def update_system_config(self, key: str, value: str) -> None:
        """
        Update system configuration

        Args:
            key: Configuration key
            value: Configuration value
        """
        query = """
            INSERT INTO system_config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = NOW()
        """
        await self.execute(query, key, value)

    # Whitelist of allowed tables for cleanup operations (SQL injection prevention)
    _ALLOWED_CLEANUP_TABLES = frozenset({
        'market_data_1min',
        'trading_signals',
        'system_events'
    })

    async def cleanup_old_data(self, days_to_keep: int = 365) -> int:
        """
        Clean up old data

        Args:
            days_to_keep: Number of days of data to keep

        Returns:
            Number of deleted rows
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        queries = [
            ("market_data_1min", "timestamp < $1"),
            ("trading_signals", "timestamp < $1"),
            ("system_events", "timestamp < $1")
        ]

        total_deleted = 0
        for table, condition in queries:
            # Validate table name against whitelist (SQL injection prevention)
            if table not in self._ALLOWED_CLEANUP_TABLES:
                logger.warning(f"Attempted cleanup on non-whitelisted table: {table}")
                continue
            
            query = f"DELETE FROM {table} WHERE {condition}"
            result = await self.execute(query, cutoff_date)
            # Parse result string to get count
            if result and 'DELETE' in result:
                count = int(result.split(' ')[1])
                total_deleted += count
                logger.info(f"Deleted {count} old records from {table}")

        return total_deleted

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self.pool:
            return {'connected': False}

        return {
            'connected': True,
            'size': self.pool.get_size(),
            'free_size': self.pool.get_idle_size(),
            'min_size': self.pool._minsize,
            'max_size': self.pool._maxsize
        }


# Singleton instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get database manager singleton instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager