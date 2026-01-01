"""
Test September 30, 2025 data collection
Using HistoricalDataFetcher and BarStorage components
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from database.connection import get_db_manager
from data.bar_storage import BarStorage
from data.historical import HistoricalDataFetcher


async def main():
    """Test September 30 data collection using HistoricalDataFetcher"""
    print("=" * 70)
    print("Testing September 30, 2025 Data Collection")
    print("=" * 70)

    target_date = datetime(2025, 9, 30)
    symbol = "ES"

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

        # Show contract info with rollover awareness
        print(f"\n3. Contract information (with rollover awareness):")
        contract = fetcher.get_contract_for_date(symbol, target_date)
        local_symbol = fetcher.get_local_symbol_for_date(symbol, target_date)
        print(f"   Date: {target_date.strftime('%Y-%m-%d')}")
        print(f"   Auto-selected contract: {contract} ({local_symbol})")
        print(f"   Note: System automatically handles rollover for expired contracts")

        # Fetch data with automatic rollover handling
        print(f"\n4. Fetching data for {target_date.strftime('%Y-%m-%d')} (automatic rollover)...")
        market_bars = await fetcher.fetch_bars_for_date(
            symbol=symbol,
            date=target_date,
            bar_size="1 min"
            # No contract_month override needed - automatic rollover!
        )

        if not market_bars:
            print("   [ERROR] No data received!")
            return

        print(f"   SUCCESS: Received {len(market_bars):,} bars")

        # Data range
        print(f"\n5. Data range:")
        print(f"   First bar: {market_bars[0].timestamp}")
        print(f"   Last bar: {market_bars[-1].timestamp}")

        # Trading hours
        trading_hours = len(market_bars) / 60
        print(f"   Trading hours: {trading_hours:.1f} hours")

        # Date verification
        first_date = market_bars[0].timestamp.date()
        last_date = market_bars[-1].timestamp.date()

        print(f"\n6. Date verification:")
        print(f"   Requested: {target_date.date()}")
        print(f"   First bar date: {first_date}")
        print(f"   Last bar date: {last_date}")

        if first_date == target_date.date() or last_date == target_date.date():
            print("   [OK] Dates match target date!")
        else:
            print(f"   [WARNING] Dates don't match target!")

        # Sample bars
        print(f"\n7. Sample bars (first 5):")
        for bar in market_bars[:5]:
            print(f"   {bar.timestamp} | O:{bar.open_price} H:{bar.high_price} "
                  f"L:{bar.low_price} C:{bar.close_price} V:{bar.volume}")

        print(f"\n   Sample bars (last 5):")
        for bar in market_bars[-5:]:
            print(f"   {bar.timestamp} | O:{bar.open_price} H:{bar.high_price} "
                  f"L:{bar.low_price} C:{bar.close_price} V:{bar.volume}")

        # Save to database using BarStorage
        print(f"\n8. Saving to database...")
        saved = await storage.save_bars_bulk(market_bars)
        print(f"   Saved {saved:,} bars (duplicates updated)")

        # Verify in DB
        print(f"\n9. Verifying in database...")
        query = """
            SELECT COUNT(*) as count,
                   MIN(timestamp) as first,
                   MAX(timestamp) as last
            FROM market_data_1min
            WHERE symbol = 'ES'
              AND DATE(timestamp) = $1
        """
        result = await db.fetchrow(query, target_date.date())

        if result and result['count'] > 0:
            print(f"    [OK] Found {result['count']:,} bars for {target_date.date()} in DB")
            print(f"    Range: {result['first']} to {result['last']}")
        else:
            print(f"    [WARNING] No data found in DB for {target_date.date()}")

        # Statistics
        print(f"\n10. Statistics:")
        fetcher_stats = fetcher.get_stats()
        storage_stats = storage.get_stats()
        print(f"    Fetcher: {fetcher_stats['bars_fetched']} bars, "
              f"{fetcher_stats['success_rate']:.1%} success rate")
        print(f"    Storage: {storage_stats['bars_saved']} saved, "
              f"{storage_stats['success_rate']:.1%} success rate")

        print("\n" + "=" * 70)
        print("COLLECTION COMPLETE")
        print("=" * 70)

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
