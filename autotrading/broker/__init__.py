"""
Broker Module - Interactive Brokers API Integration
Handles connection management, market data, and order execution
"""

from .connection_manager import IBConnectionManager
from .ib_client import IBClient
from .contracts import ContractFactory, FuturesContract

__all__ = [
    'IBConnectionManager',
    'IBClient',
    'ContractFactory',
    'FuturesContract'
]