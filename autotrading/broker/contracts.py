"""
Contract Definitions for Interactive Brokers
Defines futures contracts and contract factory
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from ib_async import Future


@dataclass
class FuturesContract:
    """Futures contract specification"""
    symbol: str
    exchange: str
    currency: str = "USD"
    multiplier: int = 50  # Default for ES
    tick_size: Decimal = Decimal("0.25")
    expiry: Optional[str] = None  # YYYYMM format
    local_symbol: Optional[str] = None

    def to_ib_contract(self) -> Future:
        """Convert to IB Future contract"""
        contract = Future(
            symbol=self.symbol,
            exchange=self.exchange,
            currency=self.currency
        )

        if self.expiry:
            contract.lastTradeDateOrContractMonth = self.expiry

        if self.local_symbol:
            contract.localSymbol = self.local_symbol

        return contract


class ContractFactory:
    """Factory for creating common contracts"""

    # Predefined futures contracts
    FUTURES_SPECS = {
        'ES': {
            'name': 'E-mini S&P 500',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 50,
            'tick_size': Decimal('0.25'),
            'min_tick_value': Decimal('12.50')
        },
        'NQ': {
            'name': 'E-mini NASDAQ-100',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 20,
            'tick_size': Decimal('0.25'),
            'min_tick_value': Decimal('5.00')
        },
        'YM': {
            'name': 'E-mini Dow',
            'exchange': 'CBOT',
            'currency': 'USD',
            'multiplier': 5,
            'tick_size': Decimal('1.00'),
            'min_tick_value': Decimal('5.00')
        },
        'RTY': {
            'name': 'E-mini Russell 2000',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 50,
            'tick_size': Decimal('0.10'),
            'min_tick_value': Decimal('5.00')
        },
        'MES': {
            'name': 'Micro E-mini S&P 500',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 5,
            'tick_size': Decimal('0.25'),
            'min_tick_value': Decimal('1.25')
        },
        'MNQ': {
            'name': 'Micro E-mini NASDAQ-100',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 2,
            'tick_size': Decimal('0.25'),
            'min_tick_value': Decimal('0.50')
        },
        'CL': {
            'name': 'Crude Oil',
            'exchange': 'NYMEX',
            'currency': 'USD',
            'multiplier': 1000,
            'tick_size': Decimal('0.01'),
            'min_tick_value': Decimal('10.00')
        },
        'GC': {
            'name': 'Gold',
            'exchange': 'COMEX',
            'currency': 'USD',
            'multiplier': 100,
            'tick_size': Decimal('0.10'),
            'min_tick_value': Decimal('10.00')
        },
        '6E': {
            'name': 'Euro FX',
            'exchange': 'CME',
            'currency': 'USD',
            'multiplier': 125000,
            'tick_size': Decimal('0.00005'),
            'min_tick_value': Decimal('6.25')
        }
    }

    @classmethod
    def create_futures(cls, symbol: str, expiry: Optional[str] = None) -> FuturesContract:
        """
        Create a futures contract

        Args:
            symbol: Futures symbol (e.g., 'ES', 'NQ')
            expiry: Contract expiry in YYYYMM format, None for continuous

        Returns:
            FuturesContract instance
        """
        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        spec = cls.FUTURES_SPECS[symbol]

        return FuturesContract(
            symbol=symbol,
            exchange=spec['exchange'],
            currency=spec['currency'],
            multiplier=spec['multiplier'],
            tick_size=spec['tick_size'],
            expiry=expiry
        )

    @classmethod
    def get_front_month_expiry(cls, reference_date: datetime = None) -> str:
        """
        Calculate the front month expiry for CME index futures.
        
        CME E-mini futures expire on the 3rd Friday of contract months (H, M, U, Z).
        Contract months: March (H), June (M), September (U), December (Z)
        
        Args:
            reference_date: Date to calculate from (default: now)
            
        Returns:
            Front month expiry in YYYYMM format
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        # Contract months: 3, 6, 9, 12 (March, June, September, December)
        contract_months = [3, 6, 9, 12]
        
        current_year = reference_date.year
        current_month = reference_date.month
        
        # Find the next contract month
        for month in contract_months:
            if month >= current_month:
                # Check if we're past the 3rd Friday of this month
                third_friday = cls._get_third_friday(current_year, month)
                if reference_date.date() <= third_friday:
                    return f"{current_year}{month:02d}"
        
        # Next year's first contract (March)
        return f"{current_year + 1}03"
    
    @staticmethod
    def _get_third_friday(year: int, month: int):
        """Get the 3rd Friday of a given month."""
        from calendar import monthcalendar
        cal = monthcalendar(year, month)
        # Find all Fridays (index 4 in week)
        fridays = [week[4] for week in cal if week[4] != 0]
        return datetime(year, month, fridays[2]).date()

    @classmethod
    def create_es_futures(cls, expiry: Optional[str] = None) -> FuturesContract:
        """Create ES (E-mini S&P 500) futures contract"""
        if expiry is None:
            expiry = cls.get_front_month_expiry()
        return cls.create_futures('ES', expiry)

    @classmethod
    def create_continuous_futures(cls, symbol: str) -> Future:
        """
        Create continuous futures contract for market data

        Args:
            symbol: Futures symbol

        Returns:
            IB Future contract
        """
        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        spec = cls.FUTURES_SPECS[symbol]

        contract = Future(
            symbol=symbol,
            exchange=spec['exchange'],
            currency=spec['currency']
        )

        # Set to continuous contract
        contract.includeExpired = False

        return contract

    @classmethod
    def get_contract_specs(cls, symbol: str) -> Dict[str, Any]:
        """
        Get contract specifications

        Args:
            symbol: Futures symbol

        Returns:
            Contract specifications dictionary
        """
        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        return cls.FUTURES_SPECS[symbol].copy()

    @classmethod
    def calculate_tick_value(cls, symbol: str, price: Decimal, ticks: int = 1) -> Decimal:
        """
        Calculate value of tick movement

        Args:
            symbol: Futures symbol
            price: Current price (not used for futures, but kept for compatibility)
            ticks: Number of ticks

        Returns:
            Dollar value of tick movement
        """
        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        spec = cls.FUTURES_SPECS[symbol]
        return Decimal(str(ticks)) * spec['min_tick_value']

    @classmethod
    def calculate_position_value(cls, symbol: str, price: Decimal, quantity: int) -> Decimal:
        """
        Calculate total position value

        Args:
            symbol: Futures symbol
            price: Current price
            quantity: Number of contracts

        Returns:
            Total position value in dollars
        """
        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        spec = cls.FUTURES_SPECS[symbol]
        return price * Decimal(str(quantity)) * Decimal(str(spec['multiplier']))

    @classmethod
    def get_margin_requirement(cls, symbol: str, is_day_trading: bool = True) -> Decimal:
        """
        Get approximate margin requirement per contract

        Args:
            symbol: Futures symbol
            is_day_trading: Whether day trading margins apply

        Returns:
            Approximate margin requirement
        """
        # These are approximate values - actual margins vary by broker and market conditions
        DAY_MARGINS = {
            'ES': Decimal('500'),
            'NQ': Decimal('500'),
            'YM': Decimal('500'),
            'RTY': Decimal('500'),
            'MES': Decimal('50'),
            'MNQ': Decimal('50'),
            'CL': Decimal('1000'),
            'GC': Decimal('1000'),
            '6E': Decimal('1000')
        }

        OVERNIGHT_MARGINS = {
            'ES': Decimal('13200'),
            'NQ': Decimal('16500'),
            'YM': Decimal('8800'),
            'RTY': Decimal('7150'),
            'MES': Decimal('1320'),
            'MNQ': Decimal('1650'),
            'CL': Decimal('5000'),
            'GC': Decimal('8000'),
            '6E': Decimal('2200')
        }

        if symbol not in cls.FUTURES_SPECS:
            raise ValueError(f"Unknown futures symbol: {symbol}")

        margins = DAY_MARGINS if is_day_trading else OVERNIGHT_MARGINS
        return margins.get(symbol, Decimal('5000'))  # Default margin

    @classmethod
    def is_market_hours(cls, symbol: str, dt: datetime = None) -> bool:
        """
        Check if market is open for trading

        Args:
            symbol: Futures symbol
            dt: Datetime to check (default: now)

        Returns:
            True if market is open
        """
        if dt is None:
            dt = datetime.now()

        # Simplified market hours (actual hours vary by product)
        # Most futures trade Sunday 6PM - Friday 5PM ET with breaks

        weekday = dt.weekday()
        hour = dt.hour

        # Closed on Saturday
        if weekday == 5:
            return False

        # Sunday opens at 6PM ET (23:00 UTC)
        if weekday == 6 and hour < 23:
            return False

        # Friday closes at 5PM ET (22:00 UTC)
        if weekday == 4 and hour >= 22:
            return False

        # Daily maintenance break (varies by product)
        # Simplified: 5PM - 6PM ET (22:00 - 23:00 UTC)
        if hour == 22:
            return False

        return True