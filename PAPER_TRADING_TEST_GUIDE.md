# Paper Trading 통합 테스트 가이드

**작성일**: 2025-10-10
**목적**: IB Gateway Paper Trading 통합 테스트 실행 방법 및 주의사항

---

## ⚠️ 중요: Windows ProactorEventLoop 제한사항

Windows 환경에서 asyncio의 ProactorEventLoop는 **재사용 시 오류가 발생**할 수 있습니다.

### 문제 증상
```
AttributeError: 'NoneType' object has no attribute 'connect'
```

### 원인
- ib_async 라이브러리가 ProactorEventLoop를 사용
- 첫 번째 테스트 후 이벤트 루프가 종료되면서 내부 Proactor가 None으로 설정됨
- 두 번째 테스트부터 새 이벤트 루프를 생성해도 Proactor 재초기화 실패

### 해결방법

**✅ 권장: 테스트를 개별적으로 실행**
```bash
# 단일 테스트 실행
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection::test_connection_lifecycle -v

# 특정 클래스의 테스트만 실행
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection -k "test_connection_lifecycle" -v
```

**⚠️ 제한적: 전체 실행 시 첫 번째 테스트만 성공**
```bash
# 첫 번째 테스트만 통과하고 나머지는 에러 발생
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection -v
```

---

## 🚀 Paper Trading 테스트 실행 방법

### 1. IB Gateway Paper Trading 실행

**포트 설정**: 4002 (Paper Trading 전용 포트)

### 2. 환경 변수 확인

```bash
# autotrading/.env 확인
IB_PORT=4002  # Paper Trading
IB_CLIENT_ID=1
```

### 3. 테스트 실행

#### A. 단위 테스트 (IB Gateway 불필요)
```bash
# ContractFactory 테스트
autotrading/venv/Scripts/python.exe -m pytest -m "unit" -v

# 또는
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestContractFactory -v
```

**결과**: 6/6 테스트 통과

#### B. 개별 Paper Trading 테스트 (IB Gateway 필요)

**연결 테스트**
```bash
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection::test_connection_lifecycle -v
```

**헬스 체크 테스트**
```bash
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection::test_health_check -v
```

**계정 요약 테스트**
```bash
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingClient::test_account_summary -v
```

---

## 📋 테스트 목록

### TestPaperTradingConnection (연결 관리)
- ✅ `test_connection_lifecycle` - 연결 생명주기 검증 (단독 실행 성공)
- ⚠️ `test_health_check` - 헬스 체크 (단독 실행 필요)
- ⚠️ `test_connection_info` - 연결 정보 조회 (단독 실행 필요)

### TestContractFactory (계약 관리) - IB Gateway 불필요
- ✅ `test_es_contract_creation` - ES 계약 생성
- ✅ `test_contract_specs` - 계약 스펙 조회
- ✅ `test_tick_value_calculation` - 틱 값 계산
- ✅ `test_position_value_calculation` - 포지션 가치 계산
- ✅ `test_margin_requirements` - 마진 요구사항
- ✅ `test_continuous_futures` - 연속 선물 계약

### TestPaperTradingClient (클라이언트 기능)
- ⚠️ `test_client_connection` - 클라이언트 연결 (단독 실행 필요)
- ⚠️ `test_account_summary` - 계정 요약 (단독 실행 필요)
- ⚠️ `test_positions` - 포지션 조회 (단독 실행 필요)
- ⚠️ `test_market_data_subscription` - 마켓 데이터 구독 (단독 실행 필요)
- ⚠️ `test_historical_data` - 히스토리컬 데이터 (단독 실행 필요)

### TestPaperTradingOrders (주문 실행)
- ⚠️ `test_market_order_lifecycle` - 시장가 주문 (단독 실행 필요)
- ⚠️ `test_limit_order` - 지정가 주문 (단독 실행 필요)
- ⚠️ `test_bracket_order` - 브래킷 주문 (단독 실행 필요)

### TestEdgeCases (엣지 케이스)
- ✅ `test_invalid_symbol` - 잘못된 심볼 (IB Gateway 불필요)
- ⚠️ `test_duplicate_subscription` - 중복 구독 (단독 실행 필요)
- ⚠️ `test_connection_resilience` - 연결 복원력 (단독 실행 필요)

---

## 🔍 테스트 결과 예시

### ✅ 성공 케이스
```
tests\test_paper_trading.py::TestPaperTradingConnection::test_connection_lifecycle PASSED
```

**로그 확인**:
- `Event bus started`
- `IBConnectionManager initialized for 127.0.0.1:4002`
- `Connecting to IB API at 127.0.0.1:4002`
- `Connected`
- `Logged on to server version 178`
- `Successfully connected to IB API`

### ❌ 실패 케이스 (연속 실행 시)
```
tests\test_paper_trading.py::TestPaperTradingConnection::test_health_check ERROR
AttributeError: 'NoneType' object has no attribute 'connect'
```

**원인**: Windows ProactorEventLoop 재사용 문제

**해결**: 테스트를 개별적으로 실행

---

## 💡 모범 사례

### 1. 개발 단계
```bash
# 1. 단위 테스트 먼저 실행 (빠름, IB Gateway 불필요)
autotrading/venv/Scripts/python.exe -m pytest -m "unit" -v

# 2. 특정 통합 테스트만 검증
autotrading/venv/Scripts/python.exe -m pytest tests/test_paper_trading.py::TestPaperTradingConnection::test_connection_lifecycle -v
```

### 2. 전체 검증
```bash
# 각 테스트를 스크립트로 순차 실행
$tests = @(
    "TestPaperTradingConnection::test_connection_lifecycle",
    "TestPaperTradingConnection::test_health_check",
    "TestPaperTradingConnection::test_connection_info"
)

foreach ($test in $tests) {
    Write-Host "Testing: $test"
    autotrading/venv/Scripts/python.exe -m pytest "tests/test_paper_trading.py::$test" -v
    Start-Sleep -Seconds 2
}
```

### 3. CI/CD 환경
```yaml
# GitHub Actions 예시
- name: Run Paper Trading Tests
  run: |
    pytest tests/test_paper_trading.py::TestPaperTradingConnection::test_connection_lifecycle -v
    sleep 2
    pytest tests/test_paper_trading.py::TestPaperTradingClient::test_account_summary -v
  env:
    IB_PORT: 4002
```

---

## 🐛 알려진 이슈

### Issue #1: ProactorEventLoop 재사용 오류
- **증상**: 두 번째 테스트부터 `AttributeError: 'NoneType' object has no attribute 'connect'`
- **해결**: 테스트를 개별적으로 실행
- **근본 원인**: ib_async 라이브러리와 Windows ProactorEventLoop 호환성 문제
- **장기 해결책**: pytest-xdist를 사용한 프로세스 분리 (향후 고려)

### Issue #2: 테스트 간 대기 시간
- **증상**: 빠른 연속 테스트 시 IB Gateway 연결 실패
- **해결**: 테스트 간 1-2초 대기
- **원인**: IB Gateway의 연결 제한 및 정리 시간 필요

---

## ✅ 검증 체크리스트

**테스트 실행 전**:
- [ ] IB Gateway Paper Trading 실행 중 (포트 4002)
- [ ] autotrading/.env에 IB_PORT=4002 설정됨
- [ ] venv 가상환경 활성화됨

**테스트 실행**:
- [ ] 단위 테스트 먼저 실행 (6/6 통과 확인)
- [ ] Paper Trading 통합 테스트는 개별 실행
- [ ] 각 테스트 간 1-2초 대기

**테스트 성공 확인**:
- [ ] "Successfully connected to IB API" 로그 확인
- [ ] "PASSED" 상태 확인
- [ ] 에러 메시지 없음

---

## 📞 문제 해결

### Q: IB Gateway 연결 실패
```
pytest.skip("IB Gateway not running - skipping test")
```
**A**: IB Gateway Paper Trading이 포트 4002에서 실행 중인지 확인

### Q: 'NoneType' object has no attribute 'connect'
```
AttributeError: 'NoneType' object has no attribute 'connect'
```
**A**: 테스트를 개별적으로 실행 (연속 실행 불가)

### Q: 계정 정보 조회 실패
```
assert 'account_id' in summary
AssertionError
```
**A**: IB Gateway에 로그인되었는지 확인, Paper Trading 계정 활성화 확인

---

**작성자**: Claude Code
**업데이트**: 2025-10-10
**다음 업데이트**: ProactorEventLoop 이슈 해결 시
