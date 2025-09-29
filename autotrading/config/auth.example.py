"""
Schwab API 인증 설정 템플릿

이 파일을 auth.py로 복사하고 실제 값으로 수정하세요.
auth.py는 gitignore되어 안전하게 관리됩니다.

설정 방법:
1. 이 파일을 auth.py로 복사
2. YOUR_*_HERE 값들을 실제 Schwab API 정보로 변경
3. 데이터베이스 연결 정보도 실제 값으로 변경

Schwab API 키 발급:
- https://developer.schwab.com/ 에서 앱 등록
- App Key와 App Secret 생성
- Callback URL 설정 (개발 시 localhost 사용)
"""

from typing import Dict, Any


# Schwab API 인증 정보
SCHWAB_CONFIG: Dict[str, Any] = {
    "app_key": "YOUR_APP_KEY_HERE",
    "app_secret": "YOUR_APP_SECRET_HERE",
    "callback_url": "https://localhost:8080/callback",
    "token_file": "tokens.json",

    # API 엔드포인트 (일반적으로 변경할 필요 없음)
    "base_url": "https://api.schwabapi.com",
    "auth_url": "https://api.schwabapi.com/oauth/authorize",
    "token_url": "https://api.schwabapi.com/oauth/token",
}

# 데이터베이스 연결 정보
DATABASE_CONFIG: Dict[str, Any] = {
    "url": "postgresql://username:password@localhost:5432/autotrading",
    "host": "localhost",
    "port": 5432,
    "database": "autotrading",
    "username": "autotrading",
    "password": "your_password_here",

    # 연결 풀 설정
    "min_connections": 5,
    "max_connections": 20,
    "connection_timeout": 30,
}

# Redis 설정 (선택적)
REDIS_CONFIG: Dict[str, Any] = {
    "url": "redis://localhost:6379/0",
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": None,  # 패스워드가 있다면 설정
}

# 개발 환경 설정
ENVIRONMENT_CONFIG: Dict[str, Any] = {
    "environment": "development",  # development, staging, production
    "debug": True,
    "log_level": "DEBUG",

    # 타임존 설정
    "timezone": "UTC",

    # 기본 거래 심볼들
    "default_symbols": ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"],
}

# 보안 설정
SECURITY_CONFIG: Dict[str, Any] = {
    # API 요청 제한
    "api_rate_limit": 120,  # 분당 요청 수
    "request_timeout": 30,  # 초

    # 세션 관리
    "session_timeout": 3600,  # 초 (1시간)
    "token_refresh_margin": 300,  # 토큰 만료 5분 전 갱신

    # 로깅 보안
    "mask_sensitive_data": True,
    "log_api_requests": False,  # 프로덕션에서는 False 권장
}