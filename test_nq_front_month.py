"""
NQ (Nasdaq Futures) front month contract discovery
Find the active front month contract
"""

import asyncio
from datetime import datetime
from ib_async import IB, Future


async def find_nq_contract():
    """Find active NQ contract"""

    print("=" * 60)
    print("[NQ] Finding Active Front Month Contract")
    print("=" * 60)

    ib = IB()

    try:
        # Connect
        print("\n[CONNECT] Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=998)
        print(f"[SUCCESS] Connected! Account: {ib.managedAccounts()}")

        # Try different contract specifications
        print("\n[SEARCH] Searching for NQ contracts...")

        # Method 1: Use symbol only, let IB find the front month
        contract1 = Future(
            symbol='NQ',
            exchange='CME'
        )

        print("\n[TRY 1] Qualifying NQ with symbol only...")
        qualified = await ib.qualifyContractsAsync(contract1)

        if qualified:
            print(f"[SUCCESS] Found {len(qualified)} contract(s):")

            # Test data retrieval with first contract (front month)
            if qualified:
                test_contract = qualified[0]
                print(f"[INFO] Using front month contract:")
                print(f"  Symbol: {test_contract.symbol}")
                print(f"  LocalSymbol: {test_contract.localSymbol}")
                print(f"  LastTradeDateOrContractMonth: {test_contract.lastTradeDateOrContractMonth}")
                print(f"  Exchange: {test_contract.exchange}")
                print(f"  ConId: {test_contract.conId}")
                print()
                print(f"\n[TEST] Testing data retrieval with {test_contract.localSymbol}...")

                bars = await ib.reqHistoricalDataAsync(
                    test_contract,
                    endDateTime='',
                    durationStr='1 D',
                    barSizeSetting='1 min',
                    whatToShow='TRADES',
                    useRTH=False,
                    formatDate=1
                )

                print(f"[SUCCESS] Received {len(bars)} bars")

                if bars:
                    print("\n[SAMPLE] Last 5 bars:")
                    print(f"{'Time':<20} {'Close':>10} {'Volume':>10}")
                    print("-" * 45)
                    for bar in bars[-5:]:
                        print(f"{str(bar.date):<20} {bar.close:>10.2f} {bar.volume:>10}")

                    print(f"\n[INFO] Contract Details:")
                    print(f"  Symbol: {test_contract.localSymbol}")
                    print(f"  Total bars: {len(bars)}")
                    print(f"  Date range: {bars[0].date} to {bars[-1].date}")
        else:
            print("[ERROR] No contracts found")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[DISCONNECT] Closing connection...")
        ib.disconnect()
        print("[DONE]")


if __name__ == "__main__":
    asyncio.run(find_nq_contract())
