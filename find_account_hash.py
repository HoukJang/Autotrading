"""
계좌 해시 찾기

schwab-py를 통해 올바른 계좌 해시를 찾습니다.
"""

import asyncio
import logging
from autotrading.core.context import create_shared_context

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def find_account_hash():
    """계좌 해시 찾기"""
    logger.info("=== 계좌 해시 찾기 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # schwab 클라이언트에 직접 접근
        schwab_client = context['schwab_service']._client

        logger.info("schwab 클라이언트 타입:")
        logger.info(f"  클라이언트: {type(schwab_client)}")
        logger.info(f"  메서드들: {[method for method in dir(schwab_client) if not method.startswith('_')]}")

        # get_account_numbers 시도
        try:
            logger.info("get_account_numbers 호출 중...")
            account_numbers_response = schwab_client.get_account_numbers()
            logger.info(f"계좌 번호 응답: {account_numbers_response}")

            if hasattr(account_numbers_response, 'json'):
                account_numbers_data = account_numbers_response.json()
                logger.info(f"계좌 번호 데이터: {account_numbers_data}")

        except Exception as e:
            logger.warning(f"get_account_numbers 실패: {e}")

        # schwab 클라이언트의 다른 계좌 관련 메서드들 확인
        account_methods = [method for method in dir(schwab_client) if 'account' in method.lower()]
        logger.info(f"계좌 관련 메서드들: {account_methods}")

        # 각 메서드 시도
        for method_name in account_methods:
            if method_name.startswith('get_'):
                try:
                    method = getattr(schwab_client, method_name)
                    logger.info(f"\n{method_name} 시도 중...")

                    # 파라미터가 없는 메서드만 시도
                    if method_name in ['get_account_numbers']:
                        result = method()
                        logger.info(f"{method_name} 결과: {result}")

                        if hasattr(result, 'json'):
                            data = result.json()
                            logger.info(f"{method_name} JSON: {data}")

                except Exception as e:
                    logger.warning(f"{method_name} 실패: {e}")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(find_account_hash())