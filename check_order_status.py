"""
실제 주문 상태 확인 스크립트

최근 실행된 주문들의 상태를 확인합니다.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from autotrading.core.context import create_shared_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_recent_orders():
    """최근 주문 상태 확인"""
    logger.info("=== 최근 주문 상태 확인 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("❌ Schwab API 인증 실패")
            return

        # 계좌 정보 확인
        accounts = await context['schwab_service'].get_accounts()
        account_hash = accounts[0].get('securitiesAccount', {}).get('accountNumber')

        logger.info(f"계좌번호: {account_hash}")

        # 현재 포지션 확인
        logger.info("\n--- 현재 계좌 상태 ---")
        account_info = accounts[0].get('securitiesAccount', {})
        current_balances = account_info.get('currentBalances', {})

        logger.info(f"가용자금: ${current_balances.get('availableFunds', 0):,.2f}")
        logger.info(f"총자산: ${current_balances.get('liquidationValue', 0):,.2f}")
        logger.info(f"현금잔액: ${current_balances.get('cashBalance', 0):,.2f}")

        # 포지션 확인 (positions 배열 확인)
        positions = account_info.get('positions', [])
        logger.info(f"\n현재 포지션 수: {len(positions)}")

        for i, position in enumerate(positions):
            instrument = position.get('instrument', {})
            symbol = instrument.get('symbol', 'N/A')
            quantity = position.get('longQuantity', 0) - position.get('shortQuantity', 0)
            market_value = position.get('marketValue', 0)

            if quantity != 0:  # 0이 아닌 포지션만 표시
                logger.info(f"포지션 {i+1}: {symbol} {quantity}주, 가치: ${market_value:,.2f}")

        # API가 지원한다면 최근 주문 확인
        logger.info("\n--- 주문 히스토리 확인 시도 ---")
        try:
            # 일부 주문 조회 API 호출 시도
            # 실제로는 schwab API 문서에 따라 구현해야 함
            logger.info("주문 히스토리 API 호출 방법 확인 필요")
        except Exception as e:
            logger.info(f"주문 히스토리 조회 제한: {e}")

        # AAPL 현재가 확인
        logger.info("\n--- AAPL 현재가 확인 ---")
        quotes = await context['schwab_service'].get_quotes(["AAPL"])
        if "AAPL" in quotes:
            quote_data = quotes["AAPL"]
            quote_info = quote_data.get('quote', {})
            current_price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)
            logger.info(f"AAPL 현재가: ${current_price}")

    except Exception as e:
        logger.error(f"❌ 주문 상태 확인 실패: {e}")
        import traceback
        traceback.print_exc()


async def main():
    await check_recent_orders()


if __name__ == "__main__":
    asyncio.run(main())