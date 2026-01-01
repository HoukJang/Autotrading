"""
Test contract rollover logic with various scenarios
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from utils.contract_utils import FuturesContractUtils


def test_expiry_calculation():
    """Test third Friday calculation"""
    print("=" * 70)
    print("Test 1: Expiration Date Calculation")
    print("=" * 70)

    utils = FuturesContractUtils()

    test_cases = [
        (2025, 9, datetime(2025, 9, 19)),   # September 2025
        (2025, 12, datetime(2025, 12, 19)), # December 2025
        (2026, 3, datetime(2026, 3, 20)),   # March 2026
        (2026, 6, datetime(2026, 6, 19)),   # June 2026
    ]

    for year, month, expected in test_cases:
        result = utils.get_expiry_date(year, month)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"{status} {year}-{month:02d}: {result.date()} (expected: {expected.date()})")

    print()


def test_contract_expired():
    """Test contract expiration check"""
    print("=" * 70)
    print("Test 2: Contract Expiration Check")
    print("=" * 70)

    utils = FuturesContractUtils()

    test_cases = [
        # (year, month, check_date, expected_expired)
        (2025, 9, datetime(2025, 9, 30), True),   # After expiration
        (2025, 9, datetime(2025, 9, 19), False),  # On expiration day
        (2025, 9, datetime(2025, 9, 18), False),  # Before expiration
        (2025, 12, datetime(2025, 9, 30), False), # Future contract
    ]

    for year, month, check_date, expected in test_cases:
        result = utils.is_contract_expired(year, month, check_date)
        status = "[OK]" if result == expected else "[FAIL]"
        expiry = utils.get_expiry_date(year, month).date()
        print(f"{status} {year}{month:02d} on {check_date.date()} (expiry: {expiry}): "
              f"Expired={result} (expected: {expected})")

    print()


def test_active_contract_rollover():
    """Test active contract selection with rollover"""
    print("=" * 70)
    print("Test 3: Active Contract Selection (Rollover Logic)")
    print("=" * 70)

    utils = FuturesContractUtils()

    test_cases = [
        # (target_date, expected_year, expected_month, description)
        (datetime(2025, 9, 30), 2025, 12, "After Sep expiry (9/19)"),
        (datetime(2025, 9, 19), 2025, 12, "On Sep expiry day"),
        (datetime(2025, 9, 14), 2025, 12, "Within rollover window (5 days before)"),
        (datetime(2025, 9, 12), 2025, 12, "On rollover boundary (7 days before)"),
        (datetime(2025, 9, 11), 2025, 9, "Just outside rollover window"),
        (datetime(2025, 9, 5), 2025, 9, "Well before expiry"),
        (datetime(2025, 10, 6), 2025, 12, "October -> Dec contract"),
        (datetime(2025, 12, 25), 2026, 3, "After Dec expiry -> Mar 2026"),
        (datetime(2025, 2, 10), 2025, 3, "February -> Mar contract"),
    ]

    for target_date, exp_year, exp_month, desc in test_cases:
        year, month = utils.get_active_contract_for_date(target_date)
        contract_str = utils.get_active_contract_string(target_date)
        local_symbol = utils.get_active_local_symbol('ES', target_date)

        status = "[OK]" if (year == exp_year and month == exp_month) else "[FAIL]"
        print(f"{status} {target_date.date()}: {contract_str} ({local_symbol}) - {desc}")
        if year != exp_year or month != exp_month:
            print(f"   Expected: {exp_year}{exp_month:02d}, Got: {contract_str}")

    print()


def test_rollover_window_custom():
    """Test custom rollover window"""
    print("=" * 70)
    print("Test 4: Custom Rollover Window")
    print("=" * 70)

    utils = FuturesContractUtils()

    # Test with different rollover windows
    test_date = datetime(2025, 9, 17)  # 2 days before Sep 19 expiry

    for rollover_days in [3, 7, 10]:
        year, month = utils.get_active_contract_for_date(test_date, rollover_days)
        contract = f"{year}{month:02d}"
        days_until = (datetime(2025, 9, 19) - test_date).days

        if days_until <= rollover_days:
            expected = "202512"  # Should roll to Dec
        else:
            expected = "202509"  # Should stay in Sep

        status = "[OK]" if contract == expected else "[FAIL]"
        print(f"{status} {test_date.date()} with {rollover_days}-day window: {contract} "
              f"({days_until} days before expiry)")

    print()


def test_year_boundary():
    """Test year boundary handling"""
    print("=" * 70)
    print("Test 5: Year Boundary Cases")
    print("=" * 70)

    utils = FuturesContractUtils()

    test_cases = [
        (datetime(2025, 12, 20), 2026, 3, "After Dec 2025 expiry"),
        (datetime(2025, 12, 10), 2025, 12, "Before Dec 2025 expiry"),
        (datetime(2026, 1, 15), 2026, 3, "January 2026"),
        (datetime(2026, 2, 28), 2026, 3, "End of February 2026"),
    ]

    for target_date, exp_year, exp_month, desc in test_cases:
        year, month = utils.get_active_contract_for_date(target_date)
        contract = f"{year}{month:02d}"
        expected = f"{exp_year}{exp_month:02d}"

        status = "[OK]" if contract == expected else "[FAIL]"
        print(f"{status} {target_date.date()}: {contract} (expected: {expected}) - {desc}")

    print()


def test_trading_contract():
    """Test get_contract_for_trading (current time)"""
    print("=" * 70)
    print("Test 6: Current Trading Contract")
    print("=" * 70)

    utils = FuturesContractUtils()

    # Get current contract for trading
    current_contract = utils.get_contract_for_trading('ES')
    year, month = utils.get_active_contract_for_date(datetime.now())
    current_local = utils.get_active_local_symbol('ES', datetime.now())

    print(f"Current date: {datetime.now().date()}")
    print(f"Active trading contract: {current_contract} ({current_local})")
    print(f"Year: {year}, Month: {month}")

    # Show next few quarterly contracts
    print("\nQuarterly contract schedule:")
    for i, exp_month in enumerate(utils.ES_EXPIRY_MONTHS * 2):
        if i >= 4:
            break
        test_year = year if exp_month >= month else year + 1
        expiry = utils.get_expiry_date(test_year, exp_month)
        month_code = utils.MONTH_CODES[exp_month]
        print(f"  ES{month_code}{test_year} (expires: {expiry.date()})")

    print()


if __name__ == "__main__":
    print("\nES Futures Contract Rollover Tests\n")

    test_expiry_calculation()
    test_contract_expired()
    test_active_contract_rollover()
    test_rollover_window_custom()
    test_year_boundary()
    test_trading_contract()

    print("=" * 70)
    print("All tests completed!")
    print("=" * 70)
