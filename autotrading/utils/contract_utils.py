"""
Futures contract utilities for Interactive Brokers
Handles contract month calculations and specifications with rollover awareness
"""
from datetime import datetime, timedelta
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class FuturesContractUtils:
    """Utility functions for futures contract specifications"""

    # ES Futures quarterly expiration months (March, June, September, December)
    ES_EXPIRY_MONTHS = [3, 6, 9, 12]

    # Rollover window: use next contract when within N days of expiration
    # Based on market practice where volume shifts 3-5 days before expiry
    DEFAULT_ROLLOVER_DAYS = 7

    # Month code mapping for futures symbols
    MONTH_CODES = {
        1: 'F',   # January
        2: 'G',   # February
        3: 'H',   # March
        4: 'J',   # April
        5: 'K',   # May
        6: 'M',   # June
        7: 'N',   # July
        8: 'Q',   # August
        9: 'U',   # September
        10: 'V',  # October
        11: 'X',  # November
        12: 'Z'   # December
    }

    @classmethod
    def _get_third_friday(cls, year: int, month: int) -> datetime:
        """
        Calculate the third Friday of a given month (ES futures expiration date).

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            datetime object for the third Friday at 00:00:00

        Example:
            _get_third_friday(2025, 9) -> 2025-09-19
            _get_third_friday(2025, 12) -> 2025-12-19
        """
        # Get the first day of the month
        first_day = datetime(year, month, 1)

        # Find the first Friday (weekday 4 = Friday, 0 = Monday)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)

        # Third Friday is 14 days after first Friday
        third_friday = first_friday + timedelta(days=14)

        return third_friday

    @classmethod
    def get_expiry_date(cls, year: int, month: int) -> datetime:
        """
        Get the expiration date for a futures contract.

        ES futures expire on the third Friday of the expiration month.

        Args:
            year: Contract year
            month: Contract month

        Returns:
            Expiration date

        Example:
            get_expiry_date(2025, 9) -> 2025-09-19
            get_expiry_date(2025, 12) -> 2025-12-19
        """
        return cls._get_third_friday(year, month)

    @classmethod
    def is_contract_expired(
        cls,
        year: int,
        month: int,
        check_date: Optional[datetime] = None
    ) -> bool:
        """
        Check if a contract has expired.

        Args:
            year: Contract year
            month: Contract month
            check_date: Date to check against (default: now)

        Returns:
            True if contract has expired

        Example:
            is_contract_expired(2025, 9, datetime(2025, 9, 30)) -> True
            is_contract_expired(2025, 12, datetime(2025, 9, 30)) -> False
        """
        expiry_date = cls.get_expiry_date(year, month)
        check = check_date or datetime.now()

        # Remove time component for date-only comparison
        expiry_date = expiry_date.replace(hour=0, minute=0, second=0, microsecond=0)
        check = check.replace(hour=0, minute=0, second=0, microsecond=0)

        return check > expiry_date

    @classmethod
    def get_active_contract_for_date(
        cls,
        target_date: datetime,
        rollover_days: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Get the active futures contract for a given date with rollover awareness.

        This method accounts for contract rollovers, where trading volume shifts
        from the expiring contract to the next contract before the actual expiration.

        Rollover Logic:
        - If target_date is after expiration: use next contract
        - If within rollover window (N days before expiry): use next contract
        - Otherwise: use current quarter contract

        Args:
            target_date: The date for which to find the active contract
            rollover_days: Days before expiry to switch contracts (default: 7)

        Returns:
            Tuple of (year, month) for the active contract

        Example:
            # After expiration
            get_active_contract_for_date(datetime(2025, 9, 30)) -> (2025, 12)

            # Within rollover window (7 days before 9/19)
            get_active_contract_for_date(datetime(2025, 9, 14)) -> (2025, 12)

            # Well before expiration
            get_active_contract_for_date(datetime(2025, 9, 5)) -> (2025, 9)
        """
        if rollover_days is None:
            rollover_days = cls.DEFAULT_ROLLOVER_DAYS

        year = target_date.year
        month = target_date.month

        # Find the current quarter's expiration month
        current_quarter_month = None
        for expiry_month in cls.ES_EXPIRY_MONTHS:
            if month <= expiry_month:
                current_quarter_month = expiry_month
                break

        # If past December, current quarter is next year's March
        if current_quarter_month is None:
            return (year + 1, 3)

        # Get expiration date for current quarter
        expiry_date = cls.get_expiry_date(year, current_quarter_month)

        # Remove time component for date-only comparison
        target_date_only = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        expiry_date_only = expiry_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if we should use next contract
        if target_date_only > expiry_date_only:
            # After expiration: use next contract
            logger.debug(
                f"Date {target_date.date()} is after expiry {expiry_date.date()}, "
                f"using next contract"
            )
            return cls._get_next_quarter(year, current_quarter_month)

        # Check rollover window
        days_until_expiry = (expiry_date_only - target_date_only).days
        if days_until_expiry <= rollover_days:
            # Within rollover window: use next contract
            logger.info(
                f"Date {target_date.date()} is {days_until_expiry} days before expiry "
                f"{expiry_date.date()} (rollover window: {rollover_days} days), "
                f"using next contract"
            )
            return cls._get_next_quarter(year, current_quarter_month)

        # Use current quarter contract
        logger.debug(
            f"Date {target_date.date()} is {days_until_expiry} days before expiry, "
            f"using current contract {year}-{current_quarter_month:02d}"
        )
        return (year, current_quarter_month)

    @classmethod
    def _get_next_quarter(cls, year: int, current_month: int) -> Tuple[int, int]:
        """
        Get the next quarterly expiration month.

        Args:
            year: Current year
            current_month: Current expiration month

        Returns:
            Tuple of (year, month) for next quarter

        Example:
            _get_next_quarter(2025, 9) -> (2025, 12)
            _get_next_quarter(2025, 12) -> (2026, 3)
        """
        for expiry_month in cls.ES_EXPIRY_MONTHS:
            if current_month < expiry_month:
                return (year, expiry_month)

        # After December, next is March of next year
        return (year + 1, 3)

    @classmethod
    def get_contract_month_for_date(cls, target_date: datetime) -> Tuple[int, int]:
        """
        Get the appropriate futures contract month for a given date.

        DEPRECATED: Use get_active_contract_for_date() instead for rollover awareness.

        This method uses simple quarter selection without considering expiration dates
        or rollover windows. It's maintained for backward compatibility.

        Args:
            target_date: The date for which to find the contract month

        Returns:
            Tuple of (year, month) for the contract

        Example:
            2025-10-13 -> (2025, 12)  # December 2025 contract
            2025-09-10 -> (2025, 9)   # September 2025 contract (may be expired!)
        """
        logger.warning(
            "get_contract_month_for_date() is deprecated. "
            "Use get_active_contract_for_date() for rollover awareness."
        )

        year = target_date.year
        month = target_date.month

        # Find the next quarterly expiration month
        for expiry_month in cls.ES_EXPIRY_MONTHS:
            if month <= expiry_month:
                return (year, expiry_month)

        # If we're past December, use March of next year
        return (year + 1, 3)

    @classmethod
    def get_active_contract_string(cls, target_date: datetime, rollover_days: Optional[int] = None) -> str:
        """
        Get the IB contract month string (YYYYMM format) for active contract with rollover awareness.

        Args:
            target_date: The date for which to find the contract
            rollover_days: Days before expiry to switch contracts (default: 7)

        Returns:
            Contract month string in YYYYMM format

        Example:
            get_active_contract_string(datetime(2025, 9, 30)) -> "202512"
            get_active_contract_string(datetime(2025, 9, 14)) -> "202512" (rollover)
            get_active_contract_string(datetime(2025, 9, 5)) -> "202509"
        """
        year, month = cls.get_active_contract_for_date(target_date, rollover_days)
        return f"{year}{month:02d}"

    @classmethod
    def get_active_local_symbol(cls, symbol: str, target_date: datetime, rollover_days: Optional[int] = None) -> str:
        """
        Get the local symbol for active contract with rollover awareness (e.g., ESZ2025).

        Args:
            symbol: Base symbol (e.g., 'ES')
            target_date: The date for which to find the contract
            rollover_days: Days before expiry to switch contracts (default: 7)

        Returns:
            Local symbol string (e.g., 'ESZ2025')

        Example:
            get_active_local_symbol('ES', datetime(2025, 9, 30)) -> "ESZ2025"
            get_active_local_symbol('ES', datetime(2025, 9, 14)) -> "ESZ2025" (rollover)
            get_active_local_symbol('ES', datetime(2025, 9, 5)) -> "ESU2025"
        """
        year, month = cls.get_active_contract_for_date(target_date, rollover_days)
        month_code = cls.MONTH_CODES[month]
        return f"{symbol}{month_code}{year}"

    @classmethod
    def get_contract_for_trading(cls, symbol: str) -> str:
        """
        Get the current active contract for real-time trading.

        Uses current datetime to determine the active contract.

        Args:
            symbol: Base symbol (e.g., 'ES')

        Returns:
            Contract month string in YYYYMM format

        Example:
            get_contract_for_trading('ES') -> "202512" (if today is past Sep rollover)
        """
        return cls.get_active_contract_string(datetime.now())

    @classmethod
    def get_contract_string(cls, target_date: datetime) -> str:
        """
        Get the IB contract month string (YYYYMM format) for a given date.

        DEPRECATED: Use get_active_contract_string() instead for rollover awareness.

        Args:
            target_date: The date for which to find the contract

        Returns:
            Contract month string in YYYYMM format

        Example:
            2025-10-13 -> "202512"
            2025-09-10 -> "202509" (may be expired!)
        """
        logger.warning(
            "get_contract_string() is deprecated. "
            "Use get_active_contract_string() for rollover awareness."
        )
        year, month = cls.get_contract_month_for_date(target_date)
        return f"{year}{month:02d}"

    @classmethod
    def get_local_symbol(cls, symbol: str, target_date: datetime) -> str:
        """
        Get the local symbol for a futures contract (e.g., ESZ2025).

        DEPRECATED: Use get_active_local_symbol() instead for rollover awareness.

        Args:
            symbol: Base symbol (e.g., 'ES')
            target_date: The date for which to find the contract

        Returns:
            Local symbol string (e.g., 'ESZ2025')

        Example:
            ('ES', 2025-10-13) -> "ESZ2025"
            ('ES', 2025-09-10) -> "ESU2025" (may be expired!)
        """
        logger.warning(
            "get_local_symbol() is deprecated. "
            "Use get_active_local_symbol() for rollover awareness."
        )
        year, month = cls.get_contract_month_for_date(target_date)
        month_code = cls.MONTH_CODES[month]
        return f"{symbol}{month_code}{year}"

    @classmethod
    def get_all_contract_months_in_range(
        cls,
        start_date: datetime,
        end_date: datetime
    ) -> list[Tuple[int, int]]:
        """
        Get all quarterly contract months within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of (year, month) tuples for all contracts in the range

        Example:
            (2025-01-01, 2025-12-31) -> [(2025, 3), (2025, 6), (2025, 9), (2025, 12)]
        """
        contracts = []
        current_year = start_date.year
        end_year = end_date.year

        while current_year <= end_year:
            for month in cls.ES_EXPIRY_MONTHS:
                # Check if this contract month falls within our range
                contract_date = datetime(current_year, month, 1)
                if start_date <= contract_date <= end_date:
                    contracts.append((current_year, month))
            current_year += 1

        return contracts


def get_es_contract_for_date(target_date: datetime) -> dict:
    """
    Get ES futures contract specification for a given date.

    Args:
        target_date: The date for which to create the contract

    Returns:
        Dictionary with contract specifications ready for IB API

    Example:
        >>> get_es_contract_for_date(datetime(2025, 10, 13))
        {
            'symbol': 'ES',
            'secType': 'FUT',
            'exchange': 'CME',
            'currency': 'USD',
            'lastTradeDateOrContractMonth': '202512'
        }
    """
    utils = FuturesContractUtils()
    contract_month = utils.get_contract_string(target_date)

    return {
        'symbol': 'ES',
        'secType': 'FUT',
        'exchange': 'CME',
        'currency': 'USD',
        'lastTradeDateOrContractMonth': contract_month
    }


if __name__ == "__main__":
    # Test the utilities
    test_dates = [
        datetime(2025, 10, 13),
        datetime(2025, 10, 1),
        datetime(2025, 9, 13),
        datetime(2025, 8, 13),
        datetime(2025, 7, 13),
        datetime(2025, 6, 13),
        datetime(2025, 1, 13),
        datetime(2024, 10, 13),
    ]

    utils = FuturesContractUtils()

    print("ES Futures Contract Month Calculator")
    print("=" * 70)

    for date in test_dates:
        contract_month = utils.get_contract_string(date)
        local_symbol = utils.get_local_symbol('ES', date)
        year, month = utils.get_contract_month_for_date(date)

        print(f"{date.strftime('%Y-%m-%d')} -> "
              f"Contract: {contract_month} | "
              f"Local Symbol: {local_symbol} | "
              f"Expiry: {year}-{month:02d}")

    print("\n" + "=" * 70)
    print("All contracts in 2025:")
    contracts = utils.get_all_contract_months_in_range(
        datetime(2025, 1, 1),
        datetime(2025, 12, 31)
    )
    for year, month in contracts:
        month_code = utils.MONTH_CODES[month]
        print(f"  ES{month_code}{year} ({year}-{month:02d})")
