"""
Collect data for September 14-20, 2025
Uses ESZ2025 contract with specific date range
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from database.connection import get_db_manager
from data.bar_storage import BarStorage
from core.events import MarketBar
from broker.contracts import ContractFactory


async def collect_date_range(
    ib_client: IBClient,
    storage: BarStorage,
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    contract_month: str
):
    """Collect data for a date range"""

    # Calculate duration
    delta = end_date - start_date
    days = delta.days + 1

    print(f"\nCollecting {days} days of data...")
    print(f"  Start: {start_date.strftime('%Y-%m-%d')}")
    print(f"  End: {end_date.strftime('%Y-%m-%d')}")
    print(f"  Contract: {contract_month}")

    # Request historical data
    # Use endDateTime for specific date range
    end_datetime_str = end_date.strftime('%Y%m%d 23:59:59 US/Eastern')
    duration_str = f"{days} D"

    print(f"\n  Requesting from IB API...")
    print(f"    Duration: {duration_str}")
    print(f"    End time: {end_datetime_str}")

    # Create contract
    futures_contract = ContractFactory.create_futures(symbol, expiry=contract_month)
    contract = futures_contract.to_ib_contract()

    # Request data directly
    bars = await ib_client._ib.reqHistoricalDataAsync(
        contract,
        endDateTime=end_datetime_str,
        durationStr=duration_str,
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1
    )

    if not bars:
        print("    No data received!")
        return 0

    print(f"    Received {len(bars):,} bars")
    print(f"    First: {bars[0].date}")
    print(f"    Last: {bars[-1].date}")

    # Convert to MarketBar
    print(f"\n  Converting bars...")
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
            print(f"    Warning: Failed to convert bar at {ib_bar.date}: {e}")

    print(f"    Converted {len(market_bars):,} bars")

    # Save to database
    print(f"\n  Saving to database...")
    saved = await storage.save_bars_bulk(market_bars)
    print(f"    Saved {saved:,} bars")

    return saved


async def main():
    """Main execution"""
    print("=" * 70)
    print("September 14-20, 2025 Data Collection")
    print("=" * 70)

    symbol = "ES"
    contract_month = "202512"  # ESZ2025

    # Date range
    start_date = datetime(2025, 9, 14)
    end_date = datetime(2025, 9, 20)

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    db = get_db_manager()
    storage = BarStorage(db)

    try:
        # Connect to database
        print("\n1. Connecting to database...")
        await db.connect()
        print("   Connected")

        # Connect to IB
        print("\n2. Connecting to IB API...")
        await ib_client.connect()
        print("   Connected")

        # Collect data
        print("\n3. Collecting data...")
        saved = await collect_date_range(
            ib_client, storage, symbol,
            start_date, end_date, contract_month
        )

        # Summary
        print("\n" + "=" * 70)
        print("COLLECTION COMPLETE")
        print("=" * 70)
        print(f"\nSymbol: {symbol}")
        print(f"Contract: {contract_month} (ESZ2025)")
        print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print(f"Bars saved: {saved:,}")

        # Show total in DB
        query = """
            SELECT COUNT(*) as total,
                   MIN(timestamp) as first,
                   MAX(timestamp) as last
            FROM market_data_1min
            WHERE symbol = 'ES'
        """
        result = await db.fetchrow(query)

        if result:
            print(f"\nTotal in database:")
            print(f"  Total bars: {result['total']:,}")
            print(f"  First bar: {result['first']}")
            print(f"  Last bar: {result['last']}")

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
