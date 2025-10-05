"""
완전 자동화 거래 시스템 테스트

수동 승인 없이 완전 자동으로 주문을 실행하는 시스템입니다.
프로그래밍적 안전 장치만으로 보호됩니다.
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

# 자동화 거래 설정
class AutoTradingConfig:
    """자동화 거래 설정"""

    # 기본 설정
    SYMBOL = "AAPL"
    QUANTITY = 1

    # 안전 장치
    MAX_ORDER_VALUE = 500.0      # 최대 주문 금액
    MAX_DAILY_TRADES = 10        # 일일 최대 거래 횟수
    MIN_ACCOUNT_BALANCE = 1000.0 # 최소 계좌 잔액

    # 가격 검증
    MIN_PRICE = 50.0            # 최소 주문 가격
    MAX_PRICE = 1000.0          # 최대 주문 가격
    MAX_SPREAD_PERCENT = 2.0    # 최대 스프레드 (%)

    # 시장 검증
    MIN_VOLUME = 100000         # 최소 일일 거래량

    # 실행 모드
    ENABLE_REAL_TRADING = True   # 실제 주문 실행 활성화


class AutomatedSafetyValidator:
    """자동화 안전 검증기"""

    def __init__(self, config: AutoTradingConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.SafetyValidator")

    def validate_price(self, price: float, bid: float, ask: float) -> bool:
        """가격 유효성 검증"""
        if not (self.config.MIN_PRICE <= price <= self.config.MAX_PRICE):
            self.logger.error(f"Price {price} outside allowed range [{self.config.MIN_PRICE}, {self.config.MAX_PRICE}]")
            return False

        if bid <= 0 or ask <= 0:
            self.logger.error(f"Invalid bid/ask: {bid}/{ask}")
            return False

        spread_percent = ((ask - bid) / price) * 100
        if spread_percent > self.config.MAX_SPREAD_PERCENT:
            self.logger.error(f"Spread too wide: {spread_percent:.2f}% > {self.config.MAX_SPREAD_PERCENT}%")
            return False

        return True

    def validate_account(self, available_funds: float, order_value: float) -> bool:
        """계좌 안전성 검증"""
        if available_funds < self.config.MIN_ACCOUNT_BALANCE:
            self.logger.error(f"Account balance {available_funds} below minimum {self.config.MIN_ACCOUNT_BALANCE}")
            return False

        if order_value > self.config.MAX_ORDER_VALUE:
            self.logger.error(f"Order value {order_value} exceeds maximum {self.config.MAX_ORDER_VALUE}")
            return False

        if order_value > available_funds:
            self.logger.error(f"Insufficient funds: {order_value} > {available_funds}")
            return False

        # 주문 후에도 최소 잔액 유지
        remaining_balance = available_funds - order_value
        if remaining_balance < self.config.MIN_ACCOUNT_BALANCE:
            self.logger.error(f"Order would leave insufficient balance: {remaining_balance}")
            return False

        return True

    def validate_market(self, volume: int) -> bool:
        """시장 유동성 검증"""
        if volume < self.config.MIN_VOLUME:
            self.logger.error(f"Volume {volume} below minimum {self.config.MIN_VOLUME}")
            return False

        return True

    def validate_trading_session(self) -> bool:
        """거래 시간 검증 (간단한 버전)"""
        current_hour = datetime.now().hour

        # 미국 시장 시간 대략적 확인 (9:30 AM - 4:00 PM EST)
        # 여기서는 간단하게 비즈니스 시간만 확인
        if not (9 <= current_hour <= 16):
            self.logger.warning(f"Trading outside normal hours: {current_hour}")
            # 경고만 하고 차단하지는 않음 (프리마켓/애프터마켓 거래 가능)

        return True


class AutomatedTrader:
    """완전 자동화 거래 실행기"""

    def __init__(self, config: AutoTradingConfig):
        self.config = config
        self.safety_validator = AutomatedSafetyValidator(config)
        self.logger = logging.getLogger(f"{__name__}.AutomatedTrader")

        # 거래 통계
        self.trade_count = 0
        self.total_volume = 0.0

    async def execute_automated_buy_order(self, context, trading_service, account_hash) -> dict:
        """완전 자동 매수 주문 실행"""
        self.logger.info(f"=== AUTOMATED BUY ORDER EXECUTION ===")

        try:
            # 1. 시장 데이터 조회
            quotes = await context['schwab_service'].get_quotes([self.config.SYMBOL])

            if self.config.SYMBOL not in quotes:
                raise Exception(f"No market data for {self.config.SYMBOL}")

            quote_data = quotes[self.config.SYMBOL]
            quote_info = quote_data.get('quote', {})

            price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)
            bid = quote_info.get('bidPrice', 0)
            ask = quote_info.get('askPrice', 0)
            volume = quote_info.get('totalVolume', 0)

            self.logger.info(f"Market data: Price=${price}, Bid=${bid}, Ask=${ask}, Volume={volume:,}")

            # 2. 계좌 정보 조회
            accounts = await context['schwab_service'].get_accounts()
            account_info = accounts[0].get('securitiesAccount', {})
            balances = account_info.get('currentBalances', {})
            available_funds = balances.get('availableFunds', 0)

            self.logger.info(f"Account: Available=${available_funds:,.2f}")

            # 3. 주문 가치 계산
            order_value = price * self.config.QUANTITY

            # 4. 자동 안전 검증
            if not self.safety_validator.validate_price(price, bid, ask):
                raise Exception("Price validation failed")

            if not self.safety_validator.validate_account(available_funds, order_value):
                raise Exception("Account validation failed")

            if not self.safety_validator.validate_market(volume):
                raise Exception("Market validation failed")

            if not self.safety_validator.validate_trading_session():
                raise Exception("Trading session validation failed")

            self.logger.info("✅ All automated safety checks passed")

            # 5. 주문 실행 결정
            if not self.config.ENABLE_REAL_TRADING:
                self.logger.info("🔒 SIMULATION MODE - Order would be executed")
                return {
                    'status': 'simulated',
                    'symbol': self.config.SYMBOL,
                    'quantity': self.config.QUANTITY,
                    'price': price,
                    'order_value': order_value,
                    'timestamp': datetime.now(),
                    'order_id': f'SIM_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                }

            # 6. 실제 주문 실행
            self.logger.info(f"🚀 EXECUTING REAL BUY ORDER")
            self.logger.info(f"Order: {self.config.SYMBOL} {self.config.QUANTITY} shares @ market")
            self.logger.info(f"Estimated cost: ${order_value:.2f}")

            result = await trading_service.create_market_order(
                account_hash=account_hash,
                symbol=self.config.SYMBOL,
                side=OrderSide.BUY,
                quantity=self.config.QUANTITY
            )

            # 7. 거래 통계 업데이트
            self.trade_count += 1
            self.total_volume += order_value

            self.logger.info(f"✅ BUY ORDER EXECUTED")
            self.logger.info(f"Order ID: {result.get('order_id', 'unknown')}")

            return result

        except Exception as e:
            self.logger.error(f"❌ Automated buy order failed: {e}")
            raise

    async def execute_automated_sell_order(self, context, trading_service, account_hash) -> dict:
        """완전 자동 매도 주문 실행"""
        self.logger.info(f"=== AUTOMATED SELL ORDER EXECUTION ===")

        try:
            # 현재가 재확인
            quotes = await context['schwab_service'].get_quotes([self.config.SYMBOL])
            quote_data = quotes[self.config.SYMBOL]
            quote_info = quote_data.get('quote', {})
            price = quote_info.get('lastPrice', 0) or quote_info.get('mark', 0)

            order_value = price * self.config.QUANTITY

            if not self.config.ENABLE_REAL_TRADING:
                self.logger.info("🔒 SIMULATION MODE - Sell order would be executed")
                return {
                    'status': 'simulated',
                    'symbol': self.config.SYMBOL,
                    'quantity': self.config.QUANTITY,
                    'price': price,
                    'order_value': order_value,
                    'timestamp': datetime.now(),
                    'order_id': f'SIM_SELL_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                }

            self.logger.info(f"🚀 EXECUTING REAL SELL ORDER")
            self.logger.info(f"Order: {self.config.SYMBOL} {self.config.QUANTITY} shares @ market")

            result = await trading_service.create_market_order(
                account_hash=account_hash,
                symbol=self.config.SYMBOL,
                side=OrderSide.SELL,
                quantity=self.config.QUANTITY
            )

            self.logger.info(f"✅ SELL ORDER EXECUTED")
            self.logger.info(f"Order ID: {result.get('order_id', 'unknown')}")

            return result

        except Exception as e:
            self.logger.error(f"❌ Automated sell order failed: {e}")
            raise

    async def execute_round_trip_trade(self, context, trading_service, account_hash) -> dict:
        """완전 자동 왕복 거래 (매수 → 매도)"""
        self.logger.info("=== AUTOMATED ROUND TRIP TRADE ===")

        trade_results = {
            'start_time': datetime.now(),
            'buy_order': None,
            'sell_order': None,
            'success': False,
            'error': None
        }

        try:
            # 1. 자동 매수
            trade_results['buy_order'] = await self.execute_automated_buy_order(
                context, trading_service, account_hash
            )

            # 2. 잠깐 대기 (실제 환경에서는 체결 확인 필요)
            await asyncio.sleep(2)

            # 3. 자동 매도 (포지션 정리)
            trade_results['sell_order'] = await self.execute_automated_sell_order(
                context, trading_service, account_hash
            )

            trade_results['success'] = True
            trade_results['end_time'] = datetime.now()

            self.logger.info("✅ AUTOMATED ROUND TRIP TRADE COMPLETED")

            return trade_results

        except Exception as e:
            trade_results['error'] = str(e)
            trade_results['end_time'] = datetime.now()
            self.logger.error(f"❌ Automated round trip trade failed: {e}")
            return trade_results


async def main():
    """자동화 거래 시스템 메인 함수"""
    logger.info("=== AUTOMATED TRADING SYSTEM TEST ===")
    logger.info(f"Test time: {datetime.now()}")

    # 설정 초기화
    config = AutoTradingConfig()

    logger.info(f"Configuration:")
    logger.info(f"  Symbol: {config.SYMBOL}")
    logger.info(f"  Quantity: {config.QUANTITY}")
    logger.info(f"  Max order value: ${config.MAX_ORDER_VALUE}")
    logger.info(f"  Real trading enabled: {config.ENABLE_REAL_TRADING}")

    if not config.ENABLE_REAL_TRADING:
        logger.info("🔒 SIMULATION MODE - No real orders will be executed")
    else:
        logger.info("🚀 REAL TRADING MODE - Orders will be executed!")

    try:
        # API 연결
        context = await create_shared_context()

        if not context['schwab_service'].is_authenticated():
            logger.error("❌ Schwab API authentication failed")
            return

        # 계좌 정보
        accounts = await context['schwab_service'].get_accounts()
        account_hash = accounts[0].get('securitiesAccount', {}).get('accountNumber')

        # TradingService 초기화
        trading_service = TradingService(context['schwab_service'])

        # 자동 거래 실행기 초기화
        trader = AutomatedTrader(config)

        # 완전 자동 왕복 거래 실행
        result = await trader.execute_round_trip_trade(context, trading_service, account_hash)

        # 결과 요약
        logger.info("\n" + "="*60)
        logger.info("AUTOMATED TRADING RESULT SUMMARY")
        logger.info("="*60)

        logger.info(f"Success: {result['success']}")
        logger.info(f"Start time: {result['start_time']}")
        logger.info(f"End time: {result.get('end_time', 'N/A')}")

        if result['buy_order']:
            buy_order = result['buy_order']
            logger.info(f"Buy order: {buy_order.get('status', 'unknown')} - ID: {buy_order.get('order_id', 'N/A')}")

        if result['sell_order']:
            sell_order = result['sell_order']
            logger.info(f"Sell order: {sell_order.get('status', 'unknown')} - ID: {sell_order.get('order_id', 'N/A')}")

        if result['error']:
            logger.error(f"Error: {result['error']}")

        if result['success']:
            logger.info("🎉 AUTOMATED TRADING SYSTEM WORKING PERFECTLY!")
        else:
            logger.warning("⚠️ Automated trading encountered issues")

        # 거래 통계
        logger.info(f"\nTrading statistics:")
        logger.info(f"  Total trades executed: {trader.trade_count}")
        logger.info(f"  Total volume: ${trader.total_volume:.2f}")

    except Exception as e:
        logger.error(f"❌ Fatal error in automated trading system: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 자동화 거래 시스템 실행
    asyncio.run(main())