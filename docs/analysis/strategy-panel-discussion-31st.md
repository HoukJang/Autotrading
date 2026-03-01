# Strategy Panel Discussion #31: Capital Deployment Bottleneck -- How to Beat S&P 500

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iter 23/26 baseline confirmed. System generates 30% ROIC but deploys only 26% of capital. Combined +15.4% vs S&P +31.4%. This discussion focuses exclusively on structural changes to close the gap.
**Prerequisite**: Panel #30 confirmed Iter 23 reproducibility. Parameter tuning era is over. All future improvements must be structural.

---

## 1. The Capital Deployment Problem -- Quantified

### Current Performance Summary (Iter 23/26 Baseline)

| Metric | P1 (Bull) | P2 (Mixed) | Combined |
|--------|-----------|------------|----------|
| Return | +7.5% | +7.9% | +15.4% |
| MaxDD | 20.2% | 21.0% | - |
| ROIC (deployed) | +26.3% | +33.0% | ~30% |
| S&P Return | +15.9% | +15.5% | +31.4% |
| Gap to S&P | -8.4%p | -7.6%p | -16.0%p |

### Capital Deployment Diagnostics

| Metric | Our System | S&P (Buy & Hold) | Gap |
|--------|-----------|-------------------|-----|
| Average capital deployed | **26.4%** | **100%** | -73.6%p |
| Average simultaneous positions | 1.5 | N/A (always 100%) | - |
| Peak simultaneous positions | 3 | N/A | - |
| Days with 0 positions | 130/522 (25%) | 0/522 (0%) | -25%p |
| Warmup period (zero trades) | 88 days (17%) | 0 days | -17%p |
| Active period deployment | ~35% | 100% | -65%p |
| Idle cash earning 0% | 73.6% avg | 0% | +73.6%p |

### The Fundamental Equation

```
System Return = Capital Deployed * ROIC

Current:  26.4% * 30% ROIC = 7.9% annual (combined ~15.4% over 2yr)
S&P:     100.0% * 15.7% ROIC = 15.7% annual (combined ~31.4% over 2yr)

To match S&P: Need deployed * ROIC >= 15.7%
Option A: Keep 30% ROIC -> need 52.3% deployment (currently 26.4%)
Option B: Keep 26% deploy -> need 60.4% ROIC (currently 30%, impossible to double)
Option C: Combination -> 40% deploy * 40% ROIC, or 45% * 35%, etc.
```

**Conclusion: The only realistic path to beating S&P is increasing deployment, not ROIC.**

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- The ADX Dead Zone and Trade Frequency

"이 시스템의 근본 문제를 트레이딩 관점에서 진단하겠다.

**진단 1: ADX Dead Zone이 전체 거래일의 40-50%를 낭비한다**

현재 2개 전략의 진입 조건을 정리하면:

```
BM (Breakout Momentum):
- ADX > 28 (강한 추세)
- Price > highest high of 15 bars (신고가)
- RSI 50-80, Volume > 1.2x average
- 결론: ADX가 28 미만이면 절대 진입 불가

MR (RSI Mean Reversion):
- ADX < 20 (비추세)
- RSI < 30 또는 RSI > 75 (극단적 과매도/과매수)
- 결론: ADX가 20 이상이면 절대 진입 불가

Dead Zone: ADX 20-28
- BM도 MR도 진입할 수 없는 영역
- SPY 기준으로 전체 거래일의 약 35-45%가 이 영역에 해당
- 개별 종목 기준으로도 유사한 비율
```

이것이 130일간 포지션 제로인 주요 원인이다. ADX가 20-28 사이에 머물면 시스템은 아무것도 하지 않는다.

**진단 2: BM의 '신고가' 조건이 진입 기회를 과도하게 제한한다**

BM은 15일 최고가 돌파를 요구한다. 이것은 강한 모멘텀 확인이지만, 추세 내 pullback-and-resume 패턴을 완전히 놓친다. 예를 들어:

```
전형적 상승 추세에서의 패턴:
Day 1-10: 주가 $100 -> $115 (신고가, BM 진입 가능)
Day 11-15: $115 -> $108 (정상 pullback, ADX 여전히 높음)
Day 16-20: $108 -> $113 (pullback 후 반등, 추세 지속 확인)

이 Day 16-20 구간에서:
- BM: 진입 불가 (아직 $115 신고가 미달)
- MR: 진입 불가 (ADX > 20)
- 결과: 가장 좋은 risk/reward 구간에서 시스템이 idle
```

pullback-to-EMA 매수는 스윙 트레이딩에서 가장 기본적이고 높은 승률의 패턴이다. 우리 시스템에 이것이 없다.

**진단 3: MR의 극단적 진입 조건이 거래 빈도를 연 12-16건으로 제한**

MR은 RSI < 30과 BB %B < 0.05를 동시에 요구한다. 이 두 조건의 동시 충족은 매우 드물다:

```
RSI < 30: 연간 ~5-8% of bars
BB %B < 0.05: 연간 ~3-5% of bars
동시 충족: 연간 ~1-3% of bars per stock
S&P 500 universe에서 연간: ~15-30건 signal (필터링 후 12-16 진입)
```

MR의 조건을 완화하는 것은 edge 감소 위험이 있어 권장하지 않는다. 그러나 MR과 다른 조건에서 mean-reversion을 잡을 수 있는 별도 전략이 필요하다.

**Strat-1의 3번째 전략 제안: Trend Pullback Strategy**

```
전략명: trend_pullback
컨셉: 확인된 상승추세 내에서 EMA(21) 또는 EMA(50) 지지선까지 pullback 후 반등 매수

진입 조건 (Long only):
- EMA(21) slope > 0 (최근 5일간 상승)
- Price > EMA(50) (중기 상승추세 확인)
- ADX > 15 AND ADX < 35 (추세 존재하나 BM이 커버하는 극단 영역 회피)
- Close <= EMA(21) * 1.01 (EMA 근접 또는 터치)
- Close > EMA(21) * 0.97 (EMA 아래 3% 이상 이탈은 추세 이탈 의심)
- RSI > 35 AND RSI < 55 (과매도 아닌 적당한 pullback)
- Bar가 양봉 또는 하방 꼬리 > body의 1.5배 (반등 징후)

Exit 조건:
- SL: Entry - 1.5 ATR (BM의 2.5보다 타이트 -- pullback은 빨리 work해야)
- TP: Entry + 3.0 ATR
- Time exit: 7일
- Trend loss: Close < EMA(50) for 2 consecutive bars

기대 성과:
- 거래 빈도: 25-40건/년 (BM의 34-40건과 유사, MR보다 2-3배)
- Win rate: 55-65% (BM보다 낮지만 tighter SL로 RR 보상)
- ADX 커버 범위: 15-35 (BM의 28+ 및 MR의 <20과 부분 겹침 있으나 핵심 dead zone 15-28 커버)
```

이 전략이 ADX 20-28 dead zone을 정면으로 공략한다."

### Strat-2 (Quant Analyst) -- 배치 최적화의 수학과 각 레버의 정량적 분석

"각 레버의 기대 효과를 정량적으로 분석하겠다. 감에 의존하지 않고 데이터와 수학으로 판단한다.

**분석 1: 각 레버별 Capital Deployment 증가 추정**

| # | Lever | 현재 Deploy | 추가 Deploy | 새 Deploy | Annual Return 추정 | 구현 난이도 | Risk |
|---|-------|-------------|-------------|-----------|-------------------|------------|------|
| 1 | Warmup 88d -> 10d | 26.4% | +4.8% | 31.2% | +1.4% | LOW | LOW |
| 2 | 3rd Strategy (Trend Pullback) | 26.4% | +8-14% | 34-40% | +2.4-4.2% | MEDIUM | MEDIUM |
| 3 | Idle Cash Money Market (5%) | 26.4% | - (수익만) | 26.4% | +3.5% | TRIVIAL | ZERO |
| 4 | MR Cap 3 -> 4 | 26.4% | +1-2% | 27-28% | +0.3-0.6% | TRIVIAL | LOW |
| 5 | Risk 2% -> 3% | 26.4% | - (사이즈만) | 26.4% | +3.7% (return), +10%p MaxDD | TRIVIAL | HIGH |
| 6 | Core+Satellite 50/50 | 26.4%->63% | +37% | 63% | +5.5% (core) +2.5% (satellite) | MEDIUM | MEDIUM |
| 7 | BM Cap 2 -> 3 | 26.4% | +2-4% | 28-30% | +0.6-1.2% | TRIVIAL | MEDIUM |
| 8 | Universe Expansion | 26.4% | +3-5% | 29-31% | +0.9-1.5% | HIGH | MEDIUM |

**분석 2: Warmup 88일의 분해**

```
Indicator warmup 요구량:
- EMA(50): 50 bars (regime classifier)
- EMA(21): 21 bars (BM entry)
- BB(20): 20 bars (MR entry)
- ADX(14): ~28 bars (ADX는 DI 14 + ADX smoothing 14)
- RSI(14): 14 bars
- Highest High(15): 15 bars
- ATR(14): 14 bars

최소 필요: max(50, 28, 21, 20, 15, 14) = 50 bars

현재 _MIN_BARS_WARMUP = 60 (코드 상)
실제 첫 거래까지: 88 days (관측값)

차이 분석: 88 - 60 = 28일 추가 지연
원인 추정:
- 첫 60일: indicator 계산 불가 (warmup)
- Day 61-88: 모든 indicator 계산 가능하나, 진입 조건 미충족 (ADX < 28 또는 RSI > 30 등)
- 또는: regime classifier의 EMA(50)가 안정화되는 데 추가 시간 필요

해법:
- Test period 시작 전에 60일의 historical data를 pre-load
- 이렇게 하면 Day 1부터 유효한 indicator 값 보유
- 첫 거래는 '조건 충족 시' 즉시 발생 (Day 1-10 가능)
- 기대 효과: 78 trading days 회복 = 전체 522일 대비 15%
```

pre-load 방식은 실제 라이브 트레이딩에서도 이미 historical warmup이 있으므로 백테스트만 정확히 맞추면 된다. 구현은 batch_simulator.py에서 data loading 시 추가 60일 데이터를 앞에 붙이고, test period 시작일 전 데이터는 indicator 계산에만 사용하되 trade execution은 하지 않도록 처리한다.

**분석 3: 3번째 전략 추가의 수학적 시뮬레이션**

Strat-1이 제안한 Trend Pullback의 기대 효과를 보수적으로 추정한다:

```
가정 (보수적):
- 연간 30건 거래 (BM 37건의 ~80%)
- Win rate: 58% (BM 78%보다 낮음, 보수적)
- Avg Win: $300 (BM $490보다 작음, SL 타이트)
- Avg Loss: $250 (BM $753보다 작음, SL 타이트)
- Average position duration: 5일

PnL 추정:
- 30 * 0.58 * $300 = $5,220 (승리)
- 30 * 0.42 * $250 = $3,150 (패배)
- Net PnL: +$2,070/년 = +2.07% on $100K equity

자본 배치 추정:
- 30 trades * 5 days * $15K avg position = $2.25M position-days
- 252 trading days * $100K equity = $25.2M equity-days
- Deployment addition: $2.25M / $25.2M = 8.9%

BM/MR과의 겹침 조정:
- ADX 15-28 구간: BM과 겹치지 않음 (BM은 ADX > 28)
- ADX 20-28 구간: MR과 겹치지 않음 (MR은 ADX < 20)
- ADX 28-35 구간: BM과 일부 겹침 (BM이 이미 진입 중일 수 있음)
- 실제 겹침 추정: 30건 중 5-8건이 BM과 동일 종목에 동시 포지션 가능
- 겹침 제외 순수 추가 배치: ~7% deployment

최종 추정:
- 추가 배치: +7-10% absolute
- 추가 수익: +1.5-2.5% on equity annually
- 새 총 배치: 33-36%
```

**분석 4: 레버 조합의 시너지 효과**

각 레버를 독립적으로 적용하는 것보다, 조합 시 시너지가 있다:

```
Phase 1 조합 (Warmup + Money Market + MR cap):
- Deployment: 26.4% + 5% (warmup) + 1% (MR cap) = 32.4%
- Return: 32.4% * 30% = 9.72% annual
- + Money market: 67.6% * 5% = 3.38%
- Total: 13.10% annual (현재 7.7% 대비 +5.4%p)
- 2년 combined: ~26.2% (vs 현재 15.4%)
- 구현: 1-2일

Phase 2 조합 (Phase 1 + 3rd Strategy):
- Deployment: 32.4% + 8% = 40.4%
- Return: 40.4% * 28% (3rd strategy ROIC가 낮아 blended 28%) = 11.3% annual
- + Money market: 59.6% * 5% = 2.98%
- Total: 14.28% annual
- 2년 combined: ~28.6% (S&P 31.4%에 근접!)
- 구현: 2-3주

Phase 3 조합 (Phase 2 + BM cap 3):
- Deployment: 40.4% + 3% = 43.4%
- Return: 43.4% * 28% = 12.15%
- + Money market: 56.6% * 5% = 2.83%
- Total: 14.98% annual
- 2년 combined: ~30.0% (S&P 31.4%와 1.4%p 차이!)
```

**결론: Phase 1 + Phase 2 + Phase 3를 순차 적용하면 S&P와 거의 동등한 수익에 도달할 수 있다. 핵심은 ROIC를 유지하면서 deployment를 43%까지 올리는 것이다.**"

### Strat-3 (Risk Manager) -- 배치 확대의 리스크와 방어 체계

"배치를 26% -> 43%로 65% 증가시키자는 제안에 대해, 리스크 관리 관점에서 철저히 검토하겠다.

**분석 1: 배치 증가에 비례하는 MaxDD 위험**

```
현재: 26.4% deployment -> 20% MaxDD
선형 외삽: 43.4% deployment -> 20% * (43.4/26.4) = 32.9% MaxDD

이것은 받아들일 수 없다.
```

그러나 이 선형 외삽은 틀렸다. 왜냐하면:

```
MaxDD는 다음 요인에 의해 결정된다:
1. 동시 포지션 수 (correlation risk)
2. 개별 포지션 손실 크기 (per-trade risk)
3. 연속 손실 확률 (strategy WR)
4. 전략 간 상관관계 (diversification effect)

배치 증가가 MaxDD에 미치는 영향은 어떤 방식으로 배치를 늘리느냐에 달려있다:
- A) 같은 전략의 position size를 키우면: MaxDD 비례 증가 (위험)
- B) 서로 다른 전략을 추가하면: sqrt(N) 효과로 MaxDD 완화 (안전)
- C) 전략 수는 같고 position 수를 늘리면: 동시 SL 위험 증가 (중간)
```

우리의 제안은 주로 (B) 새 전략 추가와 (C) 약간의 cap 증가이다. (A) position size 증가(risk 3%)는 제외했다.

**분석 2: 3rd Strategy 추가의 분산 효과**

```
현재 2전략 상관관계:
- BM: TREND_UP에서 활성 (ADX > 28)
- MR: RANGING에서 활성 (ADX < 20)
- 상관관계: 매우 낮음 (거의 동시에 활성화되지 않음)

3rd Strategy (Trend Pullback) 상관관계:
- TP: ADX 15-35에서 활성
- BM과: 부분 겹침 (ADX 28-35) -> 중간 상관관계
- MR과: 부분 겹침 (ADX 15-20) -> 낮은 상관관계

동시 포지션 시나리오:
- BM 2건 + TP 2건 = 4건 동시 (ADX 28-35 구간에서 가능)
- 4건 모두 SL: 4 * 2% risk = 8% equity loss (최악)
- TP의 SL이 1.5 ATR로 BM의 2.5 ATR보다 타이트:
  - BM 2건 SL: 2 * 2% * 2.5 = 5% 기여
  - TP 2건 SL: 2 * 2% * (1.5/2.5) = 2.4% 기여 (비례 축소)
  - 실질 동시 SL: ~7.4% (8%보다 낮음)

Safety Net 12%까지 도달하려면:
- 4건 동시 SL 후 추가 2-3건 연속 SL 필요
- 확률: (0.42)^2 * (0.22)^2 * (0.42)^2 = ~0.06% (매우 낮음)

결론: 3rd strategy 추가는 MaxDD를 2-3%p만 증가시킬 가능성이 높다.
```

**분석 3: MR Cap 3 -> 4의 리스크**

```
MR 4건 동시 포지션 시 최대 손실:
- MR SL: 1.5 ATR (long), 0.75 ATR (short) -- BM보다 타이트
- 4건 동시 long SL: 4 * 2% risk = 8% (이론적 최대)
- 실제: MR은 RANGING에서 활성, ranging 환경에서 mean-reversion은 높은 WR
- MR P2 WR 75%, 4건 동시 all-loss 확률: (0.25)^4 = 0.39%

MR cap 4의 MaxDD 영향: +1-2%p 추정 (수용 가능)

그러나 MR P1의 PF 1.08 (zero-edge)을 고려하면:
- P1에서 MR 4건 = 추가 리스크만 발생, 수익 기여 미미
- P2에서 MR 4건 = 추가 수익 기여 (PF 2.86)

해법: regime-conditional cap
- RANGING/HIGH_VOL: MR cap = 4
- TREND_UP/TREND_DOWN: MR cap = 2 (축소)
- UNCERTAIN: MR cap = 3 (현행 유지)
```

**분석 4: Risk Per Trade 2% -> 3% -- 강력 반대**

```
Risk 3% 시나리오:
- 현재 MaxDD 20% -> 추정 30% (50% 증가)
- Position size 50% 증가 -> 수익도 50% 증가
- Return: 15.4% * 1.5 = 23.1% (combined)
- MaxDD: ~30%
- Calmar: 23.1% / 30% = 0.77 (현재 15.4% / 20% = 0.77 -- 동일!)

Calmar이 개선되지 않으면 risk 증가의 의미가 없다.
더구나 30% MaxDD는 $1K-$5K 소액 계정에서 심리적으로 견디기 어렵다.
$5K 계정에서 30% DD = -$1,500. 남은 $3,500로 43% 상승해야 원금 회복.

VETO: Risk 3%는 어떤 시나리오에서도 시스템 개선이 아니다.
```

**분석 5: 새로운 리스크 파라미터 제안 (3rd Strategy 추가 시)**

```
trend_pullback 리스크 프로파일:
- Base risk: 1.5% per trade (BM 2.0%, MR 1.5%보다 보수적)
- SL: 1.5 ATR (타이트, 빠른 손절)
- Max position cap: 2 (보수적 시작)
- GDR thresholds: (0.03, 0.06) -- BM보다 타이트 (새 전략은 입증 전까지 보수적)

Portfolio-level 조정:
- _MAX_PORTFOLIO_HEAT_PCT: 0.35 -> 0.40 (3전략 수용을 위해 5%p 확대)
- _MAX_LONG_POSITIONS: 8 (유지, 3전략이 분산 사용)
- _MAX_TOTAL_POSITIONS: 9 (유지)
- _MAX_DAILY_ENTRIES: 3 -> 4 (3전략 수용)

Safety Net은 변경하지 않는다:
- _PORTFOLIO_SAFETY_NET_DD: 0.12 (유지)
- _PORTFOLIO_SAFETY_NET_RECOVERY: 0.08 (유지)
```

**Strat-3의 최종 입장: 배치 확대는 동의하되, 방어 체계를 유지하면서 진행한다. Risk Per Trade 증가는 VETO.**"

### Strat-4 (Market Analyst) -- 레짐별 빈 시간대 분석과 구조적 해법

"시스템이 idle한 기간을 레짐 관점에서 분석하겠다. 어떤 시장 환경에서 돈이 놀고 있는지 파악해야 한다.

**분석 1: 레짐별 거래 빈도와 idle 기간**

SPY 데이터(522일)에서 각 레짐의 출현 빈도를 추정한다:

```
P1 (Bull Market, ~260 days):
- TREND_UP: ~140일 (54%) -- BM 활성
- RANGING: ~45일 (17%) -- MR 활성
- UNCERTAIN: ~40일 (15%) -- 양쪽 모두 소극적
- HIGH_VOL: ~25일 (10%) -- MR 제한적
- TREND_DOWN: ~10일 (4%) -- BM 차단, MR 소극적

P2 (Mixed Market, ~262 days):
- RANGING: ~80일 (31%) -- MR 활성
- TREND_UP: ~70일 (27%) -- BM 활성
- UNCERTAIN: ~55일 (21%) -- 양쪽 모두 소극적
- HIGH_VOL: ~35일 (13%) -- MR 제한적
- TREND_DOWN: ~22일 (8%) -- BM 차단, MR 소극적

IDLE 레짐 합계 (UNCERTAIN + HIGH_VOL + TREND_DOWN 비활성 부분):
- P1: ~65일 (25%) -- 사실상 BM도 MR도 좋은 기회가 없는 기간
- P2: ~112일 (43%) -- Mixed market의 특성상 idle 비율 높음
- 전체: ~177일/522일 = 34%

ADX 20-28 (Dead Zone) 출현 추정:
- P1: ~55일 (21%)
- P2: ~75일 (29%)
- 전체: ~130일/522일 = 25%
```

**분석 2: Trend Pullback이 레짐별로 언제 활성화되는가**

```
Trend Pullback 활성화 조건: ADX 15-35, EMA(21) slope > 0, price near EMA(21)

레짐별 예상 활성화율:
- TREND_UP (ADX > 25, close > EMA50):
  - Pullback 기회 빈도: 상승추세 중 3-5일에 1회 pullback 발생
  - ~140일 * 20% pullback 구간 = ~28일 활성화 (P1 기준)

- UNCERTAIN (ADX 20-25 or mixed signals):
  - 40-55일 중 EMA(21) slope > 0인 구간: ~50%
  - ~25일 활성화 (P1+P2 평균)

- RANGING (ADX < 20):
  - 추세가 약하므로 pullback 패턴 불명확
  - ~5일 활성화 (미미)

- TREND_DOWN:
  - EMA(21) slope 하향이므로 Long 진입 불가
  - 0일 활성화

총 예상 TP 활성일:
- P1: ~35일 (BM이 진입 못하는 pullback 구간 + UNCERTAIN 일부)
- P2: ~25일 (mixed market에서 기회 감소)
- 전체: ~60일/522일 = 11.5%
```

이것이 의미하는 바: Trend Pullback은 기존 BM/MR이 커버하지 못하는 **60일**에 추가로 거래를 생성한다. 이중 ADX dead zone(20-28)에서의 거래가 40일 이상을 차지한다.

**분석 3: Core+Satellite의 레짐 관점 평가**

```
Core+Satellite (60% SPY + 40% Active):

장점:
- TREND_UP: Core가 상승을 포착 + Active(BM)가 알파 추가
- RANGING: Core가 횡보해도 최소한 포지션 유지, MR이 추가 수익
- TREND_DOWN: Core가 하락하지만 Full 100% exposure보다 40% 낮은 손실

단점:
- TREND_DOWN에서 Core가 손실 발생: 60% * (-10%) = -6%
  - Active는 BM 차단으로 idle이므로 상쇄 불가
  - 현재 시스템은 TREND_DOWN에서 idle -> 0% 손실
  - Core+Satellite는 TREND_DOWN에서 -6% 손실 -> WORSE

- P2(Mixed)에서 Core 기여: 60% * 15.5% = 9.3% (단독으로 우리 현재 수익의 60%)
  - Active(40% capital): 40% * 33% ROIC = 13.2%
  - 합계: 22.5% -- 현재 15.4%보다 7.1%p 개선
  - 그러나 S&P 31.4%에 여전히 미달

레짐 관점 결론:
- Core+Satellite는 '최소 참여'를 보장하는 보험
- 그러나 TREND_DOWN에서의 Core 손실이 약점
- 3번째 전략 추가 + warmup 최적화가 먼저 시도해볼 가치가 있음
- Core+Satellite는 Phase 3 옵션으로 유보
```

**분석 4: Idle Cash Money Market -- 무위험 수익의 즉각적 적용**

```
현행 idle cash: 평균 73.6% of equity
Money market 수익률: 연 4.5-5.0% (현재 금리 환경)

추가 수익:
- P1 (1년): 73.6% * 4.75% = 3.50%
- P2 (1년): 73.6% * 4.75% = 3.50%
- Combined: 7.00%

현재 15.4% + 7.0% = 22.4% (combined)
S&P 31.4% 대비 격차: -16.0%p -> -9.0%p (43% 격차 축소)

이것은 전략 변경 없이 얻을 수 있는 '무료 점심'이다.
금리가 향후 하락해도 3% 이상은 유지될 가능성이 높다.
```

**분석 5: 워밍업 기간의 구조적 해법**

```
현재: Test period 시작 = Data 시작 -> indicator 계산 불가 기간 = warmup
해법: Test period 시작일 이전 60-80일 데이터를 pre-load

구현:
1. data_loader에서 test_start_date - 80 trading days 부터 데이터 로드
2. Day 1 ~ Day 80: indicator 계산만 수행, trade execution 하지 않음
3. Day 81 (= test_start_date): 모든 indicator 유효, 즉시 거래 가능

효과:
- 88일 warmup -> 0일 warmup (조건 충족 시 Day 1부터 거래)
- 현실적으로 첫 거래는 Day 3-10 (조건 충족까지 수일 필요)
- 78-85일 추가 거래 기간 확보
- P1 기준: 78 추가일 * 평균 1.5 포지션 * $15K * 30% ROIC / 252일 = ~$1,250 추가 수익 ≈ +1.25%
```

**Strat-4의 최종 입장: Warmup 제거 + Money Market + Trend Pullback의 3개 조합이 최소 리스크로 최대 효과를 낸다. Core+Satellite는 이 3개 시도 이후로 유보한다.**"

---

## 3. Cross-Expert Synthesis

### Question A: 3번째 전략을 추가해야 하는가?

**만장일치: YES (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | ADX 20-28 Dead Zone은 시스템의 가장 큰 구조적 결함. Trend Pullback이 이를 직접 해결한다. |
| Strat-2 | 3rd strategy가 +7-10% deployment 추가, 연 +1.5-2.5% return 추정. Phase 2 조합 시 S&P에 근접. |
| Strat-3 | 새 전략의 타이트한 SL(1.5 ATR)과 보수적 GDR(3%/6%)로 MaxDD 증가를 2-3%p로 억제 가능. |
| Strat-4 | 레짐 분석 상 ~60일의 추가 거래일을 확보. 기존 전략과 상관관계 낮음. |

**전략 유형: Trend Pullback (EMA Pullback-and-Resume)**

```
핵심 설계 원칙:
1. ADX 15-35 범위에서 활성화 (BM/MR의 dead zone 커버)
2. 상승추세 내 pullback 매수 (high probability setup)
3. 타이트한 SL(1.5 ATR)로 빠른 손절 (BM의 2.5보다 적극적)
4. Long only (현재 시스템과 일관성)
5. Group B (confirmation 기반, 당일 MOO가 아닌 다음날 open)
```

### Question B: MR Cap 3 -> 4-5로 올려야 하는가?

**다수 동의: 조건부 YES (3/4, Strat-2 유보)**

| Expert | 입장 | 근거 |
|--------|------|------|
| Strat-1 | YES (cap 4) | MR P2 PF 2.86은 확대할 가치 있음 |
| Strat-2 | DEFER | MR 연 12-16건으로 cap 3도 거의 안 달함. 실질 효과 미미. |
| Strat-3 | YES (regime-conditional) | RANGING에서 cap 4, TREND_UP에서 cap 2로 차등 적용 |
| Strat-4 | YES (cap 4) | P2에서 MR 기여가 전체 수익의 60%. 기회 확대 합당. |

**결정: MR cap 4 채택하되, regime-conditional cap은 구현 복잡도 대비 효과 미미하므로 단순 4로 설정. P2 Priority.**

### Question C: Risk Per Trade 2% -> 3%로 올려야 하는가?

**만장일치: NO (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | Position size 증가는 MaxDD를 비례 증가시킴. Calmar 불변. |
| Strat-2 | 수학적으로 Calmar 개선 없음 (return과 DD가 같은 비율로 증가). |
| Strat-3 | **VETO.** 30% MaxDD는 $5K 소액 계정에서 절대 불가. 심리적 한계 초과. |
| Strat-4 | 레짐 전환 시 동시 SL의 dollar impact가 50% 증가. 회복 더 어려움. |

**결정: Risk 2% 유지. 이 파라미터는 LOCKED.**

### Question D: Warmup 88일을 줄일 수 있는가?

**만장일치: YES (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | 라이브 트레이딩에서도 historical warmup 사용. 백테스트도 동일하게 pre-load. |
| Strat-2 | 수학적으로 max(indicator periods) = 50 bars. 60 pre-load면 충분. |
| Strat-3 | 리스크 변경 없음. 순수 기술적 개선. |
| Strat-4 | 78일 추가 거래 기간 = +1.25% return 추정. Zero downside. |

**결정: batch_simulator 수정 -- test period 시작 전 80일 데이터 pre-load. _MIN_BARS_WARMUP은 유지하되 pre-load 데이터가 이를 충족.**

### Question E: Core+Satellite 아키텍처?

**다수 유보: DEFER (3/4, Strat-4 유보, Strat-2 조건부 찬성)**

| Expert | 입장 | 근거 |
|--------|------|------|
| Strat-1 | DEFER | 3rd strategy로 deployment 충분히 올릴 수 있음. Core+Satellite는 시스템 철학 변경. |
| Strat-2 | 조건부 YES | Phase 2 후에도 deployment < 40%면 Core 30% 도입 고려. 지금은 아님. |
| Strat-3 | DEFER | Core의 TREND_DOWN 손실이 현재 시스템의 '현금 방어' 장점을 제거. |
| Strat-4 | DEFER | 3번째 전략 + warmup + money market 결과를 먼저 확인. |

**결정: Phase 3로 유보. Phase 2 결과가 S&P 대비 -5%p 이상 격차면 재논의.**

### Question F: Idle Cash Money Market?

**만장일치: YES -- 즉시 시행 (4/4)**

| Expert | 근거 |
|--------|------|
| Strat-1 | 전략 변경 없이 연 3.5% 추가 수익. 거부할 이유 없음. |
| Strat-2 | 73.6% idle cash * 5% yield = 3.68%/year. Combined +7.4% over 2 years. |
| Strat-3 | 리스크 제로. Cash는 이미 idle. Money market은 T-bill 수준 안전. |
| Strat-4 | 금리 환경이 변해도 최소 3% yield. 장기적으로도 유효. |

**결정: batch_simulator에 cash yield 계산 추가. Daily idle cash * (annual_rate / 252).**

---

## 4. Consolidated Proposal Ranking

### Impact vs Risk vs Implementation Effort Matrix

| # | Proposal | Deploy Impact | Return Impact | MaxDD Impact | Risk Level | Effort | Priority |
|---|----------|---------------|---------------|-------------|------------|--------|----------|
| 1 | Idle Cash Money Market | 0%p | **+3.5%/yr** | 0%p | ZERO | 0.5 day | **P0** |
| 2 | Warmup Pre-load (88d -> 0d) | **+5%p** | **+1.3%/yr** | +0%p | ZERO | 1 day | **P0** |
| 3 | MR Cap 3 -> 4 | +1-2%p | +0.3-0.6%/yr | +1%p | LOW | 0.5 day | **P1** |
| 4 | 3rd Strategy (Trend Pullback) | **+7-10%p** | **+1.5-2.5%/yr** | +2-3%p | MEDIUM | 2-3 weeks | **P1** |
| 5 | BM Cap 2 -> 3 | +2-4%p | +0.6-1.2%/yr | +2-3%p | MEDIUM | 0.5 day | **P2** |
| 6 | Core+Satellite (50/50) | +37%p | +5-8%/yr | +5-10%p | MEDIUM-HIGH | 1-2 weeks | **DEFERRED** |
| 7 | Risk 2% -> 3% | 0%p | +3.7%/yr | **+10%p** | HIGH | trivial | **REJECTED** |
| 8 | Universe Expansion | +3-5%p | +0.9-1.5%/yr | +1-2%p | MEDIUM | 2-4 weeks | **DEFERRED** |
| 9 | Intraday Timeframes | +5-10%p | +2-4%/yr | unknown | HIGH | 4+ weeks | **DEFERRED** |

### Implementation Roadmap

```
Phase 1 (P0 -- 즉시 시행, 1-2일):
  [1] Idle cash money market yield (batch_simulator 수정)
  [2] Warmup pre-load (batch_simulator data loading 수정)
  [3] MR cap 3 -> 4

  Expected Combined Effect:
  - Deployment: 26.4% -> ~33%
  - Return (2yr): 15.4% + 7.0% (cash) + 2.5% (warmup) + 1.0% (MR cap) = ~25.9%
  - MaxDD: 20% -> ~21% (미미한 증가)
  - S&P Gap: -16%p -> -5.5%p (65% 축소!)

Phase 2 (P1 -- Trend Pullback 전략 추가, 2-3주):
  [4] Trend Pullback strategy design + implementation
  [5] Backtest validation (both periods)
  [6] Panel #32 review

  Expected Cumulative Effect:
  - Deployment: 33% -> ~40-43%
  - Return (2yr): 25.9% + 3.5% (TP strategy) = ~29.4%
  - MaxDD: 21% -> ~23% (3rd strategy 추가 분)
  - S&P Gap: -5.5%p -> -2.0%p (S&P 거의 근접!)

Phase 3 (P2 -- 추가 최적화, Phase 2 결과에 따라 결정):
  [7] BM cap 2 -> 3 (Phase 2 결과가 양호할 경우)
  [8] Core+Satellite 검토 (Phase 2에서 S&P 대비 격차 > 5%p일 경우)

  Expected Cumulative Effect:
  - Deployment: 43% -> ~46%
  - Return (2yr): ~30-32% (S&P 수준)
```

---

## 5. 3rd Strategy Specification: Trend Pullback

### Entry Criteria (Long Only)

```python
# Trend Pullback Strategy Entry Conditions
# Name: "trend_pullback"
# Entry Group: A (MOO -- 다음날 시가 매수)

# Required Indicators:
# - EMA(21), EMA(50)
# - ADX(14)
# - RSI(14)
# - ATR(14)

def generate_signal(context: MarketContext) -> Signal | None:
    close = context.bar.close
    ema_21 = context.indicators["EMA_21"]
    ema_50 = context.indicators["EMA_50"]
    adx = context.indicators["ADX_14"]
    rsi = context.indicators["RSI_14"]
    atr = context.indicators["ATR_14"]

    # 1. Trend confirmation
    if close < ema_50:                    # Must be above EMA(50) for uptrend
        return None

    # 2. EMA(21) slope positive (5-day lookback)
    ema_21_5d_ago = context.bar_history[-5].indicators["EMA_21"]  # 구현 시 조정
    if ema_21 <= ema_21_5d_ago:           # EMA must be rising
        return None

    # 3. ADX in target range (fills the dead zone)
    if adx < 15.0 or adx > 35.0:         # ADX 15-35
        return None

    # 4. Price near EMA(21) (pullback to support)
    ema_ratio = close / ema_21
    if ema_ratio > 1.02:                  # Must be within 2% above EMA
        return None
    if ema_ratio < 0.97:                  # Must not be >3% below (breakdown risk)
        return None

    # 5. RSI in pullback zone (not oversold, not overbought)
    if rsi < 35.0 or rsi > 60.0:         # RSI 35-60
        return None

    # 6. Reversal candle confirmation
    bar = context.bar
    body = abs(bar.close - bar.open)
    lower_wick = min(bar.open, bar.close) - bar.low
    if not (bar.close > bar.open or lower_wick > body * 1.5):
        # Must be green candle OR have strong lower wick (hammer)
        return None

    return Signal(
        symbol=context.symbol,
        strategy="trend_pullback",
        direction="long",
        strength=0.5 + (adx - 15) / 40,  # ADX로 strength 조절
        stop_distance=1.5 * atr,          # 타이트한 SL
    )
```

### Exit Rules

```
SL: Entry - 1.5 * ATR (BM의 2.5보다 타이트)
TP: Entry + 3.0 * ATR (RR = 2.0)
Time Exit: 7 bars (스윙 트레이딩 적정 기간)
Trend Loss: Close < EMA(50) for 2 consecutive bars

Trailing: YES (activation 1.5 ATR, distance 2.0 ATR -- BM과 동일)
  - Pullback 전략은 수익 보호가 중요 (추세 내 단기 매매)

Stage 1 BE: 1.0 ATR (BM의 1.5보다 빠른 breakeven 이동 -- 단기 매매 특성)
Stage 2 Profit Lock: 0.3 ATR (BM의 0.4보다 보수적 -- 빠른 SL 이동)
```

### Regime Allocation

```python
# regime_classifier.py 추가 항목:
_ALLOCATION_TABLE = {
    Regime.TREND_UP: {
        "breakout_momentum": 0.040,
        "rsi_mean_reversion": 0.012,
        "trend_pullback": 0.025,        # 상승추세 pullback = 핵심 환경
        "breakout_blocked": False,
        "mr_short_blocked": True,
        "tp_blocked": False,
    },
    Regime.TREND_DOWN: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.025,
        "trend_pullback": 0.000,        # 하락추세에서 long pullback = 불가
        "breakout_blocked": True,
        "mr_short_blocked": False,
        "tp_blocked": True,             # TREND_DOWN에서 완전 차단
    },
    Regime.RANGING: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.040,
        "trend_pullback": 0.010,        # 횡보 시장에서 약한 배치 (부분 활성)
        "breakout_blocked": False,
        "mr_short_blocked": False,
        "tp_blocked": False,
    },
    Regime.HIGH_VOLATILITY: {
        "breakout_momentum": 0.005,
        "rsi_mean_reversion": 0.020,
        "trend_pullback": 0.008,        # 고변동성에서 최소 배치
        "breakout_blocked": False,
        "mr_short_blocked": True,
        "tp_blocked": False,
    },
    Regime.UNCERTAIN: {
        "breakout_momentum": 0.008,
        "rsi_mean_reversion": 0.025,
        "trend_pullback": 0.015,        # UNCERTAIN에서 중간 배치 (ADX dead zone)
        "breakout_blocked": False,
        "mr_short_blocked": False,
        "tp_blocked": False,
    },
}
```

### GDR Configuration

```python
_STRATEGY_GDR_THRESHOLDS = {
    "breakout_momentum": (0.04, 0.08),   # LOCKED (Iter 23)
    "rsi_mean_reversion": (0.02, 0.04),  # LOCKED (Iter 23)
    "trend_pullback": (0.03, 0.06),      # 신규: BM보다 타이트 (입증 전 보수적)
}

_STRATEGY_BASE_RISK = {
    "breakout_momentum": 0.020,          # LOCKED
    "rsi_mean_reversion": 0.015,         # LOCKED
    "trend_pullback": 0.015,             # MR과 동일 (보수적 시작)
}

_SOFT_STRATEGY_CAP = {
    "breakout_momentum": 2,              # LOCKED
    "rsi_mean_reversion": 4,             # 3 -> 4 (이번 결정)
    "trend_pullback": 2,                 # 보수적 시작
}
```

---

## 6. Phase 1 Implementation Details

### Change 1: Idle Cash Money Market Yield

**File**: `autotrader/backtest/batch_simulator.py`

```python
# 새 상수 추가
_CASH_YIELD_ANNUAL: float = 0.0475   # 4.75% annual money market yield
_CASH_YIELD_DAILY: float = _CASH_YIELD_ANNUAL / 252  # ~0.01885% per trading day

# run() 메서드의 daily loop 내에서:
# 기존 equity/cash snapshot 이후에 추가:
idle_cash = self._cash  # 현재 미사용 현금
cash_yield = idle_cash * _CASH_YIELD_DAILY
self._cash += cash_yield
# daily_pnl에 포함하여 equity curve에 반영
```

**Effect**: 전략 로직 변경 없음. 순수 수익 추가.

### Change 2: Warmup Pre-load

**File**: `autotrader/backtest/batch_simulator.py` (data loading section)

```python
# 기존: data를 test_start_date부터 로드
# 변경: data를 test_start_date - 80 trading days부터 로드
# Indicator 계산은 전체 기간에 대해 수행
# Trade execution은 test_start_date 이후에만 허용

_WARMUP_PRELOAD_DAYS: int = 80  # 새 상수

# 구현: run() 메서드에서 warmup 기간의 bar를 indicator에는 feed하되
# signal generation / order execution은 skip하는 플래그 추가
```

**Effect**: 88일 warmup -> 약 5-10일 (조건 충족까지의 자연 대기). +78일 추가 거래 기간.

### Change 3: MR Cap 3 -> 4

**File**: `autotrader/backtest/batch_simulator.py`

```python
_SOFT_STRATEGY_CAP = {
    "breakout_momentum": 2,      # LOCKED
    "rsi_mean_reversion": 4,     # was 3, now 4 (Panel #31 decision)
}
```

**Effect**: MR의 동시 포지션 허용 한도 1건 증가. 연 12-16건 거래에서 cap이 binding되는 경우가 드물므로 효과는 미미하나, P2 RANGING에서 추가 기회 포착.

---

## 7. Expected Results by Phase

### Phase 1 (P0 Changes Only)

| Metric | Iter 23/26 Baseline | Phase 1 Expected | Delta |
|--------|---------------------|------------------|-------|
| P1 Return | +7.5% | +10.0% (+1.3% warmup, +1.7% cash yield) | +2.5%p |
| P2 Return | +7.9% | +10.4% (+1.0% warmup, +1.8% cash yield) | +2.5%p |
| Combined Return | +15.4% | ~+20.4% | **+5.0%p** |
| P1 MaxDD | 20.2% | ~20.5% | +0.3%p |
| P2 MaxDD | 21.0% | ~21.3% | +0.3%p |
| Capital Deployed | 26.4% | ~32% | +5.6%p |
| S&P Gap | -16.0%p | **-11.0%p** | 5.0%p 축소 |

### Phase 2 (+ Trend Pullback)

| Metric | Phase 1 Expected | Phase 2 Expected | Delta |
|--------|------------------|------------------|-------|
| Combined Return | ~20.4% | **~27-30%** | +7-10%p |
| Capital Deployed | ~32% | **~40-43%** | +8-11%p |
| MaxDD (worst) | ~21% | **~23%** | +2%p |
| S&P Gap | -11.0%p | **-1.4 ~ -4.4%p** | 대폭 축소 |

### Success / Failure Criteria

```
Phase 1 SUCCESS (proceed to Phase 2):
- Combined Return > +18% (cash yield + warmup 효과 확인)
- MaxDD < 23% (방어 체계 유지)
- 88-day warmup 제거 확인 (Day 1-10 내 첫 거래)

Phase 1 PARTIAL (adjust and retry):
- Combined Return +15-18% (cash yield만 반영, warmup 효과 미미)
- MaxDD < 25%
- Action: warmup implementation 점검

Phase 1 FAILURE (investigate):
- Combined Return < +15% (baseline 대비 악화)
- MaxDD > 25%
- Action: implementation bug 점검

Phase 2 SUCCESS (S&P 근접):
- Combined Return > +27%
- S&P Gap < -5%p
- Trend Pullback PF > 1.2 (both periods)
- MaxDD < 25%
=> PROCEED to live validation

Phase 2 PARTIAL (Phase 3 필요):
- Combined Return +22-27%
- Trend Pullback PF > 1.0
=> CONSIDER Core+Satellite or BM cap 3

Phase 2 FAILURE (Trend Pullback 재설계):
- Combined Return < +22%
- Trend Pullback PF < 1.0
=> REDESIGN 3rd strategy or consider alternative lever
```

---

## 8. Debate Points and Minority Opinions

### Debate 1: BM Cap 2 -> 3 (Phase 2 vs Phase 3?)

- **Strat-1**: Phase 2에서 즉시. BM은 검증된 전략. Cap 3이면 TREND_UP에서 더 많은 자본 배치.
- **Strat-3**: Phase 3로 유보. 3rd strategy + BM cap 3 = 동시 5-6건 포지션. MaxDD 리스크 과다.
- **결정**: **Phase 3로 유보**. 3rd strategy의 실제 MaxDD 기여를 Phase 2에서 확인 후 결정.

### Debate 2: Money Market Yield Rate 가정

- **Strat-2**: 4.75% 가정은 2026년 현재 금리 환경 기준. 금리 인하 시 3-4%로 하향 가능.
- **Strat-4**: 보수적으로 3.5%를 기본 가정으로 사용하고, 4.75%는 best case.
- **결정**: **4.0% 기본 가정** 채택. 백테스트에서는 configurable parameter로 구현.

### Debate 3: Trend Pullback ADX 범위 (15-35 vs 20-35)

- **Strat-1**: 15-35. ADX 15-20 구간도 pullback이 발생하며, MR과 겹쳐도 진입 조건이 다름.
- **Strat-4**: 20-35. MR과의 겹침을 완전 회피하는 것이 깔끔하다.
- **Strat-2**: 15-35가 수학적으로 더 많은 거래 기회를 생성. MR과 동시 진입은 position cap으로 관리.
- **결정**: **15-35 채택 (3:1, Strat-4만 20-35)**. MR과의 겹침은 portfolio-level position cap과 heat limit으로 관리.

### Debate 4: Trend Pullback Base Risk (1.5% vs 2.0%)

- **Strat-1**: 2.0%. BM과 동등한 conviction으로 시작해야 의미 있는 배치가 된다.
- **Strat-3**: 1.5%. 신규 전략은 입증 전까지 보수적. 검증 후 2.0% 상향.
- **결정**: **1.5% 채택 (Strat-3 의견 존중)**. Phase 2 결과에서 PF > 1.5 확인 시 2.0% 상향 논의.

---

## 9. DO NOT CHANGE (Locked Parameters -- 확장)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | 7-iter confirmed (Phase 3 재검토 가능) |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| BM TP ATR mult | exit_rules.py | 4.0 | Panel #27 decision |
| BM trailing activation | exit_rules.py | 1.5 | Iter 23 validated |
| BM trailing distance | exit_rules.py | 2.0 | Panel #30 confirmed |
| BM GDR thresholds | batch_simulator.py | (0.04, 0.08) | Iter 23 validated |
| MR GDR thresholds | batch_simulator.py | (0.02, 0.04) | Iter 23 validated |
| MAX_LONG | batch_simulator.py | 8 | Iter 23 value |
| MAX_TOTAL | batch_simulator.py | 9 | Iter 23 value |
| Risk per trade | batch_simulator.py | 2% | Panel #31 LOCKED |
| Heat | batch_simulator.py | 0.35 | Iter 23 value |
| Safety Net DD | batch_simulator.py | 0.12 | Iter 23 value |
| Safety Net Recovery | batch_simulator.py | 0.08 | Iter 23 value |
| Stage2 Profit Lock | exit_rules.py | 0.4 | Iter 23 value |

**새 Lock 규칙: Iter 23/26 baseline의 모든 파라미터는 LOCKED. 향후 변경은 Phase 2 이후 Panel에서만 논의 가능.**

---

## 10. Action Items

### 즉시 실행 (Phase 1 -- P0, 담당: Dev Team)

| # | Action | File | 담당 | 예상 기간 |
|---|--------|------|------|-----------|
| 1 | Cash yield 계산 로직 추가 | batch_simulator.py | Dev-2 | 0.5일 |
| 2 | Warmup pre-load 구현 | batch_simulator.py + runner | Dev-2 | 1일 |
| 3 | MR cap 3 -> 4 | batch_simulator.py | Dev-2 | 5분 |
| 4 | Phase 1 backtest (P1 + P2) | backtest runner | Dev-2 | 0.5일 |
| 5 | Panel #32: Phase 1 결과 리뷰 | - | Strategy Team | 결과 후 |

### 다음 단계 (Phase 2 -- P1, Phase 1 검증 후)

| # | Action | File | 담당 | 예상 기간 |
|---|--------|------|------|-----------|
| 6 | Trend Pullback strategy spec 최종화 | docs/analysis/ | Strategy Team | 1일 |
| 7 | Trend Pullback strategy 구현 | autotrader/strategy/ | Dev-1 | 3-4일 |
| 8 | Exit rules 확장 (TP 전용) | exit_rules.py | Dev-1 | 1일 |
| 9 | Regime allocator 확장 | regime_classifier.py | Dev-1 | 0.5일 |
| 10 | batch_simulator 3전략 통합 | batch_simulator.py | Dev-2 | 1일 |
| 11 | Phase 2 backtest (P1 + P2) | backtest runner | Dev-2 | 0.5일 |
| 12 | Panel #33: Phase 2 결과 리뷰 | - | Strategy Team | 결과 후 |

---

## 11. Iteration History (Updated)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 (LOCKED) |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | MR cap3, heat 35%, TP 4.0, trail 1.5 |
| 24 | -0.69% | +0.19% | -0.5% | 21.8% | 4.34% | DD reduction 11 changes (OVER-CORRECTED) |
| 25 | +1.76% | +3.40% | +5.16% | ? | ? | Partial rollback (6 differences from Iter 23) |
| **26** | **+7.5%** | **+7.9%** | **+15.4%** | **~20%** | **~21%** | **Clean revert to Iter 23 (reproducibility test)** |
| 27 (target) | +10.0% | +10.4% | **+20.4%** | ~20.5% | ~21.3% | **Phase 1: Cash yield + Warmup + MR cap 4** |
| 28+ (target) | ? | ? | **~27-30%** | ~23% | ~23% | **Phase 2: + Trend Pullback strategy** |

---

## 12. Key Principles Established

### Panel #31 Strategic Principles

1. **ROIC 30%는 충분하다. 문제는 deployment다.** 더 높은 ROIC를 추구하는 것보다 더 많은 자본을 일하게 하는 것이 S&P를 이기는 길이다.

2. **무위험 수익(money market)을 먼저 확보하라.** 전략 변경 없이 연 3.5%를 추가하는 것은 가장 높은 ROI 행동이다.

3. **ADX Dead Zone(20-28)은 시스템의 가장 큰 구조적 결함이다.** 이것을 해결하는 3번째 전략이 가장 높은 impact lever다.

4. **Position size 증가는 해법이 아니다.** Calmar이 개선되지 않으면 risk 증가는 무의미하다. Deployment를 strategy 다각화로 올려야 한다.

5. **Warmup 기간은 기술적 문제이지 전략적 제약이 아니다.** Pre-load로 해결 가능하며, 78일의 추가 거래 기간은 무시할 수 없는 가치다.

6. **Parameter tuning 시대는 끝났다.** 30개 이터레이션이 증명: Iter 23/26 파라미터는 최적이며, 미세 조정은 net-negative다. 앞으로는 구조적 변경만.

---

## Appendix A: 전략별 ADX 커버리지 맵

```
ADX Range:     0    5    10   15   20   25   28   30   35   40   45   50

MR Active:     |----|----|----|----▓▓▓▓▓|
               ADX < 20

TP Active:                        |▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓|
               ADX 15-35

BM Active:                                     |▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
               ADX > 28

DEAD ZONE:                        |XXXXXXXXXXXXX|
(before TP)    ADX 20-28 -- NO STRATEGY ACTIVE!

COVERAGE:      |----|----|----|▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
(after TP)     Nearly complete: ADX 0-15 only gap (very weak markets)
```

## Appendix B: Capital Deployment Projection

```
         Deployment %
    50% |                               ___________
        |                         ___---    Phase 3 (BM cap 3)
    45% |                   ___---
        |             ___---          Phase 2 (+Trend Pullback)
    40% |       ___---
        | ___---
    35% |---              Phase 1 (Warmup + MR cap)
        |
    30% |     ___
        |___--    Current + Cash yield (no deploy change, return only)
    26% |=========  Current Baseline (Iter 23/26)
        |
    20% |
        +----+----+----+----+----+----+----
             P0   P1   P2   P3   Future
```

## Appendix C: Return vs S&P Gap Projection

```
    Return %   S&P +31.4%
    32% |  - - - - - - - - - - - - - - S&P - - - - - - -
        |                                    ___---+
    30% |                              ___---    Phase 3
        |                        ___---
    28% |                  ___---    Phase 2
        |            ___---
    24% |      ___---
        |___---    Phase 1
    20% |---
        |
    16% |===  Iter 23/26 Baseline (+15.4%)
        |
    12% |
        +----+----+----+----+----+----+----
             P0   P1   P2   P3   Future

Gap:   -16%p  -11%p  -4%p  -1%p   0%p (target)
```
