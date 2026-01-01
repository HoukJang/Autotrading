"""
Historical Data Collection Script
Collects 1-minute bar data from IB API day by day and stores in PostgreSQL

Strategy:
- Request 1 day at a time to avoid IB API timeout
- Store in database with duplicate handling
- Progress tracking and resume capability
- Rate limiting to respect IB API limits
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from broker.contracts import ContractFactory
from core.event_bus import EventBus
from database.connection import get_db_manager
from data.bar_storage import BarStorage
from data.historical import HistoricalDataFetcher
from data.data_validator import DataValidator
from ib_async import Future


class HistoricalDataCollector:
    """Collects historical data day by day"""

    def __init__(self, symbol: str = "ES"):
        self.symbol = symbol
        self.event_bus = EventBus()
        self.ib_client = IBClient(self.event_bus)
        self.db = get_db_manager()
        self.storage = BarStorage(self.db)
        self.fetcher = HistoricalDataFetcher(self.ib_client)
        self.validator = DataValidator(strict_mode=False)

        # Statistics
        self.days_processed = 0
        self.days_failed = 0
        self.total_bars_saved = 0
        self.total_bars_skipped = 0

    async def initialize(self):
        """Initialize all components"""
        print("=" * 70)
        print("Historical Data Collector - 1 Year Collection")
        print("=" * 70)

        # Connect to database
        print("\n[1/3] Connecting to database...")
        await self.db.connect()
        print("      Database connected")

        # Connect to IB API
        print("\n[2/3] Connecting to IB API...")
        connected = await self.ib_client.connect()
        if not connected:
            raise Exception("Failed to connect to IB API")
        print("      IB API connected")

        # Get contract details
        print(f"\n[3/3] Qualifying {self.symbol} contract...")
        es_contract = Future(symbol=self.symbol, exchange='CME', currency='USD')
        contract_details = await self.ib_client._ib.reqContractDetailsAsync(es_contract)

        if not contract_details:
            raise Exception(f"Could not get {self.symbol} contract details")

        # Use front month
        contracts = [cd.contract for cd in contract_details]
        contracts.sort(key=lambda c: c.lastTradeDateOrContractMonth)
        self.contract = contracts[0]

        print(f"      Contract: {self.contract.localSymbol}")
        print(f"      Expiry: {self.contract.lastTradeDateOrContractMonth}")
        print("\n" + "=" * 70)

    async def collect_day(self, target_date: datetime) -> Tuple[int, int]:
        """
        Collect data for a single day

        Returns:
            (bars_saved, bars_skipped)
        """
        date_str = target_date.strftime('%Y-%m-%d')

        try:
            # Check if we already have data for this day
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            existing_bars = await self.storage.get_bars_range(
                self.symbol, start_of_day, end_of_day
            )

            if existing_bars and len(existing_bars) > 100:
                print(f"  {date_str}: SKIP ({len(existing_bars)} bars already exist)")
                return 0, len(existing_bars)

            # Request data from IB
            # Use empty string to get current time, then use duration to go back
            # This is more reliable than specifying exact date/time
            bars = await self.ib_client._ib.reqHistoricalDataAsync(
                self.contract,
                endDateTime='',  # Empty = current time
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False,
                formatDate=1
            )

            if not bars:
                print(f"  {date_str}: FAIL (no data returned)")
                return 0, 0

            # Filter bars for this specific day only
            day_bars = [
                bar for bar in bars
                if start_of_day <= bar.date < end_of_day
            ]

            if not day_bars:
                print(f"  {date_str}: SKIP (no bars in range)")
                return 0, 0

            # Convert to MarketBar and save
            from core.events import MarketBar
            from decimal import Decimal

            market_bars = []
            for ib_bar in day_bars:
                try:
                    market_bar = MarketBar(
                        symbol=self.symbol,
                        timestamp=ib_bar.date,
                        open_price=Decimal(str(ib_bar.open)),
                        high_price=Decimal(str(ib_bar.high)),
                        low_price=Decimal(str(ib_bar.low)),
                        close_price=Decimal(str(ib_bar.close)),
                        volume=int(ib_bar.volume),
                        vwap=Decimal(str(ib_bar.average)) if ib_bar.average > 0 else None,
                        tick_count=int(ib_bar.barCount) if hasattr(ib_bar, 'barCount') else None
                    )

                    # Validate
                    is_valid, errors = self.validator.validate_bar(market_bar)
                    if is_valid:
                        market_bars.append(market_bar)
                    else:
                        print(f"    Invalid bar at {ib_bar.date}: {errors}")

                except Exception as e:
                    print(f"    Failed to convert bar: {e}")

            # Bulk save
            if market_bars:
                saved = await self.storage.save_bars_bulk(market_bars)
                print(f"  {date_str}: OK ({saved} bars saved)")
                return saved, 0
            else:
                print(f"  {date_str}: FAIL (no valid bars)")
                return 0, 0

        except Exception as e:
            print(f"  {date_str}: ERROR ({e})")
            return 0, 0

    async def collect_period(
        self,
        days_back: int = 365,
        rate_limit_seconds: float = 1.0
    ):
        """
        Collect data for a period of days

        Args:
            days_back: Number of days back to collect
            rate_limit_seconds: Delay between requests
        """
        print(f"\nCollection Parameters:")
        print(f"  Symbol: {self.symbol}")
        print(f"  Days back: {days_back}")
        print(f"  Rate limit: {rate_limit_seconds}s between requests")
        print(f"  Total requests: {days_back}")
        print(f"  Estimated time: {days_back * rate_limit_seconds / 60:.1f} minutes")
        print("\n" + "=" * 70)
        print("Starting collection (newest to oldest)...\n")

        # Start from 2 days ago to avoid "today" which may have no complete data
        end_date = datetime.now() - timedelta(days=2)
        start_date = end_date - timedelta(days=days_back)

        # Collect day by day, newest first (more likely to succeed)
        current_date = end_date

        for day_num in range(days_back):
            # Process this day
            bars_saved, bars_skipped = await self.collect_day(current_date)

            # Update statistics
            if bars_saved > 0 or bars_skipped > 0:
                self.days_processed += 1
                self.total_bars_saved += bars_saved
                self.total_bars_skipped += bars_skipped
            else:
                self.days_failed += 1

            # Move to previous day
            current_date -= timedelta(days=1)

            # Rate limiting (except for last request)
            if day_num < days_back - 1:
                await asyncio.sleep(rate_limit_seconds)

            # Progress update every 10 days
            if (day_num + 1) % 10 == 0:
                progress = (day_num + 1) / days_back * 100
                print(f"\n  Progress: {progress:.1f}% ({day_num + 1}/{days_back} days)")
                print(f"  Saved: {self.total_bars_saved:,} bars")
                print(f"  Skipped: {self.total_bars_skipped:,} bars")
                print(f"  Failed: {self.days_failed} days\n")

    async def shutdown(self):
        """Cleanup and disconnect"""
        print("\n" + "=" * 70)
        print("Shutting down...")

        await self.ib_client.disconnect()
        await self.db.disconnect()

        print("Disconnected from IB API and database")

    async def run(self, days_back: int = 365):
        """Main execution flow"""
        try:
            # Initialize
            await self.initialize()

            # Collect data
            await self.collect_period(days_back=days_back)

            # Summary
            print("\n" + "=" * 70)
            print("COLLECTION SUMMARY")
            print("=" * 70)
            print(f"\nDays processed: {self.days_processed}")
            print(f"Days failed: {self.days_failed}")
            print(f"Total bars saved: {self.total_bars_saved:,}")
            print(f"Total bars skipped: {self.total_bars_skipped:,}")
            print(f"\nDatabase table: market_data_1min")
            print(f"Symbol: {self.symbol}")

            if self.total_bars_saved > 0:
                avg_bars_per_day = self.total_bars_saved / max(self.days_processed, 1)
                print(f"Average bars per day: {avg_bars_per_day:.0f}")

            # Verification query
            print("\nTo verify data:")
            print(f"  SELECT COUNT(*), MIN(timestamp), MAX(timestamp)")
            print(f"  FROM market_data_1min WHERE symbol = '{self.symbol}';")

            print("\n" + "=" * 70)

        except KeyboardInterrupt:
            print("\n\nCollection interrupted by user")

        except Exception as e:
            print(f"\n\nFatal error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.shutdown()


async def main():
    """Entry point"""
    print("\n" + "=" * 70)
    print("IB Historical Data Collector")
    print("=" * 70)
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure PostgreSQL is running")
    print("  - Check .env file has correct DB credentials")
    print("  - This will take ~6 minutes for 365 days (1s per day)")
    print("\nPress Ctrl+C to stop at any time")
    print("=" * 70)

    # Configuration
    SYMBOL = "ES"  # E-mini S&P 500
    DAYS_BACK = 365  # 1 year

    # Run collector
    collector = HistoricalDataCollector(symbol=SYMBOL)
    await collector.run(days_back=DAYS_BACK)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
