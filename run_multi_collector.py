"""
Multi-Symbol Continuous Data Collector
여러 선물 종목을 동시에 수집하는 데몬
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
    log_file = log_dir / 'multi_collector.log'

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


# 수집 가능한 모든 종목
AVAILABLE_SYMBOLS = {
    'SP500': {
        'ES': 'E-mini S&P 500 (standard)',
        'MES': 'Micro E-mini S&P 500 (1/10 size)'
    },
    'NASDAQ': {
        'NQ': 'E-mini NASDAQ-100 (standard)',
        'MNQ': 'Micro E-mini NASDAQ-100 (1/10 size)'
    },
    'DOW': {
        'YM': 'E-mini Dow ($5) (standard)',
        'MYM': 'Micro E-mini Dow ($0.50)'
    },
    'RUSSELL': {
        'RTY': 'E-mini Russell 2000 (standard)',
        'M2K': 'Micro E-mini Russell 2000 (1/10 size)'
    }
}


def print_symbol_menu():
    """종목 선택 메뉴 출력"""
    print("\n" + "=" * 70)
    print("Available Symbols for Collection")
    print("=" * 70)

    print("\n📈 S&P 500 Futures:")
    for symbol, desc in AVAILABLE_SYMBOLS['SP500'].items():
        print(f"  • {symbol:6} - {desc}")

    print("\n📊 NASDAQ Futures:")
    for symbol, desc in AVAILABLE_SYMBOLS['NASDAQ'].items():
        print(f"  • {symbol:6} - {desc}")

    print("\n📉 Dow Jones Futures:")
    for symbol, desc in AVAILABLE_SYMBOLS['DOW'].items():
        print(f"  • {symbol:6} - {desc}")

    print("\n📌 Russell 2000 Futures:")
    for symbol, desc in AVAILABLE_SYMBOLS['RUSSELL'].items():
        print(f"  • {symbol:6} - {desc}")

    print("\n" + "=" * 70)


def get_symbol_selections():
    """사용자로부터 수집할 종목 선택"""
    print("\nSelect collection mode:")
    print("  1. All major indices (ES, NQ, YM, RTY)")
    print("  2. All symbols (8 symbols)")
    print("  3. S&P 500 only (ES, MES)")
    print("  4. NASDAQ only (NQ, MNQ)")
    print("  5. Custom selection")

    choice = input("\nEnter choice (1-5, default=1): ").strip() or "1"

    if choice == "1":
        return ['ES', 'NQ', 'YM', 'RTY']
    elif choice == "2":
        symbols = []
        for category in AVAILABLE_SYMBOLS.values():
            symbols.extend(category.keys())
        return symbols
    elif choice == "3":
        return ['ES', 'MES']
    elif choice == "4":
        return ['NQ', 'MNQ']
    elif choice == "5":
        print_symbol_menu()
        symbols_input = input("\nEnter symbols (comma-separated, e.g., ES,NQ,YM): ").strip().upper()
        return [s.strip() for s in symbols_input.split(',') if s.strip()]
    else:
        print("Invalid choice, using default (ES, NQ, YM, RTY)")
        return ['ES', 'NQ', 'YM', 'RTY']


async def run_collector(symbol: str, client_id: int):
    """개별 심볼 수집기 실행"""
    logger = logging.getLogger(f'collector.{symbol}')
    logger.info(f"Starting collector for {symbol} (clientId={client_id})")

    try:
        collector = ContinuousDataCollector(symbol=symbol, client_id=client_id)
        await collector.start()
    except Exception as e:
        logger.error(f"Error in {symbol} collector: {e}", exc_info=True)


async def main():
    """메인 실행"""
    print("=" * 70)
    print("Multi-Symbol Futures Continuous Data Collector")
    print("=" * 70)
    print("\nIMPORTANT:")
    print("  - Make sure TWS/IB Gateway is running")
    print("  - Make sure PostgreSQL is running")
    print("  - Check .env file has correct credentials")
    print("  - Each symbol runs in parallel with separate connection")
    print("\nFeatures:")
    print("  - Parallel collection of multiple symbols")
    print("  - Automatic gap filling on startup")
    print("  - Real-time 5-second bars → 1-minute aggregation")
    print("  - Automatic contract rollover handling")
    print("  - Auto-reconnection with exponential backoff")
    print("  - Market break handling (16:01-16:59)")
    print("=" * 70)

    # 종목 선택
    symbols = get_symbol_selections()

    if not symbols:
        print("\nNo symbols selected. Exiting.")
        return

    print(f"\n✓ Selected symbols: {', '.join(symbols)}")
    print(f"✓ Total: {len(symbols)} symbols")
    print("\nPress Ctrl+C to stop all collectors")
    print("=" * 70)
    print()

    # 로깅 설정
    setup_logging()

    # 각 심볼별로 수집기 생성 및 실행
    logger = logging.getLogger('main')
    logger.info(f"Starting multi-symbol collection for: {', '.join(symbols)}")

    # 각 심볼에 고유한 client_id 할당 (1부터 시작)
    logger.info("Client ID assignments:")
    for idx, symbol in enumerate(symbols, start=1):
        logger.info(f"  {symbol}: clientId={idx}")

    try:
        # 모든 수집기를 병렬로 실행 (각각 다른 client_id 사용)
        tasks = [run_collector(symbol, client_id=idx) for idx, symbol in enumerate(symbols, start=1)]
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        logger.info("\nStopping all collectors by user request...")
        print("\n\nStopping all collectors...")

    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        print(f"\n\nERROR: {e}")

    finally:
        print("\nAll collectors stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
