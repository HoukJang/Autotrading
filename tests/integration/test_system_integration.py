"""
시스템 통합 테스트

전체 시스템의 컴포넌트들이 올바르게 통합되어 동작하는지 테스트합니다.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from autotrading.core.shared_context import DefaultSharedContext, create_shared_context
from autotrading.config.settings import Settings, Environment


class TestSystemIntegration:
    """시스템 통합 테스트"""

    @pytest.fixture
    def test_settings(self):
        """테스트용 설정"""
        return Settings(
            environment=Environment.DEVELOPMENT,
            debug=True,
            schwab_app_key="test_app_key",
            schwab_app_secret="test_app_secret",
            schwab_callback_url="https://localhost:8080/callback",
            schwab_token_file="test_tokens.json",
            database_url="postgresql://test:test@localhost:5432/test_autotrading"
        )

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_shared_context_initialization(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """SharedContext 초기화 테스트"""
        # Mock 데이터베이스 풀
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_pool.return_value = mock_pool

        # Mock Schwab 클라이언트
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # SharedContext 초기화
        context = DefaultSharedContext(test_settings)

        try:
            success = await context.initialize()

            assert success
            assert context.is_initialized()
            assert context.schwab_api is not None
            assert context.market_data_service is not None
            assert context.trading_service is not None
            assert context.account_service is not None
            assert context.database_pool is not None

        finally:
            await context.cleanup()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_market_data_collection_flow(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """시장 데이터 수집 플로우 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_pool.return_value = mock_pool

        mock_client = Mock()
        mock_auth_response = Mock()
        mock_auth_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_auth_response

        # 시장 데이터 응답 Mock
        mock_market_response = Mock()
        mock_market_response.json.return_value = {
            "candles": [
                {
                    "datetime": 1640995200000,  # 2022-01-01 00:00:00 UTC
                    "open": 150.0,
                    "high": 155.0,
                    "low": 149.0,
                    "close": 154.0,
                    "volume": 1000000
                }
            ]
        }
        mock_client.get_price_history.return_value = mock_market_response
        mock_easy_client.return_value = mock_client

        # 시스템 초기화 및 테스트
        async with create_shared_context(test_settings) as context:
            # 시장 데이터 수집
            symbols = ["AAPL", "GOOGL"]
            market_data = await context.market_data_service.get_latest_bars(symbols)

            assert len(market_data) == 2
            assert "AAPL" in market_data
            assert "GOOGL" in market_data

            # 데이터 검증
            aapl_data = market_data["AAPL"]
            assert not aapl_data.empty
            assert "symbol" in aapl_data.columns
            assert "ts" in aapl_data.columns
            assert "open" in aapl_data.columns
            assert "high" in aapl_data.columns
            assert "low" in aapl_data.columns
            assert "close" in aapl_data.columns
            assert "volume" in aapl_data.columns

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_trading_flow(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """트레이딩 플로우 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_pool.return_value = mock_pool

        mock_client = Mock()
        mock_auth_response = Mock()
        mock_auth_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_auth_response

        # 계좌 정보 Mock
        mock_account_response = Mock()
        mock_account_response.json.return_value = {
            "securitiesAccount": {
                "accountNumber": "123456789",
                "type": "MARGIN",
                "currentBalances": {
                    "liquidationValue": 100000.0,
                    "cashBalance": 50000.0,
                    "availableFunds": 45000.0,
                    "buyingPower": 90000.0
                },
                "initialBalances": {
                    "totalLongValue": 50000.0
                },
                "positions": []
            }
        }
        mock_client.get_account.return_value = mock_account_response

        # 주문 응답 Mock
        mock_order_response = Mock()
        mock_order_response.json.return_value = {
            "orderId": "ORDER123456"
        }
        mock_client.place_order.return_value = mock_order_response

        mock_easy_client.return_value = mock_client

        # 시스템 초기화 및 테스트
        async with create_shared_context(test_settings) as context:
            account_hash = "test_account_hash"

            # 1. 계좌 정보 조회
            account_summary = await context.account_service.get_account_summary(account_hash)
            assert account_summary["account_hash"] == account_hash
            assert account_summary["total_value"] == 100000.0
            assert account_summary["available_funds"] == 45000.0

            # 2. 매수력 확인
            buying_power = await context.account_service.get_buying_power(account_hash)
            assert buying_power == 90000.0

            # 3. 포지션 사이즈 계산
            position_calc = await context.trading_service.calculate_position_size(
                account_hash=account_hash,
                symbol="AAPL",
                risk_percentage=0.02,  # 2% 리스크
                entry_price=150.0,
                stop_loss_price=145.0
            )

            assert position_calc["symbol"] == "AAPL"
            assert position_calc["risk_percentage"] == 0.02
            assert position_calc["calculated_position_size"] > 0

            # 4. 시장가 주문 실행
            from autotrading.api.trading_service import OrderSide
            order_result = await context.trading_service.create_market_order(
                account_hash=account_hash,
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=position_calc["calculated_position_size"]
            )

            assert "order_id" in order_result or "raw_result" in order_result
            assert order_result["order_type"] == "market_buy"

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_health_monitoring(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """시스템 상태 모니터링 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_pool.get_size.return_value = 5
        mock_pool.get_idle_size.return_value = 3
        mock_create_pool.return_value = mock_pool

        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 시스템 초기화 및 테스트
        async with create_shared_context(test_settings) as context:
            # 개별 컴포넌트 상태 확인
            schwab_health = await context.schwab_api.health_check()
            assert schwab_health["status"] == "healthy"
            assert schwab_health["authenticated"] == True

            # 전체 시스템 통계
            stats = context.get_stats()
            assert stats["initialized"] == True
            assert stats["environment"] == Environment.DEVELOPMENT
            assert "components" in stats
            assert "schwab_api" in stats["components"]
            assert "database" in stats["components"]

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_error_handling_and_resilience(
        self,
        mock_easy_client,
        test_settings
    ):
        """에러 핸들링 및 복원력 테스트"""
        # 데이터베이스 연결 실패 시뮬레이션
        with patch('asyncpg.create_pool') as mock_create_pool:
            mock_create_pool.side_effect = Exception("Database connection failed")

            context = DefaultSharedContext(test_settings)

            # 초기화 실패 확인
            success = await context.initialize()
            assert not success
            assert not context.is_initialized()

            # 정리 작업이 안전하게 수행되는지 확인
            await context.cleanup()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_concurrent_operations(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """동시 작업 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_pool.return_value = mock_pool

        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response

        # 시세 응답 Mock
        mock_quotes_response = Mock()
        mock_quotes_response.json.return_value = {
            "AAPL": {"lastPrice": 150.0, "bidPrice": 149.95, "askPrice": 150.05},
            "GOOGL": {"lastPrice": 2500.0, "bidPrice": 2499.0, "askPrice": 2501.0},
            "MSFT": {"lastPrice": 300.0, "bidPrice": 299.95, "askPrice": 300.05}
        }
        mock_client.get_quotes.return_value = mock_quotes_response
        mock_easy_client.return_value = mock_client

        # 시스템 초기화 및 테스트
        async with create_shared_context(test_settings) as context:
            symbols = ["AAPL", "GOOGL", "MSFT"]

            # 동시에 여러 작업 실행
            tasks = [
                context.market_data_service.get_real_time_quotes(symbols),
                context.schwab_api.health_check(),
                context.market_data_service.get_real_time_quotes(symbols[:2])
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 모든 작업이 성공적으로 완료되었는지 확인
            for result in results:
                assert not isinstance(result, Exception)

            # 첫 번째 결과 (전체 심볼 시세) 확인
            quotes = results[0]
            assert len(quotes) == 3
            assert all(symbol in quotes for symbol in symbols)

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_context_manager_pattern(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """컨텍스트 매니저 패턴 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_pool.close = AsyncMock()
        mock_create_pool.return_value = mock_pool

        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 컨텍스트 매니저를 사용한 안전한 리소스 관리
        context_ref = None

        async with create_shared_context(test_settings) as context:
            context_ref = context
            assert context.is_initialized()

            # 컨텍스트 내에서 작업 수행
            health = await context.schwab_api.health_check()
            assert health["status"] == "healthy"

        # 컨텍스트가 종료된 후 정리가 완료되었는지 확인
        assert not context_ref.is_initialized()
        mock_pool.close.assert_called_once()


@pytest.mark.asyncio
class TestSystemFailureScenarios:
    """시스템 실패 시나리오 테스트"""

    @pytest.fixture
    def test_settings(self):
        """테스트용 설정"""
        return Settings(
            environment=Environment.DEVELOPMENT,
            debug=True,
            schwab_app_key="test_app_key",
            schwab_app_secret="test_app_secret",
            schwab_callback_url="https://localhost:8080/callback",
            database_url="postgresql://test:test@localhost:5432/test_autotrading"
        )

    @pytest.mark.asyncio
    async def test_database_failure_recovery(self, test_settings):
        """데이터베이스 실패 및 복구 테스트"""
        with patch('asyncpg.create_pool') as mock_create_pool:
            # 초기 연결 실패
            mock_create_pool.side_effect = Exception("Database unreachable")

            context = DefaultSharedContext(test_settings)
            success = await context.initialize()

            assert not success
            assert not context.is_initialized()

            await context.cleanup()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    @patch('asyncpg.create_pool')
    async def test_api_circuit_breaker_behavior(
        self,
        mock_create_pool,
        mock_easy_client,
        test_settings
    ):
        """API Circuit Breaker 동작 테스트"""
        # Mock 설정
        mock_pool = Mock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_pool.return_value = mock_pool

        # API 호출이 연속으로 실패하도록 설정
        mock_client = Mock()
        mock_client.get_user_preferences.side_effect = Exception("API Error")
        mock_easy_client.return_value = mock_client

        context = DefaultSharedContext(test_settings)
        try:
            # 초기화 실패 (인증 실패)
            success = await context.initialize()
            assert not success

        finally:
            await context.cleanup()