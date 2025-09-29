"""
Circuit Breaker 패턴 구현

API 호출 실패 시 자동으로 회로를 차단하여 시스템 안정성을 보장합니다.
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Type, Union
import logging

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit Breaker 상태"""
    CLOSED = "closed"      # 정상 동작
    OPEN = "open"          # 차단 상태
    HALF_OPEN = "half_open"  # 복구 테스트 중


class CircuitBreakerOpenException(Exception):
    """Circuit Breaker가 열린 상태에서 호출 시 발생하는 예외"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker 패턴 구현

    연속된 실패가 임계값을 초과하면 회로를 차단하고,
    일정 시간 후 점진적으로 복구를 시도합니다.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Union[Type[Exception], tuple] = Exception,
        name: str = "CircuitBreaker"
    ):
        """
        Circuit Breaker 초기화

        Args:
            failure_threshold: 실패 임계값 (연속 실패 허용 횟수)
            recovery_timeout: 복구 대기 시간 (초)
            expected_exception: 처리할 예외 타입
            name: Circuit Breaker 이름 (로깅용)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name

        # 상태 관리
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        logger.info(
            f"Circuit Breaker '{name}' initialized: "
            f"threshold={failure_threshold}, timeout={recovery_timeout}s"
        )

    @property
    def state(self) -> CircuitBreakerState:
        """현재 상태 반환"""
        return self._state

    @property
    def failure_count(self) -> int:
        """현재 실패 횟수 반환"""
        return self._failure_count

    async def __call__(self, func: Callable, *args, **kwargs) -> Any:
        """
        함수를 Circuit Breaker로 감싸서 실행

        Args:
            func: 실행할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과

        Raises:
            CircuitBreakerOpenException: Circuit Breaker가 열린 상태
        """
        async with self._lock:
            await self._update_state()

            if self._state == CircuitBreakerState.OPEN:
                logger.warning(f"Circuit Breaker '{self.name}' is OPEN, rejecting call")
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is open"
                )

        try:
            # 함수 실행
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # 성공 시 상태 업데이트
            await self._on_success()
            return result

        except self.expected_exception as e:
            # 예상된 예외 발생 시 실패 처리
            await self._on_failure()
            raise e

    async def _update_state(self) -> None:
        """상태 업데이트 (내부 메서드)"""
        if self._state == CircuitBreakerState.OPEN:
            # OPEN 상태에서 복구 시간 확인
            if (
                self._last_failure_time and
                time.time() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = CircuitBreakerState.HALF_OPEN
                logger.info(f"Circuit Breaker '{self.name}' transitioned to HALF_OPEN")

    async def _on_success(self) -> None:
        """성공 시 처리"""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                # HALF_OPEN 상태에서 성공하면 CLOSED로 전환
                self._reset()
                logger.info(f"Circuit Breaker '{self.name}' recovered, transitioned to CLOSED")
            elif self._failure_count > 0:
                # 일부 실패가 있었지만 성공하면 카운터 리셋
                self._failure_count = 0
                logger.debug(f"Circuit Breaker '{self.name}' failure count reset")

    async def _on_failure(self) -> None:
        """실패 시 처리"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            logger.warning(
                f"Circuit Breaker '{self.name}' failure {self._failure_count}/"
                f"{self.failure_threshold}"
            )

            if self._failure_count >= self.failure_threshold:
                # 임계값 초과 시 OPEN 상태로 전환
                self._state = CircuitBreakerState.OPEN
                logger.error(
                    f"Circuit Breaker '{self.name}' transitioned to OPEN "
                    f"(failures: {self._failure_count})"
                )

    def _reset(self) -> None:
        """상태 완전 리셋 (내부 메서드)"""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    async def reset(self) -> None:
        """수동으로 Circuit Breaker 리셋"""
        async with self._lock:
            self._reset()
            logger.info(f"Circuit Breaker '{self.name}' manually reset")

    def get_stats(self) -> dict:
        """Circuit Breaker 통계 정보 반환"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self._last_failure_time,
        }