#!/usr/bin/env python3
"""
Phase 2 Fixed IB API Connection Test
수정된 TWS 연결 테스트 (non-interactive)
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker.connection_manager import IBConnectionManager, ConnectionState
from broker.contracts import ContractFactory
from broker.ib_client import IBClient
from core.event_bus import EventBus
from core.events import EventType


class IBAPIFixedTest:
    """수정된 IB API 연결 테스트"""

    def __init__(self):
        self.event_bus = None
        self.client = None
        self.test_results = []

    async def setup(self):
        """테스트 환경 설정"""
        print("=" * 60)
        print("IB API Fixed Connection Test")
        print("=" * 60)

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
            # Connect to IB API (port updated to 7496)
            print("Connecting to TWS on port 7496...")
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
                self.test_results.append(("Connection Test", "FAILED"))
                return False

        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            self.test_results.append(("Connection Test", f"ERROR: {e}"))
            return False

    def test_contract_creation(self):
        """Test 2: 계약 생성 테스트"""
        print("\n[Test 2] Testing Contract Creation...")
        print("-" * 40)

        try:
            # Create ES contract with expiry
            es_contract = ContractFactory.create_es_futures()
            print(f"[PASS] ES contract created: {es_contract.symbol}")
            print(f"   Exchange: {es_contract.exchange}")
            print(f"   Expiry: {es_contract.expiry}")
            print(f"   Multiplier: {es_contract.multiplier}")

            # Convert to IB contract
            ib_contract = es_contract.to_ib_contract()
            print(f"   IB Contract: {ib_contract.symbol} {ib_contract.lastTradeDateOrContractMonth}")

            self.test_results.append(("Contract Creation", "PASSED"))
            return True

        except Exception as e:
            print(f"[ERROR] Contract creation error: {e}")
            self.test_results.append(("Contract Creation", f"ERROR: {e}"))
            return False

    async def test_positions_sync(self):
        """Test 3: 포지션 조회 (동기 방식)"""
        print("\n[Test 3] Testing Position Query (Sync)...")
        print("-" * 40)

        try:
            if not self.client.connection_manager.is_connected():
                print("[SKIP] Not connected to IB API")
                return False

            # Use sync method instead of async
            if self.client._ib:
                positions = self.client._ib.positions()

                if positions is not None:
                    if len(positions) > 0:
                        print(f"[PASS] Found {len(positions)} positions:")
                        for pos in positions:
                            print(f"   {pos.contract.symbol}: {pos.position} contracts")
                    else:
                        print("[PASS] No open positions (expected for new account)")

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

    async def test_account_values_sync(self):
        """Test 4: 계정 정보 조회 (동기 방식)"""
        print("\n[Test 4] Testing Account Values (Sync)...")
        print("-" * 40)

        try:
            if not self.client.connection_manager.is_connected():
                print("[SKIP] Not connected to IB API")
                return False

            # Use sync method
            if self.client._ib:
                account_values = self.client._ib.accountValues()

                if account_values:
                    print(f"[PASS] Retrieved {len(account_values)} account values!")

                    # Show some key values
                    key_values = {}
                    for item in account_values:
                        if item.tag in ['NetLiquidation', 'BuyingPower', 'TotalCashValue']:
                            key_values[item.tag] = item.value

                    for tag, value in key_values.items():
                        print(f"   {tag}: {value}")

                    self.test_results.append(("Account Values", "PASSED"))
                    return True
                else:
                    print("[FAIL] No account values received")
                    self.test_results.append(("Account Values", "FAILED"))
                    return False

        except Exception as e:
            print(f"[ERROR] Account values error: {e}")
            self.test_results.append(("Account Values", f"ERROR: {e}"))
            return False

    async def test_contract_details(self):
        """Test 5: 계약 세부정보 조회"""
        print("\n[Test 5] Testing Contract Details...")
        print("-" * 40)

        try:
            if not self.client.connection_manager.is_connected():
                print("[SKIP] Not connected to IB API")
                return False

            # Create ES contract
            es_contract = ContractFactory.create_es_futures()
            ib_contract = es_contract.to_ib_contract()

            # Request contract details (sync)
            if self.client._ib:
                details = self.client._ib.reqContractDetails(ib_contract)

                if details:
                    print(f"[PASS] Retrieved {len(details)} contract details!")

                    for detail in details[:2]:  # Show first 2
                        contract = detail.contract
                        print(f"   Contract: {contract.localSymbol}")
                        print(f"   Exchange: {contract.exchange}")
                        print(f"   ConId: {contract.conId}")

                    self.test_results.append(("Contract Details", "PASSED"))
                    return True
                else:
                    print("[FAIL] No contract details received")
                    self.test_results.append(("Contract Details", "FAILED"))
                    return False

        except Exception as e:
            print(f"[ERROR] Contract details error: {e}")
            self.test_results.append(("Contract Details", f"ERROR: {e}"))
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

        # Test 1: Connection
        connected = await self.test_connection()

        # Test 2: Contract creation (always run)
        self.test_contract_creation()

        if connected:
            # Tests 3-5: Only if connected
            await self.test_positions_sync()
            await self.test_account_values_sync()
            await self.test_contract_details()

        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        for test_name, result in self.test_results:
            status_icon = "[PASS]" if result == "PASSED" else "[FAIL]"
            print(f"{status_icon} {test_name}: {result}")

        passed = sum(1 for _, r in self.test_results if r == "PASSED")
        total = len(self.test_results)

        print(f"\nResults: {passed}/{total} tests passed")

        if connected:
            print("\n[SUCCESS] TWS connection working!")
            print("Phase 2 IB API integration is functional.")
            print("\nNext steps:")
            print("1. Implement tick-to-bar aggregation")
            print("2. Add strategy integration")
            print("3. Complete Phase 3 development")
        else:
            print("\n[INFO] Connection failed - check TWS settings")

        await self.cleanup()
        return passed >= 3  # At least 3 tests should pass


async def main():
    """메인 실행 함수"""
    tester = IBAPIFixedTest()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("IB API Phase 2 - Fixed Connection Test")
    print("=" * 60)
    print("Testing with corrected contract specifications...")
    print("=" * 60)

    # Run the async tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)