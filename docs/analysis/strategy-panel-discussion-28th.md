# Strategy Panel Discussion #28: Iteration 23 Review

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iteration 23 -- Panel #27 changes applied (MR cap 3, heat 35%, MAX_LONG 8, TP 4.0, trailing 1.5). Best combined return ever (+15.4%) but MaxDD exploded to 20%+.
**Verdict**: **RETURN BREAKTHROUGH BUT RISK CRISIS -- Drawdown must be halved before deployment is viable.**

---

## 1. Backtest Results Summary (Iteration 23)

### Performance Table

| Metric | P1 (Bull) | P1 S&P | P2 (Mixed) | P2 S&P |
|--------|-----------|--------|------------|--------|
| Return | +7.5% | +15.9% | +7.9% | +15.5% |
| MaxDD | 20.2% | 8.5% | 21.0% | 16.3% |
| Sharpe | 0.384 | 1.221 | 0.395 | 0.877 |
| Calmar | 0.375 | 1.900 | 0.378 | 0.959 |
| Trades | 47 | - | 52 | - |
| WR | 70.2% | - | 80.8% | - |
| PF | 1.577 | - | 2.030 | - |

### Strategy Breakdown

| Strategy | Period | Trades | WR | PF | PnL | SL Exit Rate |
|----------|--------|--------|-----|-----|------|-------------|
| BM | P1 | 34 | 73.5% | 1.806 | +$7,105 | 73.5% (25/34) |
| BM | P2 | 40 | 82.5% | 1.618 | +$3,156 | 70.0% (28/40) |
| MR | P1 | 13 | 61.5% | 1.078 | +$319 | 61.5% (8/13) |
| MR | P2 | 12 | 75.0% | 2.858 | +$4,718 | 41.7% (5/12) |

### Win/Loss Asymmetry

| Period | Avg Win | Avg Loss | Ratio |
|--------|---------|----------|-------|
| P1 | $615 | $919 | 0.67 |
| P2 | $369 | $764 | 0.48 |

### Iteration History Context

| Iter | P1 Return | P2 Return | Combined | MaxDD (est.) |
|------|-----------|-----------|----------|-------------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% (P1) |
| 22 | -0.6% | +3.5% | +2.9% | ~5-7% |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20-21%** |

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- Stop-Loss Exit 지배 현상의 해부

"Iter 23은 이전 최고 기록을 5%p 넘게 경신했다. 그러나 스윙 트레이더 관점에서 이 결과는 '운이 좋았다'라고 진단해야 한다. 이유는 분명하다.

**진단 1: Stop-Loss Exit Rate 73.5%의 의미**

BM P1에서 34건 중 25건이 stop_loss exit이다. 여기서 73.5% WR과 73.5% SL exit rate가 동시에 성립하는 것은, 2-stage SL upgrade 시스템 덕분이다:

```
34 trades total:
- 25 wins (73.5% WR)
- 9 losses
- 25 SL exits (73.5%)

SL exit 25건 중:
- 최소 16건은 breakeven/profit-lock SL exits (수익으로 계산됨)
- 최대 9건은 full-stop losses

Non-SL exits (9건):
- take_profit, trailing_stop, time_exit 등
```

이것은 2-stage SL upgrade가 실질적으로 작동하고 있다는 증거다. Stage 1 (breakeven at 1.5 ATR)과 Stage 2 (profit lock at 0.4 ATR)가 수많은 포지션을 '제로 손실' 또는 '소액 수익'으로 전환시키고 있다.

**그러나 문제는 수익 규모다.** Breakeven/profit-lock SL exit은 수익이 +$0 ~ +$50 수준이다. 반면 full-stop loss는 -$919 평균이다. 이것이 Avg Win $615 < Avg Loss $919의 원인이다.

실제 구조:
```
P1 수익 분포 (추정):
- 16건 profit-lock SL exits: 평균 +$50 = +$800
- 9건 non-SL exits (TP/trailing/time): 평균 +$700 = +$6,300
- 9건 full-stop losses: 평균 -$919 = -$8,271
- 합계: $800 + $6,300 - $8,271 = -$1,171... 하지만 실제 PnL은 +$7,105
```

계산이 맞지 않으므로, SL exit 중 상당수가 Stage 2 profit-lock에서 발생하여 의미있는 수익($200-500)을 내고 있을 가능성이 높다. 그래도 **TP나 trailing_stop으로 빠지는 거래가 9건/34건 = 26%에 불과**한 것은 문제다.

**진단 2: 왜 대부분이 TP/Trailing에 도달하지 못하는가**

현재 exit 구조:
```
BM: SL 2.5 ATR | TP 4.0 ATR | Trailing activation 1.5 ATR, trail 2.0 ATR
```

SL 2.5 ATR 대비 TP 4.0 ATR는 risk:reward = 1:1.6이다. 이론적으로는 나쁘지 않지만, daily bar 기준으로 4.0 ATR 이동은 쉽지 않다. 평균 보유 기간이 5일이면 일일 ATR의 4배를 축적해야 하는데, 이것은 강한 추세가 있을 때만 가능하다.

Trailing activation 1.5 ATR은 합리적이지만, trailing distance 2.0 ATR는 너무 넓다. 1.5 ATR까지 올라간 뒤 2.0 ATR 하락하면 활성화 시점보다 0.5 ATR 아래에서 exit한다. 사실상 entry 대비 손실이 될 수 있다.

**처방: Trailing distance를 1.5 ATR로 축소하면, trailing 활성화 후에는 최소한 entry 수준에서 exit을 보장한다.**

**진단 3: 20% MaxDD의 메커니즘**

20% DD가 발생하려면 다음이 동시에 일어나야 한다:
```
- 다수 포지션이 동시에 full-stop에 도달
- Heat 35%에서 3-4개 포지션이 열려 있을 때
- 각 포지션이 2-2.5% equity 손실
- 3-4개 * 2.5% = 7.5-10% per event
- 2-3번 반복되면 15-20%
```

Iter 22(heat 25%)에서 MaxDD ~5-7%였고, Iter 23(heat 35%)에서 20%가 되었다. Heat 10%p 상승이 DD를 3배 증가시켰다. 이것은 **비선형 관계**이며, heat 상향의 위험을 과소평가했다."

### Strat-2 (Quant Analyst) -- 수량적 구조 분석

"Iter 23은 수학적으로 흥미로운 결과를 보여준다. 숫자를 정밀하게 뜯어보겠다.

**분석 1: Return/Risk Efficiency의 급격한 악화**

| Metric | Iter 19 (추정) | Iter 22 (추정) | Iter 23 | 변화 방향 |
|--------|-------------|-------------|---------|----------|
| P1 Return | +7.4% | -0.6% | +7.5% | 개선 |
| P1 MaxDD | ~3.5% | ~2-3% | 20.2% | **6배 악화** |
| P1 Calmar | 2.119 | - | 0.375 | **82% 하락** |
| P2 Return | +2.6% | +3.5% | +7.9% | 개선 |
| P2 MaxDD | ~5-8% | ~5-7% | 21.0% | **3배 악화** |

**Return은 2배 늘었지만 MaxDD는 4-6배 증가했다.** 이것은 전형적인 '과도한 레버리지' 패턴이다. Heat cap을 25%->35%로 올린 것이 주범이다.

**분석 2: 기대값(EV) per Trade 분석**

```
P1: 47 trades, +$7,424 total -> $158/trade
P2: 52 trades, +$7,874 total -> $151/trade
Combined: 99 trades, +$15,298 -> $155/trade
```

Iter 19 대비:
```
Iter 19: 41 trades, +$10,000 -> $244/trade
Iter 23: 99 trades, +$15,298 -> $155/trade
```

**거래 건수가 141% 증가했지만 EV/trade는 37% 감소했다.** 총 수익이 증가한 것은 순전히 거래 빈도 증가(volume) 때문이지, 거래 품질(edge) 개선이 아니다.

이것은 위험 신호다. 더 많은 거래를 발생시키기 위해 엣지가 약한 시그널까지 포착하고 있다는 뜻이다.

**분석 3: BM vs MR의 기여 비율 변화**

```
P1: BM $7,105 (95.7%) + MR $319 (4.3%) = $7,424
P2: BM $3,156 (40.1%) + MR $4,718 (59.9%) = $7,874
```

P1에서 MR의 기여가 4.3%로 사실상 무의미하다. MR cap을 3으로 올렸음에도 P1 MR은 13건/PF 1.078에 그친다. **P1에서 MR cap 3은 실패한 실험이다.**

반면 P2에서 MR은 12건만으로 $4,718(59.9%)를 기여했다. PF 2.858은 우리 시스템 역사상 최고 PF다. **MR의 P2 엣지는 구조적으로 강하며, 거래 빈도를 늘리면 더 큰 기여가 가능하다.**

**분석 4: Stop-Loss Exit의 수학적 분석**

P2 MR의 SL exit rate 41.7% (5/12) vs P1 MR의 61.5% (8/13). 이 차이의 원인:

P1은 bull market로 ADX가 높은 기간이 많다. MR은 ADX < 20에서만 진입하지만, 진입 후 ADX가 상승하면 가격이 mean-reversion과 반대 방향으로 이동한다. P1의 RANGING 기간이 짧기 때문에, 진입 후 빠르게 TREND로 전환되어 SL을 hit하는 패턴이 반복된다.

P2는 mixed market로 RANGING 기간이 길고 안정적이다. 진입 후에도 RANGING이 유지되어 mean-reversion이 완성될 시간이 있다.

**결론: MR P1의 문제는 파라미터가 아니라 시장 구조다. 파라미터 조정으로는 해결할 수 없다.**

**분석 5: 적정 Heat Cap 역산**

목표: MaxDD < 15%
현재: Heat 35% -> MaxDD 20%
선형 스케일링 가정: MaxDD = f(heat) -> 20% = f(0.35)

MaxDD와 heat의 관계를 추정하면:
```
Heat 25% -> MaxDD ~7% (Iter 22 추정)
Heat 35% -> MaxDD ~20% (Iter 23 실측)

기울기: (20-7)/(35-25) = 1.3% DD per 1% heat
```

MaxDD 15% 목표:
```
15% = 7% + 1.3 * (heat - 25)
8 = 1.3 * (heat - 25)
heat - 25 = 6.15
heat = 31.15% -> 약 31%
```

**Heat 31%가 MaxDD 15%를 유지하면서 수익을 극대화하는 균형점이다.**

그러나 이것은 선형 가정이다. 실제로 DD는 heat에 대해 볼록(convex)하므로, **Heat 30%가 안전한 선택이다.**"

### Strat-3 (Risk Manager) -- 드로다운 위기와 GDR 실패 진단

"Iter 23의 결과를 리스크 매니저 관점에서 보면, **Panel #27의 결정이 리스크 관리를 파괴했다**고 평가해야 한다. 구체적으로 분석하겠다.

**진단 1: MaxDD 20%는 배치 불가 수준**

어떤 투자자도 $100K 계좌에서 $20K(20%)를 잃은 후 +7.5%의 연 수익에 만족하지 않는다. S&P는 8.5% DD로 15.9% 수익이다. 우리는 20% DD로 7.5% 수익이다.

```
S&P Calmar: 15.9% / 8.5% = 1.87
Our Calmar: 7.5% / 20.2% = 0.37
```

**Calmar 0.37은 S&P 대비 5분의 1 수준이다.** Iter 18 P2에서 Calmar 1.097로 S&P를 이겼던 성과가 완전히 상실되었다.

**진단 2: 왜 GDR이 20% DD를 방지하지 못했는가**

현재 GDR 설정:
```
BM: Tier 1 at 4%, Tier 2 (HALT) at 8%
MR: Tier 1 at 2%, Tier 2 (HALT) at 4%
Safety Net: activation at 12%, recovery at 8%
```

20% DD가 발생했다는 것은 Safety Net이 12%에서 활성화되었음에도 추가 8%의 DD가 누적되었다는 뜻이다. Safety Net 활성화 후에도 1 entry/day, 0.5% risk로 계속 거래하기 때문이다.

더 심각한 문제: **Safety Net이 활성화된 후에도 기존 open positions의 SL은 여전히 전체 크기다.** 3개 포지션이 열려있는 상태에서 Safety Net이 12%에서 활성화되면, 신규 진입은 제한하지만 기존 포지션 3개의 잠재 손실은 3 * 2.5% = 7.5%가 남아있다. 12% + 7.5% = 19.5% -- 거의 20%에 도달한다.

**이것이 정확한 20% DD 메커니즘이다.**

**진단 3: 포지션 상관관계(Correlation) 리스크**

BM cap 2, MR cap 3, MAX_LONG 8로 설정했지만, 같은 날 여러 BM 시그널이 발생하면 유사한 sector/factor exposure를 가진 주식들을 동시에 매수하게 된다. S&P 500에서 breakout하는 주식들은 같은 시장 모멘텀에 의해 구동되므로, 포지션 간 상관관계가 높다.

다수 상관 포지션이 동시에 반전하면, 이론적 개별 리스크 합계보다 훨씬 큰 DD가 발생한다.

**진단 4: Heat Cap과 Position Cap의 상호작용**

```
Heat 35%, MAX_LONG 8, 평균 position size ~$12K:
- 이론적 max deployment: $35K (heat cap binding)
- 실질적 max positions: $35K / $12K = ~3개 (heat cap이 position cap보다 먼저 binding)
- But if positions appreciate after entry, they can exceed initial heat cap
- 3개 포지션 * $12K = $36K -> already 36% heat
- 시장이 올라 position value 증가 -> heat 40%+ 가능
```

**Heat cap은 '진입 시점 기준'이지 '현재 시점 기준'이 아닐 수 있다.** 이 경우 실질 exposure가 heat cap을 초과할 수 있다.

**리스크 매니저 처방 (우선순위순):**

1. **_MAX_PORTFOLIO_HEAT_PCT: 0.35 -> 0.28** (25%와 35%의 중간보다 약간 아래)
2. **_PORTFOLIO_SAFETY_NET_DD: 0.12 -> 0.08** (더 일찍 안전망 활성화)
3. **_PORTFOLIO_SAFETY_NET_RECOVERY: 0.08 -> 0.05** (더 보수적 회복 기준)
4. **BM GDR Tier 1: 0.04 -> 0.03, Tier 2: 0.08 -> 0.05** (BM 드로다운 반응 가속)
5. **MR GDR Tier 1: 0.02 -> 0.015, Tier 2: 0.04 -> 0.03** (MR도 동일)
6. **MAX_LONG: 8 -> 6** (동시 포지션 상관 리스크 축소)
7. **MAX_TOTAL: 9 -> 7** (동일)"

### Strat-4 (Market Analyst) -- 레짐별 성과 분석과 자본 효율 최적화

"Iter 23의 결과를 레짐과 시장 구조 관점에서 분석하겠다.

**분석 1: P1 vs P2 성과의 수렴**

| Metric | P1 | P2 | 차이 |
|--------|-----|-----|------|
| Return | +7.5% | +7.9% | 0.4%p |
| MaxDD | 20.2% | 21.0% | 0.8%p |
| Sharpe | 0.384 | 0.395 | 0.011 |
| Calmar | 0.375 | 0.378 | 0.003 |

**P1과 P2의 결과가 거의 동일하다.** 이것은 이전 이터레이션(Iter 16-22)에서 항상 큰 차이를 보이던 것과 대조적이다.

왜 수렴했는가?

P1(bull): BM이 주도 ($7,105, 95.7%), MR 미미 ($319)
P2(mixed): MR이 주도 ($4,718, 59.9%), BM 보조 ($3,156)

두 전략이 각각 자신에게 유리한 시장에서 비슷한 총 기여를 하고 있다. 이것은 **레짐 배치 전략이 제대로 작동하고 있다는 증거다.** Iter 22에서 도입한 레짐 기반 BM/MR 차등 배치가 효과를 발휘하고 있다.

**분석 2: MR P2의 압도적 품질**

MR P2: 12 trades, PF 2.858, $4,718

이것은 전 이터레이션 통틀어 최고의 단일 strategy-period 성과다. 왜 이런 결과가 나왔나?

- MR cap 3으로 더 많은 MR 포지션 허용
- RANGING MR alloc 0.040으로 더 큰 포지션 사이즈
- P2의 RANGING 기간이 길어 mean-reversion이 완성될 시간 충분
- SL exit rate 41.7%로 낮음 = 대부분 indicator-based TP에 도달

그러나 **12건은 여전히 적다.** MR의 ADX_MAX = 20.0 필터가 매우 엄격하여, P2의 RANGING 기간에서도 ADX가 20을 약간 넘는 날이 많아 시그널을 놓친다.

**ADX_MAX를 23.0으로 완화하면 MR 거래 수가 15-18건으로 증가할 수 있다.** 그러나 이것은 양날의 검이다:
- P2: 추가 3-6건이 PF ~2.0을 유지한다면 +$1,200-2,400 추가 수익
- P1: ADX 20-23 구간의 MR은 trend 전환 리스크가 높아 품질 저하 가능

**분석 3: MR P1 -- 문제는 빈도가 아니라 환경**

MR P1: 13 trades, PF 1.078, $319

MR cap을 2->3으로 올렸음에도 P1 MR 거래가 13건에 그쳤고, 그나마 있는 거래의 품질도 낮다. 이것은:

1. P1(bull market)에서 ADX < 20인 기간이 15-20%에 불과
2. 그 기간에서 RSI < 30이 되는 깊은 조정이 드묾
3. 설령 진입해도, 곧 ADX가 올라가면서 반대 방향으로 이동

**P1에서 MR의 PF 1.078은 거래 비용 고려 시 사실상 zero-edge다.**

MR P1의 13건 중 profitable SL exits를 제외하면 실질 엣지가 있는 거래는 3-4건에 불과할 것으로 추정한다.

**제안: P1(TREND_UP 레짐)에서 MR alloc을 0.012 -> 0.008로 소폭 축소하여, MR의 약한 P1 거래를 2-3건 줄인다. 이로써 MR P1의 PF가 1.2+로 개선될 수 있다.**

**분석 4: 자본 배치 최적화의 Sweet Spot**

| Heat Cap | Est. Return | Est. MaxDD | Est. Calmar | 판정 |
|----------|-------------|-----------|-------------|------|
| 25% (Iter 22) | +3% avg | ~5-7% | ~0.5 | 보수적 |
| 28% | +5% avg | ~10-12% | ~0.45 | 균형점 |
| 30% | +6% avg | ~13-15% | ~0.42 | 공격적 |
| 35% (Iter 23) | +7.7% avg | ~20% | ~0.38 | 과도 |

**Heat 28%가 return/risk 균형에서 최적이다.** Heat 30%도 수용 가능하지만, MaxDD 15% 목표를 고려하면 28%가 더 안전하다.

**분석 5: BM의 Trailing Distance 문제**

현재 BM trailing: activation 1.5 ATR, distance 2.0 ATR

포지션이 1.5 ATR 수익에 도달한 후 trailing이 시작된다. 그러나 trail distance가 2.0 ATR이므로:
- 최고점에서 2.0 ATR 하락 시 exit
- 최고점이 entry + 1.5 ATR이면, exit price = entry - 0.5 ATR (손실!)

이것은 설계 결함이다. **Trailing distance는 trailing activation보다 작거나 같아야 trailing exit가 최소 breakeven 이상을 보장한다.**

수정: trailing distance 2.0 -> 1.5 ATR. 이렇게 하면 최고점이 activation 수준(entry + 1.5 ATR)일 때 exit price = entry + 0.0 ATR (breakeven). 최고점이 더 높으면 그만큼 이익이 보존된다."

---

## 3. Cross-Diagnosis Consensus

### Unanimous Agreement (4/4)

#### Consensus 1: Heat 35%는 과도했다 -- MaxDD 20%는 배치 불가

**전원 동의. 반대 없음.**

Heat을 25%->35%로 올린 Panel #27 결정이 수익을 2배로 만들었지만 DD를 4-6배로 악화시켰다. Return/Risk ratio가 S&P 대비 1/5 수준으로 추락한 것은 리스크 조정 성과의 완전한 파괴다.

Iter 18 P2에서 달성했던 Sharpe 0.919 > S&P 0.877의 리스크 조정 우위가 Sharpe 0.395로 하락했다.

#### Consensus 2: 2-Stage SL Upgrade는 효과적이나 Trailing이 부실하다

**전원 동의.**

Breakeven SL과 Profit-lock SL이 높은 WR(70-80%)에 기여하고 있다. 그러나 trailing stop의 설계(activation 1.5 ATR + distance 2.0 ATR)는 수학적으로 결함이 있다. Distance를 1.5 ATR 이하로 축소해야 한다.

#### Consensus 3: MR P1은 자연적 한계이며 강제로 개선하면 안 된다

**전원 동의.**

MR P1의 낮은 성과는 P1(bull market)의 시장 구조에서 비롯된다. ADX_MAX를 완화하거나 MR cap을 늘려도 P1에서 MR의 엣지가 개선되지 않는다. P1에서 MR은 '수익 보험'이 아니라 '최소 해적' 역할만 하면 된다. MR의 P1 allocation을 소폭 축소하는 것이 합리적이다.

### Debate Points

#### Debate 1: Heat Cap 최적값

- **Strat-3**: 28%. 안전 마진을 충분히 확보해야 한다. 30%는 MaxDD 15%를 보장하지 못한다.
- **Strat-2**: 30%. 28%는 수익이 너무 감소한다. Iter 22(heat 25%)에서 combined +2.9%에 불과했다. 28%는 +4-5%에 그칠 것이다.
- **Strat-1**: 30%. 단, GDR과 Safety Net을 동시에 강화하면 28%에서도 충분한 수익이 나올 수 있다.
- **Strat-4**: 28%. 수학적으로 28%가 Calmar 최적화 지점이다.
- **결정**: **Heat 28%를 기본으로 채택.** GDR 강화와 함께 적용하면 MaxDD < 15% 목표를 달성할 수 있다.

#### Debate 2: MAX_LONG Position Cap

- **Strat-3**: 6으로 축소. 8은 상관 리스크가 너무 크다.
- **Strat-2**: 8 유지. Heat 28%에서 실제 동시 포지션은 2-3개로 제한되므로, MAX_LONG 8은 binding constraint가 아니다. 줄여도 효과 없고, 드물게 좋은 기회가 많을 때 제약이 된다.
- **Strat-4**: 7로 중간 타협. 극단적 상황에서의 안전망 역할.
- **결정**: **MAX_LONG 7, MAX_TOTAL 8**. Heat 28%에서 실질적으로는 3-4개가 한계이므로, 7은 안전망이면서도 과도한 제약이 아님.

#### Debate 3: MR ADX_MAX 완화 여부

- **Strat-4**: 23.0으로 완화 제안. MR P2 거래 수 12 -> 15-18건 증가 기대.
- **Strat-2**: 위험하다. ADX 20-23 구간은 trend 전환 리스크가 높다. MR P2의 PF 2.858 품질을 유지하는 것이 더 중요하다.
- **Strat-1**: 동의. 현재 ADX 20이 MR의 품질 필터다. 완화하면 P2 PF가 2.8 -> 2.0으로 하락할 수 있고, 총 PnL 증가가 미미할 것이다.
- **Strat-3**: ADX 유지. 리스크 대비 기대 수익이 불확실하다.
- **결정**: **ADX_MAX 20.0 유지. MR 엣지의 품질을 보존한다.**

---

## 4. Root Cause Analysis

### Root Cause 1: Heat Cap 과잉 상향 (PRIMARY)

**현상**: MaxDD 20%+ in both periods
**근본 원인**: Heat 25% -> 35%로 10%p 상향이 DD를 비선형적으로 증가시킴. 포지션 간 상관관계가 높아 개별 포지션 리스크의 단순 합계보다 실제 DD가 훨씬 큼.
**영향**: Calmar 0.37 (S&P의 1/5), Sharpe 0.39 (S&P의 1/3). 리스크 조정 성과 완전 파괴.
**해법**: Heat 28%로 축소 + GDR/Safety Net 강화

### Root Cause 2: Trailing Stop 설계 결함 (SECONDARY)

**현상**: BM trailing distance (2.0 ATR) > trailing activation (1.5 ATR). 수학적으로 trailing exit가 entry 이하에서 발생 가능.
**근본 원인**: Panel #27에서 trailing activation만 올리고(1.0 -> 1.5) distance를 조정하지 않음
**영향**: Trailing stop이 실질적으로 '확대된 SL'로 작동. 수익 보호 효과 미미.
**해법**: Trailing distance 2.0 -> 1.5 ATR로 축소

### Root Cause 3: GDR Safety Net 지연 (TERTIARY)

**현상**: Safety Net이 12% DD에서 활성화되지만 기존 포지션의 잠재 손실이 추가 8%를 야기
**근본 원인**: Safety Net이 신규 진입만 제한하고, 기존 포지션은 관리하지 않음
**영향**: Safety Net 활성화 후에도 DD가 20%까지 확대
**해법**: Safety Net activation 8%로 조기 발동 + Recovery 5%로 보수적 복귀

### Root Cause 4: Win/Loss 비대칭 (STRUCTURAL)

**현상**: Avg Loss > Avg Win in both periods (P1: 0.67, P2: 0.48)
**근본 원인**: Full-stop losses가 크고(-$919), profit-lock exits가 작음(+$50-200). TP/trailing도달률이 낮아 대형 승리 거래가 부족.
**영향**: 높은 WR에도 불구하고 risk/reward가 비효율적
**해법**: Stage 1 BE activation 조기화(1.5 -> 1.0 ATR) + Stage 2 profit lock 확대(0.4 -> 0.5 ATR) + Trailing distance 축소(2.0 -> 1.5 ATR)

---

## 5. Specific Parameter Changes for Iteration 24

### Priority 0 (EMERGENCY): Drawdown Reduction

| # | Parameter | File | Current | Proposed | Rationale |
|---|-----------|------|---------|----------|-----------|
| 1 | `_MAX_PORTFOLIO_HEAT_PCT` | batch_simulator.py:76 | 0.35 | **0.28** | Heat 28%: DD/Return 균형점. 선형 추정 MaxDD ~10-12% |
| 2 | `_MAX_LONG_POSITIONS` | batch_simulator.py:72 | 8 | **7** | 동시 포지션 상관 리스크 축소 |
| 3 | `_MAX_TOTAL_POSITIONS` | batch_simulator.py:74 | 9 | **8** | 동일 |
| 4 | `_PORTFOLIO_SAFETY_NET_DD` | batch_simulator.py:111 | 0.12 | **0.08** | Safety Net 4%p 조기 발동 |
| 5 | `_PORTFOLIO_SAFETY_NET_RECOVERY` | batch_simulator.py:112 | 0.08 | **0.05** | 더 보수적 복귀 기준 |

**Expected Impact**: MaxDD 20% -> 12-15%, Calmar 0.37 -> 0.5-0.7

### Priority 1 (CRITICAL): Exit Rule Optimization

| # | Parameter | File | Current | Proposed | Rationale |
|---|-----------|------|---------|----------|-----------|
| 6 | `_STAGE1_BE_ACTIVATION_ATR` | exit_rules.py:32 | 1.5 | **1.0** | 더 빠른 breakeven 이동 -> 손실 거래 수 감소 |
| 7 | `_STAGE2_PROFIT_LOCK_ATR` | exit_rules.py:34 | 0.4 | **0.5** | Stage 2 도달 시 더 많은 이익 보전 |
| 8 | `_TRAILING_ATR_MULT` | exit_rules.py:64 | 2.0 | **1.5** | Trailing distance < activation -> 수학적 결함 수정 |

**Expected Impact**: Avg Win/Loss ratio 0.67 -> 0.85+, BM SL exit rate 73% -> 60%, TP/trailing exit rate 증가

### Priority 2 (HIGH): Regime Allocation Fine-Tuning

| # | Parameter | File | Current | Proposed | Rationale |
|---|-----------|------|---------|----------|-----------|
| 9 | TREND_UP MR alloc | regime_classifier.py:25 | 0.012 | **0.008** | MR P1 약한 거래 축소 (PF 1.078 -> 1.2+ 기대) |

**Expected Impact**: MR P1 trades 13 -> 10-11, MR P1 PF 1.078 -> 1.2-1.4 (약한 거래 3건 제거)

### Priority 3 (MEDIUM): GDR Tightening

| # | Parameter | File | Current | Proposed | Rationale |
|---|-----------|------|---------|----------|-----------|
| 10 | BM GDR Tier 1 | batch_simulator.py:90 | 0.04 | **0.03** | BM DD 반응 가속 |
| 11 | BM GDR Tier 2 | batch_simulator.py:90 | 0.08 | **0.06** | BM HALT 기준 강화 |
| 12 | MR GDR Tier 1 | batch_simulator.py:91 | 0.02 | **0.015** | MR DD 반응 가속 |
| 13 | MR GDR Tier 2 | batch_simulator.py:91 | 0.04 | **0.03** | MR HALT 기준 강화 |

**Expected Impact**: 개별 전략 DD 제한 강화, 전체 DD 감소에 기여

### DO NOT CHANGE (Locked Parameters)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | 7-iter confirmed |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| MR soft cap | batch_simulator.py | 3 | Panel #27 decision, P2 PF 2.858 validates |
| MR ADX_MAX | rsi_mean_reversion.py | 20.0 | Quality filter, debate resolved |
| BM trailing activation | exit_rules.py | 1.5 | Panel #27 decision, working as intended |
| BM TP ATR mult | exit_rules.py | 4.0 | Panel #27 decision |
| All regime allocs except TREND_UP MR | regime_classifier.py | various | Panel #27 validated |

---

## 6. Risk Assessment of Proposed Changes

### Change Risk Matrix

| Change | Upside Potential | Downside Risk | Confidence |
|--------|-----------------|---------------|-----------|
| Heat 0.35 -> 0.28 | MaxDD 20% -> 12% | Return -20% (P1 +6%, P2 +6.3%) | **HIGH** |
| Safety Net 0.12 -> 0.08 | 극단 DD 방지 | 과도한 거래 제한 (recoverable) | **HIGH** |
| Stage 1 BE 1.5 -> 1.0 | 손실 거래 감소 | 정상 pullback에서 조기 exit | **MEDIUM** |
| Trailing dist 2.0 -> 1.5 | 수학적 결함 수정 | 추세 중 조기 exit 가능 | **HIGH** |
| TREND_UP MR 0.012 -> 0.008 | MR P1 PF 개선 | MR P1 PnL 소폭 감소 | **MEDIUM** |
| GDR thresholds tighter | 전략별 DD 축소 | 거래 기회 감소 | **MEDIUM** |
| MAX_LONG 8 -> 7 | 상관 리스크 축소 | 거의 영향 없음 (heat가 binding) | **HIGH** |

### Expected Iter 24 Performance Range

| Metric | P1 Lower | P1 Target | P1 Upper | P2 Lower | P2 Target | P2 Upper |
|--------|----------|-----------|----------|----------|-----------|----------|
| Return | +4.5% | +6.0% | +7.0% | +5.0% | +6.5% | +8.0% |
| MaxDD | 10% | 12% | 15% | 10% | 13% | 15% |
| Sharpe | 0.4 | 0.55 | 0.7 | 0.4 | 0.55 | 0.7 |
| Calmar | 0.35 | 0.50 | 0.65 | 0.40 | 0.50 | 0.65 |
| BM Trades | 28 | 32 | 36 | 30 | 35 | 40 |
| MR Trades | 8 | 10 | 12 | 10 | 12 | 15 |
| Combined | +9.5% | +12.5% | +15.0% | - | - | - |

### Worst Case Scenario

Heat 28%에서 예상 최악:
```
- 모든 포지션 동시 full-stop: 3개 * 2.5% = 7.5%
- GDR Tier 1 진입 후 추가 1-2 거래: +1.5%
- Safety Net 8%에서 활성화
- 기존 포지션 잠재 추가 손실: 5%
- 이론적 최악 MaxDD: ~13%
```

이것은 현재 20%보다 35% 개선이며, 목표 15% 이내다.

---

## 7. Quantitative Targets (Iteration 24)

| Metric | Iter 23 P1 | Target P1 | Iter 23 P2 | Target P2 |
|--------|-----------|----------|-----------|----------|
| Return | +7.5% | **+5.5-7.0%** | +7.9% | **+6.0-8.0%** |
| MaxDD | 20.2% | **< 15%** | 21.0% | **< 15%** |
| Sharpe | 0.384 | **> 0.5** | 0.395 | **> 0.5** |
| Calmar | 0.375 | **> 0.45** | 0.378 | **> 0.45** |
| BM PF | 1.806 | **> 1.5** | 1.618 | **> 1.5** |
| MR PF | 1.078 | **> 1.2** | 2.858 | **> 2.0** |
| Avg Win/Loss | 0.67 | **> 0.85** | 0.48 | **> 0.65** |
| SL Exit Rate | 70%+ | **< 60%** | 60%+ | **< 50%** |

**핵심 목표: Return을 약간 희생하더라도 MaxDD를 15% 이내로 억제하여 Calmar 0.45+를 달성한다.**

---

## 8. Lessons Learned

### Lesson 1: Heat Cap과 DD의 비선형 관계

Heat 25% -> 35%로 10%p 상승이 Return을 ~2배 늘렸지만 DD를 4-6배 악화시켰다. 이것은 포지션 간 상관관계로 인한 비선형 효과다. 향후 heat 조정은 5%p 이하의 점진적 변경만 허용한다.

### Lesson 2: Return 극대화와 Risk 관리는 다른 차원의 문제

Iter 23은 "return은 좋은데 risk가 나쁜" 전형적 사례다. +15.4% combined return은 우수하지만, 그 과정에서 20% DD를 감수하는 것은 실제 운용에서 불가능하다. Risk-adjusted metrics(Sharpe, Calmar)가 raw return보다 중요하다.

### Lesson 3: 2-Stage SL Upgrade의 가치 확인

73.5% SL exit rate에도 73.5% WR을 유지하는 것은 2-stage SL upgrade가 대량의 손실 거래를 breakeven/소액수익으로 전환하고 있음을 의미한다. 이 메커니즘은 검증되었으며 보존해야 한다.

### Lesson 4: MR P2의 구조적 엣지 재확인

MR P2: PF 2.858, 12 trades로 $4,718은 system 역사상 최고 단일 strategy-period 성과다. MR의 RANGING market 엣지는 파라미터에 둔감하고 시장 구조에서 비롯된 진정한 알파다.

### Lesson 5: Trailing Stop의 수학적 일관성 검증 필요

Trailing activation > trailing distance여야 trailing exit이 최소 breakeven을 보장한다. 이 기본적인 수학적 일관성이 Panel #27에서 간과되었다. 향후 모든 exit rule 변경은 수학적 일관성 검증을 필수로 거쳐야 한다.

---

## 9. Decision Summary

| # | Parameter | File | Old | New | Priority |
|---|-----------|------|-----|-----|---------|
| 1 | `_MAX_PORTFOLIO_HEAT_PCT` | batch_simulator.py | 0.35 | **0.28** | P0 |
| 2 | `_MAX_LONG_POSITIONS` | batch_simulator.py | 8 | **7** | P0 |
| 3 | `_MAX_TOTAL_POSITIONS` | batch_simulator.py | 9 | **8** | P0 |
| 4 | `_PORTFOLIO_SAFETY_NET_DD` | batch_simulator.py | 0.12 | **0.08** | P0 |
| 5 | `_PORTFOLIO_SAFETY_NET_RECOVERY` | batch_simulator.py | 0.08 | **0.05** | P0 |
| 6 | `_STAGE1_BE_ACTIVATION_ATR` | exit_rules.py | 1.5 | **1.0** | P1 |
| 7 | `_STAGE2_PROFIT_LOCK_ATR` | exit_rules.py | 0.4 | **0.5** | P1 |
| 8 | `_TRAILING_ATR_MULT` | exit_rules.py | 2.0 | **1.5** | P1 |
| 9 | TREND_UP MR alloc | regime_classifier.py | 0.012 | **0.008** | P2 |
| 10 | BM GDR thresholds | batch_simulator.py | (0.04, 0.08) | **(0.03, 0.06)** | P3 |
| 11 | MR GDR thresholds | batch_simulator.py | (0.02, 0.04) | **(0.015, 0.03)** | P3 |

**Total changes: 11 parameter modifications across 3 files**

---

## 10. Parameter Change Map (Iter 24)

### batch_simulator.py
```python
_MAX_LONG_POSITIONS:                        8 -> 7
_MAX_TOTAL_POSITIONS:                       9 -> 8
_MAX_PORTFOLIO_HEAT_PCT:                    0.35 -> 0.28
_PORTFOLIO_SAFETY_NET_DD:                   0.12 -> 0.08
_PORTFOLIO_SAFETY_NET_RECOVERY:             0.08 -> 0.05

_STRATEGY_GDR_THRESHOLDS["breakout_momentum"]:   (0.04, 0.08) -> (0.03, 0.06)
_STRATEGY_GDR_THRESHOLDS["rsi_mean_reversion"]:  (0.02, 0.04) -> (0.015, 0.03)
```

### exit_rules.py
```python
_STAGE1_BE_ACTIVATION_ATR:                  1.5 -> 1.0
_STAGE2_PROFIT_LOCK_ATR:                    0.4 -> 0.5
_TRAILING_ATR_MULT:                         2.0 -> 1.5
```

### regime_classifier.py
```python
TREND_UP:  MR alloc 0.012 -> 0.008
(All other allocations unchanged)
```

### NO CHANGES (LOCKED)
```
breakout_momentum.py:     ALL PARAMETERS LOCKED
rsi_mean_reversion.py:    ALL PARAMETERS LOCKED
strategy_params.yaml:     NO CHANGES
```

---

## 11. Next Steps

1. **Iter 24**: Apply 11 parameter changes, run P1+P2 backtest
2. **Validation**: Confirm MaxDD < 15% in both periods
3. **If successful**: Proceed to 3rd strategy paper analysis
4. **If MaxDD still > 15%**: Further reduce heat to 25% and reassess

---

## Appendix: Complete Iteration History (12-23)

| Iter | P1 Return | P2 Return | Combined | MaxDD (est.) | Key Change |
|------|-----------|-----------|----------|-------------|-----------|
| 12 | +2.9% | +5.4% | +8.3% | ~10% | 2-strat debut |
| 13 | -3.9% | +5.1% | +1.2% | ~8% | MR param tune |
| 14 | -5.4% | -2.0% | -7.4% | ~12% | BM-only |
| 15 | - | - | - | - | Structural fix |
| 16 | -3.7% | +2.3% | -1.4% | ~6% | MR restored |
| 17 | -6.7% | +2.2% | -4.5% | ~8% | BM cap1, SL 2.0 |
| 18 | -6.2% | +5.2% | -1.0% | ~5% | Regime relaxed |
| 19 | +7.4% | +2.6% | +10.0% | ~4% | ADX28, LB15, high |
| 20 | -9.0% | -1.4% | -10.4% | ~10% | BM cap1 |
| 21 | -3.2% | -3.5% | -6.7% | ~5% | ADX25, LB10 |
| 22 | -0.6% | +3.5% | +2.9% | ~6% | Regime alloc |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20%** | MR cap3, heat 35% |

**Iter 23 is our best return but worst risk-adjusted performance. Iter 24 must correct the risk/return balance.**
