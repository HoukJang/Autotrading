# Paper Trading 전환 가이드

**작성일**: 2025-10-07
**목적**: Mock 테스트에서 IB Gateway Paper Trading 실제 테스트로 전환
**예상 효과**: 테스트 통과율 71% → 90%+

---

## 1. 전환 필요성

### 1.1 Mock 테스트의 한계
- **연결 상태 시뮬레이션 불완전**: isConnected() Mock이 실제 연결 상태를 재현하지 못함
- **API 메서드 미구현**: qualifyContractsAsync, reqCurrentTimeAsync 등
- **실제 동작 검증 불가**: 주문 실행, 계좌 정보, 포지션 조회
- **통과율 제약**: 41/58 (71%)

### 1.2 Paper Trading의 장점
- **실제 IB API 사용**: 모든 기능 완전 테스트
- **실제 동작 검증**: 주문 실행, 데이터 수신, 계좌 조회
- **프로덕션 준비**: 실제 환경과 동일한 테스트
- **예상 통과율**: 90%+ (52/58 이상)

### 1.3 전환 대상 테스트
| 카테고리 | Mock 통과 | Paper 예상 | 개선 |
|----------|-----------|------------|------|
| IB Client | 4/13 (31%) | 12/13 (92%) | +8 |
| Integration | 2/3 (67%) | 3/3 (100%) | +1 |
| Edge Cases | 16/21 (76%) | 19/21 (90%) | +3 |
| **합계** | **22/37** | **34/37** | **+12** |

---

## 2. 사전 준비

### 2.1 IB Gateway 설정

#### Step 1: IB Gateway 다운로드 및 설치
1. Interactive Brokers 웹사이트 접속
2. IB Gateway 최신 버전 다운로드
3. 설치 및 실행

#### Step 2: Paper Trading 계정 설정
1. IBKR Paper Trading 계정 생성 (무료)
2. 사용자명 및 비밀번호 확인
3. 계정 활성화

#### Step 3: IB Gateway 구성
1. **IB Gateway 실행**
   - Paper Trading 모드 선택
   - 사용자명/비밀번호 입력

2. **API 설정**
   - Edit → Global Configuration → API → Settings
   - "Enable ActiveX and Socket Clients" 체크
   - "Read-Only API" 체크 해제 (주문 실행 허용)
   - Socket Port: **4002** (Paper Trading 기본 포트)
   - Master API client ID: 1

3. **Trusted IPs 설정**
   - "Trusted IPs" → "127.0.0.1" 추가
   - "localhost" 추가

4. **연결 확인**
   - IB Gateway 로그인 완료
   - "API" 인디케이터 녹색 확인

### 2.2 환경 변수 설정

#### .env 파일 생성
```bash
# c:\Users\linep\Autotrading\.env
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=1
IB_PAPER_TRADING=true
LOG_LEVEL=DEBUG
```

#### 환경 변수 확인
```bash
# PowerShell
cd C:\Users\linep\Autotrading
cat .env
```

### 2.3 Python 패키지 확인
```bash
# 가상환경 활성화
autotrading\venv\Scripts\activate

# 필수 패키지 확인
pip list | grep -E "ib-async|pytest|pytest-asyncio"
```

---

## 3. 테스트 전환 절차

### 3.1 단계별 전환 계획

#### Phase 1: 연결 테스트 (5분)
**목표**: IB Gateway 연결 확인

```bash
# 연결 테스트만 실행
pytest tests/test_phase2_ib.py::TestIBConnectionManager::test_connection_lifecycle -v -s --tb=short
```

**예상 결과**:
- 연결 성공 로그 확인
- "Successfully connected to IB API" 메시지
- 테스트 통과

**실패 시 점검**:
1. IB Gateway 실행 확인
2. 포트 4002 확인
3. API 설정 확인 (Enable ActiveX and Socket Clients)

---

#### Phase 2: IB Client 개별 테스트 (30분)
**목표**: IB Client 기능별 검증

##### 2.1 Market Data 테스트
```bash
# 시장 데이터 구독
pytest tests/test_phase2_ib.py::TestIBClient::test_market_data_subscription -v -s --tb=short
```

**예상 결과**:
- ES 선물 구독 성공
- 틱 데이터 수신 확인

##### 2.2 Historical Data 테스트
```bash
# 히스토리 데이터 요청
pytest tests/test_phase2_ib.py::TestIBClient::test_historical_data_request -v -s --tb=short
```

**예상 결과**:
- 1일 1분봉 데이터 수신
- 바 데이터 형식 검증

##### 2.3 주문 실행 테스트
```bash
# 시장가 주문
pytest tests/test_phase2_ib.py::TestIBClient::test_market_order_execution -v -s --tb=short

# 지정가 주문
pytest tests/test_phase2_ib.py::TestIBClient::test_limit_order_execution -v -s --tb=short

# 브래킷 주문
pytest tests/test_phase2_ib.py::TestIBClient::test_bracket_order_execution -v -s --tb=short
```

**예상 결과**:
- 주문 ID 할당
- 주문 상태 업데이트 수신
- Paper Trading 계정에 주문 반영

##### 2.4 계좌 정보 테스트
```bash
# 포지션 조회
pytest tests/test_phase2_ib.py::TestIBClient::test_position_retrieval -v -s --tb=short

# 계좌 요약
pytest tests/test_phase2_ib.py::TestIBClient::test_account_summary -v -s --tb=short
```

**예상 결과**:
- 현재 포지션 리스트
- 계좌 잔고, Net Liquidation 값

---

#### Phase 3: 전체 IB Client 테스트 (10분)
```bash
# IB Client 전체 테스트
pytest tests/test_phase2_ib.py::TestIBClient -v --tb=short
```

**예상 결과**:
- 12/13 통과 (92%)
- 1개 실패 가능 (test_error_scenarios - 의도적 에러 테스트)

---

#### Phase 4: 통합 테스트 (15분)
```bash
# 통합 시나리오 테스트
pytest tests/test_phase2_ib.py::TestIntegrationScenarios -v --tb=short
```

**예상 결과**:
- test_complete_trading_workflow 통과
- test_connection_resilience 통과
- test_data_integrity_under_stress 통과

---

#### Phase 5: Edge Cases 재테스트 (20분)
```bash
# Edge Cases 전체
pytest tests/test_edge_cases.py -v --tb=short
```

**예상 결과**:
- 19/21 통과 (90%)
- 일부 Mock 전용 테스트는 여전히 실패 가능

---

#### Phase 6: 전체 테스트 + 커버리지 (30분)
```bash
# 전체 테스트 실행
pytest tests/ -v --cov=autotrading/broker --cov-report=term --cov-report=html:tests/coverage/html --tb=short
```

**예상 결과**:
- 52/58 통과 (90%)
- 커버리지: 85%+ (ib_client.py 커버리지 향상)

---

### 3.2 테스트 마커 활용

#### requires_tws 마커 사용
```python
# tests/test_phase2_ib.py
@pytest.mark.requires_tws
async def test_market_order_execution(self, ib_client):
    """실제 TWS/Gateway 연결 필요"""
    ...
```

#### 실행 방법
```bash
# TWS 필요 테스트만
pytest -m "requires_tws" -v

# TWS 불필요 테스트만 (Mock)
pytest -m "not requires_tws" -v
```

---

## 4. 문제 해결 가이드

### 4.1 연결 실패

#### 문제: "Connection refused"
```
ConnectionError: [Errno 10061] No connection could be made
```

**해결 방법**:
1. IB Gateway 실행 확인
2. 포트 번호 확인 (4002)
3. Firewall 설정 확인
   ```powershell
   # Windows Firewall 확인
   Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*IB*"}
   ```

#### 문제: "Already connected"
```
error: clientId 1 already in use
```

**해결 방법**:
1. 기존 연결 종료
2. 다른 Client ID 사용
   ```python
   # .env
   IB_CLIENT_ID=2
   ```
3. IB Gateway 재시작

---

### 4.2 API 설정 오류

#### 문제: "Not allowed to connect"
```
error: FA or IBroker account required
```

**해결 방법**:
1. API Settings 확인
   - "Enable ActiveX and Socket Clients" 체크
   - "Read-Only API" 체크 해제
2. Trusted IPs 확인
   - 127.0.0.1 추가
3. IB Gateway 재시작

---

### 4.3 주문 실행 오류

#### 문제: "Order rejected"
```
error 201: Order rejected - reason: ...
```

**해결 방법**:
1. Paper Trading 계정 잔고 확인
2. 주문 수량 조정 (1 계약으로 시작)
3. 시장 운영 시간 확인
   ```python
   # 테스트 전 시장 시간 확인
   from autotrading.broker.contracts import ContractFactory
   factory = ContractFactory()
   is_open = factory.is_market_open('ES')
   ```

#### 문제: "Invalid contract"
```
error 200: No security definition found for the request
```

**해결 방법**:
1. 계약 심볼 확인 (ES, NQ, YM 등)
2. 만기 월 확인 (연속 선물 사용 권장)
3. 거래소 확인 (CME, GLOBEX)

---

### 4.4 데이터 수신 오류

#### 문제: "Market data not subscribed"
```
error 354: Requested market data is not subscribed
```

**해결 방법**:
1. Paper Trading 계정 시장 데이터 권한 확인
2. Delayed data 사용
   ```python
   # ib_client.py
   self.ib.reqMarketDataType(3)  # Delayed data
   ```
3. 실시간 데이터 구독 신청

---

## 5. 성능 모니터링

### 5.1 연결 상태 모니터링
```python
# 연결 상태 확인 스크립트
import asyncio
from autotrading.broker.connection_manager import IBConnectionManager
from autotrading.core.event_bus import EventBus

async def monitor_connection():
    event_bus = EventBus()
    conn_mgr = IBConnectionManager(event_bus)

    try:
        await conn_mgr.connect()
        print(f"Connected: {conn_mgr.is_connected()}")
        print(f"Connection Info: {conn_mgr.get_connection_info()}")

        # Health check
        is_healthy = await conn_mgr.health_check()
        print(f"Health Check: {is_healthy}")

    finally:
        await conn_mgr.disconnect()

# 실행
asyncio.run(monitor_connection())
```

### 5.2 주문 실행 성능 측정
```python
# 주문 처리 시간 측정
import time
from decimal import Decimal

async def measure_order_performance(ib_client):
    start = time.time()

    # 주문 실행
    order_id = await ib_client.place_market_order('ES', 1, 'BUY')

    elapsed = time.time() - start
    print(f"Order execution time: {elapsed:.3f}s")

    return elapsed
```

### 5.3 데이터 수신 레이턴시 측정
```python
# 틱 데이터 레이턴시 측정
from datetime import datetime

async def measure_tick_latency(ib_client):
    latencies = []

    async def on_tick(tick):
        now = datetime.now()
        latency = (now - tick.timestamp).total_seconds()
        latencies.append(latency)

    ib_client.add_tick_callback(on_tick)
    await ib_client.subscribe_market_data('ES')

    # 10초간 측정
    await asyncio.sleep(10)

    avg_latency = sum(latencies) / len(latencies)
    print(f"Average latency: {avg_latency:.3f}s")
```

---

## 6. 테스트 결과 검증

### 6.1 예상 결과
| Phase | Mock | Paper Trading | 개선 |
|-------|------|---------------|------|
| Connection Manager | 7/9 (78%) | 8/9 (89%) | +1 |
| IB Client | 4/13 (31%) | 12/13 (92%) | +8 |
| Integration | 2/3 (67%) | 3/3 (100%) | +1 |
| Edge Cases | 16/21 (76%) | 19/21 (90%) | +3 |
| **전체** | **41/58 (71%)** | **52/58 (90%)** | **+11** |

### 6.2 커버리지 향상
| 모듈 | Mock | Paper Trading | 개선 |
|------|------|---------------|------|
| connection_manager.py | 91% | 95% | +4% |
| contracts.py | 90% | 92% | +2% |
| ib_client.py | 59% | 85% | +26% |
| **전체** | **76%** | **88%** | **+12%** |

---

## 7. 지속적 통합 (CI/CD)

### 7.1 GitHub Actions 설정
```yaml
# .github/workflows/test.yml
name: Paper Trading Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11

    - name: Install IB Gateway
      run: |
        # IB Gateway 설치 스크립트
        wget https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh
        chmod +x ibgateway-latest-standalone-linux-x64.sh
        ./ibgateway-latest-standalone-linux-x64.sh -q

    - name: Start IB Gateway
      run: |
        # IB Gateway 시작
        ibgateway &
        sleep 30  # 시작 대기

    - name: Install dependencies
      run: |
        pip install -r requirements.txt

    - name: Run tests
      env:
        IB_HOST: 127.0.0.1
        IB_PORT: 4002
        IB_CLIENT_ID: 1
      run: |
        pytest tests/ -v --cov=autotrading/broker
```

### 7.2 로컬 CI 시뮬레이션
```bash
# 로컬에서 CI 환경 재현
docker run -it --rm \
  -v $(pwd):/app \
  -e IB_HOST=host.docker.internal \
  -e IB_PORT=4002 \
  python:3.11 \
  bash -c "cd /app && pip install -r requirements.txt && pytest tests/ -v"
```

---

## 8. 최적화 팁

### 8.1 테스트 속도 향상
1. **병렬 실행**
   ```bash
   # pytest-xdist 사용
   pip install pytest-xdist
   pytest tests/ -n 4  # 4개 프로세스 병렬
   ```

2. **선택적 실행**
   ```bash
   # 변경된 파일만 테스트
   pytest --lf  # last failed
   pytest --ff  # failed first
   ```

3. **캐시 활용**
   ```bash
   # pytest cache 사용
   pytest --cache-show
   pytest --cache-clear  # 필요시 캐시 삭제
   ```

### 8.2 리소스 관리
1. **연결 풀링**
   ```python
   # 여러 테스트에서 연결 재사용
   @pytest.fixture(scope="session")
   async def shared_ib_connection():
       conn_mgr = IBConnectionManager()
       await conn_mgr.connect()
       yield conn_mgr
       await conn_mgr.disconnect()
   ```

2. **데이터 캐싱**
   ```python
   # 히스토리 데이터 캐싱
   @pytest.fixture(scope="session")
   async def cached_historical_data(shared_ib_connection):
       bars = await shared_ib_connection.ib.request_historical_bars('ES', '1 D', '1 min')
       return bars
   ```

---

## 9. 체크리스트

### 9.1 전환 전 체크리스트
- [ ] IB Gateway 설치 완료
- [ ] Paper Trading 계정 생성
- [ ] API 설정 완료 (포트 4002, Trusted IPs)
- [ ] .env 파일 작성
- [ ] 가상환경 활성화
- [ ] IB Gateway 실행 및 로그인

### 9.2 전환 중 체크리스트
- [ ] Phase 1: 연결 테스트 통과
- [ ] Phase 2: IB Client 개별 테스트 통과 (8/9 이상)
- [ ] Phase 3: IB Client 전체 테스트 통과 (12/13)
- [ ] Phase 4: 통합 테스트 통과 (3/3)
- [ ] Phase 5: Edge Cases 재테스트 (19/21)
- [ ] Phase 6: 전체 테스트 90%+ 통과

### 9.3 전환 후 체크리스트
- [ ] 테스트 통과율 90%+ 달성
- [ ] 커버리지 85%+ 달성
- [ ] 주문 실행 검증 완료
- [ ] 계좌 정보 조회 검증 완료
- [ ] 성능 측정 완료
- [ ] 문서 업데이트

---

## 10. 다음 단계

### 10.1 Paper Trading 검증 완료 후
1. **프로덕션 준비**
   - Live 환경 단계적 전환 계획
   - 리스크 관리 시스템 구축
   - 모니터링 시스템 구축

2. **고급 기능 추가**
   - 알고리즘 트레이딩 전략
   - 백테스팅 시스템
   - 성능 분석 대시보드

3. **문서화**
   - API 문서 작성
   - 사용자 가이드 작성
   - 운영 매뉴얼 작성

---

## 11. 결론

### 11.1 기대 효과
- **테스트 통과율**: 71% → 90%+ (+19%)
- **커버리지**: 76% → 88%+ (+12%)
- **프로덕션 준비도**: 7/10 → 9/10

### 11.2 권장 사항
1. **즉시 실행**: Paper Trading 환경 전환
2. **단계적 검증**: Phase 1부터 순차 실행
3. **문제 해결**: 문제 발생 시 가이드 참조
4. **지속 모니터링**: 성능 및 안정성 추적

### 11.3 성공 기준
- [ ] 전체 테스트 90%+ 통과
- [ ] IB Client 테스트 92%+ 통과
- [ ] 주문 실행 정상 작동
- [ ] 데이터 수신 안정적
- [ ] 성능 측정 완료

**Paper Trading 전환을 통해 프로덕션 준비도를 크게 향상시킬 수 있습니다!**
