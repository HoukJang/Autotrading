"""
Test to identify the real problem:
1. Date format issue (technical)
2. Rollover/contract issue (data not available)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from broker.contracts import ContractFactory


async def test_scenario(ib_client, description, contract_month, end_datetime, duration):
    """Test a specific scenario"""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    print(f"Contract: {contract_month}")
    print(f"End DateTime: {end_datetime}")
    print(f"Duration: {duration}")

    try:
        futures_contract = ContractFactory.create_futures("ES", expiry=contract_month)
        contract = futures_contract.to_ib_contract()

        bars = await ib_client._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime,
            durationStr=duration,
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1
        )

        if bars and len(bars) > 0:
            print(f"SUCCESS: Received {len(bars)} bars")
            print(f"  First bar: {bars[0].date}")
            print(f"  Last bar: {bars[-1].date}")
            return True, len(bars), bars[0].date, bars[-1].date
        else:
            print(f"FAILED: No data received")
            return False, 0, None, None

    except Exception as e:
        print(f"ERROR: {e}")
        return False, 0, None, None


async def main():
    """Main test"""
    print("="*70)
    print("ROLLOVER ISSUE DIAGNOSIS")
    print("="*70)

    event_bus = EventBus()
    ib_client = IBClient(event_bus)

    try:
        print("\nConnecting to IB API...")
        await ib_client.connect()
        print("Connected\n")

        # TEST 1: Current contract with empty endDateTime (baseline - should work)
        print("\n" + ">"*70)
        print("TEST GROUP 1: BASELINE (Current contract, no specific date)")
        print(">"*70)

        await test_scenario(
            ib_client,
            "Current contract (ESZ2025), recent 1 day",
            "202512",  # ESZ2025
            "",  # Empty = current time
            "1 D"
        )

        # TEST 2: Current contract with specific recent date
        print("\n" + ">"*70)
        print("TEST GROUP 2: SPECIFIC RECENT DATE")
        print(">"*70)

        # Try different date formats for Oct 12
        date_formats = [
            "",  # Empty (for comparison)
            "20251012",  # Just date
            "20251012 23:59:59",  # Date + time (no timezone)
            "20251012 23:59:59 US/Eastern",  # Full format
            "20251012-23:59:59",  # UTC format
        ]

        for fmt in date_formats:
            await test_scenario(
                ib_client,
                f"Oct 12 with format: '{fmt}'",
                "202512",
                fmt,
                "1 D"
            )
            await asyncio.sleep(1)  # Rate limiting

        # TEST 3: September dates with ESZ2025
        print("\n" + ">"*70)
        print("TEST GROUP 3: SEPTEMBER DATES WITH ESZ2025")
        print(">"*70)

        september_dates = [
            ("20250920", "Sept 20 (just date)"),
            ("20250920 23:59:59 US/Eastern", "Sept 20 (full format)"),
            ("20250914", "Sept 14 (just date)"),
            ("20250914 23:59:59 US/Eastern", "Sept 14 (full format)"),
        ]

        for date_str, desc in september_dates:
            await test_scenario(
                ib_client,
                f"{desc} with ESZ2025",
                "202512",  # ESZ2025
                date_str,
                "1 D"
            )
            await asyncio.sleep(1)

        # TEST 4: September dates with ESU2025 (old contract)
        print("\n" + ">"*70)
        print("TEST GROUP 4: SEPTEMBER DATES WITH ESU2025 (OLD CONTRACT)")
        print(">"*70)

        for date_str, desc in september_dates:
            await test_scenario(
                ib_client,
                f"{desc} with ESU2025",
                "202509",  # ESU2025
                date_str,
                "1 D"
            )
            await asyncio.sleep(1)

        # TEST 5: Different durations for September range
        print("\n" + ">"*70)
        print("TEST GROUP 5: DIFFERENT DURATIONS FOR SEPTEMBER")
        print(">"*70)

        durations = [
            ("1 D", "1 day"),
            ("7 D", "7 days"),
            ("1 W", "1 week"),
        ]

        for dur, desc in durations:
            await test_scenario(
                ib_client,
                f"Sept 20 end, {desc} duration with ESZ2025",
                "202512",
                "20250920 23:59:59 US/Eastern",
                dur
            )
            await asyncio.sleep(1)

        print("\n" + "="*70)
        print("DIAGNOSIS COMPLETE")
        print("="*70)
        print("\nAnalyze the results above to determine:")
        print("1. If date format is the issue -> Some formats work, others don't")
        print("2. If rollover/contract is the issue -> ESZ2025 and ESU2025 both fail for Sept dates")
        print("3. If it's both -> ESZ2025 works with correct format, ESU2025 never works")
        print("="*70)

    finally:
        print("\nDisconnecting...")
        await ib_client.disconnect()
        print("Done")


if __name__ == "__main__":
    asyncio.run(main())
