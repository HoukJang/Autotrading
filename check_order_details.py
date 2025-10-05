"""
주문 상태 및 체결 확인

실제 주문 ID를 사용하여 주문 상태와 체결 내역을 확인합니다.
"""

import asyncio
import logging
from autotrading.core.context import create_shared_context

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 방금 실행한 주문 ID
ORDER_ID = "1004302916359"

async def check_order_details():
    """주문 상태 상세 확인"""
    logger.info("=== 주문 상태 및 체결 확인 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # 계좌 해시 획득
        schwab_client = context['schwab_service']._client
        account_numbers_response = schwab_client.get_account_numbers()
        account_numbers_data = account_numbers_response.json()
        account_hash = account_numbers_data[0]['hashValue']

        logger.info(f"주문 ID: {ORDER_ID}")
        logger.info(f"계좌 해시: {account_hash}")

        # 1. 특정 주문 상태 확인
        try:
            logger.info("\n--- 특정 주문 상태 확인 ---")
            order_response = schwab_client.get_order(account_hash, ORDER_ID)
            order_data = order_response.json()

            logger.info(f"주문 상태: {order_data.get('status', 'UNKNOWN')}")
            logger.info(f"주문 유형: {order_data.get('orderType', 'UNKNOWN')}")
            logger.info(f"수량: {order_data.get('quantity', 'UNKNOWN')}")

            # 주문 세부 정보
            if 'orderLegCollection' in order_data:
                for leg in order_data['orderLegCollection']:
                    instrument = leg.get('instrument', {})
                    logger.info(f"종목: {instrument.get('symbol', 'UNKNOWN')}")
                    logger.info(f"지시: {leg.get('instruction', 'UNKNOWN')}")

            # 체결 정보
            if 'orderActivityCollection' in order_data:
                logger.info("\n체결 내역:")
                for activity in order_data['orderActivityCollection']:
                    execution_legs = activity.get('executionLegs', [])
                    for execution in execution_legs:
                        logger.info(f"  체결가: ${execution.get('price', 0)}")
                        logger.info(f"  체결량: {execution.get('quantity', 0)}")
                        logger.info(f"  체결시간: {execution.get('time', 'UNKNOWN')}")

        except Exception as e:
            logger.warning(f"특정 주문 조회 실패: {e}")

        # 2. 최근 주문 리스트 확인
        try:
            logger.info("\n--- 최근 주문 리스트 ---")
            orders_response = schwab_client.get_orders_for_account(account_hash)
            orders_data = orders_response.json()

            logger.info(f"총 주문 수: {len(orders_data)}")

            # 최근 5개 주문만 표시
            for i, order in enumerate(orders_data[:5]):
                logger.info(f"\n주문 {i+1}:")
                logger.info(f"  ID: {order.get('orderId', 'UNKNOWN')}")
                logger.info(f"  상태: {order.get('status', 'UNKNOWN')}")
                logger.info(f"  시간: {order.get('enteredTime', 'UNKNOWN')}")

                if 'orderLegCollection' in order:
                    for leg in order['orderLegCollection']:
                        instrument = leg.get('instrument', {})
                        logger.info(f"  종목: {instrument.get('symbol', 'UNKNOWN')}")
                        logger.info(f"  지시: {leg.get('instruction', 'UNKNOWN')}")
                        logger.info(f"  수량: {leg.get('quantity', 'UNKNOWN')}")

        except Exception as e:
            logger.warning(f"주문 리스트 조회 실패: {e}")

        # 3. 계좌 상태 재확인
        logger.info("\n--- 현재 계좌 상태 ---")
        accounts = await context['schwab_service'].get_accounts()
        account_info = accounts[0].get('securitiesAccount', {})
        balances = account_info.get('currentBalances', {})
        positions = account_info.get('positions', [])

        logger.info(f"가용자금: ${balances.get('availableFunds', 0):,.2f}")
        logger.info(f"총자산: ${balances.get('liquidationValue', 0):,.2f}")
        logger.info(f"현재 포지션 수: {len(positions)}")

        for position in positions:
            instrument = position.get('instrument', {})
            symbol = instrument.get('symbol', 'N/A')
            long_qty = position.get('longQuantity', 0)
            short_qty = position.get('shortQuantity', 0)
            net_qty = long_qty - short_qty

            if net_qty != 0:
                market_value = position.get('marketValue', 0)
                logger.info(f"  {symbol}: {net_qty}주, 가치: ${market_value:,.2f}")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_order_details())