# Strategy Panel Discussion #21: Iteration 7 Post-Mortem -- Regime Weight 무효 발견 및 Iteration 8 제안

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Data Analyst)
**Context**: Iter 7 결과 분석, regime weight 변경 무효 원인 규명, 실제 제어 레버 식별, Sharpe 1.0 현실성 평가
**Decision**: PARAM_TUNE (2개 변경: rsi_mr ADX_MAX 조임 + rsi_mr base_risk 축소)

---

## 1. 중대 발견: Regime Weight 변경이 Batch Simulator에서 무효

### 문제의 본질

Iteration 7에서 `regime_detector.py`의 TREND regime rsi_mr 비중을 0.10 -> 0.00으로 변경했으나, **rsi_mr이 P1에서 19건 거래 (이전 Iter 6의 20건과 거의 동일)**했다.

**원인**: `batch_simulator.py`는 `regime_detector`를 사용하지 않는다.

```
Live System 경로:  Strategy -> RegimeDetector -> AllocationEngine -> 포지션
Batch Sim 경로:    Strategy -> batch_simulator 자체 sizing -> 포지션
                   (RegimeDetector 우회)
```

batch_simulator의 포지션 사이징은 독립적인 메커니즘을 사용한다:

| 메커니즘 | 변수명 | 위치 |
|---------|--------|------|
| 전략별 기본 리스크 | `_STRATEGY_BASE_RISK` | batch_simulator.py L83-88 |
| 전략별 GDR 임계값 | `_STRATEGY_GDR_THRESHOLDS` | batch_simulator.py L92-97 |
| 전략 자체 진입 필터 | `ADX_MAX`, ADX slope | rsi_mean_reversion.py L56, L157 |
| 전략별 SL/TP/hold | `_SL_ATR_MULT`, `_TP_ATR_MULT`, `_MAX_HOLD_DAYS` | exit_rules.py L37-58 |

**결론**: 20th panel의 "rsi_mr TREND 차단" 권고(regime_detector 변경)는 **백테스트에서 검증할 수 없는 변경**이었다. 라이브 시스템에서만 효과가 있다. 백테스트에서 rsi_mr을 제어하려면 전략 파일 자체(ADX_MAX, slope)나 batch_simulator 상수를 변경해야 한다.

---

## 2. Iteration 7 결과 분석

### Period 2 (2025-03 ~ 2026-02): +7.4%

| Strategy | Trades | WR | PF | PnL | Avg Hold |
|----------|--------|-----|------|--------|----------|
| breakout_momentum | 52 | - | 1.064 | +$648 | - |
| consecutive_down | 20 | - | 4.532 | +$3,952 | - |
| rsi_mean_reversion | 17 | - | 1.762 | +$2,587 | - |
| **Portfolio** | **89** | - | - | **+$7,187** | - |

### Period 1 (2024-03 ~ 2025-02): -3.0%

| Strategy | Trades | WR | PF | PnL | Avg Hold |
|----------|--------|-----|------|--------|----------|
| breakout_momentum | 44 | - | 1.035 | +$387 | - |
| consecutive_down | 16 | - | 0.629 | -$1,200 | - |
| rsi_mean_reversion | 19 | - | 0.500 | -$2,362 | - |
| **Portfolio** | **79** | - | - | **-$3,013** | - |

### 핵심 수치

| Metric | P1 | P2 | 목표 |
|--------|-----|-----|------|
| Total Return | -3.0% | +7.4% | 양 기간 양수 |
| Sharpe | 0.233 | 0.409 | >= 1.0 |
| rsi_mr PnL | -$2,362 (78% of loss) | +$2,587 | 손실 축소 |
| cons_down PnL | -$1,200 | +$3,952 | - |
| breakout PnL | +$387 | +$648 | - |

---

## 3. Panel Analysis

### Strat-4 (Data Analyst) -- ADX_MAX 18 트레이드오프 정량 분석

**질문: ADX_MAX를 23에서 18로 낮추면 어떻게 되는가?**

먼저 과거 데이터를 참조한다.

| Iteration | ADX_MAX | Slope 조건 | 결과 |
|-----------|---------|-----------|------|
| 14A | 20 | slope > 0 (엄격) | 6건, WR 0% -- 사실상 비활성화 |
| 15A | 23 | slope > 1.5 (적정) | 34건, WR 32.4%, PF 1.232 |
| Iter 7 | 23 | slope > 1.5 | P1: 19건, PF 0.500 / P2: 17건, PF 1.762 |

**14A의 실패 원인**: ADX_MAX=20이 아니라 **slope > 0이 주범**이었다. slope > 0은 "ADX가 조금이라도 상승하면 차단"이므로, 거의 모든 진입을 막았다. ADX_MAX=20 자체는 과도하지 않았을 수 있다.

**ADX_MAX=18 시나리오 추정**:

S&P 500 종목에서 ADX 분포:
- ADX < 15: 극단적 횡보. 전체의 ~5-10%
- ADX 15-20: 약한 추세/횡보. 전체의 ~15-20%
- ADX 20-25: 보통 추세. 전체의 ~25-30%
- ADX 25+: 강한 추세. 전체의 ~40-50%

ADX < 18인 종목은 전체의 ~10-15%. 현재 ADX < 23에서 진입하는 종목 대비 **50-60% 감소** 예상.

| 시나리오 | P1 rsi_mr 예상 거래수 | P1 rsi_mr 예상 PnL | P2 rsi_mr 예상 거래수 | P2 rsi_mr 예상 PnL |
|---------|---------------------|-------------------|---------------------|-------------------|
| ADX_MAX=23 (현재) | 19건 | -$2,362 | 17건 | +$2,587 |
| ADX_MAX=20 | ~12건 | -$1,200~-1,500 | ~11건 | +$1,600~1,800 |
| ADX_MAX=18 | ~7건 | -$500~-800 | ~6건 | +$800~1,000 |

**ADX_MAX=18의 문제점**:
1. P2에서 rsi_mr 수익이 +$2,587 -> +$800~1,000으로 급감 (-$1,600)
2. P1 손실 개선은 -$2,362 -> -$600 수준 (+$1,800)
3. Net 효과: +$200 정도로 거의 중립이면서, 전략이 사실상 비활성화됨
4. **6-7건으로는 통계적 유의성이 전혀 없다**. PF 계산 자체가 무의미

**결론: ADX_MAX=18은 rsi_mr을 제거하는 것과 거의 동일. 그럴 거면 차라리 전략을 제거하는 것이 깔끔하다.**

ADX_MAX=20이 더 나은 절충안이다. slope>1.5와 결합하면 14A의 과도한 차단 없이 적정 필터링이 가능하다.

---

### Strat-2 (Quant Analyst) -- 수학적 접근: 무엇이 Sharpe를 개선하는가?

**Sharpe 분해**:

```
Sharpe = (mean_daily_return * sqrt(252)) / (std_daily_return * sqrt(252))
       = mean_daily_return / std_daily_return * sqrt(252)
```

Sharpe를 올리려면:
- **mean_daily_return 증가**: 더 많이 벌거나 덜 잃는다
- **std_daily_return 감소**: 일별 수익률 변동을 줄인다

현재 포트폴리오의 Sharpe 저해 요인:

**P1 (Sharpe 0.233)**:
- rsi_mr이 -$2,362 손실. 이 손실이 집중된 날들에서 일별 수익률의 분산(variance)을 크게 키운다
- breakout +$387은 52건에 걸쳐 소액 분산. 변동성 기여가 작다
- cons_down -$1,200도 16건에 집중. 변동성 기여

**P2 (Sharpe 0.409)**:
- cons_down +$3,952가 20건에 집중. 양의 수익이지만 집중도가 높아 변동성도 큼
- rsi_mr +$2,587이 17건에 분산
- breakout +$648이 52건에 분산

**rsi_mr base_risk 축소의 Sharpe 효과**:

base_risk 0.01 -> 0.007 (30% 감소)이면:
- 포지션 크기가 30% 줄어듦
- 개별 거래 PnL이 30% 축소
- P1: -$2,362 * 0.7 = -$1,653 (개선 +$709)
- P2: +$2,587 * 0.7 = +$1,811 (손실 -$776)
- 합산: 거의 중립 (-$67)

하지만 **변동성 효과**가 핵심:
- rsi_mr의 큰 손실 거래(P1)의 진폭이 30% 줄어듦
- 일별 수익률의 표준편차가 감소
- 수익률은 거의 동일 -> Sharpe 개선

**이것이 base_risk 축소의 진짜 가치다: 수익을 유지하면서 변동성을 줄인다.**

---

### Strat-1 (Swing Trader) -- ADX_MAX 조정의 실전적 의미

**ADX_MAX=20 + slope>1.5의 실전적 해석**:

ADX < 20은 "시장이 방향성을 잡지 못한 상태". 이 구간에서 mean reversion이 작동하는 이유는 명확하다: 방향이 없으니 위아래로 왔다 갔다 하고, RSI 과매도 후 반등이 발생한다.

ADX 20-23 구간은 "약한 추세가 시작되는 전환 구간". 이 구간에서 mean reversion은:
- 때때로 작동: 추세가 아직 약해서 반등이 일어남
- 때때로 실패: 추세가 강화되면서 반등 없이 추가 하락

**P1(Bull market)에서 ADX 20-23 구간의 특성**:
- 개별 종목이 시장 전체 상승에 편승하여 ADX가 20 이상으로 올라가는 경우가 많음
- 이 종목들에서 RSI 과매도가 발생하면 "상승 추세 중 일시적 하락"이며, 5일 이내에 반등이 안 올 수 있음
- 결과: SL hit 또는 time_exit에서 손실

**결론**: ADX 20-23 구간은 rsi_mr에게 "위험한 경계 구간". 이 구간을 차단하면 P1 손실이 줄어든다.

---

### Strat-3 (Risk Manager) -- 복합 리스크 관리 설계

**2개 변경을 동시에 적용하는 이유**:

단일 변경만으로는 충분하지 않다.

**시나리오 A: ADX_MAX만 20으로 변경**
- P1 rsi_mr: ~12건, PnL ~-$1,200~-1,500
- P2 rsi_mr: ~11건, PnL ~+$1,600~1,800
- P1 개선: +$800~1,100
- P2 감소: -$800~1,000
- **Net: 거의 중립. P1이 여전히 마이너스**

**시나리오 B: base_risk만 0.007로 변경**
- P1 rsi_mr: 19건, PnL ~-$1,653
- P2 rsi_mr: 17건, PnL ~+$1,811
- P1 개선: +$709
- P2 감소: -$776
- **Net: 거의 중립. P1이 여전히 마이너스**

**시나리오 C: 둘 다 변경 (ADX_MAX=20 + base_risk=0.007)**
- P1 rsi_mr: ~12건, 각 거래 30% 축소 -> PnL ~-$840~-1,050
- P2 rsi_mr: ~11건, 각 거래 30% 축소 -> PnL ~+$1,120~1,260
- P1 개선: +$1,312~1,522
- P2 감소: -$1,327~1,467
- **Net: 중립이지만, P1 총 수익이 -$3,013 + $1,400 = ~-$1,600으로 개선**
- **변동성 감소 효과로 Sharpe 개선**

**중요: 두 변경의 효과가 곱셈적(multiplicative)이므로, 각각 단독보다 P1 최대 손실 거래의 진폭 축소 효과가 크다.**

---

## 4. Sharpe 1.0 도달 현실성 -- 솔직한 평가

### 패널 합의: 파라미터 튜닝만으로 Sharpe 1.0은 구조적으로 불가능

**수학적 근거:**

현재 시스템 특성:
- 연간 거래수: ~80건 (양 기간 평균)
- 보유 기간: 2-7일
- 전략 수: 3개
- 시그널 소스: 일간 바 (정보 해상도 낮음)
- 계좌 규모: $50K (포지션 사이징 제약)

Sharpe 1.0이 의미하는 것:
- 연간 수익률 = 연간 변동성 (무위험수익률 무시 시)
- 예: 15% 수익 / 15% 변동성 = Sharpe 1.0
- 예: 20% 수익 / 20% 변동성 = Sharpe 1.0

현재 P2(최선의 기간): +7.4% 수익, Sharpe 0.409
- 역산: 변동성 ≈ 18.1%
- Sharpe 1.0이 되려면: 수익률 18% 필요 (현재의 2.4배)

**왜 2.4배가 불가능한가:**

1. **거래 빈도의 한계**: 80건/년으로 수익률을 2.4배 올리려면 개별 거래당 수익이 2.4배 커야 함. 이미 RSI 30 + BB %B 0.05 같은 극단적 진입 조건을 사용 중. 더 좋은 진입을 찾기 어려움.

2. **변동성 바닥의 한계**: 일간 바 기반 시스템에서 일별 포트폴리오 변동성의 바닥은 개별 거래의 SL 크기에 의해 결정됨. SL을 줄이면 WR이 떨어져 수익률도 감소.

3. **분산(diversification)의 부족**: 3전략은 모두 S&P 500 일간 바에 기반. 상관관계가 높아 분산 효과 제한적.

4. **소형 계좌 제약**: $50K에서 ATR-based sizing을 하면 고가 종목(>$200)에서 포지션이 매우 작아 수익 기여가 미미.

### 현실적 목표 제안

| 목표 | 달성 가능성 | 필요 조건 |
|------|-----------|----------|
| Sharpe >= 1.0 | 구조적 불가능 | 전략 수 2배 이상 증가 + 멀티 타임프레임 + 분 단위 데이터 |
| Sharpe >= 0.6 | 어려움 | P1 손실 50% 이상 축소 + P2 유지 |
| Sharpe >= 0.4 (양 기간) | 가능 | P1을 breakeven 근처로 끌어올림 |
| Calmar >= 1.0 | 어려움 | MaxDD를 수익률 이하로 유지 |
| 양 기간 양수 수익 | 가능하나 보장 불가 | rsi_mr P1 손실 제거가 핵심 |

### 파라미터 튜닝의 천장(ceiling)

20번의 iteration을 통해 관찰된 패턴:

```
Iter 1-5: breakout SL/TP 조정 -> P1과 P2가 반복적으로 seesaw
Iter 6-7: 구조적 변경 시도 (regime weights) -> 실효 없음 (batch sim 경로 문제)
```

파라미터 공간 탐색은 이미 주요 축(ADX_MAX, SL, TP, trailing, GDR threshold)을 대부분 실험했다. 남은 파라미터 마진은 작다. **이 시스템의 파라미터 튜닝 천장은 Sharpe ~0.4-0.5 수준으로 추정한다.**

Sharpe 0.6 이상은 다음 중 하나가 필요하다:
1. 4번째 전략 추가 (비상관 수익원)
2. 멀티 타임프레임 (주간 바 + 일간 바)
3. 시장 레짐 기반 포트폴리오 비중 동적 조정 (batch_simulator 수준에서)
4. 진입 타이밍 개선 (분 단위 데이터)

---

## 5. Iteration 8 제안서

### 변경 사항 (2개, 실효성 확인된 레버만)

#### 변경 1: rsi_mr ADX_MAX 23 -> 20 [진입 필터 강화]

**대상 파일**: `autotrader/strategy/rsi_mean_reversion.py` L56

```python
# 현재
ADX_MAX = 23.0

# 변경
ADX_MAX = 20.0
```

**근거**:
- 14A에서 ADX_MAX=20이 실패한 것은 slope>0 때문이지 ADX_MAX=20 때문이 아님
- 현재 slope>1.5가 유지되므로, ADX_MAX=20 + slope>1.5는 이전에 테스트된 적 없는 새 조합
- ADX 20-23 구간은 "추세 전환 경계"로, rsi_mr에게 가장 위험한 구간
- P1(bull)에서 이 구간의 종목이 가장 많은 손실을 발생시킬 것으로 추정

**예상 영향**:

| | P1 | P2 |
|---|-----|-----|
| rsi_mr 거래수 | 19건 -> ~12건 (-37%) | 17건 -> ~11건 (-35%) |
| rsi_mr PnL | -$2,362 -> ~-$1,200~-1,500 | +$2,587 -> ~+$1,600~1,800 |
| Net 영향 | +$860~1,160 개선 | -$790~990 감소 |

**ADX_MAX=18을 권장하지 않는 이유**:
- 거래수가 ~7건으로 감소하여 전략으로서 통계적 의미 상실
- 사실상 전략 제거와 동일하지만 코드는 남아 있어 복잡성만 증가
- 전략 제거를 원하면 명시적으로 제거하는 것이 낫다

#### 변경 2: rsi_mr base_risk 0.01 -> 0.007 [포지션 축소]

**대상 파일**: `autotrader/backtest/batch_simulator.py` L84

```python
# 현재
_STRATEGY_BASE_RISK: dict[str, float] = {
    "rsi_mean_reversion": 0.01,          # 1%

# 변경
_STRATEGY_BASE_RISK: dict[str, float] = {
    "rsi_mean_reversion": 0.007,         # 0.7% (30% 축소)
```

**근거**:
- ADX_MAX 변경만으로는 P1 손실 개선이 부족 (여전히 -$1,200~-1,500)
- base_risk 축소는 진입 건수를 유지하면서 개별 거래 손실폭을 줄임
- 두 변경의 곱셈적 효과: 거래수 감소 * 포지션 축소 = P1 rsi_mr 손실 대폭 감소

**예상 영향** (변경 1과 복합 적용):

| | P1 | P2 |
|---|-----|-----|
| rsi_mr 거래수 | ~12건 (ADX_MAX 효과) | ~11건 (ADX_MAX 효과) |
| 개별 거래 규모 | 70% (base_risk 효과) | 70% (base_risk 효과) |
| rsi_mr PnL | ~-$840~-1,050 | ~+$1,120~1,260 |
| **Portfolio Total** | **~-$1,650~-1,860** (from -$3,013) | **~+$5,720~5,910** (from +$7,187) |
| **Total Return** | **~-1.6%** (from -3.0%) | **~+5.7%** (from +7.4%) |

**변동성 효과**:
- rsi_mr의 큰 손실 거래 진폭이 ~50% 축소 (거래수 * 사이즈 복합)
- 일별 수익률 표준편차 감소
- P1 Sharpe: 0.233 -> ~0.30 추정
- P2 Sharpe: 0.409 -> ~0.38 추정 (수익 감소 but 변동성도 감소)

### 변경하지 않는 것 (그리고 이유)

| Parameter | 현재값 | 유지 이유 |
|-----------|--------|---------|
| ADX_MAX -> 18 | - | 전략 사실상 비활성화. 제거할 거면 명시적으로 |
| ADX slope threshold 1.5 | 1.5 | 15A에서 검증된 적정값. 14A의 slope>0 실패 교훈 |
| breakout base_risk | 0.015 | breakout은 양 기간 모두 양수(+$387, +$648). 건드리지 않음 |
| breakout GDR threshold | (0.025, 0.05) | breakout이 GDR cascade를 겪는지 Iter 7에서 명확하지 않음. 데이터 부족 |
| cons_down 파라미터 | - | P2 핵심 수익원(+$3,952). 건드리면 seesaw 재발 위험 |
| exit_rules (SL/TP/hold) | - | Iter 7에서 변경 없었고, breakout TP 3.0은 Iter 7에서 이미 적용됨 |

---

## 6. Risk Assessment

### 변경 1 (ADX_MAX 20) 리스크

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| P2 rsi_mr 수익 과도 감소 | Medium | Medium (-$800~1,000) | cons_down이 P2 주 수익원(+$3,952). rsi_mr 감소 흡수 가능 |
| 14A 재현 (과도한 차단) | Low | High | slope 조건이 다름 (>1.5 vs >0). 14A와 동일하지 않음 |
| ADX 20-23 구간에 유효 진입 존재 | Medium | Low | 유효 진입이 있더라도, 이 구간의 손실 거래가 더 많으면 Net 양수 |

### 변경 2 (base_risk 0.007) 리스크

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| P2 수익 감소 | High (확실) | Medium (-$776) | 변동성 감소가 Sharpe 관점에서 보상 |
| GDR Tier 1 진입 지연 | Low (긍정적) | Positive | 개별 손실이 작아져 GDR 발동이 늦춰짐 |
| 수익 기회비용 | Medium | Low | 0.007 vs 0.01은 30% 차이. 극단적 변경이 아님 |

### Overfitting Assessment

| Change | Overfitting Risk | Rationale |
|--------|-----------------|-----------|
| ADX_MAX 23 -> 20 | Low | 14A(20+slope0), 15A(23+slope1.5) 사이의 미탐색 영역. 과거 데이터 fitting이 아님 |
| base_risk 0.01 -> 0.007 | Very Low | 포지션 사이징 축소는 방향성이 아닌 규모 조정. 특정 기간에 맞추는 것이 아님 |

---

## 7. Iteration 8 성공 기준

| Metric | P1 Target | P2 Target | Rationale |
|--------|-----------|-----------|-----------|
| rsi_mr PnL | > -$1,100 | > +$1,000 | ADX_MAX + base_risk 복합 효과 |
| rsi_mr 거래수 | 10-14건 | 9-13건 | ADX_MAX=20 필터링 효과 확인 |
| Portfolio Return | > -2.0% | > +5.0% | 현실적 개선 목표 |
| Sharpe | > 0.28 | > 0.35 | 변동성 감소 효과 |
| cons_down PnL | 변동 없음 | 변동 없음 | 간접 영향 없어야 함 |
| breakout PnL | 변동 없음 | 변동 없음 | 간접 영향 없어야 함 |

### 관찰 포인트

1. **ADX_MAX=20 + slope>1.5 조합 효과**: 14A(slope>0)와 다른 결과가 나오는지
2. **rsi_mr 진입 ADX 분포**: 잔여 12건의 entry ADX가 모두 20 미만인지 확인
3. **GDR 발동 변화**: base_risk 축소로 rsi_mr GDR Tier 1 진입이 늦춰지는지
4. **포트폴리오 상관관계**: rsi_mr 축소가 breakout/cons_down에 간접 영향 주는지 (포지션 슬롯 경쟁)

---

## 8. 전략적 방향 권고

### 단기 (Iter 8-9): 파라미터 마무리

Iter 8 결과에 따라:
- **P1이 -2.0% 이상이면**: 파라미터 튜닝 종료. 현 설정으로 확정. 라이브 모니터링으로 전환.
- **P1이 여전히 -3.0% 이하이면**: rsi_mr 전략 자체를 batch_simulator에서 제거 검토.

### 중기 (Iter 10+): 구조적 개선 전환

파라미터 튜닝의 천장에 도달했으므로, Sharpe 개선을 위해서는 구조적 변경이 필요:

1. **4번째 전략 추가**: breakout/cons_down/rsi_mr과 비상관인 전략 (예: pairs trading, sector rotation)
2. **batch_simulator에 regime 인식 추가**: 현재 batch_simulator는 regime-blind. ADX나 SPY trend를 기반으로 전략별 sizing을 동적 조정하면 Sharpe 개선 가능
3. **멀티 시드 검증**: 현재 단일 시드 결과에 의존. 5-10개 시드로 결과 분포를 확인해야 과적합 여부 판단 가능

### 장기: 시스템 한계 인정

3전략/일간바/$50K 시스템의 현실적 Sharpe 상한은 **0.4-0.5**이다. 이 수준은 소형 계좌 개인 트레이딩 시스템으로서 괜찮은 수준이다. 프로 펀드의 Sharpe 1.0+와 비교하는 것은 인프라와 자원의 차이를 무시하는 것이다.

**현실적 성공 기준**: 양 기간 모두 양수 수익 + MaxDD < 10% + Sharpe > 0.3

---

## 9. Implementation Spec (개발팀 핸드오프)

### 코드 변경 사항

**File 1: `autotrader/strategy/rsi_mean_reversion.py`**

```python
# L56: ADX_MAX 변경
ADX_MAX = 20.0    # WAS 23.0 -- 추세 전환 경계 구간(20-23) 차단
```

**File 2: `autotrader/backtest/batch_simulator.py`**

```python
# L84: rsi_mr base_risk 변경
_STRATEGY_BASE_RISK: dict[str, float] = {
    "rsi_mean_reversion": 0.007,         # WAS 0.01 -- 포지션 30% 축소
    "consecutive_down": 0.015,           # 유지
    "ema_cross_trend": 0.015,            # 유지
    "breakout_momentum": 0.015,          # 유지
}
```

**변경 파일 수**: 2개
**변경 라인 수**: 2개
**테스트 영향**: `test_per_strategy_gdr.py`의 `test_strategy_base_risk_values` 어서션 업데이트 필요 (0.01 -> 0.007)

---

## 10. Panel Vote

| Team Member | Vote | Rationale |
|-------------|------|-----------|
| Strat-1 (Swing) | APPROVE | "ADX_MAX=20은 14A와 다른 조합(slope 1.5 유지). 실전에서 ADX 20-23은 추세 초기 구간으로 MR에 불리하다." |
| Strat-2 (Quant) | APPROVE | "base_risk 축소는 수익/손실 비율을 유지하면서 변동성만 줄인다. Sharpe 관점에서 가장 안전한 레버다." |
| Strat-3 (Risk) | APPROVE with NOTE | "2개 변경 복합 효과가 P2 수익을 ~$1,300 줄인다. 이것이 cons_down +$3,952로 충분히 커버되는지 확인 필요. 하지만 P1 리스크 감소가 더 중요." |
| Strat-4 (Data) | APPROVE with NOTE | "ADX_MAX=20 + slope>1.5 조합은 미탐색 영역이다. 결과가 14A처럼 극단적이면 ADX_MAX=21-22로 미세 조정이 필요할 수 있다. Iter 8을 탐색적 실험으로 본다." |

**전원 승인: 2개 변경 (ADX_MAX 20 + base_risk 0.007)**

**부록 -- Sharpe 1.0 판정**: 패널 전원 합의. 파라미터 튜닝만으로 Sharpe 1.0은 **도달 불가능**. 현실적 상한은 Sharpe ~0.4-0.5. 이 사실을 목표 설정에 반영할 것을 권고.

---

*Panel discussion concluded. Iteration 8 변경 사항 승인. 개발팀 구현 대기.*
