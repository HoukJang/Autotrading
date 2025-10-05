"""
실제 계좌 데이터 구조 확인용 디버깅 스크립트
"""

import asyncio
import json
import logging
from autotrading.core.context import create_shared_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_accounts():
    """계좌 데이터 구조 디버깅"""
    logger.info("=== 계좌 데이터 구조 디버깅 ===")

    try:
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("인증 실패")
            return

        # 계좌 목록 조회
        accounts = await context['schwab_service'].get_accounts()

        logger.info(f"계좌 데이터 타입: {type(accounts)}")
        logger.info(f"계좌 수: {len(accounts)}")

        # 계좌 데이터 구조 출력
        for i, account in enumerate(accounts):
            logger.info(f"\n계좌 {i+1} 데이터:")
            logger.info(f"  타입: {type(account)}")
            logger.info(f"  키들: {list(account.keys()) if isinstance(account, dict) else 'Not a dict'}")

            # JSON으로 예쁘게 출력 (민감한 정보 마스킹)
            account_copy = dict(account) if isinstance(account, dict) else account
            if isinstance(account_copy, dict):
                # 민감한 정보 마스킹
                for key in list(account_copy.keys()):
                    if 'number' in key.lower() or 'account' in key.lower():
                        if isinstance(account_copy[key], str) and len(account_copy[key]) > 4:
                            account_copy[key] = account_copy[key][:4] + "****"

                logger.info(f"  내용: {json.dumps(account_copy, indent=2, default=str)}")

    except Exception as e:
        logger.error(f"오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_accounts())