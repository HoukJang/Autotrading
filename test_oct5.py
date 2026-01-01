"""
Test October 5, 2025 data collection
Using correct date format (no timezone)
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
from core.events import MarketBar
from broker.contracts import ContractFactory


async def main():
    """Test October 5 data"""
    print("=" * 70)
    print("Testing October 5, 2025 Data Collection")
    print("=" * 70)

    target_date = datetime(2025, 10, 5)
    symbol = "ES"
    contract_month = "202512"  # ESZ2025

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    db = get_db_manager()
    storage = BarStorage(db)

    try:
        # Connect
        print("\n1. Connecting to database...")
        await db.connect()
        print("   Connected")

        print("\n2. Connecting to IB API...")
        await ib_client.connect()
        print("   Connected")

        # Prepare request
        print(f"\n3. Request details:")
        print(f"   Target date: {target_date.strftime('%Y-%m-%d')}")
        print(f"   Contract: {contract_month} (ESZ2025)")

        # CORRECT FORMAT: No timezone!
        end_datetime_str = target_date.strftime('%Y%m%d 23:59:59')
        print(f"   End DateTime: '{end_datetime_str}'")
        print(f"   Duration: 1 D")

        # Request data
        print(f"\n4. Requesting data...")

        futures_contract = ContractFactory.create_futures(symbol, expiry=contract_month)
        contract = futures_contract.to_ib_contract()

        bars = await ib_client._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime_str,
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1
        )

        if not bars:
            print("   [ERROR] No data received!")
            return

        print(f"   SUCCESS: Received {len(bars):,} bars")
        print(f"\n5. Data range:")
        print(f"   First bar: {bars[0].date}")
        print(f"   Last bar: {bars[-1].date}")

        # Verify dates
        first_date = bars[0].date.date()
        last_date = bars[-1].date.date()

        print(f"\n6. Date verification:")
        print(f"   Requested: {target_date.date()}")
        print(f"   First bar date: {first_date}")
        print(f"   Last bar date: {last_date}")

        if first_date == target_date.date() or last_date == target_date.date():
            print("   [OK] Dates match target date!")
        else:
            print(f"   [WARNING] Dates don't match target!")
            print(f"   Expected: {target_date.date()}")
            print(f"   Got: {first_date} to {last_date}")

        # Sample bars
        print(f"\n7. Sample bars (first 5):")
        for i, bar in enumerate(bars[:5]):
            print(f"   {bar.date} | O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}")

        print(f"\n   Sample bars (last 5):")
        for i, bar in enumerate(bars[-5:]):
            print(f"   {bar.date} | O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}")

        # Convert and save
        print(f"\n8. Converting to MarketBar format...")
        market_bars = []
        for ib_bar in bars:
            try:
                market_bar = MarketBar(
                    symbol=symbol,
                    timestamp=ib_bar.date,
                    open_price=Decimal(str(ib_bar.open)),
                    high_price=Decimal(str(ib_bar.high)),
                    low_price=Decimal(str(ib_bar.low)),
                    close_price=Decimal(str(ib_bar.close)),
                    volume=int(ib_bar.volume),
                    vwap=Decimal(str(ib_bar.average)) if ib_bar.average > 0 else None,
                    tick_count=int(ib_bar.barCount) if hasattr(ib_bar, 'barCount') else None
                )
                market_bars.append(market_bar)
            except Exception as e:
                print(f"   Warning: Failed to convert bar: {e}")

        print(f"   Converted {len(market_bars):,} bars")

        # Save to database
        print(f"\n9. Saving to database...")
        saved = await storage.save_bars_bulk(market_bars)
        print(f"   Saved {saved:,} bars (duplicates updated)")

        # Verify in DB
        print(f"\n10. Verifying in database...")
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
