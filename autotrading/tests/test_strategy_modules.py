"""
Unit tests for Strategy modules.

Tests for:
- BudgetAllocator
- LossLimitManager
- PositionManager
"""

import pytest
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add autotrading parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autotrading.strategy.budget_allocator import BudgetAllocator
from autotrading.strategy.loss_limit_manager import LossLimitManager, TradeResult
from autotrading.strategy.position_manager import PositionManager, Position


class TestBudgetAllocator:
    """Tests for BudgetAllocator class."""

    def test_init_default_values(self):
        """Test default initialization values."""
        allocator = BudgetAllocator()
        
        assert allocator.risk_percentage == 0.02
        assert allocator.contract_value == 15000.0

    def test_init_custom_values(self):
        """Test custom initialization values."""
        allocator = BudgetAllocator(
            risk_percentage=0.05,
            contract_value=20000.0
        )
        
        assert allocator.risk_percentage == 0.05
        assert allocator.contract_value == 20000.0

    def test_calculate_total_budget(self):
        """Test total budget calculation."""
        allocator = BudgetAllocator(risk_percentage=0.02)
        
        # $100,000 account * 2% = $2,000
        budget = allocator.calculate_total_budget(100000.0)
        assert budget == 2000.0
        
        # $50,000 account * 2% = $1,000
        budget = allocator.calculate_total_budget(50000.0)
        assert budget == 1000.0

    def test_calculate_total_position_size(self):
        """Test position size calculation."""
        allocator = BudgetAllocator(
            risk_percentage=0.02,
            contract_value=15000.0
        )
        
        # $100,000 * 2% = $2,000 / $15,000 = 0.13 -> max(1, 0) = 1
        size = allocator.calculate_total_position_size(100000.0)
        assert size == 1
        
        # $1,000,000 * 2% = $20,000 / $15,000 = 1.33 -> 1
        size = allocator.calculate_total_position_size(1000000.0)
        assert size == 1
        
        # $10,000,000 * 2% = $200,000 / $15,000 = 13.33 -> 13
        size = allocator.calculate_total_position_size(10000000.0)
        assert size == 13

    def test_calculate_position_size_minimum_one(self):
        """Test that minimum position size is 1."""
        allocator = BudgetAllocator(
            risk_percentage=0.01,
            contract_value=50000.0
        )
        
        # Small account should still get at least 1 contract
        size = allocator.calculate_total_position_size(10000.0)
        assert size == 1

    def test_allocate_proportionally(self):
        """Test proportional allocation based on scores."""
        allocator = BudgetAllocator(
            risk_percentage=0.02,
            contract_value=1000.0  # Low contract value for easier math
        )
        
        trigger_scores = {
            'trigger_a': 0.6,
            'trigger_b': 0.4,
        }
        
        # $100,000 * 2% = $2,000 / $1,000 = 2 contracts
        allocation = allocator.allocate(trigger_scores, 100000.0)
        
        # trigger_a: 0.6 / 1.0 * 2 = 1.2
        # trigger_b: 0.4 / 1.0 * 2 = 0.8
        assert allocation['trigger_a'] == pytest.approx(1.2)
        assert allocation['trigger_b'] == pytest.approx(0.8)

    def test_allocate_with_negative_scores(self):
        """Test allocation treats negative scores as zero."""
        allocator = BudgetAllocator(
            risk_percentage=0.02,
            contract_value=1000.0
        )
        
        trigger_scores = {
            'trigger_a': 0.8,
            'trigger_b': -0.2,  # Negative score
        }
        
        allocation = allocator.allocate(trigger_scores, 100000.0)
        
        # trigger_a gets all (negative treated as 0)
        # 0.8 / 0.8 * 2 = 2
        assert allocation['trigger_a'] == pytest.approx(2.0)
        assert allocation['trigger_b'] == pytest.approx(0.0)

    def test_allocate_all_zero_scores(self):
        """Test equal allocation when all scores are zero or negative."""
        allocator = BudgetAllocator(
            risk_percentage=0.02,
            contract_value=1000.0
        )
        
        trigger_scores = {
            'trigger_a': 0.0,
            'trigger_b': -0.5,
            'trigger_c': 0.0,
        }
        
        allocation = allocator.allocate(trigger_scores, 100000.0)
        
        # Equal allocation: 2 contracts / 3 triggers = 0.667 each
        expected = 2.0 / 3.0
        assert allocation['trigger_a'] == pytest.approx(expected)
        assert allocation['trigger_b'] == pytest.approx(expected)
        assert allocation['trigger_c'] == pytest.approx(expected)

    def test_get_budget_info(self):
        """Test budget info retrieval."""
        allocator = BudgetAllocator(
            risk_percentage=0.02,
            contract_value=15000.0
        )
        
        info = allocator.get_budget_info(100000.0)
        
        assert info['account_balance'] == 100000.0
        assert info['risk_percentage'] == 0.02
        assert info['total_budget'] == 2000.0
        assert info['contract_value'] == 15000.0
        assert info['total_position_size'] == 1


class TestLossLimitManager:
    """Tests for LossLimitManager class."""

    def test_init_default_values(self):
        """Test default initialization."""
        manager = LossLimitManager()
        
        assert manager.max_consecutive_losses == 3
        assert manager.pause_minutes == 30
        assert manager.consecutive_losses == 0
        assert manager.pause_until is None

    def test_init_custom_values(self):
        """Test custom initialization."""
        manager = LossLimitManager(
            max_consecutive_losses=5,
            pause_minutes=60
        )
        
        assert manager.max_consecutive_losses == 5
        assert manager.pause_minutes == 60

    def test_record_winning_trade(self):
        """Test recording a winning trade."""
        manager = LossLimitManager()
        now = datetime.now()
        
        manager.record_trade(now, 'TP', 100.0)
        
        assert len(manager.trade_history) == 1
        assert manager.consecutive_losses == 0
        assert manager.pause_until is None

    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        manager = LossLimitManager()
        now = datetime.now()
        
        manager.record_trade(now, 'SL', -50.0)
        
        assert len(manager.trade_history) == 1
        assert manager.consecutive_losses == 1

    def test_consecutive_losses_trigger_pause(self):
        """Test that consecutive losses trigger a pause."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # 3 consecutive losses
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'SL', -50.0)
        
        assert manager.consecutive_losses == 3
        assert manager.pause_until is not None
        assert manager.pause_until == now + timedelta(minutes=30)

    def test_win_resets_consecutive_losses(self):
        """Test that a win resets consecutive loss count."""
        manager = LossLimitManager(max_consecutive_losses=3)
        now = datetime.now()
        
        # 2 losses then 1 win
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'TP', 100.0)
        
        assert manager.consecutive_losses == 0

    def test_win_cancels_pause(self):
        """Test that a win cancels any active pause."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Trigger pause
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'SL', -50.0)
        
        assert manager.pause_until is not None
        
        # Win cancels pause
        manager.record_trade(now + timedelta(minutes=5), 'TP', 100.0)
        
        assert manager.pause_until is None
        assert manager.consecutive_losses == 0

    def test_can_trade_when_not_paused(self):
        """Test can_trade returns True when not paused."""
        manager = LossLimitManager()
        now = datetime.now()
        
        assert manager.can_trade(now) is True

    def test_can_trade_during_pause(self):
        """Test can_trade returns False during pause."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Trigger pause
        for _ in range(3):
            manager.record_trade(now, 'SL', -50.0)
        
        # Still within pause period
        assert manager.can_trade(now + timedelta(minutes=15)) is False

    def test_can_trade_after_pause_expires(self):
        """Test can_trade returns True after pause expires."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Trigger pause
        for _ in range(3):
            manager.record_trade(now, 'SL', -50.0)
        
        # After pause period
        assert manager.can_trade(now + timedelta(minutes=31)) is True
        assert manager.pause_until is None
        assert manager.consecutive_losses == 0

    def test_get_status(self):
        """Test status retrieval."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Initial status
        status = manager.get_status(now)
        assert status['consecutive_losses'] == 0
        assert status['is_paused'] is False
        assert status['total_trades'] == 0

    def test_get_status_during_pause(self):
        """Test status during pause."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Trigger pause
        for _ in range(3):
            manager.record_trade(now, 'SL', -50.0)
        
        status = manager.get_status(now + timedelta(minutes=10))
        
        assert status['is_paused'] is True
        assert 'pause_minutes_remaining' in status
        assert status['pause_minutes_remaining'] == pytest.approx(20.0, abs=0.1)

    def test_reset(self):
        """Test reset functionality."""
        manager = LossLimitManager(max_consecutive_losses=3, pause_minutes=30)
        now = datetime.now()
        
        # Trigger pause
        for _ in range(3):
            manager.record_trade(now, 'SL', -50.0)
        
        manager.reset()
        
        assert manager.consecutive_losses == 0
        assert manager.pause_until is None

    def test_get_recent_performance(self):
        """Test recent performance calculation."""
        manager = LossLimitManager()
        now = datetime.now()
        
        # Mix of trades
        manager.record_trade(now, 'TP', 100.0)
        manager.record_trade(now, 'TP', 150.0)
        manager.record_trade(now, 'SL', -50.0)
        manager.record_trade(now, 'TP', 75.0)
        
        perf = manager.get_recent_performance(lookback_count=10)
        
        assert perf['count'] == 4
        assert perf['wins'] == 3
        assert perf['losses'] == 1
        assert perf['win_rate'] == 0.75
        assert perf['total_pnl'] == 275.0

    def test_get_recent_performance_empty(self):
        """Test recent performance with no trades."""
        manager = LossLimitManager()
        
        perf = manager.get_recent_performance()
        
        assert perf['count'] == 0
        assert perf['win_rate'] == 0.0


class TestPositionManager:
    """Tests for PositionManager class."""

    def test_init(self):
        """Test initialization."""
        manager = PositionManager()
        
        assert len(manager.positions) == 0

    def test_open_position(self):
        """Test opening a position."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='bollinger_trigger',
            direction='LONG',
            size=2,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        assert len(manager.positions) == 1
        assert 'pos_001' in manager.positions
        
        pos = manager.positions['pos_001']
        assert pos.direction == 'LONG'
        assert pos.size == 2
        assert pos.entry_price == 5000.0

    def test_close_position(self):
        """Test closing a position."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='bollinger_trigger',
            direction='LONG',
            size=2,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        manager.close_position('pos_001')
        
        assert len(manager.positions) == 0

    def test_close_nonexistent_position(self):
        """Test closing a position that doesn't exist."""
        manager = PositionManager()
        
        # Should not raise error
        manager.close_position('nonexistent')
        
        assert len(manager.positions) == 0

    def test_can_open_position_within_limit(self):
        """Test can_open_position within limit."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=2,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        # Current: 2, requesting 3 more, max 10
        assert manager.can_open_position(3, max_total_size=10) is True

    def test_can_open_position_exceeds_limit(self):
        """Test can_open_position exceeding limit."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=5,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        # Current: 5, requesting 6 more, max 10
        assert manager.can_open_position(6, max_total_size=10) is False

    def test_get_total_position_size(self):
        """Test total position size calculation."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=3,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        manager.open_position(
            position_id='pos_002',
            signal_id='sig_002',
            trigger_name='trigger_b',
            direction='SHORT',
            size=2,
            entry_price=5050.0,
            tp=4950.0,
            sl=5100.0,
            entry_time=now
        )
        
        assert manager.get_total_position_size() == 5

    def test_get_net_position(self):
        """Test net position calculation."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=5,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        manager.open_position(
            position_id='pos_002',
            signal_id='sig_002',
            trigger_name='trigger_b',
            direction='SHORT',
            size=3,
            entry_price=5050.0,
            tp=4950.0,
            sl=5100.0,
            entry_time=now
        )
        
        # LONG 5 - SHORT 3 = 2
        assert manager.get_net_position() == 2

    def test_get_positions_by_trigger(self):
        """Test filtering positions by trigger."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='bollinger',
            direction='LONG',
            size=2,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        manager.open_position(
            position_id='pos_002',
            signal_id='sig_002',
            trigger_name='ma_cross',
            direction='LONG',
            size=1,
            entry_price=5010.0,
            tp=5110.0,
            sl=4960.0,
            entry_time=now
        )
        
        bollinger_positions = manager.get_positions_by_trigger('bollinger')
        
        assert len(bollinger_positions) == 1
        assert bollinger_positions[0].id == 'pos_001'

    def test_get_active_positions(self):
        """Test getting all active positions."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=2,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        positions = manager.get_active_positions()
        
        assert len(positions) == 1

    def test_get_statistics_empty(self):
        """Test statistics with no positions."""
        manager = PositionManager()
        
        stats = manager.get_statistics()
        
        assert stats['total_positions'] == 0
        assert stats['total_size'] == 0
        assert stats['net_position'] == 0

    def test_get_statistics_with_positions(self):
        """Test statistics with multiple positions."""
        manager = PositionManager()
        now = datetime.now()
        
        manager.open_position(
            position_id='pos_001',
            signal_id='sig_001',
            trigger_name='trigger_a',
            direction='LONG',
            size=4,
            entry_price=5000.0,
            tp=5100.0,
            sl=4950.0,
            entry_time=now
        )
        
        manager.open_position(
            position_id='pos_002',
            signal_id='sig_002',
            trigger_name='trigger_b',
            direction='SHORT',
            size=2,
            entry_price=5050.0,
            tp=4950.0,
            sl=5100.0,
            entry_time=now
        )
        
        stats = manager.get_statistics()
        
        assert stats['total_positions'] == 2
        assert stats['total_size'] == 6
        assert stats['net_position'] == 2  # 4 - 2
        assert stats['long_size'] == 4
        assert stats['short_size'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
