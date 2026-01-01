"""
Test IB API reqRealTimeBars functionality
5초봉 실시간 스트리밍 테스트
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from broker.contracts import ContractFactory
from core.event_bus import EventBus
from utils.contract_utils import FuturesContractUtils


async def test_realtime_bars():
    """reqRealTimeBars 테스트"""
    print("=" * 70)
    print("Testing IB API reqRealTimeBars (5-second bars)")
    print("=" * 70)

    symbol = "ES"
    event_bus = EventBus()
    ib_client = IBClient(event_bus)

    try:
        # 1. IB 연결
        print("\n1. Connecting to IB API...")
        connected = await ib_client.connect()
        if not connected:
            print("   [ERROR] Failed to connect to IB")
            return
        print("   Connected")

        # 2. 현재 활성 계약 가져오기
        print("\n2. Getting active contract...")
        utils = FuturesContractUtils()
        contract_month = utils.get_contract_for_trading(symbol)
        local_symbol = utils.get_active_local_symbol(symbol, datetime.now())
        print(f"   Contract: {contract_month} ({local_symbol})")

        # 3. 계약 생성
        print("\n3. Creating futures contract...")
        futures_contract = ContractFactory.create_futures(symbol, expiry=contract_month)
        contract = futures_contract.to_ib_contract()
        print(f"   Contract created: {contract.symbol} {contract.lastTradeDateOrContractMonth}")

        # 4. 실시간 바 요청
        print("\n4. Requesting real-time 5-second bars...")
        print("   This will stream live data for 60 seconds")
        print("   Watch for incoming bars...\n")

        bar_count = 0

        def on_bar_update(bars, hasNewBar):
            """실시간 바 수신 콜백"""
            nonlocal bar_count
            if hasNewBar:
                bar = bars[-1]
                bar_count += 1
                print(f"   [{bar_count}] {bar.time} | O:{bar.open_:.2f} H:{bar.high:.2f} "
                      f"L:{bar.low:.2f} C:{bar.close:.2f} V:{bar.volume}")

        # reqRealTimeBars 호출
        bars = ib_client._ib.reqRealTimeBars(
            contract=contract,
            barSize=5,  # 5초봉
            whatToShow='TRADES',
            useRTH=False
        )

        # 콜백 등록
        bars.updateEvent += on_bar_update

        print(f"   Real-time bars requested (barSize=5)")
        print(f"   Waiting for data...\n")

        # 60초 동안 대기
        for i in range(60):
            await asyncio.sleep(1)
            if i % 10 == 0 and i > 0:
                print(f"   ... {i} seconds elapsed, {bar_count} bars received")

        # 5. 결과 요약
        print(f"\n5. Test Results:")
        print(f"   Duration: 60 seconds")
        print(f"   Bars received: {bar_count}")
        print(f"   Expected: ~12 bars (60s ÷ 5s = 12)")

        if bar_count >= 10:
            print(f"   [OK] Real-time 5-second bars working!")
        elif bar_count > 0:
            print(f"   [WARNING] Received fewer bars than expected")
        else:
            print(f"   [ERROR] No bars received!")

        # 스트리밍 취소
        ib_client._ib.cancelRealTimeBars(bars)
        print("\n   Real-time streaming cancelled")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nDisconnecting...")
        await ib_client.disconnect()
        print("Done")


if __name__ == "__main__":
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure you have market data subscription")
    print("  - This test will run for 60 seconds\n")

    try:
        asyncio.run(test_realtime_bars())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
