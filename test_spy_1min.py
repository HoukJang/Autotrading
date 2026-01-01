"""
SPY (S&P 500 ETF) 1-minute bars test
Testing with stock/ETF instead of futures
"""

import asyncio
import sys
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from ib_async import IB, Stock


async def test_spy_1min_bars():
    """Get SPY 1-minute bars - this should work without futures subscription"""

    print("=" * 60)
    print("[SPY] S&P 500 ETF 1-Minute Bars Test")
    print("=" * 60)

    # Create IB connection
    ib = IB()

    try:
        # Connect to IB Gateway
        print("\n[CONNECT] Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=997)

        print("[SUCCESS] IB Gateway connected!")
        print(f"         Account: {ib.managedAccounts()}")

        # Create SPY contract (ETF)
        print("\n[CONTRACT] Creating SPY contract...")
        contract = Stock(
            symbol='SPY',
            exchange='SMART',
            currency='USD'
        )

        # Qualify contract
        print("[QUALIFY] Qualifying contract...")
        qualified = await ib.qualifyContractsAsync(contract)
        if qualified:
            contract = qualified[0]
            print(f"[SUCCESS] Contract qualified: {contract}")

        # Request SPY 1-minute bars
        print("\n[REQUEST] Requesting SPY 1-minute bars...")
        print("          Duration: 1 Day")
        print("          Bar Size: 1 min")

        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=True,  # Regular trading hours only
            formatDate=1
        )

        # Display results
        print(f"\n[SUCCESS] Received {len(bars)} bars")

        if bars:
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

            # Show sample data for verification
            print("\n[SAMPLE] First 3 bars:")
            for i, bar in enumerate(bars[:3], 1):
                print(f"  {i}. {bar.date}: O={bar.open:.2f} H={bar.high:.2f} "
                      f"L={bar.low:.2f} C={bar.close:.2f} V={bar.volume}")
        else:
            print("[WARNING] No bars received")

        print("\n[DONE] Test completed!")
        print("=" * 60)
        print("NOTE: Paper Trading works with SPY!")
        print("      For NQ futures, you may need market data subscription")
        print("=" * 60)

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
    asyncio.run(test_spy_1min_bars())
