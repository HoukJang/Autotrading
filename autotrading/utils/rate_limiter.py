"""
Rate Limiter 구현

API 호출 빈도를 제한하여 API 제한을 준수합니다.
Token Bucket 알고리즘을 사용하여 구현됩니다.
"""

import asyncio
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiterExceededException(Exception):
    """Rate Limit 초과 시 발생하는 예외"""
    pass


class TokenBucketRateLimiter:
    """
    Token Bucket 알고리즘 기반 Rate Limiter

    일정한 속도로 토큰을 버킷에 추가하고,
    요청 시마다 토큰을 소비하여 속도를 제한합니다.
    """

    def __init__(
        self,
        rate_per_minute: int = 120,
        burst_size: Optional[int] = None,
        name: str = "RateLimiter"
    ):
        """
        Rate Limiter 초기화

        Args:
            rate_per_minute: 분당 허용 요청 수
            burst_size: 버스트 허용 크기 (None이면 rate_per_minute과 동일)
            name: Rate Limiter 이름 (로깅용)
        """
        self.rate_per_minute = rate_per_minute
        self.rate_per_second = rate_per_minute / 60.0
        self.burst_size = burst_size or rate_per_minute
        self.name = name

        # 토큰 버킷 상태
        self._tokens = float(self.burst_size)
        self._last_update = time.time()
        self._lock = asyncio.Lock()

        logger.info(
            f"Rate Limiter '{name}' initialized: "
            f"{rate_per_minute}/min, burst={self.burst_size}"
        )

    async def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        토큰 획득 시도

        Args:
            tokens: 필요한 토큰 수
            timeout: 최대 대기 시간 (초, None이면 무제한)

        Returns:
            토큰 획득 성공 여부

        Raises:
            RateLimiterExceededException: timeout 내에 토큰 획득 실패
        """
        start_time = time.time()

        while True:
            async with self._lock:
                self._update_tokens()

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    logger.debug(
                        f"Rate Limiter '{self.name}' acquired {tokens} tokens, "
                        f"remaining: {self._tokens:.2f}"
                    )
                    return True

                # 토큰 부족 시 필요한 대기 시간 계산
                needed_tokens = tokens - self._tokens
                wait_time = needed_tokens / self.rate_per_second

            # Timeout 체크
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed + wait_time > timeout:
                    logger.warning(
                        f"Rate Limiter '{self.name}' timeout exceeded "
                        f"(needed {wait_time:.2f}s, timeout {timeout}s)"
                    )
                    raise RateLimiterExceededException(
                        f"Rate limit exceeded, timeout after {timeout}s"
                    )

            # 토큰이 충분해질 때까지 대기
            logger.debug(
                f"Rate Limiter '{self.name}' waiting {wait_time:.2f}s for tokens"
            )
            await asyncio.sleep(min(wait_time, 1.0))  # 최대 1초씩 대기

    async def try_acquire(self, tokens: int = 1) -> bool:
        """
        토큰 획득 시도 (대기하지 않음)

        Args:
            tokens: 필요한 토큰 수

        Returns:
            토큰 획득 성공 여부
        """
        async with self._lock:
            self._update_tokens()

            if self._tokens >= tokens:
                self._tokens -= tokens
                logger.debug(
                    f"Rate Limiter '{self.name}' acquired {tokens} tokens, "
                    f"remaining: {self._tokens:.2f}"
                )
                return True

            logger.debug(
                f"Rate Limiter '{self.name}' insufficient tokens "
                f"(needed: {tokens}, available: {self._tokens:.2f})"
            )
            return False

    def _update_tokens(self) -> None:
        """토큰 버킷 업데이트 (내부 메서드)"""
        now = time.time()
        elapsed = now - self._last_update

        # 경과 시간만큼 토큰 추가
        tokens_to_add = elapsed * self.rate_per_second
        self._tokens = min(self.burst_size, self._tokens + tokens_to_add)
        self._last_update = now

    async def reset(self) -> None:
        """Rate Limiter 리셋 (토큰 버킷을 가득 채움)"""
        async with self._lock:
            self._tokens = float(self.burst_size)
            self._last_update = time.time()
            logger.info(f"Rate Limiter '{self.name}' reset")

    def get_stats(self) -> dict:
        """Rate Limiter 통계 정보 반환"""
        return {
            "name": self.name,
            "rate_per_minute": self.rate_per_minute,
            "rate_per_second": self.rate_per_second,
            "burst_size": self.burst_size,
            "current_tokens": self._tokens,
            "last_update": self._last_update,
        }

    async def get_wait_time(self, tokens: int = 1) -> float:
        """
        토큰 획득까지 필요한 대기 시간 계산

        Args:
            tokens: 필요한 토큰 수

        Returns:
            대기 시간 (초)
        """
        async with self._lock:
            self._update_tokens()

            if self._tokens >= tokens:
                return 0.0

            needed_tokens = tokens - self._tokens
            return needed_tokens / self.rate_per_second


class CompositRateLimiter:
    """
    여러 개의 Rate Limiter를 조합하는 복합 Rate Limiter

    예: 분당 제한 + 초당 제한을 동시에 적용
    """

    def __init__(self, limiters: list[TokenBucketRateLimiter], name: str = "CompositeRateLimiter"):
        """
        복합 Rate Limiter 초기화

        Args:
            limiters: 적용할 Rate Limiter 목록
            name: 이름 (로깅용)
        """
        self.limiters = limiters
        self.name = name

        logger.info(
            f"Composite Rate Limiter '{name}' initialized with "
            f"{len(limiters)} limiters"
        )

    async def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        모든 Rate Limiter에서 토큰 획득

        Args:
            tokens: 필요한 토큰 수
            timeout: 최대 대기 시간

        Returns:
            토큰 획득 성공 여부
        """
        start_time = time.time()

        for limiter in self.limiters:
            # 각 limiter별로 남은 timeout 계산
            remaining_timeout = None
            if timeout is not None:
                elapsed = time.time() - start_time
                remaining_timeout = max(0, timeout - elapsed)

            success = await limiter.acquire(tokens, remaining_timeout)
            if not success:
                logger.warning(
                    f"Composite Rate Limiter '{self.name}' failed "
                    f"on limiter '{limiter.name}'"
                )
                return False

        return True

    async def try_acquire(self, tokens: int = 1) -> bool:
        """
        모든 Rate Limiter에서 토큰 획득 시도 (대기하지 않음)

        Args:
            tokens: 필요한 토큰 수

        Returns:
            토큰 획득 성공 여부
        """
        for limiter in self.limiters:
            if not await limiter.try_acquire(tokens):
                logger.debug(
                    f"Composite Rate Limiter '{self.name}' failed "
                    f"on limiter '{limiter.name}'"
                )
                return False

        return True

    def get_stats(self) -> dict:
        """복합 Rate Limiter 통계 정보 반환"""
        return {
            "name": self.name,
            "limiters": [limiter.get_stats() for limiter in self.limiters]
        }