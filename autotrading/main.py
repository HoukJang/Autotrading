#!/usr/bin/env python3
"""
Main Entry Point for Automated Trading System

Run from the project root with:
    python -m autotrading.main
or:
    python autotrading/main.py
"""

import asyncio
import sys
import argparse
import logging
from pathlib import Path

# Ensure autotrading package is importable when running directly
if __name__ == "__main__":
    _project_root = Path(__file__).parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

from autotrading.core import EventBus, TradingLogger, get_logger
from autotrading.config import get_config
from autotrading.database import get_db_manager


async def initialize_system():
    """Initialize all system components"""
    logger = get_logger('main')

    try:
        # Load configuration
        config = get_config()
        config.validate()
        logger.info(f"Configuration loaded: {config.environment} mode")

        # Initialize database
        db = get_db_manager()
        await db.connect()
        logger.info("Database connected")

        # Initialize event bus
        event_bus = EventBus()
        await event_bus.start()
        logger.info("Event bus started")

        return config, db, event_bus

    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise


async def shutdown_system(db, event_bus):
    """Gracefully shutdown system components"""
    logger = get_logger('main')

    try:
        # Stop event bus
        if event_bus:
            await event_bus.stop()
            logger.info("Event bus stopped")

        # Disconnect database
        if db:
            await db.disconnect()
            logger.info("Database disconnected")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


async def main(args):
    """Main application entry point"""
    print("=" * 60)
    print("Automated Futures Trading System")
    print("=" * 60)

    # Initialize logging
    logger = TradingLogger()
    main_logger = get_logger('main')

    # Initialize components
    db = None
    event_bus = None

    try:
        # Initialize system
        config, db, event_bus = await initialize_system()

        # Print configuration
        if args.verbose:
            config.print_config()

        # Log system start
        await db.log_event(
            event_type="SYSTEM_START",
            severity="INFO",
            component="main",
            message="Trading system started successfully"
        )

        print("\n[OK] System initialized successfully!")
        print(f"Environment: {config.environment}")
        print(f"Database: {config.database.name}")
        print(f"Broker: {config.broker.connection_name}")

        # Main application loop
        if not args.test:
            print("\n[INFO] Trading system is running...")
            print("Press Ctrl+C to stop")

            try:
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)

            except KeyboardInterrupt:
                print("\n[INFO] Shutdown requested...")
        else:
            print("\n[INFO] Test mode - shutting down...")

    except Exception as e:
        main_logger.error(f"System error: {e}", exc_info=True)
        print(f"\n[ERROR] System error: {e}")
        return 1

    finally:
        # Shutdown system
        await shutdown_system(db, event_bus)
        print("[INFO] System shutdown complete")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Trading System")
    parser.add_argument(
        "--env",
        choices=["development", "production"],
        default="development",
        help="Environment to run in"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (initialize and exit)"
    )

    args = parser.parse_args()

    # Set environment
    import os
    os.environ["ENVIRONMENT"] = args.env

    # Run main application
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)