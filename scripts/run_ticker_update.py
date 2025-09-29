#!/usr/bin/env python3
"""
Autotrading Ticker Update Script

Production-ready script for updating ticker information with integrated delisting detection.
Supports batch processing, comprehensive logging, and error handling.

Usage:
    python scripts/run_ticker_update.py [options]

Examples:
    # Basic update with default settings
    python scripts/run_ticker_update.py

    # Custom batch size and verbose output
    python scripts/run_ticker_update.py --batch-size 100 --verbose

    # Continuous monitoring mode
    python scripts/run_ticker_update.py --continuous --interval 3600

    # Dry run mode (simulation)
    python scripts/run_ticker_update.py --dry-run --verbose
"""

import argparse
import asyncio
import logging
import sys
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import json

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from autotrading.core.ticker_manager import run_ticker_update, BatchResult
    from autotrading.core.status_handler import StatusHandler, ComponentState
    from autotrading.database.connection import create_db_pool, close_db_pool
    from autotrading.config.settings import settings
except ImportError as e:
    print(f"Error importing autotrading modules: {e}")
    print("Make sure you're running from the project root and dependencies are installed.")
    sys.exit(1)


class TickerUpdateRunner:
    """Production-ready ticker update orchestrator"""

    def __init__(self, args: argparse.Namespace):
        """Initialize runner with CLI arguments"""
        self.args = args
        self.logger = self._setup_logging()
        self.db_pool: Optional[Any] = None
        self.status_handler: Optional[StatusHandler] = None
        self.running = True
        self.stats = {
            "runs_completed": 0,
            "total_processed": 0,
            "total_updated": 0,
            "total_errors": 0,
            "total_deactivated": 0,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "last_run": None
        }

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logging(self) -> logging.Logger:
        """Configure logging with appropriate level and format"""
        log_level = logging.DEBUG if self.args.verbose else logging.INFO

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # File handler if specified
        if self.args.log_file:
            file_handler = logging.FileHandler(self.args.log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        return logging.getLogger(__name__)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully"""
        if hasattr(self, '_first_interrupt'):
            # 두 번째 Ctrl+C는 즉시 종료
            print("\nForce quit...")
            import os
            os._exit(1)
        else:
            self._first_interrupt = True
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            print("\nStopping... (Press Ctrl+C again to force quit)")
            self.running = False

    async def _validate_configuration(self) -> bool:
        """Validate system configuration before starting"""
        try:
            self.logger.info("Validating configuration...")

            # Check required settings
            settings.validate_required_config()

            # Check database connection
            if not settings.database_url:
                self.logger.error("Database URL not configured")
                return False

            # Check API configuration
            if not settings.schwab_app_key or not settings.schwab_app_secret:
                self.logger.error("Schwab API credentials not configured")
                return False

            self.logger.info("Configuration validation successful")
            return True

        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            return False

    async def _initialize_database(self) -> bool:
        """Initialize database connection pool"""
        try:
            self.logger.info("Initializing database connection pool...")

            self.db_pool = await create_db_pool(
                settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )

            # Initialize status handler
            self.status_handler = StatusHandler(self.db_pool)

            # Status will be managed by TickerManager itself
            # No need to create separate script status

            self.logger.info("Database initialization successful")
            return True

        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            return False

    async def _cleanup(self) -> None:
        """Cleanup resources"""
        try:
            # TickerManager handles its own status cleanup
            pass

            if self.db_pool:
                await close_db_pool(self.db_pool)

            self.logger.info("Cleanup completed")

        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

    def _update_stats(self, result: BatchResult) -> None:
        """Update running statistics"""
        self.stats["runs_completed"] += 1
        self.stats["total_processed"] += result.processed_count
        self.stats["total_updated"] += result.success_count
        self.stats["total_errors"] += result.error_count
        self.stats["total_deactivated"] += result.deactivated_count
        self.stats["last_run"] = datetime.now(timezone.utc).isoformat()

    def _format_result(self, result: BatchResult) -> str:
        """Format batch result for logging"""
        return (
            f"Processed: {result.processed_count}, "
            f"Updated: {result.success_count}, "
            f"Errors: {result.error_count}, "
            f"Deactivated: {result.deactivated_count}, "
            f"Time: {result.processing_time:.2f}s"
        )

    def _show_progress(self, current: int, total: int, result: BatchResult):
        """Show progress bar with current status"""
        if total == 0:
            return

        progress = current / total
        bar_length = 40
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)

        percent = progress * 100
        status = f"[{bar}] {percent:.1f}% ({current}/{total}) | "
        status += f"✓{result.success_count} ❌{result.error_count} ⚠️{result.deactivated_count}"

        print(f"\r{status}", end='', flush=True)

    def _format_stats(self) -> str:
        """Format cumulative statistics"""
        start_time = datetime.fromisoformat(self.stats["start_time"].replace('Z', '+00:00'))
        runtime = datetime.now(timezone.utc) - start_time
        return (
            f"Runtime: {runtime}, "
            f"Runs: {self.stats['runs_completed']}, "
            f"Total Processed: {self.stats['total_processed']}, "
            f"Total Updated: {self.stats['total_updated']}, "
            f"Total Errors: {self.stats['total_errors']}, "
            f"Total Deactivated: {self.stats['total_deactivated']}"
        )

    async def _run_single_update(self) -> BatchResult:
        """Execute single ticker update batch"""
        self.logger.info(f"Starting ticker update batch (size: {self.args.batch_size})")

        if self.args.dry_run:
            self.logger.info("DRY RUN MODE - No actual updates will be performed")
            # Simulate a result for dry run
            await asyncio.sleep(1)  # Simulate processing time
            return BatchResult(
                processed_count=self.args.batch_size,
                success_count=self.args.batch_size - 2,
                error_count=2,
                deactivated_count=0,
                errors=["Simulated error 1", "Simulated error 2"],
                processing_time=1.0
            )

        try:
            result = await run_ticker_update(
                batch_size=self.args.batch_size,
                status_handler=self.status_handler
            )

            self.logger.info(f"Batch completed: {self._format_result(result)}")

            if result.errors and self.args.verbose:
                for error in result.errors:
                    self.logger.warning(f"Batch error: {error}")

            return result

        except Exception as e:
            self.logger.error(f"Ticker update batch failed: {e}")
            # Return error result
            return BatchResult(
                processed_count=0,
                success_count=0,
                error_count=1,
                deactivated_count=0,
                errors=[str(e)],
                processing_time=0.0
            )

    async def run_once(self) -> int:
        """Run ticker update once and exit"""
        try:
            if not await self._validate_configuration():
                return 1

            if not await self._initialize_database():
                return 1

            result = await self._run_single_update()
            self._update_stats(result)

            # Print summary
            print(f"\n{'='*60}")
            print("TICKER UPDATE SUMMARY")
            print(f"{'='*60}")
            print(f"Batch Result: {self._format_result(result)}")

            if result.errors:
                print(f"\nErrors encountered:")
                for error in result.errors:
                    print(f"  - {error}")

            # Exit code based on result
            if result.error_count > 0 and result.success_count == 0:
                return 1  # Complete failure
            elif result.error_count > result.success_count:
                return 2  # Partial failure
            else:
                return 0  # Success

        except Exception as e:
            self.logger.error(f"Script execution failed: {e}")
            return 1
        finally:
            await self._cleanup()

    async def run_continuous(self) -> int:
        """Run ticker updates continuously"""
        try:
            if not await self._validate_configuration():
                return 1

            if not await self._initialize_database():
                return 1

            self.logger.info(f"Starting continuous mode (interval: {self.args.interval}s)")

            while self.running:
                try:
                    result = await self._run_single_update()
                    self._update_stats(result)

                    if self.args.verbose:
                        self.logger.info(f"Cumulative stats: {self._format_stats()}")

                    # TickerManager updates its own status during execution
                    # No need for script to update status separately

                    # Wait for next interval or exit if stopped
                    for _ in range(self.args.interval):
                        if not self.running:
                            break
                        await asyncio.sleep(1)

                except Exception as e:
                    self.logger.error(f"Error in continuous loop: {e}")
                    if not self.running:
                        break

                    # Wait before retry
                    self.logger.info(f"Waiting {self.args.interval}s before retry...")
                    await asyncio.sleep(self.args.interval)

            self.logger.info("Continuous mode stopped")
            print(f"\n{'='*60}")
            print("FINAL STATISTICS")
            print(f"{'='*60}")
            print(self._format_stats())

            return 0

        except Exception as e:
            self.logger.error(f"Continuous mode failed: {e}")
            return 1
        finally:
            await self._cleanup()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Autotrading Ticker Update Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic update
    python scripts/run_ticker_update.py

    # Large batch with verbose output
    python scripts/run_ticker_update.py --batch-size 200 --verbose

    # Continuous monitoring
    python scripts/run_ticker_update.py --continuous --interval 1800

    # Test run without making changes
    python scripts/run_ticker_update.py --dry-run --verbose
        """
    )

    # Batch processing options
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,  # 0 = process all
        metavar="N",
        help="Number of tickers to process per batch (default: 0 = all tickers)"
    )

    # Execution modes
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously with specified interval"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        metavar="SECONDS",
        help="Interval between runs in continuous mode (default: 3600)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without making actual changes"
    )

    # Logging options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output"
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        metavar="PATH",
        help="Write logs to specified file"
    )

    # Configuration overrides
    parser.add_argument(
        "--config-check",
        action="store_true",
        help="Check configuration and exit"
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point"""
    args = parse_arguments()

    # Import os here for getpid if needed
    import os
    globals()['os'] = os

    # Configuration check mode
    if args.config_check:
        try:
            settings.validate_required_config()
            config_status = settings.get_auth_config_status()

            print("Configuration Status:")
            print(f"  Schwab API: {'OK' if config_status['schwab_configured'] else 'MISSING'}")
            print(f"  Database: {'OK' if config_status['database_configured'] else 'MISSING'}")
            print(f"  Redis: {'OK' if config_status['redis_configured'] else 'MISSING'}")
            print(f"  Config Source: {config_status['config_source']}")

            return 0 if all([
                config_status['schwab_configured'],
                config_status['database_configured']
            ]) else 1

        except Exception as e:
            print(f"Configuration error: {e}")
            return 1

    # Validate arguments
    if args.batch_size < 0:
        print("Error: batch-size must be non-negative (0 = all tickers)", file=sys.stderr)
        return 1

    if args.continuous and args.interval <= 0:
        print("Error: interval must be positive for continuous mode", file=sys.stderr)
        return 1

    # Run the script
    runner = TickerUpdateRunner(args)

    try:
        if args.continuous:
            return await runner.run_continuous()
        else:
            return await runner.run_once()
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)