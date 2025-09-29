"""
SchwabAPIService 단위 테스트
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from autotrading.api.schwab_service import SchwabAPIService, SchwabAPIException
from autotrading.config.settings import APIConfig
from autotrading.utils.circuit_breaker import CircuitBreakerOpenException
from autotrading.utils.rate_limiter import RateLimiterExceededException


class TestSchwabAPIService:
    """SchwabAPIService 테스트 클래스"""

    @pytest.fixture
    def api_config(self):
        """테스트용 API 설정"""
        return APIConfig(
            rate_limit_per_minute=60,  # 테스트용으로 낮게 설정
            circuit_breaker_failure_threshold=3,
            circuit_breaker_recovery_timeout=5
        )

    @pytest.fixture
    def schwab_service(self, api_config):
        """SchwabAPIService 인스턴스"""
        return SchwabAPIService(
            app_key="test_app_key",
            app_secret="test_app_secret",
            callback_url="https://localhost:8080/callback",
            token_file="test_tokens.json",
            config=api_config
        )

    def test_initialization(self, schwab_service, api_config):
        """초기화 테스트"""
        assert schwab_service.app_key == "test_app_key"
        assert schwab_service.app_secret == "test_app_secret"
        assert schwab_service.callback_url == "https://localhost:8080/callback"
        assert schwab_service.config == api_config
        assert not schwab_service.is_authenticated()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_successful_authentication(self, mock_easy_client, schwab_service):
        """성공적인 인증 테스트"""
        # Mock 클라이언트 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 인증 실행
        success = await schwab_service.initialize()

        assert success
        assert schwab_service.is_authenticated()
        mock_easy_client.assert_called_once()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_authentication_failure(self, mock_easy_client, schwab_service):
        """인증 실패 테스트"""
        # Mock 클라이언트가 예외 발생하도록 설정
        mock_easy_client.side_effect = Exception("Authentication failed")

        # 인증 실행
        success = await schwab_service.initialize()

        assert not success
        assert not schwab_service.is_authenticated()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, schwab_service):
        """Rate limiting 테스트"""
        # Rate limiter가 초과되도록 설정
        schwab_service._rate_limiter._tokens = 0

        with pytest.raises(SchwabAPIException, match="Rate limit exceeded"):
            await schwab_service._execute_with_resilience(
                "test_operation",
                lambda: "test_result"
            )

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self, schwab_service):
        """Circuit breaker 개방 테스트"""
        # Circuit breaker를 강제로 열림 상태로 설정
        schwab_service._circuit_breaker._state = \
            schwab_service._circuit_breaker.__class__.__module__.CircuitBreakerState.OPEN

        with pytest.raises(SchwabAPIException, match="Service temporarily unavailable"):
            await schwab_service._execute_with_resilience(
                "test_operation",
                lambda: "test_result"
            )

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_get_market_data(self, mock_easy_client, schwab_service):
        """시장 데이터 조회 테스트"""
        # Mock 클라이언트 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candles": [
                {
                    "datetime": 1640995200000,
                    "open": 150.0,
                    "high": 155.0,
                    "low": 149.0,
                    "close": 154.0,
                    "volume": 1000000
                }
            ]
        }

        mock_client.get_user_preferences.return_value = mock_response
        mock_client.get_price_history.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 서비스 초기화
        await schwab_service.initialize()

        # 시장 데이터 조회
        result = await schwab_service.get_market_data("AAPL")

        assert "AAPL" in result
        assert "candles" in result["AAPL"]
        mock_client.get_price_history.assert_called()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_get_quotes(self, mock_easy_client, schwab_service):
        """실시간 시세 조회 테스트"""
        # Mock 클라이언트 설정
        mock_client = Mock()
        mock_auth_response = Mock()
        mock_auth_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_auth_response

        mock_quotes_response = Mock()
        mock_quotes_response.json.return_value = {
            "AAPL": {
                "lastPrice": 154.50,
                "bidPrice": 154.25,
                "askPrice": 154.75,
                "totalVolume": 50000000
            }
        }
        mock_client.get_quotes.return_value = mock_quotes_response
        mock_easy_client.return_value = mock_client

        # 서비스 초기화
        await schwab_service.initialize()

        # 시세 조회
        result = await schwab_service.get_quotes(["AAPL"])

        assert "AAPL" in result
        assert result["AAPL"]["lastPrice"] == 154.50
        mock_client.get_quotes.assert_called_with(["AAPL"])

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_health_check(self, mock_easy_client, schwab_service):
        """상태 확인 테스트"""
        # Mock 클라이언트 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 서비스 초기화
        await schwab_service.initialize()

        # 상태 확인
        health = await schwab_service.health_check()

        assert health["status"] == "healthy"
        assert health["authenticated"] == True
        assert "circuit_breaker" in health
        assert "rate_limiter" in health

    @pytest.mark.asyncio
    async def test_service_cleanup(self, schwab_service):
        """서비스 정리 테스트"""
        # 정리 실행
        await schwab_service.close()

        assert not schwab_service.is_authenticated()
        assert schwab_service._client is None

    def test_get_stats(self, schwab_service):
        """통계 정보 조회 테스트"""
        stats = schwab_service.get_stats()

        assert "authenticated" in stats
        assert "health_status" in stats
        assert "circuit_breaker" in stats
        assert "rate_limiter" in stats
        assert stats["authenticated"] == False  # 초기 상태


@pytest.mark.asyncio
class TestSchwabServiceIntegration:
    """SchwabAPIService 통합 테스트"""

    @pytest.fixture
    def api_config(self):
        """통합 테스트용 API 설정"""
        return APIConfig(
            rate_limit_per_minute=120,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_recovery_timeout=60
        )

    @pytest.mark.skip(reason="Requires actual Schwab API credentials")
    async def test_real_authentication(self, api_config):
        """실제 인증 테스트 (실제 자격증명 필요)"""
        service = SchwabAPIService(
            app_key="REAL_APP_KEY",
            app_secret="REAL_APP_SECRET",
            callback_url="https://localhost:8080/callback",
            config=api_config
        )

        try:
            success = await service.initialize()
            assert success
            assert service.is_authenticated()

            # 간단한 API 호출 테스트
            health = await service.health_check()
            assert health["status"] == "healthy"

        finally:
            await service.close()

    @pytest.mark.skip(reason="Requires actual Schwab API credentials")
    async def test_real_market_data(self, api_config):
        """실제 시장 데이터 조회 테스트"""
        service = SchwabAPIService(
            app_key="REAL_APP_KEY",
            app_secret="REAL_APP_SECRET",
            callback_url="https://localhost:8080/callback",
            config=api_config
        )

        try:
            await service.initialize()

            # 시장 데이터 조회
            data = await service.get_market_data("AAPL", period=1)
            assert "AAPL" in data
            assert "candles" in data["AAPL"]

            # 실시간 시세 조회
            quotes = await service.get_quotes(["AAPL", "GOOGL"])
            assert len(quotes) == 2

        finally:
            await service.close()