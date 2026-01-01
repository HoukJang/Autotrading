"""
Test NQ 1-minute bar data range - Simple version
"""

import asyncio
from ib_async import IB, Future


async def test():
    ib = IB()

    try:
        print("Connecting...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=994)
        print(f"Connected: {ib.managedAccounts()}")

        # NQZ5
        contract = Future(
            symbol='NQ',
            lastTradeDateOrContractMonth='20251219',
            exchange='CME',
            currency='USD'
        )

        qualified = await ib.qualifyContractsAsync(contract)

        if qualified:
            contract = qualified[0]
            print(f"\nContract: {contract.localSymbol}")

            # Test cases
            tests = [
                ('1 D', '1 Day'),
                ('2 D', '2 Days'),
                ('1 W', '1 Week'),
                ('2 W', '2 Weeks'),
            ]

            print("\n" + "=" * 60)
            for duration, desc in tests:
                print(f"\nTesting {desc} ({duration})...")

                try:
                    bars = await ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime='',
                        durationStr=duration,
                        barSizeSetting='1 min',
                        whatToShow='TRADES',
                        useRTH=False,
                        formatDate=1
                    )

                    if bars:
                        print(f"  SUCCESS: {len(bars):,} bars")
                        print(f"  From: {bars[0].date}")
                        print(f"  To:   {bars[-1].date}")
                    else:
                        print(f"  FAILED: No data")

                    await asyncio.sleep(2)

                except Exception as e:
                    print(f"  ERROR: {e}")
        else:
            print("Contract qualification failed")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ib.disconnect()
        print("\nDone")


if __name__ == "__main__":
    asyncio.run(test())
