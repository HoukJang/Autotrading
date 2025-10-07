"""
Custom Exceptions for Trading System
Provides specific exception types for different error scenarios
"""

from typing import Optional, Any, Dict
from datetime import datetime


class TradingSystemError(Exception):
    """Base exception for trading system"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        component: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize trading system error

        Args:
            message: Error message
            error_code: Optional error code
            component: Component where error occurred
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.component = component
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'component': self.component,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


class ConnectionError(TradingSystemError):
    """Connection-related errors"""

    def __init__(
        self,
        message: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        retry_count: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize connection error

        Args:
            message: Error message
            host: Connection host
            port: Connection port
            retry_count: Number of retry attempts
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'host': host,
            'port': port,
            'retry_count': retry_count
        })
        kwargs['details'] = details
        super().__init__(message, component='connection', **kwargs)


class DataError(TradingSystemError):
    """Data-related errors"""

    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        data_type: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        **kwargs
    ):
        """
        Initialize data error

        Args:
            message: Error message
            symbol: Trading symbol
            data_type: Type of data
            timestamp: Data timestamp
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'symbol': symbol,
            'data_type': data_type,
            'data_timestamp': timestamp.isoformat() if timestamp else None
        })
        kwargs['details'] = details
        super().__init__(message, component='data', **kwargs)


class RiskError(TradingSystemError):
    """Risk management errors"""

    def __init__(
        self,
        message: str,
        risk_type: Optional[str] = None,
        current_value: Optional[float] = None,
        threshold: Optional[float] = None,
        symbol: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize risk error

        Args:
            message: Error message
            risk_type: Type of risk violation
            current_value: Current risk value
            threshold: Risk threshold exceeded
            symbol: Trading symbol
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'risk_type': risk_type,
            'current_value': current_value,
            'threshold': threshold,
            'symbol': symbol
        })
        kwargs['details'] = details
        super().__init__(message, component='risk', **kwargs)


class StrategyError(TradingSystemError):
    """Strategy-related errors"""

    def __init__(
        self,
        message: str,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        signal_type: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize strategy error

        Args:
            message: Error message
            strategy_id: Strategy identifier
            symbol: Trading symbol
            signal_type: Type of signal
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'strategy_id': strategy_id,
            'symbol': symbol,
            'signal_type': signal_type
        })
        kwargs['details'] = details
        super().__init__(message, component='strategy', **kwargs)


class OrderError(TradingSystemError):
    """Order execution errors"""

    def __init__(
        self,
        message: str,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        order_type: Optional[str] = None,
        quantity: Optional[int] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize order error

        Args:
            message: Error message
            order_id: Order identifier
            symbol: Trading symbol
            order_type: Type of order
            quantity: Order quantity
            reason: Reason for order error
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'order_id': order_id,
            'symbol': symbol,
            'order_type': order_type,
            'quantity': quantity,
            'reason': reason
        })
        kwargs['details'] = details
        super().__init__(message, component='execution', **kwargs)


class ConfigurationError(TradingSystemError):
    """Configuration errors"""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize configuration error

        Args:
            message: Error message
            config_key: Configuration key
            expected_type: Expected value type
            actual_value: Actual value found
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'config_key': config_key,
            'expected_type': expected_type,
            'actual_value': str(actual_value)
        })
        kwargs['details'] = details
        super().__init__(message, component='configuration', **kwargs)


class DatabaseError(TradingSystemError):
    """Database-related errors"""

    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        table: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize database error

        Args:
            message: Error message
            query: SQL query that failed
            table: Database table
            operation: Database operation
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'query': query,
            'table': table,
            'operation': operation
        })
        kwargs['details'] = details
        super().__init__(message, component='database', **kwargs)


class ValidationError(TradingSystemError):
    """Data validation errors"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize validation error

        Args:
            message: Error message
            field: Field that failed validation
            expected: Expected value/type
            actual: Actual value received
            **kwargs: Additional arguments
        """
        details = kwargs.get('details', {})
        details.update({
            'field': field,
            'expected': str(expected),
            'actual': str(actual)
        })
        kwargs['details'] = details
        super().__init__(message, component='validation', **kwargs)