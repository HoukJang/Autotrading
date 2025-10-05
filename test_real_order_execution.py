"""
실제 주문 실행 테스트

Schwab API의 정확한 스펙에 맞춰 실제 주문을 실행합니다.
"""

import asyncio
import logging
from datetime import datetime
from autotrading.core.context import create_shared_context

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 테스트 설정
TEST_SYMBOL = "AAPL"
TEST_QUANTITY = 1

async def test_real_order_execution():
    """실제 주문 실행 테스트"""
    logger.info("=== 실제 주문 실행 테스트 ===")

    try:
        # 1. 컨텍스트 생성
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("Schwab API 인증 실패")
            return

        # 2. 계좌 정보 확인
        accounts = await context['schwab_service'].get_accounts()
        account_info = accounts[0].get('securitiesAccount', {})
        account_number = account_info.get('accountNumber')

        logger.info(f"계좌번호: {account_number}")

        # 3. 현재가 확인
        quotes = await context['schwab_service'].get_quotes([TEST_SYMBOL])
        quote_data = quotes[TEST_SYMBOL]
        quote_info = quote_data.get('quote', {})
        current_price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)

        logger.info(f"{TEST_SYMBOL} 현재가: ${current_price}")

        # 4. 주문 사양 - Schwab API 정확한 형식
        order_spec = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": TEST_QUANTITY,
                    "instrument": {
                        "symbol": TEST_SYMBOL,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        logger.info("주문 사양:")
        logger.info(f"  Symbol: {TEST_SYMBOL}")
        logger.info(f"  Quantity: {TEST_QUANTITY}")
        logger.info(f"  Type: MARKET BUY")
        logger.info(f"  예상 비용: ${current_price * TEST_QUANTITY:.2f}")

        # 5. 실제 주문 실행
        logger.info("🚀 실제 주문 실행 중...")

        # schwab_service의 place_order 직접 호출
        result = await context['schwab_service'].place_order(account_number, order_spec)

        logger.info(f"✅ 주문 결과: {result}")

        # 6. 결과 분석
        if isinstance(result, dict):
            if 'orderId' in result:
                logger.info(f"🎉 주문 성공! Order ID: {result['orderId']}")
            elif 'error' in result:
                logger.error(f"❌ 주문 실패: {result['error']}")
            else:
                logger.info(f"📝 주문 응답: {result}")
        else:
            logger.info(f"📝 Raw 응답: {result}")

        # 7. 잠시 후 계좌 상태 재확인
        await asyncio.sleep(3)

        logger.info("\n--- 주문 후 계좌 상태 확인 ---")
        accounts_after = await context['schwab_service'].get_accounts()
        account_info_after = accounts_after[0].get('securitiesAccount', {})
        balances_after = account_info_after.get('currentBalances', {})
        positions_after = account_info_after.get('positions', [])

        logger.info(f"가용자금: ${balances_after.get('availableFunds', 0):,.2f}")
        logger.info(f"포지션 수: {len(positions_after)}")

        for position in positions_after:
            instrument = position.get('instrument', {})
            symbol = instrument.get('symbol', 'N/A')
            quantity = position.get('longQuantity', 0) - position.get('shortQuantity', 0)
            if quantity != 0:
                logger.info(f"  {symbol}: {quantity}주")

    except Exception as e:
        logger.error(f"❌ 주문 실행 실패: {e}")
        import traceback
        traceback.print_exc()

async def main():
    await test_real_order_execution()

if __name__ == "__main__":
    asyncio.run(main())