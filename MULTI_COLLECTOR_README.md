# Multi-Symbol Continuous Data Collector

여러 선물 종목을 동시에 수집하는 시스템

## 지원 종목

### 📈 S&P 500 Futures
- **ES** - E-mini S&P 500 (standard)
- **MES** - Micro E-mini S&P 500 (1/10 size)

### 📊 NASDAQ Futures
- **NQ** - E-mini NASDAQ-100 (standard)
- **MNQ** - Micro E-mini NASDAQ-100 (1/10 size)

### 📉 Dow Jones Futures
- **YM** - E-mini Dow ($5) (standard)
- **MYM** - Micro E-mini Dow ($0.50)

### 📌 Russell 2000 Futures
- **RTY** - E-mini Russell 2000 (standard)
- **M2K** - Micro E-mini Russell 2000 (1/10 size)

## 실행 방법

### 1. 단일 종목 수집
```bash
python run_continuous_collector.py
```
- 종목 선택 메뉴에서 하나 선택

### 2. 멀티 종목 수집
```bash
python run_multi_collector.py
```

#### 수집 모드:
1. **All major indices** (ES, NQ, YM, RTY) - 추천!
2. **All symbols** (8개 전체)
3. **S&P 500 only** (ES, MES)
4. **NASDAQ only** (NQ, MNQ)
5. **Custom selection** (직접 선택)

## 작동 원리

### 병렬 수집
- 각 종목마다 독립적인 수집기 실행
- 각 수집기는 고유한 IB API client ID 사용
  - ES: clientId=1
  - NQ: clientId=2
  - YM: clientId=3
  - RTY: clientId=4

### 데이터 흐름
```
Symbol 1 (ES) → IB clientId=1 → Collector 1 → DB
Symbol 2 (NQ) → IB clientId=2 → Collector 2 → DB
Symbol 3 (YM) → IB clientId=3 → Collector 3 → DB
Symbol 4 (RTY) → IB clientId=4 → Collector 4 → DB
```

### 각 수집기 동작
1. 갭 필링 루프 (15초 검증)
2. 실시간 5초봉 스트리밍
3. 12개 모아서 1분봉 생성
4. DB 저장
5. 자동 재연결 및 복구

## 로그

- **파일**: `logs/multi_collector.log`
- **콘솔**: 실시간 출력
- 각 심볼별로 태그 구분: `[collector.ES]`, `[collector.NQ]`, ...

## 주의사항

1. **IB Gateway/TWS 설정**
   - API 연결 허용 필요
   - clientId 1-8 사용 가능하도록 설정

2. **시스템 리소스**
   - 8개 종목 동시 수집시 메모리 사용량 증가
   - 권장: 4개 종목 (ES, NQ, YM, RTY)

3. **시장 시간**
   - 일요일 17:00 CT ~ 금요일 16:00 CT
   - 매일 16:00-17:00 휴식 (자동 처리)

4. **데이터베이스**
   - PostgreSQL + TimescaleDB 필요
   - 각 종목의 데이터는 동일한 `market_data_1min` 테이블에 저장
   - `symbol` 컬럼으로 구분

## 예시 실행

```bash
PS C:\Users\linep\Autotrading> python run_multi_collector.py

======================================================================
Multi-Symbol Futures Continuous Data Collector
======================================================================

Select collection mode:
  1. All major indices (ES, NQ, YM, RTY)
  2. All symbols (8 symbols)
  3. S&P 500 only (ES, MES)
  4. NASDAQ only (NQ, MNQ)
  5. Custom selection

Enter choice (1-5, default=1): 1

✓ Selected symbols: ES, NQ, YM, RTY
✓ Total: 4 symbols

--- ES Iteration 1 ---
  [1/4] Filling gaps... Filled: 152 bars
  [2/4] Starting real-time streaming...
  [3/4] Collecting 5-sec bars for 15 seconds...
  [4/4] Verification: 3 5-sec bars received
  [OK] No gap detected (3 bars in 15s)

--- NQ Iteration 1 ---
  [1/4] Filling gaps... Filled: 148 bars
  [2/4] Starting real-time streaming...
  ...

[ALL SYMBOLS COLLECTING]
```

## 중지

- `Ctrl+C` 누르면 모든 수집기 안전하게 중지
- 각 수집기가 순차적으로 종료
- 연결 해제 후 종료

## 문제 해결

### "Unable to connect as the client id is already in use"
→ IB Gateway/TWS 재시작 또는 다른 client ID 범위 사용

### 특정 종목만 데이터 안 들어옴
→ 해당 종목의 시장 데이터 구독 확인

### 메모리 부족
→ 수집 종목 수 줄이기 (8개 → 4개)
