"""
실제 소액 주문 테스트

⚠️ 주의사항:
- 실제 자금이 사용됩니다
- 매우 작은 금액(1주)으로만 테스트합니다
- 모든 주문은 수동 확인 후 실행됩니다
- 안전 장치가 내장되어 있습니다
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

# 안전 설정
MAX_ORDER_VALUE = 500.0  # 최대 주문 금액: $500
MAX_QUANTITY = 1         # 최대 수량: 1주
TEST_SYMBOL = "AAPL"     # 테스트 종목

# 안전 확인 플래그
SAFETY_CONFIRMED = False


def safety_check():
    """안전 확인 절차"""
    global SAFETY_CONFIRMED

    print("\n" + "="*60)
    print("*** REAL ORDER TEST SAFETY CHECK ***")
    print("="*60)
    print(f"Test Symbol: {TEST_SYMBOL}")
    print(f"Max Quantity: {MAX_QUANTITY} shares")
    print(f"Max Order Value: ${MAX_ORDER_VALUE}")
    print("\nWARNING:")
    print("- Real money will be used")
    print("- Losses may occur due to market conditions")
    print("- Position will be closed immediately after test")
    print("="*60)

    response = input("\nDo you confirm and want to proceed with real order test? (yes/no): ").strip().lower()

    if response == "yes":
        SAFETY_CONFIRMED = True
        print("SAFETY CONFIRMED. Proceeding with test.")
        return True
    else:
        print("Test cancelled.")
        return False


async def get_current_price_and_validate(context, symbol):
    """현재가 조회 및 주문 가능성 검증"""
    logger.info(f"\n=== {symbol} 현재가 조회 및 검증 ===")

    try:
        quotes = await context['schwab_service'].get_quotes([symbol])

        if symbol not in quotes:
            logger.error(f"❌ {symbol} 시세 정보를 찾을 수 없습니다")
            return None

        quote_data = quotes[symbol]
        quote_info = quote_data.get('quote', {})

        price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)
        bid = quote_info.get('bidPrice', 0)
        ask = quote_info.get('askPrice', 0)
        volume = quote_info.get('totalVolume', 0)

        logger.info(f"현재가: ${price}")
        logger.info(f"매수호가: ${bid}")
        logger.info(f"매도호가: ${ask}")
        logger.info(f"거래량: {volume:,}")

        # 안전성 검증
        order_value = price * MAX_QUANTITY

        if price <= 0:
            logger.error("❌ 유효하지 않은 가격")
            return None

        if order_value > MAX_ORDER_VALUE:
            logger.error(f"❌ 주문 금액(${order_value:.2f})이 안전 한도(${MAX_ORDER_VALUE})를 초과합니다")
            return None

        if volume < 100000:  # 거래량이 너무 적으면 위험
            logger.warning(f"⚠️ 거래량이 적습니다: {volume:,}")

        logger.info(f"✅ 주문 가능 - 예상 금액: ${order_value:.2f}")
        return price

    except Exception as e:
        logger.error(f"❌ 시장 데이터 조회 실패: {e}")
        return None


async def place_market_buy_order(trading_service, account_hash, symbol, quantity):
    """실제 시장가 매수 주문 실행"""
    logger.info(f"\n=== 시장가 매수 주문 실행 ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}주")

    try:
        # 주문 실행
        result = await trading_service.create_market_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity
        )

        logger.info(f"✅ 매수 주문 성공!")
        logger.info(f"주문 ID: {result.get('order_id', 'unknown')}")
        logger.info(f"주문 시간: {result.get('timestamp', 'unknown')}")

        return result

    except TradingException as e:
        logger.error(f"❌ 매수 주문 실패: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ 예상치 못한 오류: {e}")
        return None


async def monitor_order_status(trading_service, account_hash, order_id, max_wait_minutes=5):
    """주문 상태 모니터링"""
    logger.info(f"\n=== 주문 상태 모니터링 ===")
    logger.info(f"주문 ID: {order_id}")

    start_time = datetime.now()
    max_wait_seconds = max_wait_minutes * 60

    while True:
        try:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > max_wait_seconds:
                logger.warning(f"⚠️ 모니터링 시간 초과 ({max_wait_minutes}분)")
                break

            # 주문 상태 조회 (실제 구현에서는 schwab API 사용)
            logger.info(f"주문 상태 확인 중... (경과: {elapsed:.0f}초)")

            # 주문이 체결되었다고 가정 (실제로는 API 응답 확인 필요)
            await asyncio.sleep(10)  # 10초마다 확인

            logger.info("✅ 주문이 체결된 것으로 가정합니다")
            break

        except Exception as e:
            logger.error(f"❌ 주문 상태 조회 실패: {e}")
            await asyncio.sleep(5)

    return True


async def place_market_sell_order(trading_service, account_hash, symbol, quantity):
    """실제 시장가 매도 주문 실행 (포지션 정리)"""
    logger.info(f"\n=== 시장가 매도 주문 실행 (포지션 정리) ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}주")

    try:
        # 매도 주문 실행
        result = await trading_service.create_market_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity
        )

        logger.info(f"✅ 매도 주문 성공!")
        logger.info(f"주문 ID: {result.get('order_id', 'unknown')}")
        logger.info(f"주문 시간: {result.get('timestamp', 'unknown')}")

        return result

    except TradingException as e:
        logger.error(f"❌ 매도 주문 실패: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ 예상치 못한 오류: {e}")
        return None


async def get_account_positions(context, account_hash):
    """현재 포지션 확인"""
    logger.info(f"\n=== 계좌 포지션 확인 ===")

    try:
        # 계좌 정보 재조회
        accounts = await context['schwab_service'].get_accounts()
        account_info = accounts[0].get('securitiesAccount', {})

        # 현재 잔액 확인
        balances = account_info.get("currentBalances", {})
        available_funds = balances.get('availableFunds', 0)
        total_value = balances.get('liquidationValue', 0)

        logger.info(f"가용 자금: ${available_funds:,.2f}")
        logger.info(f"총 자산: ${total_value:,.2f}")

        # 포지션 확인 (실제로는 positions 배열 확인 필요)
        logger.info("개별 포지션 확인은 추가 API 호출이 필요합니다")

        return {
            'available_funds': available_funds,
            'total_value': total_value
        }

    except Exception as e:
        logger.error(f"❌ 포지션 확인 실패: {e}")
        return None


async def main():
    """메인 테스트 함수"""
    logger.info("=== 실제 소액 주문 테스트 시작 ===")
    logger.info(f"테스트 시간: {datetime.now()}")

    # 1. 안전 확인
    if not safety_check():
        return

    if not SAFETY_CONFIRMED:
        logger.error("❌ 안전 확인이 완료되지 않았습니다")
        return

    try:
        # 2. API 연결 및 인증
        logger.info("\n=== Schwab API 연결 ===")
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("❌ Schwab API 인증 실패")
            return

        logger.info("✅ Schwab API 인증 성공")

        # 3. 계좌 정보 확인
        accounts = await context['schwab_service'].get_accounts()
        account_hash = accounts[0].get('securitiesAccount', {}).get('accountNumber')

        logger.info(f"계좌번호: {account_hash}")

        # 4. TradingService 초기화
        trading_service = TradingService(context['schwab_service'])

        # 5. 현재가 조회 및 검증
        current_price = await get_current_price_and_validate(context, TEST_SYMBOL)
        if not current_price:
            logger.error("❌ 현재가 조회 실패로 테스트를 중단합니다")
            return

        # 6. 초기 포지션 확인
        initial_positions = await get_account_positions(context, account_hash)

        # 7. 실제 매수 주문 실행
        logger.info(f"\n*** EXECUTING REAL BUY ORDER! ***")
        logger.info(f"Estimated cost: ${current_price * MAX_QUANTITY:.2f}")

        final_confirm = input("Are you absolutely sure you want to execute? (YES to proceed): ").strip()
        if final_confirm != "YES":
            logger.info("Order cancelled by user")
            return

        buy_result = await place_market_buy_order(
            trading_service, account_hash, TEST_SYMBOL, MAX_QUANTITY
        )

        if not buy_result:
            logger.error("❌ 매수 주문 실패로 테스트를 중단합니다")
            return

        # 8. 주문 상태 모니터링
        order_id = buy_result.get('order_id')
        if order_id:
            await monitor_order_status(trading_service, account_hash, order_id)

        # 9. 포지션 확인
        await asyncio.sleep(5)  # 시스템 업데이트 대기
        updated_positions = await get_account_positions(context, account_hash)

        # 10. 매도 주문 실행 (포지션 정리)
        logger.info(f"\n*** EXECUTING SELL ORDER TO CLOSE POSITION! ***")

        sell_result = await place_market_sell_order(
            trading_service, account_hash, TEST_SYMBOL, MAX_QUANTITY
        )

        if sell_result:
            sell_order_id = sell_result.get('order_id')
            if sell_order_id:
                await monitor_order_status(trading_service, account_hash, sell_order_id)

        # 11. 최종 포지션 확인
        await asyncio.sleep(5)  # 시스템 업데이트 대기
        final_positions = await get_account_positions(context, account_hash)

        # 12. 결과 요약
        logger.info(f"\n=== 테스트 결과 요약 ===")
        logger.info(f"매수 주문: {'✅ 성공' if buy_result else '❌ 실패'}")
        logger.info(f"매도 주문: {'✅ 성공' if sell_result else '❌ 실패'}")

        if initial_positions and final_positions:
            value_change = final_positions['total_value'] - initial_positions['total_value']
            logger.info(f"자산 변화: ${value_change:+.2f}")

        logger.info("*** REAL ORDER TEST COMPLETED! ***")

    except Exception as e:
        logger.error(f"❌ 테스트 실행 중 치명적 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())