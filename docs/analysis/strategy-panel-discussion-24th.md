# Strategy Panel Discussion #24: Iteration 12 Review -- 2-Strategy Active Allocation System

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant), Strat-3 (Risk Manager), Strat-4 (Data Analyst)
**Context**: Iteration 12 -- first run of 2-strategy active allocation architecture (breakout_momentum + adaptive_mean_reversion with SPY regime-based allocation)
**Decision**: REDESIGN_MR + TUNE_ALLOCATION (6 changes ranked by impact)

---

## 1. Backtest Results Summary

### Period 2 (2025-03 ~ 2026-02, S&P 500 +15.5%)

| Strategy | PnL | Trades | WR | PF | Exit Breakdown |
|----------|-----|--------|-----|------|----------------|
| breakout_momentum | +$4,434 | 17 | 70.6% | 4.468 | SL:9, trailing:5, forced:2, TP:1 |
| adaptive_mean_reversion | +$821 | 39 | 53.8% | 1.085 | **SL:26**, time:12, regime:1 |
| **Portfolio** | **+$5,255 (+5.4%)** | **56** | - | - | Max DD: **32.6%** |

**Verdict: FAIL** -- 5.4% vs 15.5% benchmark. Catastrophic risk-adjusted performance.

### Period 1 (2024-03 ~ 2025-02, S&P 500 +15.9%)

| Strategy | PnL | Trades | WR | PF | Exit Breakdown |
|----------|-----|--------|-----|------|----------------|
| breakout_momentum | +$2,690 | 13 | 76.9% | 13.729 | SL:8, trailing:4, forced:1 |
| adaptive_mean_reversion | +$135 | 54 | 51.9% | 1.011 | **SL:26**, time:17, regime:11 |
| **Portfolio** | **+$2,825 (+2.9%)** | **67** | - | - | Max DD: **34.9%** |

**Verdict: FAIL** -- 2.9% vs 15.9% benchmark. MR strategy is essentially dead weight.

### Comparison with Iteration 11 (3-strategy static)

| Metric | Iter 11 P2 | Iter 12 P2 | Delta |
|--------|-----------|-----------|-------|
| Total Return | +11.0% | +5.4% | **-5.6%** |
| BM PnL | +$5,600 | +$4,434 | -$1,166 |
| MR PnL (old) | +$3,122 | +$821 | **-$2,301** |
| Max DD | 16.5% | 32.6% | **+16.1%** |

Iter 12 is a regression across every metric. The new MR strategy is worse than the old rsi_mr + consecutive_down combination it replaced, and the regime allocation system is hurting BM without adequately controlling MR risk.

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- Entry Timing Diagnosis

"adaptive_mean_reversion의 진입 로직이 구조적으로 잘못되어 있다. 핵심 문제는 **EMA(50) 아래에서만 롱 진입**하는 조건이다.

코드를 보면 (adaptive_mean_reversion.py line 168):
```python
if close < ema_50:  # LONG entries: must be below EMA(50)
```

이것은 **중기 하락 추세에 있는 종목만 매수한다**는 뜻이다. Mean reversion의 원래 의도는 '일시적으로 과매도된 종목의 반등'인데, close < EMA(50) 조건은 '추세적으로 약한 종목'을 강제 선택한다. 이런 종목은 반등하기보다 계속 하락할 확률이 높다 -- 그래서 67%가 스톱로스에 걸리는 것이다.

Gate B의 문제도 심각하다. 3일 연속 하락 + RSI < 50 + close < EMA(50)의 조합은 사실상 **하락 추세 중인 종목에 역방향 베팅**이다. RSI < 50은 과매도 필터로 너무 느슨하다. RSI 48인 종목은 과매도가 아니라 그냥 약세일 뿐이다.

올바른 MR 진입은 **횡보 구간에서 일시적으로 과매도된 종목**이어야 한다. ADX < 25 필터가 이미 비추세를 걸러주므로, EMA(50) 아래 조건은 오히려 역효과다. BB 하단을 터치한 시점에 EMA(50) 위에 있다면 그 종목은 상승세 안에서 일시적으로 빠진 것이고, 반등 확률이 훨씬 높다."

### Strat-2 (Quant) -- 수학적 분석

"숫자를 정리하겠다.

**MR 전략 수익성 분해 (Period 2)**:
- 39 trades, 21 wins (53.8%), 18 losses
- PnL: +$821, PF: 1.085
- Exit 분류: SL 26건 (66.7%), time_exit 12건 (30.8%), regime_guard 1건
- 26건 SL 중 일부는 승리 트레이드에서도 SL이 발동된 것 (2-stage SL이 breakeven으로 올라간 후 hit)

하지만 중요한 것은 **ATR 기반 stop/target 비율**이다:
- Long SL: 1.5 ATR (exit_rules.py line 50)
- Long TP: 2.5 ATR (exit_rules.py line 429)
- Risk:Reward = 1.5:2.5 = 1:1.67

1:1.67 R:R에서 53.8% WR이면 기대값은:
- EV = (0.538 * 2.5) - (0.462 * 1.5) = 1.345 - 0.693 = +0.652 ATR/trade

이론적 EV는 양수인데, 실제 PnL이 거의 0에 가까운 이유는:
1. **SL이 정확히 1.5 ATR에서 걸리지 않는다** -- 갭이나 슬리피지로 실제 손실이 1.5 ATR을 초과하는 경우가 많다
2. **TP에 도달하기 전에 time_exit (7일)로 나가는 경우** -- 12건의 time_exit이 TP보다 낮은 가격에서 청산
3. **regime_guard 강제 청산** -- 수익 중인 포지션도 레짐 전환 시 조기 청산

실질적인 문제는 **1.5 ATR SL이 MR 전략의 자연 변동성 대비 너무 타이트**하다는 것이다. MR은 과매도 진입이므로 진입 직후 추가 하락(dip further before reversion)이 정상이다. BM은 2.5 ATR SL을 쓰고 있는데, 정작 추가 하락이 필요한 MR이 1.5 ATR을 쓰는 것은 비합리적이다.

**BM 수익 감소 분석**:
Iter 11 BM: $5,600 (추정 static alloc ~2-3%)
Iter 12 BM: $4,434 (dynamic alloc)

감소 원인:
1. TREND_DOWN 레짐에서 breakout_blocked=True -> 진입 자체가 차단됨
2. RANGING에서 BM risk 0.8% -> 포지션 크기 대폭 축소
3. forced_close 2건 -> 레짐 전환 시 수익 중인 포지션 조기 청산

RANGING에서의 BM 0.8%가 특히 문제다. 레인지 돌파(range breakout)야말로 BM의 핵심 셋업인데, 가장 좋은 기회에서 포지션 크기를 1/3로 줄이고 있다."

### Strat-3 (Risk Manager) -- 드로다운 분석 및 리스크 관리

"가장 심각한 문제는 **Max DD 32.6%** (P2)와 **34.9%** (P1)이다. $1K-$5K 계좌에서 35% 드로다운은 계좌 생존 위협 수준이다. 이전 Iter 11의 16.5%에서 배로 악화되었다.

**DD 원인 분석**:
1. **MR 포지션 동시 피격**: 시장 하락 시 MR 신호가 여러 종목에서 동시 발생한다. 모두 '과매도 종목 매수'이므로 완전히 상관관계가 있다. 시장이 더 하락하면 동시에 SL에 걸린다.
2. **MR의 부의 기여**: +$821 수익에 32.6% DD를 감내한다면, MR의 리턴/리스크 비율은 처참하다.
3. **레짐 기반 리스크 조절의 역효과**: TREND_DOWN에서 MR 1.5% 할당은 오히려 너무 공격적이다. 하락 추세에서 역추세 베팅에 1.5%를 배팅하는 것은 falling knife를 잡는 행위다.

**Allocation Table 문제점**:

| Regime | BM 현재 | BM 적정 | MR 현재 | MR 적정 |
|--------|---------|---------|---------|---------|
| TREND_UP | 2.5% | 2.5% (OK) | 0.3% | 0.3% (OK) |
| TREND_DOWN | 0.5% (blocked) | 0.5% (blocked, OK) | 1.5% | **0.3%** |
| RANGING | 0.8% | **1.5%** | 2.0% | 2.0% (OK) |
| HIGH_VOL | 0.5% | 0.5% (OK) | 0.8% | 0.8% (OK) |
| UNCERTAIN | 1.2% | **1.5%** | 1.2% | **0.8%** |

TREND_DOWN에서 MR 1.5%는 즉시 0.3%로 낮춰야 한다. 하락 추세에서의 mean reversion은 가장 위험한 전략이다. 반면 RANGING에서의 BM은 range breakout 기회이므로 1.5%로 올려야 한다.

**동시 포지션 제한**: MR은 최대 2포지션 동시 보유 제한이 필요하다. 상관 리스크를 제어하지 않으면 시장 하락 시 MR 포지션들이 동시에 터지며 DD를 악화시킨다."

### Strat-4 (Data Analyst) -- 데이터 기반 진단

"Exit breakdown에서 가장 명확한 패턴이 보인다.

**adaptive_mean_reversion Exit 분포**:
```
Period 2: SL:26 (66.7%) | time_exit:12 (30.8%) | regime_guard:1 (2.6%)
Period 1: SL:26 (48.1%) | time_exit:17 (31.5%) | regime_guard:11 (20.4%)
```

**핵심 관찰**:
1. **take_profit이 단 0건이다.** TP 2.5 ATR에 도달하는 거래가 단 하나도 없다. 이것은 TP가 비현실적으로 높거나, 그 전에 다른 exit이 트리거되고 있다는 뜻이다.
2. MR 전략 코드 내부의 exit 로직(BB/RSI target, EMA(5) exit)이 exit_rules.py의 ATR TP보다 먼저 발동하고 있을 가능성이 높다. 하지만 exit breakdown에 'target'이나 'ema5_exit'이 없다는 것은 **전략 내부 exit 신호가 배치 시뮬레이터에서 제대로 처리되지 않고 있을 수 있다.**
3. P1에서 regime_guard 11건(20.4%)은 상당한 비중이다. 이 중 수익 중이었던 포지션이 레짐 전환으로 조기 청산된 케이스가 얼마나 되는지 확인이 필요하다.

**Gate별 성과 분석 필요**:
현재 metadata에 sub_strategy (mr_long_gate_a, mr_long_gate_b, mr_short_gate_a)가 기록되는데, exit breakdown에서 Gate별 분리가 되지 않았다. 다음 이터레이션에서는 Gate별 성과를 분리해야 한다.

**BM 분석**:
BM은 여전히 강력하다. 70.6% WR, PF 4.468. 문제는 거래 빈도(17건/12개월)와 할당 크기 축소다. BM의 trailing_stop:5는 긍정적 -- 추세를 타고 이익을 보호하고 있다. forced_close:2가 아쉬운 부분이다.

**비교 데이터**:
Iter 11의 old MR 전략(rsi_mr + consecutive_down)은 P2에서 $3,122를 생성했다. 새 adaptive_MR은 같은 기간에 $821이다. 두 전략을 합친 것보다 성과가 나쁘다는 것은 합산(consolidation) 자체의 문제가 아니라, **새 전략의 파라미터가 최적화되지 않았다**는 뜻이다."

---

## 3. 교차 진단 합의

### 합의 사항 (Consensus)

1. **MR SL 1.5 ATR은 너무 타이트하다** (전원 동의)
   - MR은 과매도 진입이므로 진입 후 추가 하락이 자연스럽다
   - BM도 2.5 ATR SL을 쓰는데 MR이 1.5 ATR은 비합리적

2. **close < EMA(50) 조건이 MR 롱의 핵심 실패 원인이다** (Strat-1, Strat-2 동의, Strat-3 조건부 동의)
   - 중기 하락 추세 종목만 선택하게 되어 반등 확률이 낮아짐
   - ADX < 25 필터로 이미 추세 필터링이 되고 있어 이중 제약

3. **TREND_DOWN에서 MR 1.5% 할당은 과도하다** (Strat-3 주도, 전원 동의)
   - 하락 추세에서 역추세 전략에 높은 할당은 자살 행위

4. **RANGING에서 BM 0.8%는 과소하다** (Strat-2 주도, Strat-1 동의)
   - Range breakout이 BM의 최적 셋업 중 하나인데 포지션 크기를 지나치게 줄임

### 이견 사항 (Debate)

1. **Gate B (consecutive down) 제거 vs 강화**
   - Strat-1: 제거 권고. Gate A(BB/RSI)가 더 이론적으로 건전함
   - Strat-2: 유지하되 RSI 임계값을 40으로 강화. 백테스트 데이터가 Gate별로 분리되지 않아 결론을 내리기 이름
   - **결정: Gate B 유지하되 RSI < 50 -> RSI < 40으로 강화, EMA(50) 조건 제거**

2. **MR TP 조정**
   - Strat-2: 현재 TP 2.5 ATR에 도달하는 거래가 0건이므로 TP를 낮춰야 함 (2.0 ATR 제안)
   - Strat-1: TP를 낮추면 수익 cap이 낮아지므로 현행 유지, SL을 넓히면 자연스럽게 개선될 것
   - **결정: SL 변경 후 재관찰. TP는 현행 유지.**

3. **전략 내부 exit과 exit_rules.py 간의 중복/충돌**
   - Strat-4: 전략 내부 exit 신호(target, ema5_exit, timeout)가 배치 시뮬레이터에서 실제로 작동하는지 확인 필요
   - **결정: 코드 검증 필요. 다음 이터레이션 전에 확인.**

---

## 4. Ranked Recommendations for Iteration 13

### Priority 1 (CRITICAL): MR Stop Loss 확대
**Impact: 예상 MR WR +10-15%, DD -5-8%**

| Parameter | File | Line | Current | Proposed |
|-----------|------|------|---------|----------|
| SL ATR mult (long) | exit_rules.py | 50 | 1.5 | **2.5** |
| SL ATR mult (short) | exit_rules.py | 50 | 2.0 | **2.5** |
| SL in strategy code (long) | adaptive_mean_reversion.py | 181, 206 | `close - 1.5 * atr` | `close - 2.5 * atr` |

**근거**: MR은 과매도 진입이므로 가격이 진입 후 추가 하락하는 것이 정상이다. 1.5 ATR은 자연 변동성 범위 안에 있어 노이즈에 의해 조기 스톱아웃된다. 2.5 ATR은 충분한 호흡 공간을 제공하면서도 리스크를 제어한다.

### Priority 2 (CRITICAL): EMA(50) 필터 제거/수정
**Impact: 예상 MR 진입 품질 개선, SL rate -15-20%**

| Parameter | File | Line | Current | Proposed |
|-----------|------|------|---------|----------|
| Long entry condition | adaptive_mean_reversion.py | 168 | `close < ema_50` | **제거 (ADX<25가 이미 추세 필터)** |
| Gate B long condition | adaptive_mean_reversion.py | 168 | `close < ema_50` | **제거** |
| Short entry condition | adaptive_mean_reversion.py | 227 | `close > ema_50` | 유지 |

**근거**: close < EMA(50)는 중기 하락세 종목만 선택하게 만들어 반등 실패율을 높인다. ADX < 25 필터가 이미 추세 시장을 차단하므로 EMA(50)는 이중 제약이다. EMA(50) 위에서 BB 하단에 터치한 종목은 '상승 추세 안에서의 일시적 과매도'이므로 반등 확률이 훨씬 높다. Short 진입의 close > EMA(50)은 유지한다 (중기 상승세 종목의 과매수를 공매도하는 것은 합리적).

### Priority 3 (HIGH): Gate A 진입 임계값 완화
**Impact: 예상 MR 진입 타이밍 개선, 더 얕은 과매도에서 진입**

| Parameter | File | Line | Current | Proposed |
|-----------|------|------|---------|----------|
| GATE_A_LONG_PCT_B_MAX | adaptive_mean_reversion.py | 38 | 0.20 | **0.30** |
| GATE_A_LONG_RSI_MAX | adaptive_mean_reversion.py | 39 | 40.0 | **45.0** |

**근거**: pct_b < 0.20은 BB 하단 20% 이내로 매우 깊은 과매도다. 이 시점에서 진입하면 추가 하락 여지가 크고 SL까지 거리가 짧다. pct_b < 0.30은 여전히 과매도이지만 덜 극단적이어서 반등 성공률이 높다. RSI 40 -> 45 완화도 같은 논리다.

### Priority 4 (HIGH): Gate B RSI 임계값 강화
**Impact: 예상 Gate B 잡음 신호 -30-40%**

| Parameter | File | Line | Current | Proposed |
|-----------|------|------|---------|----------|
| GATE_B_LONG_RSI_MAX | adaptive_mean_reversion.py | 45 | 50.0 | **40.0** |

**근거**: RSI < 50은 과매도 필터로 너무 느슨하다. RSI 48인 종목은 '약간 약세'일 뿐 과매도가 아니다. Gate A와 동일한 RSI < 40으로 맞추면, Gate B도 진정한 과매도 상태에서만 트리거된다.

### Priority 5 (HIGH): Regime Allocation 조정
**Impact: BM 수익 +$500-800, MR DD -5%**

| Regime | Strategy | File | Current | Proposed |
|--------|----------|------|---------|----------|
| TREND_DOWN | adaptive_mean_reversion | regime_classifier.py | 0.015 | **0.003** |
| RANGING | breakout_momentum | regime_classifier.py | 0.008 | **0.015** |
| UNCERTAIN | breakout_momentum | regime_classifier.py | 0.012 | **0.015** |
| UNCERTAIN | adaptive_mean_reversion | regime_classifier.py | 0.012 | **0.008** |

**근거**:
- TREND_DOWN에서 MR 1.5%는 하락 추세 역행 베팅. 0.3%로 최소화하여 "있되 거의 안 쓴다" 수준으로.
- RANGING에서 BM 0.8%는 range breakout 기회 상실. 1.5%로 올려 적정 포지션 확보.
- UNCERTAIN에서 BM은 안정적(PF 4.4)이므로 약간 증가, MR은 불안정(PF 1.0)이므로 감소.

### Priority 6 (MEDIUM): MR 동시 포지션 제한
**Impact: 예상 상관 DD -5-10%**

| Parameter | File | Current | Proposed |
|-----------|------|---------|----------|
| MR max concurrent positions | batch_simulator.py | 제한 없음 | **최대 2** |

**근거**: MR 신호는 시장 하락 시 동시 다발적으로 발생한다. 모두 '과매도 종목 매수'이므로 완전히 상관되어 있다. 동시 2포지션 제한으로 집중 리스크를 제어한다.

---

## 5. 코드 검증 필요 사항 (Pre-Iteration 13)

### 5-1. 전략 내부 Exit 신호 처리 확인
adaptive_mean_reversion.py의 `_check_exit()`이 "target", "ema5_exit", "timeout" 신호를 반환하지만, exit breakdown에 이 이유들이 나타나지 않는다. batch_simulator가 전략 내부 exit signal을 어떻게 처리하는지 확인 필요:
- 전략이 `direction="close"` 신호를 반환할 때 시뮬레이터가 이를 인식하는가?
- exit_rules.py의 SL/TP가 전략 exit보다 먼저 체크되어 override하는 것은 아닌가?

### 5-2. Gate별 성과 분리 로깅
다음 이터레이션 결과에서 sub_strategy별(gate_a, gate_b, short_gate_a) 분리 통계 필요:
- 각 gate의 WR, PF, 평균 수익/손실
- 어느 gate가 수익을 내고 어느 gate가 손실을 내는지

### 5-3. SL Hit 타이밍 분석
26건의 SL 중 진입 후 몇 일째에 걸리는지 분포 확인:
- Day 1-2 SL: 진입 타이밍 문제 (너무 빠른 진입)
- Day 3-5 SL: SL 너비 문제 (너무 타이트)
- Day 6-7 SL: 방향 판단 실패 (전략 근본 문제)

---

## 6. Decision Summary

| 항목 | 결정 |
|------|------|
| MR SL | 1.5 -> 2.5 ATR (long), 2.0 -> 2.5 ATR (short) |
| EMA(50) filter | Long 진입에서 제거, Short 유지 |
| Gate A pct_b | 0.20 -> 0.30 |
| Gate A RSI | 40.0 -> 45.0 |
| Gate B RSI | 50.0 -> 40.0 |
| TREND_DOWN MR alloc | 1.5% -> 0.3% |
| RANGING BM alloc | 0.8% -> 1.5% |
| UNCERTAIN BM alloc | 1.2% -> 1.5% |
| UNCERTAIN MR alloc | 1.2% -> 0.8% |
| MR concurrent limit | 무제한 -> 2 |
| Gate B 처리 | 유지, RSI 강화 |
| TP | 현행 유지 (SL 변경 후 재관찰) |
| 코드 검증 | 전략 exit 신호 처리, Gate별 통계 분리 |

**Next Step**: Priority 1-5 구현 후 Iteration 13 backtest 실행. Priority 6은 구현 복잡도 따라 판단.
