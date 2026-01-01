"""
NQ (Nasdaq Futures) 1-minute bars test
Get real market data from IB Gateway Paper Trading
"""

import asyncio
import sys
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker import IBClient
from core.event_bus import EventBus


async def test_nq_1min_bars():
    """Get NQ 1-minute bars from IB Gateway"""

    print("=" * 60)
    print("[NQ] Nasdaq Futures 1-Minute Bars Test")
    print("=" * 60)

    # Create Event Bus
    event_bus = EventBus()
    await event_bus.start()

    # Create IB Client
    client = IBClient(event_bus)

    try:
        # Connect to IB Gateway
        print("\n[CONNECT] Connecting to IB Gateway...")
        connected = await client.connect()

        if not connected:
            print("[FAILED] IB Gateway connection failed!")
            print("        Make sure IB Gateway Paper Trading is running on port 4002")
            return

        print("[SUCCESS] IB Gateway connected!")
        print(f"         Account: {client.connection_manager.ib.managedAccounts()}")

        # Request NQ 1-minute bars
        print("\n[REQUEST] Requesting NQ 1-minute bars...")
        print("          Duration: 1 Day")
        print("          Bar Size: 1 min")

        bars = await client.request_historical_bars(
            symbol='NQ',
            duration='1 D',      # 1 day
            bar_size='1 min'     # 1 minute
        )

        # Display results
        print(f"\n[SUCCESS] Received {len(bars)} bars")
        print("\n" + "=" * 80)
        print("[DATA] Last 10 bars")
        print("=" * 80)
        print(f"{'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>10}")
        print("-" * 80)

        # Show last 10 bars
        for bar in bars[-10:]:
            print(f"{str(bar.date):<20} {bar.open:>10.2f} {bar.high:>10.2f} "
                  f"{bar.low:>10.2f} {bar.close:>10.2f} {bar.volume:>10}")

        # Statistics
        print("\n" + "=" * 60)
        print("[STATS] Data Statistics")
        print("=" * 60)

        if bars:
            closes = [bar.close for bar in bars]
            print(f"Low:        {min(closes):>10,.2f}")
            print(f"High:       {max(closes):>10,.2f}")
            print(f"Average:    {sum(closes)/len(closes):>10,.2f}")
            print(f"First time: {bars[0].date}")
            print(f"Last time:  {bars[-1].date}")
            print(f"Total bars: {len(bars)}")

        print("\n[DONE] Test completed!")

    except Exception as e:
        print(f"\n[ERROR] Error occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Disconnect
        print("\n[DISCONNECT] Closing connection...")
        await client.disconnect()
        await event_bus.stop()
        print("[DONE] Connection closed")


if __name__ == "__main__":
    asyncio.run(test_nq_1min_bars())
