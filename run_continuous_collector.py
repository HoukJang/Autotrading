"""
Continuous Data Collector Daemon Runner
ES futures 연속 데이터 수집 데몬 실행 스크립트
"""

import asyncio
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from data.continuous_collector import ContinuousDataCollector


def setup_logging():
    """로깅 설정"""
    # 로그 디렉토리 생성
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    # 로그 파일 경로
    log_file = log_dir / 'continuous_collector.log'

    # 포맷 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger('ib_async').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


async def main():
    """메인 실행"""
    print("=" * 70)
    print("Futures Continuous Data Collector")
    print("=" * 70)
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure PostgreSQL is running")
    print("  - Check .env file has correct credentials")
    print("\nFeatures:")
    print("  - Automatic gap filling on startup")
    print("  - Real-time 5-second bars → 1-minute aggregation")
    print("  - Automatic contract rollover handling")
    print("  - Auto-reconnection with exponential backoff")
    print("  - Market break handling (16:01-16:59)")
    print("  - Data validation and filtering")
    print("=" * 70)

    # 종목 선택
    print("\nSelect symbol to collect:")
    print("  1. ES  (E-mini S&P 500)")
    print("  2. NQ  (E-mini NASDAQ-100)")
    print("  3. YM  (E-mini Dow)")
    print("  4. RTY (E-mini Russell 2000)")
    print("  5. Custom (enter symbol)")

    choice = input("\nEnter choice (1-5, default=1): ").strip() or "1"

    symbol_map = {
        "1": "ES",
        "2": "NQ",
        "3": "YM",
        "4": "RTY"
    }

    if choice in symbol_map:
        symbol = symbol_map[choice]
    elif choice == "5":
        symbol = input("Enter symbol: ").strip().upper()
    else:
        print("Invalid choice, using ES")
        symbol = "ES"

    print(f"\n✓ Selected symbol: {symbol}")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    print()

    # 로깅 설정
    setup_logging()

    # 데이터 수집기 생성
    collector = ContinuousDataCollector(symbol=symbol)

    try:
        # 시작
        await collector.start()

    except KeyboardInterrupt:
        print("\n\nStopping by user request...")

    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nShutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
