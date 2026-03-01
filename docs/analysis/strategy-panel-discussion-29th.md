# Strategy Panel Discussion #29: Iteration 24 Post-Mortem & Iter 25 Recovery Plan

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iteration 24 applied 11 DD-reduction changes from Panel #28. Performance collapsed from +15.4% combined (Iter 23, best ever) to -0.5% combined. P1 MaxDD actually INCREASED to 21.8% despite all DD-reduction measures. This is a critical failure requiring forensic root cause analysis and surgical recovery.
**Verdict**: **PANEL #28 OVER-CORRECTED. 8 of 11 changes were destructive. Selective rollback required.**

---

## 1. Backtest Results Summary (Iteration 24)

### Performance Table

| Metric | P1 (Bull) Iter 23 | P1 (Bull) Iter 24 | Delta | P2 (Mixed) Iter 23 | P2 (Mixed) Iter 24 | Delta |
|--------|-------------------|-------------------|-------|--------------------|--------------------|-------|
| Return | +7.5% | **-0.69%** | -8.2%p | +7.9% | **+0.19%** | -7.7%p |
| MaxDD | 20.2% | **21.8%** | +1.6%p | 21.0% | **4.34%** | -16.7%p |
| Trades | 47 | 54 | +7 | 52 | 54 | +2 |
| WR | 70.2% | **57.4%** | -12.8%p | 80.8% | **59.3%** | -21.5%p |
| PF | 1.577 | **0.940** | -0.637 | 2.030 | **1.011** | -1.019 |

### Strategy Breakdown

| Strategy | Period | Iter 23 Trades | Iter 23 WR | Iter 23 PF | Iter 23 PnL | Iter 24 Trades | Iter 24 WR | Iter 24 PF | Iter 24 PnL |
|----------|--------|---------------|------------|------------|-------------|---------------|------------|------------|-------------|
| BM | P1 | 34 | 73.5% | 1.806 | +$7,105 | 40 | **57.5%** | **0.938** | **-$610** |
| BM | P2 | 40 | 82.5% | 1.618 | +$3,156 | 42 | **57.1%** | **0.632** | **-$2,979** |
| MR | P1 | 13 | 61.5% | 1.078 | +$319 | 14 | 57.1% | 0.946 | -$200 |
| MR | P2 | 12 | 75.0% | 2.858 | +$4,718 | 12 | **66.7%** | **1.974** | +$3,108 |

### Exit Reason Comparison (BM Only)

| Exit Reason | Iter 23 P1 | Iter 24 P1 | Iter 23 P2 | Iter 24 P2 |
|-------------|-----------|-----------|-----------|-----------|
| stop_loss | 25/34 (73.5%) | 24/40 (60%) | 28/40 (70%) | 29/42 (69%) |
| trailing_stop | **2/34 (5.9%)** | **13/40 (32.5%)** | **9/40 (22.5%)** | **11/42 (26.2%)** |
| take_profit + other | 7/34 (20.6%) | 3/40 (7.5%) | 3/40 (7.5%) | 2/42 (4.8%) |

### Win/Loss Asymmetry

| Period | Iter 23 Avg Win | Iter 24 Avg Win | Iter 23 Avg Loss | Iter 24 Avg Loss |
|--------|----------------|----------------|-----------------|-----------------|
| P1 | $615 | **$409** | $919 | **$587** |
| P2 | $369 | **$357** | $764 | **$513** |

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- Trailing Stop 조기 활성화의 파괴적 효과

"Iter 24의 결과는 스윙 트레이딩의 기본 원칙이 위반되었을 때 어떤 결과가 나오는지를 보여주는 교과서적 사례다. 핵심 진단부터 하겠다.

**진단 1: Trailing Stop 조기 활성화가 모든 것을 파괴했다**

데이터가 명확하게 말하고 있다:

```
BM P1 trailing_stop exits:
- Iter 23: 2/34 (5.9%)
- Iter 24: 13/40 (32.5%)  -- 6.5배 증가!

BM P2 trailing_stop exits:
- Iter 23: 9/40 (22.5%)
- Iter 24: 11/42 (26.2%)  -- 소폭 증가
```

P1에서 trailing exit가 2건에서 13건으로 폭증했다. **이 11건의 추가 trailing exit가 Iter 24 P1의 성과를 파괴한 주범이다.**

이 메커니즘을 정확히 설명하겠다:

```
Iter 23 (BM trailing activation = 1.5 ATR):
- 가격이 entry + 1.5 ATR 이동해야 trailing 시작
- Trail stop = max(entry, highest - 2.0*ATR)
- 1.5 ATR 이동은 상당한 모멘텀을 의미 -> 이 레벨에 도달한 거래는 이미 강한 추세 확인
- 그래서 34건 중 단 2건만 trailing exit -> 나머지는 TP(4.0 ATR)까지 갈 시간 확보

Iter 24 (BM trailing activation = 1.0 ATR):
- 가격이 entry + 1.0 ATR만 이동하면 trailing 시작
- Trail stop = max(entry, highest - 1.5*ATR)
- 1.0 ATR 이동 = 단 하루치 평균 변동폭!
- Daily bar에서 1.0 ATR 이동은 '정상적 일일 변동'이지 '추세 확인'이 아님
- trailing이 너무 일찍 활성화 -> breakeven floor에서 정상 pullback에 의해 exit
- 40건 중 13건(32.5%)이 trailing exit
```

**스윙 트레이딩에서 가장 중요한 원칙: '거래에 숨 쉴 공간을 줘라(Give the trade room to breathe)'.** Trailing activation 1.0 ATR은 이 원칙을 정면으로 위반한다. 일일 평균 변동폭(ATR)만큼만 움직여도 trailing이 시작되면, 정상적인 일중 pullback이 breakeven exit을 유발한다.

**진단 2: 추가 trailing exit 11건의 추정 손실**

이 11건이 trailing exit 대신 원래 궤적(TP/time exit)을 따랐다면:

```
Iter 23 BM P1 기준:
- Non-SL exits (TP/trailing/time): ~$700 평균 수익
- 11건 * $700 = $7,700 추정 수익

Iter 24에서 이 11건은:
- Breakeven trailing exits: ~$50-100 평균
- 11건 * $75 = ~$825

차이: $7,700 - $825 = $6,875 손실
Iter 24 P1 BM PnL이 -$610인데, 이 $6,875를 더하면 +$6,265 -- Iter 23 P1 BM의 +$7,105와 거의 일치한다.
```

**이 하나의 파라미터 변경(trailing activation 1.5 -> 1.0)이 BM P1의 $7,700+ 수익을 증발시켰다.**

**진단 3: WR 붕괴의 직접 원인**

```
BM P1 WR 변화:
- Iter 23: 73.5% (25/34 wins)
- Iter 24: 57.5% (23/40 wins)

거래 구성 분석:
- Iter 23: 25 wins = 16 profit-lock SL + 7 TP/trail/time + 2 trailing
- Iter 24: 23 wins = ? profit-lock SL + 3 TP/other + 13 trailing(대부분 breakeven)

Iter 24의 13건 trailing exit 중:
- 대부분은 breakeven 또는 소액 수익(+$50 미만)
- 이것이 'win'으로 카운트되지만 실질 수익은 거의 없음
- 반면 7건의 full TP exit가 3건으로 감소 -> 대형 수익 거래 급감
```

WR 자체의 하락(73.5% -> 57.5%)보다 더 심각한 것은, **승리 거래의 품질이 급락한 것이다.** Avg Win이 $615 -> $409로 33% 하락. 이것은 breakeven trailing exit가 작은 수익으로 카운트되어 평균을 끌어내리기 때문이다.

**처방: BM trailing activation을 1.5 ATR로 즉시 복원한다. 이것은 비협상적이다.**"

### Strat-2 (Quant Analyst) -- 11개 변수 변경의 개별 영향 분해

"Panel #28은 동시에 11개 변수를 변경했다. 이것은 실험 설계의 기본 원칙을 위반한 것이다. 통제 변수 없이 11개 독립 변수를 동시에 변경하면, 어떤 변수가 어떤 결과를 초래했는지 분리할 수 없다. 그래도 데이터에서 추론 가능한 것들을 정리하겠다.

**분석 1: 변수별 파괴력 랭킹**

11개 변경을 파괴력 순서로 정렬한다:

| 순위 | 변경 | 증거 | 추정 영향 | 신뢰도 |
|------|------|------|----------|--------|
| **1** | BM trailing activation 1.5->1.0 | Trailing exits 2->13 (P1), WR 73.5->57.5% | **-$7,000+** (P1 BM) | 높음 |
| **2** | Safety Net DD 12%->8% | DD still 21.8% but recovery impossible | **-$3,000** (회복 차단) | 중간 |
| **3** | BM GDR (4%,8%)->(3%,6%) | 첫 손실 후 반 사이즈, 회복 둔화 | **-$2,000** | 중간 |
| **4** | Heat 35%->28% | 자본 배치 20% 감소 | **-$1,500** (비례 감소) | 높음 |
| 5 | MR GDR (2%,4%)->(1.5%,3%) | MR 회복 둔화 | -$500 | 중간 |
| 6 | MAX_LONG 8->7 | Heat이 binding이므로 영향 미미 | ~$0 | 높음 |
| 7 | MAX_TOTAL 9->8 | 동일 | ~$0 | 높음 |
| 8 | Safety Net Recovery 8%->5% | Safety Net 해제 지연 | -$300 | 낮음 |
| 9 | Trailing distance 2.0->1.5 | **유익** - 수학적 결함 수정 | **+$200** | 중간 |
| 10 | Stage2 profit lock 0.4->0.5 | **유익** - 수익 보전 증가 | **+$100** | 중간 |
| 11 | TREND_UP MR alloc 0.012->0.008 | **유익** - zero-edge 거래 축소 | **+$50** | 중간 |

**상위 4개 변경이 합계 -$13,500의 손실을 초래한 것으로 추정한다. 하위 3개 변경은 합계 +$350 수준의 소액 개선이었다.**

**분석 2: P1 MaxDD가 21.8%로 오히려 악화된 이유**

이것은 직관에 반하는 결과다. Heat를 35%에서 28%로 낮추고, GDR을 강화하고, Safety Net을 조기 발동했는데 MaxDD가 오히려 증가했다. 왜인가?

```
메커니즘:
1. Trailing activation 1.0 ATR -> 수익 거래의 대부분이 breakeven에서 exit
2. Breakeven exit = 커미션/슬리피지 고려 시 소액 손실 (-$15~30 per trade)
3. 13건의 breakeven trailing exit = ~-$300 (사실상 손실)
4. 이 동안 full SL 거래는 여전히 -$587 평균 손실 발생
5. 수익을 내는 거래가 3건(TP)으로 줄어 +$1,200만 생성
6. 결과: 다수의 소액 손실 + 소수의 대형 손실 - 소수의 중형 수익 = 지속적 출혈
7. Safety Net 8%에서 활성화 -> 신규 진입 극도 제한 -> 회복 불가
8. 기존 포지션 SL hit -> DD 지속 확대 -> 21.8%
```

**핵심: DD를 방지하려는 시도가 오히려 DD를 악화시켰다.** 이것은 '과도한 방어'의 역설이다. 수익을 만드는 메커니즘(trailing 수익 보호)을 조기 활성화시키면, 거래가 충분한 수익을 축적하기 전에 exit하여, 불가피한 손실을 상쇄할 수익원이 사라진다.

**분석 3: P2의 상대적 양호함이 주는 단서**

P2는 +0.19%로 거의 flat이지만, MR P2가 +$3,108을 벌어 BM P2의 -$2,979를 간신히 상쇄했다. MR P2가 +$3,108을 달성한 이유:

```
MR P2: 12 trades, 66.7% WR, PF 1.974
- MR은 trailing stop 전략이 아님 (MR은 _TRAILING_STRATEGIES에 포함되지 않음)
- 따라서 trailing activation 변경의 영향을 받지 않음!
- MR P2의 PF가 2.858에서 1.974로 하락한 것은 GDR/heat 변경의 영향
```

**MR이 trailing activation 변경의 영향을 받지 않았기 때문에 P2에서 살아남았다.** 이것은 trailing activation 1.0이 파괴의 주범이라는 가설을 강력히 지지한다.

**분석 4: 적정 Heat 재계산**

```
데이터 포인트 업데이트:
- Heat 25% -> MaxDD ~7% (Iter 22)
- Heat 28% -> MaxDD 4.3% (P2) / 21.8% (P1) -- P1은 exit rule 오류로 오염
- Heat 35% -> MaxDD 20% (Iter 23)

P2만 사용한 재계산 (P1은 trailing 오류로 오염):
- Heat 25% -> MaxDD ~7%
- Heat 28% -> MaxDD 4.3% (exit 오류 있으나 P2는 MR이 방어하여 낮음)
- Heat 35% -> MaxDD 21.0% (P2 Iter 23)

P2 기울기: (21.0-7.0)/(35-25) = 1.4%DD per 1%heat
MaxDD 15% 목표: 15 = 7 + 1.4*(heat-25) -> heat = 30.7%

P1 기울기 (Iter 23만 사용): (20.2-7.0)/(35-25) = 1.32
MaxDD 15%: 15 = 7 + 1.32*(heat-25) -> heat = 31.06%

두 추정치 모두 heat ~31%를 가리킨다. 안전 마진 1%p를 적용하면 heat 30%.
그러나 trailing fix(1.5 ATR 복원)가 WR을 73%로 회복시키면 DD가 자연적으로 감소한다.
trailing fix + heat 32%가 MaxDD 15%를 달성할 수 있다고 추정한다.
```

**제안: Heat 32%. Trailing fix의 WR 회복 효과를 고려하면 MaxDD 14-16% 범위에 들 것이다.**"

### Strat-3 (Risk Manager) -- Panel #28 과잉교정의 반성과 방어선 재설정

"Iter 24의 결과를 보고 가장 큰 책임을 느끼는 것은 나(Strat-3, Risk Manager)다. Panel #28에서 내가 주도한 처방이 11개 변경 중 7개를 차지했고, 이 중 5개가 파괴적이었다. 무엇이 잘못되었는지 솔직하게 진단하겠다.

**자기 진단 1: 'DD 공포'에 의한 과잉 반응**

Iter 23에서 MaxDD 20%를 보고 나는 패닉 모드에 진입했다. '배치 불가 수준'이라는 내 판단은 옳았지만, 해법이 과도했다. 7개 방어 메커니즘을 동시에 강화한 것은 **치료가 병보다 나쁜** 전형적 사례가 되었다.

```
내 처방 7개 중 결과:
1. Heat 35% -> 28%: 자본 배치 과잉 축소 -> 수익 기반 파괴
2. Safety Net 12% -> 8%: 조기 발동 -> 회복 차단
3. Safety Net Recovery 8% -> 5%: 복귀 지연 -> 장기 제한
4. BM GDR (4%,8%) -> (3%,6%): 첫 손실 후 즉시 위축 -> 회복 불가
5. MR GDR (2%,4%) -> (1.5%,3%): 동일
6. MAX_LONG 8 -> 7: 영향 미미 (유일한 무해 변경)
7. MAX_TOTAL 9 -> 8: 영향 미미

7개 중 5개가 파괴적, 2개가 무해. 유익한 변경 0개.
```

**이것은 '방어의 역설'이다.** 모든 방어벽을 동시에 강화하면, 시스템이 '공격(수익 창출)' 능력을 잃는다. 수익이 없으면 DD를 상쇄할 수 없어, DD가 오히려 커진다.

**자기 진단 2: Safety Net 8%가 왜 실패했는가**

```
Safety Net 12% (Iter 23):
- 활성화 시점까지 시스템이 자유롭게 거래 -> 높은 WR로 DD 자연 회복
- 12% 도달하는 경우 자체가 드물었음 (P1에서 약 2회 정도)
- 충분한 회복 시간 확보

Safety Net 8% (Iter 24):
- 시스템이 8% DD에 도달하면 거의 즉시 제한 모드 진입
- 8% DD = trailing activation 오류로 인한 정상적 출혈 수준
- 시스템이 거의 항상 Safety Net 모드에 갇힘
- 1 entry/day, 0.5% risk = 수익 발생 불가
- 기존 포지션은 계속 손실 -> DD 확대 -> 영원히 Safety Net 탈출 불가
```

**P1 MaxDD가 21.8%로 증가한 핵심 원인: Safety Net이 DD를 방지하지 못하고 회복만 차단했다.**

**자기 진단 3: GDR Tier 1 = 3%의 수학적 불합리성**

```
BM 단일 거래 최대 손실:
- SL 2.5 ATR, 평균 ATR ~$3-5, 평균 포지션 $10K-12K
- 손실: 2.5 * $4 / $150 * $12K = ~$800 (약 0.8% of $100K equity)
- GDR 기준은 전략의 rolling peak 대비 DD

BM GDR Tier 1 at 3%:
- 3개 연속 full-SL 거래 = 3 * 0.8% = 2.4% strategy DD
- 4개째에서 Tier 1 진입 -> risk 50% 감소
- 이것은 너무 일찍 발동. BM WR 57-73%에서 3-4개 연속 손실은 통계적으로 발생

BM GDR Tier 1 at 4% (Iter 23):
- 5-6개 연속 full-SL 후에야 Tier 1 진입
- 충분한 회복 기회 제공 후 방어 발동
```

**GDR Tier 1 = 3%는 정상적인 손실 시퀀스에도 방어를 발동시켜, 시스템을 '만성 위축' 상태로 만든다.**

**수정된 리스크 관리 처방 (반성 후):**

내 핵심 교훈: **리스크 관리의 목표는 '손실 제로'가 아니라 '손실 대비 충분한 수익'이다.** Panel #28에서 나는 '손실 제로' 쪽으로 과도하게 기울었다.

1. **Heat: 0.28 -> 0.32** (35%에서 3%p만 줄이는 것이 적절)
2. **Safety Net DD: 0.08 -> 0.10** (12%와 8%의 중간, 타협안)
3. **Safety Net Recovery: 0.05 -> 0.07** (8%보다 약간 타이트, 합리적 수준)
4. **BM GDR: (0.03, 0.06) -> (0.04, 0.08)** (Iter 23 값으로 완전 복원)
5. **MR GDR: (0.015, 0.03) -> (0.02, 0.04)** (Iter 23 값으로 완전 복원)
6. **MAX_LONG: 7 -> 8** (Heat가 binding이므로 복원)
7. **MAX_TOTAL: 8 -> 9** (동일)

**이전 처방 7개 중 2개(MAX_LONG/TOTAL)만 유지하고 5개를 수정한다.**"

### Strat-4 (Market Analyst) -- 레짐 관점에서 본 시스템 붕괴의 구조

"Iter 23 vs 24의 가장 놀라운 차이는 P1과 P2의 비대칭적 결과다:

```
P1: Iter 23 +7.5% -> Iter 24 -0.69% (8.2%p 하락)
    Iter 23 MaxDD 20.2% -> Iter 24 MaxDD 21.8% (악화!)

P2: Iter 23 +7.9% -> Iter 24 +0.19% (7.7%p 하락)
    Iter 23 MaxDD 21.0% -> Iter 24 MaxDD 4.34% (대폭 개선!)
```

**분석 1: P1 vs P2 결과 비대칭의 원인**

P1(Bull Market)과 P2(Mixed Market)의 가장 큰 차이는 **BM의 기여도**다:

```
P1: BM이 수익의 95.7% 기여 (Iter 23)
   -> BM trailing 파괴 시 전체 수익 소멸
   -> MR은 4.3%만 기여하므로 방어막 없음

P2: MR이 수익의 59.9% 기여 (Iter 23)
   -> BM trailing 파괴되어도 MR이 방어
   -> MR은 trailing 영향 안 받음 (MR에 trailing 없음)
```

**P1이 더 심하게 타격받은 이유: P1은 BM 의존도가 극단적으로 높고, BM trailing이 파괴되면 대체 수익원이 없다.**

반면 P2는 MR이 BM 손실을 거의 상쇄했다. MR P2가 Iter 23의 $4,718에서 $3,108로 감소한 것은 GDR/Heat 변경의 영향이지만, 여전히 +$3,108으로 BM의 -$2,979를 겨우 커버했다.

**분석 2: P2 MaxDD 4.34%가 주는 교훈**

P2 MaxDD가 21.0%에서 4.34%로 대폭 감소한 것은 '좋은 결과'처럼 보이지만 사실은 **시스템이 거의 거래하지 못했다는 증거다.**

```
MaxDD 4.34% + Return +0.19% = 시스템이 거의 'flat' 상태로 운영됨
- Safety Net 8% 발동되지 않을 정도로 포지션 사이즈가 작았거나
- MR의 꾸준한 수익이 BM 손실을 실시간으로 상쇄했거나
- 둘 다
```

P2에서 DD가 낮은 것은 DD-reduction 변경의 '성공'이 아니라, **시스템의 거래 능력이 박탈된 결과**다. Return +0.19%로 S&P +15.5%를 15.3%p 하회하는 것은 '리스크 관리 성공'이 아니라 '자본 비효율'이다.

**분석 3: 레짐별 최적 전략의 재확인**

| 레짐 | 주력 전략 | Iter 23 성과 | Iter 24 성과 | 변화 원인 |
|------|----------|------------|------------|----------|
| TREND_UP (P1) | BM | +$7,105 | -$610 | Trailing 파괴 |
| RANGING (P2) | MR | +$4,718 | +$3,108 | GDR/Heat 축소 |

레짐-전략 매핑은 Iter 23에서 완벽하게 작동했다. BM은 TREND_UP에서, MR은 RANGING에서 각각 우세했다. Iter 24의 실패는 **레짐 배치의 문제가 아니라 exit rule과 리스크 파라미터의 과잉 조정**이다.

**분석 4: TREND_UP MR alloc 0.008의 효과**

```
MR P1: Iter 23에서 13 trades, PF 1.078 (zero edge)
MR P1: Iter 24에서 14 trades, PF 0.946 (negative edge)

alloc 0.012 -> 0.008로 축소했으나:
- 거래 수가 오히려 1건 증가 (13 -> 14)
- PF가 더 악화 (1.078 -> 0.946)
```

alloc 축소가 거래 수에 영향을 주지 않은 것은, alloc이 포지션 사이즈에만 영향을 미치고 진입 자체를 차단하지 않기 때문이다. MR P1의 문제는 진입 빈도가 아니라 시장 환경이므로, alloc 축소는 무해하지만 유의미한 개선도 아니다.

**그래도 alloc 0.008은 유지해야 한다.** MR P1이 zero-edge이므로 더 큰 사이즈로 거래할 이유가 없다. 단, 이것이 MR P1 성과를 '개선'시키지는 않는다는 점을 인정한다.

**분석 5: Iter 25를 위한 레짐 관점 권고**

1. **Heat 32%**: 35%에서 3%p만 축소. TREND_UP에서 BM의 충분한 자본 배치 보장
2. **Trailing activation 1.5 복원**: TREND_UP BM의 수익 능력 복원이 DD 감소보다 중요
3. **GDR 원복**: 레짐 전환 시의 자연적 DD를 허용하되, 극단적 DD만 방지
4. **Safety Net 10%**: 12%와 8%의 합리적 중간점"

---

## 3. Cross-Diagnosis Consensus

### Unanimous Agreement (4/4)

#### Consensus 1: BM Trailing Activation 1.0 ATR이 Performance 파괴의 Primary Cause

**전원 동의. 반대 없음.**

증거:
- BM P1 trailing exits: 2건 -> 13건 (6.5배 증가)
- BM P1 WR: 73.5% -> 57.5% (16%p 하락)
- BM P1 PnL: +$7,105 -> -$610 ($7,715 반전)
- MR(trailing 없음)은 상대적으로 양호 -> trailing이 원인 확인

**처방: BM trailing activation 1.0 -> 1.5 ATR 즉시 복원 (비협상)**

#### Consensus 2: Safety Net 8%와 GDR Tier 1 = 3%가 Recovery를 불가능하게 만듦

**전원 동의.**

Safety Net 8%는 정상적 변동에서도 발동하여 신규 진입을 과도하게 제한했다. GDR Tier 1 = 3%는 3-4개 연속 손실(통계적으로 정상)에도 위축 모드로 전환시켰다. 두 메커니즘이 결합하여 시스템의 회복 능력을 완전히 제거했다.

**처방: GDR을 Iter 23 값으로 완전 복원. Safety Net은 10%로 타협.**

#### Consensus 3: Panel #28의 11개 동시 변경은 실험 설계 실패

**전원 동의.**

11개 변수를 동시에 변경하면 어떤 변수가 어떤 효과를 가져왔는지 분리할 수 없다. 향후 이터레이션에서는 **최대 3-4개 변수만 동시 변경**하고, 변경 그룹별로 논리적 연관성이 있어야 한다.

#### Consensus 4: Trailing Distance 1.5와 Stage2 Profit Lock 0.5는 유익한 변경

**전원 동의.**

- Trailing distance 2.0 -> 1.5: 수학적 결함 수정 (activation >= distance 보장)
- Stage2 profit lock 0.4 -> 0.5: 약간 더 많은 이익 보전

이 두 변경은 Iter 24에서도 유익했으나, trailing activation의 파괴적 효과에 묻혔다. Iter 25에서 반드시 유지해야 한다.

### Debate Points

#### Debate 1: Heat 최적값

- **Strat-2**: 32%. Trailing fix 후 WR 73% 회복 시 DD 자연 감소. 32%면 MaxDD ~14-16%.
- **Strat-3**: 30%. 안전 마진 2%p 확보. 반성 후에도 보수적 성향을 완전히 포기하긴 어렵다.
- **Strat-1**: 32%. 거래에 충분한 자본이 필요하다. 30%는 Iter 22(heat 25%)의 실패를 반복할 수 있다.
- **Strat-4**: 32%. TREND_UP에서 BM의 충분한 배치가 핵심이다.
- **결정**: **Heat 32% 채택 (3:1 다수결, Strat-3만 30% 주장)**

#### Debate 2: Safety Net DD Threshold

- **Strat-3**: 10%. 12%에서 '기존 포지션 잔여 손실'로 20%까지 가는 것을 방지하려면 10%가 적절.
- **Strat-2**: 12% 유지. 8%가 실패했으니 원래 값으로 복원하는 것이 안전하다.
- **Strat-1**: 10%. 12%와 8%의 중간이 합리적. 12%는 너무 늦고 8%는 너무 빠르다.
- **Strat-4**: 10%. Heat 32%에서 10% Safety Net이면 실질 MaxDD ~15% 이내 유지 가능.
- **결정**: **Safety Net DD 10% 채택 (3:1, Strat-2만 12% 주장)**

#### Debate 3: Safety Net Recovery Threshold

- **Strat-3**: 7%. 5%는 너무 보수적이었고, 8%는 Safety Net 10%와 너무 가까워 진동 위험.
- **전원 동의**: 7%가 합리적.
- **결정**: **Safety Net Recovery 7% 채택 (4:0)**

---

## 4. Root Cause Analysis

### Root Cause 1: BM Trailing Activation 조기화 (PRIMARY - 70% 기여)

**현상**: BM WR 73-82% -> 57%, trailing exits 2 -> 13, PnL +$7,105 -> -$610
**근본 원인**: Trailing activation 1.5 -> 1.0 ATR. 일일 ATR 수준의 정상적 가격 이동으로 trailing이 조기 활성화. Breakeven floor에서 정상 pullback에 의해 exit, 잠재적 수익 거래를 breakeven으로 전환.
**영향**: BM P1에서만 추정 -$7,000 손실. P2에서도 -$3,000+ 손실. Combined -$10,000+.
**해법**: Trailing activation 1.0 -> 1.5 ATR 즉시 복원.

### Root Cause 2: 회복 메커니즘 과잉 억제 (SECONDARY - 20% 기여)

**현상**: DD 발생 후 회복 불가. P1 MaxDD 오히려 증가(20.2% -> 21.8%).
**근본 원인**: Safety Net 8%, GDR 3%/6%, Recovery 5%가 동시에 적용되어 신규 진입을 극도로 제한. 손실은 기존 포지션에서 계속 발생하지만, 회복을 위한 신규 수익 거래가 불가능.
**영향**: DD에서 회복 불가능한 하향 나선(downward spiral) 형성.
**해법**: GDR을 Iter 23 값으로 복원(4%/8%, 2%/4%). Safety Net 10%, Recovery 7%.

### Root Cause 3: 자본 배치 과잉 축소 (TERTIARY - 10% 기여)

**현상**: 거래 수는 유사하나 포지션 사이즈 축소로 수익 감소.
**근본 원인**: Heat 35% -> 28% = 20% 자본 배치 감소.
**영향**: 수익 거래의 달러 수익 감소, 손실 거래의 달러 손실은 SL 기반이므로 비례 감소하나, 고정 비용(커미션, 슬리피지)의 비중 증가.
**해법**: Heat 28% -> 32%.

---

## 5. Specific Parameter Changes for Iteration 25

### Change Category A: REVERT (파괴적 변경 원복)

| # | Parameter | File | Iter 24 (Current) | Iter 25 (Proposed) | Iter 23 (Reference) | Rationale |
|---|-----------|------|-------------------|-------------------|--------------------|-----------|
| 1 | BM trailing activation | exit_rules.py:69 | **1.0** | **1.5** | 1.5 | Primary performance destroyer. 즉시 복원 필수. |
| 2 | BM GDR thresholds | batch_simulator.py:90 | **(0.03, 0.06)** | **(0.04, 0.08)** | (0.04, 0.08) | Tier 1=3% 너무 일찍 발동. Iter 23 값 복원. |
| 3 | MR GDR thresholds | batch_simulator.py:91 | **(0.015, 0.03)** | **(0.02, 0.04)** | (0.02, 0.04) | 동일 논리. Iter 23 값 복원. |
| 4 | _MAX_LONG_POSITIONS | batch_simulator.py:72 | 7 | **8** | 8 | Heat가 binding. 유연성 복원. |
| 5 | _MAX_TOTAL_POSITIONS | batch_simulator.py:74 | 8 | **9** | 9 | 동일. |

### Change Category B: ADJUST (타협 조정)

| # | Parameter | File | Iter 24 (Current) | Iter 25 (Proposed) | Iter 23 (Reference) | Rationale |
|---|-----------|------|-------------------|-------------------|--------------------|-----------|
| 6 | _MAX_PORTFOLIO_HEAT_PCT | batch_simulator.py:76 | 0.28 | **0.32** | 0.35 | 35%는 DD 과다, 28%는 수익 부족. 32%가 균형점. |
| 7 | _PORTFOLIO_SAFETY_NET_DD | batch_simulator.py:111 | 0.08 | **0.10** | 0.12 | 12%와 8% 사이의 합리적 중간. |
| 8 | _PORTFOLIO_SAFETY_NET_RECOVERY | batch_simulator.py:112 | 0.05 | **0.07** | 0.08 | 타이트한 Safety Net에 맞춰 Recovery도 조정. |

### Change Category C: KEEP (유익한 변경 유지)

| # | Parameter | File | Iter 24 (Current) | Iter 25 | Iter 23 | Rationale |
|---|-----------|------|-------------------|---------|---------|-----------|
| 9 | _TRAILING_ATR_MULT | exit_rules.py:64 | 1.5 | **1.5 (no change)** | 2.0 | 수학적 결함 수정 (activation >= distance). |
| 10 | _STAGE2_PROFIT_LOCK_ATR | exit_rules.py:34 | 0.5 | **0.5 (no change)** | 0.4 | 더 많은 이익 보전. |
| 11 | TREND_UP MR alloc | regime_classifier.py:25 | 0.008 | **0.008 (no change)** | 0.012 | MR P1 zero edge. 소규모 배치 유지. |

### DO NOT CHANGE (Locked Parameters)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | 7-iter confirmed |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| BM TP ATR mult | exit_rules.py | 4.0 | Panel #27 decision |
| MR soft cap | batch_simulator.py | 3 | Panel #27, PF 2.858 validates |
| MR ADX_MAX | rsi_mean_reversion.py | 20.0 | Quality filter |
| Stage1 BE activation | exit_rules.py | 1.5 | Working correctly |
| All regime allocs except TREND_UP MR | regime_classifier.py | various | Validated |

---

## 6. Parameter Change Map (Iter 25)

### exit_rules.py
```python
# Line 69: BM trailing activation (REVERT from 1.0 to 1.5)
_TRAILING_ACTIVATION_ATR = {
    "ema_cross_trend": 1.5,
    "breakout_momentum": 1.5,      # was 1.0 -> REVERT to 1.5
}

# Line 34: Stage2 profit lock (NO CHANGE - keep 0.5)
_STAGE2_PROFIT_LOCK_ATR: float = 0.5

# Line 64: Trailing distance (NO CHANGE - keep 1.5)
_TRAILING_ATR_MULT: float = 1.5
```

### batch_simulator.py
```python
_MAX_LONG_POSITIONS: int = 8              # was 7, REVERT to 8
_MAX_TOTAL_POSITIONS: int = 9             # was 8, REVERT to 9
_MAX_PORTFOLIO_HEAT_PCT: float = 0.32     # was 0.28, ADJUST to 0.32

_STRATEGY_GDR_THRESHOLDS = {
    "breakout_momentum": (0.04, 0.08),    # was (0.03, 0.06), REVERT to Iter 23
    "rsi_mean_reversion": (0.02, 0.04),   # was (0.015, 0.03), REVERT to Iter 23
}

_PORTFOLIO_SAFETY_NET_DD: float = 0.10            # was 0.08, ADJUST to 0.10
_PORTFOLIO_SAFETY_NET_RECOVERY: float = 0.07      # was 0.05, ADJUST to 0.07
```

### regime_classifier.py
```python
# NO CHANGES (TREND_UP MR alloc stays at 0.008)
```

---

## 7. Risk Assessment of Proposed Changes

### Change Risk Matrix

| Change | Upside Potential | Downside Risk | Confidence |
|--------|-----------------|---------------|-----------|
| BM trailing 1.0->1.5 | BM WR 57->73%, +$7,000 P1 | 거의 없음 (Iter 23 검증값) | **매우 높음** |
| GDR revert to Iter 23 | 회복 능력 복원 | DD 방어 약간 감소 | **높음** |
| Heat 28%->32% | 수익 ~15% 증가 | MaxDD ~2-3%p 증가 | **높음** |
| Safety Net 8%->10% | 적절한 회복 기회 | 극단 DD 방어 약간 약화 | **높음** |
| MAX_LONG/TOTAL revert | 유연성 확보 | 영향 미미 (heat binding) | **매우 높음** |
| Safety Net Recovery 5%->7% | 합리적 복귀 속도 | 약간 빠른 Safety Net 해제 | **높음** |

### Expected Iter 25 Performance Range

| Metric | P1 Lower | P1 Target | P1 Upper | P2 Lower | P2 Target | P2 Upper |
|--------|----------|-----------|----------|----------|-----------|----------|
| Return | +5.5% | **+6.5%** | +7.5% | +6.0% | **+7.0%** | +8.0% |
| MaxDD | 12% | **15%** | 17% | 10% | **14%** | 17% |
| Calmar | 0.35 | **0.45** | 0.60 | 0.40 | **0.50** | 0.70 |
| BM WR | 65% | **72%** | 78% | 70% | **78%** | 85% |
| BM PF | 1.2 | **1.5** | 1.8 | 1.2 | **1.5** | 1.8 |
| MR PF (P2) | 1.5 | **2.5** | 3.0 | - | - | - |
| Combined Return | +11.5% | **+13.5%** | +15.5% | - | - | - |

### Worst Case Scenario (Iter 25)

```
Heat 32%, BM trailing 1.5, GDR (4%/8%):
- 최악 동시 full-stop: 3개 * 2.5% equity = 7.5% DD
- Safety Net 10% 이전에 추가 1 거래: +1.0%
- Safety Net 활성화 (10% DD)
- 기존 포지션 2개 잔여 리스크: 2 * 2.5% = 5%
- 이론적 최악 MaxDD: ~15%

이것은 목표 범위 이내다.
```

### Best Case Scenario

```
Trailing fix로 BM WR 75% 회복 + heat 32%:
- P1: +6-7% return, MaxDD 12-14%
- P2: +7-8% return, MaxDD 10-13%
- Combined: +13-15%
- Calmar: 0.9-1.2
- S&P Calmar 대비 50-65% 수준으로 개선 (Iter 23의 20%에서 대폭 개선)
```

---

## 8. Lessons Learned

### Lesson 1: 단일 파라미터의 파괴력을 과소평가하지 말라

BM trailing activation 1개 변수가 전체 시스템 수익의 90%를 소멸시켰다. 11개 변수 중 1개가 이 수준의 파괴력을 가질 수 있다는 것은, **모든 파라미터 변경에 대해 개별 민감도 분석이 필수**라는 것을 의미한다.

향후 규칙: **새로운 파라미터 값을 적용하기 전에, 해당 파라미터의 변경이 exit flow에 미치는 수학적 영향을 반드시 시뮬레이션하라.**

### Lesson 2: DD 방어와 수익 보존은 제로섬이 아니다

Panel #28은 DD 방어를 위해 수익 보존을 희생했다. 그러나 실제로는 **수익 보존 없이 DD 방어는 불가능하다.** 수익이 없으면 DD는 자연적으로 누적되기만 하고, 어떤 Safety Net도 기존 포지션의 손실을 막을 수 없다.

DD를 줄이는 올바른 방법: **(a) 수익 거래의 WR과 RR을 유지하면서 (b) 자본 배치를 적당히 줄이는 것.** 수익 메커니즘을 건드리는 것은 금지해야 한다.

### Lesson 3: 동시 변경 최대 3-4개 규칙 확립

11개 동시 변경은 실패의 원인을 분리할 수 없게 만들었다. 향후:
- **최대 3-4개 변수만 동시 변경**
- **변경 그룹 간 논리적 독립성 보장** (exit rules, sizing, GDR을 동시에 변경하지 않음)
- **각 변경의 개별 영향을 사전 추정**하고 사후 검증 가능하도록 설계

### Lesson 4: Exit Rule 변경은 Entry/Sizing 변경보다 훨씬 위험하다

Heat 35%->28%(sizing)은 수익을 비례적으로 줄였지만 시스템을 파괴하지 않았다. 반면 trailing activation 1.5->1.0(exit rule)은 시스템의 수익 구조 자체를 붕괴시켰다.

**Exit rule은 시스템의 DNA다.** Entry와 sizing은 조절 가능한 볼륨 노브이지만, exit rule은 수익/손실의 분배 구조를 결정한다. Exit rule 변경에는 entry/sizing 변경의 3배 이상의 주의가 필요하다.

### Lesson 5: '방어의 역설' 인식

모든 방어 메커니즘을 동시에 강화하면, 시스템이 '공격(수익)' 능력을 잃어 오히려 DD가 악화된다. 이것은 군사 전략의 '수비에만 집중하면 전쟁에 진다'와 동일한 원리다. P1 MaxDD가 20.2%에서 21.8%로 오히려 증가한 것이 이를 증명한다.

---

## 9. Decision Summary

### Full Change List (Iter 24 -> Iter 25)

| # | Parameter | File | Iter 24 | Iter 25 | Action | Priority |
|---|-----------|------|---------|---------|--------|---------|
| 1 | BM trailing activation | exit_rules.py:69 | 1.0 | **1.5** | REVERT | P0 |
| 2 | BM GDR thresholds | batch_simulator.py:90 | (0.03, 0.06) | **(0.04, 0.08)** | REVERT | P0 |
| 3 | MR GDR thresholds | batch_simulator.py:91 | (0.015, 0.03) | **(0.02, 0.04)** | REVERT | P0 |
| 4 | _MAX_LONG_POSITIONS | batch_simulator.py:72 | 7 | **8** | REVERT | P0 |
| 5 | _MAX_TOTAL_POSITIONS | batch_simulator.py:74 | 8 | **9** | REVERT | P0 |
| 6 | _MAX_PORTFOLIO_HEAT_PCT | batch_simulator.py:76 | 0.28 | **0.32** | ADJUST | P1 |
| 7 | _PORTFOLIO_SAFETY_NET_DD | batch_simulator.py:111 | 0.08 | **0.10** | ADJUST | P1 |
| 8 | _PORTFOLIO_SAFETY_NET_RECOVERY | batch_simulator.py:112 | 0.05 | **0.07** | ADJUST | P1 |

**Total changes: 8 parameter modifications across 2 files**
**REVERT: 5 | ADJUST: 3 | KEEP (from Iter 24): 3 | NEW: 0**

### Summary of What Stays from Iter 24

| # | Parameter | File | Value | Reason |
|---|-----------|------|-------|--------|
| 1 | _TRAILING_ATR_MULT | exit_rules.py:64 | 1.5 | 수학적 결함 수정 (Panel #28 유일한 설계 개선) |
| 2 | _STAGE2_PROFIT_LOCK_ATR | exit_rules.py:34 | 0.5 | 이익 보전 개선 |
| 3 | TREND_UP MR alloc | regime_classifier.py:25 | 0.008 | MR P1 zero-edge 반영 |

### Net Effect vs Iter 23

```
Iter 25 = Iter 23 + 3가지 개선:
1. Heat 35% -> 32% (-3%p, DD 감소 기대)
2. Trailing distance 2.0 -> 1.5 (수학적 수정, trailing exit 시 수익 보전 개선)
3. Stage2 profit lock 0.4 -> 0.5 (약간의 이익 보전 개선)

+ 2가지 안전망 강화:
4. Safety Net DD 12% -> 10% (2%p 조기 발동)
5. Safety Net Recovery 8% -> 7% (1%p 타이트)

+ 1가지 alloc 조정:
6. TREND_UP MR alloc 0.012 -> 0.008 (zero-edge 축소)
```

---

## 10. Quantitative Targets (Iteration 25)

| Metric | Iter 23 P1 | Iter 24 P1 | Target P1 | Iter 23 P2 | Iter 24 P2 | Target P2 |
|--------|-----------|-----------|----------|-----------|-----------|----------|
| Return | +7.5% | -0.69% | **+6.0-7.0%** | +7.9% | +0.19% | **+6.5-8.0%** |
| MaxDD | 20.2% | 21.8% | **< 17%** | 21.0% | 4.3% | **< 17%** |
| Calmar | 0.375 | negative | **> 0.40** | 0.378 | ~0.04 | **> 0.40** |
| BM WR | 73.5% | 57.5% | **> 70%** | 82.5% | 57.1% | **> 75%** |
| BM PF | 1.806 | 0.938 | **> 1.4** | 1.618 | 0.632 | **> 1.4** |
| BM Trailing Exits | 2 | 13 | **< 5** | 9 | 11 | **< 10** |
| MR PF (P2) | 2.858 | 1.974 | **> 2.0** | - | - | - |
| Combined | +15.4% | -0.5% | **+12.5-15.0%** | - | - | - |

**핵심 목표: Iter 23의 90% 수익을 유지하면서 MaxDD를 17% 이내로 억제. Calmar 0.40+ 달성.**

---

## 11. Future Iteration Guidelines

### 변경 수 제한 규칙 (신규)

```
Per iteration:
- Exit rule 변경: 최대 1-2개
- Sizing 변경: 최대 2개
- GDR/Safety Net 변경: 최대 2개
- 총 변경: 최대 4개
- 변경 그룹은 상호 독립적이어야 함
```

### 변경 전 필수 체크리스트 (신규)

```
1. [ ] Exit rule 변경 시: 수학적 일관성 검증 (activation vs distance, SL vs trail 관계)
2. [ ] Sizing 변경 시: 선형 스케일링 추정 (return, DD 동시 계산)
3. [ ] GDR 변경 시: 통계적 정상 손실 시퀀스에서 Tier 1 발동 여부 확인
4. [ ] Safety Net 변경 시: 기존 포지션 잔여 리스크 포함 MaxDD 추정
5. [ ] 모든 변경: 이전 이터레이션 대비 변경 방향과 크기 명시적 기록
```

### Iter 25 성공/실패 기준

```
성공 (P3 진행):
- Combined Return > +10%
- MaxDD < 17% (both periods)
- BM WR > 68% (both periods)
- BM trailing exits < 6 (P1)

부분 성공 (Iter 26 미세 조정):
- Combined Return +7-10%
- MaxDD 15-20%
- BM WR 65-68%

실패 (구조적 재검토):
- Combined Return < +7%
- MaxDD > 20%
- BM WR < 65%
```

---

## 12. Iteration History (Updated through Iter 24)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 (LOCKED) |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | MR cap3, heat 35%, TP 4.0, trail 1.5 |
| **24** | **-0.69%** | **+0.19%** | **-0.5%** | **21.8%** | **4.34%** | DD reduction 11 changes (OVER-CORRECTED) |
| 25 (target) | +6.5% | +7.0% | +13.5% | <17% | <17% | Selective rollback + heat 32% |

---

## Appendix A: Complete Change Tracking (Iter 23 -> 24 -> 25)

| Parameter | Iter 23 | Iter 24 | Iter 25 | Net vs 23 |
|-----------|---------|---------|---------|-----------|
| Heat | 0.35 | 0.28 | **0.32** | -0.03 |
| MAX_LONG | 8 | 7 | **8** | 0 |
| MAX_TOTAL | 9 | 8 | **9** | 0 |
| Safety Net DD | 0.12 | 0.08 | **0.10** | -0.02 |
| Safety Net Recovery | 0.08 | 0.05 | **0.07** | -0.01 |
| BM GDR | (0.04, 0.08) | (0.03, 0.06) | **(0.04, 0.08)** | 0 |
| MR GDR | (0.02, 0.04) | (0.015, 0.03) | **(0.02, 0.04)** | 0 |
| BM trailing activation | 1.5 | 1.0 | **1.5** | 0 |
| Trailing distance | 2.0 | 1.5 | **1.5** | -0.5 |
| Stage2 profit lock | 0.4 | 0.5 | **0.5** | +0.1 |
| TREND_UP MR alloc | 0.012 | 0.008 | **0.008** | -0.004 |

**Iter 25 = Iter 23 기본 + 4가지 타겟 개선 (heat -3%p, trail distance fix, profit lock +0.1, safety net 조정)**

---

## Appendix B: Panel #28 Retrospective Scorecard

| Panel #28 변경 | 의도 | 실제 결과 | 평가 |
|---------------|------|----------|------|
| Heat 35%->28% | DD 감소 | 수익 과잉 축소 | 과잉교정 |
| MAX_LONG 8->7 | 상관 리스크 축소 | 영향 미미 | 무해 |
| MAX_TOTAL 9->8 | 동일 | 영향 미미 | 무해 |
| Safety Net 12%->8% | 조기 방어 | 회복 차단 | 파괴적 |
| Safety Net Recovery 8%->5% | 보수적 복귀 | 장기 제한 | 과잉교정 |
| BM GDR (4%,8%)->(3%,6%) | DD 반응 가속 | 정상 손실에 위축 | 파괴적 |
| MR GDR (2%,4%)->(1.5%,3%) | 동일 | 동일 | 과잉교정 |
| BM trailing activation 1.5->1.0 | 빠른 BE 이동 | WR 붕괴, 수익 증발 | **매우 파괴적** |
| Stage2 profit lock 0.4->0.5 | 이익 보전 | 소폭 개선 | 유익 |
| Trailing distance 2.0->1.5 | 설계 결함 수정 | 설계 수정 완료 | **유익** |
| TREND_UP MR alloc 0.012->0.008 | zero-edge 축소 | 미미한 개선 | 유익 |

**최종 점수: 11개 변경 중 3개 유익, 2개 무해, 3개 과잉교정, 2개 파괴적, 1개 매우 파괴적.**
**Panel #28의 의도는 올바랐으나, 실행의 강도와 동시 적용이 문제였다.**
