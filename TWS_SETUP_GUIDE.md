# TWS Setup Guide for Phase 2 Testing

## 현재 상황
- **Phase 2 IB API 구현 완료**: ✅
- **TWS 연결 테스트**: ❌ (TWS not running)

## TWS 설정 가이드

### 1. TWS 다운로드 및 설치
1. Interactive Brokers 웹사이트에서 TWS 다운로드
2. Paper Trading 계정으로 로그인

### 2. API 설정 (중요!)
1. **TWS 메뉴**: File → Global Configuration → API → Settings
2. **설정 항목**:
   - ✅ Enable ActiveX and Socket Clients
   - Socket port: `7497` (TWS 기본값)
   - ✅ Create API message log file
   - Master API client ID: 비워두기

3. **Precautionary Settings** 탭:
   - ✅ Bypass Order Precautions for API Orders
   - Read-Only API: ❌ (체크 해제)

4. **Trusted IP Addresses**:
   - Add: `127.0.0.1`

### 3. Paper Trading 확인
- TWS 우측 상단: "Paper Trading" 표시 확인
- 실제 돈이 아닌 가상 자금으로 거래

### 4. 연결 테스트

#### 간단한 연결 확인
```bash
# TWS 실행 후
autotrading/venv/Scripts/python.exe autotrading/tests/test_phase2_ib_real.py
```

#### 예상 결과
```
[Test 1] Testing IB API Connection...
[PASS] Successfully connected to IB API!
   Connection state: connected
   Host: 127.0.0.1
   Port: 7497
```

## 현재 Phase 2 구현 상태

### ✅ 완료된 구성 요소

1. **Connection Manager** (`broker/connection_manager.py`)
   - 자동 재연결 로직
   - 헬스 체크 (30초 간격)
   - 연결 상태 관리

2. **Contract Factory** (`broker/contracts.py`)
   - ES, NQ, YM, RTY 등 주요 선물 정의
   - 틱 값 계산
   - 마진 계산

3. **IB Client** (`broker/ib_client.py`)
   - 마켓 데이터 스트리밍
   - 주문 실행 (Market, Limit, Bracket)
   - 포지션 관리

4. **테스트 파일들**
   - `test_ib_simple.py`: 기본 기능 검증 ✅
   - `test_phase2_ib_real.py`: 실제 API 연결 테스트
   - `test_phase2_mock.py`: Mock 기반 단위 테스트

## 다음 단계

### TWS 연결 후 테스트 순서
1. **연결 테스트**: TWS API 연결 확인
2. **계정 정보**: Paper Trading 계정 정보 조회
3. **마켓 데이터**: ES 실시간 데이터 구독
4. **히스토리컬 데이터**: 과거 데이터 요청
5. **포지션 조회**: 현재 포지션 확인
6. **Paper 주문**: 테스트 주문 실행

### Phase 3 준비 사항
- Tick-to-Bar aggregation 시스템
- Strategy 통합
- Risk Management 통합
- 실시간 거래 시뮬레이션

## 트러블슈팅

### 연결 실패 시
1. **포트 확인**: TWS는 7497, IB Gateway는 4001
2. **API 활성화**: TWS 설정에서 API 활성화 확인
3. **방화벽**: Windows 방화벽에서 TWS 허용
4. **로그 확인**: TWS API 로그 파일 확인

### 일반적인 오류
- `[WinError 1225]`: TWS가 실행되지 않음
- `API connection failed`: API 설정이 비활성화됨
- `No market data permissions`: 데이터 구독 필요

## 연락처
- IB 기술 지원: https://www.interactivebrokers.com/en/support/
- API 문서: https://interactivebrokers.github.io/tws-api/