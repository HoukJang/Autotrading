"""Core exception hierarchy for AutoTrader v2.

This module defines the complete exception hierarchy used throughout AutoTrader
for error handling and exception propagation.
"""


class AutoTraderError(Exception):
    """Base exception class for all AutoTrader errors.

    All AutoTrader-specific exceptions inherit from this class,
    allowing callers to catch all framework errors with a single except clause.
    """


class ConfigError(AutoTraderError):
    """Configuration-related errors.

    Raised when there are issues with configuration files, invalid settings,
    missing required parameters, or configuration validation failures.
    """


class BrokerError(AutoTraderError):
    """Broker communication and operation errors.

    Base class for all broker-related errors including connection issues
    and order execution problems.
    """


class ConnectionError(BrokerError):
    """Broker connection failures.

    Raised when the connection to a broker API fails, times out, or becomes
    unexpectedly disconnected.

    Attributes:
        broker: Name of the broker that failed to connect.
        reason: Detailed reason for the connection failure.
    """

    def __init__(self, broker: str, reason: str):
        """Initialize ConnectionError with broker and reason details.

        Args:
            broker: Name of the broker (e.g., "Alpaca", "Interactive Brokers").
            reason: Description of why the connection failed.
        """
        super().__init__(f"[{broker}] Connection failed: {reason}")
        self.broker = broker
        self.reason = reason


class OrderError(BrokerError):
    """Order submission and execution errors.

    Raised when an order fails to submit, gets rejected, or encounters
    execution issues at the broker.

    Attributes:
        symbol: Trading symbol of the problematic order.
        reason: Detailed reason for the order failure.
    """

    def __init__(self, symbol: str, reason: str):
        """Initialize OrderError with symbol and reason details.

        Args:
            symbol: Trading symbol (e.g., "AAPL", "BTC/USD").
            reason: Description of why the order failed (e.g., "insufficient buying power").
        """
        super().__init__(f"[{symbol}] Order error: {reason}")
        self.symbol = symbol
        self.reason = reason


class RiskLimitError(AutoTraderError):
    """Risk limit exceeded during trading operations.

    Raised when a trade or position violates configured risk management rules
    such as position size limits, daily loss limits, or sector concentration rules.

    Attributes:
        rule: Name of the risk rule that was violated.
        detail: Specific details about the limit violation.
    """

    def __init__(self, rule: str, detail: str):
        """Initialize RiskLimitError with rule and detail information.

        Args:
            rule: Name of the risk management rule (e.g., "max_position_size", "daily_loss_limit").
            detail: Specific information about what was exceeded and by how much.
        """
        super().__init__(f"Risk limit [{rule}]: {detail}")
        self.rule = rule
        self.detail = detail


class DataError(AutoTraderError):
    """Data pipeline and processing errors.

    Raised when there are failures in data fetching, processing, validation,
    or any other data pipeline operations.
    """


class StrategyError(AutoTraderError):
    """Strategy execution and logic errors.

    Raised when a strategy fails to initialize, execute, or encounters
    runtime errors during signal generation or analysis.
    """
