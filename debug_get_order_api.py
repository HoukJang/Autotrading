"""
get_order API 사용법 디버깅

schwab-py의 정확한 get_order API 사용법을 확인합니다.
"""

import asyncio
import logging
from autotrading.core.context import create_shared_context

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 최근 주문 ID
ORDER_ID = "1004302916639"

async def debug_get_order_api():
    """get_order API 사용법 디버깅"""
    logger.info("=== get_order API 사용법 디버깅 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # 계좌 해시 및 번호 확인
        schwab_client = context['schwab_service']._client
        account_numbers_response = schwab_client.get_account_numbers()
        account_numbers_data = account_numbers_response.json()

        account_number = account_numbers_data[0]['accountNumber']
        account_hash = account_numbers_data[0]['hashValue']

        logger.info(f"계좌번호: {account_number}")
        logger.info(f"계좌해시: {account_hash}")
        logger.info(f"주문ID: {ORDER_ID}")

        # schwab_client의 메서드 시그너처 확인
        logger.info(f"get_order 메서드: {schwab_client.get_order}")

        # 다양한 방법으로 시도
        methods_to_try = [
            ("get_order(account_hash, order_id)", lambda: schwab_client.get_order(account_hash, ORDER_ID)),
            ("get_order(order_id, account_hash)", lambda: schwab_client.get_order(ORDER_ID, account_hash)),
            ("get_order(account_number, order_id)", lambda: schwab_client.get_order(account_number, ORDER_ID)),
            ("get_order(order_id, account_number)", lambda: schwab_client.get_order(ORDER_ID, account_number)),
        ]

        for method_name, method_call in methods_to_try:
            try:
                logger.info(f"\n--- {method_name} 시도 ---")
                response = method_call()
                logger.info(f"응답 상태: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ 성공! 주문 상태: {data.get('status', 'UNKNOWN')}")
                    logger.info(f"주문 데이터: {data}")
                    break
                else:
                    logger.warning(f"❌ 실패: {response.status_code} - {response.text}")

            except Exception as e:
                logger.error(f"❌ 오류: {e}")

        # 주문 리스트에서 해당 주문 찾기 (대안 방법)
        logger.info(f"\n--- 주문 리스트에서 찾기 ---")
        try:
            orders_response = schwab_client.get_orders_for_account(account_hash)
            orders_data = orders_response.json()

            logger.info(f"총 주문 수: {len(orders_data)}")

            for order in orders_data:
                order_id = order.get('orderId', 'UNKNOWN')
                status = order.get('status', 'UNKNOWN')
                logger.info(f"주문 ID: {order_id}, 상태: {status}")

                if order_id == ORDER_ID:
                    logger.info(f"✅ 찾은 주문: {order}")
                    break

        except Exception as e:
            logger.error(f"주문 리스트 조회 실패: {e}")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_get_order_api())