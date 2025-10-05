"""
완전한 라운드트립 거래 시스템

시장가로 매수 → 포지션 확인 → 매도 → 포지션 정리까지의 전체 사이클을 자동 실행합니다.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from autotrading.core.context import create_shared_context
from autotrading.api.trading_service import TradingService, OrderSide, TradingException
from autotrading.utils.market_hours import MarketHoursValidator

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 거래 설정
class RoundTripConfig:
    """라운드트립 거래 설정"""
    SYMBOL = "AAPL"
    QUANTITY = 1
    MAX_ORDER_VALUE = 500.0
    MIN_ACCOUNT_BALANCE = 1000.0

    # 체결 확인 설정
    ORDER_CHECK_INTERVAL = 3  # 초
    MAX_ORDER_WAIT_TIME = 60  # 최대 대기시간 (초)
    POSITION_CHECK_INTERVAL = 5  # 포지션 확인 간격 (초)
    MAX_POSITION_WAIT_TIME = 120  # 포지션 반영 최대 대기시간 (초)

class RoundTripTrader:
    """완전한 라운드트립 거래 실행기"""

    def __init__(self, config: RoundTripConfig):
        self.config = config
        self.market_validator = MarketHoursValidator()
        self.logger = logging.getLogger(f"{__name__}.RoundTripTrader")

        # 거래 상태 추적
        self.trade_state = {
            'buy_order_id': None,
            'buy_executed': False,
            'position_created': False,
            'sell_order_id': None,
            'sell_executed': False,
            'position_closed': False,
            'start_time': None,
            'end_time': None,
            'errors': []
        }

    async def validate_trading_conditions(self, context) -> bool:
        """거래 조건 검증"""
        self.logger.info("=== 거래 조건 검증 ===")

        # 1. 시장 시간 확인
        market_status = self.market_validator.get_market_status()
        self.logger.info(f"시장 상태: {market_status['message']}")

        if not market_status['is_market_open']:
            self.logger.error(f"❌ 시장이 닫혀있습니다: {market_status['message']}")
            return False

        # 2. 계좌 정보 확인
        accounts = await context['schwab_service'].get_accounts()
        account_info = accounts[0].get('securitiesAccount', {})
        balances = account_info.get('currentBalances', {})
        available_funds = balances.get('availableFunds', 0)

        if available_funds < self.config.MIN_ACCOUNT_BALANCE:
            self.logger.error(f"❌ 계좌 잔액 부족: ${available_funds} < ${self.config.MIN_ACCOUNT_BALANCE}")
            return False

        # 3. 현재가 확인
        quotes = await context['schwab_service'].get_quotes([self.config.SYMBOL])
        quote_data = quotes[self.config.SYMBOL]
        quote_info = quote_data.get('quote', {})
        current_price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)

        order_value = current_price * self.config.QUANTITY

        if order_value > self.config.MAX_ORDER_VALUE:
            self.logger.error(f"❌ 주문 금액 초과: ${order_value} > ${self.config.MAX_ORDER_VALUE}")
            return False

        if order_value > available_funds:
            self.logger.error(f"❌ 자금 부족: ${order_value} > ${available_funds}")
            return False

        self.logger.info("✅ 모든 거래 조건 충족")
        self.logger.info(f"현재가: ${current_price}, 주문 예상금액: ${order_value:.2f}")
        return True

    async def get_account_hash(self, context) -> str:
        """계좌 해시 획득"""
        schwab_client = context['schwab_service']._client
        account_numbers_response = schwab_client.get_account_numbers()
        account_numbers_data = account_numbers_response.json()
        return account_numbers_data[0]['hashValue']

    async def wait_for_order_execution(self, context, account_hash: str, order_id: str) -> Dict[str, Any]:
        """주문 체결 대기"""
        self.logger.info(f"주문 체결 대기: {order_id}")

        start_time = datetime.now()
        schwab_client = context['schwab_service']._client

        while True:
            try:
                # 주문 상태 확인 (올바른 파라미터 순서: order_id, account_hash)
                order_response = schwab_client.get_order(order_id, account_hash)
                order_data = order_response.json()

                status = order_data.get('status', 'UNKNOWN')
                self.logger.debug(f"주문 상태: {status}")

                if status == 'FILLED':
                    self.logger.info(f"✅ 주문 체결 완료: {order_id}")
                    return order_data
                elif status in ['REJECTED', 'CANCELLED', 'EXPIRED']:
                    status_desc = order_data.get('statusDescription', 'No description')
                    self.logger.error(f"❌ 주문 실패: {status} - {status_desc}")
                    return order_data

                # 대기시간 초과 확인
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.config.MAX_ORDER_WAIT_TIME:
                    self.logger.warning(f"⏰ 주문 대기시간 초과: {elapsed}초")
                    return order_data

                # 잠시 대기 후 재확인
                await asyncio.sleep(self.config.ORDER_CHECK_INTERVAL)

            except Exception as e:
                self.logger.warning(f"주문 상태 확인 실패: {e}")
                await asyncio.sleep(self.config.ORDER_CHECK_INTERVAL)

    async def wait_for_position_update(self, context, symbol: str, expected_quantity: int) -> bool:
        """포지션 업데이트 대기"""
        self.logger.info(f"포지션 업데이트 대기: {symbol} {expected_quantity}주")

        start_time = datetime.now()

        while True:
            try:
                # 계좌 정보 조회
                accounts = await context['schwab_service'].get_accounts()
                account_info = accounts[0].get('securitiesAccount', {})
                positions = account_info.get('positions', [])

                # 해당 종목 포지션 찾기
                for position in positions:
                    instrument = position.get('instrument', {})
                    position_symbol = instrument.get('symbol', '')

                    if position_symbol == symbol:
                        long_qty = position.get('longQuantity', 0)
                        short_qty = position.get('shortQuantity', 0)
                        net_qty = long_qty - short_qty

                        self.logger.debug(f"포지션 확인: {symbol} {net_qty}주 (목표: {expected_quantity}주)")

                        if net_qty == expected_quantity:
                            self.logger.info(f"✅ 포지션 업데이트 완료: {symbol} {net_qty}주")
                            return True

                # 대기시간 초과 확인
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.config.MAX_POSITION_WAIT_TIME:
                    self.logger.warning(f"⏰ 포지션 대기시간 초과: {elapsed}초")
                    return False

                # 잠시 대기 후 재확인
                await asyncio.sleep(self.config.POSITION_CHECK_INTERVAL)

            except Exception as e:
                self.logger.warning(f"포지션 확인 실패: {e}")
                await asyncio.sleep(self.config.POSITION_CHECK_INTERVAL)

    async def execute_buy_order(self, context, trading_service, account_hash: str) -> bool:
        """매수 주문 실행"""
        self.logger.info("=== 매수 주문 실행 ===")

        try:
            # 매수 주문 실행
            result = await context['schwab_service'].place_order(account_hash, {
                "orderType": "MARKET",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [{
                    "instruction": "BUY",
                    "quantity": self.config.QUANTITY,
                    "instrument": {
                        "symbol": self.config.SYMBOL,
                        "assetType": "EQUITY"
                    }
                }]
            })

            if result.get('status') == 'success':
                order_id = result.get('order_id')
                self.trade_state['buy_order_id'] = order_id
                self.logger.info(f"✅ 매수 주문 접수: {order_id}")

                # 체결 대기
                order_data = await self.wait_for_order_execution(context, account_hash, order_id)

                if order_data.get('status') == 'FILLED':
                    self.trade_state['buy_executed'] = True
                    self.logger.info("✅ 매수 주문 체결 완료")

                    # 포지션 생성 대기
                    position_created = await self.wait_for_position_update(context, self.config.SYMBOL, self.config.QUANTITY)
                    self.trade_state['position_created'] = position_created

                    return position_created
                else:
                    self.logger.error(f"❌ 매수 주문 실패: {order_data.get('status')}")
                    return False
            else:
                self.logger.error(f"❌ 매수 주문 접수 실패: {result}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 매수 주문 실행 실패: {e}")
            self.trade_state['errors'].append(f"Buy order error: {e}")
            return False

    async def execute_sell_order(self, context, trading_service, account_hash: str) -> bool:
        """매도 주문 실행"""
        self.logger.info("=== 매도 주문 실행 ===")

        try:
            # 매도 주문 실행
            result = await context['schwab_service'].place_order(account_hash, {
                "orderType": "MARKET",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [{
                    "instruction": "SELL",
                    "quantity": self.config.QUANTITY,
                    "instrument": {
                        "symbol": self.config.SYMBOL,
                        "assetType": "EQUITY"
                    }
                }]
            })

            if result.get('status') == 'success':
                order_id = result.get('order_id')
                self.trade_state['sell_order_id'] = order_id
                self.logger.info(f"✅ 매도 주문 접수: {order_id}")

                # 체결 대기
                order_data = await self.wait_for_order_execution(context, account_hash, order_id)

                if order_data.get('status') == 'FILLED':
                    self.trade_state['sell_executed'] = True
                    self.logger.info("✅ 매도 주문 체결 완료")

                    # 포지션 정리 대기
                    position_closed = await self.wait_for_position_update(context, self.config.SYMBOL, 0)
                    self.trade_state['position_closed'] = position_closed

                    return position_closed
                else:
                    self.logger.error(f"❌ 매도 주문 실패: {order_data.get('status')}")
                    return False
            else:
                self.logger.error(f"❌ 매도 주문 접수 실패: {result}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 매도 주문 실행 실패: {e}")
            self.trade_state['errors'].append(f"Sell order error: {e}")
            return False

    async def execute_round_trip_trade(self, context) -> Dict[str, Any]:
        """완전한 라운드트립 거래 실행"""
        self.logger.info("🚀 === 완전한 라운드트립 거래 시작 ===")
        self.trade_state['start_time'] = datetime.now()

        try:
            # 1. 거래 조건 검증
            if not await self.validate_trading_conditions(context):
                return self.get_trade_result(False, "거래 조건 미충족")

            # 2. 계좌 해시 획득
            account_hash = await self.get_account_hash(context)
            trading_service = TradingService(context['schwab_service'])

            # 3. 매수 주문 실행
            if not await self.execute_buy_order(context, trading_service, account_hash):
                return self.get_trade_result(False, "매수 주문 실패")

            self.logger.info("💰 매수 단계 완료, 매도 단계 시작")

            # 4. 매도 주문 실행
            if not await self.execute_sell_order(context, trading_service, account_hash):
                return self.get_trade_result(False, "매도 주문 실패")

            # 5. 성공적 완료
            return self.get_trade_result(True, "라운드트립 거래 성공")

        except Exception as e:
            self.logger.error(f"❌ 라운드트립 거래 실패: {e}")
            self.trade_state['errors'].append(f"Round trip error: {e}")
            return self.get_trade_result(False, f"시스템 오류: {e}")

        finally:
            self.trade_state['end_time'] = datetime.now()

    def get_trade_result(self, success: bool, message: str) -> Dict[str, Any]:
        """거래 결과 생성"""
        # end_time이 설정되지 않았으면 현재 시간으로 설정
        if not self.trade_state.get('end_time'):
            self.trade_state['end_time'] = datetime.now()

        duration = None
        if self.trade_state.get('start_time') and self.trade_state.get('end_time'):
            duration = (self.trade_state['end_time'] - self.trade_state['start_time']).total_seconds()

        return {
            'success': success,
            'message': message,
            'symbol': self.config.SYMBOL,
            'quantity': self.config.QUANTITY,
            'trade_state': self.trade_state.copy(),
            'duration_seconds': duration or 0,  # None 대신 0 사용
            'timestamp': datetime.now().isoformat()
        }


async def main():
    """메인 실행 함수"""
    logger.info("=== 완전한 라운드트립 거래 시스템 ===")

    try:
        # 설정 초기화
        config = RoundTripConfig()
        trader = RoundTripTrader(config)

        logger.info(f"거래 설정:")
        logger.info(f"  종목: {config.SYMBOL}")
        logger.info(f"  수량: {config.QUANTITY}주")
        logger.info(f"  최대 주문금액: ${config.MAX_ORDER_VALUE}")

        # API 연결
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("❌ Schwab API 인증 실패")
            return

        # 라운드트립 거래 실행
        result = await trader.execute_round_trip_trade(context)

        # 결과 출력
        logger.info("\n" + "="*60)
        logger.info("라운드트립 거래 결과")
        logger.info("="*60)

        logger.info(f"성공 여부: {result['success']}")
        logger.info(f"메시지: {result['message']}")
        logger.info(f"거래 시간: {result.get('duration_seconds', 0):.1f}초")

        trade_state = result['trade_state']
        logger.info(f"\n거래 상태:")
        logger.info(f"  매수 주문 ID: {trade_state['buy_order_id']}")
        logger.info(f"  매수 체결: {trade_state['buy_executed']}")
        logger.info(f"  포지션 생성: {trade_state['position_created']}")
        logger.info(f"  매도 주문 ID: {trade_state['sell_order_id']}")
        logger.info(f"  매도 체결: {trade_state['sell_executed']}")
        logger.info(f"  포지션 정리: {trade_state['position_closed']}")

        if trade_state['errors']:
            logger.error(f"\n오류 목록:")
            for error in trade_state['errors']:
                logger.error(f"  - {error}")

        if result['success']:
            logger.info("🎉 라운드트립 거래 완전 성공!")
        else:
            logger.warning("⚠️ 라운드트립 거래 부분 실패")

    except Exception as e:
        logger.error(f"❌ 시스템 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())