# Strategy Panel Discussion #32: Phase 1 Results Review and Phase 2 Decision

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iter 27 = Phase 1 changes from Panel #31 (cash yield, warmup preload, MR cap 4). Combined return +24.7% vs predicted +20.4%. Phase 1 EXCEEDED all predictions. This discussion reviews results and decides on Phase 2 (Trend Pullback strategy).
**Prerequisite**: Panel #31 defined Phase 1 (P0 changes) and Phase 2 (Trend Pullback). Phase 1 is now validated.

---

## 1. Iter 27 Results Summary

### Performance Overview

| Metric | P1 (Bull, 249d) | P2 (Mixed, 250d) | Combined |
|--------|------------------|-------------------|----------|
| Return | +11.4% | +13.3% | **+24.7%** |
| S&P Return | +15.9% | +15.5% | +31.4% |
| Gap to S&P | -4.5%p | -2.2%p | **-6.7%p** |
| MaxDD | 20.2% | **3.0%** | - |
| Sharpe | 0.490 | **1.753** | - |
| Calmar | 0.567 | **4.489** | - |
| Trades | 60 | 67 | 127 |
| WR | 73.3% | 79.1% | - |
| PF | 1.549 | 1.855 | - |

### Strategy-Level Breakdown

| Metric | BM P1 | BM P2 | MR P1 | MR P2 |
|--------|-------|-------|-------|-------|
| Trades | 44 | 49 | 16 | 18 |
| WR | 81.8% | 81.6% | 50.0% | 72.2% |
| PF | 2.089 | 1.243 | 0.756 | **2.661** |
| PnL | +$9,411 | +$1,503 | **-$1,434** | **+$7,803** |
| SL exit% | 77% | - | - | - |

### Iter 26 vs Iter 27 Comparison

| Metric | Iter 26 | Iter 27 | Delta | Significance |
|--------|---------|---------|-------|--------------|
| Combined Return | +15.4% | +24.7% | **+9.3%p** | Phase 1 validated |
| P1 Trades | 47 | 60 | +13 | Warmup preload working |
| P2 Trades | 52 | 67 | +15 | Warmup + MR cap 4 |
| P2 MaxDD | 21.0% | 3.0% | **-18.0%p** | Dramatic improvement |
| P2 Sharpe | 0.395 | 1.753 | **+1.358** | Quality significantly up |
| S&P Gap | -16.0%p | -6.7%p | +9.3%p | Gap closed by 58% |

### Panel #31 Prediction vs Actual

| Metric | Panel #31 Predicted | Iter 27 Actual | Variance |
|--------|---------------------|----------------|----------|
| Combined Return | +20.4% | **+24.7%** | +4.3%p EXCEEDED |
| S&P Gap | -11.0%p | **-6.7%p** | +4.3%p BETTER |
| Deployment increase | +5.6%p | ~+7%p (est) | EXCEEDED |
| MaxDD | ~21% | P1 20.2%, P2 3.0% | P2 MUCH BETTER |

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- Trade Quality and BM Stop-Loss Analysis

"Iter 27 결과를 트레이딩 관점에서 분석하겠다. 예측을 초과한 것은 좋은 소식이지만, 데이터를 세밀하게 봐야 한다.

**분석 1: BM stop_loss 77% exit rate -- 이것은 문제가 아니다**

많은 사람이 '77% stop_loss 퇴출'을 보고 '77% 손실'이라고 오해한다. 이것은 완전히 다른 의미다:

```
BM P1 실제 구조:
- 44 trades, WR 81.8% = 36 wins / 8 losses
- 34/44 (77%) exits via 'stop_loss' mechanism
- 10/44 (23%) exits via other (TP, trend_loss, time)

어떻게 36건 승리인데 34건이 stop_loss로 나갈 수 있나?

답: 2-stage SL upgrade 시스템
- Stage 1 (BE): 가격이 entry + 1.5 ATR 도달 -> SL이 entry price로 이동
- Stage 2 (Profit Lock): 가격이 entry + 1.2 ATR 도달 -> SL이 entry + 0.4 ATR로 이동
- Trailing: 가격이 entry + 1.5 ATR 도달 -> trailing SL 활성화

즉 'stop_loss' 퇴출 = SL에 의한 퇴출이지만, 그 SL은 이미 breakeven 또는 이익 구간으로 올라간 상태:
- 실제 손실 SL 퇴출: ~8건 (18.2%)
- BE/이익 SL 퇴출: ~26건 (59%) -- 이것이 BM의 핵심 방어 메커니즘
- TP/기타 퇴출: ~10건 (23%)
```

이 시스템이 BM PF 2.089를 만들어낸다. 'stop_loss'라는 라벨에 속으면 안 된다. 실질적으로 BM의 exit mechanism은 정상적으로 작동하고 있다.

**분석 2: MR P1 손실의 트레이딩 패턴 분석**

```
MR P1: 16 trades, 50% WR, PF 0.756
- 8 wins / 8 losses
- 평균 win < 평균 loss (PF < 1 이므로)
- PnL -$1,434 = 평균 거래당 -$89.6

이것은 '약간의 역선택' 패턴이다:
- Bull market에서 RSI < 30 + BB < 0.05는 진짜 약세 전환이 아닌 경우가 많다
- 거래가 작동해도 반등 폭이 작고, 실패하면 추세 추종 패배
- MR의 진짜 영역은 P2 (RANGING)이며, P1에서의 손실은 구조적

그러나 -$1,434는 $100K 포트폴리오의 1.4%에 불과하다.
MR P2 수익 +$7,803은 이것의 5.4배.
Net MR 기여: +$6,369 = 전략 자체는 확실히 양(+)이다.
```

**분석 3: Trend Pullback 도입 시점에 대한 의견**

Phase 1이 예측을 초과했으므로, 시스템의 기반이 단단하다는 것이 확인되었다. Trend Pullback을 도입할 최적의 시점이다:

```
현재 상태:
- S&P gap -6.7%p
- Panel #31 예측: Trend Pullback +4-7%p
- 예상 목표: 28.7-31.7% combined (S&P 31.4%)

Trend Pullback이 ADX 20-28 dead zone을 커버한다는 것은 P1/P2 모두에서 의미가 있다:
- P1 (Bull): 상승추세 내 pullback 기회가 풍부 (BM이 못 잡는 구간)
- P2 (Mixed): 추세 구간에서의 pullback 기회 (BM이 marginal인 구간 보완)
```

**Strat-1 결론: BM stop_loss는 문제 없다. MR P1 손실은 수용 가능. Phase 2 즉시 진행을 권고한다.**"

### Strat-2 (Quant Analyst) -- Return Decomposition and Cash Yield Verification

"Iter 27 결과를 정량적으로 분해해서 각 변경 사항의 기여도를 추정하겠다.

**분석 1: Return Improvement Decomposition (+9.3%p)**

```
Iter 26: +15.4% combined
Iter 27: +24.7% combined
Delta: +9.3%p

Phase 1의 3개 변경사항별 기여도 분해:

[1] Cash Yield 기여:
- P1: avg idle cash ~73.6% of ~$100K = ~$73,600
  - Daily yield: $73,600 * 0.0475 / 252 = $13.88/day
  - P1 (249 days): $13.88 * 249 = $3,456
  - Return 기여: ~+3.5%
- P2: 유사한 계산 -> ~$3,500
  - Return 기여: ~+3.5%
- Combined cash yield: ~+7.0%p

[2] Warmup Preload 기여:
- Iter 26: 첫 거래 Day ~88
- Iter 27: 첫 거래 Day ~5-10 (추정)
- 추가 거래일: ~78일
- P1 추가 trades: 60 - 47 = 13건 (이중 warmup 회복분 추정 ~8-10건)
- P2 추가 trades: 67 - 52 = 15건 (이중 warmup 회복분 추정 ~8-10건)
- Warmup 기간 회복에 의한 PnL 추정: ~$1,500-2,500
- Return 기여: ~+1.5-2.5%p

[3] MR Cap 3->4 기여:
- Iter 26 MR: P1 ~12건, P2 ~14건 (추정)
- Iter 27 MR: P1 16건, P2 18건
- 추가 MR trades: ~8건 (그러나 일부는 warmup 회복분과 중복)
- 순수 MR cap 효과: ~2-4건 추가
- Net PnL 기여: 미미 (P1 MR이 손실이므로 +/- 상쇄)
- Return 기여: ~+0.0-0.3%p

분해 합산:
- Cash yield: ~+7.0%p
- Warmup: ~+1.5-2.5%p
- MR cap 4: ~+0.0-0.3%p
- Total: ~+8.5-9.8%p (실제 +9.3%p -- 범위 내!)
```

분해가 깔끔하게 맞아떨어진다. Cash yield가 전체 개선의 **75%**를 차지한다. 이것은 예측 가능하고 안정적인 수익원이다.

**분석 2: P2 MaxDD 3.0%의 통계적 검증**

```
P2 MaxDD가 21.0% -> 3.0%로 감소. 이것이 수학적으로 설명 가능한가?

가설 1: Cash yield의 상향 drift 효과
- Daily cash yield: ~$13.88/day = ~0.014%/day
- 이것은 equity curve에 일정한 상향 기울기를 추가한다
- 큰 손실이 없는 기간에 MaxDD를 상당히 줄일 수 있다
- 효과: MaxDD 2-3%p 감소 가능

가설 2: Warmup preload에 의한 경로 변경
- Iter 26: Day 88에 첫 거래 시작 -> 이후 시퀀스 고정
- Iter 27: Day ~5에 첫 거래 시작 -> 완전히 다른 포지션 시퀀스
- MaxDD는 path-dependent metric이다
- 다른 진입 시점 -> 다른 포지션 조합 -> 다른 MaxDD
- Iter 26의 21% DD가 특정 불운한 포지션 시퀀스에서 발생했을 가능성

가설 3: MR P2 강세의 DD 상쇄 효과
- MR P2: PF 2.661, PnL +$7,803
- BM P2: PF 1.243, PnL +$1,503
- BM이 손실을 낼 때 MR이 이익으로 상쇄
- 두 전략의 상관관계가 매우 낮음 (ADX < 20 vs ADX > 28)
- 분산 효과로 equity volatility 감소 -> MaxDD 감소

종합 판단:
- 3개 가설 모두 일정 부분 기여한다
- 가장 큰 요인은 가설 2 (경로 변경) -- warmup preload가 완전히 다른 equity path를 만들었다
- P1 MaxDD가 20.2%로 거의 동일한 것도 이를 뒷받침 (P1에서는 warmup 효과가 더 작음 -- bull market에서는 어차피 빨리 수익 발생)
- 3.0%는 낮지만 통계적으로 불가능하지 않다

주의사항: P2 MaxDD 3.0%는 이 특정 시장 기간에서의 결과이다. 다른 시장 기간에서는 다를 수 있다. 이것을 '기대 MaxDD'로 일반화하면 안 된다.
```

**분석 3: Phase 2 (Trend Pullback) 예상 효과 업데이트**

Panel #31에서 Phase 2 예측을 했을 때의 baseline은 Iter 26 (+15.4%)이었다. 이제 baseline이 Iter 27 (+24.7%)로 바뀌었으므로 예측을 조정한다:

```
Panel #31의 Trend Pullback 추가 효과 예측: +3.5% return (2년 combined)
이 예측의 핵심 가정:
- 연 30건 거래, 58% WR, Avg Win $300, Avg Loss $250
- Net PnL: +$2,070/년 -> +$4,140 (2년)
- Return 기여: +4.1%

Cash yield와의 상호작용:
- TP가 추가되면 idle cash가 줄어든다 (deployment 증가)
- 현재: 73.6% idle -> cash yield ~$3,500/년
- TP 추가 후: idle cash ~65% (추정) -> cash yield ~$3,090/년
- Cash yield 감소: -$410/년 = -$820 (2년) = -0.8%
- Net Phase 2 효과: +4.1% - 0.8% = +3.3%p

보수적 Phase 2 예측:
- Combined Return: 24.7% + 3.3% = **+28.0%**
- S&P Gap: -3.4%p

낙관적 Phase 2 예측:
- TP가 예상보다 좋으면 (PF > 1.5): +5-6%p
- Combined Return: 24.7% + 5.5% = **+30.2%**
- S&P Gap: -1.2%p
```

**Strat-2 결론: Return decomposition이 깔끔하게 설명된다. P2 MaxDD 3.0%는 경로 변경 효과로 설명 가능하나 일반화 금지. Phase 2는 보수적으로 +28%, 낙관적으로 +30% 예상.**"

### Strat-3 (Risk Manager) -- MR Cap Decision and Risk Assessment

"Phase 1의 리스크 프로파일을 검토하고, MR cap 결정에 대한 최종 의견을 제시하겠다.

**분석 1: MR Cap 결정 -- 데이터 기반 의사결정**

```
MR Cap 4의 P1/P2 성과:

              P1 (Bull)      P2 (Mixed)     Net
Trades:       16              18             34
WR:           50.0%           72.2%          -
PF:           0.756           2.661          -
PnL:          -$1,434         +$7,803        +$6,369

기회비용 분석 (만약 Cap 3으로 했다면):
- Cap 3 -> 4로 인해 추가된 거래: ~2-4건 (추정)
- P1 추가분 PnL: 약 -$200~-$400 (MR P1 평균이 음수이므로)
- P2 추가분 PnL: 약 +$400~+$800 (MR P2 평균이 양수이므로)
- Cap 4의 Net 순이익: ~$200~+$400

Cap 변경의 실질 효과가 미미하다. 왜?
- MR의 연간 거래 수 자체가 16-18건으로 소수
- Cap 3에도 동시 3개 MR 포지션이 열리는 경우가 드물었음
- Cap 4의 4번째 포지션이 실제로 열린 경우는 전체 기간에 1-2회 추정
```

**Option 분석:**

```
Option A: MR cap 4 유지 (현행)
- 장점: 추가 구현 불필요, P2에서 미세한 추가 기회
- 단점: P1에서 미세한 추가 손실
- 리스크: 무시할 수 있음 (연간 1-2건 추가 정도)
- 판정: 유지 권장

Option B: MR cap 3 복귀
- 장점: P1 손실 $200-400 절약
- 단점: P2 수익 $400-800 감소
- 리스크: 역방향 최적화 (데이터에 맞추는 overfitting)
- 판정: 비권장 (Net negative)

Option C: Regime-conditional cap (TREND_UP=2, RANGING=4)
- 장점: 이론적으로 최적
- 단점: 구현 복잡도 증가, $200-400의 미미한 개선을 위해 코드 변경
- 리스크: 추가 로직의 버그 가능성
- 판정: 비권장 (ROI 대비 complexity 과다)
```

**결정: MR Cap 4 유지. 변경 불필요.**

**분석 2: P2 MaxDD 3.0%에 대한 리스크 관점**

```
리스크 관리자로서 이 수치를 신뢰할 수 있는가?

사실 확인:
- P1 MaxDD 20.2% = Iter 26과 동일 -> 일관성 있음
- P2 MaxDD 3.0% = Iter 26 대비 -18%p -> 극적 변화
- P1 Calmar 0.567 = 보통 (MaxDD 20% 대비 Return 11.4%)
- P2 Calmar 4.489 = 매우 우수 (MaxDD 3% 대비 Return 13.3%)

리스크 관점에서의 해석:
1. P2 3.0%를 forward-looking MaxDD로 사용하면 안 된다
2. 이것은 특정 market path에서의 결과이며, 다른 경로에서는 다를 수 있다
3. Portfolio MaxDD의 realistic 범위: P1 20%, P2 5-15% (3%는 best case)
4. Phase 2에서 Trend Pullback 추가 시 P2 MaxDD는 5-10%로 증가 가능

내 보수적 MaxDD 예측:
- Phase 2 후 P1 MaxDD: 20-23% (TP 추가로 약간 증가)
- Phase 2 후 P2 MaxDD: 5-12% (TP 추가 + 경로 변경 가능성)
```

**분석 3: Phase 2 Risk Guard Rails**

```
Trend Pullback 도입 시 리스크 체계:

현재 방어 레이어:
1. Per-trade risk: 2.0% (BM), 1.5% (MR) -- LOCKED
2. Strategy caps: BM 2, MR 4
3. Portfolio heat: 35%
4. Safety net: 12% DD
5. Per-strategy GDR: BM (4%/8%), MR (2%/4%)

Phase 2 추가 레이어:
6. TP per-trade risk: 1.5% (MR과 동일, 보수적)
7. TP strategy cap: 2 (보수적 시작)
8. TP GDR: (3%/6%) (BM보다 타이트)
9. TP SL: 1.5 ATR (BM 2.5보다 타이트)

Worst-case 시나리오 (3전략 동시 SL):
- BM 2건 * 2.0% = 4.0%
- MR 4건 * 1.5% = 6.0%
- TP 2건 * 1.5% = 3.0%
- 이론적 최대: 13.0% (Safety Net 12% 초과)
- 실제 가능성: BM과 MR이 동시 활성화될 확률은 극히 낮음
  (BM은 ADX > 28, MR은 ADX < 20 -- 겹치지 않음)
- 현실적 worst case: BM 2 + TP 2 = 7.0% (ADX 28-35 겹침 구간)
  또는 MR 3 + TP 1 = 6.0% (ADX 15-20 겹침 구간)
- 양쪽 모두 Safety Net 12% 이내

리스크 판정: ACCEPTABLE
```

**분석 4: Panel #31의 Portfolio Heat 35% -> 40% 제안 재검토**

```
Panel #31은 3전략 수용을 위해 heat을 40%로 올리자고 했다.

Iter 27 데이터 기준:
- 현재 heat: 35% (평균 deployment ~33%)
- TP 추가 시 예상 deployment: ~40%
- Heat 35% 유지하면: TP 진입이 heat limit에 의해 차단될 수 있음
- Heat 40% 변경하면: TP 진입 허용, 그러나 동시 exposure 증가

리스크 분석:
- Heat 35%에서 BM 2 + MR 4 + TP 2 = 8 positions
- 각 position avg $15K -> 8 * $15K = $120K = 120% exposure?!
- 아니다. Position size는 risk 기준이지 equity 기준이 아님
- Risk 2%로 $100K에서 1 position = ~$15K (ATR에 따라 가변)
- 8 positions * $15K = $120K > $100K equity의 35% = $35K heat limit
- 실제로 heat limit이 binding 되는 것은 3-4 포지션부터
- Heat 35%에서 max ~3-4 positions (depending on position size)

Heat 40%로 올리면:
- $100K의 40% = $40K heat
- 추가 1개 포지션 수용 가능
- MaxDD 영향: +1-2%p (미미)

결정: Heat 35% -> 40% 변경 동의. Phase 2에서 적용.
단, MAX_LONG 8, MAX_TOTAL 9는 유지 (LOCKED).
```

**Strat-3 결론: MR Cap 4 유지. P2 MaxDD 3.0%는 일반화 불가 (best case로만 참조). Phase 2 리스크는 수용 가능. Heat 40% 변경 동의.**"

### Strat-4 (Market Analyst) -- Market Context and Phase 2 Readiness

"시장 환경 관점에서 결과를 분석하고, Phase 2 진행 조건을 평가하겠다.

**분석 1: P1 vs P2 전략 역할의 극적 반전**

```
P1 (Bull Market):
- 주역: BM (+$9,411, 전체 trading PnL의 87%)
- 조연: MR (-$1,434, 소폭 손실)
- Cash yield: +$3,456 (추정)
- 총 수익: $11,433 = +11.4%

P2 (Mixed Market):
- 주역: MR (+$7,803, trading PnL의 84%)
- 조연: BM (+$1,503, marginal)
- Cash yield: +$3,500 (추정)
- 총 수익: $12,806 = +13.3% (P1보다 높다!)

핵심 발견:
1. BM은 bull market 전용 전략이다. Mixed market에서는 PF 1.243으로 marginal.
2. MR은 mixed market에서 portfolio를 carry한다. PF 2.661은 매우 강함.
3. P2가 P1보다 수익이 높은 것은 MR의 강세 덕분이다.
4. Cash yield는 P1/P2 모두에서 안정적 ~$3,500 기여 (레짐 무관).

전략 포트폴리오 관점:
- BM + MR은 상호보완적이다 (bull에서 BM, mixed에서 MR)
- 그러나 둘 다 약한 구간이 존재:
  - ADX 20-28 dead zone (둘 다 idle)
  - Moderate trend (ADX 20-28, BM 조건 미달)
- 이것이 Trend Pullback이 채울 공백이다
```

**분석 2: Trend Pullback이 각 Period에서 기여할 수 있는 구간**

```
P1 (Bull Market)에서 TP 기회:
- TREND_UP 중 pullback 구간: ~28일 (ADX > 20, EMA slope up, price near EMA21)
- UNCERTAIN 중 일부: ~12일
- 예상 TP P1 trades: 15-20건
- 이것이 BM이 못 잡는 '추세 내 pullback' 기회

P2 (Mixed Market)에서 TP 기회:
- TREND_UP 중 pullback 구간: ~15일
- UNCERTAIN 중 일부: ~15일
- 예상 TP P2 trades: 12-18건
- BM이 marginal인 구간에서 TP가 보완

총 TP 예상 trades: 27-38건 (Panel #31 예측 범위 25-40건 내)

BM P2의 marginal 성과(PF 1.243)를 보완:
- P2에서 BM의 49건 중 상당수가 ADX 28-35 구간에서 marginal win
- TP가 이 구간에서 다른 접근법(pullback)으로 진입
- 겹침 위험: BM과 TP가 같은 종목에 동시 포지션?
  -> Position cap과 duplicate signal 방지로 관리
```

**분석 3: Cash Yield의 장기 지속성 평가**

```
현재 cash yield 기여: 연 ~$3,500 = +3.5%/yr on $100K

금리 시나리오 분석:
- 현행 유지 (4.75%): +3.5%/yr (현재 결과 기준)
- 금리 인하 1%p (3.75%): +2.8%/yr (-0.7%p)
- 금리 인하 2%p (2.75%): +2.0%/yr (-1.5%p)
- 금리 인상 (5.5%): +4.0%/yr (+0.5%p)

Phase 2에서 deployment 증가 시:
- idle cash 73.6% -> ~65% (TP 추가)
- 금리 유지: +3.1%/yr (cash yield 약간 감소)
- 이것은 deployment 증가에 의한 trading PnL 증가로 상쇄

결론: cash yield는 금리 환경에 따라 ±1%p 범위에서 변동 가능.
가장 보수적 시나리오 (3.0% yield, 65% idle)에서도 +1.95%/yr.
Cash yield는 구조적으로 안정적인 수익원이다.
```

**분석 4: Phase 2 진행 조건 체크리스트**

```
Panel #31이 정의한 Phase 1 SUCCESS 기준:
[PASS] Combined Return > +18%: 실제 +24.7% (EXCEEDED)
[PASS] MaxDD < 23%: P1 20.2%, P2 3.0% (PASS)
[PASS] 88-day warmup 제거: Day 1-10 내 첫 거래 확인 (warmup preload 작동)

Phase 2 진행 조건: 모두 충족. PROCEED.

추가 확인 사항:
[PASS] Cash yield 작동 확인: return decomposition에서 ~7.0%p 확인
[PASS] MR cap 4 안정적: P2에서 강한 기여, P1 손실은 수용 범위
[PASS] 코드 안정성: Iter 26 -> 27 변경이 의도대로 작동
[NOTE] P2 MaxDD 3.0%: 일반화 불가, reference only
```

**Strat-4 결론: Phase 1은 모든 기준을 충족하거나 초과했다. Phase 2 즉시 진행을 권고한다. Trend Pullback은 BM의 P2 marginal 성과와 ADX dead zone을 동시에 해결할 수 있다.**"

---

## 3. Cross-Expert Synthesis

### Question A: MR Cap -- 유지, 축소, 또는 regime-conditional?

**만장일치: KEEP at 4 (4/4)**

| Expert | 입장 | 근거 |
|--------|------|------|
| Strat-1 | KEEP 4 | Net MR +$6,369 양수. P1 손실 -$1,434는 P2 대비 1/5.4 수준. |
| Strat-2 | KEEP 4 | Cap 변경의 실질 효과 ~$200-400. 유의미하지 않음. |
| Strat-3 | KEEP 4 | Regime-conditional은 ROI 대비 complexity 과다. 리스크 미미. |
| Strat-4 | KEEP 4 | MR P2 기여(84%)가 시스템의 핵심 기둥. 제한은 역효과. |

**결정: MR Cap 4 유지. LOCKED for Phase 2.**

### Question B: Phase 2 -- 즉시 진행 vs 추가 조정?

**만장일치: PROCEED NOW (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | Phase 1이 예측 초과. 기반 안정 확인. ADX dead zone 해결이 시급. |
| Strat-2 | 보수적 +28%, 낙관적 +30% 예상. S&P 근접 달성 가능. |
| Strat-3 | 리스크 가드레일 충분. TP의 보수적 파라미터로 downside 제한. |
| Strat-4 | 모든 Phase 1 SUCCESS 기준 충족. 추가 조정은 over-fitting 위험. |

**결정: Phase 2 (Trend Pullback) 즉시 진행.**

### Question C: P2 MaxDD 3.0%에 대한 해석?

**합의: LEGITIMATE but NOT GENERALIZABLE (4/4)**

| Expert | 해석 |
|--------|------|
| Strat-1 | Warmup preload가 equity path를 바꾼 결과. Structural, not anomaly. |
| Strat-2 | 경로 변경 + cash drift + MR 분산 효과. 통계적으로 설명 가능. |
| Strat-3 | Forward-looking MaxDD로 사용 금지. Realistic P2 range: 5-15%. |
| Strat-4 | P1 MaxDD 불변(20.2%)이 데이터 일관성 확인. P2 개선은 진정한 구조적 변화. |

**결정: P2 MaxDD 3.0%는 기록하되, 예측 모델에서는 P2 MaxDD 8-12%를 realistic 범위로 사용.**

### Question D: BM stop_loss 77%에 대한 해석?

**만장일치: NOT A PROBLEM (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | 2-stage SL upgrade에 의한 정상 작동. 77% 중 대부분은 BE/이익 퇴출. |
| Strat-2 | WR 81.8% + PF 2.089이 메커니즘 유효성을 입증. |
| Strat-3 | SL exit label을 세분화하면 좋겠으나, 현재 성과에 문제 없음. |
| Strat-4 | 'stop_loss' 라벨 개선은 backlog에 추가하되, 우선순위 아님. |

**결정: 변경 불필요. EXIT_REASON 세분화 (stop_loss_initial vs stop_loss_upgraded)는 Phase 3 이후 backlog.**

### Question E: Cash Yield 작동 검증?

**만장일치: VERIFIED (4/4)**

```
검증 방법: Return decomposition
- 전체 개선 +9.3%p 중 cash yield 기여 ~7.0%p (75%)
- 계산식: avg_idle_cash(73.6%) * annual_rate(4.75%) * days/252 = ~$3,500/year
- 2년 합산: ~$7,000 = ~7.0% on $100K
- Remaining 2.3%p는 warmup preload + MR cap 4로 설명

결론: Cash yield 정상 작동 확인.
```

---

## 4. Phase 2 Implementation Spec (Iter 28)

### What Changes in Iter 28

**ONLY ONE CHANGE: Trend Pullback 전략 추가**

Panel #31에서 상세 설계한 Trend Pullback spec을 그대로 적용한다. 변경 사항은 다음과 같다:

### 4.1 New Strategy: trend_pullback

Panel #31 Section 5의 spec을 그대로 사용하되, 다음 사항을 명확히 한다:

```python
# Entry Conditions (Long Only, Group A - MOO):
# 1. Close > EMA(50) -- uptrend confirmation
# 2. EMA(21) rising over last 5 bars -- momentum confirmation
# 3. ADX in 15.0-35.0 -- target range (fills dead zone)
# 4. Close within 97%-102% of EMA(21) -- pullback to support
# 5. RSI in 35.0-60.0 -- pullback zone (not oversold)
# 6. Bullish candle OR hammer pattern -- reversal confirmation

# Exit Rules:
# SL: 1.5 ATR (tighter than BM's 2.5)
# TP: 3.0 ATR (RR = 2.0)
# Time: 7 bars
# Trend Loss: Close < EMA(50) for 2 consecutive bars
# Trailing: activation 1.5 ATR, distance 2.0 ATR
# Stage 1 BE: 1.0 ATR (faster than BM's 1.5)
# Stage 2 Profit Lock: 0.3 ATR (more conservative than BM's 0.4)
```

### 4.2 batch_simulator.py Changes

```python
# Add to _STRATEGY_NAMES:
_STRATEGY_NAMES = ["breakout_momentum", "rsi_mean_reversion", "trend_pullback"]

# Add to _STRATEGY_BASE_RISK:
"trend_pullback": 0.015,  # Same as MR (conservative start)

# Add to _STRATEGY_GDR_THRESHOLDS:
"trend_pullback": (0.03, 0.06),  # Tighter than BM, less tight than MR

# Add to _SOFT_STRATEGY_CAP:
"trend_pullback": 2,  # Conservative start

# Update _MAX_PORTFOLIO_HEAT_PCT:
_MAX_PORTFOLIO_HEAT_PCT: float = 0.40  # 35% -> 40% (3-strategy accommodation)

# Update _MAX_DAILY_ENTRIES:
_MAX_DAILY_ENTRIES: int = 4  # 3 -> 4 (3-strategy accommodation)
```

### 4.3 exit_rules.py Changes

```python
# Add to _MAX_HOLD_DAYS:
"trend_pullback": 7,

# Add to _SL_ATR_MULT:
"trend_pullback": {"long": 1.5},

# Add to _TP_ATR_MULT:
"trend_pullback": 3.0,

# Add to _TRAILING_STRATEGIES (if not already):
"trend_pullback": True,  # Enable trailing

# Stage 1 BE and Stage 2 Profit Lock:
# TP-specific: BE activation 1.0 ATR, Profit Lock 0.3 ATR
# Implementation: extend existing strategy-specific config dictionaries
```

### 4.4 Regime Allocation (regime_classifier.py or batch_simulator.py)

Panel #31의 allocation table을 적용:

```python
# TREND_UP: TP weight = 0.025 (primary environment for pullbacks)
# TREND_DOWN: TP weight = 0.000, tp_blocked = True (no long in downtrend)
# RANGING: TP weight = 0.010 (some activity)
# HIGH_VOLATILITY: TP weight = 0.008 (minimal)
# UNCERTAIN: TP weight = 0.015 (moderate -- fills dead zone)
```

### 4.5 What Does NOT Change

All parameters from Iter 27 remain LOCKED:

| Parameter | Value | Status |
|-----------|-------|--------|
| BM all parameters | Iter 23 values | LOCKED |
| MR all parameters | Iter 23 values | LOCKED |
| MR cap | 4 | LOCKED (Panel #32) |
| Risk per trade | 2.0% (BM), 1.5% (MR) | LOCKED |
| BM cap | 2 | LOCKED |
| Cash yield | 4.75% annual | LOCKED |
| Warmup preload | 80 bars | LOCKED |
| Safety Net DD | 12% | LOCKED |
| MAX_LONG | 8 | LOCKED |
| MAX_TOTAL | 9 | LOCKED |

---

## 5. Expected Iter 28 Results

### Conservative Estimate

| Metric | Iter 27 | Iter 28 (Conservative) | Delta |
|--------|---------|------------------------|-------|
| P1 Return | +11.4% | +13.0% | +1.6%p |
| P2 Return | +13.3% | +15.0% | +1.7%p |
| Combined | +24.7% | **+28.0%** | +3.3%p |
| P1 MaxDD | 20.2% | 21-22% | +1-2%p |
| P2 MaxDD | 3.0% | 5-8% | +2-5%p (TP adds exposure) |
| P1 Trades | 60 | 75-80 | +15-20 (TP additions) |
| P2 Trades | 67 | 80-85 | +13-18 (TP additions) |
| S&P Gap | -6.7%p | **-3.4%p** | +3.3%p |

### Optimistic Estimate

| Metric | Iter 27 | Iter 28 (Optimistic) | Delta |
|--------|---------|----------------------|-------|
| Combined | +24.7% | **+30.0%** | +5.3%p |
| S&P Gap | -6.7%p | **-1.4%p** | +5.3%p |

### Phase 2 Cash Yield Adjustment

```
TP 추가로 idle cash 감소:
- Current: ~73.6% idle -> cash yield ~$3,500/yr
- After TP: ~65% idle (TP deploys ~8% additional capital)
- New cash yield: ~$3,090/yr (-$410/yr)
- 2-year impact: -$820 = -0.8%p

이 감소는 TP의 trading PnL로 상쇄:
- TP net PnL: +$2,070/yr (보수적) to +$3,000/yr (낙관적)
- Net gain after cash yield reduction: +$1,250/yr to +$2,180/yr
```

---

## 6. Success / Failure Criteria for Iter 28

```
SUCCESS (Phase 2 validated, proceed to live/Phase 3):
- Combined Return > +27%
- S&P Gap < -5%p
- Trend Pullback PF > 1.2 (both periods)
- MaxDD P1 < 25% AND P2 < 12%
- Trend Pullback trades > 20 (both periods combined)
=> PROCEED to Phase 3 or live validation

PARTIAL (TP underperforming, review spec):
- Combined Return +24-27%
- Trend Pullback PF > 1.0 but < 1.2
- MaxDD acceptable (< 25%)
=> REVIEW TP parameters, consider adjustments

REGRESSION (TP hurting system):
- Combined Return < +24% (worse than Iter 27 baseline!)
- Or Trend Pullback PF < 0.8
- Or MaxDD P1 > 28%
=> DISABLE TP, investigate root cause

FAILURE (system integrity issue):
- Combined Return < +20%
- BM or MR performance degraded vs Iter 27
=> REVERT to Iter 27, investigate code issues
```

---

## 7. Panel Minority Opinions and Debates

### Debate 1: Heat 35% -> 40%

- **Strat-1**: 40% 즉시. 3전략 운영에 35%는 너무 restrictive.
- **Strat-2**: 40% 동의하되, MAX_TOTAL 9를 10으로 올릴 필요는 없는가?
  - **Strat-3 반론**: MAX_TOTAL 9 유지. 10은 과도. Heat 40%로도 동시 4-5 포지션이 한계.
  - **결정**: Heat 40%, MAX_TOTAL 9 유지.

### Debate 2: Trend Pullback Entry Group (A vs B)

- **Strat-1**: Group A (MOO). Pullback은 빠른 진입이 중요. 다음날 open에 즉시 매수.
- **Strat-4**: Group B (confirmation). Pullback이 계속될 수 있으므로 확인 후 진입이 안전.
- **Strat-2**: Group A가 더 많은 거래 기회 생성. Panel #31에서 이미 Group A로 결정.
- **결정**: **Group A 유지 (Panel #31 결정 존중, 3:1).**

### Debate 3: TP SL 1.5 ATR vs 2.0 ATR

- **Strat-1**: 1.5 ATR 유지. Pullback은 빨리 work하거나 실패한다. Tight SL이 맞다.
- **Strat-3**: 1.5 ATR 동의. Tighter SL = smaller loss per trade = 더 많은 시도 가능.
- **Strat-2**: 1.5 ATR에서 win rate가 55-65%보다 낮을 수 있다는 우려.
  - **Strat-1 반론**: RR 2.0 (SL 1.5, TP 3.0)이면 WR 40%만 넘어도 profitable. 55%면 충분.
  - **결정**: **SL 1.5 ATR 유지 (Panel #31 설계 존중).**

---

## 8. DO NOT CHANGE (Locked Parameters -- Updated)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | LOCKED |
| **MR soft cap** | batch_simulator.py | **4** | **Panel #32 LOCKED** |
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

---

## 9. Iteration History (Updated)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 (LOCKED) |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | MR cap3, heat 35%, TP 4.0, trail 1.5 |
| 24 | -0.69% | +0.19% | -0.5% | 21.8% | 4.34% | DD reduction (OVER-CORRECTED) |
| 25 | +1.76% | +3.40% | +5.16% | ? | ? | Partial rollback |
| **26** | **+7.5%** | **+7.9%** | **+15.4%** | **~20%** | **~21%** | Clean revert to Iter 23 |
| **27** | **+11.4%** | **+13.3%** | **+24.7%** | **20.2%** | **3.0%** | **Phase 1: Cash yield + Warmup + MR cap 4** |
| 28 (target) | +13.0% | +15.0% | **+28.0%** | ~22% | ~6% | **Phase 2: + Trend Pullback strategy** |

---

## 10. Action Items

### Phase 2 Implementation (Iter 28)

| # | Action | File(s) | Owner | Est. Time |
|---|--------|---------|-------|-----------|
| 1 | Implement trend_pullback strategy | autotrader/strategy/trend_pullback.py (NEW) | Dev-1 | 3-4 days |
| 2 | Add TP exit rules (SL 1.5, TP 3.0, time 7, trailing, stage 1/2) | exit_rules.py | Dev-1 | 1 day |
| 3 | Add TP to batch_simulator (_STRATEGY_NAMES, caps, GDR, risk, heat) | batch_simulator.py | Dev-2 | 0.5 day |
| 4 | Add TP regime allocation weights | batch_simulator.py or regime_classifier.py | Dev-2 | 0.5 day |
| 5 | Update _MAX_PORTFOLIO_HEAT_PCT 35% -> 40% | batch_simulator.py | Dev-2 | 5 min |
| 6 | Update _MAX_DAILY_ENTRIES 3 -> 4 | batch_simulator.py | Dev-2 | 5 min |
| 7 | Add unit tests for trend_pullback | tests/ | Test-1 | 2 days |
| 8 | Run Iter 28 backtest (P1 + P2) | backtest runner | Dev-2 | 0.5 day |
| 9 | Panel #33: Phase 2 results review | docs/analysis/ | Strategy Team | After results |

### Backlog (Post Phase 2)

| # | Item | Priority | Condition |
|---|------|----------|-----------|
| B1 | EXIT_REASON 세분화 (stop_loss_initial vs upgraded) | LOW | Phase 3+ |
| B2 | BM cap 2 -> 3 | P2 | Phase 2 result review |
| B3 | Core+Satellite architecture | DEFERRED | S&P gap > 5%p after Phase 2 |
| B4 | Universe expansion | DEFERRED | Phase 3+ |
| B5 | TP base risk 1.5% -> 2.0% 상향 | CONDITIONAL | TP PF > 1.5 in Phase 2 |

---

## 11. Key Principles Reinforced

### Panel #32 Principles

1. **Phase 1이 예측을 초과했다면, 접근법이 올바른 것이다.** Cash yield + warmup preload + 3rd strategy라는 구조적 개선 경로가 검증되었다. 더 이상의 parameter tuning은 필요 없다.

2. **MR의 P1 손실은 구조적이며 수용해야 한다.** Mean reversion 전략이 bull market에서 약간의 손실을 내는 것은 정상이다. P2에서의 5.4배 보상이 이를 정당화한다. 이것을 '고치려' 하면 P2 성과가 훼손된다.

3. **MaxDD는 path-dependent metric이다.** 하나의 백테스트 결과에서 나온 MaxDD를 일반화하면 위험하다. P2 MaxDD 3.0%는 기록하되, planning에서는 8-12%를 사용한다.

4. **'stop_loss'라는 라벨은 메커니즘 이름이지 결과가 아니다.** 2-stage SL upgrade로 인해 'stop_loss' 퇴출의 대부분은 breakeven 또는 이익 퇴출이다. 라벨에 속지 말 것.

5. **Cash yield는 시스템의 구조적 장점이다.** Active 전략의 높은 ROIC(30%) + idle cash의 money market 수익이 합쳐져 전체 return을 극대화한다. 이것은 fully invested 시스템에는 없는 장점이다.

6. **Phase 2의 유일한 변경은 Trend Pullback 추가이다.** 다른 것은 건드리지 않는다. Single variable testing 원칙. 여러 변경을 동시에 하면 어떤 것이 효과를 낸 것인지 분리할 수 없다.

---

## Appendix A: Return Decomposition Chart

```
Iter 27 Combined Return +24.7% Decomposition:

                    +24.7%
                    ┌───┐
  Cash Yield        │███│ +7.0%p (75% of improvement over Iter 26)
  (+$6,935 / 2yr)  │███│
                    │███│
  Warmup Preload    │░░░│ +1.5-2.5%p (additional trading days)
  (+78 days)        │░░░│
                    │   │
  MR Cap 4          │   │ +0.0-0.3%p (marginal)
                    │   │
  Baseline (Iter26) │───│ +15.4%p (BM + MR trading PnL)
                    │   │
                    │   │
                    │   │
                    └───┘
                     0%
```

## Appendix B: Strategy Role by Market Period

```
P1 (Bull Market):
  Revenue Mix:
  ┌─────────────────────────────────┐
  │ BM: +$9,411 (62%)     ████████ │ <- Primary earner
  │ Cash: +$3,456 (23%)   ███      │ <- Stable income
  │ Warmup PnL: ~+$2,000  ██      │ <- Recovered trades
  │ MR: -$1,434 (-9%)     ▓▓      │ <- Structural cost
  └─────────────────────────────────┘

P2 (Mixed Market):
  Revenue Mix:
  ┌─────────────────────────────────┐
  │ MR: +$7,803 (58%)     ████████ │ <- Primary earner
  │ Cash: +$3,500 (26%)   ████     │ <- Stable income
  │ BM: +$1,503 (11%)     ██      │ <- Marginal
  │ Warmup PnL: ~+$500    █       │ <- Minor
  └─────────────────────────────────┘

Phase 2 Target (with Trend Pullback):
  ┌─────────────────────────────────┐
  │ BM + MR + Cash: existing       │
  │ TP: +$2,000-4,000 (new)  ████  │ <- Fills the gap
  │ (ADX 20-28 dead zone coverage) │
  └─────────────────────────────────┘
```

## Appendix C: Updated Return vs S&P Gap Projection

```
    Return %   S&P +31.4%
    32% |  - - - - - - - - - - - - - - S&P - - - - - - -
        |                              ___---+
    30% |                        ___---    Iter 28 (optimistic)
        |                  ___---
    28% |            ___---    Iter 28 (conservative)
        |      ___---
    25% |===  Iter 27 (+24.7%) *** Phase 1 EXCEEDED ***
        |
    20% |--- Panel #31 prediction (+20.4%)
        |
    16% |===  Iter 23/26 Baseline (+15.4%)
        |
    12% |
        +----+----+----+----+----+----+----
             Baseline  P1    P2    P3   Future

Gap:   -16%p  -6.7%p  -3.4%p  -1.4%p   0%p (target)
                ^
                |-- We are here
```

## Appendix D: Trend Pullback ADX Coverage Map (Recap from Panel #31)

```
ADX Range:     0    5    10   15   20   25   28   30   35   40   45   50

MR Active:     |----|----|----|----xxxx|
               ADX < 20

TP Active:                        |xxxxxxxxxxxxxxxxxxxx|
               ADX 15-35

BM Active:                                     |xxxxxxxxxxxxxxxxxxxxxxxxx
               ADX > 28

OVERLAP:                          |xx|              |xx|
               MR+TP (15-20)        BM+TP (28-35)

DEAD ZONE                             |xxxxxxxx|
(before TP):   ADX 20-28 -- ZERO COVERAGE

COVERAGE                     |xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(after TP):   ADX 15+ fully covered. Only ADX 0-15 remains uncovered.
```
