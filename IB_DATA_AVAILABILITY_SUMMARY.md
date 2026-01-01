# IB Historical Data Availability - 1 Minute Bars

테스트 일시: 2025-10-13
계약: ES (E-mini S&P 500) 선물 front month (ESZ5, 만기: 2025-12-19)
IB API 포트: 4002 (Paper Trading Gateway)

## 테스트 결과

| Duration | Description | Bars Count | Status | Date Range | Coverage (days) |
|----------|-------------|------------|--------|------------|-----------------|
| 1 D | 1 day | 369 | ✓ | 2025-10-12 ~ 2025-10-12 | 0.3 |
| 2 D | 2 days | 1,749 | ✓ | 2025-10-09 ~ 2025-10-12 | 3.3 |
| 1 W | 1 week | 5,889 | ✓ | 2025-10-06 ~ 2025-10-12 | 6.3 |
| 2 W | 2 weeks | 12,789 | ✓ | 2025-09-29 ~ 2025-10-12 | 13.3 |
| **1 M** | **1 month** | **27,969** | **✓** | **2025-09-14 ~ 2025-10-12** | **28.3** |
| 2 M | 2 months | - | ✗ Timeout | - | - |
| 3 M+ | 3+ months | - | ✗ Timeout | - | - |

## 결론

### 최대 가용 기간
- **1개월 (1 M)**: 27,969 bars
- **약 28일** 동안의 데이터
- **거래일 기준**: 약 72일 (27,969 / 390 분/일)

### 백테스팅 권장사항

#### 1. 초기화 기간
```python
# Adaptive Strategy Manager 초기화에 사용
duration_str = "1 M"  # 1 month
expected_bars = 27,969  # ~72 trading days worth
```

#### 2. 백테스팅 전략
1. **Phase 4 초기화**:
   - 1개월 (27,969 bars) 전체를 사용하여 초기 스코어 생성
   - 모든 트리거의 regime별/시간대별 성과 계산
   - Exponential decay (lambda=0.1)로 최근 데이터에 가중치

2. **Rolling Window 백테스트**:
   - 초기화가 완료되면 실시간 시뮬레이션 시작
   - 매 bar마다 virtual signal tracking
   - 스코어 지속 업데이트

3. **데이터 더 필요하면**:
   - IB 제한: Paper/Live 계정 모두 1개월까지만 1분봉 제공
   - 장기 백테스트 필요시: 데이터 vendor 사용
     - Norgate Data
     - AlgoSeek
     - Databento
     - QuantConnect

#### 3. 구현 예시
```python
from autotrading.strategy import AdaptiveStrategyManager
from autotrading.broker import IBClient

# Get 1 month of historical data
bars = await ib_client.request_historical_bars(
    symbol="ES",
    duration="1 M",
    bar_size="1 min"
)

# Initialize strategy with historical data
strategy_manager = AdaptiveStrategyManager(
    triggers=[...],
    account_balance=100000,
    risk_percentage=0.02
)

# Initialize from backtest
strategy_manager.initialize_from_backtest(bars)

# Now ready for live/paper trading with initialized scores
```

## IB API 제한사항

### Historical Data 제한
- **1분봉**: 최대 30일 (IB documentation)
- **실제 테스트**: 28일 성공, 2개월부터 timeout
- **Paper Trading**: Live 계정과 동일한 데이터 접근
- **Data Subscription**: ES futures 데이터 구독 필요

### 참고 문서
- IB API Historical Data Limitations: https://www.interactivebrokers.com/en/software/api/apiguide/tables/historical_data_limitations.htm
- ES Futures Specs: https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.html

## 다음 단계

1. **Phase 4 코드 수정**:
   - `AdaptiveStrategyManager.initialize_from_backtest()` 메서드 확인
   - Duration 파라미터 "1 M" 사용하도록 설정

2. **전체 백테스트 실행**:
   - 1개월 데이터로 초기화
   - 모든 트리거의 성과 검증
   - Regime/시간대별 스코어 분석

3. **Live/Paper Trading 전환**:
   - 초기화된 스코어로 실시간 거래 시작
   - Virtual signal tracking 계속 진행
   - 스코어 동적 업데이트

## Technical Notes

### 거래시간 고려사항
- ES futures: 거의 24시간 거래 (일일 유지보수 시간 제외)
- 1분봉 기준: 약 390 bars/trading day (일반 주식시장 기준)
- Futures 24h 거래: 약 1,380 bars/day (23시간 × 60분)
- 실제 데이터: 27,969 bars / 28 days ≈ 999 bars/day
  - 유지보수 시간, 주말 제외된 값

### 데이터 품질
- IB 제공 데이터: 높은 품질
- Paper Trading 계정: 실제 시장 데이터 사용
- Delayed data vs Real-time: 구독 수준에 따라 다름
