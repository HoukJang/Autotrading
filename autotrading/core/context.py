"""
SharedContext 생성 및 관리

모든 서비스가 공유하는 리소스들을 중앙에서 관리하며,
자동 인증을 포함한 초기화를 담당합니다.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Protocol, runtime_checkable
import webbrowser
import subprocess
import sys

from ..config.settings import Settings
from ..api.schwab_service import SchwabAPIService, AuthenticationException
from ..database.connection import create_db_pool


logger = logging.getLogger(__name__)


@runtime_checkable
class SharedContext(Protocol):
    """공유 컨텍스트 프로토콜"""

    db_pool: Any
    schwab_client: Any
    config: Settings
    logger: logging.Logger


class AutoAuthenticationError(Exception):
    """자동 인증 관련 오류"""
    pass


async def create_shared_context(
    auto_auth: bool = True,
    force_manual_auth: bool = False
) -> Dict[str, Any]:
    """
    SharedContext 생성 및 초기화

    자동 인증을 포함한 전체 시스템 초기화를 수행합니다.

    Args:
        auto_auth: 자동 인증 수행 여부
        force_manual_auth: 강제 수동 인증 수행 여부

    Returns:
        초기화된 SharedContext 딕셔너리

    Raises:
        AutoAuthenticationError: 자동 인증 실패 시
    """
    logger.info("Creating SharedContext...")

    try:
        # 1. 설정 로드
        settings = Settings()
        logger.info(f"Settings loaded: environment={settings.environment}")

        # 2. 데이터베이스 연결
        logger.info("Connecting to database...")
        db_pool = await create_db_pool(settings.database_url)
        logger.info("Database connection established")

        # 3. Schwab API 서비스 초기화 (자동 인증 포함)
        schwab_service = None
        if auto_auth:
            schwab_service = await _initialize_schwab_service_with_auto_auth(
                settings, force_manual_auth
            )
        else:
            schwab_service = SchwabAPIService(
                app_key=settings.schwab_app_key,
                app_secret=settings.schwab_app_secret,
                callback_url=settings.schwab_callback_url,
                token_file=settings.schwab_token_file,
                config=settings.api_config
            )
            logger.info("Schwab service created without authentication")

        # 4. SharedContext 구성
        context = {
            'db_pool': db_pool,
            'schwab_client': schwab_service.client if schwab_service else None,
            'schwab_service': schwab_service,
            'config': settings,
            'logger': logging.getLogger('autotrading')
        }

        logger.info("SharedContext created successfully")
        return context

    except Exception as e:
        logger.error(f"Failed to create SharedContext: {e}")
        raise AutoAuthenticationError(f"Context creation failed: {e}")


async def _initialize_schwab_service_with_auto_auth(
    settings: Settings,
    force_manual: bool = False
) -> SchwabAPIService:
    """
    자동 인증을 포함한 Schwab 서비스 초기화

    토큰 유효성을 확인하고, 필요시 자동으로 수동 브라우저 인증을 시작합니다.

    Args:
        settings: 애플리케이션 설정
        force_manual: 강제 수동 인증 수행 여부

    Returns:
        초기화된 SchwabAPIService 인스턴스

    Raises:
        AutoAuthenticationError: 인증 실패 시
    """
    logger.info("Initializing Schwab service with auto-authentication...")

    service = SchwabAPIService(
        app_key=settings.schwab_app_key,
        app_secret=settings.schwab_app_secret,
        callback_url=settings.schwab_callback_url,
        token_file=settings.schwab_token_file,
        config=settings.api_config
    )

    # 강제 수동 인증 요청 시
    if force_manual:
        logger.info("Force manual authentication requested")
        await _perform_manual_authentication(settings, service)
        return service

    # 기존 토큰으로 초기화 시도
    try:
        logger.info("Attempting authentication with existing token...")
        success = await service.initialize()

        if success and service.is_authenticated():
            logger.info("✅ Authentication successful with existing token")
            return service
        else:
            logger.warning("❌ Authentication failed with existing token")

    except AuthenticationException as e:
        logger.warning(f"Authentication failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")

    # 기존 토큰 실패 시 자동으로 수동 인증 진행
    logger.info("🔄 Starting automatic manual authentication...")
    await _perform_manual_authentication(settings, service)

    return service


async def _perform_manual_authentication(
    settings: Settings,
    service: SchwabAPIService
) -> None:
    """
    수동 브라우저 인증 실행

    브라우저 인증 스크립트를 실행하여 토큰을 획득합니다.

    Args:
        settings: 애플리케이션 설정
        service: Schwab API 서비스 인스턴스

    Raises:
        AutoAuthenticationError: 수동 인증 실패 시
    """
    logger.info("🌐 Starting manual browser authentication...")

    print("\n" + "="*60)
    print("🔐 SCHWAB API AUTHENTICATION REQUIRED")
    print("="*60)
    print("자동 인증을 위해 브라우저 인증이 필요합니다.")
    print()
    print("진행 과정:")
    print("1. 브라우저가 자동으로 열립니다")
    print("2. Schwab 계정으로 로그인하세요")
    print("3. 애플리케이션 권한을 승인하세요")
    print("4. 토큰이 자동으로 저장됩니다")
    print("5. 이후 자동 인증이 가능합니다")
    print()
    print("⚠️  주의: SSL 경고가 나타날 수 있지만 정상입니다")
    print("="*60)

    # 사용자 확인
    try:
        response = input("\n브라우저 인증을 시작하시겠습니까? (y/n): ").strip().lower()
        if response != 'y':
            raise AutoAuthenticationError("User cancelled manual authentication")
    except KeyboardInterrupt:
        raise AutoAuthenticationError("Authentication cancelled by user")

    try:
        # 수동 인증 스크립트 실행
        manual_auth_script = Path(__file__).parent.parent.parent / "tests" / "manual" / "manual_auth_test.py"

        if not manual_auth_script.exists():
            raise AutoAuthenticationError(f"Manual auth script not found: {manual_auth_script}")

        print("\n🚀 브라우저 인증을 시작합니다...")
        print("(브라우저가 열리지 않으면 수동으로 인증 과정을 진행하세요)")

        # 새로운 프로세스에서 인증 스크립트 실행
        result = subprocess.run(
            [sys.executable, str(manual_auth_script)],
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )

        if result.returncode == 0:
            print("✅ 브라우저 인증이 완료되었습니다!")

            # 토큰 파일 확인
            token_path = Path(settings.schwab_token_file)
            if token_path.exists():
                print(f"✅ 토큰이 저장되었습니다: {settings.schwab_token_file}")

                # 서비스 재초기화
                success = await service.initialize()
                if success and service.is_authenticated():
                    print("✅ 인증이 성공적으로 완료되었습니다!")
                    return
                else:
                    raise AutoAuthenticationError("Authentication verification failed")
            else:
                raise AutoAuthenticationError("Token file not created")
        else:
            error_msg = result.stderr if result.stderr else "Unknown error"
            raise AutoAuthenticationError(f"Manual authentication script failed: {error_msg}")

    except subprocess.TimeoutExpired:
        raise AutoAuthenticationError("Manual authentication timeout (5 minutes)")
    except Exception as e:
        logger.error(f"Manual authentication failed: {e}")
        raise AutoAuthenticationError(f"Manual authentication failed: {e}")


async def _check_token_validity(settings: Settings) -> bool:
    """
    기존 토큰의 유효성 확인

    Args:
        settings: 애플리케이션 설정

    Returns:
        토큰 유효성 여부
    """
    try:
        token_path = Path(settings.schwab_token_file)

        if not token_path.exists():
            logger.info("No existing token file found")
            return False

        # 임시 서비스로 토큰 검증
        temp_service = SchwabAPIService(
            app_key=settings.schwab_app_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_callback_url,
            token_file=settings.schwab_token_file,
            config=settings.api_config
        )

        success = await temp_service.initialize()
        await temp_service.close()

        if success:
            logger.info("✅ Existing token is valid")
            return True
        else:
            logger.warning("❌ Existing token is invalid")
            return False

    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return False


async def close_shared_context(context: Dict[str, Any]) -> None:
    """
    SharedContext 리소스 정리

    Args:
        context: 정리할 SharedContext
    """
    logger.info("Closing SharedContext...")

    try:
        # Schwab 서비스 정리
        if 'schwab_service' in context and context['schwab_service']:
            await context['schwab_service'].close()
            logger.info("Schwab service closed")

        # 데이터베이스 연결 정리
        if 'db_pool' in context and context['db_pool']:
            await context['db_pool'].close()
            logger.info("Database pool closed")

        logger.info("SharedContext closed successfully")

    except Exception as e:
        logger.error(f"Error closing SharedContext: {e}")