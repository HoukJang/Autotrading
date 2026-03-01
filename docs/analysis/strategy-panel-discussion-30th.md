# Strategy Panel Discussion #30: Clean Revert to Iter 23 Baseline

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iter 25 partially rolled back Iter 24's destructive changes but kept 6 "improvements" from Panel #28. Combined return dropped from +15.4% (Iter 23) to +5.16% (Iter 25). The remaining 6 differences are now identified and the primary suspect is trailing distance 1.5 (should be 2.0).
**Verdict**: **Panel #28's "math flaw" claim was WRONG. Full revert to Iter 23 values for reproducibility confirmation.**

---

## 1. Performance Delta (Iter 23 vs Iter 25)

| Metric | Iter 23 | Iter 25 | Delta |
|--------|---------|---------|-------|
| P1 Return | +7.5% | +1.76% | **-5.74%p** |
| P2 Return | +7.9% | +3.40% | **-4.50%p** |
| Combined | +15.4% | +5.16% | **-10.24%p** |
| BM P1 PF | 1.806 | 1.396 | -0.41 |
| BM P2 PF | 1.618 | 0.844 | **-0.77** |
| MR P2 PF | 2.858 | 2.882 | +0.02 |

BM exit analysis (P1):

| Exit Reason | Iter 23 P1 | Iter 25 P1 |
|-------------|-----------|-----------|
| stop_loss | 25 | 24 |
| trailing_stop | **2** | **6** |
| take_profit | 6 | 4 |
| BM PF | 1.806 | 1.396 |

BM exit analysis (P2):

| Exit Reason | Iter 23 P2 | Iter 25 P2 |
|-------------|-----------|-----------|
| stop_loss | 28 | 34 |
| trailing_stop | 9 | 8 |
| take_profit | 1 | 0 |
| BM PF | 1.618 | **0.844** |

---

## 2. Remaining Differences (Iter 23 vs Iter 25)

| # | Parameter | Iter 23 | Iter 25 (Current) | Panel #28 Rationale |
|---|-----------|---------|-------------------|---------------------|
| 1 | _TRAILING_ATR_MULT | **2.0** | 1.5 | "math flaw: distance > activation" |
| 2 | _STAGE2_PROFIT_LOCK_ATR | 0.4 | 0.5 | "more profit protection" |
| 3 | _MAX_PORTFOLIO_HEAT_PCT | 0.35 | 0.32 | "DD reduction" |
| 4 | _PORTFOLIO_SAFETY_NET_DD | 0.12 | 0.10 | "earlier safety net" |
| 5 | _PORTFOLIO_SAFETY_NET_RECOVERY | 0.08 | 0.07 | "tighter recovery" |
| 6 | TREND_UP MR alloc | 0.012 | 0.008 | "MR zero-edge in TREND_UP" |

---

## 3. Panel Discussion

### Strat-1 (Swing Trader) -- Panel #28의 "수학적 결함" 주장은 틀렸다

"이번 이터레이션의 핵심 발견은 Panel #28이 '수학적 결함'이라고 진단한 것이 **완전한 오해였다**는 점이다. 이것을 명확히 짚고 넘어가야 한다.

**Trailing Activation과 Trailing Distance는 완전히 다른 개념이다:**

```
Trailing ACTIVATION (1.5 ATR):
- 가격이 진입가 대비 1.5 ATR만큼 유리한 방향으로 이동하면
- 그 시점에서 stop이 breakeven(진입가)으로 이동
- 이것은 'trailing을 시작하는 조건'

Trailing DISTANCE (2.0 ATR):
- trailing이 활성화된 이후, stop은 최고가에서 2.0 ATR 뒤에 따라붙음
- 이것은 'trailing 중인 stop의 간격'
```

activation=1.5, distance=2.0인 경우의 작동 시나리오:

```
1. 진입가 $100, ATR=$5
2. 가격이 $107.50 도달 (1.5*$5 = $7.50 이동) -> trailing 활성화
3. 이 시점에서 stop = max(entry, highest - 2.0*ATR) = max($100, $107.50 - $10) = $100
4. 가격이 $115로 상승 -> stop = max($100, $115 - $10) = $105
5. 가격이 $120으로 상승 -> stop = max($100, $120 - $10) = $110
6. 정상적 pullback으로 $111까지 하락 -> stop $110 미도달, 거래 유지
7. 가격 $125로 재상승 -> stop = $115
```

distance > activation인 것은 결함이 아니라 **의도적 설계**다. 활성화 직후의 초기 단계에서 stop은 breakeven(진입가)에 고정되고, 가격이 더 상승해야 trailing stop이 진입가 위로 올라간다. 이것이 거래에 '숨 쉴 공간'을 제공한다.

**distance=1.5로 줄이면:**

```
1. 진입가 $100, ATR=$5
2. 가격 $107.50 -> trailing 활성화
3. stop = max($100, $107.50 - $7.50) = $100 (동일)
4. 가격 $112 -> stop = max($100, $112 - $7.50) = $104.50
5. 정상적 pullback으로 $106 하락 -> stop $104.50 미도달이지만 간격이 좁아 위험
6. 가격 $115 -> stop = $107.50
7. 정상 pullback $108 -> trailing exit 발동!
```

distance 1.5는 distance 2.0 대비 pullback 허용 범위가 0.5 ATR 좁다. 이것이 BM P2에서 PF 1.618 -> 0.844로 붕괴시킨 원인이다. 수익 거래가 정상 pullback에서 조기 exit된다.

**내 결론: trailing distance를 2.0으로 즉시 복원해야 한다.**"

### Strat-2 (Quant Analyst) -- 6개 잔여 변경의 누적 영향 분해

"6개 잔여 변경의 영향을 정량적으로 추정하겠다.

**변경별 추정 영향:**

| # | Parameter | Iter 23->25 | 추정 영향 (Combined) | 근거 |
|---|-----------|-------------|---------------------|------|
| 1 | Trail distance 2.0->1.5 | **-6%~-8%** | P2 BM PF 1.618->0.844, P1 trail exits 2->6 |
| 2 | Heat 0.35->0.32 | -1.0%~-1.5% | 8.5% 자본 축소 -> 수익 비례 감소 |
| 3 | Safety Net 0.12->0.10 | -0.3%~-0.5% | 조기 제한 -> 경미한 회복 지연 |
| 4 | Safety Net Recovery 0.08->0.07 | -0.1%~-0.2% | 미미한 영향 |
| 5 | Profit lock 0.4->0.5 | +0.1%~+0.3% | 약간의 이익 보전 개선 |
| 6 | TREND_UP MR 0.012->0.008 | -0.1%~-0.2% | MR P1 zero-edge, 사이즈 축소 |
| **합계** | | **-7.4%~-10.1%** | 실제 delta: -10.24% |

**핵심 발견: trailing distance 하나가 전체 delta의 60-75%를 설명한다.** 나머지 5개 변경은 합계 -2%~-3%p 수준.

그러나 여기서 중요한 질문이 있다: **Iter 23을 정확히 재현하면 +15.4%가 나오는가?**

이것을 확인하려면 모든 6개 변경을 동시에 Iter 23 값으로 복원해야 한다. 만약 한두 개만 복원하면, 어떤 변경이 얼마나 기여했는지 여전히 불확실하다.

**내 제안: Iter 26에서 6개 전부 Iter 23 값으로 복원한다. 이것은 '실험 재현성 확인'이다.**

만약 Iter 26 = Iter 23이 재현되면:
- Iter 24/25의 모든 '개선 시도'가 net-negative였음이 확증
- 파라미터 튜닝 시대의 종결 선언
- 구조적 변경(3번째 전략 추가 등)으로 방향 전환

만약 Iter 26 != Iter 23이면:
- 다른 숨겨진 변수가 존재할 가능성
- 코드 레벨 디버깅 필요"

### Strat-3 (Risk Manager) -- 과거 오판에 대한 솔직한 반성

"Panel #28에서 내가 trailing distance 2.0을 '수학적 결함'이라고 진단한 것은 **명백한 오류**였다. 이 오류가 어떻게 발생했는지 솔직하게 밝히겠다.

**오판의 원인:**

```
내 당시 논리:
- activation = 1.5 ATR (거래가 1.5 ATR 이동 시 trailing 시작)
- distance = 2.0 ATR (stop이 최고가에서 2.0 ATR 뒤)
- '활성화 시점에서 stop 위치 = highest - 2.0 ATR'
- 'activation에서 1.5 ATR만 이동했는데 distance가 2.0이면 stop이 진입가 이하?'
- '결함이다!'

실제 메커니즘:
- 활성화 시점: stop = max(entry, highest - distance*ATR)
- max() 함수가 entry를 floor로 보장
- 따라서 distance > activation이어도 stop은 절대 entry 아래로 가지 않음
- distance > activation = 활성화 초기에 stop이 entry에 고정 = breathing room
```

코드를 다시 읽어보면 (exit_rules.py line 483):
```python
position.highest_price - _TRAILING_ATR_MULT * atr,
```
이것이 `max(entry, ...)` 로 감싸져 있었다. 나는 이 `max()` 제한을 간과했다.

**반성: exit rule 변경을 제안할 때는 반드시 코드의 실제 로직을 line-by-line으로 추적해야 한다. 개념적 이해만으로 '결함'을 선언하면 안 된다.**

**리스크 관점에서의 revert 동의:**

Iter 23 값으로 전체 복원하는 것에 대한 리스크 평가:

```
복원 후 예상 리스크 프로파일:
- MaxDD: ~20% (Iter 23 수준)
- Heat 35%에서 MaxDD 20%는 이미 확인된 값
- Safety Net 12%: DD 12%에서 제한 모드 진입
- 최악의 경우: Iter 23과 동일한 20% MaxDD

이것은 '알려진 리스크'다.
Iter 25의 5.16% return + 미지의 DD 프로파일보다
Iter 23의 15.4% return + 알려진 20% MaxDD가 더 예측 가능하다.
```

DD를 줄이고 싶다면, Iter 23 재현을 확인한 **이후에** 한 번에 하나의 변경만 테스트해야 한다. Heat 35->32를 먼저 테스트하고, 그 결과를 본 후 Safety Net을 조정하는 식으로."

### Strat-4 (Market Analyst) -- 실험 재현성의 중요성

"Iter 23이 best-ever 결과(+15.4%)인데, 현재 코드는 Iter 23이 아니다. 6개 변수가 다르다. 이 상태에서 어떤 새로운 시도를 하든, 기준선(baseline)이 불확실하다.

**재현성 확인이 먼저인 이유:**

```
현재 상황:
- Iter 23: +15.4% (알려진 최고)
- Iter 25: +5.16% (6개 변경 적용)
- Delta: -10.24%

만약 Iter 26에서 Iter 23 값을 완전 복원하여:
- 시나리오 A: +15.4% 재현 -> baseline 확립, 향후 변경의 참조점 확보
- 시나리오 B: +13-14% (약간 미달) -> 코드 변경 외 다른 요인 존재 가능
- 시나리오 C: +10% 미만 -> 숨겨진 변수나 코드 regression 의심

시나리오 A가 확인되어야만 향후 최적화의 방향을 결정할 수 있다.
```

**레짐 관점의 추가 분석:**

Iter 25 P2에서 BM PF가 0.844로 나온 것은 RANGING/HIGH_VOL 레짐에서 trailing distance 1.5가 특히 치명적이라는 것을 보여준다. RANGING 시장에서는 가격이 좁은 범위에서 oscillation하므로, 1.5 ATR distance는 정상적인 oscillation의 상단과 하단 사이 거리보다 좁을 수 있다. 2.0 ATR distance는 이 oscillation을 흡수할 수 있는 여유를 제공한다.

**내 결론: 전원이 동의하는 clean revert가 올바른 접근이다.**"

---

## 4. Consensus

### 만장일치 (4/4): Iter 23 값으로 6개 전부 복원

**Strat-1**: "Trailing distance 2.0 복원이 핵심. 나머지도 함께 복원하여 baseline 확립."
**Strat-2**: "실험 재현성 확인이 과학적으로 올바른 다음 단계."
**Strat-3**: "Panel #28의 '수학적 결함' 진단이 오류였음을 인정. Clean revert 동의."
**Strat-4**: "Baseline 없이 최적화는 불가능. Iter 23 재현부터."

### Panel #28 오류 정정

| Panel #28 주장 | 실제 | 정정 |
|---------------|------|------|
| "trailing distance > activation은 수학적 결함" | activation과 distance는 다른 개념. max(entry, ...) 보호 존재. | distance > activation은 의도적 설계 (breathing room) |
| "trailing distance 1.5가 유익한 변경" | BM PF 붕괴의 주범 (1.618->0.844, P2) | trailing distance 2.0이 올바른 값 |
| "stage2 profit lock 0.5가 유익" | 영향 미미 (+0.1~0.3%p). 불확실성 제거를 위해 0.4로 복원 | 개별 테스트 없이 '유익'이라 단정할 수 없었음 |

---

## 5. Exact Parameter Changes for Iteration 26

**원칙: Iter 23 값으로 완전 복원. 변경 0개. 순수 재현성 테스트.**

### File 1: `autotrader/execution/exit_rules.py`

| # | Parameter | Line | Current (Iter 25) | Iter 26 (= Iter 23) | Action |
|---|-----------|------|-------------------|---------------------|--------|
| 1 | `_TRAILING_ATR_MULT` | 64 | **1.5** | **2.0** | REVERT |
| 2 | `_STAGE2_PROFIT_LOCK_ATR` | 34 | **0.5** | **0.4** | REVERT |

### File 2: `autotrader/backtest/batch_simulator.py`

| # | Parameter | Line | Current (Iter 25) | Iter 26 (= Iter 23) | Action |
|---|-----------|------|-------------------|---------------------|--------|
| 3 | `_MAX_PORTFOLIO_HEAT_PCT` | 76 | **0.32** | **0.35** | REVERT |
| 4 | `_PORTFOLIO_SAFETY_NET_DD` | 111 | **0.10** | **0.12** | REVERT |
| 5 | `_PORTFOLIO_SAFETY_NET_RECOVERY` | 112 | **0.07** | **0.08** | REVERT |

### File 3: `autotrader/backtest/regime_classifier.py`

| # | Parameter | Line | Current (Iter 25) | Iter 26 (= Iter 23) | Action |
|---|-----------|------|-------------------|---------------------|--------|
| 6 | TREND_UP `rsi_mean_reversion` alloc | 25 | **0.008** | **0.012** | REVERT |

### Code Changes (Copy-Paste Ready)

**exit_rules.py:**
```python
# Line 34: REVERT stage2 profit lock 0.5 -> 0.4
_STAGE2_PROFIT_LOCK_ATR: float = 0.4      # Stage 2: SL moved to entry + this

# Line 64: REVERT trailing distance 1.5 -> 2.0
_TRAILING_ATR_MULT: float = 2.0
```

**batch_simulator.py:**
```python
# Line 76: REVERT heat 0.32 -> 0.35
_MAX_PORTFOLIO_HEAT_PCT: float = 0.35   # max 35% of equity exposed (Iter 23 baseline)

# Line 111: REVERT safety net DD 0.10 -> 0.12
_PORTFOLIO_SAFETY_NET_DD: float = 0.12          # 12% total portfolio DD (Iter 23 baseline)

# Line 112: REVERT safety net recovery 0.07 -> 0.08
_PORTFOLIO_SAFETY_NET_RECOVERY: float = 0.08    # resume per-strategy GDR when DD < 8% (Iter 23 baseline)
```

**regime_classifier.py:**
```python
# Line 23-27: REVERT TREND_UP MR alloc 0.008 -> 0.012
Regime.TREND_UP: {
    "breakout_momentum": 0.040,     # BM dominant (unchanged)
    "rsi_mean_reversion": 0.012,    # MR reverted to Iter 23
    "breakout_blocked": False,
    "mr_short_blocked": True,       # no shorting in uptrend
},
```

### Test Assertion Updates Required

`tests/unit/batch/test_per_strategy_gdr.py` line 111-112:
```python
# Update safety net threshold assertions to match Iter 23
assert _PORTFOLIO_SAFETY_NET_DD == 0.12    # was 0.10
assert _PORTFOLIO_SAFETY_NET_RECOVERY == 0.08  # was 0.07
```

---

## 6. DO NOT CHANGE (Locked Parameters)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 7-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 7-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 7-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | 7-iter confirmed |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| BM TP ATR mult | exit_rules.py | 4.0 | Panel #27 decision |
| BM trailing activation | exit_rules.py | 1.5 | Iter 23 value, validated |
| MR soft cap | batch_simulator.py | 3 | Panel #27, PF 2.858 validates |
| BM GDR thresholds | batch_simulator.py | (0.04, 0.08) | Iter 23 value, validated |
| MR GDR thresholds | batch_simulator.py | (0.02, 0.04) | Iter 23 value, validated |
| MAX_LONG | batch_simulator.py | 8 | Iter 23 value |
| MAX_TOTAL | batch_simulator.py | 9 | Iter 23 value |

---

## 7. Expected Results

### If Iter 26 reproduces Iter 23:

| Metric | Expected Iter 26 | Iter 23 Reference |
|--------|------------------|-------------------|
| P1 Return | +7.0~8.0% | +7.5% |
| P2 Return | +7.5~8.5% | +7.9% |
| Combined | +14.5~16.5% | +15.4% |
| BM P1 PF | 1.6~1.9 | 1.806 |
| BM P2 PF | 1.4~1.8 | 1.618 |
| MR P2 PF | 2.5~3.0 | 2.858 |
| P1 MaxDD | 18~22% | 20.2% |
| P2 MaxDD | 19~22% | 21.0% |
| BM P1 trailing exits | 1~3 | 2 |

### Success / Failure Criteria

```
SUCCESS (baseline confirmed):
- Combined Return within 2%p of Iter 23 (+13.4% ~ +17.4%)
- BM PF > 1.4 (both periods)
- BM trailing exits < 5 (P1)
=> CONCLUSION: Iter 24/25 "improvements" were all net-negative
=> NEXT: structural changes (3rd strategy, etc.) NOT parameter tuning

PARTIAL MATCH (minor deviation):
- Combined Return +10~13%
- BM PF > 1.2
=> CONCLUSION: mostly reproduced, minor variance acceptable
=> NEXT: same as success

FAILURE (not reproduced):
- Combined Return < +10%
- BM PF < 1.2
=> CONCLUSION: hidden code regression or untracked parameter change
=> NEXT: line-by-line code diff between Iter 23 commit and current
```

---

## 8. Strategic Direction After Iter 26

If Iter 23 is confirmed reproducible, the panel recommends:

1. **STOP parameter tuning.** Iter 23's parameters are the proven baseline. The 10+ iterations of parameter changes since Iter 23 have all been net-negative.

2. **Shift to structural improvements:**
   - 3rd complementary strategy (e.g., sector rotation, momentum factor)
   - Walk-forward validation framework
   - Out-of-sample testing on different time periods

3. **DD reduction through structure, not parameter tightening:**
   - Portfolio diversification (more uncorrelated strategies) reduces DD naturally
   - Individual strategy parameter tightening has proven counterproductive

---

## 9. Iteration History (Updated through Iter 25)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 (LOCKED) |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | MR cap3, heat 35%, TP 4.0, trail 1.5 |
| 24 | -0.69% | +0.19% | -0.5% | 21.8% | 4.34% | DD reduction 11 changes (OVER-CORRECTED) |
| 25 | +1.76% | +3.40% | +5.16% | ? | ? | Partial rollback (5 of 11 reverted) |
| **26 (target)** | **+7.5%** | **+7.9%** | **+15.4%** | **~20%** | **~21%** | **Clean revert to Iter 23 (reproducibility test)** |

---

## Appendix: Complete Iter 23 vs 25 vs 26 Parameter Tracking

| Parameter | Iter 23 | Iter 25 (Current) | Iter 26 (Proposed) | Net vs Iter 23 |
|-----------|---------|-------------------|-------------------|----------------|
| _TRAILING_ATR_MULT | 2.0 | 1.5 | **2.0** | 0 |
| _STAGE2_PROFIT_LOCK_ATR | 0.4 | 0.5 | **0.4** | 0 |
| _MAX_PORTFOLIO_HEAT_PCT | 0.35 | 0.32 | **0.35** | 0 |
| _PORTFOLIO_SAFETY_NET_DD | 0.12 | 0.10 | **0.12** | 0 |
| _PORTFOLIO_SAFETY_NET_RECOVERY | 0.08 | 0.07 | **0.08** | 0 |
| TREND_UP MR alloc | 0.012 | 0.008 | **0.012** | 0 |
| BM trailing activation | 1.5 | 1.5 | 1.5 | 0 |
| BM GDR | (0.04, 0.08) | (0.04, 0.08) | (0.04, 0.08) | 0 |
| MR GDR | (0.02, 0.04) | (0.02, 0.04) | (0.02, 0.04) | 0 |
| Heat | 0.35 | 0.32 | **0.35** | 0 |
| MAX_LONG | 8 | 8 | 8 | 0 |
| MAX_TOTAL | 9 | 9 | 9 | 0 |

**Iter 26 = Iter 23 (exact match, all zeros). This is a pure reproducibility test.**
