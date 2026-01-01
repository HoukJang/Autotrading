"""
Test specific date: September 10, 2025
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
from utils.contract_utils import FuturesContractUtils


async def main():
    """Test September 10, 2025 data"""
    print("=" * 70)
    print("Testing September 20, 2025 Data")
    print("=" * 70)

    target_date = datetime(2025, 9, 20)
    symbol = "ES"

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    db = get_db_manager()
    storage = BarStorage(db)
    utils = FuturesContractUtils()

    try:
        # Connect to DB
        print("\n1. Connecting to database...")
        await db.connect()
        print("   Connected")

        # Connect to IB
        print("\n2. Connecting to IB API...")
        await ib_client.connect()
        print("   Connected")

        # Get contract month for date
        auto_contract_month = utils.get_contract_string(target_date)
        auto_local_symbol = utils.get_local_symbol(symbol, target_date)

        print(f"\n3. Target date: {target_date.strftime('%Y-%m-%d')}")
        print(f"   Auto-detected contract: {auto_contract_month} ({auto_local_symbol})")

        # Try ESZ2025 instead (since rollover happened on 9/14)
        contract_month = "202512"  # ESZ2025
        local_symbol = "ESZ2025"

        print(f"   Trying contract: {contract_month} ({local_symbol})")

        # Request data
        print("\n4. Requesting 1-day data...")
        bars = await ib_client.request_historical_bars(
            symbol=symbol,
            duration="1 D",
            bar_size="1 min",
            contract_month=contract_month
        )

        if bars:
            print(f"   Received {len(bars)} bars")
            print(f"   First: {bars[0].date}")
            print(f"   Last: {bars[-1].date}")

            # Convert to MarketBar
            print("\n5. Converting bars...")
            market_bars = []
            for ib_bar in bars:
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

            print(f"   Converted {len(market_bars)} bars")

            # Save to DB
            print("\n6. Saving to database...")
            saved = await storage.save_bars_bulk(market_bars)
            print(f"   Saved {saved} bars")

            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)

        else:
            print("\n   [ERROR] No data received")

    finally:
        print("\nDisconnecting...")
        await ib_client.disconnect()
        await db.disconnect()
        print("Done")


if __name__ == "__main__":
    asyncio.run(main())
