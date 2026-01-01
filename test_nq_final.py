"""
NQ (Nasdaq Futures) 1-minute bars test
Using specific contract month: NQZ5 (Dec 2025) or NQH6 (Mar 2026)
"""

import asyncio
from ib_async import IB, Future


async def test_nq_1min():
    """Get NQ 1-minute bars"""

    print("=" * 70)
    print("[NQ] Nasdaq Futures 1-Minute Bars Test")
    print("=" * 70)

    ib = IB()

    try:
        # Connect
        print("\n[CONNECT] Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=996)
        print(f"[SUCCESS] Connected! Account: {ib.managedAccounts()}")

        # Try NQZ5 (December 2025)
        print("\n[CONTRACT] Trying NQZ5 (December 2025)...")
        contract = Future(
            symbol='NQ',
            lastTradeDateOrContractMonth='20251219',
            exchange='CME',
            currency='USD'
        )

        qualified = await ib.qualifyContractsAsync(contract)

        if not qualified:
            print("[WARN] NQZ5 not found, trying NQH6 (March 2026)...")
            contract = Future(
                symbol='NQ',
                lastTradeDateOrContractMonth='20260320',
                exchange='CME',
                currency='USD'
            )
            qualified = await ib.qualifyContractsAsync(contract)

        if qualified:
            contract = qualified[0]
            print(f"[SUCCESS] Contract qualified:")
            print(f"  LocalSymbol: {contract.localSymbol}")
            print(f"  Expiry: {contract.lastTradeDateOrContractMonth}")
            print(f"  Multiplier: {contract.multiplier}")

            # Request 1-minute bars
            print("\n[REQUEST] Requesting 1-minute bars (1 day)...")
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime='',
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False,
                formatDate=1
            )

            print(f"[SUCCESS] Received {len(bars)} bars")

            if bars:
                print("\n" + "=" * 80)
                print("[DATA] Last 10 bars")
                print("=" * 80)
                print(f"{'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>10}")
                print("-" * 80)

                for bar in bars[-10:]:
                    print(f"{str(bar.date):<20} {bar.open:>10.2f} {bar.high:>10.2f} "
                          f"{bar.low:>10.2f} {bar.close:>10.2f} {bar.volume:>10}")

                # Statistics
                closes = [bar.close for bar in bars]
                highs = [bar.high for bar in bars]
                lows = [bar.low for bar in bars]
                volumes = [bar.volume for bar in bars]

                print("\n" + "=" * 60)
                print("[STATS] Data Statistics")
                print("=" * 60)
                print(f"Low:         {min(closes):>10,.2f}")
                print(f"High:        {max(closes):>10,.2f}")
                print(f"Average:     {sum(closes)/len(closes):>10,.2f}")
                print(f"Range:       {max(highs) - min(lows):>10,.2f}")
                print(f"Total Vol:   {sum(volumes):>10,}")
                print(f"First time:  {bars[0].date}")
                print(f"Last time:   {bars[-1].date}")
                print(f"Total bars:  {len(bars)}")

                print("\n[SUCCESS] NQ futures data retrieved successfully!")
        else:
            print("[ERROR] Could not qualify any NQ contract")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[DISCONNECT] Closing connection...")
        ib.disconnect()
        print("[DONE]")


if __name__ == "__main__":
    asyncio.run(test_nq_1min())
