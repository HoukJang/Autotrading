"""
Event Definitions for Trading System
Defines all event types used in the event-driven architecture
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import uuid


class EventType(Enum):
    """Event type enumeration"""
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    RISK = "RISK"
    SYSTEM = "SYSTEM"
    POSITION = "POSITION"
    PERFORMANCE = "PERFORMANCE"


class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    CLOSE_ALL = "CLOSE_ALL"


class OrderAction(Enum):
    """Order action types"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order types"""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"
    TRAILING_STOP = "TRAIL"
    BRACKET = "BRACKET"


class OrderStatus(Enum):
    """Order status"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class RiskLevel(Enum):
    """Risk severity levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SystemSeverity(Enum):
    """System event severity"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class Event:
    """Base event class"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.SYSTEM
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'metadata': self.metadata
        }


@dataclass
class MarketBar:
    """Market bar data"""
    symbol: str
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    vwap: Optional[Decimal] = None
    tick_count: Optional[int] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    spread: Optional[Decimal] = None

    def __post_init__(self):
        """Calculate spread if bid and ask are available"""
        if self.bid and self.ask:
            self.spread = self.ask - self.bid


@dataclass
class MarketDataEvent(Event):
    """Market data event containing bar information"""
    symbol: str = ""
    bar: Optional[MarketBar] = None
    bars: List[MarketBar] = field(default_factory=list)  # For multiple bars

    def __post_init__(self):
        self.event_type = EventType.MARKET_DATA
        if self.bar:
            self.symbol = self.bar.symbol
            self.timestamp = self.bar.timestamp


@dataclass
class Signal:
    """Trading signal data"""
    strategy_id: str
    symbol: str
    signal_type: SignalType
    quantity: int
    price: Decimal
    confidence: float = 1.0  # 0.0 to 1.0
    stop_loss_levels: List[Tuple[Decimal, int]] = field(default_factory=list)
    take_profit_levels: List[Tuple[Decimal, int]] = field(default_factory=list)
    trailing_stop: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalEvent(Event):
    """Signal event from strategy"""
    signal: Optional[Signal] = None

    def __post_init__(self):
        self.event_type = EventType.SIGNAL
        if self.signal:
            self.source = self.signal.strategy_id


@dataclass
class Order:
    """Order data"""
    order_id: str
    symbol: str
    action: OrderAction
    order_type: OrderType
    quantity: int
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    parent_order_id: Optional[str] = None
    parent_signal_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    fill_price: Optional[Decimal] = None
    fill_quantity: int = 0
    commission: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderEvent(Event):
    """Order event"""
    order: Optional[Order] = None
    orders: List[Order] = field(default_factory=list)  # For bracket orders

    def __post_init__(self):
        self.event_type = EventType.ORDER


@dataclass
class Fill:
    """Order fill data"""
    fill_id: str
    order_id: str
    symbol: str
    action: OrderAction
    quantity: int
    fill_price: Decimal
    commission: Decimal
    realized_pnl: Optional[Decimal] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FillEvent(Event):
    """Fill event when order is executed"""
    fill: Optional[Fill] = None

    def __post_init__(self):
        self.event_type = EventType.FILL
        if self.fill:
            self.timestamp = self.fill.timestamp


@dataclass
class RiskAlert:
    """Risk alert data"""
    risk_type: str
    risk_level: RiskLevel
    symbol: Optional[str] = None
    message: str = ""
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    action_required: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskEvent(Event):
    """Risk management event"""
    alert: Optional[RiskAlert] = None

    def __post_init__(self):
        self.event_type = EventType.RISK
        self.source = "RiskManager"


@dataclass
class SystemInfo:
    """System information data"""
    component: str
    severity: SystemSeverity
    message: str
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemEvent(Event):
    """System-level event"""
    info: Optional[SystemInfo] = None

    def __post_init__(self):
        self.event_type = EventType.SYSTEM
        if self.info:
            self.source = self.info.component


@dataclass
class Position:
    """Position data"""
    symbol: str
    quantity: int  # Positive for long, negative for short
    avg_cost: Decimal
    market_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Decimal = Decimal("0")
    commission_paid: Decimal = Decimal("0")

    def __post_init__(self):
        """Calculate market value and unrealized P&L"""
        if self.market_price:
            self.market_value = self.market_price * abs(self.quantity)
            if self.quantity != 0:
                if self.quantity > 0:  # Long position
                    self.unrealized_pnl = (self.market_price - self.avg_cost) * self.quantity
                else:  # Short position
                    self.unrealized_pnl = (self.avg_cost - self.market_price) * abs(self.quantity)


@dataclass
class PositionEvent(Event):
    """Position update event"""
    position: Optional[Position] = None
    positions: List[Position] = field(default_factory=list)

    def __post_init__(self):
        self.event_type = EventType.POSITION
        self.source = "PositionManager"


@dataclass
class Performance:
    """Performance metrics data"""
    date: datetime
    total_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[Decimal] = None
    portfolio_value: Decimal = Decimal("0")


@dataclass
class PerformanceEvent(Event):
    """Performance update event"""
    performance: Optional[Performance] = None

    def __post_init__(self):
        self.event_type = EventType.PERFORMANCE
        self.source = "PerformanceManager"