"""
Simple Historical Data Collection
Collects maximum available data (1 month) from IB and stores in DB

This is simpler and more reliable than day-by-day collection.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from core.events import MarketBar
from database.connection import get_db_manager
from data.bar_storage import BarStorage
from utils.contract_utils import FuturesContractUtils


async def main():
    """Main execution"""
    print("=" * 70)
    print("Simple Historical Data Collector")
    print("=" * 70)
    print("\nThis will collect maximum available 1-minute data from IB")
    print("(approximately 1 month = ~28,000 bars)")
    print("\n" + "=" * 70)

    symbol = "ES"
    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    db = get_db_manager()
    storage = BarStorage(db)

    try:
        # 1. Connect to database
        print("\n[1/4] Connecting to database...")
        await db.connect()
        print("      Connected")

        # 2. Connect to IB
        print("\n[2/4] Connecting to IB API...")
        connected = await ib_client.connect()
        if not connected:
            raise Exception("Failed to connect to IB")
        print("      Connected")

        # 3. Get current contract month
        print(f"\n[3/4] Determining current contract month...")
        utils = FuturesContractUtils()
        contract_month = utils.get_contract_string(datetime.now())
        local_symbol = utils.get_local_symbol(symbol, datetime.now())

        print(f"      Contract month: {contract_month}")
        print(f"      Local symbol: {local_symbol}")

        # 4. Request maximum data
        print(f"\n[4/4] Requesting historical data...")
        print("      Duration: 1 M (1 month - maximum for 1-minute bars)")
        print("      Bar size: 1 min")
        print("      This may take ~30 seconds...")

        bars = await ib_client.request_historical_bars(
            symbol=symbol,
            duration='1 M',
            bar_size='1 min',
            contract_month=contract_month
        )

        if not bars:
            print("      No data returned!")
            return

        print(f"      Received {len(bars):,} bars")
        print(f"      First bar: {bars[0].date}")
        print(f"      Last bar: {bars[-1].date}")

        # 5. Convert to MarketBar format
        print(f"\n[5/6] Converting {len(bars):,} bars...")

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
                print(f"      Warning: Failed to convert bar at {ib_bar.date}: {e}")

        print(f"      Converted {len(market_bars):,} bars successfully")

        # 6. Bulk save to database
        print(f"\n[6/6] Saving to database...")
        saved = await storage.save_bars_bulk(market_bars)

        print(f"      Saved {saved:,} bars to database")

        # Summary
        print("\n" + "=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print(f"\nSymbol: {symbol}")
        print(f"Bars saved: {saved:,}")
        print(f"Date range: {bars[0].date} to {bars[-1].date}")
        print(f"Database table: market_data_1min")

        # Verification query
        print("\nTo verify:")
        print(f"  SELECT COUNT(*), MIN(timestamp), MAX(timestamp)")
        print(f"  FROM market_data_1min WHERE symbol = '{symbol}';")

        print("\nTo use for backtesting:")
        print(f"  SELECT * FROM market_data_1min")
        print(f"  WHERE symbol = '{symbol}'")
        print(f"  ORDER BY timestamp ASC;")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        print("\nDisconnecting...")
        await ib_client.disconnect()
        await db.disconnect()
        print("Done")


if __name__ == "__main__":
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure PostgreSQL is running")
    print("  - Check .env file has correct credentials\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n\nError: {e}")
