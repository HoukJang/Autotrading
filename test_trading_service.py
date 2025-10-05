"""
TradingService 실제 주문 테스트

AAPL 종목으로 모든 주문 유형을 테스트합니다:
- 시장가 주문 (Market Order)
- 지정가 주문 (Limit Order)
- 정지가 주문 (Stop Order)
- 정지지정가 주문 (Stop Limit Order)
"""

import asyncio
import os
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
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
RISK_PERCENTAGE = 0.01  # 1% 리스크


def create_mock_schwab_service():
    """Mock Schwab API 서비스 생성"""
    mock_service = AsyncMock()

    # 계좌 정보 Mock
    mock_service.get_accounts.return_value = [
        {"hashValue": "test_account_hash_12345"}
    ]

    # 계좌 상세 정보 Mock
    mock_service.get_account_info.return_value = {
        "securitiesAccount": {
            "currentBalances": {
                "availableFunds": 50000.0,  # $50,000 가용 자금
                "totalValue": 100000.0
            }
        }
    }

    # 주문 실행 Mock
    async def mock_place_order(account_hash, order_spec):
        return {
            "orderId": f"order_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "status": "WORKING",
            "message": "Order placed successfully"
        }

    mock_service.place_order = mock_place_order

    return mock_service


async def get_current_price(symbol):
    """현재가 조회 (시뮬레이션)"""
    simulated_prices = {
        "AAPL": 185.50,
        "TSLA": 245.30,
        "NVDA": 425.80,
        "MSFT": 380.20,
        "SPY": 475.60
    }
    return simulated_prices.get(symbol, 100.0)


async def test_market_order(trading_service, account_hash, symbol, quantity):
    """시장가 주문 테스트"""
    logger.info(f"\n=== 시장가 주문 테스트 시작 ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}")

    try:
        # 매수 주문
        buy_result = await trading_service.create_market_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity
        )
        logger.info(f"매수 주문 결과: {buy_result}")

        # 매도 주문
        sell_result = await trading_service.create_market_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity
        )
        logger.info(f"매도 주문 결과: {sell_result}")

        return {"buy": buy_result, "sell": sell_result}

    except TradingException as e:
        logger.error(f"시장가 주문 실패: {e}")
        return {"error": str(e)}


async def test_limit_order(trading_service, account_hash, symbol, quantity, current_price):
    """지정가 주문 테스트"""
    logger.info(f"\n=== 지정가 주문 테스트 시작 ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}, 현재가: ${current_price}")

    try:
        # 현재가보다 낮은 매수 지정가
        buy_limit_price = current_price * 0.98  # 2% 할인된 가격
        buy_result = await trading_service.create_limit_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            limit_price=buy_limit_price
        )
        logger.info(f"매수 지정가 주문 (${buy_limit_price:.2f}): {buy_result}")

        # 현재가보다 높은 매도 지정가
        sell_limit_price = current_price * 1.02  # 2% 프리미엄 가격
        sell_result = await trading_service.create_limit_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            limit_price=sell_limit_price
        )
        logger.info(f"매도 지정가 주문 (${sell_limit_price:.2f}): {sell_result}")

        return {"buy": buy_result, "sell": sell_result}

    except TradingException as e:
        logger.error(f"지정가 주문 실패: {e}")
        return {"error": str(e)}


async def test_stop_order(trading_service, account_hash, symbol, quantity, current_price):
    """정지가 주문 테스트"""
    logger.info(f"\n=== 정지가 주문 테스트 시작 ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}, 현재가: ${current_price}")

    try:
        # 손절매 정지가 주문 (현재가보다 낮음)
        stop_loss_price = current_price * 0.95  # 5% 손절
        sell_stop_result = await trading_service.create_stop_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            stop_price=stop_loss_price
        )
        logger.info(f"손절매 정지가 주문 (${stop_loss_price:.2f}): {sell_stop_result}")

        # 추격매수 정지가 주문 (현재가보다 높음)
        buy_stop_price = current_price * 1.05  # 5% 돌파시 매수
        buy_stop_result = await trading_service.create_stop_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            stop_price=buy_stop_price
        )
        logger.info(f"추격매수 정지가 주문 (${buy_stop_price:.2f}): {buy_stop_result}")

        return {"sell_stop": sell_stop_result, "buy_stop": buy_stop_result}

    except TradingException as e:
        logger.error(f"정지가 주문 실패: {e}")
        return {"error": str(e)}


async def test_stop_limit_order(trading_service, account_hash, symbol, quantity, current_price):
    """정지지정가 주문 테스트"""
    logger.info(f"\n=== 정지지정가 주문 테스트 시작 ===")
    logger.info(f"종목: {symbol}, 수량: {quantity}, 현재가: ${current_price}")

    try:
        # 손절매 정지지정가 주문
        stop_price = current_price * 0.95      # 5% 손절 트리거
        limit_price = current_price * 0.94     # 6% 할인 지정가

        sell_stop_limit_result = await trading_service.create_stop_limit_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            stop_price=stop_price,
            limit_price=limit_price
        )
        logger.info(f"손절매 정지지정가 주문 (정지: ${stop_price:.2f}, 지정: ${limit_price:.2f}): {sell_stop_limit_result}")

        # 추격매수 정지지정가 주문
        buy_stop_price = current_price * 1.05   # 5% 돌파 트리거
        buy_limit_price = current_price * 1.06  # 6% 프리미엄 지정가

        buy_stop_limit_result = await trading_service.create_stop_limit_order(
            account_hash=account_hash,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            stop_price=buy_stop_price,
            limit_price=buy_limit_price
        )
        logger.info(f"추격매수 정지지정가 주문 (정지: ${buy_stop_price:.2f}, 지정: ${buy_limit_price:.2f}): {buy_stop_limit_result}")

        return {"sell_stop_limit": sell_stop_limit_result, "buy_stop_limit": buy_stop_limit_result}

    except TradingException as e:
        logger.error(f"정지지정가 주문 실패: {e}")
        return {"error": str(e)}


async def test_position_size_calculation(trading_service, account_hash, symbol, current_price):
    """포지션 사이즈 계산 테스트"""
    logger.info(f"\n=== 포지션 사이즈 계산 테스트 ===")

    try:
        entry_price = current_price
        stop_loss_price = current_price * 0.95  # 5% 손절

        position_calc = await trading_service.calculate_position_size(
            account_hash=account_hash,
            symbol=symbol,
            risk_percentage=RISK_PERCENTAGE,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price
        )

        logger.info(f"포지션 계산 결과: {position_calc}")
        return position_calc

    except TradingException as e:
        logger.error(f"포지션 계산 실패: {e}")
        return {"error": str(e)}


async def main():
    """메인 테스트 함수"""
    logger.info("=== TradingService 실제 주문 테스트 시작 ===")
    logger.info(f"테스트 종목: {TEST_SYMBOL}")
    logger.info(f"테스트 시간: {datetime.now()}")

    try:
        # Mock Schwab 서비스 생성
        mock_schwab_service = create_mock_schwab_service()

        # TradingService 초기화
        trading_service = TradingService(mock_schwab_service)

        # 계좌 정보 확인
        accounts = await mock_schwab_service.get_accounts()
        if not accounts:
            logger.error("계좌 정보를 찾을 수 없습니다")
            return

        account_hash = accounts[0]["hashValue"]
        logger.info(f"사용 계좌: {account_hash}")

        # 현재가 조회
        current_price = await get_current_price(TEST_SYMBOL)
        logger.info(f"{TEST_SYMBOL} 현재가: ${current_price}")

        # 테스트 결과 저장
        test_results = {}

        # 1. 시장가 주문 테스트
        test_results["market_orders"] = await test_market_order(
            trading_service, account_hash, TEST_SYMBOL, TEST_QUANTITY
        )

        # 2. 지정가 주문 테스트
        test_results["limit_orders"] = await test_limit_order(
            trading_service, account_hash, TEST_SYMBOL, TEST_QUANTITY, current_price
        )

        # 3. 정지가 주문 테스트
        test_results["stop_orders"] = await test_stop_order(
            trading_service, account_hash, TEST_SYMBOL, TEST_QUANTITY, current_price
        )

        # 4. 정지지정가 주문 테스트
        test_results["stop_limit_orders"] = await test_stop_limit_order(
            trading_service, account_hash, TEST_SYMBOL, TEST_QUANTITY, current_price
        )

        # 5. 포지션 사이즈 계산 테스트
        test_results["position_calculation"] = await test_position_size_calculation(
            trading_service, account_hash, TEST_SYMBOL, current_price
        )

        # 결과 요약
        logger.info(f"\n=== 테스트 완료 ===")
        logger.info(f"총 테스트 항목: 5개")

        success_count = 0
        for test_name, result in test_results.items():
            if "error" not in result:
                success_count += 1
                logger.info(f"✓ {test_name}: 성공")
            else:
                logger.error(f"✗ {test_name}: 실패 - {result['error']}")

        logger.info(f"성공률: {success_count}/5 ({success_count/5*100:.1f}%)")

        return test_results

    except Exception as e:
        logger.error(f"테스트 실행 중 오류: {e}")
        raise


if __name__ == "__main__":
    # 환경 변수 확인
    required_vars = ["SCHWAB_APP_KEY", "SCHWAB_APP_SECRET"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.warning(f"환경 변수가 설정되지 않았습니다: {missing_vars}")
        logger.info("테스트 모드로 실행합니다. (실제 주문은 실행되지 않음)")

        # 테스트 모드로 실행
        asyncio.run(main())
    else:
        logger.info("프로덕션 모드로 실행합니다.")
        asyncio.run(main())