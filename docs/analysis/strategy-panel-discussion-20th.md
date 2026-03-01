# Strategy Panel Discussion #20: Iteration 6 Post-Mortem -- Parameter Seesaw 진단 및 Iteration 7 제안

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Data Analyst)
**Context**: Iteration 6 결과 vs Iteration 5 비교, Parameter Seesaw 근본 원인 분석, 구조적 해결 방안 수립
**Decision**: STRUCTURAL + PARAM_TUNE (2개 변경: rsi_mr TREND 차단 + breakout TP 절충)

---

## 1. Iteration 6 Results Summary

### Period 2 (2025-03 ~ 2026-02) -- Mixed market

| Metric | Iter 5 | Iter 6 | Delta | 방향 |
|--------|--------|--------|-------|------|
| Total Return | +9.1% | +5.3% | -3.8%p | 악화 |
| breakout PnL | +$3,844 | -$1,811 | -$5,655 | 대폭 악화 |
| breakout trades | 45 | 29 | -16 | 급감 |
| breakout WR | 66.7% | 44.8% | -21.9%p | 급락 |
| rsi_mr PnL | +$2,558 | +$5,000 | +$2,442 | 개선 |

### Period 1 (2024-03 ~ 2025-02) -- Bull market

| Metric | Iter 5 | Iter 6 | Delta | 방향 |
|--------|--------|--------|-------|------|
| Total Return | -6.5% | -2.8% | +3.7%p | 개선 |
| breakout PnL | -$2,788 | +$1,401 | +$4,189 | 대폭 개선 |
| rsi_mr PnL | -$3,335 | -$2,599 | +$736 | 소폭 개선 |

### Iter 6 변경 내용 복기

| Parameter | Iter 5 | Iter 6 |
|-----------|--------|--------|
| breakout SL | 2.0 ATR | 2.5 ATR |
| breakout TP | 4.0 ATR | 2.5 ATR |
| breakout trailing activation | 1.5 ATR | 1.0 ATR |

---

## 2. Exit Distribution 변화 분석

### P2 (Mixed): Iter 5 -> Iter 6

| Exit Reason | Iter 5 | Iter 6 | Delta |
|-------------|--------|--------|-------|
| stop_loss | 19 (42%) | 11 (38%) | -8건, -4%p |
| time_exit | 21 (47%) | 10 (34%) | -11건, -13%p |
| take_profit | 1 (2%) | 2 (7%) | +1건, +5%p |
| trailing_stop | 3 (7%) | 6 (21%) | +3건, +14%p |

Exit 분포 자체는 개선됨. SL 비율 감소, trailing 증가. 그러나 거래수 45 -> 29로 급감하면서 WR이 66.7% -> 44.8%로 급락.

### P1 (Bull): Iter 5 -> Iter 6

| Exit Reason | Iter 5 | Iter 6 | Delta |
|-------------|--------|--------|-------|
| stop_loss | 20 (53%) | 12 (28%) | -8건, -25%p |
| time_exit | 18 (47%) | 21 (49%) | +3건, +2%p |
| take_profit | 0 (0%) | 6 (14%) | +6건, +14%p |
| trailing_stop | 0 (0%) | 4 (9%) | +4건, +9%p |

P1에서 극적 개선. SL 53% -> 28%, TP와 trailing이 0%에서 각각 14%/9%로 활성화. PnL -$2,788 -> +$1,401 전환.

---

## 3. Panel Analysis

### Strat-4 (Data Analyst) -- Seesaw 정량 진단

**핵심 질문: P2에서 거래수가 45 -> 29로 줄어든 원인은 무엇인가?**

breakout_momentum 전략의 진입 조건(ADX > 25, RSI 50-80, 10일 신고가, 거래량 1.2x)은 Iter 5와 6에서 동일하다. 진입 조건이 같으므로 "진입 시그널 발생 건수"는 동일하다. 그러면 16건이 줄어든 원인은 진입 이후 단계에 있다.

**원인 1: ATR-based sizing에서 qty = 0 발생 (SL 확대 부작용)**

position sizing 공식: `qty = risk_per_trade / stop_distance`

- Iter 5: stop_distance = 2.0 * ATR
- Iter 6: stop_distance = 2.5 * ATR (25% 증가)

stop_distance가 25% 커지면, 동일 risk budget에서 qty가 20% 감소한다. 소형 계좌($50K)에서 고가 종목의 경우 qty < 1이 되어 진입 자체가 불가능해진다.

예시: 주가 $400, ATR $8, risk_per_trade = $750 (1.5% of $50K)
- Iter 5: qty = $750 / ($8 * 2.0) = 46주
- Iter 6: qty = $750 / ($8 * 2.5) = 37주

이 예시에서는 문제 없지만, 자본이 감소하거나 ATR이 큰 종목에서는 qty = 0이 될 수 있다. 16건 전체가 이 원인은 아니지만, 일부 기여한다.

**원인 2: Per-Strategy GDR 조기 발동**

breakout_momentum의 GDR 임계값:
- Tier 1: 초기자본 대비 2.5% DD ($1,250)
- Tier 2 (HALT): 초기자본 대비 5.0% DD ($2,500)

Iter 6에서 SL이 2.5 ATR로 넓어지면, 개별 손실 트레이드의 손실 금액이 커진다. SL hit 시 손실이 커지면 Tier 1 진입이 빨라지고, Tier 1에서 risk가 50% 감소하면 이후 트레이드가 더 작아져 수익으로 회복하기 어려워진다.

P2 최종 breakout PnL이 -$1,811이므로, 시뮬레이션 중간에 Tier 1(-$1,250)에 진입했다가 일부 회복한 패턴이 의심된다. Tier 1 기간 동안 entry가 차단되거나 size가 축소되어 16건의 기회를 놓쳤을 것이다.

**원인 3: 포지션 슬롯 경쟁**

max_total_positions = 5, max_daily_entries = 3. Iter 6에서 rsi_mr이 +$5,000으로 개선되었다는 것은 rsi_mr이 더 많은 포지션 슬롯을 차지했다는 의미일 수 있다. breakout과 rsi_mr이 동일 날 시그널을 발생시키면 strength 기반 우선순위에서 rsi_mr이 선택될 수 있다.

**결론: 거래수 감소는 SL 확대 -> GDR 조기 발동 + qty 감소의 복합 효과. 단일 원인이 아닌 시스템 동학.**

---

### Strat-2 (Quant Analyst) -- Seesaw의 수학적 분석

**Parameter Seesaw 구조:**

```
Iter 5: SL 2.0, TP 4.0, trail 1.5
  P1: breakout -$2,788 (SL too tight for bull pullbacks)
  P2: breakout +$3,844 (tight SL acceptable in mixed market)

Iter 6: SL 2.5, TP 2.5, trail 1.0
  P1: breakout +$1,401 (wider SL survives pullbacks)
  P2: breakout -$1,811 (wider SL -> GDR cascade -> trades blocked)
```

**Seesaw의 진짜 원인은 SL이 아니라 GDR과의 상호작용이다.**

SL 2.0 -> 2.5 변경 자체는 양 기간 모두에서 SL hit rate를 개선했다 (P1: 53%->28%, P2: 42%->38%). 문제는 SL hit당 손실 금액이 25% 커지면서 GDR Tier 1 진입이 빨라지고, 이것이 이후 거래 기회를 차단한다는 점이다.

**이것은 파라미터 문제가 아니라 시스템 피드백 루프 문제다:**

```
SL 확대 -> 개별 손실 증가 -> GDR 조기 발동 -> 진입 차단/축소
-> 회복 기회 상실 -> 누적 손실 심화 -> GDR 장기 지속
```

**해결 방향:**

1. SL을 다시 줄이면 P1이 악화됨 (seesaw 반복)
2. GDR 임계값을 조정하면 리스크 관리가 약화됨
3. **진짜 해법: P1의 주 손실원인인 rsi_mr을 제거하면, breakout이 P1에서 약간 손해를 보더라도 포트폴리오 전체가 수익**

rsi_mr P1 -$2,599 제거가 breakout 파라미터 어떤 조합보다 P1 개선 효과가 크다.

---

### Strat-1 (Swing Trader) -- 실전적 관점

**breakout TP 2.5의 P2 문제:**

TP 2.5와 trailing activation 1.0을 동시에 사용하면 두 exit이 경쟁한다.

trailing stop 로직 분석:
- activation: 가격이 entry + 1.0*ATR 도달
- trail_stop = max(entry, highest - 2.0*ATR)

만약 가격이 entry + 1.5*ATR까지 올라갔다가 하락하면:
- trail_stop = max(entry, entry + 1.5 - 2.0) = entry (breakeven)
- 이 시점에서 가격이 entry 이하로 내려가면 trailing exit at breakeven

만약 가격이 entry + 2.5*ATR까지 올라가면:
- TP 2.5가 먼저 발동 (take_profit exit)
- trailing은 발동 안 함

**문제: TP 2.5가 trailing의 잠재적 추가 수익을 차단한다.**

P1(Bull)에서 가격이 2.5 ATR 이상 올라갈 수 있는 트레이드가 있는데, TP 2.5에서 조기 청산됨. trailing이 이것을 3, 4, 5 ATR까지 따라갈 수 있었는데 기회를 놓침.

**권고: TP를 3.0 ATR로 올려서 trailing에 더 많은 공간을 부여.**

TP 3.0이면:
- 가격이 1.0~3.0 ATR 사이에서 trailing이 이익을 보호
- 가격이 3.0 ATR 이상이면 TP가 확정 수익 확보
- P2에서도 TP 3.0은 Iter 5의 4.0보다 현실적이므로 hit rate 유지

---

### Strat-3 (Risk Manager) -- 리스크 구조 분석

**현재 가장 큰 리스크: rsi_mean_reversion의 TREND regime 진입**

| Period | rsi_mr PnL | TREND 비중 | regime_guard 차단 |
|--------|-----------|-----------|-----------------|
| P1 (Bull) | -$2,599 | TREND 10% | 7/20건만 차단 |
| P2 (Mixed) | +$5,000 | TREND 10% | - |

regime_guard 조건 분석:
```python
current_adx > 23.0 AND (current_adx - entry_adx) >= 3.0
```

이것은 "포지션 보유 중 ADX가 급등하면 청산"하는 로직이다. 그러나 이것만으로는 부족하다:
- 이미 ADX가 높은(>25) TREND 환경에서 진입하면, ADX delta >= 3 조건이 충족되기 어려움
- 즉, 강한 TREND에서 진입한 rsi_mr은 regime_guard에 걸리지 않고 SL이나 time_exit까지 보유됨
- P1에서 20건 중 7건만 차단 = 65%의 역추세 트레이드가 필터를 통과

**rsi_mr TREND 차단의 P2 영향 분석:**

P2에서 rsi_mr이 +$5,000. 이 중 TREND 기간에 발생한 수익이 얼마인지가 관건이다.

_REGIME_WEIGHTS에서 TREND 시 rsi_mr 비중은 0.10 (10%). 즉, TREND 기간에는 매우 작은 비중으로만 진입한다. P2의 +$5,000 대부분은 RANGING(35%) 또는 HIGH_VOL(25%) 기간에서 발생했을 것이다.

보수적 추정: TREND 기간 rsi_mr 수익 = +$5,000 * 0.10 / (0.10 + 0.35 + 0.25 + 0.25) = ~$526

**TREND 차단 시 P2 영향: -$500 수준. rsi_mr +$5,000 대비 10% 감소.**

반면 P1에서 rsi_mr -$2,599의 대부분이 TREND 기간에서 발생. TREND 차단 시 +$2,000~2,500 회복 예상.

**Net 효과: +$1,500~2,000 개선. 명백한 양의 EV.**

---

## 4. Seesaw 문제의 근본 진단

### 패널 합의: 파라미터 Seesaw는 breakout 단독 문제가 아니다

Iter 5-6의 seesaw를 breakout 파라미터만으로 해결하려 하면 끝없이 반복된다. 근본 원인은 두 가지가 겹쳐있다:

**원인 A: rsi_mr이 P1에서 -$2,599의 "하중"을 부과**
- breakout이 P1에서 약간만 양수여도, rsi_mr이 포트폴리오를 마이너스로 끌어내림
- breakout 파라미터를 P1에 맞추면 (SL 넓게) -> P2에서 GDR cascade
- breakout 파라미터를 P2에 맞추면 (SL 좁게) -> P1에서 SL 과다

**원인 B: GDR이 SL 확대를 증폭**
- SL이 넓으면 손실 금액이 커지고, GDR이 빨리 발동되어 이후 기회를 차단
- 이것은 "좋은 의도의 나쁜 결과" -- 리스크 관리가 수익 기회를 과도하게 제한

**해결 전략: 원인 A를 제거하면 breakout 파라미터에 대한 압박이 줄어든다.**

rsi_mr TREND 차단 후, P1에서 breakout이 약간 손실을 보더라도 포트폴리오 전체는 수익이 가능하다. 이것이 seesaw를 깨는 핵심이다.

---

## 5. Iteration 7 제안서

### 변경 사항 (2개, 최소 변경 원칙)

#### 변경 1: rsi_mean_reversion TREND regime 진입 차단 [STRUCTURAL]

**현재 코드:**
```python
# regime_detector.py L146-152
MarketRegime.TREND: {
    "rsi_mean_reversion": 0.10,  # 10% 비중으로 진입 허용
    ...
}

# regime_position_reviewer.py L49-54
"rsi_mean_reversion": {
    MarketRegime.TREND,           # 15% -- 호환으로 분류
    MarketRegime.RANGING,
    MarketRegime.HIGH_VOLATILITY,
    MarketRegime.UNCERTAIN,
},
```

**제안 변경:**
```python
# regime_detector.py L146-152
MarketRegime.TREND: {
    "rsi_mean_reversion": 0.00,  # TREND에서 진입 차단
    ...
    # 나머지 전략 비중 재분배:
    # consecutive_down: 0.15 -> 0.15 (유지)
    # ema_pullback: 0.25 -> 0.30 (+0.05)
    # volume_divergence: 0.20 -> 0.20 (유지)
    # breakout_momentum: 0.30 -> 0.35 (+0.05)
}

# regime_position_reviewer.py L49-54
"rsi_mean_reversion": {
    # MarketRegime.TREND 제거
    MarketRegime.RANGING,
    MarketRegime.HIGH_VOLATILITY,
    MarketRegime.UNCERTAIN,
},
```

**근거:**
- Mean reversion 전략은 TREND 환경에서 구조적으로 역방향 매매. 이론적으로 부적합
- P1 데이터: WR 21.4%, PF 0.216, -$2,599. 압도적인 실패
- regime_guard가 7/20(35%)만 차단. 나머지 13건이 그대로 손실 누적
- rsi_mr을 0.00으로 만들면 TREND에서 아예 시그널이 생성되지 않음 (regime_guard보다 확실)

**양 기간 예상 영향:**

| | P1 (Bull) | P2 (Mixed) |
|--|-----------|-----------|
| rsi_mr PnL 변화 | +$2,000~2,500 (TREND 손실 제거) | -$300~500 (TREND 기간 소량 수익 상실) |
| breakout 영향 | 0 (직접 영향 없음) | 약간 긍정 (rsi_mr이 슬롯 양보 -> breakout 진입 기회 증가) |
| Portfolio 총 영향 | +$2,000~2,500 | -$300~500 |
| **Net 양 기간 합산** | **+$1,500~2,000** | |

#### 변경 2: breakout_momentum TP 2.5 -> 3.0 ATR [PARAM_TUNE]

**현재 코드 (Iter 6 적용 상태):**
```python
# exit_rules.py L57
_TP_ATR_MULT: dict[str, float | None] = {
    ...
    "breakout_momentum": 2.5,   # Iter 6에서 4.0 -> 2.5로 변경
}
```

**제안 변경:**
```python
# exit_rules.py L57
_TP_ATR_MULT: dict[str, float | None] = {
    ...
    "breakout_momentum": 3.0,   # 절충값
}
```

**근거:**
- TP 2.5가 trailing stop과 경쟁함. TP가 먼저 발동하면 trailing의 추가 수익 기회 차단
- TP 3.0이면 trailing activation(1.0) -> trailing이 1.0~3.0 ATR 구간에서 이익 보호
- TP 4.0(Iter 5)은 비현실적(hit rate 1.2%), TP 2.5(Iter 6)는 trailing과 충돌
- TP 3.0은 "trailing에 공간을 주면서도 강한 모멘텀에서 확정 수익"

**양 기간 예상 영향:**

| | P1 (Bull) | P2 (Mixed) |
|--|-----------|-----------|
| TP hit rate | 14% -> ~10% (약간 감소) | 7% -> ~5% (약간 감소) |
| trailing hit rate | 9% -> ~12% (trailing 공간 확대) | 21% -> ~25% (trailing 공간 확대) |
| breakout WR | 유사 (TP 감소 ≈ trailing 증가) | 약간 개선 (trailing이 더 유리한 가격에서 exit) |
| breakout PnL | +$1,401 -> +$1,200~1,600 (유사) | -$1,811 -> -$1,000~-$500 (개선) |

### 변경하지 않는 것 (그리고 이유)

| Parameter | 현재값 | 유지 이유 |
|-----------|--------|---------|
| breakout SL | 2.5 ATR | P1에서 SL hit 53%->28%로 대폭 개선. P2에서도 42%->38% 개선. SL 자체는 seesaw 원인 아님 |
| breakout trailing activation | 1.0 ATR | 양 기간 모두 긍정적. P1: 0%->9%, P2: 7%->21%. 유지 |
| breakout max_hold | 7일 | TP 3.0으로 조정하면 time_exit 비율 자연 변화. 동시 변경 시 인과관계 혼동 |
| GDR thresholds | (0.025, 0.05) | GDR 자체를 완화하면 리스크 관리 약화. 근본 원인(rsi_mr) 해결이 우선 |
| breakout trailing distance | 2.0 ATR | trailing exit이 breakeven 근처에서 발동하는 것은 "이익 보호" 관점에서 정상 작동 |
| rsi_mr 기타 파라미터 | - | TREND 차단만으로 충분. 추가 변경은 과도한 동시 조정 |

---

## 6. Risk Assessment

### 변경 1 (rsi_mr TREND 차단) 리스크

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| P2 TREND 기간 rsi_mr 수익 상실 | High (확실) | Low (-$300~500) | TREND에서 rsi_mr 비중이 10%로 이미 미미. 상실 금액 제한적 |
| TREND 비중 재분배로 breakout 과집중 | Low | Medium | breakout 0.30->0.35는 5%p 증가. 과집중이라 보기 어려움 |
| rsi_mr 전체 거래수 감소 | Medium | Low | RANGING(35%)+HIGH_VOL(25%)+UNCERTAIN(25%)=85% 유지. TREND 10%만 상실 |

### 변경 2 (breakout TP 3.0) 리스크

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| TP hit rate 감소 | Medium | Low | trailing이 대체. TP + trailing 합산 hit rate는 유사할 것 |
| P2에서 수익 미회수 | Low | Medium | TP 3.0은 여전히 7일 내 도달 가능한 수준 (4.0보다 훨씬 현실적) |
| P1 개선 효과 감소 | Low | Low | rsi_mr 차단이 P1의 주 개선 동력. breakout TP는 보조적 |

### Overfitting Assessment

| Change | Overfitting Risk | Rationale |
|--------|-----------------|-----------|
| rsi_mr TREND 차단 | Very Low | 이론적 근거 명확 (mean reversion != trend following). 데이터가 이론을 확인 |
| breakout TP 2.5 -> 3.0 | Very Low | Iter 5(4.0)와 Iter 6(2.5) 사이의 절충. 특정 기간에 맞추지 않음 |

---

## 7. Iteration 7 성공 기준

| Metric | P1 Target | P2 Target | Rationale |
|--------|-----------|-----------|-----------|
| rsi_mr PnL (P1) | > -$500 | > +$4,500 | TREND 차단으로 P1 손실 제거, P2 미미한 감소 |
| breakout PnL | > +$1,000 | > -$500 | TP 3.0으로 P2 약간 개선 예상 |
| Total Return | > 0% | > +7% | rsi_mr 차단이 P1을 양수로 전환 |
| Sharpe | > 0.3 | > 0.5 | P1 개선이 Sharpe에 직접 반영 |
| Seesaw 해소 확인 | 양 기간 모두 양수 | - | 한 기간 최적화 시 다른 기간 악화 여부 확인 |

### 관찰 포인트

1. **rsi_mr TREND 차단 효과**: P1에서 rsi_mr 거래수/PnL 변화. 20건 -> ~7건 이하 예상
2. **breakout P2 거래수 회복**: rsi_mr 슬롯 양보로 breakout 진입 기회 증가 여부
3. **GDR 발동 시점 변화**: breakout GDR Tier 1 진입 시점이 늦춰지는지
4. **trailing vs TP 분포**: TP 3.0에서 trailing이 더 많은 역할을 하는지

---

## 8. Implementation Spec (개발팀 핸드오프)

### 코드 변경 사항

**File 1: `autotrader/portfolio/regime_detector.py`**

```python
# L146-152: TREND regime weights
MarketRegime.TREND: {
    "rsi_mean_reversion": 0.00,    # WAS 0.10 -- TREND에서 진입 차단
    "consecutive_down": 0.15,       # 유지
    "ema_pullback": 0.30,           # WAS 0.25 -- +0.05 재분배
    "volume_divergence": 0.20,      # 유지
    "breakout_momentum": 0.35,      # WAS 0.30 -- +0.05 재분배
},
```

**File 2: `autotrader/portfolio/regime_position_reviewer.py`**

```python
# L49-54: rsi_mean_reversion compatible regimes
"rsi_mean_reversion": {
    # MarketRegime.TREND 제거
    MarketRegime.RANGING,          # 35%
    MarketRegime.HIGH_VOLATILITY,  # 25%
    MarketRegime.UNCERTAIN,        # 25%
},
```

**File 3: `autotrader/execution/exit_rules.py`**

```python
# L57: TP ATR multiplier
_TP_ATR_MULT: dict[str, float | None] = {
    ...
    "breakout_momentum": 3.0,      # WAS 2.5
}
```

**변경 파일 수**: 3개
**변경 라인 수**: ~5개
**테스트 영향**: regime_detector TREND weights 테스트, regime_position_reviewer compatibility 테스트, exit_rules TP 참조 테스트 업데이트 필요

---

## 9. 향후 로드맵

### Iter 7 결과에 따른 분기 시나리오

**시나리오 A: 양 기간 모두 양수 달성 (목표 달성)**
- Iter 8: breakout max_hold 조정 (7 -> 8~10일), portfolio heat 최적화
- 안정화 단계로 전환

**시나리오 B: P1은 개선되었으나 P2가 추가 악화**
- 진단: TP 3.0이 P2에서 부족한지, GDR cascade가 지속되는지 확인
- Iter 8: breakout GDR threshold 완화 (0.025 -> 0.035) 검토

**시나리오 C: 양 기간 모두 개선 미미**
- 진단: TREND regime 감지 정확도 확인. P1이 실제로 TREND로 분류되는지
- Iter 8: RegimeDetector의 TREND 판별 기준 검토

---

## 10. Panel Vote

| Team Member | Vote | Rationale |
|-------------|------|-----------|
| Strat-1 (Swing) | APPROVE | "rsi_mr TREND 차단은 이론과 데이터가 일치하는 명백한 개선. TP 3.0은 trailing에 공간을 준다." |
| Strat-2 (Quant) | APPROVE | "seesaw를 breakout 파라미터로만 풀려는 접근 자체가 잘못이었다. rsi_mr 제거로 시스템 전체 EV를 개선하는 것이 수학적으로 옳다." |
| Strat-3 (Risk) | APPROVE | "P2 rsi_mr 수익 -$500은 P1 손실 +$2,500 대비 명백히 양의 기대값. 리스크 감소가 크다." |
| Strat-4 (Data) | APPROVE | "6차례 iteration의 데이터가 명확하다: breakout 파라미터 단독 조정은 seesaw를 반복한다. 구조적 변경이 필요한 시점이다." |

**만장일치: 2개 변경 승인 (rsi_mr TREND 차단 + breakout TP 3.0)**

---

*Panel discussion concluded. Iteration 7 변경 사항 승인. 개발팀 구현 대기.*
