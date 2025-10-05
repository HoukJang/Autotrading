"""
계좌 정보 상세 디버깅

계좌번호와 해시 정보를 정확히 파악합니다.
"""

import asyncio
import logging
import json
from autotrading.core.context import create_shared_context

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_account_info():
    """계좌 정보 상세 분석"""
    logger.info("=== 계좌 정보 상세 디버깅 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # 원본 계좌 정보 가져오기
        accounts = await context['schwab_service'].get_accounts()

        logger.info(f"계좌 수: {len(accounts)}")

        for i, account in enumerate(accounts):
            logger.info(f"\n--- 계좌 {i+1} 상세 정보 ---")
            logger.info(f"전체 응답 구조: {json.dumps(account, indent=2, default=str)}")

            # 다양한 계좌 식별자 확인
            securities_account = account.get('securitiesAccount', {})

            logger.info(f"\nSecurities Account 정보:")
            logger.info(f"  accountNumber: {securities_account.get('accountNumber')}")
            logger.info(f"  accountId: {securities_account.get('accountId')}")
            logger.info(f"  hashValue: {securities_account.get('hashValue')}")
            logger.info(f"  accountColor: {securities_account.get('accountColor')}")
            logger.info(f"  type: {securities_account.get('type')}")

            # 최상위 레벨 정보도 확인
            logger.info(f"\n최상위 레벨 정보:")
            for key in account.keys():
                if key != 'securitiesAccount':
                    logger.info(f"  {key}: {account[key]}")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_account_info())