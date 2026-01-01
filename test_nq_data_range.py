"""
Test NQ 1-minute bar data range limits
Find maximum historical data available
"""

import asyncio
from ib_async import IB, Future


async def test_data_ranges():
    """Test different duration ranges for 1-minute bars"""

    print("=" * 70)
    print("[TEST] NQ 1-Minute Bar Data Range Limits")
    print("=" * 70)

    ib = IB()

    try:
        # Connect
        print("\n[CONNECT] Connecting...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=995)
        print(f"[SUCCESS] Connected! Account: {ib.managedAccounts()}")

        # Qualify NQZ5 contract
        print("\n[CONTRACT] Trying NQZ5...")
        contract = Future(
            symbol='NQ',
            lastTradeDateOrContractMonth='20251219',
            exchange='CME',
            currency='USD'
        )
        qualified = await ib.qualifyContractsAsync(contract)

        if not qualified:
            print("[WARN] NQZ5 not found, trying NQH6...")
            contract = Future(
                symbol='NQ',
                lastTradeDateOrContractMonth='20260320',
                exchange='CME',
                currency='USD'
            )
            qualified = await ib.qualifyContractsAsync(contract)

        if not qualified:
            print("[ERROR] No contract qualified")
            return

        contract = qualified[0]
        print(f"[SUCCESS] Contract: {contract.localSymbol}")

        # Test different durations
        test_cases = [
            ('1 D', '1 Day'),
            ('2 D', '2 Days'),
            ('1 W', '1 Week'),
            ('2 W', '2 Weeks'),
            ('1 M', '1 Month'),
            ('2 M', '2 Months'),
        ]

        results = []

        for duration_str, description in test_cases:
            print(f"\n[TEST] Requesting {description} ({duration_str})...")

            try:
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime='',
                    durationStr=duration_str,
                    barSizeSetting='1 min',
                    whatToShow='TRADES',
                    useRTH=False,
                    formatDate=1
                )

                if bars:
                    first_date = bars[0].date
                    last_date = bars[-1].date
                    total_bars = len(bars)

                    print(f"[SUCCESS] Received {total_bars:,} bars")
                    print(f"          From: {first_date}")
                    print(f"          To:   {last_date}")

                    results.append({
                        'duration': description,
                        'bars': total_bars,
                        'first': first_date,
                        'last': last_date,
                        'success': True
                    })
                else:
                    print(f"[WARN] No data received")
                    results.append({
                        'duration': description,
                        'success': False,
                        'error': 'No data'
                    })

                # Wait between requests to avoid rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                print(f"[ERROR] {e}")
                results.append({
                    'duration': description,
                    'success': False,
                    'error': str(e)
                })

        # Summary
        print("\n" + "=" * 80)
        print("[SUMMARY] Data Range Test Results")
        print("=" * 80)
        print(f"{'Duration':<15} {'Status':<10} {'Bars':>10} {'Date Range':<40}")
        print("-" * 80)

        for r in results:
            if r['success']:
                date_range = f"{r['first']} to {r['last']}"
                print(f"{r['duration']:<15} {'SUCCESS':<10} {r['bars']:>10,} {date_range:<40}")
            else:
                print(f"{r['duration']:<15} {'FAILED':<10} {'-':>10} {r.get('error', 'Unknown'):<40}")

        # Find maximum successful duration
        successful = [r for r in results if r['success']]
        if successful:
            max_result = successful[-1]
            print("\n" + "=" * 70)
            print("[RESULT] Maximum 1-Minute Bar Data Range")
            print("=" * 70)
            print(f"Duration:    {max_result['duration']}")
            print(f"Total Bars:  {max_result['bars']:,}")
            print(f"First Date:  {max_result['first']}")
            print(f"Last Date:   {max_result['last']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[DISCONNECT] Closing...")
        ib.disconnect()
        print("[DONE]")


if __name__ == "__main__":
    asyncio.run(test_data_ranges())
