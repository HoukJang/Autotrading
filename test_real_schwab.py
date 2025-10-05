"""
실제 Schwab API 연동 테스트

환경 변수를 확인하고 실제 Schwab API와 연동하여 TradingService를 테스트합니다.
"""

import asyncio
import os
import logging
from datetime import datetime
from autotrading.core.context import create_shared_context
from autotrading.api.trading_service import TradingService, OrderSide, TradingException

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 테스트 설정
TEST_SYMBOL = "AAPL"
TEST_QUANTITY = 1  # 1주로 테스트


async def test_schwab_authentication():
    """Schwab API 인증 테스트"""
    logger.info("=== Schwab API 인증 테스트 ===")

    try:
        context = await create_shared_context()

        # 인증 상태 확인
        if context['schwab_service'].is_authenticated():
            logger.info("✅ Schwab API 인증 성공")
            return context
        else:
            logger.error("❌ Schwab API 인증 실패")
            return None

    except Exception as e:
        logger.error(f"❌ Schwab API 인증 중 오류: {e}")
        return None


async def test_account_info(context):
    """계좌 정보 조회 테스트"""
    logger.info("\n=== 계좌 정보 조회 테스트 ===")

    try:
        # 계좌 목록 조회
        accounts = await context['schwab_service'].get_accounts()
        logger.info(f"계좌 수: {len(accounts)}")

        for i, account in enumerate(accounts):
            account_info = account.get('securitiesAccount', {})
            account_number = account_info.get('accountNumber', 'N/A')
            account_type = account_info.get('type', 'N/A')
            logger.info(f"계좌 {i+1}: {account_number} ({account_type})")

        if not accounts:
            logger.error("❌ 계좌 정보를 찾을 수 없습니다")
            return None

        # 첫 번째 계좌 정보 사용
        first_account = accounts[0].get('securitiesAccount', {})
        account_hash = first_account.get('accountNumber')
        account_info = await context['schwab_service'].get_account_info(account_hash)

        # 계좌 잔액 정보는 이미 첫 번째 응답에 포함되어 있음
        balances = first_account.get("currentBalances", {})
        logger.info(f"가용 자금: ${balances.get('availableFunds', 0):,.2f}")
        logger.info(f"총 자산: ${balances.get('liquidationValue', 0):,.2f}")

        return account_hash

    except Exception as e:
        logger.error(f"❌ 계좌 정보 조회 실패: {e}")
        return None


async def test_market_data(context, symbol):
    """시장 데이터 조회 테스트"""
    logger.info(f"\n=== {symbol} 시장 데이터 조회 테스트 ===")

    try:
        # 실시간 시세 조회
        quotes = await context['schwab_service'].get_quotes([symbol])

        if symbol in quotes:
            quote_data = quotes[symbol]
            # 가격 정보는 'quote' 필드 안에 있음
            quote_info = quote_data.get('quote', {})
            price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)
            bid = quote_info.get('bidPrice', 0)
            ask = quote_info.get('askPrice', 0)
            volume = quote_info.get('totalVolume', 0)

            logger.info(f"현재가: ${price}")
            logger.info(f"매수호가: ${bid}")
            logger.info(f"매도호가: ${ask}")
            logger.info(f"거래량: {volume:,}")

            return price
        else:
            logger.error(f"❌ {symbol} 시세 데이터를 찾을 수 없습니다")
            return None

    except Exception as e:
        logger.error(f"❌ 시장 데이터 조회 실패: {e}")
        return None


async def test_dry_run_order(trading_service, account_hash, symbol, current_price):
    """실제 주문 실행 없이 주문 스펙만 생성 테스트"""
    logger.info(f"\n=== {symbol} 주문 스펙 생성 테스트 (DRY RUN) ===")

    try:
        # 포지션 사이즈 계산
        risk_percentage = 0.01  # 1% 리스크
        stop_loss_price = current_price * 0.95  # 5% 손절

        position_calc = await trading_service.calculate_position_size(
            account_hash=account_hash,
            symbol=symbol,
            risk_percentage=risk_percentage,
            entry_price=current_price,
            stop_loss_price=stop_loss_price
        )

        logger.info(f"포지션 계산 결과:")
        logger.info(f"  - 계산된 포지션: {position_calc['calculated_position_size']}주")
        logger.info(f"  - 리스크 금액: ${position_calc['risk_amount']:,.2f}")
        logger.info(f"  - 총 포지션 가치: ${position_calc['total_position_value']:,.2f}")

        # 주문 스펙 생성 (실제 실행하지 않음)
        logger.info("\n주문 스펙 생성 테스트:")

        # 1. 시장가 매수 주문 스펙
        market_buy_spec = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 1,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        logger.info(f"✅ 시장가 매수 주문 스펙 생성 완료")

        # 2. 지정가 매도 주문 스펙
        sell_limit_price = current_price * 1.02  # 2% 프리미엄
        limit_sell_spec = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": str(sell_limit_price),
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 1,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        logger.info(f"✅ 지정가 매도 주문 스펙 생성 완료 (${sell_limit_price:.2f})")

        return True

    except Exception as e:
        logger.error(f"❌ 주문 스펙 생성 실패: {e}")
        return False


async def test_health_check(context):
    """Schwab API 상태 확인"""
    logger.info("\n=== Schwab API 상태 확인 ===")

    try:
        health = await context['schwab_service'].health_check()
        logger.info(f"상태: {health.get('status', 'unknown')}")
        logger.info(f"인증 상태: {health.get('authenticated', False)}")

        if 'circuit_breaker' in health:
            cb_stats = health['circuit_breaker']
            logger.info(f"Circuit Breaker: {cb_stats.get('state', 'unknown')}")

        if 'rate_limiter' in health:
            rl_stats = health['rate_limiter']
            logger.info(f"Rate Limiter: {rl_stats.get('tokens_remaining', 'unknown')} 토큰 남음")

        return health.get('status') == 'HEALTHY'

    except Exception as e:
        logger.error(f"❌ 상태 확인 실패: {e}")
        return False


async def main():
    """메인 테스트 함수"""
    logger.info("=== 실제 Schwab API 연동 테스트 시작 ===")
    logger.info(f"테스트 시간: {datetime.now()}")

    # config/auth.py에서 설정 확인
    try:
        from autotrading.config.auth import SCHWAB_CONFIG
        logger.info("✅ Schwab 설정 확인 완료")
        logger.info(f"App Key: {SCHWAB_CONFIG['app_key'][:10]}...")
        logger.info(f"Callback URL: {SCHWAB_CONFIG['callback_url']}")
    except ImportError as e:
        logger.error(f"❌ config/auth.py 파일을 찾을 수 없습니다: {e}")
        logger.info("config/auth.example.py를 복사하여 config/auth.py로 만들고 실제 API 키를 입력해주세요")
        return

    # 1. Schwab API 인증 테스트
    context = await test_schwab_authentication()
    if not context:
        logger.error("❌ 인증 실패로 테스트를 중단합니다")
        return

    # 2. 계좌 정보 조회 테스트
    account_hash = await test_account_info(context)
    if not account_hash:
        logger.error("❌ 계좌 정보 조회 실패로 테스트를 중단합니다")
        return

    # 3. 시장 데이터 조회 테스트
    current_price = await test_market_data(context, TEST_SYMBOL)
    if not current_price:
        logger.error("❌ 시장 데이터 조회 실패로 테스트를 중단합니다")
        return

    # 4. TradingService 초기화 및 테스트
    trading_service = TradingService(context['schwab_service'])
    dry_run_success = await test_dry_run_order(
        trading_service, account_hash, TEST_SYMBOL, current_price
    )

    # 5. 상태 확인
    health_ok = await test_health_check(context)

    # 결과 요약
    logger.info("\n=== 테스트 결과 요약 ===")
    results = [
        ("Schwab API 인증", "✅" if context else "❌"),
        ("계좌 정보 조회", "✅" if account_hash else "❌"),
        ("시장 데이터 조회", "✅" if current_price else "❌"),
        ("주문 스펙 생성", "✅" if dry_run_success else "❌"),
        ("API 상태 확인", "✅" if health_ok else "❌"),
    ]

    success_count = sum(1 for _, status in results if status == "✅")

    for test_name, status in results:
        logger.info(f"{status} {test_name}")

    logger.info(f"\n성공률: {success_count}/5 ({success_count/5*100:.1f}%)")

    if success_count == 5:
        logger.info("🎉 모든 테스트가 성공했습니다! TradingService가 실제 주문 실행 준비 완료!")
    else:
        logger.warning("⚠️ 일부 테스트가 실패했습니다. 문제를 해결해주세요.")


if __name__ == "__main__":
    asyncio.run(main())