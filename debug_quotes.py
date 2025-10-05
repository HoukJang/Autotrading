"""
실제 시장 데이터 응답 구조 확인용 디버깅 스크립트
"""

import asyncio
import json
import logging
from autotrading.core.context import create_shared_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_quotes():
    """시장 데이터 응답 구조 디버깅"""
    logger.info("=== 시장 데이터 응답 구조 디버깅 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # 시세 조회
        symbols = ["AAPL", "SPY"]
        quotes = await context['schwab_service'].get_quotes(symbols)

        logger.info(f"응답 데이터 타입: {type(quotes)}")
        logger.info(f"응답 키들: {list(quotes.keys()) if isinstance(quotes, dict) else 'Not a dict'}")

        # 각 심볼별 데이터 구조 출력
        for symbol in symbols:
            if symbol in quotes:
                quote_data = quotes[symbol]
                logger.info(f"\n{symbol} 데이터:")
                logger.info(f"  타입: {type(quote_data)}")

                if isinstance(quote_data, dict):
                    logger.info(f"  키들: {list(quote_data.keys())}")
                    # 주요 가격 필드들 확인
                    price_fields = ['lastPrice', 'mark', 'bidPrice', 'askPrice', 'closePrice', 'openPrice']
                    for field in price_fields:
                        if field in quote_data:
                            logger.info(f"  {field}: {quote_data[field]}")

                    # JSON으로 예쁘게 출력 (일부만)
                    sample_data = {k: v for k, v in quote_data.items() if k in ['symbol', 'lastPrice', 'mark', 'bidPrice', 'askPrice', 'totalVolume', 'exchangeName', 'delayed']}
                    logger.info(f"  샘플 데이터: {json.dumps(sample_data, indent=2, default=str)}")
            else:
                logger.warning(f"{symbol} 데이터 없음")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_quotes())