"""
Test IB API data timing
1. Historical data fetch speed (5 bars)
2. Real-time data availability delay
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker.ib_client import IBClient
from core.event_bus import EventBus
from data.historical import HistoricalDataFetcher
from utils.contract_utils import FuturesContractUtils


async def test_historical_fetch_speed():
    """테스트 1: 히스토리컬 1분봉 5개 요청 속도 측정"""
    print("=" * 70)
    print("TEST 1: Historical Data Fetch Speed (5 bars)")
    print("=" * 70)

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    fetcher = HistoricalDataFetcher(ib_client)

    try:
        # 연결
        print("\n1. Connecting to IB API...")
        connected = await ib_client.connect()
        if not connected:
            print("   [ERROR] Failed to connect")
            return
        print("   Connected")

        # 현재 활성 계약
        utils = FuturesContractUtils()
        contract_month = utils.get_contract_for_trading("ES")
        print(f"\n2. Using contract: {contract_month}")

        # 10번 측정
        print("\n3. Fetching 5 bars (1-minute) - 10 iterations:")
        print("   Duration: 300 S (5 minutes)")
        print("")

        times = []

        for i in range(10):
            start_time = time.perf_counter()

            # 5분 데이터 요청 (5개 1분봉)
            bars = await ib_client.request_historical_bars(
                symbol="ES",
                duration="300 S",  # 5분
                bar_size="1 min",
                contract_month=contract_month
            )

            end_time = time.perf_counter()
            elapsed = end_time - start_time
            times.append(elapsed)

            print(f"   Iteration {i+1:2d}: {len(bars)} bars in {elapsed:.3f} seconds")

            # Rate limiting
            if i < 9:
                await asyncio.sleep(1)

        # 통계
        print(f"\n4. Statistics:")
        print(f"   Minimum: {min(times):.3f} seconds")
        print(f"   Maximum: {max(times):.3f} seconds")
        print(f"   Average: {sum(times)/len(times):.3f} seconds")
        print(f"   Median:  {sorted(times)[len(times)//2]:.3f} seconds")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await ib_client.disconnect()
        print("\nDisconnected")


async def test_realtime_availability_delay():
    """테스트 2: 실시간 데이터 가용성 지연 측정"""
    print("\n" + "=" * 70)
    print("TEST 2: Real-time Data Availability Delay")
    print("=" * 70)
    print("\nThis test measures how quickly historical bars become available")
    print("after their timestamp. For example:")
    print("  - Bar timestamp: 11:50:00")
    print("  - Query time: 11:50:XX (when does it become available?)")
    print("")

    event_bus = EventBus()
    ib_client = IBClient(event_bus)
    fetcher = HistoricalDataFetcher(ib_client)

    try:
        # 연결
        print("1. Connecting to IB API...")
        connected = await ib_client.connect()
        if not connected:
            print("   [ERROR] Failed to connect")
            return
        print("   Connected")

        # 현재 활성 계약
        utils = FuturesContractUtils()
        contract_month = utils.get_contract_for_trading("ES")
        print(f"\n2. Using contract: {contract_month}")

        print("\n3. Waiting for next minute boundary...")

        # 다음 분 경계까지 대기
        now = datetime.now()
        next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
        wait_seconds = (next_minute - now).total_seconds()
        print(f"   Current time: {now.strftime('%H:%M:%S')}")
        print(f"   Next minute:  {next_minute.strftime('%H:%M:%S')}")
        print(f"   Waiting {wait_seconds:.1f} seconds...")

        await asyncio.sleep(wait_seconds)

        # 분 경계 통과
        bar_timestamp = next_minute
        print(f"\n4. Minute boundary reached: {bar_timestamp.strftime('%H:%M:%S')}")
        print("   Starting availability checks...")
        print("")

        # 0초부터 60초까지 1초 간격으로 체크
        availability_time = None

        for delay_seconds in range(61):
            check_time = datetime.now()

            try:
                # 최근 10분봉 요청 (가장 최신 바 확인)
                bars = await ib_client.request_historical_bars(
                    symbol="ES",
                    duration="600 S",  # 10분
                    bar_size="1 min",
                    contract_month=contract_month
                )

                if bars and len(bars) > 0:
                    latest_bar = bars[-1]
                    latest_bar_time = latest_bar.date

                    # 타임존 처리
                    if isinstance(latest_bar_time, str):
                        latest_bar_time = datetime.fromisoformat(latest_bar_time)

                    # 현재 시간 (로컬)과 비교
                    # IB에서 받은 시간을 로컬 시간으로 변환
                    if latest_bar_time.tzinfo is not None:
                        # Timezone-aware면 로컬로 변환
                        latest_bar_local = latest_bar_time.astimezone()
                    else:
                        latest_bar_local = latest_bar_time

                    # 현재 시간
                    now_local = datetime.now()

                    # 분 단위로 비교
                    latest_minute = latest_bar_local.replace(second=0, microsecond=0, tzinfo=None)
                    current_minute = now_local.replace(second=0, microsecond=0)
                    target_minute = bar_timestamp.replace(second=0, microsecond=0)

                    # 디버그 정보
                    time_diff_from_now = (current_minute - latest_minute).total_seconds() / 60

                    # 현재 분과 같거나 1분 이전이면 최신 데이터
                    if time_diff_from_now <= 1:
                        availability_time = delay_seconds
                        print(f"   [{delay_seconds:2d}s] AVAILABLE!")
                        print(f"        Latest bar: {latest_bar_local.strftime('%H:%M:%S')}")
                        print(f"        Current:    {now_local.strftime('%H:%M:%S')}")
                        print(f"        Delay: {time_diff_from_now:.1f} minutes old")
                        print(f"        → Data became available {delay_seconds}s after minute boundary")
                        break
                    else:
                        print(f"   [{delay_seconds:2d}s] NOT YET - Latest: {latest_bar_local.strftime('%H:%M:%S')}, "
                              f"Current: {now_local.strftime('%H:%M:%S')} ({time_diff_from_now:.0f}m old)")
                else:
                    print(f"   [{delay_seconds:2d}s] NO DATA")

            except Exception as e:
                print(f"   [{delay_seconds:2d}s] ERROR: {e}")

            # 1초 대기
            await asyncio.sleep(1)

        # 결과
        print(f"\n5. Result:")
        if availability_time is not None:
            print(f"   Data availability delay: {availability_time} seconds")
            print(f"   Bar for {bar_timestamp.strftime('%H:%M:%S')} available at +{availability_time}s")
        else:
            print(f"   [ERROR] Data did not become available within 60 seconds")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await ib_client.disconnect()
        print("\nDisconnected")


async def main():
    """메인 실행"""
    print("\n" + "=" * 70)
    print("IB API Data Timing Tests")
    print("=" * 70)
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure market is open for accurate Test 2")
    print("  - Test 1 takes ~20 seconds")
    print("  - Test 2 takes up to ~90 seconds (waits for next minute)")
    print("\n" + "=" * 70)

    # 테스트 선택
    print("\nSelect test:")
    print("  1. Historical fetch speed (5 bars)")
    print("  2. Real-time availability delay")
    print("  3. Both tests")

    choice = input("\nEnter choice (1-3): ").strip()

    print("\n")

    if choice == "1":
        await test_historical_fetch_speed()
    elif choice == "2":
        await test_realtime_availability_delay()
    elif choice == "3":
        await test_historical_fetch_speed()
        print("\n" + "=" * 70)
        print("Waiting 10 seconds to avoid clientId conflict...")
        print("=" * 70)
        await asyncio.sleep(10)
        await test_realtime_availability_delay()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
