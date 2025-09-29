"""
Pytest 설정 및 공통 픽스처

모든 테스트에서 사용할 수 있는 공통 설정과 픽스처를 정의합니다.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from autotrading.config.settings import APIConfig, Settings, Environment


@pytest.fixture
def test_api_config():
    """테스트용 API 설정"""
    return APIConfig(
        rate_limit_per_minute=60,  # 테스트용으로 낮게 설정
        rate_limit_burst=5,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=5,
        retry_max_attempts=2,
        connect_timeout=5,
        read_timeout=10,
        total_timeout=15
    )


@pytest.fixture
def test_settings(test_api_config):
    """테스트용 전체 설정"""
    return Settings(
        environment=Environment.DEVELOPMENT,
        debug=True,
        schwab_app_key="TEST_APP_KEY",
        schwab_app_secret="TEST_APP_SECRET",
        schwab_callback_url="https://localhost:8182/callback",
        schwab_token_file="test_tokens.json",
        database_url="postgresql://test:test@localhost:5432/test_db",
        api_config=test_api_config
    )


@pytest.fixture
def temp_token_file():
    """임시 토큰 파일"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name

    yield temp_path

    # 정리
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_token_data():
    """Mock 토큰 데이터"""
    return {
        "token": {
            "access_token": "mock_access_token_12345678901234567890",
            "refresh_token": "mock_refresh_token_09876543210987654321",
            "expires_in": 1800,
            "token_type": "Bearer",
            "scope": "api"
        },
        "creation_timestamp": 1640995200.0,
        "refresh_timestamp": 1640995200.0
    }


@pytest.fixture
def mock_schwab_client():
    """Mock Schwab 클라이언트"""
    client = Mock()

    # 기본 응답 설정
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "ok"}

    client.get_user_preferences.return_value = response
    client.get_quotes.return_value = response
    client.get_price_history.return_value = response
    client.get_account.return_value = response
    client.place_order.return_value = response

    return client


@pytest.fixture
def mock_market_data():
    """Mock 시장 데이터"""
    return {
        "AAPL": {
            "candles": [
                {
                    "datetime": 1640995200000,  # 2022-01-01 00:00:00 UTC
                    "open": 150.0,
                    "high": 155.0,
                    "low": 149.0,
                    "close": 154.0,
                    "volume": 1000000
                },
                {
                    "datetime": 1640995260000,  # 2022-01-01 00:01:00 UTC
                    "open": 154.0,
                    "high": 156.0,
                    "low": 153.0,
                    "close": 155.5,
                    "volume": 950000
                }
            ]
        }
    }


@pytest.fixture
def mock_quotes_data():
    """Mock 실시간 시세 데이터"""
    return {
        "AAPL": {
            "symbol": "AAPL",
            "lastPrice": 154.50,
            "bidPrice": 154.25,
            "askPrice": 154.75,
            "bidSize": 100,
            "askSize": 200,
            "totalVolume": 50000000,
            "quoteTimeInLong": 1640995200000
        },
        "GOOGL": {
            "symbol": "GOOGL",
            "lastPrice": 2500.00,
            "bidPrice": 2499.50,
            "askPrice": 2500.50,
            "bidSize": 50,
            "askSize": 75,
            "totalVolume": 25000000,
            "quoteTimeInLong": 1640995200000
        }
    }


@pytest.fixture
def mock_account_data():
    """Mock 계좌 데이터"""
    return {
        "securitiesAccount": {
            "accountNumber": "123456789",
            "type": "MARGIN",
            "currentBalances": {
                "liquidationValue": 100000.0,
                "cashBalance": 50000.0,
                "availableFunds": 45000.0,
                "buyingPower": 90000.0,
                "equity": 100000.0,
                "longMarketValue": 50000.0,
                "shortMarketValue": 0.0,
                "totalLongValue": 50000.0
            },
            "initialBalances": {
                "totalLongValue": 48000.0
            },
            "positions": [
                {
                    "instrument": {
                        "symbol": "AAPL",
                        "assetType": "EQUITY",
                        "cusip": "037833100"
                    },
                    "longQuantity": 100.0,
                    "averagePrice": 150.0,
                    "marketValue": 15450.0,
                    "currentPrice": 154.50,
                    "currentDayProfitLoss": 450.0,
                    "currentDayProfitLossPercentage": 3.0
                }
            ],
            "isDayTrader": False,
            "isClosingOnlyRestricted": False
        }
    }


@pytest.fixture
def sample_symbols():
    """테스트용 심볼 목록"""
    return ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]


@pytest.fixture
def populated_token_file(temp_token_file, mock_token_data):
    """토큰 데이터가 있는 임시 파일"""
    with open(temp_token_file, 'w') as f:
        json.dump(mock_token_data, f)

    return temp_token_file


# 테스트 환경 설정
def pytest_configure(config):
    """Pytest 설정"""
    # 테스트 마커 등록
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )
    config.addinivalue_line(
        "markers", "auth: Authentication related tests"
    )


# 테스트 세션 시작/종료 훅
def pytest_sessionstart(session):
    """테스트 세션 시작 시 실행"""
    print("\nStarting Autotrading test session...")


def pytest_sessionfinish(session, exitstatus):
    """테스트 세션 종료 시 실행"""
    if exitstatus == 0:
        print("All tests passed!")
    else:
        print("Some tests failed.")


# 테스트 함수별 설정
def pytest_runtest_setup(item):
    """각 테스트 실행 전 설정"""
    # 특정 마커가 있는 테스트의 경우 추가 설정
    if "slow" in item.keywords:
        pytest.skip("Slow test skipped (use --slow to run)")


# 커스텀 마커 검증
def pytest_collection_modifyitems(config, items):
    """테스트 수집 후 항목 수정"""
    # --slow 옵션이 없으면 slow 테스트 건너뛰기
    if not config.getoption("--slow", default=False):
        skip_slow = pytest.mark.skip(reason="need --slow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)