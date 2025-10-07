#!/usr/bin/env python3
"""
Phase 2 Mock-based Unit Tests
Tests core functionality without real IB API connection
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker.contracts import ContractFactory, FuturesContract
from core.exceptions import TradingSystemError


class TestContractFactory(unittest.TestCase):
    """Test Contract Factory with various futures"""

    def test_es_futures_creation(self):
        """Test ES futures contract creation"""
        print("\n✓ Testing ES futures creation...")
        contract = ContractFactory.create_es_futures()

        self.assertEqual(contract.symbol, 'ES')
        self.assertEqual(contract.exchange, 'CME')
        self.assertEqual(contract.currency, 'USD')
        self.assertEqual(contract.multiplier, 50)
        self.assertEqual(contract.tick_size, Decimal('0.25'))
        print(f"  ES contract: {contract.symbol} on {contract.exchange}")
        print(f"  Multiplier: {contract.multiplier}, Tick size: {contract.tick_size}")

    def test_multiple_futures_creation(self):
        """Test creation of various futures contracts"""
        print("\n✓ Testing multiple futures contracts...")

        symbols_to_test = [
            ('ES', 'E-mini S&P 500', 50, Decimal('0.25')),
            ('NQ', 'E-mini Nasdaq-100', 20, Decimal('0.25')),
            ('YM', 'E-mini Dow Jones', 5, Decimal('1.0')),
            ('RTY', 'E-mini Russell 2000', 50, Decimal('0.1')),
            ('MES', 'Micro E-mini S&P 500', 5, Decimal('0.25')),
            ('MNQ', 'Micro E-mini Nasdaq-100', 2, Decimal('0.25'))
        ]

        for symbol, name, multiplier, tick_size in symbols_to_test:
            contract = ContractFactory.create_futures(symbol)
            specs = ContractFactory.get_contract_specs(symbol)

            self.assertEqual(contract.symbol, symbol)
            self.assertEqual(contract.multiplier, multiplier)
            self.assertEqual(contract.tick_size, tick_size)
            self.assertEqual(specs['name'], name)

            print(f"  {symbol}: {name}")
            print(f"    Exchange: {contract.exchange}")
            print(f"    Multiplier: {multiplier}, Tick size: {tick_size}")

    def test_continuous_futures(self):
        """Test continuous futures contract creation"""
        print("\n✓ Testing continuous futures...")

        contract = ContractFactory.create_continuous_futures('ES')

        self.assertEqual(contract.symbol, 'ES')
        self.assertEqual(contract.exchange, 'CME')
        self.assertFalse(contract.includeExpired)
        print(f"  Continuous {contract.symbol} created successfully")

    def test_futures_with_expiry(self):
        """Test futures with specific expiry"""
        print("\n✓ Testing futures with expiry...")

        contract = ContractFactory.create_futures('ES', '202412')

        self.assertEqual(contract.symbol, 'ES')
        self.assertEqual(contract.expiry, '202412')
        print(f"  {contract.symbol} Dec 2024 contract created")

    def test_tick_value_calculations(self):
        """Test tick value calculations for different futures"""
        print("\n✓ Testing tick value calculations...")

        test_cases = [
            ('ES', Decimal('4500'), 2, Decimal('25.00')),  # 2 ticks * $12.50
            ('ES', Decimal('4500'), 4, Decimal('50.00')),  # 4 ticks * $12.50
            ('NQ', Decimal('15000'), 2, Decimal('10.00')), # 2 ticks * $5.00
            ('MES', Decimal('4500'), 4, Decimal('5.00')),  # 4 ticks * $1.25
        ]

        for symbol, price, ticks, expected_value in test_cases:
            value = ContractFactory.calculate_tick_value(symbol, price, ticks)
            self.assertEqual(value, expected_value)
            print(f"  {symbol}: {ticks} ticks @ {price} = ${value}")

    def test_position_value_calculations(self):
        """Test position value calculations"""
        print("\n✓ Testing position value calculations...")

        test_cases = [
            ('ES', Decimal('4500'), 2, Decimal('450000')),  # 4500 * 2 * 50
            ('NQ', Decimal('15000'), 3, Decimal('900000')), # 15000 * 3 * 20
            ('MES', Decimal('4500'), 10, Decimal('225000')), # 4500 * 10 * 5
        ]

        for symbol, price, contracts, expected_value in test_cases:
            value = ContractFactory.calculate_position_value(symbol, price, contracts)
            self.assertEqual(value, expected_value)
            print(f"  {symbol}: {contracts} contracts @ {price} = ${value:,.2f}")

    def test_margin_requirements(self):
        """Test margin requirement calculations"""
        print("\n✓ Testing margin requirements...")

        symbols = ['ES', 'NQ', 'MES', 'MNQ']

        for symbol in symbols:
            day_margin = ContractFactory.get_margin_requirement(symbol, is_day_trading=True)
            overnight_margin = ContractFactory.get_margin_requirement(symbol, is_day_trading=False)

            self.assertIsNotNone(day_margin)
            self.assertIsNotNone(overnight_margin)
            self.assertGreater(overnight_margin, day_margin)

            print(f"  {symbol} margins:")
            print(f"    Day trading: ${day_margin}")
            print(f"    Overnight: ${overnight_margin}")

    def test_market_hours_validation(self):
        """Test market hours validation"""
        print("\n✓ Testing market hours validation...")

        # Create test dates
        monday_10am = datetime(2024, 1, 8, 10, 0)  # Monday
        friday_3pm = datetime(2024, 1, 12, 15, 0)  # Friday
        saturday_10am = datetime(2024, 1, 13, 10, 0)  # Saturday
        sunday_5pm = datetime(2024, 1, 14, 17, 0)  # Sunday

        # ES trades Sunday 5pm - Friday 4pm CT
        self.assertTrue(ContractFactory.is_market_hours('ES', monday_10am))
        self.assertTrue(ContractFactory.is_market_hours('ES', friday_3pm))
        self.assertFalse(ContractFactory.is_market_hours('ES', saturday_10am))
        self.assertTrue(ContractFactory.is_market_hours('ES', sunday_5pm))

        print("  Market hours validation working correctly")

    def test_invalid_symbol_handling(self):
        """Test handling of invalid symbols"""
        print("\n✓ Testing invalid symbol handling...")

        with self.assertRaises(ValueError) as context:
            ContractFactory.create_futures('INVALID')

        self.assertIn("Unknown futures symbol", str(context.exception))
        print("  Invalid symbol properly rejected")

    def test_contract_conversion(self):
        """Test conversion to IB contract format"""
        print("\n✓ Testing IB contract conversion...")

        futures = ContractFactory.create_futures('ES')
        ib_contract = futures.to_ib_contract()

        self.assertEqual(ib_contract.symbol, 'ES')
        self.assertEqual(ib_contract.secType, 'FUT')
        self.assertEqual(ib_contract.exchange, 'CME')
        self.assertEqual(ib_contract.currency, 'USD')
        print("  Contract successfully converted to IB format")


class TestConnectionState(unittest.TestCase):
    """Test connection state management"""

    def test_connection_states(self):
        """Test all connection state values"""
        print("\n✓ Testing connection states...")

        from broker.connection_manager import ConnectionState

        states = [
            ConnectionState.DISCONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.ERROR
        ]

        for state in states:
            self.assertIsNotNone(state.value)
            print(f"  State: {state.value}")


class TestExceptions(unittest.TestCase):
    """Test custom exception classes"""

    def test_execution_error(self):
        """Test ExecutionError creation"""
        print("\n✓ Testing ExecutionError...")

        from core.exceptions import ExecutionError

        error = ExecutionError("Order failed", order_id="123", symbol="ES")
        self.assertEqual(error.message, "Order failed")
        self.assertEqual(error.component, "execution")
        self.assertEqual(error.details.get("order_id"), "123")
        self.assertEqual(error.details.get("symbol"), "ES")
        print("  ExecutionError created successfully")

    def test_connection_error(self):
        """Test ConnectionError creation"""
        print("\n✓ Testing ConnectionError...")

        from core.exceptions import ConnectionError

        error = ConnectionError("Connection failed", host="127.0.0.1", port=7497)
        self.assertEqual(error.message, "Connection failed")
        self.assertEqual(error.component, "connection")
        self.assertEqual(error.details.get("host"), "127.0.0.1")
        self.assertEqual(error.details.get("port"), 7497)
        print("  ConnectionError created successfully")


def run_all_tests():
    """Run all Phase 2 mock tests"""
    print("="*60)
    print("Phase 2 Mock Tests - Core Functionality Validation")
    print("="*60)
    print("Testing without IB API connection...")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestContractFactory))
    suite.addTests(loader.loadTestsFromTestCase(TestConnectionState))
    suite.addTests(loader.loadTestsFromTestCase(TestExceptions))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*60)
    print("PHASE 2 TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ ALL PHASE 2 MOCK TESTS PASSED!")
        print("Core components working correctly without IB connection.")
        print("\nNext steps:")
        print("1. Ensure TWS/IB Gateway is running on port 7497")
        print("2. Enable API connections in TWS settings")
        print("3. Run integration tests with actual IB connection")
    else:
        print("\n❌ SOME TESTS FAILED")
        if result.failures:
            print("\nFAILURES:")
            for test, trace in result.failures:
                print(f"- {test}")
        if result.errors:
            print("\nERRORS:")
            for test, trace in result.errors:
                print(f"- {test}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)