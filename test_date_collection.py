"""
Test collecting data for specific dates
Tests how far back we can go with IB API
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from data.historical import HistoricalDataFetcher


async def main():
    """Test specific dates"""
    print("=" * 70)
    print("Testing IB Data Availability for Specific Dates")
    print("=" * 70)

    event_bus = EventBus()
    ib_client = IBClient(event_bus)

    try:
        # Connect
        print("\nConnecting to IB API...")
        await ib_client.connect()
        print("Connected\n")

        fetcher = HistoricalDataFetcher(ib_client)

        # Test dates (going backwards from recent)
        test_dates = [
            datetime(2025, 10, 11),  # 2 days ago
            datetime(2025, 10, 1),   # ~12 days ago
            datetime(2025, 9, 13),   # ~1 month ago
            datetime(2025, 8, 13),   # ~2 months ago
            datetime(2025, 7, 13),   # ~3 months ago
            datetime(2025, 6, 13),   # ~4 months ago
            datetime(2025, 1, 13),   # ~9 months ago
            datetime(2024, 10, 13),  # ~1 year ago
        ]

        print("Testing dates:")
        print("-" * 70)

        results = []

        for test_date in test_dates:
            date_str = test_date.strftime('%Y-%m-%d')
            try:
                print(f"\n{date_str}: ", end="", flush=True)

                # Try to fetch data for this date
                bars = await fetcher.fetch_bars_for_date(
                    symbol="ES",
                    date=test_date,
                    bar_size="1 min"
                )

                if bars and len(bars) > 0:
                    first = bars[0].timestamp
                    last = bars[-1].timestamp
                    result = {
                        'date': date_str,
                        'success': True,
                        'bars': len(bars),
                        'first': first,
                        'last': last
                    }
                    print(f"OK ({len(bars)} bars, {first} to {last})")
                else:
                    result = {
                        'date': date_str,
                        'success': False,
                        'error': 'No data'
                    }
                    print(f"FAIL (no data)")

                results.append(result)

                # Small delay to avoid rate limiting
                await asyncio.sleep(2)

            except Exception as e:
                result = {
                    'date': date_str,
                    'success': False,
                    'error': str(e)
                }
                print(f"ERROR: {e}")
                results.append(result)
                await asyncio.sleep(2)

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        successful = [r for r in results if r.get('success')]
        failed = [r for r in results if not r.get('success')]

        if successful:
            print(f"\nSuccessful: {len(successful)}/{len(results)}")
            for r in successful:
                print(f"  {r['date']}: {r['bars']} bars")

            # Find oldest successful date
            oldest = successful[-1]
            print(f"\nOldest successful date: {oldest['date']}")
            print(f"Total bars: {oldest['bars']}")

        if failed:
            print(f"\nFailed: {len(failed)}/{len(results)}")
            for r in failed:
                error = r.get('error', 'Unknown')
                print(f"  {r['date']}: {error}")

        print("\n" + "=" * 70)

    finally:
        print("\nDisconnecting...")
        await ib_client.disconnect()
        print("Done")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
