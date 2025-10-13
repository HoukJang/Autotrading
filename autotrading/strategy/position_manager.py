"""
Position Manager

Tracks active positions and enforces total exposure limits.
"""

from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime


@dataclass
class Position:
    """
    Active trading position.
    """
    id: str
    signal_id: str
    trigger_name: str
    direction: str  # 'LONG' or 'SHORT'
    size: int  # Number of contracts
    entry_price: float
    tp: float
    sl: float
    entry_time: datetime


class PositionManager:
    """
    Manages active positions and enforces exposure limits.

    Features:
    - Tracks current total position size
    - Enforces maximum exposure limit
    - Manages position lifecycle
    """

    def __init__(self):
        """Initialize position manager."""
        self.positions: Dict[str, Position] = {}

    def can_open_position(
        self,
        size: int,
        max_total_size: int
    ) -> bool:
        """
        Check if new position can be opened within limits.

        Args:
            size: Requested position size
            max_total_size: Maximum total position size allowed

        Returns:
            True if position can be opened
        """
        current_total = self.get_total_position_size()

        return (current_total + size) <= max_total_size

    def open_position(
        self,
        position_id: str,
        signal_id: str,
        trigger_name: str,
        direction: str,
        size: int,
        entry_price: float,
        tp: float,
        sl: float,
        entry_time: datetime,
    ):
        """
        Open a new position.

        Args:
            position_id: Unique position ID
            signal_id: Associated signal ID
            trigger_name: Trigger that generated this position
            direction: 'LONG' or 'SHORT'
            size: Number of contracts
            entry_price: Entry price
            tp: Take profit
            sl: Stop loss
            entry_time: Entry timestamp
        """
        position = Position(
            id=position_id,
            signal_id=signal_id,
            trigger_name=trigger_name,
            direction=direction,
            size=size,
            entry_price=entry_price,
            tp=tp,
            sl=sl,
            entry_time=entry_time,
        )

        self.positions[position_id] = position

    def close_position(self, position_id: str):
        """
        Close a position.

        Args:
            position_id: Position ID to close
        """
        if position_id in self.positions:
            del self.positions[position_id]

    def get_total_position_size(self) -> int:
        """
        Get current total position size.

        Returns:
            Total number of contracts currently held
        """
        return sum(pos.size for pos in self.positions.values())

    def get_net_position(self) -> int:
        """
        Get net position (LONG - SHORT).

        Returns:
            Net position size (positive = net LONG, negative = net SHORT)
        """
        long_size = sum(pos.size for pos in self.positions.values() if pos.direction == 'LONG')
        short_size = sum(pos.size for pos in self.positions.values() if pos.direction == 'SHORT')

        return long_size - short_size

    def get_positions_by_trigger(self, trigger_name: str) -> List[Position]:
        """
        Get all positions from a specific trigger.

        Args:
            trigger_name: Trigger name

        Returns:
            List of positions
        """
        return [
            pos for pos in self.positions.values()
            if pos.trigger_name == trigger_name
        ]

    def get_active_positions(self) -> List[Position]:
        """
        Get all active positions.

        Returns:
            List of all positions
        """
        return list(self.positions.values())

    def get_statistics(self) -> Dict:
        """
        Get position statistics.

        Returns:
            Statistics dictionary
        """
        positions = list(self.positions.values())

        if len(positions) == 0:
            return {
                'total_positions': 0,
                'total_size': 0,
                'net_position': 0,
                'long_size': 0,
                'short_size': 0,
            }

        long_size = sum(pos.size for pos in positions if pos.direction == 'LONG')
        short_size = sum(pos.size for pos in positions if pos.direction == 'SHORT')

        return {
            'total_positions': len(positions),
            'total_size': long_size + short_size,
            'net_position': long_size - short_size,
            'long_size': long_size,
            'short_size': short_size,
        }
