"""
Quick test of historical data retrieval
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus


async def main():
    """Test historical bars"""
    print("Testing Historical Data Retrieval")
    print("=" * 70)

    event_bus = EventBus()
    ib_client = IBClient(event_bus)

    try:
        # Connect
        print("\n1. Connecting to IB...")
        await ib_client.connect()
        print("   Connected")

        # Request historical data
        print("\n2. Requesting 1-day 1-minute bars...")
        bars = await ib_client.request_historical_bars(
            symbol="ES",
            duration="1 D",
            bar_size="1 min"
        )

        if bars:
            print(f"   Received {len(bars)} bars")
            print(f"   First: {bars[0].date}")
            print(f"   Last: {bars[-1].date}")
            print(f"\n   Sample bar:")
            print(f"     Date: {bars[0].date}")
            print(f"     Open: {bars[0].open}")
            print(f"     High: {bars[0].high}")
            print(f"     Low: {bars[0].low}")
            print(f"     Close: {bars[0].close}")
            print(f"     Volume: {bars[0].volume}")
        else:
            print("   No data received!")

    finally:
        print("\n3. Disconnecting...")
        await ib_client.disconnect()
        print("   Done")


if __name__ == "__main__":
    asyncio.run(main())
