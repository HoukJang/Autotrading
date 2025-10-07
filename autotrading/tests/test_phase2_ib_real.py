#!/usr/bin/env python3
"""
Phase 2 Real IB API Connection Test
실제 TWS/IB Gateway 연결 테스트 (Paper Trading)
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker.connection_manager import IBConnectionManager, ConnectionState
from broker.contracts import ContractFactory
from broker.ib_client import IBClient
from core.event_bus import EventBus
from core.events import EventType


class IBAPIRealTest:
    """실제 IB API 연결 테스트"""

    def __init__(self):
        self.event_bus = None
        self.client = None
        self.test_results = []

    async def setup(self):
        """테스트 환경 설정"""
        print("="*60)
        print("IB API Real Connection Test (Paper Trading)")
        print("="*60)
        print("\n[!] Prerequisites:")
        print("1. TWS or IB Gateway must be running")
        print("2. Paper Trading account should be active")
        print("3. API Settings:")
        print("   - Enable ActiveX and Socket Clients")
        print("   - Socket port: 7497 (TWS) or 4001 (Gateway)")
        print("   - Allow connections from 127.0.0.1")
        print("="*60)

        # Initialize event bus
        self.event_bus = EventBus()
        await self.event_bus.start()

        # Create IB client
        self.client = IBClient(self.event_bus)

    async def test_connection(self):
        """Test 1: IB API 연결 테스트"""
        print("\n[Test 1] Testing IB API Connection...")
        print("-" * 40)

        try:
            # Connect to IB API
            print("Connecting to TWS on port 7497...")
            result = await self.client.connect()

            if result:
                print("[PASS] Successfully connected to IB API!")
                print(f"   Connection state: {self.client.connection_manager.state.value}")

                # Get connection info
                info = self.client.connection_manager.get_connection_info()
                print(f"   Host: {info['host']}")
                print(f"   Port: {info['port']}")
                print(f"   Client ID: {info['client_id']}")

                self.test_results.append(("Connection Test", "PASSED"))
                return True
            else:
                print("[FAIL] Failed to connect to IB API")
                print("   Check if TWS is running and API is enabled")
                self.test_results.append(("Connection Test", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            print("\n   Troubleshooting:")
            print("   1. Is TWS running? (Check system tray)")
            print("   2. Is API enabled? (File → Global Configuration → API)")
            print("   3. Is port 7497 open? (TWS default)")
            print("   4. Try IB Gateway on port 4001 if TWS fails")
            self.test_results.append(("Connection Test", f"ERROR: {e}"))
            return False

    async def test_account_info(self):
        """Test 2: 계정 정보 조회"""
        print("\n[Test 2] Getting Account Information...")
        print("-" * 40)

        try:
            summary = await self.client.get_account_summary()

            if summary:
                print("[PASS] Account information retrieved!")
                print(f"   Net Liquidation: ${summary.get('net_liquidation', 0):,.2f}")
                print(f"   Buying Power: ${summary.get('buying_power', 0):,.2f}")
                print(f"   Total Cash: ${summary.get('total_cash', 0):,.2f}")

                # Paper trading account should have default values
                if summary.get('net_liquidation', 0) > 0:
                    print("   [OK] Paper trading account active")

                self.test_results.append(("Account Info", "PASSED"))
                return True
            else:
                print("[FAIL] No account information received")
                self.test_results.append(("Account Info", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Account info error: {e}")
            self.test_results.append(("Account Info", f"ERROR: {e}"))
            return False

    async def test_market_data(self):
        """Test 3: 실시간 마켓 데이터 구독"""
        print("\n[Test 3] Testing Market Data Subscription...")
        print("-" * 40)

        try:
            # Subscribe to ES futures
            symbol = 'ES'
            print(f"Subscribing to {symbol} market data...")

            result = await self.client.subscribe_market_data(symbol)

            if result:
                print(f"[PASS] Subscribed to {symbol} market data!")

                # Wait for a few ticks
                print("   Waiting for market data (5 seconds)...")
                await asyncio.sleep(5)

                # Check subscription status
                status = self.client.get_subscription_status()
                if status.get(symbol):
                    print(f"   [OK] {symbol} subscription active")

                # Unsubscribe
                await self.client.unsubscribe_market_data(symbol)
                print(f"   [OK] Unsubscribed from {symbol}")

                self.test_results.append(("Market Data", "PASSED"))
                return True
            else:
                print(f"[FAIL] Failed to subscribe to {symbol}")
                print("   Note: Market data requires subscription permissions")
                self.test_results.append(("Market Data", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Market data error: {e}")
            self.test_results.append(("Market Data", f"ERROR: {e}"))
            return False

    async def test_historical_data(self):
        """Test 4: 히스토리컬 데이터 요청"""
        print("\n[Test 4] Testing Historical Data Request...")
        print("-" * 40)

        try:
            symbol = 'ES'
            print(f"Requesting historical data for {symbol}...")

            bars = await self.client.request_historical_bars(
                symbol=symbol,
                duration="1 D",
                bar_size="1 hour"
            )

            if bars:
                print(f"[PASS] Received {len(bars)} historical bars!")

                # Show first few bars
                for i, bar in enumerate(bars[:3]):
                    print(f"   Bar {i+1}: Open={bar.open}, High={bar.high}, "
                          f"Low={bar.low}, Close={bar.close}")

                self.test_results.append(("Historical Data", "PASSED"))
                return True
            else:
                print("[FAIL] No historical data received")
                self.test_results.append(("Historical Data", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Historical data error: {e}")
            print("   Note: Historical data requires data subscription")
            self.test_results.append(("Historical Data", f"ERROR: {e}"))
            return False

    async def test_positions(self):
        """Test 5: 포지션 조회"""
        print("\n[Test 5] Testing Position Query...")
        print("-" * 40)

        try:
            positions = await self.client.get_positions()

            if positions is not None:
                if len(positions) > 0:
                    print(f"[PASS] Found {len(positions)} positions:")
                    for pos in positions:
                        print(f"   {pos['symbol']}: {pos['quantity']} contracts")
                else:
                    print("[PASS] No open positions (expected for new paper account)")

                self.test_results.append(("Position Query", "PASSED"))
                return True
            else:
                print("[FAIL] Failed to query positions")
                self.test_results.append(("Position Query", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Position query error: {e}")
            self.test_results.append(("Position Query", f"ERROR: {e}"))
            return False

    async def test_paper_order(self):
        """Test 6: 페이퍼 트레이딩 주문 테스트"""
        print("\n[Test 6] Testing Paper Trading Order...")
        print("-" * 40)
        print("[WARNING] This will place a PAPER order (not real money)")

        try:
            # Place a small limit order that won't fill
            symbol = 'MES'  # Micro E-mini for smaller size
            price = Decimal('4000')  # Far from market price

            print(f"Placing limit order: BUY 1 {symbol} @ ${price}")
            print("(Order price is far from market, should not fill)")

            order_id = await self.client.place_limit_order(
                symbol=symbol,
                quantity=1,
                price=price,
                action='BUY'
            )

            if order_id:
                print(f"[PASS] Order placed successfully! Order ID: {order_id}")

                # Wait a bit
                await asyncio.sleep(2)

                # Cancel the order
                print("   Cancelling order...")
                result = await self.client.cancel_order(order_id)

                if result:
                    print("   [OK] Order cancelled successfully")

                self.test_results.append(("Paper Order", "PASSED"))
                return True
            else:
                print("[FAIL] Failed to place order")
                self.test_results.append(("Paper Order", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Order error: {e}")
            self.test_results.append(("Paper Order", f"ERROR: {e}"))
            return False

    async def cleanup(self):
        """테스트 정리"""
        if self.client:
            await self.client.disconnect()
        if self.event_bus:
            await self.event_bus.stop()

    async def run_all_tests(self):
        """모든 테스트 실행"""
        await self.setup()

        # Check if we should continue based on connection test
        connected = await self.test_connection()

        if connected:
            # Run remaining tests only if connected
            await self.test_account_info()
            await self.test_market_data()
            await self.test_historical_data()
            await self.test_positions()

            # Ask before running order test
            print("\n" + "="*60)
            response = input("Run paper trading order test? (y/n): ")
            if response.lower() == 'y':
                await self.test_paper_order()

        # Print summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        for test_name, result in self.test_results:
            status_icon = "[PASS]" if result == "PASSED" else "[FAIL]"
            print(f"{status_icon} {test_name}: {result}")

        passed = sum(1 for _, r in self.test_results if r == "PASSED")
        total = len(self.test_results)

        print(f"\nResults: {passed}/{total} tests passed")

        if not connected:
            print("\n[SETUP] Connection Setup Instructions:")
            print("1. Download TWS from Interactive Brokers website")
            print("2. Login with paper trading credentials")
            print("3. Go to File → Global Configuration → API → Settings")
            print("4. Enable 'Enable ActiveX and Socket Clients'")
            print("5. Set Socket port to 7497")
            print("6. Add 127.0.0.1 to trusted IPs")
            print("7. Restart TWS and try again")

        await self.cleanup()
        return passed == total


async def main():
    """메인 실행 함수"""
    tester = IBAPIRealTest()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    print("\n" + "="*60)
    print("IB API Phase 2 - Real Connection Test")
    print("="*60)
    print("This test requires TWS or IB Gateway running!")
    print("="*60)

    # Run the async tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)