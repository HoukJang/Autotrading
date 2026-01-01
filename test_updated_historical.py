"""
Test updated historical data collection methods
Tests IBClient and HistoricalDataFetcher with date-based collection
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from database.connection import get_db_manager
from data.bar_storage import BarStorage
from data.historical import HistoricalDataFetcher


async def test_date_collection(fetcher: HistoricalDataFetcher, storage: BarStorage,
                               symbol: str, target_date: datetime):
    """Test data collection for a specific date"""
    print(f"\n{'='*70}")
    print(f"Testing: {target_date.strftime('%Y-%m-%d (%A)')}")
    print(f"{'='*70}")

    try:
        # Fetch data using updated method
        market_bars = await fetcher.fetch_bars_for_date(
            symbol=symbol,
            date=target_date,
            bar_size="1 min"
        )

        if not market_bars:
            print("   [ERROR] No data received!")
            return False

        print(f"   SUCCESS: Received {len(market_bars):,} bars")
        print(f"   First bar: {market_bars[0].timestamp}")
        print(f"   Last bar: {market_bars[-1].timestamp}")

        # Calculate trading hours
        trading_hours = len(market_bars) / 60
        print(f"   Trading hours: {trading_hours:.1f} hours")

        # Save to database
        saved = await storage.save_bars_bulk(market_bars)
        print(f"   Saved {saved:,} bars to database")

        return True

    except Exception as e:
        print(f"   [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Test updated historical data methods"""
    print("=" * 70)
    print("Testing Updated Historical Data Collection Methods")
    print("=" * 70)

    symbol = "ES"

    # Test dates
    test_dates = [
        datetime(2025, 10, 5),   # Sunday (6 hours)
        datetime(2025, 10, 6),   # Monday (23 hours)
        datetime(2025, 10, 7),   # Tuesday (23 hours)
        datetime(2025, 10, 10),  # Friday (23 hours)
    ]

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    db = get_db_manager()
    storage = BarStorage(db)
    fetcher = HistoricalDataFetcher(ib_client)

    try:
        # Connect
        print("\n1. Connecting to database...")
        await db.connect()
        print("   Connected")

        print("\n2. Connecting to IB API...")
        await ib_client.connect()
        print("   Connected")

        # Test each date
        print("\n3. Testing date-based collection:")
        results = []
        for target_date in test_dates:
            success = await test_date_collection(fetcher, storage, symbol, target_date)
            results.append((target_date, success))
            await asyncio.sleep(2)  # Rate limiting

        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        for target_date, success in results:
            status = "[OK]" if success else "[FAILED]"
            day_name = target_date.strftime('%A')
            print(f"{status} {target_date.strftime('%Y-%m-%d')} ({day_name})")

        success_count = sum(1 for _, success in results if success)
        print(f"\nTotal: {success_count}/{len(results)} tests passed")

        # Fetch stats
        stats = fetcher.get_stats()
        print(f"\nFetcher Stats:")
        print(f"  Bars fetched: {stats['bars_fetched']:,}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Success rate: {stats['success_rate']:.1%}")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nDisconnecting...")
        await ib_client.disconnect()
        await db.disconnect()
        print("Done")


if __name__ == "__main__":
    asyncio.run(main())
