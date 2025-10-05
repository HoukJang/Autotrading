"""
schwab-py 라이브러리 직접 테스트

계좌 해시와 주문 API를 직접 확인합니다.
"""

import asyncio
import logging
import json
import schwab
from autotrading.config.auth import SCHWAB_CONFIG

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_schwab_direct():
    """schwab 라이브러리 직접 테스트"""
    logger.info("=== schwab-py 라이브러리 직접 테스트 ===")

    try:
        # 1. schwab 클라이언트 직접 생성
        client = schwab.client.AsyncClient(
            app_key=SCHWAB_CONFIG["app_key"],
            app_secret=SCHWAB_CONFIG["app_secret"],
            callback_url=SCHWAB_CONFIG["callback_url"],
            token_path="tokens.json"
        )

        # 2. 계좌 정보 확인
        logger.info("계좌 정보 조회 중...")
        accounts_response = client.get_accounts()
        accounts_data = accounts_response.json()

        logger.info(f"응답 타입: {type(accounts_response)}")
        logger.info(f"상태 코드: {accounts_response.status_code}")

        # 3. 계좌 해시 찾기
        for account in accounts_data:
            securities_account = account.get('securitiesAccount', {})
            account_number = securities_account.get('accountNumber')

            logger.info(f"계좌 번호: {account_number}")

            # 4. 계좌 해시 조회 (다른 API 엔드포인트 시도)
            logger.info("계좌 해시 조회 시도...")
            try:
                # get_account로 단일 계좌 정보 조회
                account_detail_response = client.get_account(account_number)
                account_detail = account_detail_response.json()

                logger.info(f"단일 계좌 응답: {json.dumps(account_detail, indent=2, default=str)}")

            except Exception as e:
                logger.warning(f"단일 계좌 조회 실패: {e}")

            # 5. 주문 테스트 (실제 계좌번호로)
            logger.info(f"계좌번호 {account_number}로 주문 테스트...")

            order_spec = {
                "orderType": "MARKET",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "BUY",
                        "quantity": 1,
                        "instrument": {
                            "symbol": "AAPL",
                            "assetType": "EQUITY"
                        }
                    }
                ]
            }

            try:
                logger.info("주문 실행 중...")
                order_response = client.place_order(account_number, order_spec)
                logger.info(f"주문 응답 상태: {order_response.status_code}")
                logger.info(f"주문 응답 내용: {order_response.text}")

                if order_response.status_code == 201:
                    logger.info("🎉 주문 성공!")
                elif order_response.status_code == 400:
                    logger.error(f"❌ 400 오류: {order_response.text}")
                else:
                    logger.warning(f"⚠️ 예상치 못한 응답: {order_response.status_code}")

            except Exception as e:
                logger.error(f"주문 실행 오류: {e}")

    except Exception as e:
        logger.error(f"전체 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_schwab_direct())