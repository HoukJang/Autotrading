# Strategy Panel Discussion #26: Iteration 14 Review -- BM-Only Portfolio Signal Flood 진단

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant), Strat-3 (Risk Manager), Strat-4 (Data Analyst)
**Context**: Iteration 14 -- MR 제거 후 BM-only 포트폴리오 첫 백테스트. 거래 수 급증(15->65) 및 수익 붕괴 진단.
**Verdict**: **STRUCTURAL FIX REQUIRED -- BM 엔트리 필터 강화 + 포지션 캡 복원 필수**

---

## 1. Backtest Results Summary

### Period 2 (2025-03 ~ 2026-02, S&P 500 +15.5%)

| Metric | Iter 12 BM | Iter 14 BM | Delta |
|--------|-----------|-----------|-------|
| Trades | 15 | **65** | **+50 (+333%)** |
| WR | 73.3% | 58.5% | -14.8%p |
| PF | 5.959 | **0.804** | **-5.155** |
| PnL | +$4,583 | **-$2,102** | **-$6,685** |
| MaxDD | ~15% (est.) | 6.8% | - |
| AvgHold | ~8.4d | 7.8d | -0.6d |
| Exit: SL | ~53% | **60%** | +7%p |
| Exit: TS | ~33% | 32% | -1%p |
| Exit: TP | ~7% | **3%** | -4%p |

### Period 1 (2024-03 ~ 2025-02, S&P 500 +15.9%)

| Metric | Iter 12 BM | Iter 14 BM | Delta |
|--------|-----------|-----------|-------|
| Trades | 13 | **49** | **+36 (+277%)** |
| WR | 76.9% | 51.0% | **-25.9%p** |
| PF | 13.729 | **0.543** | **-13.186** |
| PnL | +$2,690 | **-$5,501** | **-$8,191** |
| MaxDD | ~10% (est.) | 5.6% | - |
| AvgHold | ~7.2d | 7.5d | +0.3d |
| Exit: SL | ~62% | **69%** | +7%p |
| Exit: TS | ~31% | 29% | -2%p |
| Exit: TP | ~8% | **0%** | **-8%p** |

### Iteration History (Updated)

| Iter | P2 Return | P1 Return | P2 Trades | P2 PF | Key Change |
|------|-----------|-----------|-----------|-------|------------|
| 11 | +11.0% | -1.1% | 56 (3-strat) | - | Static baseline |
| 12 | +5.4% | +2.9% | 56 (BM:15+MR:39) | BM:5.959 | 2-strat + regime |
| 13 | +5.1% | -3.9% | 55 (BM:15+MR:40) | BM:5.959 | MR tuning (worse) |
| 14 | **-2.0%** | **-5.4%** | **65 (BM only)** | **0.804** | MR removed, signal flood |

---

## 2. Panel Discussion

### Strat-1 (Swing Trader) -- Signal Flood의 메커니즘 분석

"이번 결과는 MR 제거의 1차 효과(나쁜 전략 제거)와 2차 효과(암묵적 필터 제거)가 충돌한 전형적인 사례다. 우리는 1차 효과만 예상했고 2차 효과를 완전히 간과했다.

**암묵적 필터 메커니즘 (Iter 12에서 작동하던 것)**:

`batch_simulator.py` line 910을 보면:
```python
multi_strategy_mode = len(strategies_with_signals) >= 2
```

Iter 12에서는 BM + MR 두 전략이 모두 시그널을 생성했으므로 `multi_strategy_mode = True`였다. 이때 두 가지 필터가 작동했다:

1. **_SOFT_STRATEGY_CAP = 2**: BM이 동시에 2개 포지션까지만 보유 가능. 이것이 가장 강력한 필터였다. 동시에 2개 포지션만 유지하면, 기존 포지션이 청산될 때까지 새 진입이 차단된다. AvgHold ~8일이면 8일마다 2개 슬롯이 비는 것이므로, 12개월에 약 (252/8)*2 = 63개 이론적 최대이지만, 시그널 발생 빈도와 결합하면 실제로는 15-17개 정도만 통과.

2. **랭킹 경쟁**: MR 시그널과 BM 시그널이 composite score로 경쟁. MR이 많은 시그널(39건)을 생성하면서 TOP_N=12 안에서 약한 BM 시그널을 밀어냈다. Strategy diversity bonus(+0.25)가 있지만, MR 시그널이 워낙 많아서 약한 BM 시그널은 TOP_N 밖으로 밀려남.

**Iter 14에서 이 필터들이 모두 사라진 결과**:

MR 제거 -> `len(strategies_with_signals) = 1` -> `multi_strategy_mode = False` -> **_SOFT_STRATEGY_CAP 미적용**. BM은 이제 `_MAX_TOTAL_POSITIONS = 5`까지 자유롭게 진입 가능. 랭킹에서도 경쟁 없이 TOP_N=12개 시그널이 모두 BM이므로, 매일 최대 3개(`_MAX_DAILY_ENTRIES`)까지 진입.

**추가된 50개 거래의 프로파일**:

Iter 12에서 15개가 통과했고 Iter 14에서 65개가 통과했으니, 추가 50개는 랭킹 하위/캡 초과 시그널이다. 이들의 공통 특성을 추정하면:
- ADX 25-30 (borderline trend) -- 강한 추세가 아닌 약한 추세에서의 breakout
- volume_ratio 1.2-1.4 -- 최소 기준만 간신히 통과
- signal_strength 0.10-0.25 -- 하위 25%

스윙 트레이더 관점에서, ADX 25-30 구간의 breakout은 'false breakout 지뢰밭'이다. ADX 25는 추세의 시작도 끝도 아닌 경계 지점이며, 이 구간에서 10일 신고가 돌파는 노이즈일 확률이 매우 높다.

**핵심 처방**: `_SOFT_STRATEGY_CAP`의 역할을 복원하되, multi_strategy_mode 의존성을 제거해야 한다. BM-only여도 동시 보유 포지션 수를 제한하는 구조적 캡이 필요하다."

### Strat-2 (Quant) -- 수학적 분석: 시그널 품질 분포와 필터 최적화

"수학적으로 이번 현상을 분석하겠다. 핵심은 **시그널 품질 분포의 꼬리(tail)가 노출된 것**이다.

**시그널 강도 분포 추정**:

BM의 signal strength 공식:
```
adx_score = min(0.5, (ADX - 25) / 50)
vol_score = min(0.5, (vol_ratio - 1.0) * 0.5)
strength = min(1.0, adx_score + vol_score)
```

| ADX | Vol Ratio | ADX Score | Vol Score | Strength | Quality Tier |
|-----|-----------|-----------|-----------|----------|-------------|
| 45+ | 2.0+ | 0.40+ | 0.50 | 0.90+ | A (excellent) |
| 35-45 | 1.5-2.0 | 0.20-0.40 | 0.25-0.50 | 0.45-0.90 | B (good) |
| 30-35 | 1.3-1.5 | 0.10-0.20 | 0.15-0.25 | 0.25-0.45 | C (marginal) |
| 25-30 | 1.2-1.3 | 0.00-0.10 | 0.10-0.15 | 0.10-0.25 | D (poor) |

**Iter 12 BM P2** (15 trades): 캡과 랭킹이 Tier A+B만 통과시킴
**Iter 14 BM P2** (65 trades): Tier A+B+C+D 모두 통과

추가된 50개 trades의 대부분이 Tier C+D라고 가정하면:
- 원래 15 trades (Tier A+B): PnL +$4,583, WR 73.3%, PF 5.959
- 추가 50 trades (Tier C+D 추정): PnL = -$2,102 - (+$4,583 추정) = **-$6,685**
- 추가 50 trades의 추정 WR: ~54%, 추정 PF: ~0.35

**이것은 명확한 결론이다: Tier C+D 시그널의 기대값은 강하게 음수(-$134/trade).**

**BM TP 5.0 ATR 문제**:

현재 exit_rules.py에서 BM의 TP는 5.0 ATR이다. 동시에 trailing stop 활성화는 1.0 ATR, trailing 거리는 2.0 ATR이다. 수학적으로:

```
TP 도달 조건: price >= entry + 5.0 * ATR (연속적 상승 필요)
Trailing 활성화: price >= entry + 1.0 * ATR (첫 수익 구간에서 즉시 활성화)
Trailing exit: price <= highest - 2.0 * ATR
```

TP에 도달하려면 가격이 entry+1.0 ATR 이후 한 번도 2.0 ATR 이상 하락하지 않고 5.0 ATR까지 올라가야 한다. 이것은 사실상 4.0 ATR의 연속 상승이 필요하며, 10-day breakout 종목의 일봉 데이터에서는 극히 드문 이벤트다.

**TP를 3.5 ATR로 내리면**: entry+1.0 ATR 활성화 후 2.5 ATR 추가 상승이면 충분. 실현 가능성이 대폭 증가한다.

또한 trailing 활성화를 1.0 -> 1.5 ATR로 올리면:
- 초기 노이즈에 의한 조기 trailing exit 방지
- 트렌드가 좀 더 확립된 후 trailing 시작
- 평균 승리 크기 증가 기대

**필터 최적화 제안 (수학적 근거)**:

1. **ADX_MIN 25 -> 30**: ADX 25-30 구간은 'trend developing' 단계. breakout 전략은 'trend established'(ADX 30+)에서 edge가 있다. 이것은 과적합이 아니라 기술적 분석의 기본 원칙이다. Wilder의 원래 ADX 해석에서도 30+를 'strong trend'로 분류한다.

2. **VOL_RATIO_MIN 1.2 -> 1.5**: 1.2x는 일상적 변동 범위 내. 1.5x는 통계적으로 의미 있는 거래량 급증(대략 2 표준편차). breakout의 유효성을 확인하는 최소 기준으로 1.5x가 문헌에서 더 널리 사용된다.

3. **BREAKOUT_LOOKBACK 10 -> 20**: 10일 신고가는 2주일의 가격 범위에 불과. 20일(1개월) 신고가 돌파는 Donchian Channel의 기본 설정이며, 더 의미 있는 기술적 수준이다. 10일 범위에서는 일시적 노이즈에 의한 false breakout이 빈번하다.

**예상 거래 수 감소 효과**:
- ADX 25->30: ~35-40% 시그널 감소 (ADX 분포 기반 추정)
- VOL 1.2->1.5: ~20-25% 추가 감소
- Lookback 10->20: ~25-30% 추가 감소
- 복합 효과 (중복 제외): 원래 65 trades의 약 50-60% 감소 -> **25-35 trades 예상**
- 포지션 캡(3)과 결합하면: **20-30 trades**로 수렴

이 범위가 통계적으로 유의미한 결과를 낼 수 있는 최소 거래 수(>20)를 유지하면서, Iter 12의 15건보다는 충분히 많다."

### Strat-3 (Risk Manager) -- 포지션 관리 구조 및 리스크 예산

"MaxDD 6.8%(P2)과 5.6%(P1)은 이전 이터레이션들의 30%+에 비하면 대폭 개선되었다. 하지만 이것은 MR 제거의 효과일 뿐, BM-only가 잘 작동한다는 의미는 아니다. **PnL이 음수인데 MaxDD가 낮다는 것은, 큰 손실 한 방이 아니라 작은 손실의 반복적 누적**이라는 뜻이다.

**리스크 구조 분석**:

현재 BM의 position sizing:
- Regime-based risk: TREND_UP 2.5%, RANGING 0.8%, etc.
- SL distance: 2.5 ATR
- qty = (equity * risk_pct) / (SL_mult * ATR)

$100K 계좌, 주가 $200, ATR $5 기준:
- TREND_UP: risk = $100K * 0.025 = $2,500, qty = $2,500 / ($5 * 2.5) = 200주 ($40,000 포지션)
- RANGING: risk = $100K * 0.008 = $800, qty = $800 / $12.5 = 64주 ($12,800 포지션)

**_MAX_TOTAL_POSITIONS = 5 + _MAX_DAILY_ENTRIES = 3의 문제**:

5개 동시 포지션 * TREND_UP 각 $40,000 = $200,000 = 계좌의 200%. 물론 _MAX_POSITION_PCT = 0.20이 20%로 제한하지만, 5개 * 20% = 100%까지 가능하다. BM-only에서 5개 모멘텀 포지션은 모두 상관관계가 높다(시장 방향에 동시에 노출). 시장 급락 시 5개가 동시에 SL을 맞으면 5 * 2.5% = 12.5% 계좌 손실이 하루에 발생할 수 있다.

**포지션 캡 복원 필요성**:

| Config | Current | Proposed | 근거 |
|--------|---------|----------|------|
| _MAX_TOTAL_POSITIONS | 5 | **3** | BM-only 상관 리스크 제어 |
| _MAX_DAILY_ENTRIES | 3 | **2** | 진입 속도 제어 |
| _MAX_LONG_POSITIONS | 4 | **3** | BM은 long-only이므로 이것이 실질 캡 |

3 동시 포지션 * TREND_UP 각 2.5% risk = 최대 7.5% 동시 리스크. 이것은 허용 범위 내다.

**추가 안전장치: BM max_hold_days 설정**

현재 BM은 `_MAX_HOLD_DAYS`에 등록되어 있지 않아 시간 제한이 없다. exit_rules.py line 37-42를 보면 BM이 빠져 있다. 이것은 설계 결함이다.

breakout이 실패하면 가격은 SL까지 천천히 하락하거나, EMA(21) 아래로 가서 전략 내부의 trend_loss exit을 트리거해야 한다. 하지만 **전략 내부 exit 시그널이 batch_simulator에서 제대로 처리되는지가 이전 Panel #24에서도 의문이 제기된 바 있다**. 전략의 `_check_exit()`이 `direction='close'` 시그널을 반환하더라도, batch_simulator의 _scan_signals에서 line 814: `if signal is None or signal.direction == 'close': continue`로 무시된다.

즉, BM의 trend_loss exit(EMA(21) 아래 2연속 종가)이 실제로 batch simulator에서 작동하지 않을 가능성이 있다. 이 경우 SL이나 trailing stop만이 exit 메커니즘이 되며, 이것이 SL 60%+ 비율의 또 다른 원인일 수 있다.

**MAX_HOLD_DAYS = 12일을 BM에 추가해야 한다.** 12일은 평균 보유(7.8일)의 약 1.5배로, 정상 거래에는 영향을 주지 않으면서 좀비 포지션을 정리한다.

**RANGING 할당 추가 감소 필요**:

현재 RANGING BM 할당 0.008(0.8%)도 BM이 RANGING에서 edge가 없다는 것을 Iter 12-13 데이터가 보여줬다. RANGING에서의 breakout은 대부분 false breakout이다. 0.005(0.5%)로 추가 감소하거나, RANGING에서도 breakout_blocked = True를 검토할 수 있다.

그러나 RANGING에서 완전 차단은 과적합 위험이 있다. RANGING -> TREND_UP 전환 초기에 breakout이 발생할 수 있고, 이런 전환 시점의 breakout이야말로 가장 수익성이 높은 셋업이다. 0.005로 최소화하되 완전 차단은 하지 않는 것이 합리적이다."

### Strat-4 (Data Analyst) -- Exit 패턴 심층 분석 및 코드 검증 이슈

"데이터를 정밀하게 분석하겠다.

**Exit 분포 비교 (Iter 12 vs Iter 14, P2 BM)**:

| Exit Reason | Iter 12 (17 trades) | Iter 14 (65 trades) | Delta |
|-------------|-------------------|-------------------|-------|
| stop_loss | 9 (52.9%) | 39 (60.0%) | +7.1%p |
| trailing_stop | 5 (29.4%) | 21 (32.3%) | +2.9%p |
| take_profit | 1 (5.9%) | 2 (3.1%) | -2.8%p |
| forced_close | 2 (11.8%) | 3 (4.6%) | -7.2%p |

**관찰 1: SL rate 증가의 원인 분해**

Iter 12에서 9/17 = 52.9% SL은 이미 높지만, WR 70.6%이므로 SL exit 중 일부는 수익 거래(2-stage SL upgrade로 breakeven 이상에서 SL)다. 9건 SL 중 추정 3-4건은 Stage 1(breakeven) 또는 Stage 2(profit lock)에서의 SL hit.

Iter 14에서 39/65 = 60% SL. WR 58.5%이므로 27건이 손실. 39건 SL 중 약 20-25건이 원래 SL(entry - 2.5*ATR)에서의 순손실, 나머지 14-19건이 BE/profit lock SL. **순손실 SL 비율이 30-38%에서 증가한 것이 핵심.**

**관찰 2: Trailing Stop은 건전하게 작동 중**

TS 비율은 29-32%로 안정적이다. 이것은 breakout 성공 시 trailing이 정상적으로 이익을 보호하고 있다는 의미. 문제는 TS가 아니라 SL이다.

**관찰 3: TP 5.0 ATR의 비현실성**

P1 Iter 14에서 TP 0건, P2에서 2건(3.1%). BM TP = 5.0 ATR은 exit_rules.py line 58에서 확인된다. Trailing이 1.0 ATR에서 활성화되고 2.0 ATR 거리로 추적하므로:

```
시나리오: 가격이 entry+3.0 ATR까지 상승 후 1.5 ATR 하락
- Trailing: 활성화 됨 (entry+1.0 ATR 돌파)
- Trail stop = (entry+3.0ATR) - 2.0ATR = entry+1.0ATR
- 가격 entry+1.5ATR에서 trail stop(entry+1.0ATR) > 현재가 -> 아직 미발동
- 가격이 더 떨어져 entry+1.0ATR -> trail stop hit -> trailing_stop exit
- TP(entry+5.0ATR)에 도달하지 못함
```

사실상 TP 5.0 ATR에 도달하려면 entry 이후 한 번도 2.0 ATR 이상의 조정(pullback) 없이 5.0 ATR을 달성해야 한다. 이것은 개별 주식의 10-20일 보유 기간에서 극히 희귀한 이벤트다.

**TP를 3.5 ATR로 내리면**:
- entry+1.0 ATR trailing 활성화 후 2.5 ATR 추가 상승이면 TP 도달
- Trailing은 이 과정에서 pullback 2.0 ATR 이상이면 먼저 발동
- 3.5 ATR 도달 확률은 5.0 ATR 대비 상당히 높음
- 예상 TP rate: 5-10% (현재 3%에서 개선)

**관찰 4: Forced Close 의미**

FC 3건(P2)은 레짐 전환에 의한 강제 청산이다. 이것은 정상 작동이며 문제가 아니다. 오히려 TREND_DOWN 전환 시 수익을 보호하는 기능이다.

**관찰 5: BM 전략 내부 Exit 처리 문제 (재확인)**

Panel #24에서 제기된 이슈가 여전히 미해결이다. BM의 `_check_exit()`은 `trend_loss` 신호를 반환하지만, batch_simulator의 exit 평가 루프에서 전략 내부 exit을 호출하는 경로가 명확하지 않다.

`_scan_signals()`(line 807-826)에서 전략을 호출하지만, 이때 이미 포지션이 열린 심볼은 line 797에서 skip된다:
```python
if sym in self._positions:
    continue
```

즉, 이미 보유 중인 심볼에 대해서는 전략의 on_context()가 호출되지 않으므로, **BM의 trend_loss exit은 batch simulator에서 실행되지 않는다.** Exit은 전적으로 ExitRuleEngine의 SL/TP/Trailing/Time에 의존한다.

이것은 BM에 time exit이 없는 현재 구조에서, 실패한 breakout이 SL(-2.5 ATR)까지 느리게 하락하는 동안 자본이 묶이는 원인이 된다. **BM의 trend_loss exit(EMA21 아래 2연속 종가)은 SL 도달 전에 포지션을 정리하는 중요한 안전장치인데, 현재 작동하지 않고 있다.**

다만, 이 이슈 수정은 코드 변경이 필요하므로 이번 패널의 파라미터 제안 범위를 넘어선다. 대안으로 MAX_HOLD_DAYS 설정이 유사한 보호를 제공할 수 있다."

---

## 3. 교차 진단 합의

### 만장일치 합의 (Unanimous Consensus)

#### 합의 1: Signal Flood의 근본 원인은 구조적 문제

**전원 동의. 반대 의견 없음.**

MR 제거로 `multi_strategy_mode`가 False가 되면서 `_SOFT_STRATEGY_CAP`이 비활성화된 것이 1차 원인. 랭킹 경쟁 소멸이 2차 원인. 이것은 BM 전략의 문제가 아니라, **시스템의 필터링 메커니즘이 단일 전략 모드를 고려하지 않은 설계 결함**이다.

#### 합의 2: 포지션 캡 + 엔트리 필터 동시 강화 필수

**전원 동의.**

두 가지 방어선이 모두 필요하다:
1. **포지션 캡(구조적 방어)**: 신호 품질과 무관하게 동시 리스크 제한
2. **엔트리 필터(품질 방어)**: 약한 시그널을 진입 전에 차단

#### 합의 3: BM 전략 내부 Exit 미작동 이슈 확인

**전원 동의.**

trend_loss exit이 batch simulator에서 실행되지 않는 것이 확인됨. MAX_HOLD_DAYS 설정으로 임시 보완하되, 근본 수정은 코드 레벨에서 별도 처리 필요.

### 이견 사항 (Debate)

#### 이견 1: BREAKOUT_LOOKBACK 10 -> 20 변경

- **Strat-2**: 20일로 변경 권고. Donchian Channel 표준이며, 10일 범위의 false breakout을 구조적으로 제거.
- **Strat-1**: 20일은 신호 빈도를 과도하게 줄일 수 있다. 15일이 절충안.
- **Strat-3**: 20일이 더 보수적이고 안전. 거래 수 감소는 오히려 긍정적.
- **Strat-4**: 두 기간 모두에서 효과를 보려면 극단적 변경보다 15일이 안전.
- **결정**: **20일 채택. 10일 신고가는 2주 범위에 불과하여 노이즈 breakout이 너무 많다. 20일(1개월)은 기술적 분석의 표준 기간이며 과적합이 아니다.**

#### 이견 2: RANGING에서의 BM 처리

- **Strat-3**: RANGING에서 breakout_blocked = True 검토 제안.
- **Strat-1**: RANGING -> TREND_UP 전환 초기 breakout을 포착하려면 완전 차단은 과잉. 할당 축소로 충분.
- **결정**: **RANGING 할당 0.008 -> 0.005로 축소. 완전 차단은 하지 않음.**

#### 이견 3: 변경 사항 적용 단위

- **Strat-2**: 모든 변경을 동시에 적용하여 복합 효과 측정.
- **Strat-4**: 변경이 많으면 어떤 것이 효과적인지 분리할 수 없다. 2단계로 분리 권고: 1단계(구조적 캡), 2단계(엔트리 필터).
- **Strat-1**: 현재 시스템이 -2.0%/-5.4% 손실 중이므로 빠른 수정이 필요. 동시 적용이 합리적.
- **결정**: **P1(캡 + 필터)를 동시 적용. 단, 개별 변경의 기대 효과를 문서에 명시하여 사후 분석 가능하도록 한다.**

---

## 4. 핵심 문제점과 근본 원인

### 문제 1: 단일 전략 모드에서의 시그널 필터 부재 (ROOT CAUSE)

**현상**: 거래 수 15 -> 65 급증, WR 73.3% -> 58.5%, PF 5.959 -> 0.804
**근본 원인**: `_SOFT_STRATEGY_CAP`이 `multi_strategy_mode=True`일 때만 작동하도록 설계됨. MR 제거로 single-strategy 모드가 되자 캡이 비활성화.
**영향**: 약한 Tier C+D 시그널 50개가 무필터로 진입, 추정 -$6,685 손실

### 문제 2: BM 엔트리 필터의 과도한 관대함 (CONTRIBUTING)

**현상**: ADX 25+, volume 1.2x, 10일 lookback이 너무 많은 시그널 허용
**근본 원인**: 이 파라미터들은 multi-strategy 환경에서 랭킹으로 걸러질 것을 전제로 설정됨. 단독 운영 시 과도하게 관대.
**영향**: Tier C+D 시그널의 진입 허용

### 문제 3: TP 5.0 ATR의 비현실성 (SECONDARY)

**현상**: TP 도달률 0-3%
**근본 원인**: Trailing stop(1.0 ATR 활성화, 2.0 ATR 거리)이 TP보다 먼저 발동
**영향**: 수익 거래의 이익 규모가 제한됨 (trailing이 캡처하는 이익 < TP 이익)

### 문제 4: BM 전략 내부 Exit 미작동 (STRUCTURAL)

**현상**: trend_loss exit이 batch simulator에서 실행되지 않음
**근본 원인**: 보유 중 심볼은 _scan_signals에서 skip됨 -> 전략 on_context() 미호출
**영향**: 실패한 breakout이 SL까지 느리게 하락하며 자본 묶임

---

## 5. 권고사항 (Prioritized)

### Priority 1 (CRITICAL): 포지션 캡 복원

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| _MAX_TOTAL_POSITIONS | batch_simulator.py | 5 | **3** | BM-only 상관 리스크 제어 |
| _MAX_DAILY_ENTRIES | batch_simulator.py | 3 | **2** | 진입 속도 제어 |
| _MAX_LONG_POSITIONS | batch_simulator.py | 4 | **3** | BM long-only 실질 캡 |

**예상 효과**: 동시 리스크 최대 7.5% (3 * 2.5%), 거래 수 상한 ~40-50으로 제한
**과적합 위험**: 없음 (구조적 리스크 관리, 데이터 의존성 없음)

### Priority 2 (CRITICAL): BM 엔트리 필터 강화

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| ADX_MIN | breakout_momentum.py | 25.0 | **30.0** | Wilder 'strong trend' 기준 |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | **1.5** | 의미 있는 거래량 급증 (~2 std dev) |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 10 | **20** | Donchian Channel 1개월 표준 |

**예상 효과**: 시그널 50-60% 감소, Tier C+D 시그널 대부분 차단
**과적합 위험**: 낮음 (기술적 분석 표준 값, 기간별 독립적)

### Priority 3 (HIGH): Exit 파라미터 최적화

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| BM TP ATR mult | exit_rules.py (_TP_ATR_MULT) | 5.0 | **3.5** | 현실적 목표, TP 도달률 5-10%로 개선 |
| Trailing activation | exit_rules.py (_TRAILING_ACTIVATION_ATR) | 1.0 | **1.5** | 조기 trailing 방지, 트렌드 확립 후 시작 |
| BM MAX_HOLD_DAYS | exit_rules.py (_MAX_HOLD_DAYS) | 없음 | **12** | 좀비 포지션 방지 + trend_loss exit 대체 |

**예상 효과**: 평균 승리 크기 증가, 좀비 포지션 제거
**과적합 위험**: 낮음 (trailing/TP 비율 조정, 기간 독립적)

### Priority 4 (MEDIUM): Regime 할당 미세 조정

| Regime | Current | Proposed | 근거 |
|--------|---------|----------|------|
| TREND_UP | 0.025 | **0.025** (유지) | BM 최적 조건 |
| TREND_DOWN | 0.005 (blocked) | **0.005 (blocked)** (유지) | 역추세 차단 |
| RANGING | 0.008 | **0.005** | False breakout 리스크 추가 축소 |
| HIGH_VOL | 0.005 | **0.005** (유지) | 이미 보수적 |
| UNCERTAIN | 0.012 | **0.008** | 불확실한 환경에서 보수적 운영 |

**예상 효과**: RANGING/UNCERTAIN에서의 false breakout 손실 20-30% 감소
**과적합 위험**: 낮음 (방향성은 전략 원리에 기반, 미세 조정 수준)

### Priority 5 (LOW): 최소 시그널 강도 설정

| Parameter | File | Current | Proposed | 근거 |
|-----------|------|---------|----------|------|
| MIN_SIGNAL_STRENGTH | batch_simulator.py (신규) | 없음 | **0.30** | Tier D 시그널 안전망 차단 |

**근거**: P2 엔트리 필터(ADX 30, VOL 1.5)와 중복되지만, 향후 파라미터 변경 시에도 최소 품질 보장하는 안전장치 역할.
**예상 효과**: P2 필터와 대부분 중복, 향후 안전망으로 기능
**과적합 위험**: 없음 (하한 설정은 구조적)

### 코드 수정 필요 사항 (별도 트래킹)

**[CODE-1] BM 전략 내부 Exit 미작동 수정**

batch_simulator의 exit 평가 루프에서 보유 중인 포지션에 대해 전략의 `on_context()`를 호출하고, `direction='close'` 시그널이 반환되면 포지션을 청산해야 한다. 이것은 ExitRuleEngine의 exit hierarchy 내에 통합되거나, 별도의 "strategy exit" 단계로 추가되어야 한다.

이 수정이 구현되면 BM의 trend_loss exit(EMA21 아래 2연속 종가)이 작동하여:
- 실패한 breakout의 조기 정리 (SL 도달 전 exit)
- SL rate 감소 예상 (60% -> 45-50%)
- 평균 손실 크기 감소

**현재 이터레이션에서는 MAX_HOLD_DAYS = 12로 임시 보완.**

---

## 6. 예상 성과 목표

### P1+P2 복합 목표

| Metric | Iter 14 (P2) | Iter 14 (P1) | Iter 15 Target (P2) | Iter 15 Target (P1) |
|--------|-------------|-------------|--------------------|--------------------|
| Trades | 65 | 49 | **20-30** | **15-25** |
| WR | 58.5% | 51.0% | **> 65%** | **> 60%** |
| PF | 0.804 | 0.543 | **> 2.0** | **> 1.5** |
| MaxDD | 6.8% | 5.6% | **< 10%** | **< 8%** |
| Return | -2.0% | -5.4% | **> +5%** | **> +2%** |
| SL rate | 60% | 69% | **< 45%** | **< 50%** |

### 목표의 근거

- 거래 수 20-30: P1+P2 캡(3 positions, 2 daily) + 강화된 필터의 복합 효과
- WR 65%+: Tier A+B 시그널만 통과하면 Iter 12 수준(70-77%) 근접 기대
- PF 2.0+: Iter 12 P2 BM이 5.959였으므로, 약간의 품질 저하를 감안해도 2.0+ 달성 가능
- MaxDD 10% 미만: 3 positions * 2.5% risk = 최대 7.5% 동시 리스크 + GDR 보호
- SL rate 45% 미만: 더 높은 ADX/VOL 기준으로 breakout 품질 개선

---

## 7. 이터레이션 14 교훈 (Lessons Learned)

### 교훈 1: 2차 효과의 중요성

MR 제거의 1차 효과(나쁜 전략 제거)는 예상대로 작동했다(DD 개선). 하지만 2차 효과(암묵적 필터 제거)가 수익을 파괴했다. 전략 제거/추가 시 반드시 시스템 수준의 상호작용(캡, 랭킹, 리소스 경쟁)을 점검해야 한다.

### 교훈 2: multi_strategy_mode 의존적 캡은 취약하다

`_SOFT_STRATEGY_CAP`이 전략 수에 의존하는 것은 설계 결함이다. 포지션 캡은 전략 수와 무관하게 항상 적용되어야 한다. BM-only든 5-strategy든 동시 보유 상한은 리스크 관리의 기본이다.

### 교훈 3: 엔트리 필터는 독립적으로 robust해야 한다

엔트리 필터가 '다른 메커니즘(랭킹 경쟁)이 보완해줄 것'이라는 전제 하에 느슨하게 설정되면, 환경이 바뀔 때 취약해진다. 각 필터는 독립적으로 의미 있는 품질 기준이어야 한다.

### 교훈 4: 전략 내부 Exit의 실제 작동 검증이 필수

Panel #24에서 제기된 BM trend_loss exit 미작동 이슈가 여전히 미해결. 전략 설계 시 exit 로직이 시뮬레이터에서 실제로 실행되는지 반드시 코드 수준에서 검증해야 한다. '설계했으니 작동하겠지'는 위험한 가정이다.

---

## 8. Decision Summary

| 항목 | 결정 |
|------|------|
| _MAX_TOTAL_POSITIONS | 5 -> **3** |
| _MAX_DAILY_ENTRIES | 3 -> **2** |
| _MAX_LONG_POSITIONS | 4 -> **3** |
| ADX_MIN | 25.0 -> **30.0** |
| VOL_RATIO_MIN | 1.2 -> **1.5** |
| BREAKOUT_LOOKBACK | 10 -> **20** |
| BM TP ATR mult | 5.0 -> **3.5** |
| Trailing activation ATR | 1.0 -> **1.5** |
| BM MAX_HOLD_DAYS | 없음 -> **12** |
| RANGING alloc | 0.008 -> **0.005** |
| UNCERTAIN alloc | 0.012 -> **0.008** |
| MIN_SIGNAL_STRENGTH | 없음 -> **0.30** (optional) |
| BM trend_loss exit 수정 | **코드 수정 필요 (별도 트래킹)** |

**MUST IMPLEMENT (P1+P2)**: 포지션 캡 복원 + 엔트리 필터 강화 (총 6개 파라미터)
**SHOULD IMPLEMENT (P3)**: Exit 파라미터 최적화 (3개 파라미터)
**NICE TO HAVE (P4+P5)**: Regime 미세 조정 + MIN_SIGNAL_STRENGTH (4개 파라미터)

**Next Step**: P1-P3 구현 후 Iteration 15 BM-only 백테스트 실행. 목표는 trades 20-30, WR 65%+, PF 2.0+, MaxDD < 10%.

---

## Appendix: Iteration History

| Iter | P2 Return | P1 Return | P2 Trades | P2 PF | MaxDD (P2) | Key Change | Verdict |
|------|-----------|-----------|-----------|-------|------------|------------|---------|
| 11 | +11.0% | -1.1% | 56 | - | 16.5% | 3-strategy static | PARTIAL |
| 12 | +5.4% | +2.9% | 56 | BM:5.959 | 32.6% | 2-strategy + regime | FAIL |
| 13 | +5.1% | -3.9% | 55 | BM:5.959 | 35.2% | MR tuning (6 changes) | FAIL |
| 14 | -2.0% | -5.4% | 65 | **0.804** | 6.8% | BM-only, MR removed | **FAIL** |
| 15 (plan) | TBD | TBD | target 20-30 | target >2.0 | target <10% | Cap restore + filter tightening | - |

## Appendix: Parameter Change Map

### breakout_momentum.py
```
ADX_MIN:          25.0  -> 30.0   (line 35)
VOL_RATIO_MIN:    1.2   -> 1.5    (line 42)
BREAKOUT_LOOKBACK: 10   -> 20     (line 34)
```

### exit_rules.py
```
_TP_ATR_MULT["breakout_momentum"]:                5.0  -> 3.5   (line 58)
_TRAILING_ACTIVATION_ATR["breakout_momentum"]:     1.0  -> 1.5   (line 69)
_MAX_HOLD_DAYS["breakout_momentum"]:               N/A  -> 12    (add to dict, line 37-42)
```

### batch_simulator.py
```
_MAX_TOTAL_POSITIONS:  5  -> 3     (line 73)
_MAX_DAILY_ENTRIES:    3  -> 2     (line 105)
_MAX_LONG_POSITIONS:   4  -> 3     (line 71)
```

### regime_classifier.py
```
RANGING BM alloc:     0.008 -> 0.005  (line 32)
UNCERTAIN BM alloc:   0.012 -> 0.008  (line 40)
```
