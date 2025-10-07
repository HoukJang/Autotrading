#!/usr/bin/env python3
"""
Phase 1 Infrastructure Test Script
Validates all core components are working correctly
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Fix Windows console encoding
if sys.platform == 'win32':
    import locale
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from core import (
    Event, MarketDataEvent, SignalEvent, OrderEvent,
    EventBus, TradingLogger, get_logger,
    TradingSystemError, ConnectionError
)
from core.events import (
    EventType, SignalType, OrderAction, OrderType, OrderStatus,
    MarketBar, Signal, Order
)
from config import get_config
from database import get_db_manager


async def test_configuration():
    """Test configuration loading"""
    print("\n[CONFIG] Testing Configuration...")
    try:
        config = get_config()

        # Validate configuration
        config.validate()
        print("[OK] Configuration loaded and validated")

        # Print configuration summary
        print(f"  Environment: {config.environment}")
        print(f"  Database: {config.database.name} @ {config.database.host}")
        print(f"  Broker: {config.broker.connection_name} @ {config.broker.host}:{config.broker.port}")
        print(f"  Risk: Max position={config.risk.max_position_size}, Max risk={config.risk.max_portfolio_risk:.2%}")

        return True
    except Exception as e:
        print(f"[ERROR] Configuration test failed: {e}")
        return False


async def test_database_connection():
    """Test database connection and operations"""
    print("\n[DATABASE] Testing Database Connection...")
    try:
        db = get_db_manager()

        # Connect to database
        await db.connect()
        print("[OK] Database connected")

        # Test connection
        result = await db.test_connection()
        if result:
            print("[OK] Connection test successful")
        else:
            print("[ERROR] Connection test failed")
            return False

        # Test insert
        await db.log_event(
            event_type="TEST",
            severity="INFO",
            component="test_script",
            message="Phase 1 infrastructure test",
            metadata={"test": True, "timestamp": datetime.now().isoformat()}
        )
        print("[OK] Event logging successful")

        # Test query
        events = await db.fetch(
            "SELECT * FROM system_events WHERE event_type = 'TEST' ORDER BY timestamp DESC LIMIT 1"
        )
        if events:
            print(f"[OK] Query successful: Found {len(events)} test event(s)")
        else:
            print("[WARNING] No test events found")

        # Test market data insert
        bar_id = await db.insert_market_data(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=4500.25,
            high_price=4505.50,
            low_price=4498.75,
            close_price=4502.00,
            volume=12345,
            vwap=4501.50,
            tick_count=567
        )
        print(f"[OK] Market data insert successful (ID: {bar_id})")

        # Test retrieval
        bars = await db.get_latest_bars("ES", limit=1)
        if bars:
            print(f"[OK] Market data retrieval successful: {bars[0]['symbol']} @ {bars[0]['close_price']}")

        # Get pool stats
        stats = await db.get_pool_stats()
        print(f"[OK] Connection pool: {stats['free_size']}/{stats['size']} connections free")

        return True
    except Exception as e:
        print(f"[ERROR] Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_event_system():
    """Test event bus and event handling"""
    print("\n[EVENTS] Testing Event System...")
    try:
        event_bus = EventBus(queue_size=1000)

        # Track received events
        received_events = []

        # Create test handlers
        async def market_data_handler(event: MarketDataEvent):
            received_events.append(("market", event))
            print(f"  [MARKET] Received market data: {event.symbol}")

        async def signal_handler(event: SignalEvent):
            received_events.append(("signal", event))
            print(f"  [SIGNAL] Received signal: {event.signal.signal_type.value}")

        async def order_handler(event: OrderEvent):
            received_events.append(("order", event))
            print(f"  [ORDER] Received order: {event.order.action.value}")

        # Subscribe handlers
        event_bus.subscribe(EventType.MARKET_DATA, market_data_handler)
        event_bus.subscribe(EventType.SIGNAL, signal_handler)
        event_bus.subscribe(EventType.ORDER, order_handler)
        print("[OK] Event handlers subscribed")

        # Start event bus
        await event_bus.start()
        print("[OK] Event bus started")

        # Publish test events
        # Market data event
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("4500.00"),
            high_price=Decimal("4505.00"),
            low_price=Decimal("4495.00"),
            close_price=Decimal("4502.50"),
            volume=10000
        )
        market_event = MarketDataEvent(symbol="ES", bar=bar)
        await event_bus.publish(market_event)

        # Signal event
        signal = Signal(
            strategy_id="test_strategy",
            symbol="ES",
            signal_type=SignalType.BUY,
            quantity=2,
            price=Decimal("4502.50"),
            confidence=0.85
        )
        signal_event = SignalEvent(signal=signal)
        await event_bus.publish(signal_event)

        # Order event
        order = Order(
            order_id="TEST123",
            symbol="ES",
            action=OrderAction.BUY,
            order_type=OrderType.LIMIT,
            quantity=2,
            limit_price=Decimal("4502.00")
        )
        order_event = OrderEvent(order=order)
        await event_bus.publish(order_event)

        # Wait for processing
        await event_bus.wait_until_empty()
        await asyncio.sleep(0.5)  # Allow handlers to complete

        # Check results
        if len(received_events) == 3:
            print(f"[OK] All {len(received_events)} events processed successfully")
        else:
            print(f"[WARNING] Only {len(received_events)}/3 events processed")

        # Get statistics
        stats = event_bus.get_stats()
        print(f"[OK] Event stats: {stats['total_events']} total, "
              f"{stats['avg_processing_time_ms']:.2f}ms avg processing time")

        # Stop event bus
        await event_bus.stop()
        print("[OK] Event bus stopped cleanly")

        return True
    except Exception as e:
        print(f"[ERROR] Event system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_logging_system():
    """Test structured logging"""
    print("\n[LOGGING] Testing Logging System...")
    try:
        # Initialize logger
        logger = TradingLogger()
        print("[OK] Logger initialized")

        # Get component logger
        trading_logger = get_logger('trading.test')

        # Test different log levels
        trading_logger.debug("Debug message", extra={'test': True})
        trading_logger.info("Info message", extra={'component': 'test'})
        trading_logger.warning("Warning message", extra={'symbol': 'ES'})
        trading_logger.error("Error message (test)", extra={'error_code': 'TEST001'})
        print("[OK] Log levels tested")

        # Test trade logging
        logger.log_trade(
            action="BUY",
            symbol="ES",
            quantity=2,
            price=4502.50,
            order_id="TEST123",
            strategy_id="test_strategy"
        )
        print("[OK] Trade logging tested")

        # Test risk logging
        logger.log_risk_event(
            risk_type="POSITION_LIMIT",
            severity="warning",
            message="Position approaching limit",
            symbol="ES",
            position=4.0
        )
        print("[OK] Risk logging tested")

        # Test performance logging
        logger.log_performance(
            pnl=1250.50,
            trades=10,
            win_rate=0.60,
            sharpe_ratio=1.85
        )
        print("[OK] Performance logging tested")

        # Check log file exists
        log_file = Path(os.getenv('LOG_FILE', 'logs/trading_system.log'))
        if log_file.exists():
            print(f"[OK] Log file created: {log_file}")
            # Check file size
            size = log_file.stat().st_size
            print(f"  Log file size: {size:,} bytes")
        else:
            print("[WARNING] Log file not found")

        return True
    except Exception as e:
        print(f"[ERROR] Logging test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_exception_handling():
    """Test custom exceptions"""
    print("\n[EXCEPTIONS] Testing Exception Handling...")
    try:
        # Test different exception types
        exceptions_tested = 0

        try:
            raise ConnectionError(
                "Test connection error",
                host="localhost",
                port=5432,
                retry_count=3
            )
        except ConnectionError as e:
            print(f"[OK] ConnectionError caught: {e.message}")
            exceptions_tested += 1

        try:
            from core.exceptions import DataError
            raise DataError(
                "Test data error",
                symbol="ES",
                data_type="bar",
                timestamp=datetime.now()
            )
        except DataError as e:
            error_dict = e.to_dict()
            print(f"[OK] DataError caught and serialized: {error_dict['error_type']}")
            exceptions_tested += 1

        try:
            from core.exceptions import RiskError
            raise RiskError(
                "Test risk violation",
                risk_type="MAX_POSITION",
                current_value=6.0,
                threshold=5.0,
                symbol="ES"
            )
        except RiskError as e:
            print(f"[OK] RiskError caught: {e.details['risk_type']}")
            exceptions_tested += 1

        print(f"[OK] All {exceptions_tested} exception types tested successfully")
        return True

    except Exception as e:
        print(f"[ERROR] Exception handling test failed: {e}")
        return False


async def integration_test():
    """Full integration test of Phase 1 components"""
    print("\n[INTEGRATION] Running Integration Test...")
    try:
        # Initialize all components
        config = get_config()
        db = get_db_manager()
        event_bus = EventBus()
        logger = get_logger('integration_test')

        # Connect database
        await db.connect()

        # Create integrated handler
        async def integrated_handler(event: MarketDataEvent):
            # Log event
            logger.info(
                f"Processing market data for {event.symbol}",
                extra={'symbol': event.symbol, 'event_id': event.event_id}
            )

            # Store in database
            if event.bar:
                await db.insert_market_data(
                    symbol=event.symbol,
                    timestamp=event.bar.timestamp,
                    open_price=event.bar.open_price,  # Keep as Decimal
                    high_price=event.bar.high_price,  # Keep as Decimal
                    low_price=event.bar.low_price,    # Keep as Decimal
                    close_price=event.bar.close_price, # Keep as Decimal
                    volume=event.bar.volume
                )

        # Subscribe handler
        event_bus.subscribe(EventType.MARKET_DATA, integrated_handler)

        # Start event bus
        await event_bus.start()

        # Publish test event
        bar = MarketBar(
            symbol="ES",
            timestamp=datetime.now(),
            open_price=Decimal("4500.00"),
            high_price=Decimal("4510.00"),
            low_price=Decimal("4495.00"),
            close_price=Decimal("4508.00"),
            volume=25000
        )
        event = MarketDataEvent(symbol="ES", bar=bar)
        await event_bus.publish(event)

        # Wait for processing with proper synchronization
        await event_bus.wait_until_empty()

        # Poll database with timeout instead of fixed sleep
        max_retries = 10
        retry_delay = 0.1
        bars = None
        for i in range(max_retries):
            bars = await db.get_latest_bars("ES", limit=1)
            if bars and bars[0]['volume'] == 25000:
                break
            await asyncio.sleep(retry_delay)

        # Verify data was stored
        if bars and bars[0]['volume'] == 25000:
            print("[OK] Integration test successful: Event -> Handler -> Database")
        else:
            print("[ERROR] Integration test failed: Data not found in database")
            return False

        # Stop event bus
        await event_bus.stop()

        # Disconnect database
        await db.disconnect()

        return True

    except Exception as e:
        print(f"[ERROR] Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    print("=" * 60)
    print("[INFO] Phase 1 Infrastructure Validation")
    print("=" * 60)

    results = {
        'configuration': await test_configuration(),
        'database': await test_database_connection(),
        'events': await test_event_system(),
        'logging': await test_logging_system(),
        'exceptions': await test_exception_handling(),
        'integration': await integration_test()
    }

    # Summary
    print("\n" + "=" * 60)
    print("[SUMMARY] Test Results")
    print("=" * 60)

    passed = 0
    failed = 0
    for component, result in results.items():
        status = "[OK] PASSED" if result else "[ERROR] FAILED"
        print(f"{component.capitalize():15} {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print(f"Total: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n[SUCCESS] Phase 1 Infrastructure is fully operational!")
        print("\n[INFO] Next Steps:")
        print("1. Review log files for any warnings")
        print("2. Start Phase 2: IB API Integration")
        print("3. Begin implementing IB connection manager")
    else:
        print(f"\n[WARNING] {failed} test(s) failed. Please review and fix issues.")


if __name__ == "__main__":
    asyncio.run(main())