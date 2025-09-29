"""
Ticker Manager - 지능형 ticker 생명주기 관리

상장폐지 감지, 신규 ticker 발견, 데이터 품질 관리를 담당하는 핵심 컴포넌트입니다.
오케스트레이터에서 호출할 수 있는 배치 처리 메서드들을 제공합니다.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass

import psycopg2
from schwab import auth
from schwab.client import Client

from ..config.settings import settings
from .status_handler import StatusHandler, ComponentState


class ErrorConfidence(Enum):
    """오류 신뢰도 수준"""
    HIGH = "high"      # 즉시 조치 필요
    MEDIUM = "medium"  # 추가 조사 필요
    LOW = "low"        # 재시도 필요


class TickerStatus(Enum):
    """Ticker 상태"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVESTIGATING = "investigating"
    DELISTED = "delisted"


@dataclass
class ErrorAnalysis:
    """API 오류 분석 결과"""
    error_type: str
    confidence: ErrorConfidence
    should_deactivate: bool
    retry_recommended: bool
    message: str


@dataclass
class BatchResult:
    """배치 처리 결과"""
    processed_count: int
    success_count: int
    error_count: int
    deactivated_count: int
    errors: List[str]
    processing_time: float


class TickerManager:
    """
    지능형 Ticker 관리자

    주요 기능:
    - 상장폐지 감지 및 비활성화
    - 신규 ticker 발견 및 추가
    - 데이터 품질 모니터링
    - 배치 처리 오케스트레이션
    """

    def __init__(self, schwab_client: Optional[Client] = None, status_handler: Optional[StatusHandler] = None):
        self.logger = logging.getLogger(__name__)
        self.schwab_client = schwab_client
        self.status_handler = status_handler
        self.db_connection = None

        # 설정값들
        self.batch_size = 50  # API rate limit 고려
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.delisting_threshold = 5  # 연속 실패 횟수

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        await self._connect_db()
        if not self.schwab_client:
            self.schwab_client = await self._create_schwab_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.db_connection:
            self.db_connection.close()

    async def _connect_db(self):
        """데이터베이스 연결"""
        try:
            self.db_connection = psycopg2.connect(settings.database_url)
            self.logger.info("Database connection established")
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            raise

    async def _create_schwab_client(self) -> Client:
        """Schwab API 클라이언트 생성"""
        try:
            client = auth.easy_client(
                api_key=settings.schwab_app_key,
                app_secret=settings.schwab_app_secret,
                callback_url=settings.schwab_callback_url,
                token_path=settings.schwab_token_file
            )
            self.logger.info("Schwab client initialized")
            return client
        except Exception as e:
            self.logger.error(f"Schwab client initialization failed: {e}")
            raise

    def _analyze_api_error(self,
                          symbol: str,
                          status_code: int,
                          error_message: str,
                          error_code: Optional[str] = None) -> ErrorAnalysis:
        """
        API 오류 분석 및 신뢰도 판정

        Returns:
            ErrorAnalysis: 오류 분석 결과
        """
        error_message_lower = error_message.lower()

        # HIGH 신뢰도: 즉시 상장폐지로 판정
        if (status_code in [400, 404] and
            (error_code in ['INVALID_SYMBOL', 'SYMBOL_NOT_FOUND', 'SECURITY_NOT_TRADEABLE'] or
             any(phrase in error_message_lower for phrase in
                 ['symbol not found', 'invalid symbol', 'delisted', 'not tradeable']))):

            return ErrorAnalysis(
                error_type="delisting",
                confidence=ErrorConfidence.HIGH,
                should_deactivate=True,
                retry_recommended=False,
                message=f"High confidence delisting indicator: {error_message}"
            )

        # LOW 신뢰도: 임시 오류로 판정
        if (status_code in [500, 502, 503, 504, 429] or
            error_code in ['SERVICE_UNAVAILABLE', 'RATE_LIMIT_EXCEEDED', 'INTERNAL_ERROR'] or
            any(phrase in error_message_lower for phrase in
                ['service unavailable', 'rate limit', 'internal error', 'timeout'])):

            return ErrorAnalysis(
                error_type="temporary",
                confidence=ErrorConfidence.LOW,
                should_deactivate=False,
                retry_recommended=True,
                message=f"Temporary API issue: {error_message}"
            )

        # MEDIUM 신뢰도: 추가 조사 필요
        return ErrorAnalysis(
            error_type="unknown",
            confidence=ErrorConfidence.MEDIUM,
            should_deactivate=False,
            retry_recommended=True,
            message=f"Unknown error pattern: {error_message}"
        )

    async def _log_ticker_error(self,
                               symbol: str,
                               analysis: ErrorAnalysis,
                               status_code: int,
                               error_code: Optional[str] = None):
        """Ticker 오류 로그 기록"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                INSERT INTO ticker_errors (
                    symbol, error_type, error_code, http_status,
                    error_message, confidence_level
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                symbol, analysis.error_type, error_code, status_code,
                analysis.message, analysis.confidence.value
            ))
            self.db_connection.commit()
        except Exception as e:
            self.logger.error(f"Failed to log ticker error for {symbol}: {e}")

    async def _get_error_history(self, symbol: str, days: int = 7) -> List[Dict]:
        """심볼의 최근 오류 이력 조회"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT error_type, confidence_level, created_at, error_message
                FROM ticker_errors
                WHERE symbol = %s
                  AND created_at >= %s
                ORDER BY created_at DESC
            """, (symbol, datetime.utcnow() - timedelta(days=days)))

            columns = ['error_type', 'confidence_level', 'created_at', 'error_message']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get error history for {symbol}: {e}")
            return []

    async def _should_deactivate_ticker(self, symbol: str, current_analysis: ErrorAnalysis) -> bool:
        """
        심볼 비활성화 여부 결정

        결정 로직:
        - HIGH 신뢰도 오류: 즉시 비활성화
        - MEDIUM 신뢰도 오류가 3회 이상: 비활성화
        - 모든 오류가 10회 이상: 임시 비활성화
        """
        if current_analysis.confidence == ErrorConfidence.HIGH:
            return True

        error_history = await self._get_error_history(symbol, days=7)

        # 최근 7일간 HIGH 신뢰도 오류 수
        high_confidence_errors = sum(1 for err in error_history
                                   if err['confidence_level'] == 'high')

        # 최근 7일간 MEDIUM 신뢰도 오류 수
        medium_confidence_errors = sum(1 for err in error_history
                                     if err['confidence_level'] == 'medium')

        # 전체 오류 수
        total_errors = len(error_history)

        # 결정 로직
        if high_confidence_errors >= 1:  # HIGH 오류 1회면 비활성화
            return True
        elif medium_confidence_errors >= 3:  # MEDIUM 오류 3회 이상
            return True
        elif total_errors >= 10:  # 전체 오류 10회 이상
            return True

        return False

    async def _update_status_via_handler(self, details: Dict[str, Any]) -> None:
        """
        StatusHandler를 통한 상태 업데이트 헬퍼 메서드

        Args:
            details: 상태에 추가할 세부 정보
        """
        try:
            if self.status_handler:
                await self.status_handler.update_status(
                    component_name="ticker_manager",
                    state=ComponentState.RUNNING,
                    details=details
                )
        except Exception as e:
            self.logger.error(f"Failed to update status via handler: {e}")

    async def _deactivate_ticker(self, symbol: str, reason: str):
        """Ticker 비활성화"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                UPDATE tickers
                SET is_active = false,
                    record_modified_at = NOW()
                WHERE symbol = %s
            """, (symbol,))

            self.db_connection.commit()
            self.logger.warning(f"Ticker {symbol} deactivated: {reason}")

            # StatusHandler를 통한 상태 업데이트
            if self.status_handler:
                await self._update_status_via_handler({
                    "deactivated_ticker": symbol,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat()
                })

        except Exception as e:
            self.logger.error(f"Failed to deactivate ticker {symbol}: {e}")

    async def monitor_delisting_batch(self, batch_size: Optional[int] = None) -> BatchResult:
        """
        배치 상장폐지 모니터링

        오케스트레이터에서 호출하는 주요 메서드입니다.
        활성 ticker들의 상태를 확인하고 상장폐지된 것들을 비활성화합니다.

        Args:
            batch_size: 배치 크기 (기본값: self.batch_size)

        Returns:
            BatchResult: 배치 처리 결과
        """
        start_time = datetime.utcnow()
        batch_size = batch_size or self.batch_size

        try:
            # 활성 ticker 목록 조회 (최근 업데이트가 오래된 것 우선)
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT symbol
                FROM tickers
                WHERE is_active = true
                ORDER BY COALESCE(market_data_refreshed_at, created_at) ASC
                LIMIT %s
            """, (batch_size,))

            symbols = [row[0] for row in cursor.fetchall()]

            if not symbols:
                return BatchResult(0, 0, 0, 0, [], 0.0)

            self.logger.info(f"Starting delisting monitoring for {len(symbols)} symbols")

            processed_count = 0
            success_count = 0
            error_count = 0
            deactivated_count = 0
            errors = []

            # 심볼들을 배치로 처리
            for i in range(0, len(symbols), 10):  # 10개씩 처리
                batch_symbols = symbols[i:i+10]

                try:
                    # Schwab API로 quote 요청 (동기 함수)
                    response = self.schwab_client.get_quotes(batch_symbols)
                    response_data = response.json()  # JSON으로 변환

                    for symbol in batch_symbols:
                        processed_count += 1

                        if symbol in response_data:
                            # 성공적으로 데이터 수신
                            quote_data = response_data[symbol]

                            # 거래 중단 여부 확인
                            if quote_data.get('tradingHalted', False):
                                self.logger.warning(f"Trading halted for {symbol}")
                                # 거래 중단은 일시적일 수 있으므로 즉시 비활성화하지 않음

                            success_count += 1

                            # market_data_refreshed_at 업데이트
                            cursor.execute("""
                                UPDATE tickers
                                SET market_data_refreshed_at = NOW()
                                WHERE symbol = %s
                            """, (symbol,))
                        else:
                            # 응답에 심볼이 없음 (잠재적 상장폐지)
                            error_analysis = ErrorAnalysis(
                                error_type="missing_quote",
                                confidence=ErrorConfidence.MEDIUM,
                                should_deactivate=False,
                                retry_recommended=True,
                                message=f"Symbol {symbol} not in quote response"
                            )

                            await self._log_ticker_error(symbol, error_analysis, 200)

                            if await self._should_deactivate_ticker(symbol, error_analysis):
                                await self._deactivate_ticker(symbol, "Missing from quote response")
                                deactivated_count += 1

                            error_count += 1

                except Exception as e:
                    # API 오류 발생
                    error_msg = str(e)
                    self.logger.error(f"Batch quote request failed: {error_msg}")

                    # 각 심볼에 대해 개별 오류 처리
                    for symbol in batch_symbols:
                        processed_count += 1

                        # HTTP 상태 코드 추출 시도
                        status_code = getattr(e, 'status_code', 0)
                        if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                            status_code = e.response.status_code

                        error_analysis = self._analyze_api_error(symbol, status_code, error_msg)
                        await self._log_ticker_error(symbol, error_analysis, status_code)

                        if await self._should_deactivate_ticker(symbol, error_analysis):
                            await self._deactivate_ticker(symbol, f"API error: {error_msg}")
                            deactivated_count += 1

                        error_count += 1

                    errors.append(f"Batch {i//10 + 1}: {error_msg}")

                # Rate limit 준수
                await asyncio.sleep(1.0)

            self.db_connection.commit()
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            result = BatchResult(
                processed_count=processed_count,
                success_count=success_count,
                error_count=error_count,
                deactivated_count=deactivated_count,
                errors=errors,
                processing_time=processing_time
            )

            self.logger.info(f"Delisting monitoring completed: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Delisting monitoring batch failed: {e}")
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return BatchResult(0, 0, 1, 0, [str(e)], processing_time)

    async def discover_new_tickers_batch(self) -> BatchResult:
        """
        신규 ticker 발견 배치

        새로운 IPO나 상장 변경을 감지하여 ticker 테이블에 추가합니다.
        """
        start_time = datetime.utcnow()

        try:
            # 현재는 기본 구현으로 향후 확장 예정
            # TODO: Exchange API나 IPO 스케줄 API 통합

            self.logger.info("New ticker discovery not yet implemented")

            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return BatchResult(0, 0, 0, 0, ["Feature not implemented"], processing_time)

        except Exception as e:
            self.logger.error(f"New ticker discovery failed: {e}")
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return BatchResult(0, 0, 1, 0, [str(e)], processing_time)

    async def update_ticker_info_batch(self, batch_size: Optional[int] = None) -> BatchResult:
        """
        Ticker 정보 업데이트 배치

        활성 ticker들의 기본 정보 (가격, 시가총액, 재무지표 등)를 업데이트합니다.
        """
        start_time = datetime.utcnow()
        batch_size = batch_size or self.batch_size

        try:
            # 오래된 정보를 가진 활성 ticker 조회
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT symbol
                FROM tickers
                WHERE is_active = true
                  AND (market_data_refreshed_at IS NULL OR market_data_refreshed_at < NOW() - INTERVAL '1 day')
                ORDER BY COALESCE(market_data_refreshed_at, created_at) ASC
                LIMIT %s
            """, (batch_size,))

            symbols = [row[0] for row in cursor.fetchall()]

            if not symbols:
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                return BatchResult(0, 0, 0, 0, [], processing_time)

            self.logger.info(f"Starting ticker info update for {len(symbols)} symbols")

            processed_count = 0
            success_count = 0
            error_count = 0
            errors = []

            # 배치 처리
            for i in range(0, len(symbols), 10):
                batch_symbols = symbols[i:i+10]

                try:
                    response = self.schwab_client.get_quotes(batch_symbols)
                    response_data = response.json()  # JSON으로 변환

                    for symbol in batch_symbols:
                        processed_count += 1

                        if symbol in response_data:
                            quote_data = response_data[symbol]

                            # Ticker 정보 업데이트
                            cursor.execute("""
                                UPDATE tickers SET
                                    last_price = %(last_price)s,
                                    market_cap = %(market_cap)s,
                                    pe_ratio = %(pe_ratio)s,
                                    dividend_yield = %(dividend_yield)s,
                                    beta = %(beta)s,
                                    avg_volume_30d = %(avg_volume_30d)s,
                                    market_data_refreshed_at = NOW(),
                                    record_modified_at = NOW()
                                WHERE symbol = %(symbol)s
                            """, {
                                'symbol': symbol,
                                'last_price': quote_data.get('quote', {}).get('lastPrice'),
                                'market_cap': None,  # Not available in quotes API
                                'pe_ratio': quote_data.get('fundamental', {}).get('peRatio'),
                                'dividend_yield': quote_data.get('fundamental', {}).get('divYield'),
                                'beta': None,  # Not available in quotes API
                                'avg_volume_30d': quote_data.get('fundamental', {}).get('avg10DaysVolume')
                            })

                            success_count += 1
                        else:
                            error_count += 1
                            errors.append(f"No quote data for {symbol}")

                except Exception as e:
                    error_msg = str(e)
                    self.logger.error(f"Quote update batch failed: {error_msg}")
                    error_count += len(batch_symbols)
                    errors.append(f"Batch {i//10 + 1}: {error_msg}")

                await asyncio.sleep(1.0)

            self.db_connection.commit()
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            result = BatchResult(
                processed_count=processed_count,
                success_count=success_count,
                error_count=error_count,
                deactivated_count=0,
                errors=errors,
                processing_time=processing_time
            )

            self.logger.info(f"Ticker info update completed: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Ticker info update batch failed: {e}")
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return BatchResult(0, 0, 1, 0, [str(e)], processing_time)

    async def validate_data_quality_batch(self) -> BatchResult:
        """
        데이터 품질 검증 배치

        ticker 테이블의 데이터 일관성과 품질을 검증합니다.
        """
        start_time = datetime.utcnow()

        try:
            cursor = self.db_connection.cursor()

            # 데이터 품질 이슈 검사
            quality_checks = [
                ("negative_market_cap", "SELECT symbol FROM tickers WHERE market_cap < 0"),
                ("invalid_pe_ratio", "SELECT symbol FROM tickers WHERE pe_ratio < 0 OR pe_ratio > 1000"),
                ("excessive_dividend", "SELECT symbol FROM tickers WHERE dividend_yield > 50"),
                ("stale_data", "SELECT symbol FROM tickers WHERE is_active = true AND market_data_refreshed_at < NOW() - INTERVAL '7 days'"),
                ("missing_exchange", "SELECT symbol FROM tickers WHERE is_active = true AND exchange IS NULL")
            ]

            issues_found = 0
            total_checked = 0
            errors = []

            for check_name, query in quality_checks:
                try:
                    cursor.execute(query)
                    problematic_symbols = [row[0] for row in cursor.fetchall()]
                    total_checked += len(problematic_symbols)

                    if problematic_symbols:
                        issues_found += len(problematic_symbols)
                        self.logger.warning(f"Data quality issue '{check_name}': {len(problematic_symbols)} symbols")

                        # StatusHandler를 통한 상태 업데이트
                        if self.status_handler:
                            await self._update_status_via_handler({
                                "quality_issue": check_name,
                                "affected_symbols": len(problematic_symbols),
                                "timestamp": datetime.utcnow().isoformat()
                            })

                except Exception as e:
                    errors.append(f"Quality check '{check_name}' failed: {str(e)}")

            self.db_connection.commit()
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            result = BatchResult(
                processed_count=total_checked,
                success_count=total_checked - issues_found,
                error_count=issues_found,
                deactivated_count=0,
                errors=errors,
                processing_time=processing_time
            )

            self.logger.info(f"Data quality validation completed: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Data quality validation failed: {e}")
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            return BatchResult(0, 0, 1, 0, [str(e)], processing_time)


# 오케스트레이터에서 사용할 수 있는 편의 함수들
async def run_delisting_monitor(batch_size: int = 50, status_handler: Optional[StatusHandler] = None) -> BatchResult:
    """상장폐지 모니터링 실행"""
    async with TickerManager(status_handler=status_handler) as manager:
        return await manager.monitor_delisting_batch(batch_size)


async def run_ticker_update(batch_size: int = 50, status_handler: Optional[StatusHandler] = None) -> BatchResult:
    """Ticker 정보 업데이트 실행"""
    async with TickerManager(status_handler=status_handler) as manager:
        return await manager.update_ticker_info_batch(batch_size)


async def run_data_quality_check(status_handler: Optional[StatusHandler] = None) -> BatchResult:
    """데이터 품질 검증 실행"""
    async with TickerManager(status_handler=status_handler) as manager:
        return await manager.validate_data_quality_batch()