# Strategy Panel Discussion #39: Short Signal Scarcity Analysis

## Date: 2026-03-10

## Issue
Live paper trading 시작 후 (2026-03-03~) short signal이 단 한 건도 발생하지 않음.
- 현재 보유: MRNA, NFLX, ROST, TGT (전부 long)
- 오늘(3/10) nightly scan: NKE long만 1건, short 0건
- RSI Mean Reversion만 short 가능 (BM은 long only)
- 질문: "왜 short signal이 절대 나오지 않는가?"

---

## Code-Verified Short Signal Filter Chain

Short signal이 최종 진입까지 도달하려면 4개 레이어를 전부 통과해야 함:

### Layer 1: 전략 시그널 생성 (rsi_mean_reversion.py:188)
```
RSI > 75.0          -- 극심한 과매수
BB %B > 0.95        -- 볼린저 상단 근접
ADX < 20.0          -- 비추세 시장
ADX slope <= 1.5    -- 최근 3봉 ADX 상승폭 제한
```

### Layer 2: SPY 레짐 블로킹 (regime.py:69-99)
| Regime | mr_short_blocked | 비고 |
|--------|:----------------:|------|
| TREND_UP | **TRUE** | ADX>=25, close>EMA50 |
| TREND_DOWN | FALSE | ADX>=25, close<EMA50 |
| RANGING | FALSE | ADX<20, bb_ratio<0.8 |
| HIGH_VOLATILITY | **TRUE** | bb_ratio>1.2, ADX<25 |
| UNCERTAIN | FALSE | fallback |

### Layer 3: 진입 제약 (entry_checker.py)
- MAX_SHORT_POSITIONS = 3 (vs MAX_LONG = 8)
- MAX_TOTAL_POSITIONS = 9
- 기타: GDR, safety net, re-entry block, heat limit

### Layer 4: 포지션 사이징 (constants.py)
- SHORT_SIZE_RATIO = 0.65 (롱의 65%)
- SL_ATR_MULT short = 0.75 (롱 1.5의 절반 -- 매우 타이트)

---

## Strategy Team Analysis

---

### Strat-1 (Swing Trader): 시장 타이밍 관점

**핵심 진단: RSI > 75 + ADX < 20 조합은 구조적으로 거의 불가능한 조건이다.**

실전 관점에서 분석하면:

1. **ADX < 20 환경의 특성**: ADX가 20 미만이라는 것은 가격이 뚜렷한 방향 없이 밴드 안에서 횡보한다는 뜻. 이런 시장에서 RSI가 75를 넘으려면 "추세 없이 급등"이라는 모순적 상황이 필요. 실제로는 가격이 밴드 상단에 닿으면 되돌림이 오기 때문에 RSI가 75까지 축적되기 어렵다.

2. **시간 프레임 문제**: 일봉(daily bar) 기준 RSI > 75는 상당한 연속 상승을 의미. 3-5일 연속 상승하면 ADX는 자연스럽게 20 이상으로 올라가 ADX 필터에 걸림. 즉, RSI가 75에 도달하는 과정 자체가 ADX < 20 조건을 파괴.

3. **S&P 500 종목 특성**: 대형주 500개를 대상으로 해도, 일봉 RSI > 75 AND ADX < 20 동시 충족 종목은 연간 수십 건 수준일 것으로 추정. 여기에 BB %B > 0.95 + ADX slope 필터까지 적용하면 연간 한 자릿수 이하.

4. **bull market 환경**: 현재(2026-03 초) 시장이 상승세라면 SPY 레짐은 대부분 TREND_UP. TREND_UP에서는 mr_short_blocked=True이므로, 설령 개별 종목이 전략 조건을 충족해도 레짐 블로킹에서 차단됨.

**결론**: 1주일간 short signal이 0건인 것은 완전히 예상 가능한 결과. 연간으로 봐도 short 진입 기회는 손에 꼽을 정도일 것.

---

### Strat-2 (Quant): 통계적 빈도 분석

**정량 분석: 조건별 통과 확률 추정**

S&P 500 일별 500종목 기준, 각 조건의 독립 통과 확률을 추정하면:

| Filter | 조건 | 일별 통과 종목 수 (추정) | 통과율 |
|--------|------|:------------------------:|:------:|
| RSI > 75 | 극심한 과매수 | 15-30 / 500 | ~5% |
| BB %B > 0.95 | 볼린저 상단 | 20-40 / 500 | ~6% |
| ADX < 20 | 비추세 | 100-200 / 500 | ~30% |
| RSI>75 AND %B>0.95 AND ADX<20 | 교집합 | **1-3 / 500** | ~0.4% |
| + ADX slope <= 1.5 | 추세전환 제외 | **0-2 / 500** | ~0.3% |

**그러나** 위 조건들은 독립이 아니다. RSI>75와 ADX<20은 **음의 상관관계**:
- RSI가 75를 넘기 위해서는 연속 상승 필요
- 연속 상승은 ADX를 상승시킴
- 따라서 실제 교집합은 독립 가정보다 훨씬 작음

**교차 확률 보정 추정**:
- RSI>75 AND ADX<20 실제 동시 발생: 일별 500종목 중 0-1건
- + BB %B > 0.95: 0-1건 (대부분 0)
- + ADX slope: 0-1건

**레짐 블로킹 적용**:
- SPY TREND_UP 빈도: bull market에서 ~40-50% of trading days
- SPY HIGH_VOL 빈도: ~10-15%
- 즉 ~50-65%의 거래일에서 short 자체가 완전 차단
- 남은 35-50% 날에서만 short 가능

**최종 예상 빈도**:
```
연간 거래일: ~252일
레짐 허용일: ~252 * 0.40 = ~100일
시그널 발생일: ~100 * 0.003 = 0.3건/일 = ~30건/년 (낙관적)
현실 보정 (음의 상관): ~5-15건/년
```

**결론**: 연간 short signal은 5-15건 수준으로 추정. 1주일(5거래일) 동안 0건은 통계적으로 완전히 정상. 오히려 short signal이 나오는 것이 이례적인 이벤트.

---

### Strat-3 (Risk Manager): 리스크 관리 관점

**리스크 분석: 현 short 체계의 위험 대비 기대 보상**

#### 1. Short의 비대칭 리스크
- Long: 최대 손실 = 투자금 전액 (0으로 제한)
- Short: 이론적 손실 무제한 (가격 상방 무한)
- $1K-$5K 소형 계좌에서 short의 한 번의 대형 손실은 치명적

#### 2. 현재 안전장치 평가
| 안전장치 | 설정 | 평가 |
|----------|------|------|
| SL ATR mult (short) | 0.75 | **매우 타이트** -- 정상 변동에도 스톱 히트 |
| SHORT_SIZE_RATIO | 0.65 | 적절 -- 롱 대비 35% 축소 |
| MAX_SHORT_POSITIONS | 3 | 적절 |
| 레짐 블로킹 | TREND_UP, HIGH_VOL | **핵심 보호 메커니즘** |
| Max hold | 5일 | 적절 |

#### 3. SL 0.75 ATR의 의미
MR short의 SL이 0.75 ATR이라는 것은:
- S&P 500 대형주 평균 ATR이 주가의 1.5-2.5% 수준
- 0.75 * 1.5% = 1.125% 움직임에 스톱 히트
- 일중 변동성(daily range)이 이를 쉽게 초과
- **결과**: 설령 진입해도 스톱아웃 확률이 매우 높음

#### 4. 기대값 분석
```
진입 빈도: ~10건/년 (Strat-2 추정 중간값)
SL 히트율 (0.75 ATR): ~60-70% (타이트한 SL)
승률: ~30-40%
평균 이익 (target): RSI < 50 or %B < 0.50 (작은 이동)
평균 손실: 0.75 ATR
```
연간 10건 중 3-4건 수익, 6-7건 손실. 손익비가 이 빈도에서 유의미한 알파를 만들기 어려움.

#### 5. mr_short_blocked의 합리성
- TREND_UP에서 short 차단: **절대적으로 올바름**. 상승추세에서 역추세 short은 자살 행위.
- HIGH_VOL에서 short 차단: **올바름**. 높은 변동성에서 0.75 ATR SL은 즉사.

**결론**: 현재 short signal의 희소성은 **의도된 설계이자 올바른 리스크 관리**. 소형 계좌에서 short의 risk/reward는 매우 비우호적이며, 현 안전장치들이 제대로 작동하고 있다.

---

### Strat-4 (Analyst): 시장 구조 분석

**시장 구조적 관점에서의 short signal 부재 분석**

#### 1. 주식시장의 구조적 long bias
- 미국 주식시장은 장기적으로 연평균 +7-10% 상승
- 이는 구조적으로 long signal이 short보다 빈번하고 수익성이 높다는 의미
- S&P 500 = 생존자 편향이 내재된 지수 (약한 기업은 퇴출)
- 숏셀링은 시장의 구조적 흐름에 역행하는 행위

#### 2. ADX-RSI 모순의 구조적 원인

```
[비추세 시장 (ADX<20)]
    가격 → 밴드 상단 → 되돌림 → 밴드 하단 → 반등 → ...
    RSI: 40-60 사이 진동 (극단값 도달 어려움)

[추세 시장 (ADX>20)]
    가격 → 연속 상승 → RSI 상승 → 75+ 가능
    그러나 ADX > 20 → 전략 필터 차단
```

이것은 mean reversion 전략의 본질적 딜레마:
- **충분히 과매수된 종목** = 강한 모멘텀 보유 = ADX 상승 = MR 전략 부적합
- **ADX가 낮은 종목** = 모멘텀 부재 = 극단적 과매수 도달 불가

#### 3. 레짐 분류기와 개별 종목의 이중 구조

현 시스템은 **이중 필터** 구조:
- **SPY 레짐** (시장 전체): TREND_UP이면 전종목 short 차단
- **개별 종목 조건**: ADX<20, RSI>75 등

이 이중 구조의 결과:
```
SPY TREND_UP (시장 상승) → 대부분의 종목도 상승 중 → 개별 ADX도 높음
  → 레짐 블로킹 + 개별 필터 모두에서 차단 (이중 사형선고)

SPY RANGING (시장 횡보) → 개별 종목 ADX<20 가능성 높음
  → 그러나 횡보 시장에서 RSI>75 도달 어려움
  → 결과적으로 시그널 빈도는 여전히 극히 낮음

SPY TREND_DOWN (시장 하락) → short 허용되나
  → 시장 하락 시 개별 종목도 하락 → RSI는 낮아짐 (과매도 방향)
  → RSI>75 과매수 종목은 더욱 희귀
```

**모든 레짐에서 short signal이 구조적으로 억제되는 "완전 봉쇄" 상태.**

#### 4. 백테스트 데이터에서의 MR short 기여도

MEMORY에 기록된 Iter 23/26 결과(+15.4%)에서:
- MR short가 총 수익에 기여한 비중은 기록되지 않았으나
- Capital deployment가 평균 26.4%, max 동시 포지션 3건이었던 점을 감안하면
- MR short의 실제 기여는 미미하거나 거의 없었을 가능성이 높음

**결론**: Short signal의 부재는 시장 구조, 지표 간 수학적 관계, 레짐 시스템의 합리적 설계가 결합된 자연스러운 결과. 버그가 아니라 시스템이 올바르게 작동하고 있는 증거.

---

## Panel Consensus

### Q1: Short signal 희소성은 설계 의도인가 버그인가?

**만장일치: 설계 의도 (Feature, Not Bug)**

- RSI > 75 + ADX < 20 조합은 수학적으로 극히 드문 조건이며, 이는 MR short이 "확실한 기회에서만" 진입하도록 의도된 보수적 설계
- 레짐 블로킹은 시장 전체가 불리한 환경에서 short을 차단하는 올바른 안전장치
- 결과적으로 연간 5-15건 수준의 극히 선별적인 short만 허용

### Q2: RSI>75 + ADX<20은 근본적으로 모순인가?

**Strat-2/4 합의: 강한 음의 상관관계로 인해 "거의 모순에 가깝다"**

- 완전히 불가능하지는 않음 (갭업 후 횡보, 어닝 서프라이즈 후 밴드 확대 등)
- 그러나 일봉 기준으로 이 조합의 자연 발생 확률은 극히 낮음
- RSI 65-70 + ADX < 20이면 더 현실적이겠으나, 현재 SYSTEM FREEZE

### Q3: SHORT 파라미터를 조정해야 하는가?

**만장일치: NO -- SYSTEM FREEZE 유지**

| 가능한 조정 | 효과 | 패널 판단 |
|-------------|------|-----------|
| RSI 75 -> 65 | short 빈도 5-10배 증가 | REJECT: 검증 안 된 변경 |
| ADX 20 -> 25 | 완화 | REJECT: 추세 시장에서 역추세 위험 |
| SL 0.75 -> 1.0 ATR | 스톱아웃 감소 | REJECT: 손실 폭 증가 |
| 레짐 블로킹 해제 | 모든 레짐에서 short 허용 | REJECT: 핵심 안전장치 제거 |

**이유**:
1. SYSTEM FREEZE가 Panel #34에서 선언됨 -- 파라미터 튜닝 시대 종료
2. Short 빈도를 높이면 낮은 승률 + 높은 리스크 = 순손실 증가 가능성
3. $1K-$5K 계좌에서 short의 marginal benefit은 리스크 대비 미미
4. Iter 23/26의 +15.4% 결과에서 MR short 기여도 자체가 작았을 것

### Q4: 예상 short signal 빈도

| 시나리오 | 연간 추정 | 비고 |
|----------|:---------:|------|
| 낙관적 (레짐 허용 多) | ~15건 | bear market 기간 포함 |
| 중립적 (현 시장) | ~5-10건 | 현재 bull market 환경 |
| 비관적 (강 bull) | ~2-5건 | SPY TREND_UP 지배적 |

### Q5: MR short 전략의 $1K-$5K 계좌 적합성

**Strat-3 주도 판결: 현 계좌 규모에서 short은 "보험 성격"**

- Short은 수익 극대화가 아닌 하방 보호 옵션
- 실제 작동 시나리오: bear market 진입 시 SPY TREND_DOWN 전환 -> short 허용
- 그러나 bear market에서도 RSI > 75 종목은 드묾 (역설적)
- **현실적 가치**: 연간 5-10건의 선별적 short으로 bear market에서 소량 수익
- **위험 대비**: 현 안전장치(레짐 블로킹, 타이트 SL, 축소 사이징)가 적절히 보호

---

## Final Verdict

```
STATUS: SHORT SIGNAL 부재는 정상 작동 (NO ACTION REQUIRED)
SYSTEM FREEZE: 유지
파라미터 변경: 없음
모니터링: 6개월간 short signal 빈도 로깅 추가 권고 (diagnostic용)
```

### 권고사항

1. **단기 (즉시)**: 현 상태 유지. Short이 안 나오는 것 자체가 시스템의 올바른 작동
2. **중기 (paper trading 종료 후)**: 백테스트 데이터에서 MR short의 과거 실제 발생 빈도 및 수익 기여도 정밀 추출. 만약 기여도가 0에 가까우면 short 제거도 고려 가능 (코드 단순화)
3. **장기**: 계좌가 $10K 이상 성장하고 3번째 전략 추가 시점에서 short 전략 재검토

### 한 줄 요약

> **"Short signal이 나오지 않는 것은 버그가 아니라, 극도로 보수적인 조건이 모든 레이어에서 중첩된 결과이며, 소형 계좌의 리스크 관리 관점에서 이것이 올바른 작동이다."**

---

## Appendix: Short Signal 필터 체인 시각화

```
S&P 500 ~500종목 (일별)
    |
    v
[Layer 1: 전략 필터]
RSI > 75 AND %B > 0.95 AND ADX < 20 AND ADX slope <= 1.5
    |  ~0-2 종목 통과 / 일
    v
[Layer 2: SPY 레짐 블로킹]
TREND_UP -> BLOCKED    (~40-50% of days)
HIGH_VOL -> BLOCKED    (~10-15% of days)
RANGING  -> PASS       (~20-25% of days)
TREND_DN -> PASS       (~5-10% of days)
UNCERTAIN -> PASS      (~10-15% of days)
    |  ~35-50% of days에서만 통과 가능
    v
[Layer 3: 진입 제약]
MAX_SHORT = 3, GDR, safety net, heat limit
    |  대부분 통과 (short이 거의 없으므로 제약에 걸릴 일 없음)
    v
[Layer 4: 사이징]
SHORT_SIZE_RATIO = 0.65, SL = 0.75 ATR
    |  진입해도 스톱아웃 확률 높음
    v
최종 short 진입: 연간 ~5-15건 추정
```
