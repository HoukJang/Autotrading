"""
Schwab API Service

Schwab API와의 통신을 담당하는 핵심 서비스 클래스입니다.
Circuit breaker, rate limiting, 인증, 에러 핸들링을 통합 제공합니다.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

import schwab
from schwab.auth import easy_client
from schwab.client import Client

from ..config.settings import APIConfig, HealthStatus
from ..utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from ..utils.rate_limiter import TokenBucketRateLimiter, RateLimiterExceededException

logger = logging.getLogger(__name__)


class SchwabAPIException(Exception):
    """Schwab API 관련 예외"""
    pass


class AuthenticationException(SchwabAPIException):
    """인증 관련 예외"""
    pass


class SchwabAPIService:
    """
    Schwab API 서비스

    Schwab API와의 모든 통신을 담당하며, 다음 기능을 제공합니다:
    - OAuth 인증 및 토큰 관리
    - Rate limiting (분당 120 요청)
    - Circuit breaker 패턴
    - 자동 재시도 및 에러 핸들링
    - Health check 및 모니터링
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        callback_url: str,
        token_file: str = "tokens.json",
        config: Optional[APIConfig] = None
    ):
        """
        Schwab API 서비스 초기화

        Args:
            app_key: Schwab API 앱 키
            app_secret: Schwab API 앱 시크릿
            callback_url: OAuth 콜백 URL
            token_file: 토큰 저장 파일 경로
            config: API 설정 (None이면 기본값 사용)
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.callback_url = callback_url
        self.token_file = Path(token_file)
        self.config = config or APIConfig()

        # 클라이언트 상태
        self._client: Optional[Client] = None
        self._authenticated = False
        self._last_token_refresh = 0.0

        # Rate limiting
        self._rate_limiter = TokenBucketRateLimiter(
            rate_per_minute=self.config.rate_limit_per_minute,
            burst_size=self.config.rate_limit_burst,
            name="SchwabAPI"
        )

        # Circuit breaker
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            recovery_timeout=self.config.circuit_breaker_recovery_timeout,
            expected_exception=(SchwabAPIException, Exception),
            name="SchwabAPI"
        )

        # Health check
        self._last_health_check = 0.0
        self._health_status = HealthStatus.HEALTHY

        logger.info(f"SchwabAPIService initialized with config: {self.config}")

    async def initialize(self) -> bool:
        """
        서비스 초기화 및 인증

        Returns:
            초기화 성공 여부
        """
        try:
            await self._authenticate()
            logger.info("SchwabAPIService initialized successfully")
            return True
        except Exception as e:
            logger.error(f"SchwabAPIService initialization failed: {e}")
            return False

    async def _authenticate(self) -> None:
        """
        Schwab API 인증 수행

        기존 토큰이 있으면 유효성을 확인하고 재사용하며, 없거나 무효하면 새로 인증합니다.
        """
        try:
            if self.token_file.exists():
                # 기존 토큰 유효성 먼저 확인
                logger.info("Checking existing token validity...")
                if await self._validate_existing_token():
                    logger.info("Existing token is valid, using it")
                    return
                else:
                    logger.warning("Existing token is invalid or expired")
                    # 무효한 토큰 파일 백업 후 제거
                    backup_path = self.token_file.with_suffix('.json.backup')
                    self.token_file.rename(backup_path)
                    logger.info(f"Invalid token backed up to: {backup_path}")

            # 새로운 인증 플로우 또는 토큰 재생성
            logger.info("Starting new authentication flow")
            self._client = easy_client(
                self.app_key,
                self.app_secret,
                self.callback_url,
                str(self.token_file)
            )

            # 인증 테스트
            await self._test_authentication()
            self._authenticated = True
            self._last_token_refresh = time.time()

            logger.info("Schwab API authentication successful")

        except Exception as e:
            logger.error(f"Schwab API authentication failed: {e}")
            raise AuthenticationException(f"Authentication failed: {e}")

    async def _validate_existing_token(self) -> bool:
        """
        기존 토큰 파일의 유효성 검증

        Returns:
            토큰 유효성 여부
        """
        try:
            # 토큰 파일 내용 확인
            import json
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)

            if "token" not in token_data:
                logger.warning("Token file missing 'token' field")
                return False

            token = token_data["token"]
            if not token.get("access_token"):
                logger.warning("Token file missing access_token")
                return False

            # 클라이언트 생성 시도
            self._client = easy_client(
                self.app_key,
                self.app_secret,
                self.callback_url,
                str(self.token_file)
            )

            # 실제 API 호출로 토큰 유효성 확인
            await self._test_authentication()
            self._authenticated = True
            self._last_token_refresh = time.time()

            logger.info("Token validation successful")
            return True

        except json.JSONDecodeError:
            logger.warning("Token file contains invalid JSON")
            return False
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False

    async def _test_authentication(self) -> None:
        """인증 상태 테스트"""
        if not self._client:
            raise AuthenticationException("Client not initialized")

        try:
            # 간단한 API 호출로 인증 상태 확인
            response = self._client.get_user_preferences()
            if response.status_code != 200:
                raise AuthenticationException(f"Auth test failed: {response.status_code}")
        except Exception as e:
            raise AuthenticationException(f"Auth test failed: {e}")

    async def _refresh_token_if_needed(self) -> None:
        """필요시 토큰 갱신"""
        # 토큰 갱신은 schwab 라이브러리가 자동으로 처리
        # 여기서는 갱신 시간만 기록
        current_time = time.time()
        if current_time - self._last_token_refresh > 3000:  # 50분마다 체크
            logger.debug("Checking token refresh status")
            self._last_token_refresh = current_time

    async def _execute_with_resilience(
        self,
        operation: str,
        func: callable,
        *args,
        **kwargs
    ) -> Any:
        """
        복원력 패턴을 적용하여 API 호출 실행

        Args:
            operation: 작업 이름 (로깅용)
            func: 실행할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과

        Raises:
            SchwabAPIException: API 호출 실패
        """
        # Rate limiting 적용
        await self._rate_limiter.acquire(timeout=30.0)

        # 토큰 갱신 체크
        await self._refresh_token_if_needed()

        # Circuit breaker 적용하여 실행
        try:
            result = await self._circuit_breaker(func, *args, **kwargs)
            logger.debug(f"API operation '{operation}' completed successfully")
            return result

        except CircuitBreakerOpenException:
            logger.error(f"API operation '{operation}' blocked by circuit breaker")
            raise SchwabAPIException("Service temporarily unavailable")

        except RateLimiterExceededException:
            logger.error(f"API operation '{operation}' rate limited")
            raise SchwabAPIException("Rate limit exceeded")

        except Exception as e:
            logger.error(f"API operation '{operation}' failed: {e}")
            raise SchwabAPIException(f"Operation '{operation}' failed: {e}")

    async def get_market_data(
        self,
        symbols: Union[str, List[str]],
        period_type: str = "day",
        period: int = 1,
        frequency_type: str = "minute",
        frequency: int = 1
    ) -> Dict[str, Any]:
        """
        시장 데이터 조회

        Args:
            symbols: 심볼(들)
            period_type: 기간 타입 (day, month, year, ytd)
            period: 기간
            frequency_type: 빈도 타입 (minute, daily, weekly, monthly)
            frequency: 빈도

        Returns:
            시장 데이터
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        results = {}
        for symbol in symbols:
            try:
                data = await self._execute_with_resilience(
                    f"get_market_data_{symbol}",
                    lambda: self._client.get_price_history(
                        symbol=symbol,
                        period_type=Client.PriceHistory.PeriodType(period_type.upper()),
                        period=period,
                        frequency_type=Client.PriceHistory.FrequencyType(frequency_type.upper()),
                        frequency=frequency
                    )
                )
                results[symbol] = data.json() if hasattr(data, 'json') else data

            except Exception as e:
                logger.error(f"Failed to get market data for {symbol}: {e}")
                results[symbol] = {"error": str(e)}

        return results

    async def get_quotes(self, symbols: Union[str, List[str]]) -> Dict[str, Any]:
        """
        실시간 시세 조회

        Args:
            symbols: 심볼(들)

        Returns:
            실시간 시세 데이터
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        try:
            quotes = await self._execute_with_resilience(
                f"get_quotes_{','.join(symbols)}",
                lambda: self._client.get_quotes(symbols)
            )
            return quotes.json() if hasattr(quotes, 'json') else quotes

        except Exception as e:
            logger.error(f"Failed to get quotes for {symbols}: {e}")
            raise SchwabAPIException(f"Failed to get quotes: {e}")

    async def get_account_info(self, account_hash: str) -> Dict[str, Any]:
        """
        계좌 정보 조회

        Args:
            account_hash: 계좌 해시

        Returns:
            계좌 정보
        """
        try:
            account_info = await self._execute_with_resilience(
                f"get_account_info_{account_hash}",
                lambda: self._client.get_account(account_hash)
            )
            return account_info.json() if hasattr(account_info, 'json') else account_info

        except Exception as e:
            logger.error(f"Failed to get account info for {account_hash}: {e}")
            raise SchwabAPIException(f"Failed to get account info: {e}")

    async def place_order(self, account_hash: str, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        주문 실행

        Args:
            account_hash: 계좌 해시
            order: 주문 정보

        Returns:
            주문 결과
        """
        try:
            result = await self._execute_with_resilience(
                f"place_order_{account_hash}",
                lambda: self._client.place_order(account_hash, order)
            )
            logger.info(f"Order placed successfully for account {account_hash}")
            return result.json() if hasattr(result, 'json') else result

        except Exception as e:
            logger.error(f"Failed to place order for {account_hash}: {e}")
            raise SchwabAPIException(f"Failed to place order: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """
        시스템 상태 확인

        Returns:
            상태 정보
        """
        current_time = time.time()

        # 주기적으로만 실제 health check 수행
        if current_time - self._last_health_check < self.config.health_check_interval:
            return {
                "status": self._health_status.value,
                "authenticated": self._authenticated,
                "last_check": self._last_health_check,
                "cached": True
            }

        try:
            # 간단한 API 호출로 상태 확인
            if self._authenticated and self._client:
                await self._execute_with_resilience(
                    "health_check",
                    lambda: self._client.get_user_preferences()
                )
                self._health_status = HealthStatus.HEALTHY

            self._last_health_check = current_time

            return {
                "status": self._health_status.value,
                "authenticated": self._authenticated,
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "rate_limiter": self._rate_limiter.get_stats(),
                "last_check": self._last_health_check,
                "cached": False
            }

        except Exception as e:
            self._health_status = HealthStatus.UNHEALTHY
            logger.error(f"Health check failed: {e}")

            return {
                "status": self._health_status.value,
                "authenticated": self._authenticated,
                "error": str(e),
                "last_check": current_time,
                "cached": False
            }

    async def close(self) -> None:
        """서비스 종료 및 리소스 정리"""
        logger.info("Closing SchwabAPIService")
        # schwab 클라이언트는 자동으로 정리됨
        self._client = None
        self._authenticated = False

    def is_authenticated(self) -> bool:
        """인증 상태 확인"""
        return self._authenticated

    @property
    def client(self) -> Optional[Client]:
        """Schwab API 클라이언트 인스턴스에 접근"""
        return self._client

    def get_stats(self) -> Dict[str, Any]:
        """서비스 통계 정보 반환"""
        return {
            "authenticated": self._authenticated,
            "health_status": self._health_status.value,
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "rate_limiter": self._rate_limiter.get_stats(),
            "last_token_refresh": self._last_token_refresh,
            "last_health_check": self._last_health_check,
        }