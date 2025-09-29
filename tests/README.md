# Autotrading Tests

이 디렉토리는 autotrading 시스템의 모든 테스트를 포함합니다.

## 📁 Directory Structure

```
tests/
├── README.md                    # 이 파일
├── unit/                        # 단위 테스트
│   ├── test_authentication.py   # 인증 관련 단위 테스트
│   └── test_schwab_service.py   # SchwabAPIService 단위 테스트
├── integration/                 # 통합 테스트
│   └── test_system_integration.py # 전체 시스템 통합 테스트
└── manual/                      # 수동 테스트
    └── manual_auth_test.py      # 브라우저 인증 테스트
```

## 🧪 Test Categories

### 1. Unit Tests (`tests/unit/`)
개별 컴포넌트의 기능을 검증하는 단위 테스트

**실행 방법:**
```bash
# 모든 단위 테스트 실행
python -m pytest tests/unit/ -v

# 특정 테스트 파일 실행
python -m pytest tests/unit/test_authentication.py -v

# 커버리지와 함께 실행
python -m pytest tests/unit/ -v --cov=autotrading
```

**포함된 테스트:**
- `test_authentication.py`: 인증 플로우, 토큰 관리, 헬스 체크 (17 tests)
- `test_schwab_service.py`: API 서비스 기본 기능, 에러 핸들링

### 2. Integration Tests (`tests/integration/`)
여러 컴포넌트 간의 상호작용을 검증하는 통합 테스트

**실행 방법:**
```bash
# 통합 테스트 실행
python -m pytest tests/integration/ -v

# 특정 시나리오 테스트
python -m pytest tests/integration/test_system_integration.py::TestSystemIntegration::test_market_data_collection_flow -v
```

**포함된 테스트:**
- SharedContext 초기화 및 통합
- 시장 데이터 수집 플로우
- 트레이딩 플로우 (계좌 조회 → 포지션 계산 → 주문 실행)
- 헬스 모니터링 및 통계
- 동시 작업 및 에러 시나리오

### 3. Manual Tests (`tests/manual/`)
사용자 상호작용이 필요한 수동 테스트

**실행 방법:**
```bash
# 수동 브라우저 인증 테스트
cd tests/manual
python manual_auth_test.py
```

**포함된 테스트:**
- `manual_auth_test.py`: 실제 Schwab 계정으로 OAuth 인증

## 🚀 Quick Start

### 전체 테스트 실행
```bash
# 모든 자동화된 테스트 실행
python -m pytest tests/unit/ tests/integration/ -v

# 커버리지 리포트와 함께
python -m pytest tests/unit/ tests/integration/ -v --cov=autotrading --cov-report=html
```

### 개별 컴포넌트 테스트
```bash
# 인증 기능만 테스트
python -m pytest tests/unit/test_authentication.py -v

# 시스템 통합 테스트만
python -m pytest tests/integration/test_system_integration.py -v
```

## 📊 Test Coverage

현재 테스트 커버리지:
- **SchwabAPIService**: 100% (인증, API 호출, 에러 핸들링)
- **Authentication Flow**: 100% (OAuth, 토큰 관리, 상태 확인)
- **System Integration**: 90% (SharedContext, 서비스 통합)
- **Error Scenarios**: 85% (Circuit breaker, Rate limiting, 장애 복구)

## 🔧 Test Configuration

### Pytest 설정 (`pyproject.toml`)
```toml
[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --strict-markers"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

### Mock 설정
모든 테스트는 실제 API 호출 없이 Mock을 사용합니다:
- `unittest.mock.patch`를 통한 schwab 라이브러리 Mock
- AsyncMock을 사용한 비동기 함수 Mock
- 임시 파일을 사용한 토큰 파일 테스트

## 🔒 Security Notes

### 테스트 환경 보안
- 모든 단위/통합 테스트는 실제 API 키 불필요
- Mock 데이터 사용으로 안전한 테스트 환경
- 임시 파일 자동 정리로 데이터 누출 방지

### 수동 테스트 주의사항
- `manual_auth_test.py`는 실제 API 키 필요
- `.env` 파일의 API 키가 Git에 커밋되지 않도록 주의
- 토큰 파일(`tokens.json`)도 `.gitignore`에 포함됨

## 🐛 Troubleshooting

### 일반적인 문제

**1. Import Error**
```bash
# 해결: 프로젝트 루트에서 실행
cd /path/to/Autotrading
python -m pytest tests/unit/test_authentication.py
```

**2. Async Test Issues**
```bash
# pytest-asyncio 설치 확인
pip install pytest-asyncio
```

**3. Mock 관련 오류**
```bash
# unittest.mock이 제대로 패치되는지 확인
# 테스트에서 정확한 모듈 경로 사용
```

## 📈 Adding New Tests

### 새로운 단위 테스트 추가
1. `tests/unit/` 디렉토리에 `test_[component].py` 파일 생성
2. pytest 및 asyncio 픽스처 사용
3. Mock을 통한 외부 의존성 제거
4. 성공/실패 시나리오 모두 테스트

### 새로운 통합 테스트 추가
1. `tests/integration/` 디렉토리에 테스트 추가
2. SharedContext를 사용한 실제 통합 시나리오
3. 여러 컴포넌트 간 상호작용 검증
4. 에러 처리 및 복구 시나리오 포함

### 테스트 네이밍 컨벤션
- 파일: `test_[component_name].py`
- 클래스: `Test[ComponentName]`
- 메서드: `test_[specific_functionality]`
- Async 테스트: `@pytest.mark.asyncio` 데코레이터 사용