"""
NQ (Nasdaq Futures) 1-minute bars test - Version 2
Using localSymbol for current front month contract
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from ib_async import IB, Future
from core.event_bus import EventBus


async def test_nq_1min_bars():
    """Get NQ 1-minute bars using direct IB connection"""

    print("=" * 60)
    print("[NQ] Nasdaq Futures 1-Minute Bars Test v2")
    print("=" * 60)

    # Create IB connection
    ib = IB()

    try:
        # Connect to IB Gateway
        print("\n[CONNECT] Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=999)

        print("[SUCCESS] IB Gateway connected!")
        print(f"         Account: {ib.managedAccounts()}")

        # Create NQ contract using localSymbol (front month)
        print("\n[CONTRACT] Creating NQ contract...")
        contract = Future(
            localSymbol='NQZ4',  # December 2024
            exchange='CME'
        )

        # Qualify contract
        print("[QUALIFY] Qualifying contract...")
        await ib.qualifyContractsAsync(contract)
        print(f"[SUCCESS] Contract qualified: {contract}")

        # Request NQ 1-minute bars
        print("\n[REQUEST] Requesting NQ 1-minute bars...")
        print("          Duration: 1 Day")
        print("          Bar Size: 1 min")

        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,  # Include extended hours
            formatDate=1
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
            highs = [bar.high for bar in bars]
            lows = [bar.low for bar in bars]
            volumes = [bar.volume for bar in bars]

            print(f"Low:         {min(closes):>10,.2f}")
            print(f"High:        {max(closes):>10,.2f}")
            print(f"Average:     {sum(closes)/len(closes):>10,.2f}")
            print(f"Range:       {max(highs) - min(lows):>10,.2f}")
            print(f"Total Vol:   {sum(volumes):>10,}")
            print(f"First time:  {bars[0].date}")
            print(f"Last time:   {bars[-1].date}")
            print(f"Total bars:  {len(bars)}")

        print("\n[DONE] Test completed!")

    except Exception as e:
        print(f"\n[ERROR] Error occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Disconnect
        print("\n[DISCONNECT] Closing connection...")
        ib.disconnect()
        print("[DONE] Connection closed")


if __name__ == "__main__":
    asyncio.run(test_nq_1min_bars())
