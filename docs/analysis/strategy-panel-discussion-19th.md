# Strategy Panel Discussion #19: Iteration 5 Post-Mortem -- breakout_momentum Exit Structure Failure

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Data Analyst)
**Context**: Iteration 5 results review, breakout_momentum exit parameter diagnosis, P1 structural loss analysis
**Decision**: PARAM_TUNE (3 parameter changes focused on breakout_momentum exit structure)

---

## 1. Iteration 5 Results Summary

### Period 2 (2025-03 ~ 2026-02) -- Mixed market with correction

| Metric | Value | Target | Gap |
|--------|-------|--------|-----|
| Total Return | +9.1% | >= +15% | -5.9%p |
| MaxDD | 16.9% | < 20% | OK |
| Sharpe | 0.414 | >= 1.0 | -0.586 |
| Calmar | 0.540 | >= 1.0 | -0.460 |
| Trades | 81 | - | - |
| WR | 70.4% | - | - |
| PF | 1.531 | - | - |

### Period 1 (2024-03 ~ 2025-02) -- Strong bull market

| Metric | Value | Target | Gap |
|--------|-------|--------|-----|
| Total Return | -6.5% | > 0% | -6.5%p |
| MaxDD | 22.9% | < 20% | -2.9%p |
| Sharpe | 0.073 | >= 1.0 | -0.927 |
| Calmar | -0.283 | >= 1.0 | -1.283 |
| Trades | 72 | - | - |
| WR | 45.8% | - | - |
| PF | 0.654 | - | - |

### S&P 500 Benchmark Comparison

| Metric | P1 (SPY) | P1 (Ours) | P2 (SPY) | P2 (Ours) |
|--------|----------|-----------|----------|-----------|
| Return | +15.9% | -6.5% | +15.5% | +9.1% |
| MaxDD | 8.5% | 22.9% | 16.3% | 16.9% |
| Sharpe | 1.221 | 0.073 | 0.877 | 0.414 |

**Verdict**: P1에서 벤치마크 대비 22.4%p 언더퍼폼. P2에서도 6.4%p 언더퍼폼. 두 기간 모두 목표 미달.

---

## 2. Per-Strategy Breakdown

### breakout_momentum (핵심 문제 전략)

| Metric | P1 (Bull) | P2 (Mixed) | Delta |
|--------|-----------|------------|-------|
| Trades | 38 | 45 | +7 |
| WR | 47.4% | 66.7% | +19.3%p |
| PF | 0.759 | 1.331 | +0.572 |
| PnL | -$2,788 | +$3,844 | +$6,632 |
| Avg Hold | ~5-6d | 5.7d | - |

**Exit Distribution (P1)**:
- stop_loss: 20건 (53%) -- 가장 빈번
- time_exit: 18건 (47%) -- 두 번째
- take_profit: 0건 (0%) -- **ZERO**
- trailing_stop: 0건 (0%) -- **ZERO**

**Exit Distribution (P2)**:
- time_exit: 21건 (47%) -- 가장 빈번
- stop_loss: 19건 (42%) -- 두 번째
- trailing_stop: 3건 (7%) -- 미미
- take_profit: 1건 (2%) -- 거의 없음
- forced_close: 1건 (2%)

### consecutive_down (양호)

| Metric | P1 | P2 |
|--------|----|----|
| Trades | 20 | 16 |
| WR | 60.0% | 87.5% |
| PF | 0.852 | 4.626 |
| PnL | -$483 | +$2,521 |

P1에서 소폭 손실이지만 구조적으로 안정적. 이번 이터레이션에서는 건드리지 않음.

### rsi_mean_reversion (P1 구조적 문제 지속)

| Metric | P1 | P2 |
|--------|----|----|
| Trades | 14 | 20 |
| WR | 21.4% | 65.0% |
| PF | 0.216 | 1.571 |
| PnL | -$3,335 | +$2,558 |

**P1 Exit Distribution**:
- regime_guard: 4건 (29%)
- stop_loss: 5건 (36%)
- take_profit: 1건 (7%)
- time_exit: 4건 (29%)

P2에서는 양호하나 P1에서 WR 21.4%는 전략의 구조적 한계. 다만 이번에는 breakout_momentum에 집중하고 rsi_mr은 다음 이터레이션에서 다룸.

---

## 3. Panel Analysis

### Strat-4 (Data Analyst) -- Exit Structure 정량 분석

**핵심 발견: TP 4.0 ATR은 7일 보유 기간 내에 도달이 사실상 불가능하다.**

수치적 증거:
- P1 (강한 상승장): TP hit 0회 / 38 trades = 0%
- P2 (혼합장): TP hit 1회 / 45 trades = 2.2%
- 두 기간 합산: TP hit 1회 / 83 trades = **1.2%**

trailing_stop도 마찬가지:
- P1: trailing hit 0회 / 38 trades = 0%
- P2: trailing hit 3회 / 45 trades = 6.7%
- 합산: trailing hit 3회 / 83 trades = 3.6%

**이것은 무엇을 의미하는가?**

breakout_momentum 전략이 7일 내에 4.0 ATR를 올라가는 일은 거의 발생하지 않는다. trailing activation 1.5 ATR도 P1에서는 한 번도 도달하지 못했다. 이는 다음을 의미한다:

1. 진입 후 가격이 유리한 방향으로 1.5 ATR도 움직이지 않음 (P1)
2. 따라서 승리한 트레이드조차 이익 규모가 매우 작음 (time_exit으로 소폭 이익)
3. SL 2.0 ATR은 비교적 쉽게 도달 (53% hit rate)
4. **Risk:Reward 비대칭이 역방향**: SL은 자주 도달하고, TP는 거의 도달하지 않음

**Expected Value 계산 (P1 breakout_momentum):**

승리 시 평균 이익을 추정하면 (TP 미도달이므로 time_exit 기준):
- 승리: 18건 중 대부분이 time_exit, 평균 이익 ~0.5-1.0 ATR
- 패배: 20건이 SL at 2.0 ATR
- EV = 0.474 * 0.75 ATR - 0.526 * 2.0 ATR = 0.36 - 1.05 = **-0.69 ATR per trade**

P2에서도:
- 승리 평균 ~0.8 ATR (TP 거의 없으므로)
- 패배: 19건 SL at 2.0 ATR
- EV = 0.667 * 0.8 - 0.333 * 2.0 = 0.53 - 0.67 = **-0.14 ATR per trade**

P2에서 PF가 1.33이지만 per-trade EV는 여전히 빈약하다. 수익은 높은 WR과 position sizing에서 나올 뿐, 구조적으로 건강하지 않다.

### Strat-1 (Swing Trader) -- 구조적 진단

**breakout_momentum이 강한 상승장(P1)에서 실패하는 근본 원인:**

역설적으로 보이지만, 설명은 간단하다:

1. **상승장에서 브레이크아웃은 빈번하지만 지속력이 부족하다.** 모든 종목이 올라가는 장에서 10일 신고가 돌파는 흔한 이벤트이다. 이 중 상당수는 단기 오버슈팅 후 정상 풀백(1-2 ATR)이 동반된다.

2. **SL 2.0 ATR이 정상 풀백에 걸린다.** 상승장에서 ATR이 확대되어도, 2.0 ATR 풀백은 "정상적인 건전한 조정"의 범위 안에 있다. 진입 직후 1-3일 이내에 이 수준의 풀백이 발생하면 SL에 걸린다.

3. **TP 4.0 ATR은 비현실적이다.** 7일이라는 짧은 보유 기간에 4.0 ATR 상승은 대형주(S&P 500)에서 매우 드문 이벤트이다. 일평균 ATR이 2-3% 수준이면, 4.0 ATR = 8-12% 상승을 7일 내에 달성해야 한다. 이는 어닝 서프라이즈 급의 이벤트 없이는 불가능하다.

4. **trailing activation 1.5 ATR도 높다.** P1에서 trailing이 한 번도 활성화되지 않았다는 것은 진입 후 가격이 1.5 ATR(3-4.5%) 이상 유리한 방향으로 움직이는 일 자체가 7일 내에 드물다는 뜻이다.

**결론: 이 전략은 "큰 수익을 노리되 자주 잃는" 구조인데, 큰 수익이 실현되지 않으니 "자주 잃기만 하는" 전략이 되었다.**

### Strat-2 (Quant Analyst) -- 파라미터 재설계

**TP 목표 수준 교정:**

S&P 500 대형주의 일일 변동 특성:
- 평균 일 변동폭: ~1.5-2.5% (대략 1 ATR)
- 7일간 유리한 방향 최대 이동 (현실적): 2-3 ATR
- 10일간 유리한 방향 최대 이동 (현실적): 3-4 ATR

TP 4.0 ATR은 7일 보유에서 **97%의 확률로 도달 불가**한 수준이다.

**권고 파라미터:**

| Parameter | Current | Proposed | Rationale |
|-----------|---------|----------|-----------|
| TP | 4.0 ATR | 2.5 ATR | 7일 내 도달 가능한 현실적 수준. 대형주 weekly range의 상단 |
| Trailing Activation | 1.5 ATR | 1.0 ATR | 1 ATR 이동 후 즉시 이익 보호 시작. P1에서 0회였던 것이 활성화 기대 |
| SL | 2.0 ATR | 2.5 ATR | 정상 풀백(1.5-2 ATR)을 수용. whipsaw 스톱아웃 감소 |

**왜 이 3개인가?**

1. TP 2.5 ATR: 가격이 진입 후 2.5 ATR 상승하면 이익 실현. 현재 대부분 time_exit(소폭 이익)으로 나가는 것을 TP hit(풀 이익)으로 전환
2. Trailing 1.0 ATR: 가격이 1.0 ATR만 올라가도 trailing 시작. 최고가에서 2.0 ATR 풀백 시 exit. 이익을 보호하면서 추가 상승 여지 확보
3. SL 2.5 ATR: 진입 직후 정상 풀백(1-2 ATR)에서 스톱아웃 되는 것을 방지. 0.5 ATR 여유가 "노이즈 필터"

**Expected Value 개선 예측 (P1):**

개선 후 예상 시나리오:
- SL hit 감소: 53% -> ~35% (0.5 ATR 여유로 약 18%p 감소 추정)
- TP hit 증가: 0% -> ~10-15% (2.5 ATR은 도달 가능)
- Trailing hit 증가: 0% -> ~15-20% (1.0 ATR activation으로 활성화)
- Time exit: 47% -> ~30-40%

새 EV 추정:
- 승리: ~65% (WR 개선), 평균 이익 ~1.5 ATR (TP 2.5와 trailing mix)
- 패배: ~35%, 평균 손실 ~2.5 ATR (SL 확대)
- EV = 0.65 * 1.5 - 0.35 * 2.5 = 0.975 - 0.875 = **+0.10 ATR per trade**

현재 -0.69 ATR에서 +0.10 ATR로 개선이면, 38 trades * 0.79 ATR 개선 = 약 30 ATR 분량의 개선.

### Strat-3 (Risk Manager) -- 리스크 관점 검증

**SL 확대(2.0 -> 2.5 ATR)의 위험:**

| 우려 | 평가 | 판단 |
|------|------|------|
| 단일 트레이드 손실 증가 | +25% (2.0 -> 2.5 ATR) | position sizing으로 상쇄 가능 |
| MaxDD 증가 | 이론적으로 가능 | portfolio heat 25%로 제한됨 |
| 연속 손실 시 자본 소진 | medium risk | GDR tier 1(2.5% DD)에서 리스크 50% 감소 |

**SL 확대는 position sizing 조정으로 상쇄해야 하는가?**

아니다. 현재 base_risk 1.5%에서 SL 2.5 ATR이면 position size는 자동으로 줄어든다 (qty = risk / SL_distance). SL이 넓어지면 주당 위험금액이 커지지만 수량이 줄어서 총 위험금액은 동일하게 유지된다. 이것이 ATR-based sizing의 자동 조절 효과이다.

**TP 축소(4.0 -> 2.5 ATR)의 위험:**

| 우려 | 평가 | 판단 |
|------|------|------|
| 큰 수익 기회 상실 | 이론상 가능 | 현실에서 4.0 ATR은 1.2%만 달성. 상실할 기회 자체가 없음 |
| Trailing이 TP 대체 | 가능 | Trailing activation 1.0 ATR + trail 2.0 ATR = 이론적 최대 수익 무제한 |

**최종 리스크 평가: 수용 가능.** 현재 구조가 더 위험하다 (확실한 손실 vs. 이론적 이익).

---

## 4. P1 전체 손실의 근본 원인 진단

### 왜 강한 상승장에서 모든 전략이 실패하나?

| 전략 | P1 실패 원인 | 구조적 vs 파라미터 |
|------|-------------|-------------------|
| breakout_momentum | TP 비현실적, SL too tight, 정상 풀백에서 스톱아웃 | **파라미터** (이번에 수정) |
| rsi_mean_reversion | 트렌드 환경에서 역방향 진입, regime_guard 불충분 | **구조적** (다음 이터레이션) |
| consecutive_down | 강한 하락 후 반등 전략이 트렌드 중 dip buying에 적합하나, SL에서 일부 손실 | **파라미터** (근접 손익분기, 보류) |

**종합 진단:**

P1 손실의 60%는 rsi_mean_reversion(-$3,335)에서 발생한다. 이 전략은 트렌드 시장에서 구조적으로 부적합하지만, regime_guard가 충분히 차단하지 못하고 있다.

breakout_momentum(-$2,788)은 트렌드 시장에서 작동해야 하는 전략임에도 불구하고 손실을 기록했다. 이것은 순수 파라미터 문제이며, exit 구조(TP/SL/trailing)를 현실적으로 조정하면 개선 가능하다.

consecutive_down(-$483)은 거의 손익분기에 도달했으며, 현재 파라미터로 충분히 안정적이다.

---

## 5. Iteration 6 제안서

### 변경 사항 (3개 파라미터, breakout_momentum 전용)

| # | Parameter | Current | Proposed | File | Line |
|---|-----------|---------|----------|------|------|
| 1 | TP ATR multiplier | 4.0 | 2.5 | `exit_rules.py` | L57 |
| 2 | Trailing activation | 1.5 ATR | 1.0 ATR | `exit_rules.py` | L68 |
| 3 | SL ATR multiplier | 2.0 | 2.5 | `exit_rules.py` | L49 |

### 변경하지 않는 것 (그리고 이유)

| Parameter | 현재값 | 변경 안 함 이유 |
|-----------|--------|---------------|
| max_hold | 7일 | TP가 낮아지면 7일 내 도달 확률 증가. time_exit 비율 자연 감소 예상. 동시에 변경하면 인과관계 파악 불가 |
| rsi_mr 파라미터 | - | breakout_momentum과 동시 변경 시 어느 변경이 효과를 냈는지 구분 불가. 다음 이터레이션에서 별도 처리 |
| cons_down 파라미터 | - | P2에서 PF 4.626으로 최고 성과. P1에서도 근접 손익분기. 건드릴 이유 없음 |
| GDR thresholds | - | 현재 구조 적절. exit 파라미터 변경 후 GDR 효과 재평가 필요 |
| portfolio heat | 25% | MaxDD 16.9%(P2)로 이미 양호. heat 조정은 exit 구조 확정 후 |

### 각 변경의 근거와 예상 효과

**변경 1: TP 4.0 -> 2.5 ATR**

근거:
- 83건 중 TP 달성 1건(1.2%). 이론상 존재하지만 실질적으로 죽은 exit path
- 4.0 ATR = S&P 500 종목이 7일간 8-12% 상승 필요. 어닝 없이 불가능
- 2.5 ATR = 5-7.5% 상승. 강한 브레이크아웃 시 충분히 가능한 수준

예상 효과:
- TP hit rate: 1.2% -> 10-15%
- 승리 트레이드의 평균 수익 증가 (time_exit의 소폭 이익 -> TP의 2.5 ATR 이익)
- PF 개선: 특히 P1에서 0.759 -> 0.9-1.1 예상

**변경 2: Trailing Activation 1.5 -> 1.0 ATR**

근거:
- P1에서 trailing activation 0회. 가격이 1.5 ATR 유리한 방향으로 움직이지 않음
- 1.0 ATR은 대형주의 2-3일 정상 움직임 범위. 달성 확률 높음
- Trailing이 활성화되면 추가 상승분 캡처 + 하락 시 이익 보호

예상 효과:
- Trailing hit rate: 3.6% -> 15-20%
- "이기고 있는 트레이드"의 이익을 지키는 역할
- time_exit으로 소폭 이익 또는 소폭 손실로 끝나는 트레이드가 trailing으로 적정 이익 확보

**변경 3: SL 2.0 -> 2.5 ATR**

근거:
- SL hit rate이 42-53%로 가장 빈번한 exit
- 2.0 ATR 풀백은 건전한 조정 범위. 진입 직후 1-2일의 정상 변동에서 스톱아웃
- 0.5 ATR 여유가 "노이즈 필터" 역할
- ATR-based position sizing으로 인해 SL이 넓어져도 총 위험금액은 동일

예상 효과:
- SL hit rate: 42-53% -> 30-40% (약 12%p 감소)
- 일부 트레이드가 SL 대신 TP/trailing/time_exit으로 전환
- WR 개선: 특히 P1에서 47.4% -> 55-60% 예상

---

## 6. Risk Assessment

### 변경의 위험 분석

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SL 확대로 개별 손실 증가 | Low | Low | ATR-based sizing이 자동 조절. 수량 감소로 총 위험 동일 |
| TP 축소로 대형 수익 상실 | Low | Low | 현재 대형 수익 자체가 없음(1.2% hit rate). 상실할 것이 없음 |
| 3개 동시 변경으로 인과관계 혼동 | Medium | Medium | 3개 모두 동일 전략의 exit 구조를 개선하는 방향. 개별 효과보다 시너지가 중요 |
| P2 성과 하락 | Low | Medium | P2에서도 TP hit 2.2%로 현재 TP가 무의미. 변경이 P2를 악화시킬 이유 없음 |
| 오버피팅 우려 | Low | Low | 표준적인 ATR 배수 조정. 전략 논리 변경 아님 |

### Overfitting Assessment

| Change | Overfitting Risk | Rationale |
|--------|-----------------|-----------|
| TP 4.0 -> 2.5 | Very Low | 도달 불가능한 값을 현실적 수준으로 조정. 커브 피팅 아닌 상식적 교정 |
| Trailing 1.5 -> 1.0 | Very Low | 활성화되지 않는 기능을 활성화. 기능 자체의 작동 여부 개선 |
| SL 2.0 -> 2.5 | Low | S&P 500 대형주의 정상 변동폭을 반영. 시장 특성 기반 조정 |

---

## 7. Iteration 6 목표

### 성공 기준

| Metric | P1 Target | P2 Target | Rationale |
|--------|-----------|-----------|-----------|
| breakout_momentum PF | > 1.0 | > 1.5 | 현재 0.759/1.331 -> exit 구조 개선 효과 |
| breakout_momentum TP hit | > 5% | > 10% | 현재 0%/2.2% -> 현실적 TP 도달 확인 |
| breakout_momentum SL hit | < 45% | < 35% | 현재 53%/42% -> SL 확대 효과 확인 |
| Total Return | > -3% | > +10% | 점진적 개선 |
| Sharpe | > 0.2 | > 0.5 | 점진적 개선 |

### 관찰 포인트

1. **trailing_stop hit rate 변화**: 0%/6.7% -> 15%+ 예상. 미달성 시 activation 추가 조정 필요
2. **time_exit 비율 변화**: 47% -> 30% 이하 예상. TP/trailing으로 전환되어야 함
3. **P1 breakout_momentum PnL**: -$2,788 -> $0 이상 (손익분기 이상)
4. **rsi_mean_reversion 불변 확인**: 파라미터 미변경이므로 유사한 결과 예상

---

## 8. 향후 로드맵

### Iteration 7+ 예상 과제

| Priority | Task | Category |
|----------|------|----------|
| P0 | rsi_mean_reversion TREND regime 차단 강화 | STRUCTURAL |
| P1 | max_hold 조정 검토 (Iter 6 결과에 따라) | PARAM_TUNE |
| P2 | portfolio heat 최적화 | PARAM_TUNE |
| P3 | breakout_momentum short 방향 추가 검토 | NEW_FEATURE |

### 목표까지의 거리 분석 (Strat-2)

현재 최선 결과 vs 목표:

| | P1 Best | P1 Target | Gap | P2 Best | P2 Target | Gap |
|--|---------|-----------|-----|---------|-----------|-----|
| Sharpe | 0.073 | 1.0 | 0.927 | 0.414 | 1.0 | 0.586 |
| Calmar | -0.283 | 1.0 | 1.283 | 0.540 | 1.0 | 0.460 |

솔직한 평가: breakout_momentum exit 구조 개선만으로는 목표 달성이 어렵다. rsi_mean_reversion의 P1 손실($3,335) 제거가 반드시 동반되어야 한다. 이번 Iteration 6에서 breakout을 개선하고, Iteration 7에서 rsi_mr regime filter를 강화하는 2단계 접근이 현실적이다.

---

## 9. Panel Vote

| Team Member | Vote | Rationale |
|-------------|------|-----------|
| Strat-1 (Swing) | APPROVE | "exit 구조가 비현실적이었다. TP 2.5와 trailing 1.0은 대형주 breakout의 실제 움직임과 일치한다." |
| Strat-2 (Quant) | APPROVE | "EV 계산상 현재 구조는 음수. 세 파라미터 변경으로 EV를 양수로 전환할 수 있다." |
| Strat-3 (Risk) | APPROVE | "SL 확대의 리스크는 ATR sizing으로 자동 상쇄된다. 순수 리스크 증가 없음." |
| Strat-4 (Data) | APPROVE | "83건의 데이터가 현재 exit 구조의 실패를 명확히 보여준다. 변경은 데이터 기반 교정이다." |

**만장일치: 3개 파라미터 변경 승인**

---

## 10. Implementation Spec (개발팀 핸드오프)

### 코드 변경 사항

**File: `autotrader/execution/exit_rules.py`**

```python
# Line 49: SL ATR multiplier
_SL_ATR_MULT: dict[str, dict[str, float]] = {
    ...
    "breakout_momentum": {"long": 2.5},    # WAS 2.0
}

# Line 57: TP ATR multiplier
_TP_ATR_MULT: dict[str, float | None] = {
    ...
    "breakout_momentum": 2.5,              # WAS 4.0
}

# Line 68: Trailing activation
_TRAILING_ACTIVATION_ATR: dict[str, float] = {
    ...
    "breakout_momentum": 1.0,              # WAS 1.5
}
```

**변경 파일 수**: 1개 (`exit_rules.py`)
**변경 라인 수**: 3개
**테스트 영향**: ExitRuleEngine 관련 테스트에서 breakout_momentum 파라미터 참조하는 테스트 업데이트 필요

---

*Panel discussion concluded. Iteration 6 파라미터 변경 승인. 개발팀 구현 대기.*
