"""
설정 관리 모듈

Schwab API 및 시스템 전반의 설정을 관리합니다.
config 폴더의 auth.py 파일과 환경 변수를 통합하여 설정을 로드합니다.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import Field
from pydantic_settings import BaseSettings

# auth.py 파일에서 설정 로드 시도
try:
    from .auth import (
        SCHWAB_CONFIG,
        DATABASE_CONFIG,
        REDIS_CONFIG,
        ENVIRONMENT_CONFIG,
        SECURITY_CONFIG,
    )
    _AUTH_CONFIG_AVAILABLE = True
except ImportError:
    # auth.py가 없으면 기본값 사용
    SCHWAB_CONFIG = {}
    DATABASE_CONFIG = {}
    REDIS_CONFIG = {}
    ENVIRONMENT_CONFIG = {}
    SECURITY_CONFIG = {}
    _AUTH_CONFIG_AVAILABLE = False


class Environment(str, Enum):
    """환경 설정"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class HealthStatus(str, Enum):
    """시스템 상태"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class APIConfig:
    """Schwab API 설정"""
    # Rate limiting
    rate_limit_per_minute: int = 120  # Schwab API 공식 제한
    rate_limit_burst: int = 10        # 순간 최대 요청

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60  # seconds
    circuit_breaker_expected_exception: tuple = (Exception,)

    # Retry policy
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0  # seconds
    retry_max_delay: float = 60.0  # seconds
    retry_exponential_base: float = 2.0

    # Timeouts
    connect_timeout: int = 10  # seconds
    read_timeout: int = 30     # seconds
    total_timeout: int = 60    # seconds

    # Cache settings
    cache_ttl_market_data: int = 60    # seconds
    cache_ttl_account_info: int = 30   # seconds
    cache_ttl_symbols: int = 86400     # seconds (1 day)

    # Health check
    health_check_interval: int = 30    # seconds
    health_check_timeout: int = 5      # seconds


@dataclass
class DatabaseConfig:
    """데이터베이스 설정"""
    host: str = "localhost"
    port: int = 5432
    database: str = "autotrading"
    username: str = "autotrading"
    password: str = ""

    # Connection pool settings
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout: int = 30
    command_timeout: int = 60

    # TimescaleDB settings
    enable_timescaledb: bool = True
    chunk_time_interval: str = "1 day"


@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # File logging
    enable_file_logging: bool = True
    log_file_path: str = "logs/autotrading.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5

    # Structured logging
    enable_json_logging: bool = False

    # Component-specific levels
    schwab_api_level: str = "DEBUG"
    database_level: str = "INFO"
    trading_level: str = "INFO"


class Settings(BaseSettings):
    """전체 시스템 설정

    우선순위: 환경 변수 > auth.py 파일 > 기본값
    """

    # Environment
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        env="ENVIRONMENT",
        description="실행 환경"
    )
    debug: bool = Field(
        default=False,
        env="DEBUG",
        description="디버그 모드"
    )

    # Schwab API credentials
    schwab_app_key: str = Field(
        default="",
        env="SCHWAB_APP_KEY",
        description="Schwab API 앱 키"
    )
    schwab_app_secret: str = Field(
        default="",
        env="SCHWAB_APP_SECRET",
        description="Schwab API 앱 시크릿"
    )
    schwab_callback_url: str = Field(
        default="https://localhost:8080/callback",
        env="SCHWAB_CALLBACK_URL",
        description="OAuth 콜백 URL"
    )
    schwab_token_file: str = Field(
        default="tokens.json",
        env="SCHWAB_TOKEN_FILE",
        description="토큰 저장 파일"
    )

    # Database
    database_url: str = Field(
        default="",
        env="DATABASE_URL",
        description="데이터베이스 연결 URL"
    )

    # Redis (선택적)
    redis_url: Optional[str] = Field(
        default=None,
        env="REDIS_URL",
        description="Redis 연결 URL"
    )

    # API Configuration
    api_config: APIConfig = Field(default_factory=APIConfig)
    database_config: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging_config: LoggingConfig = Field(default_factory=LoggingConfig)

    # System settings
    timezone: str = Field(
        default="UTC",
        env="TIMEZONE",
        description="시스템 타임존"
    )
    data_collection_symbols: list[str] = Field(
        default_factory=lambda: ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"],
        description="데이터 수집 심볼 목록"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        # Pydantic이 먼저 환경 변수를 로드하도록 base class 초기화
        super().__init__(**kwargs)

        # 환경 변수로 설정되지 않은 값들만 auth.py에서 보완
        if _AUTH_CONFIG_AVAILABLE:
            # Schwab 설정 - 환경 변수가 없거나 기본값인 경우만 auth.py 사용
            if not self.schwab_app_key and SCHWAB_CONFIG.get('app_key'):
                self.schwab_app_key = SCHWAB_CONFIG['app_key']
            if not self.schwab_app_secret and SCHWAB_CONFIG.get('app_secret'):
                self.schwab_app_secret = SCHWAB_CONFIG['app_secret']
            if self.schwab_callback_url == "https://localhost:8080/callback" and SCHWAB_CONFIG.get('callback_url'):
                self.schwab_callback_url = SCHWAB_CONFIG['callback_url']
            if self.schwab_token_file == "tokens.json" and SCHWAB_CONFIG.get('token_file'):
                self.schwab_token_file = SCHWAB_CONFIG['token_file']

            # 데이터베이스 설정 - 환경 변수가 없는 경우만 auth.py 사용
            if not self.database_url and DATABASE_CONFIG.get('url'):
                self.database_url = DATABASE_CONFIG['url']

            # Redis 설정 - 환경 변수가 없는 경우만 auth.py 사용
            if not self.redis_url and REDIS_CONFIG.get('url'):
                self.redis_url = REDIS_CONFIG['url']

    def is_production(self) -> bool:
        """프로덕션 환경 여부 확인"""
        return self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """개발 환경 여부 확인"""
        return self.environment == Environment.DEVELOPMENT

    def get_auth_config_status(self) -> Dict[str, Any]:
        """인증 설정 파일 상태 확인"""
        # 실제 설정 소스 판단
        env_file_exists = os.path.exists(".env")
        config_source = "environment_variables"

        if env_file_exists and _AUTH_CONFIG_AVAILABLE:
            config_source = "env_file_with_auth_fallback"
        elif env_file_exists:
            config_source = "env_file"
        elif _AUTH_CONFIG_AVAILABLE:
            config_source = "auth.py"
        else:
            config_source = "defaults_only"

        return {
            "auth_config_available": _AUTH_CONFIG_AVAILABLE,
            "env_file_available": env_file_exists,
            "schwab_configured": bool(self.schwab_app_key and self.schwab_app_secret),
            "database_configured": bool(self.database_url),
            "redis_configured": bool(self.redis_url),
            "config_source": config_source
        }

    def validate_required_config(self) -> None:
        """필수 설정 검증"""
        missing_configs = []

        if not self.schwab_app_key or self.schwab_app_key in ["", "YOUR_ACTUAL_APP_KEY", "YOUR_APP_KEY_HERE"]:
            missing_configs.append("schwab_app_key")

        if not self.schwab_app_secret or self.schwab_app_secret in ["", "YOUR_ACTUAL_APP_SECRET", "YOUR_APP_SECRET_HERE"]:
            missing_configs.append("schwab_app_secret")

        if not self.database_url or "your_real_password" in self.database_url or "your_password_here" in self.database_url:
            missing_configs.append("database_url")

        if missing_configs:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing_configs)}. "
                f"Please check autotrading/config/auth.py file or set environment variables."
            )


# 글로벌 설정 인스턴스
settings = Settings()