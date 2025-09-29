"""
Authentication 단위 테스트

SchwabAPIService의 인증 관련 기능을 테스트합니다.
"""

import pytest
import asyncio
import tempfile
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

from autotrading.api.schwab_service import (
    SchwabAPIService,
    SchwabAPIException,
    AuthenticationException
)
from autotrading.config.settings import APIConfig, HealthStatus


class TestAuthentication:
    """인증 관련 테스트 클래스"""

    @pytest.fixture
    def api_config(self):
        """테스트용 API 설정"""
        return APIConfig(
            rate_limit_per_minute=60,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_recovery_timeout=5
        )

    @pytest.fixture
    def temp_token_file(self):
        """임시 토큰 파일"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        yield temp_path
        # 정리
        Path(temp_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_token_data(self):
        """Mock 토큰 데이터"""
        return {
            "token": {
                "access_token": "mock_access_token_12345",
                "refresh_token": "mock_refresh_token_67890",
                "expires_in": 1800,
                "token_type": "Bearer",
                "scope": "api"
            },
            "creation_timestamp": 1640995200.0
        }

    @pytest.fixture
    def schwab_service(self, api_config, temp_token_file):
        """SchwabAPIService 인스턴스"""
        return SchwabAPIService(
            app_key="TEST_APP_KEY",
            app_secret="TEST_APP_SECRET",
            callback_url="https://localhost:8182/callback",
            token_file=temp_token_file,
            config=api_config
        )

    def test_service_initialization(self, schwab_service, api_config):
        """서비스 초기화 테스트"""
        assert schwab_service.app_key == "TEST_APP_KEY"
        assert schwab_service.app_secret == "TEST_APP_SECRET"
        assert schwab_service.callback_url == "https://localhost:8182/callback"
        assert schwab_service.config == api_config
        assert not schwab_service.is_authenticated()
        assert schwab_service._client is None

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_successful_authentication_with_existing_token(
        self,
        mock_easy_client,
        schwab_service,
        temp_token_file,
        mock_token_data
    ):
        """기존 토큰으로 성공적인 인증 테스트"""
        # 기존 토큰 파일 생성
        with open(temp_token_file, 'w') as f:
            json.dump(mock_token_data, f)

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
        assert schwab_service._client is not None
        mock_easy_client.assert_called_once_with(
            "TEST_APP_KEY",
            "TEST_APP_SECRET",
            "https://localhost:8182/callback",
            temp_token_file
        )

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_successful_authentication_new_token(
        self,
        mock_easy_client,
        schwab_service
    ):
        """새로운 토큰으로 성공적인 인증 테스트"""
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
    async def test_authentication_failure_client_creation(
        self,
        mock_easy_client,
        schwab_service
    ):
        """클라이언트 생성 실패 테스트"""
        # Mock이 예외를 발생하도록 설정
        mock_easy_client.side_effect = Exception("Failed to create client")

        # 인증 실행
        success = await schwab_service.initialize()

        assert not success
        assert not schwab_service.is_authenticated()
        assert schwab_service._client is None

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_authentication_failure_api_test(
        self,
        mock_easy_client,
        schwab_service
    ):
        """API 테스트 실패 테스트"""
        # Mock 클라이언트 설정 (API 호출 실패)
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 401  # Unauthorized
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        # 인증 실행
        success = await schwab_service.initialize()

        assert not success
        assert not schwab_service.is_authenticated()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_authentication_failure_api_exception(
        self,
        mock_easy_client,
        schwab_service
    ):
        """API 호출 예외 테스트"""
        # Mock 클라이언트 설정 (API 호출 시 예외)
        mock_client = Mock()
        mock_client.get_user_preferences.side_effect = Exception("API Error")
        mock_easy_client.return_value = mock_client

        # 인증 실행
        success = await schwab_service.initialize()

        assert not success
        assert not schwab_service.is_authenticated()

    @pytest.mark.asyncio
    async def test_token_refresh_check(self, schwab_service):
        """토큰 갱신 체크 테스트"""
        import time

        # 토큰 갱신 시간 설정
        schwab_service._last_token_refresh = time.time() - 3600  # 1시간 전

        # 토큰 갱신 체크 실행
        await schwab_service._refresh_token_if_needed()

        # 갱신 시간이 업데이트되었는지 확인
        assert schwab_service._last_token_refresh > time.time() - 10

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_service_cleanup(self, mock_easy_client, schwab_service):
        """서비스 정리 테스트"""
        # 인증된 상태로 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        await schwab_service.initialize()
        assert schwab_service.is_authenticated()

        # 정리 실행
        await schwab_service.close()

        assert not schwab_service.is_authenticated()
        assert schwab_service._client is None

    def test_authentication_state_methods(self, schwab_service):
        """인증 상태 관련 메서드 테스트"""
        # 초기 상태
        assert not schwab_service.is_authenticated()

        # 수동으로 인증 상태 설정
        schwab_service._authenticated = True
        assert schwab_service.is_authenticated()

        # 상태 리셋
        schwab_service._authenticated = False
        assert not schwab_service.is_authenticated()

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_health_check_authenticated(self, mock_easy_client, schwab_service):
        """인증된 상태에서 헬스 체크 테스트"""
        # 인증된 상태로 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        await schwab_service.initialize()

        # 헬스 체크 실행
        health = await schwab_service.health_check()

        assert health["status"] == HealthStatus.HEALTHY.value
        assert health["authenticated"] == True
        assert "circuit_breaker" in health
        assert "rate_limiter" in health

    @pytest.mark.asyncio
    async def test_health_check_unauthenticated(self, schwab_service):
        """인증되지 않은 상태에서 헬스 체크 테스트"""
        # 헬스 체크 실행
        health = await schwab_service.health_check()

        assert health["authenticated"] == False
        assert "last_check" in health

    def test_get_stats(self, schwab_service):
        """통계 정보 조회 테스트"""
        stats = schwab_service.get_stats()

        assert "authenticated" in stats
        assert "health_status" in stats
        assert "circuit_breaker" in stats
        assert "rate_limiter" in stats
        assert stats["authenticated"] == False

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_get_stats_authenticated(self, mock_easy_client, schwab_service):
        """인증된 상태에서 통계 정보 조회 테스트"""
        # 인증된 상태로 설정
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_user_preferences.return_value = mock_response
        mock_easy_client.return_value = mock_client

        await schwab_service.initialize()

        stats = schwab_service.get_stats()

        assert stats["authenticated"] == True
        assert stats["health_status"] == HealthStatus.HEALTHY.value
        assert "last_token_refresh" in stats
        assert "last_health_check" in stats


class TestAuthenticationIntegration:
    """인증 통합 테스트"""

    @pytest.fixture
    def api_config(self):
        """통합 테스트용 API 설정"""
        return APIConfig(
            rate_limit_per_minute=120,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_recovery_timeout=60
        )

    @pytest.mark.asyncio
    @patch('autotrading.api.schwab_service.easy_client')
    async def test_full_authentication_flow(self, mock_easy_client, api_config):
        """전체 인증 플로우 테스트"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_token_file = f.name

        try:
            # SchwabAPIService 생성
            service = SchwabAPIService(
                app_key="TEST_KEY",
                app_secret="TEST_SECRET",
                callback_url="https://localhost:8182/callback",
                token_file=temp_token_file,
                config=api_config
            )

            # Mock 설정
            mock_client = Mock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.get_user_preferences.return_value = mock_response
            mock_easy_client.return_value = mock_client

            # 전체 플로우 실행
            success = await service.initialize()
            assert success
            assert service.is_authenticated()

            # 헬스 체크
            health = await service.health_check()
            assert health["status"] == HealthStatus.HEALTHY.value

            # 통계 확인
            stats = service.get_stats()
            assert stats["authenticated"] == True

            # 정리
            await service.close()
            assert not service.is_authenticated()

        finally:
            # 임시 파일 정리
            Path(temp_token_file).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_authentication_error_handling(self, api_config):
        """인증 오류 처리 테스트"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_token_file = f.name

        try:
            service = SchwabAPIService(
                app_key="INVALID_KEY",
                app_secret="INVALID_SECRET",
                callback_url="https://localhost:8182/callback",
                token_file=temp_token_file,
                config=api_config
            )

            # easy_client가 실패하도록 설정
            with patch('autotrading.api.schwab_service.easy_client') as mock_easy_client:
                mock_easy_client.side_effect = Exception("Authentication failed")

                success = await service.initialize()
                assert not success
                assert not service.is_authenticated()

                # 오류 상태에서 헬스 체크
                health = await service.health_check()
                assert health["authenticated"] == False

        finally:
            Path(temp_token_file).unlink(missing_ok=True)


class TestTokenManagement:
    """토큰 관리 테스트"""

    @pytest.fixture
    def mock_token_data(self):
        """Mock 토큰 데이터"""
        return {
            "token": {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 1800,
                "token_type": "Bearer"
            }
        }

    def test_token_file_handling(self, mock_token_data):
        """토큰 파일 처리 테스트"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_token_file = f.name
            json.dump(mock_token_data, f)

        try:
            # 토큰 파일이 존재하는지 확인
            token_path = Path(temp_token_file)
            assert token_path.exists()

            # 토큰 데이터 읽기
            with open(temp_token_file, 'r') as f:
                loaded_data = json.load(f)

            assert loaded_data == mock_token_data
            assert "access_token" in loaded_data["token"]
            assert "refresh_token" in loaded_data["token"]

        finally:
            Path(temp_token_file).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_token_refresh_timing(self):
        """토큰 갱신 타이밍 테스트"""
        import time

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_token_file = f.name

        try:
            service = SchwabAPIService(
                app_key="TEST_KEY",
                app_secret="TEST_SECRET",
                callback_url="https://localhost:8182/callback",
                token_file=temp_token_file
            )

            # 초기 갱신 시간
            initial_time = service._last_token_refresh

            # 시간이 지난 것으로 시뮬레이션
            service._last_token_refresh = time.time() - 3600

            # 갱신 체크
            await service._refresh_token_if_needed()

            # 갱신 시간이 업데이트되었는지 확인
            assert service._last_token_refresh > initial_time

        finally:
            Path(temp_token_file).unlink(missing_ok=True)