"""
실제 주문 직전까지의 완전 검증 테스트

실제 주문은 실행하지 않고, 주문 직전까지의 모든 프로세스를 검증합니다.
실제 주문 실행 시점에서 DRY RUN으로 전환됩니다.
"""

import asyncio
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
TEST_QUANTITY = 1
MAX_ORDER_VALUE = 500.0

# DRY RUN 모드 (실제 주문 실행 방지)
DRY_RUN = True


async def validate_trading_readiness():
    """트레이딩 준비 상태 완전 검증"""
    logger.info("=== 트레이딩 준비 상태 완전 검증 ===")

    results = {
        'api_connection': False,
        'authentication': False,
        'account_access': False,
        'market_data': False,
        'trading_service': False,
        'order_validation': False,
        'safety_checks': False
    }

    try:
        # 1. API 연결 및 인증
        logger.info("\n--- 1. Schwab API 연결 및 인증 ---")
        context = await create_shared_context()

        if context['schwab_service'].is_authenticated():
            logger.info("✅ Schwab API 인증 성공")
            results['api_connection'] = True
            results['authentication'] = True
        else:
            logger.error("❌ Schwab API 인증 실패")
            return results

        # 2. 계좌 접근 검증
        logger.info("\n--- 2. 계좌 접근 검증 ---")
        accounts = await context['schwab_service'].get_accounts()

        if accounts:
            account_info = accounts[0].get('securitiesAccount', {})
            account_number = account_info.get('accountNumber')
            account_type = account_info.get('type')
            balances = account_info.get('currentBalances', {})

            logger.info(f"✅ 계좌번호: {account_number}")
            logger.info(f"✅ 계좌유형: {account_type}")
            logger.info(f"✅ 가용자금: ${balances.get('availableFunds', 0):,.2f}")
            logger.info(f"✅ 총자산: ${balances.get('liquidationValue', 0):,.2f}")

            results['account_access'] = True
        else:
            logger.error("❌ 계좌 정보 조회 실패")
            return results

        # 3. 시장 데이터 접근 검증
        logger.info(f"\n--- 3. {TEST_SYMBOL} 시장 데이터 접근 검증 ---")
        quotes = await context['schwab_service'].get_quotes([TEST_SYMBOL])

        if TEST_SYMBOL in quotes:
            quote_data = quotes[TEST_SYMBOL]
            quote_info = quote_data.get('quote', {})

            current_price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)
            bid = quote_info.get('bidPrice', 0)
            ask = quote_info.get('askPrice', 0)
            volume = quote_info.get('totalVolume', 0)

            logger.info(f"✅ 현재가: ${current_price}")
            logger.info(f"✅ 매수호가: ${bid}")
            logger.info(f"✅ 매도호가: ${ask}")
            logger.info(f"✅ 거래량: {volume:,}")

            if current_price > 0:
                results['market_data'] = True
            else:
                logger.error("❌ 유효하지 않은 가격 데이터")
                return results
        else:
            logger.error(f"❌ {TEST_SYMBOL} 시세 데이터 없음")
            return results

        # 4. TradingService 초기화 검증
        logger.info("\n--- 4. TradingService 초기화 검증 ---")
        trading_service = TradingService(context['schwab_service'])

        logger.info("✅ TradingService 초기화 성공")
        results['trading_service'] = True

        # 5. 주문 생성 로직 검증 (실제 실행 없음)
        logger.info("\n--- 5. 주문 생성 로직 검증 ---")

        # 시장가 매수 주문 스펙 생성
        try:
            # 포지션 사이즈 계산 테스트
            position_calc = await trading_service.calculate_position_size(
                account_hash=account_number,
                symbol=TEST_SYMBOL,
                risk_percentage=0.01,
                entry_price=current_price,
                stop_loss_price=current_price * 0.95
            )

            logger.info("✅ 포지션 사이즈 계산 성공")
            logger.info(f"   계산된 포지션: {position_calc['calculated_position_size']}주")
            logger.info(f"   리스크 금액: ${position_calc['risk_amount']:,.2f}")

            # 주문 스펙 검증 (TradingService 내부 로직 테스트)
            market_order_spec = {
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

            # 주문 검증 로직 테스트
            trading_service._validate_order(market_order_spec)
            logger.info("✅ 주문 스펙 검증 통과")

            results['order_validation'] = True

        except TradingException as e:
            logger.error(f"❌ 주문 검증 실패: {e}")
            return results

        # 6. 안전성 검사
        logger.info("\n--- 6. 안전성 검사 ---")

        order_value = current_price * TEST_QUANTITY
        available_funds = balances.get('availableFunds', 0)

        logger.info(f"주문 예상 금액: ${order_value:.2f}")
        logger.info(f"가용 자금: ${available_funds:,.2f}")
        logger.info(f"안전 한도: ${MAX_ORDER_VALUE}")

        safety_checks = []

        # 가격 유효성
        if current_price > 0:
            safety_checks.append("✅ 유효한 가격")
        else:
            safety_checks.append("❌ 무효한 가격")

        # 자금 충분성
        if available_funds >= order_value:
            safety_checks.append("✅ 충분한 자금")
        else:
            safety_checks.append("❌ 자금 부족")

        # 안전 한도
        if order_value <= MAX_ORDER_VALUE:
            safety_checks.append("✅ 안전 한도 내")
        else:
            safety_checks.append("❌ 안전 한도 초과")

        # 거래량 충분성
        if volume > 100000:
            safety_checks.append("✅ 충분한 거래량")
        else:
            safety_checks.append("⚠️ 적은 거래량")

        # 시장 시간 (간접 확인)
        if bid > 0 and ask > 0:
            safety_checks.append("✅ 시장 활성 상태")
        else:
            safety_checks.append("⚠️ 시장 비활성 가능성")

        for check in safety_checks:
            logger.info(f"   {check}")

        if all("✅" in check for check in safety_checks if "⚠️" not in check):
            results['safety_checks'] = True
            logger.info("✅ 모든 안전성 검사 통과")
        else:
            logger.warning("⚠️ 일부 안전성 검사 실패")

        # 7. 실제 주문 실행 준비 상태 확인
        logger.info("\n--- 7. 실제 주문 실행 준비 상태 ---")

        if DRY_RUN:
            logger.info("🔒 DRY RUN 모드: 실제 주문 실행하지 않음")
            logger.info("🎯 실제 주문 실행 준비 완료 상태!")

            # 모든 조건이 만족되면 실제 주문 실행이 가능함을 확인
            all_ready = all(results.values())
            if all_ready:
                logger.info("🚀 모든 시스템이 실제 주문 실행 준비 완료!")

                # 실제 주문 시뮬레이션 (로그만)
                logger.info("\n=== 실제 주문 시뮬레이션 ===")
                logger.info(f"매수 주문: {TEST_SYMBOL} {TEST_QUANTITY}주 @ 시장가")
                logger.info(f"예상 비용: ${order_value:.2f}")
                logger.info("주문 상태: 체결 대기 중...")
                await asyncio.sleep(2)
                logger.info("주문 상태: 체결 완료 (시뮬레이션)")

                logger.info("\n매도 주문: 포지션 정리")
                logger.info(f"매도 주문: {TEST_SYMBOL} {TEST_QUANTITY}주 @ 시장가")
                logger.info("주문 상태: 체결 대기 중...")
                await asyncio.sleep(2)
                logger.info("주문 상태: 체결 완료 (시뮬레이션)")

                logger.info("🎉 주문 사이클 시뮬레이션 완료!")

        return results

    except Exception as e:
        logger.error(f"❌ 검증 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return results


async def main():
    """메인 검증 함수"""
    logger.info("=== 실제 주문 실행 준비 상태 완전 검증 ===")
    logger.info(f"검증 시간: {datetime.now()}")
    logger.info(f"DRY RUN 모드: {DRY_RUN}")

    # 완전 검증 실행
    results = await validate_trading_readiness()

    # 결과 요약
    logger.info("\n" + "="*60)
    logger.info("검증 결과 요약")
    logger.info("="*60)

    total_checks = len(results)
    passed_checks = sum(results.values())

    for check_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{check_name:<20}: {status}")

    success_rate = (passed_checks / total_checks) * 100
    logger.info(f"\n성공률: {passed_checks}/{total_checks} ({success_rate:.1f}%)")

    if success_rate == 100:
        logger.info("🎉 모든 검증 통과! 실제 주문 실행 준비 완료!")
        logger.info("\n실제 주문을 실행하려면:")
        logger.info("1. DRY_RUN = False로 설정")
        logger.info("2. 안전 확인 절차 포함")
        logger.info("3. 수동 승인 과정 추가")
    else:
        logger.warning("⚠️ 일부 검증 실패. 문제를 해결 후 재시도하세요.")


if __name__ == "__main__":
    asyncio.run(main())