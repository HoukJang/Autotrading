"""
Shared Context

시스템 전반에서 공유되는 리소스와 서비스를 관리하는 컨텍스트입니다.
의존성 주입 패턴을 통해 각 컴포넌트가 필요한 서비스에 접근할 수 있도록 합니다.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Protocol
from contextlib import asynccontextmanager

import asyncpg

from ..config.settings import Settings
from ..api.schwab_service import SchwabAPIService
from ..api.market_data_service import MarketDataService
from ..api.trading_service import TradingService
from ..api.account_service import AccountService
from .status_handler import StatusHandler, StatusDashboard

logger = logging.getLogger(__name__)


class SharedContext(Protocol):
    """
    공유 컨텍스트 프로토콜

    시스템의 모든 컴포넌트가 접근해야 하는 공통 리소스를 정의합니다.
    """

    # Configuration
    settings: Settings
    config: Dict[str, Any]

    # Database
    database_pool: Optional[asyncpg.Pool]

    # API Services
    schwab_api: SchwabAPIService
    market_data_service: MarketDataService
    trading_service: TradingService
    account_service: AccountService

    # Logging
    logger: logging.Logger

    # Status Management
    status_handler: StatusHandler
    status_dashboard: StatusDashboard

    # Lifecycle methods
    async def initialize(self) -> bool:
        """컨텍스트 초기화"""
        ...

    async def cleanup(self) -> None:
        """리소스 정리"""
        ...

    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        ...


class DefaultSharedContext:
    """
    기본 공유 컨텍스트 구현

    SharedContext 프로토콜을 구현하여 실제 리소스 관리를 담당합니다.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        SharedContext 초기화

        Args:
            settings: 시스템 설정 (None이면 기본값 사용)
        """
        self.settings = settings or Settings()
        self.config = self._build_config()

        # 상태 관리
        self._initialized = False
        self._database_pool: Optional[asyncpg.Pool] = None

        # API Services (초기화 시 생성)
        self.schwab_api: Optional[SchwabAPIService] = None
        self.market_data_service: Optional[MarketDataService] = None
        self.trading_service: Optional[TradingService] = None
        self.account_service: Optional[AccountService] = None

        # Status Management (초기화 시 생성)
        self.status_handler: Optional[StatusHandler] = None
        self.status_dashboard: Optional[StatusDashboard] = None

        # Logging 설정
        self.logger = self._setup_logging()

        logger.info(f"SharedContext created for environment: {self.settings.environment}")

    def _build_config(self) -> Dict[str, Any]:
        """설정 딕셔너리 구성"""
        return {
            "environment": self.settings.environment,
            "debug": self.settings.debug,
            "api_config": self.settings.api_config,
            "database_config": self.settings.database_config,
            "logging_config": self.settings.logging_config,
            "timezone": self.settings.timezone,
            "data_collection_symbols": self.settings.data_collection_symbols,
        }

    def _setup_logging(self) -> logging.Logger:
        """로깅 설정"""
        logging_config = self.settings.logging_config

        # 기본 로깅 설정
        logging.basicConfig(
            level=getattr(logging, logging_config.level),
            format=logging_config.format
        )

        # 컴포넌트별 로깅 레벨 설정
        logging.getLogger("autotrading.api.schwab_service").setLevel(
            getattr(logging, logging_config.schwab_api_level)
        )
        logging.getLogger("autotrading.data").setLevel(
            getattr(logging, logging_config.database_level)
        )
        logging.getLogger("autotrading.core.trader").setLevel(
            getattr(logging, logging_config.trading_level)
        )

        return logging.getLogger(__name__)

    async def initialize(self) -> bool:
        """
        컨텍스트 초기화

        모든 서비스와 리소스를 초기화합니다.

        Returns:
            초기화 성공 여부
        """
        if self._initialized:
            logger.warning("SharedContext already initialized")
            return True

        try:
            logger.info("Initializing SharedContext...")

            # 1. 데이터베이스 연결 풀 생성
            await self._initialize_database()

            # 2. Schwab API 서비스 초기화
            await self._initialize_schwab_api()

            # 3. Status Management 서비스 초기화
            self._initialize_status_management()

            # 4. 관련 서비스들 초기화
            self._initialize_dependent_services()

            # 5. 시스템 상태를 'initialized'로 설정
            await self.status_handler.update_status("system", "initialized", {
                "environment": self.settings.environment,
                "components_initialized": True
            })

            # 6. 상태 확인
            health_status = await self._health_check()
            if not health_status["healthy"]:
                raise Exception(f"Health check failed: {health_status}")

            self._initialized = True
            logger.info("SharedContext initialized successfully")
            return True

        except Exception as e:
            logger.error(f"SharedContext initialization failed: {e}")
            await self.cleanup()
            return False

    async def _initialize_database(self) -> None:
        """데이터베이스 연결 풀 초기화"""
        try:
            db_config = self.settings.database_config

            self._database_pool = await asyncpg.create_pool(
                self.settings.database_url,
                min_size=db_config.min_connections,
                max_size=db_config.max_connections,
                command_timeout=db_config.command_timeout,
                server_settings={
                    "application_name": "autotrading",
                    "timezone": self.settings.timezone
                }
            )

            # 연결 테스트
            async with self._database_pool.acquire() as conn:
                await conn.execute("SELECT 1")

            logger.info("Database connection pool initialized")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def _initialize_schwab_api(self) -> None:
        """Schwab API 서비스 초기화"""
        try:
            self.schwab_api = SchwabAPIService(
                app_key=self.settings.schwab_app_key,
                app_secret=self.settings.schwab_app_secret,
                callback_url=self.settings.schwab_callback_url,
                token_file=self.settings.schwab_token_file,
                config=self.settings.api_config
            )

            # API 서비스 초기화 및 인증
            success = await self.schwab_api.initialize()
            if not success:
                raise Exception("Schwab API initialization failed")

            logger.info("Schwab API service initialized")

        except Exception as e:
            logger.error(f"Schwab API initialization failed: {e}")
            raise

    def _initialize_dependent_services(self) -> None:
        """의존 서비스들 초기화"""
        try:
            # Market Data Service
            self.market_data_service = MarketDataService(self.schwab_api)

            # Trading Service
            self.trading_service = TradingService(self.schwab_api)

            # Account Service
            self.account_service = AccountService(self.schwab_api)

            logger.info("Dependent services initialized")

        except Exception as e:
            logger.error(f"Dependent services initialization failed: {e}")
            raise

    def _initialize_status_management(self) -> None:
        """Status Management 서비스 초기화"""
        try:
            if not self._database_pool:
                raise Exception("Database pool must be initialized before status management")

            # StatusHandler 초기화
            self.status_handler = StatusHandler(self._database_pool)

            # StatusDashboard 초기화
            self.status_dashboard = StatusDashboard(self.status_handler)

            logger.info("Status management services initialized")

        except Exception as e:
            logger.error(f"Status management initialization failed: {e}")
            raise

    async def _health_check(self) -> Dict[str, Any]:
        """전체 시스템 상태 확인"""
        health_status = {
            "healthy": True,
            "components": {},
            "timestamp": logging.time.time()
        }

        try:
            # 데이터베이스 상태 확인
            if self._database_pool:
                async with self._database_pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                health_status["components"]["database"] = "healthy"
            else:
                health_status["components"]["database"] = "unavailable"
                health_status["healthy"] = False

            # Schwab API 상태 확인
            if self.schwab_api:
                api_health = await self.schwab_api.health_check()
                health_status["components"]["schwab_api"] = api_health["status"]
                if api_health["status"] != "healthy":
                    health_status["healthy"] = False
            else:
                health_status["components"]["schwab_api"] = "unavailable"
                health_status["healthy"] = False

            logger.debug(f"Health check completed: {health_status}")
            return health_status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["healthy"] = False
            health_status["error"] = str(e)
            return health_status

    async def cleanup(self) -> None:
        """리소스 정리"""
        logger.info("Cleaning up SharedContext...")

        try:
            # API 서비스 정리
            if self.schwab_api:
                await self.schwab_api.close()
                self.schwab_api = None

            # 데이터베이스 연결 풀 정리
            if self._database_pool:
                await self._database_pool.close()
                self._database_pool = None

            # 서비스 참조 정리
            self.market_data_service = None
            self.trading_service = None
            self.account_service = None
            self.status_handler = None
            self.status_dashboard = None

            self._initialized = False
            logger.info("SharedContext cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._initialized

    @property
    def database_pool(self) -> Optional[asyncpg.Pool]:
        """데이터베이스 연결 풀 반환"""
        return self._database_pool

    async def get_database_connection(self):
        """데이터베이스 연결 획득 (컨텍스트 매니저)"""
        if not self._database_pool:
            raise Exception("Database pool not initialized")

        return self._database_pool.acquire()

    def get_stats(self) -> Dict[str, Any]:
        """SharedContext 통계 정보"""
        stats = {
            "initialized": self._initialized,
            "environment": self.settings.environment,
            "debug": self.settings.debug,
            "components": {}
        }

        # 각 컴포넌트 상태
        if self.schwab_api:
            stats["components"]["schwab_api"] = self.schwab_api.get_stats()

        if self._database_pool:
            stats["components"]["database"] = {
                "min_size": self._database_pool._minsize,
                "max_size": self._database_pool._maxsize,
                "current_size": self._database_pool.get_size(),
                "idle_size": self._database_pool.get_idle_size()
            }

        return stats


@asynccontextmanager
async def create_shared_context(settings: Optional[Settings] = None):
    """
    SharedContext 생성 및 관리를 위한 컨텍스트 매니저

    Args:
        settings: 시스템 설정

    Yields:
        초기화된 SharedContext 인스턴스

    Example:
        async with create_shared_context() as context:
            # 컨텍스트 사용
            data = await context.market_data_service.get_latest_bars(["AAPL"])
    """
    context = DefaultSharedContext(settings)

    try:
        success = await context.initialize()
        if not success:
            raise Exception("Failed to initialize SharedContext")

        yield context

    finally:
        await context.cleanup()