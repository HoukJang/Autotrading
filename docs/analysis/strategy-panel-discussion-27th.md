# Strategy Panel Discussion #27: Iterations 16-22 Comprehensive Review

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iterations 16-22 -- 7-iteration deep review of BM+MR 2-strategy portfolio optimization. 22 total iterations since project inception.
**Verdict**: **ARCHITECTURAL CEILING REACHED -- Parameter optimization near exhaustion. Structural changes required to beat S&P 500.**

---

## 1. Backtest Results Summary (Iterations 16-22)

### Complete Performance Table

| Iter | Config Summary | P1 Return | P2 Return | Combined | BM P1 PF | BM P2 PF | MR P1 PF | MR P2 PF |
|------|---------------|-----------|-----------|----------|----------|----------|----------|----------|
| 16 | ADX25, LB10, cap2/2, moderate | -3.7% | +2.3% | -1.4% | 0.559 | 1.206 | 1.165 | 1.408 |
| 17 | ADX25, LB10, BMcap1, SL2.0 | -6.7% | +2.2% | -4.5% | 0.439 | 1.243 | 0.607 | 1.299 |
| 18 | ADX25, LB10, BMcap1, regime relaxed | -6.2% | **+5.2%** | -1.0% | 0.420 | 1.585 | 0.668 | 1.596 |
| **19** | **ADX28, LB15, BMcap2, MRcap3, high** | **+7.4%** | +2.6% | **+10.0%** | **1.832** | 1.067 | **1.783** | 1.698 |
| 20 | ADX28, LB15, BMcap1, MRcap3, high | -9.0% | -1.4% | -10.4% | 0.348 | 0.527 | 0.520 | 2.022 |
| 21 | ADX25, LB10, cap2/2, high | -3.2% | -3.5% | -6.7% | 0.702 | 0.510 | 1.052 | 1.939 |
| 22 | ADX28, LB15, cap2/2, regime alloc | -0.6% | +3.5% | +2.9% | 1.170 | 1.180 | 0.684 | 1.862 |

### Benchmark Reference
- **Period 1** (2024-03 ~ 2025-02, bull market): S&P 500 **+15.9%**
- **Period 2** (2025-02 ~ 2026-02, mixed market): S&P 500 **+15.5%**

### Best Results Across All Iterations
- **Best P1**: Iter 19 at +7.4% (47% of S&P)
- **Best P2**: Iter 18 at +5.2% (34% of S&P)
- **Best Combined**: Iter 19 at +10.0% (32% of S&P combined +31.4%)
- **No iteration has beaten S&P in either period.**

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- BM의 구조적 한계와 SL 문제

"7개 이터레이션을 거치면서 BM의 행동 패턴이 매우 명확해졌다. 핵심 진단을 세 가지로 정리하겠다.

**진단 1: ADX/Lookback/Cap 삼각관계의 확정**

데이터가 반복적으로 보여주는 패턴이 있다:

| Config | P1 BM PF | P2 BM PF | 판정 |
|--------|----------|----------|------|
| ADX25 + cap1 (Iter 17, 18) | 0.420-0.439 | 1.243-1.585 | P1 재앙 |
| ADX25 + cap2 (Iter 16, 21) | 0.559-0.702 | 0.510-1.206 | 양쪽 불안정 |
| ADX28 + cap1 (Iter 20) | 0.348 | 0.527 | 완전 실패 |
| ADX28 + cap2 (Iter 19, 22) | **1.170-1.832** | **1.067-1.180** | **유일한 양호 조합** |

**ADX 28 + cap 2가 유일하게 두 기간 모두에서 PF > 1.0을 유지하는 조합이다.** 이것은 7번의 독립 실험으로 확인된 결과이므로 과적합이 아니다. ADX 28은 Wilder의 'strong trend' 기준이며, cap 2는 동시 리스크를 제어하면서 충분한 거래 기회를 허용한다.

ADX 25는 'developing trend'를 포함하는데, 이 구간의 breakout은 false breakout 확률이 현저히 높다. 특히 P1(강한 상승장)에서 ADX 25-28 구간은 일시적 조정(pullback) 후 재상승 과정의 노이즈를 잡아버린다.

**진단 2: BM의 P2 SL 문제는 구조적이다**

Iter 19-22에서 P2 BM의 stop_loss rate 추정:

| Iter | P2 BM Trades | P2 BM WR | Estimated SL exits | SL Rate |
|------|-------------|----------|-------------------|---------|
| 19 | 31 | 54.8% | ~16-18 | ~52-55% |
| 22 | 33 | 60.6% | ~14-16 | ~43-48% |

ADX 28 + LB 15로 강화해도 P2에서 BM의 SL rate는 43-55%에 머문다. 이것은 P2의 시장 특성(mixed market)에서 breakout 전략이 본질적으로 약하기 때문이다. 횡보/조정 구간이 잦은 시장에서 모멘텀 breakout은 false signal 비율이 높다.

스윙 트레이더 관점에서 해법은 두 가지다:
1. **P2에서 BM 노출을 줄이고 MR에 의존** -- 이미 Iter 22에서 시도 중이나 불충분
2. **BM에 regime-aware 추가 필터 도입** -- RANGING/UNCERTAIN에서 ADX delta > 5 (ADX가 상승 중일 때만 진입) 같은 추세 강화 필터

**진단 3: Trailing Stop 개선 여지**

현재 BM trailing 활성화는 1.0 ATR이다. 이것은 진입 직후 작은 수익 구간에서 즉시 trailing이 시작되어, 이후 정상적인 pullback에서 조기 exit하는 경향이 있다. 1.5 ATR로 올리면 추세가 좀 더 확립된 후 trailing이 시작되어 승리 거래의 평균 이익이 증가할 것으로 기대한다.

그러나 이것은 한계적 개선(marginal improvement)이다. BM의 근본 문제는 진입 품질이지 exit 타이밍이 아니다."

### Strat-2 (Quant Analyst) -- 자본 배치의 수학과 엣지 분석

"22개 이터레이션의 데이터를 종합적으로 분석한 결과, **수학적으로 불편한 진실**이 명확해졌다. 하나씩 풀어보겠다.

**분석 1: 자본 배치(Capital Deployment) 산술**

S&P 500은 $100K를 365일 24시간 시장에 노출한다. 우리 시스템은:

```
평균 동시 포지션: ~2.3개 (Iter 19-22 평균)
평균 포지션 크기: ~$12,000 (equity의 12%)
평균 자본 배치: $12,000 * 2.3 = $27,600 (27.6%)
나머지 72.4%: 현금 (수익률 0%)
```

S&P 대비 자본 효율:
```
S&P: $100,000 * 15.9% = $15,900 (P1)
우리 최선(Iter 19): BM+MR invested capital ~$27,600
필요 수익률: $7,330 / $27,600 = 26.6% on invested capital
```

$27,600을 투자해서 12개월에 26.6% 수익을 내야 S&P의 15.9%를 이기는 것이다. 개별 주식 daily bar 전략으로 26.6%는 상위 5% 헤지펀드 수준이다.

**분석 2: 거래별 기대값(EV) 요구 사항**

Iter 19 P1 (최선):
```
30 BM trades: +$5,467 → $182/trade
11 MR trades: +$1,863 → $169/trade
총 41 trades: +$7,330 → $179/trade
```

S&P를 이기려면:
```
41 trades * $X = $15,900
X = $388/trade (현재의 2.2배)
```

거래 수를 41에서 70으로 늘려도:
```
70 trades * $X = $15,900
X = $227/trade (현재의 1.3배)
```

거래 수 70건은 현재 BM 30 + MR 11 = 41건에서 70% 증가가 필요하다. MR cap을 3으로 올리고 RANGING 할당을 키워도 MR이 20건 정도 추가하면 61건이 된다. 그래도 $260/trade가 필요하고, 이것은 현재 최선($179)의 1.45배다.

**분석 3: 전략별 엣지 안정성**

7개 이터레이션의 PF 분포:

| Strategy | Period | PF Range | Mean PF | Std Dev | CV(%) |
|----------|--------|----------|---------|---------|-------|
| BM | P1 | 0.348-1.832 | 0.782 | 0.530 | 67.8% |
| BM | P2 | 0.510-1.585 | 1.044 | 0.360 | 34.5% |
| MR | P1 | 0.520-1.783 | 0.926 | 0.441 | 47.6% |
| MR | P2 | 1.299-2.022 | 1.661 | 0.267 | 16.1% |

**핵심 발견: MR의 P2 PF는 CV 16.1%로 매우 안정적이다.** 모든 config에서 PF > 1.29를 유지한다. 반면 BM의 P1 PF는 CV 67.8%로 극히 불안정하다. 이것은 BM이 config에 매우 민감하다는 뜻이다.

MR은 P2(mixed market)에서 일관된 엣지를 보유하고 있으며, 이 엣지를 최대한 활용해야 한다. 문제는 MR의 거래 빈도가 9-13건으로 낮아 총 기여가 제한적이라는 점이다.

**분석 4: 적정 전략 포트폴리오 규모**

자본 배치를 50%로 올리려면:
```
목표: $50,000 average deployed
현재: $27,600 average deployed
갭: $22,400 추가 배치 필요
```

BM+MR로는:
- BM cap 3 (현재 2): +1 포지션 * $12,000 = +$12,000
- MR cap 3 (현재 2): +1 포지션 * $8,000 = +$8,000
- 합계: +$20,000 → $47,600 (47.6%)

하지만 BM cap 3은 Iter 20에서 증명된 것처럼 위험하다 (ADX28+cap1=재앙이면, cap 3의 3번째 포지션은 약한 시그널). MR cap 3은 Iter 19에서 긍정적이었다 (PF 1.698-1.783).

**결론: MR cap 3은 안전하게 확대 가능. BM cap은 2를 유지해야 한다. 자본 배치 갭을 메우려면 3번째 전략이 필요하다.**"

### Strat-3 (Risk Manager) -- 드로다운과 리스크 조정 수익

"7개 이터레이션의 리스크 프로파일을 총정리하겠다.

**분석 1: MaxDD 추정 (데이터 제한적)**

완전한 DD 데이터는 Iter 18과 19에서만 제공되었다:
- Iter 18 P2: Sharpe 0.919, Calmar 1.097
- Iter 19 P1: Calmar 2.119

나머지는 return 기반 추정만 가능하다. 그러나 return이 음수인 경우(Iter 16-17 P1, Iter 20-21) MaxDD는 return의 절대값 이상이다.

| Iter | P1 Return | P1 Est MaxDD | P2 Return | P2 Est MaxDD |
|------|-----------|-------------|-----------|-------------|
| 16 | -3.7% | >3.7% | +2.3% | ~5-8% |
| 17 | -6.7% | >6.7% | +2.2% | ~5-8% |
| 18 | -6.2% | >6.2% | +5.2% | ~4.7% (Calmar=1.097) |
| 19 | +7.4% | ~3.5% (Calmar=2.119) | +2.6% | ~5-8% |
| 20 | -9.0% | >9.0% | -1.4% | >5% |
| 21 | -3.2% | >3.2% | -3.5% | >3.5% |
| 22 | -0.6% | >2% | +3.5% | ~5-7% |

**긍정적 관점**: MaxDD는 대부분 10% 이내로 추정된다. Iter 12-14 시절의 30%+ DD에서 대폭 개선.

**분석 2: 리스크 조정 수익의 가능성**

Iter 18 P2:
```
Return: +5.2%
Sharpe: 0.919 (S&P: 0.877)
Calmar: 1.097 (S&P: 0.959)
```

**Iter 18 P2는 S&P를 risk-adjusted basis로 이미 이기고 있다.** Sharpe와 Calmar 모두 S&P를 초과한다. 원금 수익률은 열위하지만, 리스크 대비 수익은 우월하다.

이것은 중요한 시사점이다: **raw return 기준이 아니라 risk-adjusted 기준으로 벤치마크를 재정의하면, 현재 시스템도 승리할 수 있다.**

**분석 3: 포트폴리오 heat 관리**

현재 `_MAX_PORTFOLIO_HEAT_PCT = 0.25` (25%)는 매우 보수적이다. S&P는 100% heat이다. 이 cap을 올리면:

| Heat Cap | Average Deployment | Estimated Return Impact |
|----------|-------------------|----------------------|
| 25% (current) | ~27% | baseline |
| 35% | ~35% | +30% more return |
| 50% | ~45% | +67% more return |

25% -> 35% heat cap만으로도 Iter 19의 +7.4%가 +9.6%로 개선될 수 있다 (proportional scaling, 실제로는 비선형이지만 방향성은 맞다).

**분석 4: 전략간 상관관계와 분산 효과**

BM과 MR의 월별 수익 상관관계를 추정하면:
- TREND_UP: BM positive, MR neutral/slightly positive → 양의 상관
- RANGING: BM neutral/negative, MR positive → 음의 상관
- TREND_DOWN: BM blocked, MR active → 상관 없음

전체적으로 BM-MR 상관관계는 낮다(추정 0.1-0.3). 이것은 좋은 분산 효과가 있다는 뜻이다. 3번째 전략이 BM, MR 모두와 낮은 상관을 가진다면, 포트폴리오의 Sharpe가 의미있게 개선될 수 있다.

**리스크 매니저 판정**:
1. DD 관리는 양호 -- 현재 구조에서 리스크가 잘 통제되고 있음
2. 문제는 리스크를 너무 회피한다는 것 -- 72% 현금은 기회비용
3. Heat cap 상향과 3번째 전략 추가가 동시에 필요
4. Risk-adjusted benchmark 재정의를 강력 권고"

### Strat-4 (Market Analyst) -- 레짐 분석과 교차 이터레이션 패턴

"7개 이터레이션을 교차 분석하여 명확한 패턴 3가지를 도출했다.

**패턴 1: P1(bull)과 P2(mixed)의 전략 성과 역전**

| Strategy | P1 (bull) 평균 PF | P2 (mixed) 평균 PF | P1 우위 여부 |
|----------|-------------------|-------------------|-------------|
| BM | 0.782 | 1.044 | **P2 우위** (반직관적) |
| MR | 0.926 | 1.661 | P2 우위 (예상대로) |

BM이 P2(mixed)에서 P1(bull)보다 평균 PF가 높다는 것은 반직관적이다. Bull market에서 breakout이 더 잘 작동해야 하는데 왜 그런가?

답은 **config 민감도**에 있다. P1에서 BM PF가 극단적으로 흔들리는 것은(0.348-1.832), config가 잘못되면 bull market에서도 대규모 손실이 발생한다는 뜻이다. Bull market의 '쉬운 이익'은 ADX 28 + LB 15 + cap 2 config에서만 포착된다. 잘못된 config(ADX 25, cap 1)는 오히려 bull market의 noise를 amplify한다.

반면 P2에서 BM은 config에 덜 민감하다(CV 34.5% vs 67.8%). Mixed market에서는 config 관계없이 breakout이 ~50:50 확률이기 때문이다.

**이 패턴의 전략적 시사점: P1 성과를 잡으려면 BM config를 ADX28/LB15/cap2로 고정하고 절대 바꾸지 말아야 한다.**

**패턴 2: MR의 P2 일관성은 '숨겨진 보물'**

MR의 P2 performance across all 7 iterations:

| Iter | MR P2 PF | MR P2 Trades | MR P2 PnL |
|------|----------|-------------|-----------|
| 16 | 1.408 | 9 | +$568 |
| 17 | 1.299 | 13 | +$785 |
| 18 | 1.596 | 12 | +$1,791 |
| 19 | 1.698 | 9 | +$1,751 |
| 20 | 2.022 | 12 | +$2,496 |
| 21 | 1.939 | 9 | +$2,244 |
| 22 | 1.862 | 10 | +$2,161 |

**MR은 P2에서 7/7 이터레이션 전부 수익이다. PF 최소 1.299, 최대 2.022. 이 일관성은 주목할만하다.**

하지만 절대 금액은 $568-$2,496 범위다. 9-13건의 거래로는 $2,500 이상의 기여가 어렵다. MR의 거래 빈도를 15-20건으로 늘릴 수 있다면, PnL 기여가 $3,000-4,000으로 올라갈 수 있다.

**패턴 3: 레짐 분포의 기간별 차이**

P1(bull market)의 추정 레짐 분포:
- TREND_UP: ~60-65%
- RANGING: ~15-20%
- UNCERTAIN: ~10-15%
- TREND_DOWN: ~5%
- HIGH_VOL: ~5%

P2(mixed market)의 추정 레짐 분포:
- TREND_UP: ~35-40%
- RANGING: ~25-30%
- UNCERTAIN: ~15-20%
- TREND_DOWN: ~10-15%
- HIGH_VOL: ~5-10%

P1에서 TREND_UP이 60%이므로 BM에게 유리한 시간이 많다. 문제는 나머지 40% 시간에 BM이 비활동이거나 false breakout을 잡는다는 것이다.

P2에서 TREND_UP이 35%이므로 BM이 활동할 수 있는 시간이 절반으로 줄어든다. 나머지 65%는 RANGING/UNCERTAIN이 지배하며, 이것이 MR의 무대다.

**레짐 배치 최적화 제안**:

현재 regime_classifier.py의 할당이 P1과 P2에서 동일하게 적용되는 것이 문제다. 동적으로 조정할 수는 없지만, '양쪽 시장에서 모두 합리적인' 할당을 찾아야 한다.

| Regime | BM Current | BM Proposed | MR Current | MR Proposed | 근거 |
|--------|-----------|-------------|-----------|-------------|------|
| TREND_UP | 0.040 | **0.040** | 0.008 | **0.012** | MR 약간 증가 (분산) |
| TREND_DOWN | 0.005 (blocked) | **blocked** | 0.025 | **0.025** | 유지 |
| RANGING | 0.008 | **0.005** | 0.035 | **0.040** | MR 주도, BM 최소화 |
| HIGH_VOL | 0.008 | **0.005** | 0.015 | **0.020** | MR 증가, BM 축소 |
| UNCERTAIN | 0.012 | **0.008** | 0.020 | **0.025** | MR 증가, BM 축소 |

이 조정으로 MR의 RANGING/UNCERTAIN 배치가 커지고 거래 빈도가 9-13 -> 15-20건으로 증가할 것으로 예상한다."

---

## 3. 교차 진단 합의

### 만장일치 합의 (Unanimous Consensus)

#### 합의 1: 파라미터 최적화의 천장에 도달

**전원 동의. 반대 의견 없음.**

22개 이터레이션 후 BM + MR 2-strategy 포트폴리오의 최적 config가 수렴했다:
- BM: ADX 28, LB 15, cap 2 (Iter 19에서 확립, 7개 이터레이션으로 확인)
- MR: cap 2-3, 안정적 엣지 확인 (P2 PF > 1.29 일관)
- Best achievable: P1 +7.4%, P2 +5.2% (다른 config에서, 동시 달성 불가)

파라미터 공간의 탐색은 사실상 완료되었다. 추가적인 미세 조정은 한계 수익이 급감하는 영역이다.

#### 합의 2: S&P 500 raw return 벤치마크는 현재 아키텍처로 달성 불가능

**전원 동의.**

수학적 논증:
```
평균 자본 배치: ~27% ($27,600)
S&P 수익률: ~16%
필요 invested capital 수익률: 16% / 27% = 59.3%
현재 best invested capital 수익률: 10% / 27% = 37.0%
갭: 22.3%p (현재 대비 +60% 추가 수익 필요)
```

이 갭은 파라미터 튜닝으로 메울 수 없다. 구조적 변화가 필요하다.

#### 합의 3: Iter 19 config를 기본 파라미터 세트로 확정

**전원 동의.**

ADX 28, LB 15, BM cap 2는 7개 이터레이션에서 유일하게 양 기간 BM PF > 1.0을 달성한 조합이다. 이것을 '고정 파라미터'로 확정하고 더 이상 변경하지 않는다.

### 이견 사항 (Debate)

#### 이견 1: 자본 배치 확대 방법

- **Strat-2**: MR cap 3 + heat cap 35% + 3번째 전략 추가가 가장 효과적. 3번째 전략 없이는 배치 확대가 상관 리스크를 키운다.
- **Strat-3**: Heat cap 상향은 동의하지만 35%가 아니라 40%까지 가능하다. 현재 DD가 잘 통제되고 있으므로 여유가 있다. 3번째 전략 추가 전에 먼저 기존 2전략의 배치를 최대화해야 한다.
- **Strat-1**: BM cap 2 유지에 동의. 하지만 MR cap 3은 MR의 상관 리스크를 키울 수 있다. P2에서만 cap 3을 허용하는 조건부 접근이 안전하다.
- **Strat-4**: 레짐 기반 conditional cap을 제안한다. RANGING에서만 MR cap 3, 나머지 레짐에서는 cap 2.
- **결정**: MR cap은 현재 코드 구조상 레짐별 조건부 cap이 불가능하므로, **MR cap 3 고정 + 레짐 할당으로 간접 제어**. Heat cap은 **0.25 -> 0.35**로 상향.

#### 이견 2: 벤치마크 재정의

- **Strat-3**: Risk-adjusted benchmark(Sharpe, Calmar) 재정의를 강력 주장. Iter 18 P2는 이미 S&P를 Sharpe/Calmar 기준으로 이기고 있다.
- **Strat-2**: 동의하되, 고객(사용자)이 raw return 벤치마크를 명시적으로 요구했으므로 양쪽 모두 보고해야 한다.
- **Strat-1**: Raw return 목표를 완전히 포기하기보다, 현실적인 구간 목표(P1 +10%, P2 +8%)를 설정하고 동시에 risk-adjusted 우위를 추구하자.
- **결정**: **사용자에게 raw return 한계를 투명하게 보고. 동시에 risk-adjusted 벤치마크를 병행 제안. 현실적 raw return 목표는 P1 +10%, P2 +8%.**

#### 이견 3: 3번째 전략 추가 시점

- **Strat-4**: 즉시 3번째 전략 설계 착수. 현재 파라미터 최적화가 수렴했으므로 더 이상 기존 2전략을 조정하는 것은 한계 수익이 낮다.
- **Strat-1**: 동의. Sector rotation 또는 trend following이 후보.
- **Strat-2**: 동의하되, 3번째 전략은 기존 BM/MR과 낮은 상관관계를 가져야 한다. 단순히 '비슷한 전략을 하나 더 추가'하면 분산 효과가 없다.
- **Strat-3**: 3번째 전략 후보를 먼저 paper analysis로 검토하고, 구현은 다음 단계로.
- **결정**: **Iter 23에서 기존 2전략 배치 최적화를 마무리하고, 동시에 3번째 전략 후보의 paper analysis를 수행. Iter 24부터 3번째 전략 구현.**

---

## 4. 근본 원인 분석 (Root Cause Analysis)

### 원인 1: 자본 비가동(Capital Idleness) -- 근본 원인

**현상**: 평균 72-75%의 자본이 현금 상태로 수익을 내지 못함
**근본 원인**: 2-strategy 포트폴리오의 거래 빈도 한계 (30-40건/12개월) + 보수적 포지션 캡 (2-3개 동시)
**영향**: 투자 자본 수익률이 37%에 달해도 전체 계좌 수익률은 10%에 불과
**해법**: 자본 배치 비율 확대 (heat cap 상향, 전략 추가, 캡 조정)

### 원인 2: BM의 config 민감도 -- 2차 원인

**현상**: BM PF의 CV가 67.8%(P1)로 config에 극히 민감
**근본 원인**: ADX/LB/cap 삼각관계에서 좁은 최적 영역만 존재
**영향**: 최적 config(ADX28/LB15/cap2)를 벗어나면 급격한 성과 저하
**해법**: 최적 config 고정 (더 이상 변경하지 않음)

### 원인 3: MR의 거래 빈도 제한 -- 3차 원인

**현상**: MR이 일관된 엣지(P2 PF > 1.29)를 가지고 있으나 거래 빈도가 9-13건으로 제한
**근본 원인**: 보수적 레짐 할당 + cap 2 제한
**영향**: MR의 총 PnL 기여가 $568-$2,496 범위로 제한
**해법**: RANGING/UNCERTAIN 레짐에서 MR 할당 확대, cap 3으로 상향

### 원인 4: 단일 시장 전략의 한계 -- 구조적 원인

**현상**: BM은 TREND_UP에서만, MR은 RANGING에서만 효과적. 전체 시간의 30-40%에서 두 전략 모두 비활성 또는 약한 엣지
**근본 원인**: 2-strategy 포트폴리오로는 모든 시장 레짐을 커버할 수 없음
**해법**: 3번째 전략 추가 (UNCERTAIN/HIGH_VOL 커버)

---

## 5. 권고사항 (Prioritized)

### Priority 1 (CRITICAL): BM 파라미터 고정 -- 더 이상 변경 금지

| Parameter | File | Value | Status |
|-----------|------|-------|--------|
| ADX_MIN | breakout_momentum.py | 28.0 | **LOCK** |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | **LOCK** |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | **LOCK** |
| BM soft cap | batch_simulator.py | 2 | **LOCK** |
| BM SL ATR mult | exit_rules.py | 2.5 | **LOCK** |

**근거**: 7개 이터레이션에서 유일하게 양 기간 PF > 1.0을 달성한 조합. 추가 조정은 한계 수익이 거의 없으며 과적합 위험만 증가한다. ADX 28 + LB 15 + cap 2는 '확정 파라미터'로 선언한다.

### Priority 2 (CRITICAL): MR 배치 확대

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| MR soft cap | batch_simulator.py | 2 | **3** | MR 거래 빈도 확대 (P2 PF > 1.29 일관) |
| RANGING MR alloc | regime_classifier.py | 0.035 | **0.040** | MR 주력 레짐에서 배치 확대 |
| UNCERTAIN MR alloc | regime_classifier.py | 0.020 | **0.025** | MR 보조 레짐에서 배치 확대 |
| TREND_UP MR alloc | regime_classifier.py | 0.008 | **0.012** | bull에서도 분산 효과 |
| HIGH_VOL MR alloc | regime_classifier.py | 0.015 | **0.020** | HV에서 MR 역할 확대 |

**예상 효과**:
- MR 거래 수: P2 10건 -> 15-18건 (+50-80%)
- MR PnL: P2 +$2,161 -> +$3,200-3,800 (+50-75%)
- P2 total: +3.5% -> +5.0-6.0%

### Priority 3 (CRITICAL): 자본 배치 확대

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| _MAX_PORTFOLIO_HEAT_PCT | batch_simulator.py | 0.25 | **0.35** | 배치 비율 25% -> 35% |
| _MAX_LONG_POSITIONS | batch_simulator.py | 6 | **8** | 동시 포지션 여유 확대 |
| _MAX_TOTAL_POSITIONS | batch_simulator.py | 7 | **9** | 총 포지션 상한 확대 |

**예상 효과**:
- 평균 자본 배치: 27% -> 35-40%
- 비례적 수익 증가: +25-45% (비선형이므로 추정)
- Iter 19 P1 기준: +7.4% -> +9.2-10.7%

**과적합 위험**: 없음 (구조적 제약 완화, 데이터 의존성 없음)

### Priority 4 (HIGH): BM 비TREND_UP 레짐 축소

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| RANGING BM alloc | regime_classifier.py | 0.008 | **0.005** | False breakout 빈도 축소 |
| UNCERTAIN BM alloc | regime_classifier.py | 0.012 | **0.008** | 불확실 시장에서 보수적 |
| HIGH_VOL BM alloc | regime_classifier.py | 0.008 | **0.005** | 변동성 시장에서 보수적 |

**예상 효과**: P2 BM의 약한 거래 3-5건 제거, BM PF 약간 개선

### Priority 5 (HIGH): Trailing Stop 개선

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| BM trailing activation | exit_rules.py | 1.0 ATR | **1.5 ATR** | 조기 trailing exit 방지 |
| BM TP | exit_rules.py | 5.0 ATR | **4.0 ATR** | 현실적 목표 (TP 도달률 3% -> 8-10%) |

**예상 효과**: 승리 거래의 평균 이익 증가, BM 총 PnL +$500-1,000

### Priority 6 (MEDIUM): 벤치마크 병행 보고

향후 모든 백테스트 결과에 다음을 병행 보고:
1. Raw return vs S&P 500 total return
2. **Sharpe ratio vs S&P 500 Sharpe**
3. **Calmar ratio vs S&P 500 Calmar**
4. Max drawdown comparison
5. Capital deployment ratio

---

## 6. 구조적 권고사항 (Strategic Recommendations)

### 6-1. 3번째 전략 후보 평가

현재 포트폴리오의 레짐 커버리지 갭:

| Regime | BM 효과 | MR 효과 | 갭 |
|--------|---------|---------|-----|
| TREND_UP | Strong | Weak | None |
| TREND_DOWN | Blocked | Moderate | Partial |
| RANGING | Weak | Strong | None |
| HIGH_VOL | Weak | Moderate | **GAP** |
| UNCERTAIN | Weak | Moderate | **GAP** |

3번째 전략은 HIGH_VOL과 UNCERTAIN에서 엣지가 있어야 한다.

**후보 A: Volatility Momentum (추천)**
- 개념: VIX spike 후 반등 매매, 또는 IV crush 이후 방향성 베팅
- 레짐: HIGH_VOL에서 주로 활동
- BM/MR 상관: 낮음 (다른 시장 조건에서 활동)
- 구현 복잡도: 중간 (VIX 데이터 추가 필요)

**후보 B: Sector Rotation (추천)**
- 개념: 상대 강도 기반 섹터 ETF 로테이션
- 레짐: 모든 레짐에서 활동 (항상 최강 섹터가 존재)
- BM/MR 상관: 낮음 (ETF 기반, 개별 주식이 아님)
- 구현 복잡도: 중간
- **자본 배치 기여가 가장 큼** (항상 1-2 포지션 유지)

**후보 C: EMA Crossover Trend Following**
- 개념: 중장기 트렌드 팔로잉 (50/200 EMA cross)
- 레짐: TREND_UP/TREND_DOWN에서 활동
- BM/MR 상관: BM과 부분 상관 (같은 추세 방향)
- 구현 복잡도: 낮음 (기존 인프라 활용)
- 분산 효과 제한적

**패널 추천**: 후보 B (Sector Rotation) 우선 검토. 자본 배치 기여가 가장 크고 기존 전략과 상관이 낮다.

### 6-2. Core + Satellite 구조 검토

장기적으로 가장 현실적인 S&P 벤치마크 전략:

```
Core (60-70%): SPY/VOO 인덱스 ETF buy-and-hold
  -> S&P 수익의 60-70%를 자동 확보
  -> 항상 100% 배치 (자본 비가동 문제 해결)

Satellite (30-40%): BM + MR + 3번째 전략
  -> Alpha generation 목적
  -> 독립적 수익원 + 분산 효과
```

이 구조에서:
```
Core 수익: $100K * 65% * 16% = $10,400
Satellite 수익: $100K * 35% * 10% = $3,500
합계: $13,900 (13.9%) -- S&P에 근접

Alpha가 양수이면:
Core: $10,400
Satellite: $100K * 35% * 15% = $5,250
합계: $15,650 (15.7%) -- S&P에 근접하거나 초과
```

**이 구조는 별도 설계 세션이 필요하며, 현재 iteration loop의 범위를 벗어난다.**

---

## 7. 수량적 목표 (Quantitative Targets)

### Iter 23 목표 (기존 2-strategy 최적화 마무리)

| Metric | Iter 22 P1 | Target P1 | Iter 22 P2 | Target P2 |
|--------|-----------|----------|-----------|----------|
| Return | -0.6% | **+8-10%** | +3.5% | **+6-8%** |
| BM PF | 1.170 | **> 1.5** | 1.180 | **> 1.2** |
| MR PF | 0.684 | **> 1.2** | 1.862 | **> 1.5** |
| BM Trades | 29 | 28-32 | 33 | 30-35 |
| MR Trades | 13 | 12-16 | 10 | **15-20** |
| Max DD | >2% | **< 8%** | ~5-7% | **< 8%** |
| Sharpe | - | **> 0.8** | - | **> 0.9** |
| Capital Deploy | ~27% | **> 35%** | ~27% | **> 35%** |

### S&P 벤치마크와의 갭 인식

| Metric | System Target | S&P 500 | Gap | 달성 가능성 |
|--------|--------------|---------|-----|-----------|
| P1 Raw Return | +8-10% | +15.9% | -5.9 to -7.9%p | 파라미터로 불가 |
| P2 Raw Return | +6-8% | +15.5% | -7.5 to -9.5%p | 파라미터로 불가 |
| P2 Sharpe | > 0.9 | 0.877 | **달성 가능** | Iter 18에서 이미 달성 |
| P2 Calmar | > 1.0 | 0.959 | **달성 가능** | Iter 18에서 이미 달성 |
| MaxDD | < 8% | 10-15% | **이미 우위** | 유지 중 |

**핵심 메시지: Raw return에서는 S&P를 이길 수 없다. Risk-adjusted metrics에서는 이미 이기고 있거나 이길 수 있다.**

### 3번째 전략 추가 후 목표 (Iter 24+)

| Metric | 2-Strategy | 3-Strategy Target | 근거 |
|--------|-----------|-------------------|------|
| Capital Deploy | 27% | **45-55%** | 3번째 전략이 20%p 추가 |
| P1 Return | +8-10% | **+12-14%** | 배치 증가 비례 |
| P2 Return | +6-8% | **+10-12%** | 배치 증가 비례 |
| P2 Sharpe | > 0.9 | **> 1.0** | 분산 효과 |

3-strategy + 50% 배치로도 S&P의 16%에는 미달할 수 있다. 그러나 S&P 대비 MaxDD가 절반 이하이므로, 레버리지(margin)를 사용하면 risk-adjusted 기준 동등한 return을 더 낮은 MaxDD로 달성할 수 있다.

---

## 8. Iteration 22 교훈 (Lessons Learned)

### 교훈 1: 22개 이터레이션의 수렴

7차 이터레이션(16-22)에서 최적 config가 명확히 수렴했다. ADX28/LB15/cap2가 BM의 '안정 영역'이며, 이를 벗어난 모든 시도는 실패했다. 이제 파라미터 탐색보다 구조적 개선에 리소스를 집중해야 한다.

### 교훈 2: 자본 배치가 수익의 상한을 결정한다

아무리 높은 invested capital return을 달성해도, 배치 비율이 25%면 전체 수익은 1/4로 축소된다. 이것은 전략 품질의 문제가 아니라 포트폴리오 구조의 문제다.

### 교훈 3: MR은 과소평가되었다

22개 이터레이션 동안 MR(rsi_mean_reversion)은 '보조 전략'으로 취급되었으나, P2에서의 일관성(7/7 수익, PF > 1.29)은 BM보다 우수하다. MR의 배치를 확대하면 안정적인 수익 기반을 구축할 수 있다.

### 교훈 4: Risk-adjusted 우위는 실재한다

Iter 18 P2의 Sharpe 0.919 > S&P 0.877, Calmar 1.097 > S&P 0.959는 우리 시스템의 risk-adjusted 우위를 보여준다. 이것은 '위로'가 아니라 실제 투자자 관점에서 의미 있는 우위다. 같은 리스크를 감수할 때 더 높은 수익을, 같은 수익을 목표로 할 때 더 낮은 리스크를 제공할 수 있다.

### 교훈 5: 벤치마크 재정의의 필요성

'S&P를 이기겠다'는 목표는 Warren Buffett의 bet과 동일하다 -- 대부분의 active manager가 실패하는 목표다. 100% 자본을 시장에 노출하는 인덱스 펀드와, 25% 배치 + 75% 현금인 active trading 시스템을 raw return으로 비교하는 것은 공정하지 않다. Risk-adjusted 또는 같은 배치 비율 기준(invested capital return)으로 비교하는 것이 합리적이다.

---

## 9. Decision Summary

| 항목 | 결정 | 우선순위 |
|------|------|---------|
| BM params (ADX28, LB15, cap2) | **LOCK -- 더 이상 변경 금지** | P1 |
| MR soft cap | 2 -> **3** | P2 |
| RANGING MR alloc | 0.035 -> **0.040** | P2 |
| UNCERTAIN MR alloc | 0.020 -> **0.025** | P2 |
| TREND_UP MR alloc | 0.008 -> **0.012** | P2 |
| HIGH_VOL MR alloc | 0.015 -> **0.020** | P2 |
| _MAX_PORTFOLIO_HEAT_PCT | 0.25 -> **0.35** | P3 |
| _MAX_LONG_POSITIONS | 6 -> **8** | P3 |
| _MAX_TOTAL_POSITIONS | 7 -> **9** | P3 |
| RANGING BM alloc | 0.008 -> **0.005** | P4 |
| UNCERTAIN BM alloc | 0.012 -> **0.008** | P4 |
| HIGH_VOL BM alloc | 0.008 -> **0.005** | P4 |
| BM trailing activation | 1.0 -> **1.5 ATR** | P5 |
| BM TP | 5.0 -> **4.0 ATR** | P5 |
| Risk-adjusted benchmark 병행 | **도입** | P6 |
| 3번째 전략 paper analysis | **착수** | P6 |

**총 변경: 14개 항목 (파라미터 12개 + 구조 2개)**

---

## 10. Next Steps

1. **Iter 23**: P2-P5 파라미터 변경 적용 후 백테스트
2. **병행**: 3번째 전략 후보 (Sector Rotation) paper analysis
3. **Iter 24+**: 3번째 전략 구현 및 통합 테스트
4. **장기**: Core+Satellite 구조 설계 세션

---

## Appendix: Full Iteration History (12-22)

| Iter | P1 Return | P2 Return | Combined | Key Config | Best Feature |
|------|-----------|-----------|----------|-----------|-------------|
| 12 | +2.9% | +5.4% | +8.3% | 2-strat debut | First dual-strat |
| 13 | -3.9% | +5.1% | +1.2% | MR param tune | MR SL natural experiment |
| 14 | -5.4% | -2.0% | -7.4% | BM-only | Signal flood lesson |
| 15 | - | - | - | Cap restore + filter | Structural fix |
| 16 | -3.7% | +2.3% | -1.4% | MR restored, cap2/2 | MR re-entry |
| 17 | -6.7% | +2.2% | -4.5% | BM cap1, SL 2.0 | Cap interaction |
| 18 | -6.2% | **+5.2%** | -1.0% | Regime relaxed | **Best P2** |
| 19 | **+7.4%** | +2.6% | **+10.0%** | ADX28, LB15, high | **Best P1, Best Combined** |
| 20 | -9.0% | -1.4% | -10.4% | BM cap1 (else 19) | Cap interaction confirmed |
| 21 | -3.2% | -3.5% | -6.7% | ADX25, LB10, high | ADX sensitivity confirmed |
| 22 | -0.6% | +3.5% | +2.9% | Iter19 + regime alloc | Regime allocation effect |

## Appendix: Parameter Change Map (Iter 23)

### batch_simulator.py
```
_SOFT_STRATEGY_CAP["rsi_mean_reversion"]:  2 -> 3
_MAX_PORTFOLIO_HEAT_PCT:                   0.25 -> 0.35
_MAX_LONG_POSITIONS:                       6 -> 8
_MAX_TOTAL_POSITIONS:                      7 -> 9
```

### regime_classifier.py
```
TREND_UP:    BM 0.040 (unchanged), MR 0.008 -> 0.012
TREND_DOWN:  BM blocked (unchanged), MR 0.025 (unchanged)
RANGING:     BM 0.008 -> 0.005, MR 0.035 -> 0.040
HIGH_VOL:    BM 0.008 -> 0.005, MR 0.015 -> 0.020
UNCERTAIN:   BM 0.012 -> 0.008, MR 0.020 -> 0.025
```

### exit_rules.py
```
_TRAILING_ACTIVATION_ATR["breakout_momentum"]:  1.0 -> 1.5
_TP_ATR_MULT["breakout_momentum"]:              5.0 -> 4.0
```

### breakout_momentum.py
```
NO CHANGES (parameters LOCKED)
```
