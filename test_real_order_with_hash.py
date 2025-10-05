"""
올바른 계좌 해시로 실제 주문 실행

get_account_numbers로 얻은 hashValue를 사용하여 실제 주문을 실행합니다.
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

async def test_real_order_with_hash():
    """올바른 계좌 해시로 실제 주문 실행"""
    logger.info("=== 올바른 계좌 해시로 실제 주문 실행 ===")

    try:
        # 1. 컨텍스트 생성
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("Schwab API 인증 실패")
            return

        # 2. 계좌 해시 확인
        schwab_client = context['schwab_service']._client
        account_numbers_response = schwab_client.get_account_numbers()
        account_numbers_data = account_numbers_response.json()

        account_info = account_numbers_data[0]
        account_number = account_info['accountNumber']
        account_hash = account_info['hashValue']

        logger.info(f"계좌번호: {account_number}")
        logger.info(f"계좌 해시: {account_hash}")

        # 3. 현재가 확인
        quotes = await context['schwab_service'].get_quotes([TEST_SYMBOL])
        quote_data = quotes[TEST_SYMBOL]
        quote_info = quote_data.get('quote', {})
        current_price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)

        logger.info(f"{TEST_SYMBOL} 현재가: ${current_price}")

        # 4. 주문 사양
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

        # 5. 실제 주문 실행 (올바른 해시 사용)
        logger.info("🚀 올바른 계좌 해시로 실제 주문 실행 중...")

        result = await context['schwab_service'].place_order(account_hash, order_spec)

        logger.info(f"✅ 주문 결과: {result}")

        # 6. 결과 분석
        if isinstance(result, dict):
            if 'orderId' in result:
                logger.info(f"🎉 주문 성공! Order ID: {result['orderId']}")
            elif 'message' in result:
                if 'Invalid account number' in result['message']:
                    logger.error(f"❌ 여전히 계좌번호 오류: {result['message']}")
                else:
                    logger.info(f"📝 응답 메시지: {result['message']}")
            else:
                logger.info(f"📝 주문 응답: {result}")
        else:
            logger.info(f"📝 Raw 응답: {result}")

        # 7. 주문 후 계좌 상태 확인
        await asyncio.sleep(5)

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
    await test_real_order_with_hash()

if __name__ == "__main__":
    asyncio.run(main())