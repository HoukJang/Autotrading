"""
Test script to check IB historical data availability for 1-minute bars.

IB Historical Data Limitations Documentation:
https://www.interactivebrokers.com/en/software/api/apiguide/tables/historical_data_limitations.htm

Common limitations for 1-minute bars:
- Stocks/ETFs: Up to 60 days
- Futures: Depends on data subscription, typically 30-180 days
- Forex: Up to 1 year

This script tests actual availability with your IB account.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from ib_async import Future


async def test_data_limits():
    """Test IB historical data limits for 1-minute bars."""

    print("=" * 70)
    print("IB Historical Data Availability Test - 1 Minute Bars")
    print("=" * 70)

    # Initialize client
    event_bus = EventBus()
    client = IBClient(event_bus)

    try:
        # Connect to IB
        print("\nStep 1: Connecting to IB API...")
        connected = await client.connect()

        if not connected:
            print("Error: Failed to connect to IB API")
            print("Make sure TWS/IB Gateway is running!")
            return

        print("Success: Connected to IB API")

        # Test with ES futures - front month
        print("\nStep 2: Getting ES futures contract details...")
        symbol = "ES"

        # Create basic contract
        es_contract = Future(
            symbol='ES',
            exchange='CME',
            currency='USD'
        )

        # Get contract details to find all available expiries
        contract_details = await client._ib.reqContractDetailsAsync(es_contract)

        if not contract_details:
            print("Error: Could not get ES contract details")
            print("  Make sure you have market data subscription for ES futures")
            return

        print(f"  Found {len(contract_details)} available ES contracts")

        # Extract contracts and sort by expiry
        contracts = [cd.contract for cd in contract_details]
        contracts.sort(key=lambda c: c.lastTradeDateOrContractMonth)

        # Use front month (nearest expiry)
        front_month = contracts[0]

        print(f"Success: Selected front month contract")
        print(f"  Local Symbol: {front_month.localSymbol}")
        print(f"  Expiry: {front_month.lastTradeDateOrContractMonth}")
        print(f"  ConId: {front_month.conId}")

        # Test different durations
        print("\nStep 3: Testing historical data availability...")
        print("-" * 70)

        test_cases = [
            ("1 D", "1 day"),
            ("2 D", "2 days"),
            ("1 W", "1 week"),
            ("2 W", "2 weeks"),
            ("1 M", "1 month"),
            ("2 M", "2 months"),
            ("3 M", "3 months"),
            ("6 M", "6 months"),
            ("1 Y", "1 year"),
        ]

        results = []
        max_success = None

        for duration_str, description in test_cases:
            try:
                print(f"\nTesting {description} ({duration_str})...", end=" ")

                bars = await client._ib.reqHistoricalDataAsync(
                    front_month,
                    endDateTime='',
                    durationStr=duration_str,
                    barSizeSetting="1 min",
                    whatToShow='TRADES',
                    useRTH=False,  # Use regular trading hours = False to get all data
                    formatDate=1
                )

                if bars and len(bars) > 0:
                    first_bar = bars[0]
                    last_bar = bars[-1]
                    days_coverage = (last_bar.date - first_bar.date).total_seconds() / 86400

                    result = {
                        'duration': description,
                        'duration_str': duration_str,
                        'bars_count': len(bars),
                        'first_date': first_bar.date,
                        'last_date': last_bar.date,
                        'days_coverage': days_coverage,
                        'success': True
                    }

                    print(f"OK ({len(bars):,} bars)")
                    print(f"    Period: {first_bar.date} -> {last_bar.date}")
                    print(f"    Coverage: {days_coverage:.1f} days")

                    max_success = result
                    results.append(result)

                else:
                    print("FAILED (no data)")
                    results.append({
                        'duration': description,
                        'duration_str': duration_str,
                        'success': False,
                        'error': 'No data returned'
                    })

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                error_str = str(e)
                print(f"ERROR: {error_str}")
                results.append({
                    'duration': description,
                    'duration_str': duration_str,
                    'success': False,
                    'error': error_str
                })
                await asyncio.sleep(0.5)

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]

        if successful:
            print(f"\nSuccessful requests: {len(successful)}/{len(results)}")
            print("\nAll successful durations:")
            for r in successful:
                print(f"  - {r['duration']:12s}: {r['bars_count']:7,} bars "
                      f"({r['first_date']} -> {r['last_date']})")

            if max_success:
                print(f"\nMaximum available duration:")
                print(f"  Duration: {max_success['duration']} ({max_success['duration_str']})")
                print(f"  Total bars: {max_success['bars_count']:,}")
                print(f"  Date range: {max_success['first_date']} -> {max_success['last_date']}")
                print(f"  Coverage: {max_success['days_coverage']:.1f} days")

                # Calculate trading days (390 mins per day)
                trading_days = max_success['bars_count'] / 390
                print(f"  Approx {trading_days:.1f} trading days")

        if failed:
            print(f"\nFailed requests: {len(failed)}")
            for r in failed:
                error = r.get('error', 'Unknown error')
                print(f"  - {r['duration']:12s}: {error}")

        # Recommendations
        print("\n" + "=" * 70)
        print("RECOMMENDATIONS FOR BACKTESTING")
        print("=" * 70)

        if max_success:
            safe_duration = None
            safe_bars = 0

            # Find the largest successful duration
            for r in successful:
                if r['bars_count'] > safe_bars:
                    safe_bars = r['bars_count']
                    safe_duration = r

            if safe_duration:
                print(f"\nRecommended backtest initialization period:")
                print(f"  Duration string: '{safe_duration['duration_str']}'")
                print(f"  Expected data: ~{safe_duration['bars_count']:,} bars")
                print(f"  Approx {safe_duration['bars_count'] / 390:.0f} trading days")
                print(f"  Date coverage: ~{safe_duration['days_coverage']:.0f} calendar days")

                print(f"\nBacktest strategy:")
                print(f"  1. Initialize with {safe_duration['duration']} of historical data")
                print(f"  2. Use this period to calculate initial regime/energy scores")
                print(f"  3. Start virtual trading from most recent data")

                print(f"\nIB Historical Data Notes:")
                print(f"  - Data availability depends on your market data subscriptions")
                print(f"  - ES futures typically have good historical depth")
                print(f"  - For longer backtests, consider using data vendors (Norgate, etc.)")
                print(f"  - IB Paper account has same data as live account")

        else:
            print("\nNo successful data requests!")
            print("Possible issues:")
            print("  - No market data subscription for ES futures")
            print("  - IB Gateway/TWS not properly configured")
            print("  - Connection issues")
            print("\nCheck your IB account settings and data subscriptions.")

        print("\n" + "=" * 70)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")

    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Disconnect
        print("\nDisconnecting from IB API...")
        await client.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    print("\nIMPORTANT: Make sure TWS/IB Gateway is running!")
    print("           Configure File -> Global Configuration -> API -> Settings")
    print("           Enable ActiveX and Socket Clients\n")

    try:
        asyncio.run(test_data_limits())
    except KeyboardInterrupt:
        print("\nTest cancelled by user")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
