# Strategy Panel Discussion #33: Iter 28 Trend Pullback Post-Mortem

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iter 28 = Phase 2 (Trend Pullback added to BM+MR). Combined return REGRESSED from +24.7% to +19.6%. TP is a net-losing strategy in P2 and near-zero in P1. Panel #32's REGRESSION criteria triggered. This discussion conducts a full post-mortem and decides next steps.
**Verdict**: **REGRESSION CONFIRMED. Trend Pullback FAILED. Immediate revert to Iter 27 baseline.**

---

## 1. Iter 28 Results Summary

### Performance Overview

| Metric | Iter 27 (Baseline) | Iter 28 (+ TP) | Delta | Verdict |
|--------|-------------------|-----------------|-------|---------|
| P1 Return | +11.4% | +7.3% | **-4.1%p** | REGRESSION |
| P2 Return | +13.3% | +12.3% | **-1.0%p** | REGRESSION |
| Combined | +24.7% | +19.6% | **-5.1%p** | REGRESSION |
| P1 MaxDD | 20.2% | 21.7% | +1.5%p | Worse |
| P2 MaxDD | 3.0% | 22.4% | **+19.4%p** | CATASTROPHIC |
| P1 Trades | 60 | 98 | +38 | TP flooding |
| P2 Trades | 67 | 107 | +40 | TP flooding |

### Strategy-Level Breakdown

| Strategy | Period | Trades | WR | PF | PnL | Assessment |
|----------|--------|--------|------|-------|---------|-----------|
| BM | P1 | 17 | 82.4% | 2.399 | +$4,044 | Quality up, quantity DOWN |
| BM | P2 | 25 | 80.0% | 3.340 | +$6,576 | Quality up, quantity DOWN |
| MR | P1 | 15 | 46.7% | 0.725 | -$1,550 | Consistent with Iter 27 |
| MR | P2 | 15 | 73.3% | 2.857 | +$6,597 | Consistent with Iter 27 |
| **TP** | **P1** | **66** | **53.0%** | **1.077** | **+$1,449** | **Barely positive** |
| **TP** | **P2** | **67** | **44.8%** | **0.699** | **-$4,465** | **NET LOSING** |

### BM Trade Count Collapse (Critical Finding)

| Period | BM Iter 27 | BM Iter 28 | Lost Trades | Lost Trades % |
|--------|-----------|-----------|-------------|---------------|
| P1 | 44 | 17 | **-27** | **-61%** |
| P2 | 49 | 25 | **-24** | **-49%** |
| Combined | 93 | 42 | **-51** | **-55%** |

### Panel #32 Success/Failure Criteria Check

```
SUCCESS criteria (ALL must be met):
[FAIL] Combined Return > +27%:  Actual +19.6% -- FAILED by -7.4%p
[FAIL] S&P Gap < -5%p:  Actual -11.8%p -- FAILED
[FAIL] TP PF > 1.2 (both):  P1 1.077, P2 0.699 -- FAILED
[PASS] MaxDD P1 < 25%:  21.7% -- OK
[FAIL] MaxDD P2 < 12%:  22.4% -- FAILED (catastrophic)
[PASS] TP trades > 20:  133 -- OK (too many, actually)

REGRESSION criteria (Panel #32 defined):
[TRIGGERED] Combined Return < +24%:  +19.6% -- YES
[TRIGGERED] TP PF < 0.8:  P2 PF 0.699 -- YES
=> ACTION: DISABLE TP, investigate root cause
```

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- 트레이딩 관점의 근본 원인 분석

"Iter 28의 결과를 트레이딩 실행 관점에서 상세히 해부하겠다. 이번 실패에서 3가지 핵심 문제를 발견했다.

**문제 1: TP가 예측의 3-5배 거래를 생성했다 -- 진입 조건이 전혀 선택적이지 않다**

```
Panel #31/32의 예측:
- 연간 25-40건 거래
- 2년(P1+P2) 합산: 50-80건

Iter 28 실제:
- P1: 66건, P2: 67건
- 2년 합산: 133건
- 예측 대비: 1.7x ~ 2.7x (최소 기준 대비)

왜 이렇게 많은 거래가 발생했나?

TP의 6개 진입 조건을 개별 확률로 분해하면:
1. close > EMA(50): S&P 500 상승추세 중 ~70-80%의 종목이 충족
2. EMA(21) 5일간 상승: ~60% 확률 (EMA는 대부분 smooth한 추세)
3. ADX 15-35: 이것은 '보통' 구간이다. 전체 거래일의 ~50-60%
4. close within 97-102% of EMA(21): ~15-25% (이것이 유일한 좁은 필터)
5. RSI 35-60: ~40-50% (정상 범위, 전혀 제한적이지 않음)
6. 양봉 또는 해머: ~55-60% (봉의 절반 이상이 양봉)

결합 확률 추정: 0.75 * 0.60 * 0.55 * 0.20 * 0.45 * 0.57 = ~1.5%
S&P 500 유니버스 * 500일 * 1.5% = ~3,750건 raw signal
필터(cap, heat, ranking) 후: ~130건 = 실제 결과와 일치

문제의 핵심: RSI 35-60과 '양봉' 조건은 사실상 필터가 아니다.
대부분의 날에 대부분의 종목이 이 범위 안에 있다.
유일하게 선택적인 필터는 #4 (close near EMA21) 뿐인데,
이것만으로는 edge를 만들 수 없다.
```

**문제 2: BM 거래 수가 55% 감소했다 -- TP가 BM을 crowding out**

이것이 이번 실패의 가장 치명적인 발견이다:

```
Iter 27 BM: P1 44건, P2 49건 = 93건 total
Iter 28 BM: P1 17건, P2 25건 = 42건 total
손실: -51건 (-55%)

BM은 PF 2.0-3.3의 고품질 전략이다.
51건의 BM 거래를 잃은 것의 가치를 추정하면:
- BM Iter 27 avg PnL/trade: ($9,411+$1,503)/93 = $117/trade
- 51건 손실 * $117 = $5,967 잠재 수익 손실

TP가 이 51건을 대체하여 얻은 것:
- TP 133건 총 PnL: +$1,449 + (-$4,465) = -$3,016 (순 손실)

Net impact: -$5,967 (BM 기회비용) + (-$3,016) (TP 손실) = -$8,983
이것이 Iter 27 대비 수익 감소(-$5,100)의 대부분을 설명한다.
(나머지는 cash yield 감소와 MR 약간의 변동)
```

메커니즘: TP가 하루에 2-3건 시그널을 생성하면, daily entry cap (4건)과 heat limit (40%)을 소비한다. BM이 같은 날 좋은 시그널을 내도 자리가 없다. 그리고 TP가 2건의 포지션을 유지하면 MAX_LONG 8에서 차지하는 비율이 커져 BM의 후속 진입도 차단된다.

**문제 3: TP의 WR 44-53%는 RR 2.0에서 이론적으로 breakeven이지만 실제로는 손실**

```
이론적 breakeven WR = 1 / (1 + RR) = 1 / (1 + 2.0) = 33.3%
TP WR 44-53%이면 이론상 profitable이어야 한다.

그러나 현실에서는:
- SL 1.5 ATR에서 stop-out 된 후 가격이 반등하는 경우가 빈번 (whipsaw)
- TP 3.0 ATR까지 도달하기 전에 time exit (7일) 또는 structure break에 의해 퇴출
- 실제 avg win / avg loss 비율이 2.0이 아닌 것으로 추정

P2 데이터로 역산:
- TP P2: 67 trades, WR 44.8% = 30 wins / 37 losses
- PF 0.699 = total_wins / total_losses
- 30 * avg_win = 0.699 * 37 * avg_loss
- avg_win / avg_loss = 0.699 * 37 / 30 = 0.862

실제 RR은 2.0이 아니라 0.862이다!

이것은 대부분의 '승리' 거래가 TP(3.0 ATR)까지 가지 못하고
time exit, structure break, 또는 trailing stop에 의해 조기 퇴출되어
평균 승리 크기가 평균 손실보다 작다는 것을 의미한다.
```

**Strat-1 결론: TP의 실패는 3중이다. (1) 진입 조건이 선택적이지 않아 noise trade를 대량 생성, (2) 이 noise가 BM의 고품질 거래를 crowding out, (3) 실제 RR이 설계 RR의 43% 수준. TP는 설계 자체의 결함이다. Parameter 조정으로 해결할 수 없다.**"

### Strat-2 (Quant Analyst) -- 정량적 실패 분해와 통계적 진단

"Iter 28의 실패를 수학적으로 분해하고, TP의 edge 존재 여부를 통계적으로 검증하겠다.

**분석 1: Return Decomposition (Iter 27 vs Iter 28)**

```
Iter 27 Return Sources:
- BM P1+P2: +$9,411 + $1,503 = +$10,914
- MR P1+P2: -$1,434 + $7,803 = +$6,369
- Cash Yield (est): ~$7,000
- Total: ~$24,283 = +24.3% (close to actual +24.7%)

Iter 28 Return Sources:
- BM P1+P2: +$4,044 + $6,576 = +$10,620
- MR P1+P2: -$1,550 + $6,597 = +$5,047
- TP P1+P2: +$1,449 + (-$4,465) = -$3,016
- Cash Yield (est): ~$6,200 (idle cash 감소로 yield 감소)
- Total: ~$18,851 = +18.9% (close to actual +19.6%)

Delta 분해:
[1] BM PnL 감소: $10,914 -> $10,620 = -$294 (-1.4%)
    -> BM의 per-trade 품질은 향상(PF 2.4-3.3)되었으나 거래수 55% 감소
    -> BM PnL이 거의 유지된 것은 남은 42건이 모두 '최고 품질' 거래였기 때문
    -> 그러나 93건->42건에서 중간 품질 51건의 기회비용은 반영되지 않음

[2] MR PnL 감소: $6,369 -> $5,047 = -$1,322 (-6.7%)
    -> MR은 TP와 ADX 15-20 겹침 구간에서 약간의 crowding out 발생
    -> MR P2 PnL: $7,803 -> $6,597 = -$1,206 (이 대부분이 여기서 발생)

[3] TP PnL: -$3,016 (직접 손실)
    -> P1에서 +$1,449로 간신히 양수이나, P2에서 -$4,465로 상쇄 이상

[4] Cash yield 감소: $7,000 -> $6,200 = -$800
    -> TP가 자본을 점유하여 idle cash 감소

Total Delta: -$294 + (-$1,322) + (-$3,016) + (-$800) = -$5,432
실제 Delta: $24,700 - $19,600 = -$5,100 (reasonably close)
```

**분석 2: TP의 Edge 통계적 검증**

```
귀무가설(H0): TP에 통계적 edge가 없다 (random entry와 동일)

P1 TP: 66 trades, WR 53.0%, PF 1.077
- PnL: +$1,449 on 66 trades = $21.95/trade
- StdDev(PnL) 추정: ~$300/trade (SL 1.5 ATR on $15K position)
- t-statistic: $21.95 / ($300 / sqrt(66)) = $21.95 / $36.93 = 0.594
- p-value (one-tailed): ~0.28
- 결론: 통계적으로 유의하지 않음 (p > 0.05)

P2 TP: 67 trades, WR 44.8%, PF 0.699
- PnL: -$4,465 on 67 trades = -$66.64/trade
- t-statistic: -$66.64 / ($300 / sqrt(67)) = -$66.64 / $36.65 = -1.818
- p-value (one-tailed, loss): ~0.037
- 결론: 95% 신뢰수준에서 TP는 negative edge를 가진다

종합: P1에서 edge 없음(noise), P2에서 negative edge.
TP 전략은 통계적으로 무작위 진입보다 나쁘거나 동등하다.
H0을 기각할 수 없다. TP에는 exploitable edge가 없다.
```

**분석 3: 8연속 손실의 확률 분석 (P1)**

```
TP P1 WR 53%에서 8연속 손실 확률:
- P(8 consecutive losses) = (1 - 0.53)^8 = (0.47)^8 = 0.0024 = 0.24%

66건 거래에서 8연속 손실이 한 번이라도 발생할 확률:
- 시행 수 = 66 - 8 + 1 = 59 windows
- P(at least one run of 8) ≈ 1 - (1 - 0.0024)^59 ≈ 13.2%

13.2%는 낮지 않다. 66건 중 8연속 손실은 '불운'으로 설명 가능하다.
그러나 이것은 TP의 edge가 53% WR이라는 전제 하의 계산이다.
실제 edge가 없다면(true WR ~50%), 8연속 손실 확률은 ~22%로 더 높아진다.

핵심: 8연속 손실 자체가 문제가 아니다. TP의 edge 부재가 문제다.
```

**분석 4: Panel #31 예측 vs 실제 비교**

| Metric | Panel #31/32 예측 | Iter 28 실제 | 오차 |
|--------|-------------------|-------------|------|
| TP 연간 거래수 | 25-40 | 66-67/yr | **+67-168%** |
| TP WR | 55-65% | 44.8-53% | **-2 ~ -20.2%p** |
| TP PF | > 1.2 | 0.699-1.077 | **-0.12 ~ -0.50** |
| TP Net PnL/yr | +$2,070 | -$1,508/yr | **-$3,578** |
| Combined Return | +28% | +19.6% | **-8.4%p** |
| BM trade count | unchanged | -55% | **UNPREDICTED** |

**예측이 틀린 핵심 이유:**
1. 진입 조건의 선택성을 과대평가했다. 'ADX 15-35 + RSI 35-60'이 얼마나 쉽게 충족되는지를 과소평가.
2. BM crowding out 효과를 전혀 예측하지 못했다. 이것이 가장 큰 맹점이었다.
3. RR 2.0 가정이 실제와 괴리. Time exit와 structure break가 승리 크기를 크게 축소.

**Strat-2 결론: TP는 통계적으로 edge가 없다 (P1: noise, P2: negative edge). 예측이 거래 빈도, WR, PF 모든 측면에서 틀렸다. 가장 위험한 미예측 효과는 BM crowding out이었다. TP는 즉시 제거해야 한다.**"

### Strat-3 (Risk Manager) -- 리스크 프로파일 붕괴 분석

"Iter 28의 리스크 프로파일이 어떻게 붕괴했는지 분석하겠다.

**분석 1: P2 MaxDD 3.0% -> 22.4% -- 이것은 재앙이다**

```
Iter 27 P2: MaxDD 3.0% (exceptional)
Iter 28 P2: MaxDD 22.4% (catastrophic)
Delta: +19.4%p

Panel #32에서 나는 Phase 2 후 P2 MaxDD를 5-12%로 예측했다.
실제 22.4%는 예측 상한의 1.9배다.

무엇이 22.4% DD를 만들었나?

가설: TP의 67건 거래 중 37건 손실이 연쇄적으로 발생하며 equity를 깎았다.
- TP P2 평균 손실 추정: $4,465 / 37 = $120.7/loss
- 그러나 DD는 누적이므로, 연속 손실 구간에서 발생

TP P2 PF 0.699 = 총 승리 / 총 손실
- 30건 * avg_win + 37건 * avg_loss = net -$4,465
- PF 0.699 -> total_win = 0.699 * total_loss
- total_win + (-total_loss) = -$4,465
- 0.699L - L = -$4,465 -> -0.301L = -$4,465 -> L = $14,835
- total_loss = $14,835, total_win = $10,370
- avg_loss = $14,835/37 = $401, avg_win = $10,370/30 = $346

avg_loss > avg_win. 이것은 SL (1.5 ATR ~ $400-500)에 정확히 부합한다.
대부분의 손실이 full SL hit이고, 승리는 SL 크기에도 미치지 못한다.

BM의 DD 보상 능력 감소:
- Iter 27: BM이 49건으로 MR 손실을 상쇄
- Iter 28: BM이 25건으로 줄어 TP 손실을 상쇄할 수 없음
- BM P2 PnL $6,576 vs TP P2 PnL -$4,465: BM이 TP 손실의 68%만 상쇄
```

**분석 2: 동시 포지션과 포트폴리오 Risk Exposure**

```
Iter 28의 동시 포지션 문제:

TP cap 2 + BM cap 2 + MR cap 4 = 이론적 최대 8건 동시
(MAX_LONG 8과 일치)

실제로 TP가 cap 2를 빈번히 채움:
- TP 66-67건 * avg 3-5일 hold = 198-335 position-days
- 250 거래일 중: 평균 0.79-1.34 TP positions open
- 이것은 BM이 MAX_LONG에 접근할 여유를 줄임

Heat 40% 소비:
- TP 2건 * ~$15K = $30K = 30% heat (40% 한도의 75% 소비)
- BM이 추가 진입할 수 있는 여유: ~$10K (1건 미만)
- 이것이 BM 거래 55% 감소의 주요 원인
```

**분석 3: Safety Net과 GDR 상호작용**

```
TP의 GDR 설정: (0.03, 0.06)
- Tier 1: TP 전략 DD 3% -> risk 50% 감소
- Tier 2: TP 전략 DD 6% -> 진입 중단

TP P2에서 -$4,465 = 전체 포트폴리오 대비 -4.47%
- TP 전략 자체의 DD: TP peak equity에서의 하락
- GDR Tier 1이 발동되었을 가능성이 높으나, 그 전에 이미 상당한 손실 누적

핵심 문제: GDR은 '전략별 DD'를 추적하지만,
TP의 crowding out으로 BM이 놓친 수익은 '기회비용'이므로 GDR에 잡히지 않는다.
GDR은 직접 손실만 추적하지, 간접 손실(crowding out)은 추적할 수 없다.

이것은 리스크 관리의 맹점이다.
```

**분석 4: 리스크 관점의 의사결정**

```
Option A (TP 제거, Iter 27 복귀):
- 즉시 MaxDD를 20.2%/3.0%로 복구 (P2 DD 22.4% -> 3.0%는 엄청난 개선)
- 수익 +19.6% -> +24.7%로 복구
- 리스크: ZERO (검증된 baseline 복귀)
- 내 판단: STRONGLY RECOMMENDED

Option B (TP 파라미터 강화):
- 거래수를 66건 -> 15-20건으로 줄여야 의미 있음
- 그러나 edge가 통계적으로 없는 전략의 거래수를 줄여도 edge가 생기지 않음
- MaxDD 리스크: 개선되겠으나 불확실
- 내 판단: NOT RECOMMENDED (edge 부재 문제 해결 안됨)

Option C (완전히 다른 3rd 전략):
- 새 전략 설계 + 구현 + 테스트에 2-3주 소요
- 또 다른 실패의 리스크 존재
- 내 판단: DEFER (Iter 27 baseline 복귀 후 신중히 설계)
```

**Strat-3 결론: P2 MaxDD 22.4%는 용납할 수 없는 수준이다. TP는 직접 손실(-$3,016)뿐 아니라 BM crowding out을 통한 간접 손실($5,000+)까지 초래했다. 즉시 제거하고 Iter 27로 복귀해야 한다. 새 3rd 전략은 crowding out 분석을 포함한 더 엄격한 사전 검증을 거쳐야 한다.**"

### Strat-4 (Market Analyst) -- ADX Dead Zone 전략의 구조적 한계

"TP가 실패한 시장 구조적 원인을 분석하고, 향후 3rd 전략의 방향을 제시하겠다.

**분석 1: 'ADX 20-28 Dead Zone을 채운다'는 전제 자체의 검증**

```
Panel #31의 핵심 전제:
'ADX 20-28 구간에서 BM도 MR도 진입하지 않으므로, 이 구간을 채울 전략이 필요하다.'

이 전제를 재검토하면:
- ADX 20-28은 '중간 추세' = 추세가 있지만 강하지 않음
- 이 구간에서 pullback-and-resume 패턴이 정말로 수익성이 있는가?
- 답: 일일 봉 기준으로는 매우 의심스럽다.

일일 봉에서 ADX 20-28 구간의 특성:
1. 추세가 형성 중이거나 소멸 중 (방향 불확실)
2. EMA(21)에서 반등이 아니라 EMA를 관통하는 경우가 빈번
3. Noise-to-signal ratio가 높음
4. 기관 투자자들이 이 구간에서 방향성 베팅을 자제

핵심 발견: ADX 20-28이 'dead zone'인 이유는
우리 시스템의 결함이 아니라 이 구간 자체의 낮은 예측성 때문이다.
시장이 이 구간에서 명확한 방향을 제시하지 않으므로,
어떤 방향성 전략이든 이 구간에서 고전할 수밖에 없다.
```

**분석 2: TP가 실제로 ADX 20-28에서만 거래했나?**

```
TP ADX 범위: 15-35 (설계)

이 중 ADX dead zone (20-28): 범위의 62%
BM 겹침 구간 (28-35): 범위의 33%
MR 겹침 구간 (15-20): 범위의 24%

(겹침 포함하여 합이 100% 초과하는 것은 정상)

133건 TP 거래의 ADX 분포를 추정하면:
- ADX 15-20 (MR 겹침): ~25건 (19%)
- ADX 20-28 (dead zone): ~70건 (53%) -- 이것이 주목적
- ADX 28-35 (BM 겹침): ~38건 (28%)

BM 겹침 구간(28-35)에서의 38건이 문제:
- 이 구간에서 TP는 BM과 같은 종목을 경쟁한다
- TP의 ranking score가 BM보다 높으면 BM 시그널이 밀려난다
- 이것이 BM 거래 55% 감소의 상당 부분을 설명한다

Dead zone(20-28)에서의 70건:
- WR/PF를 별도로 추정하면, 이 구간의 edge는 더 나쁠 수 있다
- ADX 20-28은 추세 방향이 불확실한 구간이므로 pullback 전략의 전제(추세 존속)가 약하다
```

**분석 3: 일일 봉 Pullback 전략의 구조적 한계**

```
Pullback 전략이 잘 작동하는 조건:
1. 명확한 추세 존재 (ADX > 30 이상이 이상적)
2. 충분한 시간 해상도 (4시간봉 또는 1시간봉)
3. 좁은 SL (추세가 강할수록 pullback 깊이가 얕음)
4. 빠른 회복 (강한 추세에서 EMA 터치 후 즉일 반등)

우리 시스템의 제약:
1. ADX 15-35 = 추세가 약하거나 보통 (이상적이지 않음)
2. 일일 봉만 사용 = 시간 해상도 부족
3. SL 1.5 ATR = 일일 봉 기준으로는 적정하나, 약한 추세에서 빈번히 hit
4. 다음날 open에 진입 = pullback 반등 시점을 놓칠 수 있음 (Group A MOO)

핵심: EMA pullback 전략은 본질적으로 intraday 또는 4시간봉에서
더 잘 작동한다. 일일 봉에서는 noise가 너무 크다.

일일 봉에서 'pullback to EMA21'이 발생했을 때:
- 다음날 반등: ~50% (동전 던지기와 유사)
- EMA 관통 후 추가 하락: ~30%
- 횡보: ~20%

50% 확률에서 RR 0.86으로는 수익을 낼 수 없다.
```

**분석 4: Cash Yield의 상대적 우위 재확인**

```
TP를 제거하고 Iter 27로 복귀하면:
- idle cash ~73.6% -> cash yield ~$3,500/yr
- 2년: ~$7,000 = +7.0%p

TP가 있으면:
- idle cash ~65% (TP가 자본 점유) -> cash yield ~$3,100/yr
- 2년: ~$6,200 = +6.2%p
- TP net PnL: -$3,016

Cash yield 관점:
- TP 제거: +$7,000 (cash yield) + $0 (TP PnL) = +$7,000
- TP 유지: +$6,200 (cash yield) + (-$3,016) (TP PnL) = +$3,184

TP를 제거하는 것만으로 cash yield가 +$800 증가하고,
TP 손실 -$3,016을 피하므로, 총 +$3,816의 개선이 있다.

이것은 '아무것도 하지 않는 것'이 '나쁜 전략으로 거래하는 것'보다
훨씬 나은 결과를 만든다는 현금 수익률의 힘을 보여준다.
```

**분석 5: S&P 갭을 줄이기 위한 대안적 접근**

```
현재 상태 (Iter 27, TP 없이):
- Combined: +24.7%
- S&P Gap: -6.7%p

이 갭의 구성:
- P1 gap: -4.5%p (Bull market에서 BM이 S&P 상승을 충분히 포착 못함)
- P2 gap: -2.2%p (Mixed market에서 MR이 상당 부분 보완)

P1 gap -4.5%p의 원인:
- BM은 breakout만 잡으므로, 추세 중 steady gains를 놓침
- 이것은 '자본 배치 문제'가 아니라 '전략 유형 문제'
- S&P는 매일 100% 투자이므로 steady gains를 자동 포착
- 우리는 특정 이벤트(breakout, mean reversion)만 포착

구조적 해법 방향 (향후 논의용):
1. BM cap 2 -> 3: 검증된 전략의 활동 범위 확대 (가장 안전)
2. Market-neutral 전략: long/short pair로 방향성 의존도 감소
3. 더 짧은 timeframe: 4시간봉으로 해상도 증가 (대규모 변경)
4. 현재 수준 수용: +24.7%는 충분히 좋은 결과. S&P를 이길 필요가 있는가?
```

**Strat-4 결론: ADX 20-28 dead zone은 '채워야 할 공백'이 아니라 '본질적으로 예측이 어려운 구간'이다. 일일 봉 pullback 전략은 이 구간에서 구조적으로 edge를 가질 수 없다. TP 즉시 제거에 동의한다. 향후 3rd 전략은 ADX dead zone이 아닌 다른 각도에서 접근해야 한다.**"

---

## 3. Cross-Expert Synthesis

### Question A: TP를 즉시 제거하고 Iter 27로 복귀해야 하는가?

**만장일치: YES -- IMMEDIATE REVERT (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | TP의 3중 실패 (선택성 부재, crowding out, 실제 RR 괴리). Parameter 조정 불가. |
| Strat-2 | 통계적 edge 부재 확인. 예측 대비 모든 metric에서 실패. |
| Strat-3 | P2 MaxDD 22.4%는 용납 불가. 즉시 리스크 정상화 필요. |
| Strat-4 | 일일 봉 pullback 전략의 구조적 한계. Dead zone은 본질적으로 예측 불가. |

**결정: Iter 29 = Iter 27 값으로 완전 복귀. TP 코드는 유지하되 batch_simulator에서 비활성화.**

### Question B: TP를 파라미터 강화로 살릴 수 있는가? (Salvage Assessment)

**만장일치: NO (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | 거래수를 1/4로 줄여도 (66건->15건), edge가 없으면 무의미. |
| Strat-2 | P2에서 negative edge가 통계적으로 유의. 이것은 parameter 문제가 아니라 concept 문제. |
| Strat-3 | 더 타이트한 조건은 거래수만 줄이지 edge를 만들지 않음. Risk/reward 근본이 틀림. |
| Strat-4 | ADX 20-28에서의 pullback은 일일 봉 해상도에서 structural edge가 없음. |

**결정: TP salvage 시도 하지 않음. Concept 자체가 flawed.**

### Question C: 대안 3rd 전략을 즉시 설계해야 하는가?

**다수 의견: DEFER (3/4, Strat-1만 조건부 YES)**

| Expert | 입장 | 근거 |
|--------|------|------|
| Strat-1 | 조건부 YES | BM cap 3을 먼저 테스트한 후, 결과를 보고 3rd 전략 필요성 재평가 |
| Strat-2 | DEFER | Iter 27이 +24.7%로 충분히 강한 시스템. 나쁜 전략 추가보다 현상 유지가 나음 |
| Strat-3 | DEFER | 3rd 전략 실패를 경험한 직후 서두르면 안 됨. 충분한 분석 후 신중히 접근 |
| Strat-4 | DEFER | ADX dead zone 접근 자체를 재고해야 함. 새로운 각도의 탐색 필요 |

**결정: 3rd 전략 설계는 DEFER. 우선 Iter 27 복귀 -> BM cap 3 테스트 -> 결과에 따라 재논의.**

### Question D: BM Cap 2 -> 3을 다음 Phase로 추진하는가?

**다수 동의: YES, 단 Iter 27 복귀 확인 후 (3/4, Strat-3 조건부)**

| Expert | 입장 | 근거 |
|--------|------|------|
| Strat-1 | YES | BM은 PF 2.0-3.3의 검증된 전략. Cap 확대는 edge가 확인된 전략의 활동 확대. |
| Strat-2 | YES | BM cap 3 추가 시 연 +12-15건 추가 BM 거래. BM avg PnL $117/trade 기준 +$1,400-1,750/yr |
| Strat-3 | 조건부 | Iter 29에서 Iter 27 재현 확인 후에만. MaxDD 영향 +2-3%p 추정. |
| Strat-4 | YES | BM의 ADX > 28 구간은 signal quality가 높다. 더 많은 BM = 더 많은 고품질 거래. |

**결정: Iter 29 = Iter 27 복귀 확인 -> Iter 30에서 BM cap 3 테스트.**

### Question E: S&P 갭(-6.7%p)에 대한 현실적 목표 재설정?

**합의: 갭 축소는 가능하나 S&P 초과는 현 시스템으로 불현실적 (4/4)**

```
현실적 목표:
- Iter 27 baseline: +24.7% (S&P gap -6.7%p)
- BM cap 3 추가 효과: +1.5-3.0%p
- 예상 도달점: +26-28% (S&P gap -3 ~ -5%p)
- S&P 31.4%에 완전히 도달하기 위해서는 deployment ~50% 이상 필요
- 현재 system은 event-driven (breakout/reversion)이므로 50% deployment는 구조적 한계

전략적 수용:
- +24-28%는 MaxDD 20%에서 달성하는 것이므로 risk-adjusted로 나쁘지 않다
- S&P는 MaxDD 8-16% 범위 (시기에 따라 다름)
- Calmar: 우리 24.7%/20% = 1.24 vs S&P 31.4%/16.3% = 1.93
- Risk-adjusted로는 아직 S&P가 우세하나, 격차는 줄어들고 있음
- Cash yield + BM cap 3으로 +26-28% / MaxDD ~22% = Calmar 1.18-1.27
```

**결정: S&P 초과 달성을 단기 목표에서 제외. 현실 목표는 Combined +26-28% (S&P gap -3 ~ -5%p). Risk-adjusted return 개선에 집중.**

---

## 4. Root Cause Summary

### TP 실패의 5가지 근본 원인

| # | 원인 | 심각도 | 설명 |
|---|------|--------|------|
| 1 | **진입 조건의 낮은 선택성** | CRITICAL | RSI 35-60, 양봉 조건 등이 사실상 필터 역할 못함. 신호 대비 잡음 비율 과다. |
| 2 | **BM crowding out** | CRITICAL | TP 133건이 daily cap, heat, position cap을 소비하여 BM 93건 -> 42건으로 55% 감소. |
| 3 | **실제 RR << 설계 RR** | HIGH | 설계 RR 2.0이지만 실제 avg_win/avg_loss = 0.86. Time exit와 structure break가 승리 크기 축소. |
| 4 | **일일 봉 pullback의 구조적 한계** | HIGH | ADX 20-28에서 pullback 방향 예측은 동전 던지기 수준. 해상도 부족. |
| 5 | **사전 crowding out 분석 미비** | MEDIUM | Panel #31/32에서 TP 추가 시 BM에 대한 영향을 전혀 분석하지 않았음. |

### 교훈: 새 전략 추가 전 필수 검증 체크리스트

향후 새 전략을 추가할 때 반드시 검증해야 할 항목:

```
[1] EDGE 검증:
    - 해당 전략의 statistical edge가 존재하는가?
    - Out-of-sample 데이터에서 PF > 1.3인가?
    - WR * avg_win > (1-WR) * avg_loss 인가?

[2] CROWDING OUT 분석:
    - 새 전략이 기존 전략의 거래 기회를 얼마나 감소시키는가?
    - Daily entry cap 소비량은?
    - Heat limit 소비량은?
    - Position cap 점유율은?
    - BM 거래수 변화를 반드시 tracking

[3] TRADE COUNT 검증:
    - 실제 거래수가 예측 범위 내인가?
    - 진입 조건의 개별 확률을 곱한 결합 확률로 검증

[4] ACTUAL RR 검증:
    - Time exit, strategy exit 등 비-SL/TP 퇴출에 의한 avg_win 축소 효과 분석
    - 이론적 RR이 아닌 실현 RR 기준으로 breakeven WR 계산

[5] NET IMPACT 검증:
    - 새 전략 PnL + BM PnL 변화 + MR PnL 변화 + Cash yield 변화 = Net impact
    - Net impact > 0이어야만 추가 정당화
```

---

## 5. Iter 29 Revert Specification

### What Changes in Iter 29

**원칙: Iter 27과 완전히 동일한 상태로 복귀. TP 관련 모든 변경을 제거하거나 비활성화.**

### 5.1 batch_simulator.py Changes

```python
# REVERT: _STRATEGY_NAMES에서 trend_pullback 제거
_STRATEGY_NAMES: list[str] = ["breakout_momentum", "rsi_mean_reversion"]

# REVERT: _GROUP_A에서 trend_pullback 제거
_GROUP_A: frozenset[str] = frozenset({"breakout_momentum", "rsi_mean_reversion"})

# REVERT: _STRATEGY_CLASSES에서 TrendPullback 제거
_STRATEGY_CLASSES = [
    BreakoutMomentum,
    RsiMeanReversion,
]

# REVERT: _SOFT_STRATEGY_CAP에서 trend_pullback 제거
_SOFT_STRATEGY_CAP: dict[str, int] = {
    "breakout_momentum": 2,      # LOCKED
    "rsi_mean_reversion": 4,     # Panel #31 LOCKED
}

# REVERT: _STRATEGY_BASE_RISK에서 trend_pullback 제거
_STRATEGY_BASE_RISK: dict[str, float] = {
    "breakout_momentum": 0.020,
    "rsi_mean_reversion": 0.015,
}

# REVERT: _STRATEGY_GDR_THRESHOLDS에서 trend_pullback 제거
_STRATEGY_GDR_THRESHOLDS: dict[str, tuple[float, float]] = {
    "breakout_momentum": (0.04, 0.08),
    "rsi_mean_reversion": (0.02, 0.04),
}

# REVERT: _MAX_PORTFOLIO_HEAT_PCT 40% -> 35% (Iter 27 value)
_MAX_PORTFOLIO_HEAT_PCT: float = 0.35

# REVERT: _MAX_DAILY_ENTRIES 4 -> 3 (Iter 27 value)
_MAX_DAILY_ENTRIES: int = 3

# TrendPullback import 제거 (또는 주석 처리)
# from autotrader.strategy.trend_pullback import TrendPullback  # DISABLED
```

### 5.2 regime_classifier.py Changes

```python
# REVERT: trend_pullback 관련 항목 제거
# 모든 regime에서 "trend_pullback" key와 "tp_blocked" key 제거

Regime.TREND_UP: {
    "breakout_momentum": 0.040,
    "rsi_mean_reversion": 0.012,
    "breakout_blocked": False,
    "mr_short_blocked": True,
},
# ... 다른 regime도 동일하게 trend_pullback / tp_blocked 제거
```

### 5.3 What Does NOT Change

| Parameter | Value | Status |
|-----------|-------|--------|
| BM all parameters | Iter 23 values | LOCKED |
| MR all parameters | Iter 23 values | LOCKED |
| MR cap | 4 | LOCKED (Panel #32) |
| Risk per trade BM/MR | 2.0%/1.5% | LOCKED |
| BM cap | 2 | LOCKED (Iter 30에서 3으로 변경 테스트 예정) |
| Cash yield | 4.75% annual | LOCKED |
| Warmup preload | 80 bars | LOCKED |
| Safety Net DD | 12% | LOCKED |
| Safety Net Recovery | 8% | LOCKED |
| Stage2 Profit Lock | 0.4 ATR | LOCKED |
| MAX_LONG | 8 | LOCKED |
| MAX_TOTAL | 9 | LOCKED |
| Trailing distance | 2.0 ATR | LOCKED |
| Trailing activation | 1.5 ATR (BM) | LOCKED |

### 5.4 trend_pullback.py 파일

**코드 삭제하지 않는다.** 파일은 유지하되 batch_simulator에서 import/사용하지 않도록 한다. 향후 참조용으로 보존.

---

## 6. Expected Iter 29 Results

### Reproducibility Test (Iter 27 재현)

| Metric | Iter 27 Reference | Iter 29 Expected | Tolerance |
|--------|-------------------|------------------|-----------|
| P1 Return | +11.4% | +11.0-12.0% | +/-1%p |
| P2 Return | +13.3% | +12.8-13.8% | +/-1%p |
| Combined | +24.7% | +23.8-25.8% | +/-1%p |
| P1 MaxDD | 20.2% | 18-22% | +/-2%p |
| P2 MaxDD | 3.0% | 2-5% | +/-2%p |
| P1 BM trades | 44 | 40-48 | +/-4 |
| P2 BM trades | 49 | 45-53 | +/-4 |
| P1 MR trades | 16 | 14-18 | +/-2 |
| P2 MR trades | 18 | 16-20 | +/-2 |

### Success / Failure Criteria

```
SUCCESS (Iter 27 재현 확인):
- Combined Return +23% ~ +26% (Iter 27의 +24.7% 기준 +/-1.7%p)
- BM P1 trades > 35 (Iter 27의 44 대비 80% 이상)
- MaxDD P1 < 23%
=> PROCEED to Iter 30 (BM cap 3 테스트)

PARTIAL (minor deviation):
- Combined Return +20% ~ +23%
- BM trade count partially recovered
=> INVESTIGATE: Iter 28의 코드 변경이 완전히 revert되지 않았을 가능성

FAILURE (not reproduced):
- Combined Return < +20%
- BM trades still < 30
=> CRITICAL BUG: line-by-line code diff 필요
```

---

## 7. Forward Plan: Iter 30+ Roadmap

### Phase 2 (Revised): BM Cap 3 Test

**전제조건**: Iter 29에서 Iter 27 재현 확인

```python
# Iter 30 유일한 변경:
_SOFT_STRATEGY_CAP = {
    "breakout_momentum": 3,      # 2 -> 3 (capacity expansion of proven strategy)
    "rsi_mean_reversion": 4,     # LOCKED
}
```

**예상 효과:**
- BM 추가 거래: +12-18건/년 (기존 44-49건의 25-37% 증가)
- 추가 수익: +$1,400-2,100/yr (BM avg $117/trade 기준)
- Combined Return 증가: +1.4-2.1%p/yr = +2.8-4.2%p over 2yr
- 예상 Combined: +27-29%
- MaxDD 영향: +1-3%p (동시 BM 3건 SL worst case = 6%)

**BM cap 3의 장점 vs TP 추가:**
| Factor | BM Cap 3 | TP 추가 |
|--------|---------|---------|
| Edge 확인 | PF 2.0-3.3 (검증됨) | PF 0.7-1.1 (edge 없음) |
| Crowding out | 없음 (같은 전략의 확장) | 심각 (-55% BM trades) |
| 구현 리스크 | 숫자 1개 변경 | 새 전략 전체 구현 |
| MaxDD 영향 | +1-3%p (수용 가능) | +19.4%p (재앙) |
| Return 기여 | +2.8-4.2%p (확실) | -5.1%p (악화) |

### Phase 3 Options (Iter 30 결과 후 결정)

```
Option 1: 현 수준 수용 (Combined +27-29%, S&P gap -2 ~ -4%p)
- 추가 리스크 없음
- Cash yield가 안정적 기여
- Risk-adjusted return 유지

Option 2: BM SL/TP 미세 조정 (Panel에서 논의 후)
- BM의 avg_win 증가 방안 (TP 4.0 -> 4.5? 또는 trailing 최적화)
- 매우 신중하게 접근 (Iter 24의 교훈)

Option 3: 새 3rd 전략 (완전히 다른 접근)
- Sector momentum rotation (주간 rebalancing)
- Earnings reaction strategy (event-driven)
- Market microstructure (intraday는 현재 불가)
- 충분한 사전 분석 후 Panel에서 논의

Option 4: Core+Satellite (유보, S&P gap > 5%p 시 재논의)
```

---

## 8. Panel Minority Opinions and Debates

### Debate 1: 'ADX Dead Zone' 개념의 유효성

- **Strat-1**: "Dead zone 자체는 존재한다. 문제는 pullback이 아닌 다른 접근법이 필요하다는 것이다. Sector rotation이나 market-neutral pair trading이 이 구간에서 더 적합할 수 있다."
- **Strat-4**: "Dead zone을 '채워야 할 공백'으로 보는 시각 자체가 틀렸다. 이 구간은 시장이 방향을 제시하지 않는 구간이므로, 그냥 쉬는 것(현금 보유)이 최선일 수 있다."
- **Strat-2**: "데이터가 Strat-4를 지지한다. TP의 dead zone(ADX 20-28) 거래 추정 70건의 net PnL은 음수일 가능성이 높다."
- **결정**: **Dead zone 전략은 더 이상 추구하지 않는다. Cash yield가 idle 기간의 최선의 전략.**

### Debate 2: BM Cap 3의 타이밍

- **Strat-1**: "Iter 29와 Iter 30을 동시에 (TP 제거 + BM cap 3). 두 변경은 독립적이다."
- **Strat-2**: "Single variable testing 원칙. Iter 29에서 Iter 27 재현 먼저. Iter 30에서 BM cap 3."
- **Strat-3**: "Strat-2에 동의. Iter 28의 교훈은 '하나만 바꿔라'. TP 제거와 BM cap 3을 동시에 하면 어떤 변경이 어떤 효과를 낸 것인지 분리 불가."
- **결정**: **Sequential testing 유지. Iter 29 = TP 제거만. Iter 30 = BM cap 3만.**

### Debate 3: TP 코드 완전 삭제 vs 비활성화

- **Strat-1**: "코드 유지, batch_simulator에서 비활성화. 향후 참조용."
- **Strat-3**: "완전 삭제. 코드가 남아있으면 누군가 다시 활성화할 유혹이 있다."
- **Strat-2**: "비활성화 찬성. 코드 자체는 교육적 가치가 있다."
- **결정**: **비활성화 (코드 유지, _STRATEGY_NAMES에서만 제거). 3:1.**

---

## 9. DO NOT CHANGE (Locked Parameters -- Updated)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | LOCKED (Iter 30 재검토 예정) |
| MR soft cap | batch_simulator.py | 4 | Panel #32 LOCKED |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| BM TP ATR mult | exit_rules.py | 4.0 | Panel #27 decision |
| BM trailing activation | exit_rules.py | 1.5 | Iter 23 validated |
| BM trailing distance | exit_rules.py | 2.0 | Panel #30 confirmed |
| BM GDR thresholds | batch_simulator.py | (0.04, 0.08) | Iter 23 validated |
| MR GDR thresholds | batch_simulator.py | (0.02, 0.04) | Iter 23 validated |
| MR all entry params | rsi_mean_reversion.py | RSI30/75, BB0.05/0.95, ADX<20 | LOCKED |
| MAX_LONG | batch_simulator.py | 8 | LOCKED |
| MAX_TOTAL | batch_simulator.py | 9 | LOCKED |
| Risk per trade (BM) | batch_simulator.py | 2.0% | LOCKED |
| Risk per trade (MR) | batch_simulator.py | 1.5% | LOCKED |
| Cash yield rate | batch_simulator.py | 4.75% annual | LOCKED |
| Warmup preload | batch_simulator.py | 80 bars | LOCKED |
| Safety Net DD | batch_simulator.py | 12% | LOCKED |
| Safety Net Recovery | batch_simulator.py | 8% | LOCKED |
| Stage2 Profit Lock | exit_rules.py | 0.4 (BM) | Iter 23 value |
| _MAX_PORTFOLIO_HEAT_PCT | batch_simulator.py | **0.35** | **REVERTED from 0.40** |
| _MAX_DAILY_ENTRIES | batch_simulator.py | **3** | **REVERTED from 4** |

---

## 10. Iteration History (Updated)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 (LOCKED) |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | MR cap3, heat 35%, TP 4.0, trail 1.5 |
| 24 | -0.69% | +0.19% | -0.5% | 21.8% | 4.34% | DD reduction (OVER-CORRECTED) |
| 25 | +1.76% | +3.40% | +5.16% | ? | ? | Partial rollback |
| **26** | **+7.5%** | **+7.9%** | **+15.4%** | **~20%** | **~21%** | Clean revert to Iter 23 |
| **27** | **+11.4%** | **+13.3%** | **+24.7%** | **20.2%** | **3.0%** | Phase 1: Cash yield + Warmup + MR cap 4 |
| **28** | **+7.3%** | **+12.3%** | **+19.6%** | **21.7%** | **22.4%** | **Phase 2: Trend Pullback ADDED -> REGRESSION** |
| 29 (target) | +11.4% | +13.3% | **+24.7%** | ~20% | ~3% | **Revert to Iter 27 (TP removed)** |
| 30 (target) | +12.5% | +14.5% | **+27.0%** | ~22% | ~5% | **BM cap 2 -> 3** |

---

## 11. Key Principles Reinforced and New Lessons

### Principles from Previous Panels (Confirmed)

1. **Parameter tuning 시대는 끝났다.** Iter 23 baseline의 파라미터는 최적이며, 10+ 이터레이션의 조정이 모두 net-negative였다. 이번에도 새 전략 추가가 기존 baseline을 악화시켰다.

2. **Cash yield는 시스템의 구조적 장점이다.** TP를 제거하고 현금을 유지하는 것이 TP로 거래하는 것보다 +$3,816 더 나은 결과를 만든다. '아무것도 안 하는 것'이 '나쁜 일을 하는 것'보다 낫다.

3. **Single variable testing은 절대 원칙이다.** Panel #32에서 이 원칙을 천명했고, 이번에도 그 가치가 입증되었다. TP 추가의 영향을 정확히 분리할 수 있었다.

### New Lessons from Iter 28

4. **새 전략 추가 시 crowding out 효과를 반드시 분석해야 한다.** TP의 가장 큰 피해는 직접 손실(-$3,016)이 아니라 BM 거래 55% 감소에 의한 간접 손실(~$5,000+)이었다. 향후 새 전략 추가 전에 기존 전략의 거래 기회 감소를 정량적으로 예측해야 한다.

5. **'빈 공간을 채운다'가 항상 좋은 것은 아니다.** ADX 20-28 dead zone은 시장이 방향을 제시하지 않는 구간이다. 이 구간에서 방향성 전략을 강행하는 것보다 현금 보유(cash yield)가 더 나은 결과를 만든다.

6. **이론적 RR과 실현 RR은 다르다.** TP의 설계 RR 2.0 (SL 1.5, TP 3.0)이지만 실제 avg_win/avg_loss = 0.86이었다. Time exit, structure break 등 비-SL/TP 퇴출 경로가 실현 RR을 크게 왜곡한다. 향후 전략 설계 시 모든 exit 경로를 고려한 실현 RR을 추정해야 한다.

7. **검증된 전략의 확장이 새 전략 추가보다 안전하다.** BM cap 2 -> 3은 검증된 edge(PF 2.0-3.3)의 활동 범위를 넓히는 것이다. 새 전략 추가는 edge 존재 자체가 불확실하다. 가능한 한 검증된 전략의 capacity를 먼저 확장해야 한다.

8. **예측은 검증 가능한 수치로 제시하고, 실제 결과와 반드시 대조해야 한다.** Panel #31/32의 예측(TP 25-40건/yr, PF > 1.2, Combined +28%)이 모두 틀렸다. 이것은 예측 자체가 잘못된 것이 아니라, 예측의 기반 가정(진입 조건 선택성, RR 실현율)이 검증되지 않았기 때문이다.

---

## 12. Action Items

### Immediate (Iter 29 -- TP 제거, Iter 27 복귀)

| # | Action | File(s) | Owner | Est. Time |
|---|--------|---------|-------|-----------|
| 1 | TP를 _STRATEGY_NAMES, _GROUP_A, _STRATEGY_CLASSES에서 제거 | batch_simulator.py | Dev-2 | 15 min |
| 2 | TP 관련 config 제거 (_SOFT_STRATEGY_CAP, _BASE_RISK, _GDR) | batch_simulator.py | Dev-2 | 10 min |
| 3 | Heat 40% -> 35%, Daily entries 4 -> 3 복귀 | batch_simulator.py | Dev-2 | 5 min |
| 4 | Regime allocator에서 TP 관련 항목 제거 | regime_classifier.py | Dev-2 | 10 min |
| 5 | Run Iter 29 backtest (P1 + P2) | backtest runner | Dev-2 | 0.5 day |
| 6 | Iter 27 재현 확인 (BM trades > 35, Combined +23-26%) | - | Strategy Team | After results |

### Next Phase (Iter 30 -- BM Cap 3, Iter 29 검증 후)

| # | Action | File(s) | Owner | Est. Time |
|---|--------|---------|-------|-----------|
| 7 | BM cap 2 -> 3 | batch_simulator.py | Dev-2 | 5 min |
| 8 | Run Iter 30 backtest (P1 + P2) | backtest runner | Dev-2 | 0.5 day |
| 9 | Panel #34: Iter 30 결과 리뷰 | docs/analysis/ | Strategy Team | After results |

### Backlog (Post Phase 2 Revised)

| # | Item | Priority | Condition |
|---|------|----------|-----------|
| B1 | EXIT_REASON 세분화 (stop_loss_initial vs upgraded) | LOW | Phase 3+ |
| B2 | Core+Satellite architecture | DEFERRED | S&P gap > 5%p after BM cap 3 |
| B3 | Universe expansion | DEFERRED | Phase 3+ |
| B4 | New 3rd strategy (non-pullback, non-dead-zone) | DEFERRED | Full pre-validation required |
| B5 | Intraday timeframes exploration | DEFERRED | Major architecture change |

---

## Appendix A: TP Failure Decomposition Chart

```
Iter 28 Combined Return +19.6% (REGRESSION from +24.7%)

           Iter 27         Iter 28        Delta
           +24.7%          +19.6%         -5.1%p
           +------+        +------+       +------+
 BM PnL   |+$10.9K|       |+$10.6K| -->  | -$0.3K| BM quality up, qty down
           |       |       |       |       |       |
 MR PnL   | +$6.4K|       | +$5.0K| -->  | -$1.3K| MR slightly crowded
           |       |       |       |       |       |
 Cash Yld  | +$7.0K|       | +$6.2K| -->  | -$0.8K| Less idle cash
           |       |       |       |       |       |
 TP PnL   |   $0  |       | -$3.0K| -->  | -$3.0K| Direct TP losses
           +------+        +------+       +------+
 Total     +$24.3K         +$18.8K        -$5.4K

TP의 총 영향: -$5.4K = 직접 손실 -$3.0K + BM 간접 -$0.3K + MR 간접 -$1.3K + Cash -$0.8K
```

## Appendix B: BM Trade Count Impact

```
BM Trades by Period:

         Iter 27        Iter 28       Change
P1:      44 trades      17 trades     -27 (-61%)  <-- DEVASTATING
P2:      49 trades      25 trades     -24 (-49%)  <-- SEVERE
Total:   93 trades      42 trades     -51 (-55%)

Lost BM trades value (estimated):
- 51 trades * $117 avg PnL = $5,967 opportunity cost
- This alone exceeds the total regression (-$5,100)
- TP's direct PnL (-$3,016) is ADDITIONAL to this

Root cause: TP consumed daily entry cap (4), heat limit (40%), and position slots
before BM could enter on its high-quality signals.
```

## Appendix C: Strategy Role (Iter 27 vs Iter 28)

```
Iter 27 (BM + MR, Working System):
  Revenue Mix:
  +-----------------------------------------------+
  | BM: +$10,914 (45%)    ████████████             | <- Primary earner
  | MR: +$6,369  (26%)    ███████                  | <- Complementary
  | Cash: +$7,000 (29%)   ████████                 | <- Stable income
  +-----------------------------------------------+
  Total: +$24,283

Iter 28 (BM + MR + TP, BROKEN System):
  +-----------------------------------------------+
  | BM: +$10,620 (56%)    ████████████             | <- Still good but fewer trades
  | MR: +$5,047  (27%)    ██████                   | <- Slightly reduced
  | Cash: +$6,200 (33%)   ███████                  | <- Reduced (less idle)
  | TP: -$3,016  (-16%)   ▓▓▓▓▓▓                   | <- VALUE DESTROYER
  +-----------------------------------------------+
  Total: +$18,851
```

## Appendix D: Forward Plan Projection

```
    Return %   S&P +31.4%
    32% |  - - - - - - - - - - - - - - S&P - - - - - - -
        |
    30% |
        |                                    Iter 30 (BM cap 3, optimistic)
    28% |                              ___---+
        |                        ___---
    26% |                  ___---         Iter 30 (BM cap 3, conservative)
        |            ___---
    25% |===  Iter 27/29 (+24.7%) *** RESTORED BASELINE ***
        |
    20% |--- Iter 28 (+19.6%) *** FAILED EXPERIMENT ***
        |
    16% |===  Iter 23/26 Baseline (+15.4%)
        |
    12% |
        +----+----+----+----+----+----+----
             Baseline  Iter27  Iter28  Iter29  Iter30
                       (P1)    (TP     (revert) (BM
                               fail)           cap3)

Path:  +15.4% -> +24.7% -> +19.6% [WRONG TURN] -> +24.7% -> +27%
                                    ^^^^^^^^^^^^
                                    We are here, reverting
```
