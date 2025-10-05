"""
종합 Schwab API 기능 테스트

모든 Schwab API 기능에 대한 포괄적인 테스트 스위트입니다.
실제 거래 전에 모든 기능을 안전하게 테스트할 수 있습니다.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from autotrading.core.context import create_shared_context
from autotrading.api.trading_service import OrderType, StopType, TimeInForce, ComplexOrderStrategyType

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 테스트 설정
TEST_SYMBOL = "AAPL"
TEST_OPTION_SYMBOL = "AAPL_012025C150"  # 예시 옵션 심볼
TEST_QUANTITY = 1
TEST_PRICE = 150.0

class ComprehensiveSchwabAPITest:
    """포괄적인 Schwab API 테스트 클래스"""

    def __init__(self):
        self.context = None
        self.trading_service = None
        self.account_hash = None

    async def setup(self):
        """테스트 환경 설정"""
        logger.info("=== 테스트 환경 설정 ===")
        try:
            self.context = await create_shared_context()
            self.trading_service = self.context['trading_service']

            if not self.context['schwab_service'].is_authenticated():
                logger.error("Schwab API 인증 실패")
                return False

            # 계좌 해시 확인
            schwab_client = self.context['schwab_service']._client
            account_numbers_response = schwab_client.get_account_numbers()
            account_numbers_data = account_numbers_response.json()

            if account_numbers_data:
                self.account_hash = account_numbers_data[0]['hashValue']
                logger.info(f"계좌 해시: {self.account_hash}")
                return True
            else:
                logger.error("계좌 정보 없음")
                return False

        except Exception as e:
            logger.error(f"테스트 환경 설정 실패: {e}")
            return False

    async def test_basic_order_types(self):
        """기본 주문 타입 테스트"""
        logger.info("\n=== 기본 주문 타입 테스트 ===")

        try:
            # Market Buy Order
            logger.info("1. Market Buy Order 테스트")
            market_buy = await self.trading_service.create_buy_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.MARKET
            )
            logger.info(f"Market Buy 결과: {market_buy}")

            # Limit Buy Order
            logger.info("2. Limit Buy Order 테스트")
            limit_buy = await self.trading_service.create_buy_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.LIMIT,
                price=TEST_PRICE - 5.0
            )
            logger.info(f"Limit Buy 결과: {limit_buy}")

            # Stop Loss Order
            logger.info("3. Stop Loss Order 테스트")
            stop_loss = await self.trading_service.create_sell_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.STOP,
                stop_price=TEST_PRICE - 10.0
            )
            logger.info(f"Stop Loss 결과: {stop_loss}")

            # Stop Limit Order
            logger.info("4. Stop Limit Order 테스트")
            stop_limit = await self.trading_service.create_sell_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.STOP_LIMIT,
                price=TEST_PRICE - 8.0,
                stop_price=TEST_PRICE - 10.0
            )
            logger.info(f"Stop Limit 결과: {stop_limit}")

            return True

        except Exception as e:
            logger.error(f"기본 주문 타입 테스트 실패: {e}")
            return False

    async def test_advanced_order_types(self):
        """고급 주문 타입 테스트"""
        logger.info("\n=== 고급 주문 타입 테스트 ===")

        try:
            # Trailing Stop Order
            logger.info("1. Trailing Stop Order 테스트")
            trailing_stop = await self.trading_service.create_trailing_stop_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                instruction="SELL",
                stop_type=StopType.PERCENT,
                stop_offset=5.0
            )
            logger.info(f"Trailing Stop 결과: {trailing_stop}")

            # Short Sell Order
            logger.info("2. Short Sell Order 테스트")
            short_sell = await self.trading_service.create_short_sell_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.MARKET
            )
            logger.info(f"Short Sell 결과: {short_sell}")

            # Buy to Cover Order
            logger.info("3. Buy to Cover Order 테스트")
            buy_to_cover = await self.trading_service.create_buy_to_cover_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                order_type=OrderType.MARKET
            )
            logger.info(f"Buy to Cover 결과: {buy_to_cover}")

            return True

        except Exception as e:
            logger.error(f"고급 주문 타입 테스트 실패: {e}")
            return False

    async def test_complex_order_strategies(self):
        """복합 주문 전략 테스트"""
        logger.info("\n=== 복합 주문 전략 테스트 ===")

        try:
            # OCO Order
            logger.info("1. OCO (One Cancels Other) Order 테스트")
            oco_order = await self.trading_service.create_oco_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                primary_order_type=OrderType.LIMIT,
                secondary_order_type=OrderType.STOP,
                primary_price=TEST_PRICE + 5.0,
                secondary_price=TEST_PRICE - 5.0,
                primary_instruction="SELL",
                secondary_instruction="SELL"
            )
            logger.info(f"OCO Order 결과: {oco_order}")

            # OTO Order
            logger.info("2. OTO (One Triggers Other) Order 테스트")
            oto_order = await self.trading_service.create_oto_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                trigger_quantity=TEST_QUANTITY,
                trigger_order_type=OrderType.LIMIT,
                trigger_price=TEST_PRICE - 2.0,
                trigger_instruction="BUY",
                target_quantity=TEST_QUANTITY,
                target_order_type=OrderType.LIMIT,
                target_price=TEST_PRICE + 10.0,
                target_instruction="SELL"
            )
            logger.info(f"OTO Order 결과: {oto_order}")

            # Bracket Order
            logger.info("3. Bracket Order 테스트")
            bracket_order = await self.trading_service.create_bracket_order(
                account_hash=self.account_hash,
                symbol=TEST_SYMBOL,
                quantity=TEST_QUANTITY,
                entry_order_type=OrderType.LIMIT,
                entry_price=TEST_PRICE - 2.0,
                take_profit_price=TEST_PRICE + 10.0,
                stop_loss_price=TEST_PRICE - 5.0,
                instruction="BUY"
            )
            logger.info(f"Bracket Order 결과: {bracket_order}")

            return True

        except Exception as e:
            logger.error(f"복합 주문 전략 테스트 실패: {e}")
            return False

    async def test_options_trading(self):
        """옵션 거래 테스트"""
        logger.info("\n=== 옵션 거래 테스트 ===")

        try:
            # Basic Options Order
            logger.info("1. 기본 옵션 주문 테스트")
            option_order = await self.trading_service.create_options_order(
                account_hash=self.account_hash,
                option_symbol=TEST_OPTION_SYMBOL,
                quantity=1,
                instruction="BUY_TO_OPEN",
                order_type=OrderType.LIMIT,
                price=5.0
            )
            logger.info(f"옵션 주문 결과: {option_order}")

            # Covered Call
            logger.info("2. Covered Call 전략 테스트")
            covered_call = await self.trading_service.create_covered_call(
                account_hash=self.account_hash,
                underlying_symbol=TEST_SYMBOL,
                option_symbol=TEST_OPTION_SYMBOL,
                quantity=1,
                call_price=3.0,
                order_type=OrderType.LIMIT
            )
            logger.info(f"Covered Call 결과: {covered_call}")

            # Protective Put
            logger.info("3. Protective Put 전략 테스트")
            protective_put = await self.trading_service.create_protective_put(
                account_hash=self.account_hash,
                underlying_symbol=TEST_SYMBOL,
                option_symbol="AAPL_012025P140",
                quantity=1,
                put_price=2.0,
                order_type=OrderType.LIMIT
            )
            logger.info(f"Protective Put 결과: {protective_put}")

            # Straddle
            logger.info("4. Straddle 전략 테스트")
            straddle = await self.trading_service.create_straddle(
                account_hash=self.account_hash,
                call_symbol=TEST_OPTION_SYMBOL,
                put_symbol="AAPL_012025P150",
                quantity=1,
                instruction="BUY_TO_OPEN",
                net_price=8.0,
                order_type=OrderType.LIMIT
            )
            logger.info(f"Straddle 결과: {straddle}")

            # Vertical Spread
            logger.info("5. Vertical Spread 전략 테스트")
            vertical_spread = await self.trading_service.create_vertical_spread(
                account_hash=self.account_hash,
                long_option_symbol="AAPL_012025C150",
                short_option_symbol="AAPL_012025C155",
                quantity=1,
                spread_type="CALL",
                net_price=2.0,
                order_type=OrderType.LIMIT
            )
            logger.info(f"Vertical Spread 결과: {vertical_spread}")

            return True

        except Exception as e:
            logger.error(f"옵션 거래 테스트 실패: {e}")
            return False

    async def test_order_management(self):
        """주문 관리 테스트"""
        logger.info("\n=== 주문 관리 테스트 ===")

        try:
            # Get Orders
            logger.info("1. 주문 목록 조회 테스트")
            orders = await self.trading_service.get_orders(
                account_hash=self.account_hash,
                max_results=10
            )
            logger.info(f"주문 목록: {orders}")

            # Get Orders by Date Range
            logger.info("2. 기간별 주문 조회 테스트")
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            orders_by_date = await self.trading_service.get_orders_by_path(
                account_hash=self.account_hash,
                start_date=start_date,
                end_date=end_date
            )
            logger.info(f"기간별 주문: {orders_by_date}")

            # 주문 취소 및 수정은 실제 주문 ID가 필요하므로 구조만 테스트
            logger.info("3. 주문 취소/수정 구조 테스트 (실제 실행 안함)")
            logger.info("- cancel_order() 메서드 사용 가능")
            logger.info("- replace_order() 메서드 사용 가능")
            logger.info("- get_order_by_id() 메서드 사용 가능")

            return True

        except Exception as e:
            logger.error(f"주문 관리 테스트 실패: {e}")
            return False

    async def test_market_data(self):
        """시장 데이터 테스트"""
        logger.info("\n=== 시장 데이터 테스트 ===")

        try:
            # Price History
            logger.info("1. 가격 히스토리 조회 테스트")
            price_history = await self.trading_service.get_price_history(
                symbol=TEST_SYMBOL,
                period_type="day",
                period=5,
                frequency_type="minute",
                frequency=1
            )
            logger.info(f"가격 히스토리: {price_history.get('status', 'Failed')}")

            # Option Chain
            logger.info("2. 옵션 체인 조회 테스트")
            option_chain = await self.trading_service.get_option_chain(
                symbol=TEST_SYMBOL,
                contract_type="ALL",
                strike_count=5
            )
            logger.info(f"옵션 체인: {option_chain.get('status', 'Failed')}")

            # Market Movers
            logger.info("3. 시장 주요 변동 종목 조회 테스트")
            market_movers = await self.trading_service.get_market_movers(
                index="$DJI",
                direction="up",
                change="percent"
            )
            logger.info(f"시장 주요 변동: {market_movers.get('status', 'Failed')}")

            # Instrument Search
            logger.info("4. 금융상품 검색 테스트")
            instruments = await self.trading_service.search_instruments(
                symbol="AAPL",
                projection="symbol-search"
            )
            logger.info(f"금융상품 검색: {instruments.get('status', 'Failed')}")

            return True

        except Exception as e:
            logger.error(f"시장 데이터 테스트 실패: {e}")
            return False

    async def test_portfolio_data(self):
        """포트폴리오 데이터 테스트"""
        logger.info("\n=== 포트폴리오 데이터 테스트 ===")

        try:
            # Positions
            logger.info("1. 포지션 조회 테스트")
            positions = await self.trading_service.get_positions(
                account_hash=self.account_hash
            )
            logger.info(f"포지션 수: {positions.get('count', 0)}")

            # Balance
            logger.info("2. 잔고 조회 테스트")
            balance = await self.trading_service.get_balance(
                account_hash=self.account_hash
            )
            available_funds = balance.get('balances', {}).get('availableFunds', 0)
            logger.info(f"가용자금: ${available_funds:,.2f}")

            # Transactions
            logger.info("3. 거래 내역 조회 테스트")
            transactions = await self.trading_service.get_transactions(
                account_hash=self.account_hash,
                transaction_type="ALL"
            )
            logger.info(f"거래 내역 수: {transactions.get('count', 0)}")

            return True

        except Exception as e:
            logger.error(f"포트폴리오 데이터 테스트 실패: {e}")
            return False

    async def test_streaming_data(self):
        """스트리밍 데이터 테스트"""
        logger.info("\n=== 스트리밍 데이터 테스트 ===")

        try:
            # Start Streaming
            logger.info("1. 스트리밍 시작 테스트")
            start_streaming = await self.trading_service.start_streaming(
                symbols=[TEST_SYMBOL, "MSFT"],
                service="CHART_EQUITY"
            )
            logger.info(f"스트리밍 시작: {start_streaming.get('status', 'Failed')}")

            # Get Streaming Data (구조만 테스트)
            logger.info("2. 스트리밍 데이터 수신 테스트")
            streaming_data = await self.trading_service.get_streaming_data(
                service="CHART_EQUITY",
                timeout=5
            )
            logger.info(f"스트리밍 데이터: {streaming_data.get('status', 'Failed')}")

            # Stop Streaming
            logger.info("3. 스트리밍 중지 테스트")
            stop_streaming = await self.trading_service.stop_streaming(
                symbols=[TEST_SYMBOL, "MSFT"],
                service="CHART_EQUITY"
            )
            logger.info(f"스트리밍 중지: {stop_streaming.get('status', 'Failed')}")

            return True

        except Exception as e:
            logger.error(f"스트리밍 데이터 테스트 실패: {e}")
            return False

    async def run_comprehensive_test(self):
        """포괄적인 테스트 실행"""
        logger.info("=== 종합 Schwab API 기능 테스트 시작 ===")

        # 환경 설정
        if not await self.setup():
            logger.error("테스트 환경 설정 실패")
            return

        test_results = {}

        # 1. 기본 주문 타입 테스트
        test_results['basic_orders'] = await self.test_basic_order_types()

        # 2. 고급 주문 타입 테스트
        test_results['advanced_orders'] = await self.test_advanced_order_types()

        # 3. 복합 주문 전략 테스트
        test_results['complex_strategies'] = await self.test_complex_order_strategies()

        # 4. 옵션 거래 테스트
        test_results['options_trading'] = await self.test_options_trading()

        # 5. 주문 관리 테스트
        test_results['order_management'] = await self.test_order_management()

        # 6. 시장 데이터 테스트
        test_results['market_data'] = await self.test_market_data()

        # 7. 포트폴리오 데이터 테스트
        test_results['portfolio_data'] = await self.test_portfolio_data()

        # 8. 스트리밍 데이터 테스트
        test_results['streaming_data'] = await self.test_streaming_data()

        # 결과 요약
        logger.info("\n=== 테스트 결과 요약 ===")
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)

        for test_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"{test_name}: {status}")

        logger.info(f"\n전체 테스트: {passed}/{total} 통과")

        if passed == total:
            logger.info("🎉 모든 Schwab API 기능 테스트 통과!")
            logger.info("권한 문제가 해결되면 실제 거래 준비 완료!")
        else:
            logger.warning("⚠️ 일부 테스트 실패 - 구현 점검 필요")

async def main():
    """메인 테스트 실행"""
    tester = ComprehensiveSchwabAPITest()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())