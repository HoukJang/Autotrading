"""
시장 시간 검증 테스트

현재 시장 상태를 확인하고 거래 가능 여부를 판단합니다.
"""

import asyncio
import logging
from autotrading.utils.market_hours import check_market_status, is_market_open_now

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_market_hours():
    """시장 시간 검증 테스트"""
    logger.info("=== 시장 시간 검증 테스트 ===")

    try:
        # 현재 시장 상태 확인
        status = check_market_status()

        logger.info("현재 시장 상태:")
        logger.info(f"  동부시간: {status['current_time_eastern']}")
        logger.info(f"  요일: {status['weekday_name']} ({status['weekday']})")
        logger.info(f"  거래일 여부: {status['is_trading_day']}")
        logger.info(f"  거래시간 여부: {status['is_market_hours']}")
        logger.info(f"  시장 개장 여부: {status['is_market_open']}")
        logger.info(f"  상태: {status['status']}")
        logger.info(f"  메시지: {status['message']}")

        # 간단한 확인
        is_open = is_market_open_now()
        logger.info(f"\n시장 개장 여부 (간단 확인): {is_open}")

        if is_open:
            logger.info("✅ 거래 가능한 시간입니다!")
        else:
            logger.warning("❌ 거래 불가능한 시간입니다")

        return status

    except Exception as e:
        logger.error(f"시장 시간 확인 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_market_hours()