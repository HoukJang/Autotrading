"""
Structured Logging System
JSON-formatted logging with rotation and environment-specific configuration
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import json
from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TradingLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for trading system logs"""

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        """Add custom fields to log record"""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record['timestamp'] = datetime.now().isoformat()

        # Add environment
        log_record['environment'] = os.getenv('ENVIRONMENT', 'development')

        # Add component if available
        if hasattr(record, 'component'):
            log_record['component'] = record.component

        # Add event_type if available
        if hasattr(record, 'event_type'):
            log_record['event_type'] = record.event_type

        # Add trading-specific fields if available
        for field in ['symbol', 'strategy_id', 'order_id', 'position', 'pnl']:
            if hasattr(record, field):
                log_record[field] = getattr(record, field)

        # Remove redundant fields
        for field in ['asctime', 'created', 'msecs', 'relativeCreated']:
            log_record.pop(field, None)


class TradingLogger:
    """Trading system logger with structured JSON output"""

    _instance: Optional['TradingLogger'] = None
    _loggers: Dict[str, logging.Logger] = {}

    def __new__(cls) -> 'TradingLogger':
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize logging system"""
        if self._initialized:
            return

        self._initialized = True
        self.setup_logging()

    def setup_logging(self) -> None:
        """Setup logging configuration"""
        # Get configuration from environment
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        log_file = os.getenv('LOG_FILE', 'logs/trading_system.log')
        max_bytes = int(os.getenv('LOG_MAX_BYTES', 104857600))  # 100MB default
        backup_count = int(os.getenv('LOG_BACKUP_COUNT', 10))

        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create formatter
        formatter = TradingLogFormatter(
            '%(timestamp)s %(name)s %(levelname)s %(message)s'
        )

        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level))

        # Remove existing handlers
        root_logger.handlers = []

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Console handler for development
        if os.getenv('ENVIRONMENT') == 'development':
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            root_logger.addHandler(console_handler)

        # Add specific handlers for critical components
        self._setup_component_loggers()

        # Log startup message
        root_logger.info(
            "Trading system logging initialized",
            extra={
                'component': 'logger',
                'log_level': log_level,
                'log_file': str(log_file),
                'environment': os.getenv('ENVIRONMENT', 'development')
            }
        )

    def _setup_component_loggers(self) -> None:
        """Setup component-specific loggers"""
        components = [
            ('trading.ib', 'IB API operations'),
            ('trading.strategy', 'Strategy execution'),
            ('trading.risk', 'Risk management'),
            ('trading.data', 'Market data processing'),
            ('trading.execution', 'Order execution'),
            ('trading.performance', 'Performance tracking')
        ]

        for name, description in components:
            logger = logging.getLogger(name)
            logger.info(f"Component logger initialized: {description}")
            self._loggers[name] = logger

    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger instance

        Args:
            name: Logger name

        Returns:
            Logger instance
        """
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        self._loggers[name] = logger
        return logger

    def log_trade(
        self,
        action: str,
        symbol: str,
        quantity: int,
        price: float,
        order_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log trading activity

        Args:
            action: Trade action (BUY/SELL)
            symbol: Trading symbol
            quantity: Trade quantity
            price: Trade price
            order_id: Order ID
            strategy_id: Strategy ID
            metadata: Additional metadata
        """
        logger = self.get_logger('trading.execution')
        logger.info(
            f"Trade executed: {action} {quantity} {symbol} @ {price}",
            extra={
                'component': 'execution',
                'event_type': 'TRADE',
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'order_id': order_id,
                'strategy_id': strategy_id,
                'metadata': metadata or {}
            }
        )

    def log_risk_event(
        self,
        risk_type: str,
        severity: str,
        message: str,
        symbol: Optional[str] = None,
        position: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log risk management event

        Args:
            risk_type: Type of risk event
            severity: Severity level
            message: Risk message
            symbol: Trading symbol
            position: Current position
            metadata: Additional metadata
        """
        logger = self.get_logger('trading.risk')
        log_method = getattr(logger, severity.lower(), logger.warning)

        log_method(
            f"Risk event: {risk_type} - {message}",
            extra={
                'component': 'risk',
                'event_type': 'RISK',
                'risk_type': risk_type,
                'symbol': symbol,
                'position': position,
                'metadata': metadata or {}
            }
        )

    def log_performance(
        self,
        pnl: float,
        trades: int,
        win_rate: float,
        sharpe_ratio: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log performance metrics

        Args:
            pnl: Profit and loss
            trades: Number of trades
            win_rate: Win rate percentage
            sharpe_ratio: Sharpe ratio
            metadata: Additional metadata
        """
        logger = self.get_logger('trading.performance')
        logger.info(
            f"Performance update: PnL={pnl:.2f}, Trades={trades}, WinRate={win_rate:.2%}",
            extra={
                'component': 'performance',
                'event_type': 'PERFORMANCE',
                'pnl': pnl,
                'trades': trades,
                'win_rate': win_rate,
                'sharpe_ratio': sharpe_ratio,
                'metadata': metadata or {}
            }
        )

    def rotate_logs(self) -> None:
        """Manually rotate log files"""
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.doRollover()
                logging.info("Log files rotated manually")


# Create singleton instance
_trading_logger = TradingLogger()


def get_logger(name: str = 'trading') -> logging.Logger:
    """
    Get a logger instance

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return _trading_logger.get_logger(name)


# Export main functions
log_trade = _trading_logger.log_trade
log_risk_event = _trading_logger.log_risk_event
log_performance = _trading_logger.log_performance