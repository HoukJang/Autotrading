# Strategy Team Design Session: 2-Strategy + Active Allocation Architecture

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing), Strat-2 (Quant), Strat-3 (Risk), Strat-4 (Analyst)
**Session Type**: DESIGN (신규 아키텍처 설계)
**Context**: 21차 패널 결론(파라미터 튜닝 천장 도달, 구조 변경 필요)에 따른 근본적 아키텍처 전환

---

## 0. 설계 원칙

패널 전원 합의:

1. **2전략 only**: breakout_momentum(추세추종) + adaptive_mean_reversion(평균회귀)
2. **상보성 극대화**: ADX 25를 경계로 두 전략이 깔끔하게 분리
3. **Regime이 배분을 제어**: batch_simulator에서 일간 regime 판단 -> 전략별 risk budget 동적 조정
4. **consecutive_down 흡수**: 기존 cons_down(P2 +$3,952 핵심 수익원)의 로직을 새 MR에 통합
5. **기존 rsi_mr 대체**: 더 넓은 진입 게이트로 거래 빈도 확보

---

## Task 1: 새 Mean-Reversion 전략 설계

### 1.1 기존 전략 실패 원인 진단

**Strat-4 (Analyst)**:

| 전략 | 핵심 문제 | 데이터 근거 |
|------|----------|------------|
| rsi_mean_reversion | RSI<30 AND %B<0.05 동시 충족이 극단적으로 드묾 | P2: 17건, P1: 19건. 목표 대비 50% 부족 |
| rsi_mean_reversion | ADX<20 필터가 bull market에서 대부분 종목 차단 | S&P500 종목의 ~50%가 bull에서 ADX>20 |
| consecutive_down | 독립적으로 잘 작동하나 별개 전략으로 존재 | P2: +$3,952 (포트 최대 수익원) |

### 1.2 전략 접근법 비교 평가

**Strat-2 (Quant)**:

| 접근법 | 거래 빈도 | 엣지 신뢰도 | 구현 복잡도 | breakout 상관 | 판정 |
|--------|----------|------------|------------|--------------|------|
| A) BB Lower Band | 높음 (30-50건) | 중간 | 낮음 | 낮음 | 후보 |
| B) RSI Divergence | 낮음 (5-10건) | 높음 | 높음 (peak detection) | 낮음 | 탈락: 구현 복잡 + 빈도 부족 |
| C) Volume Climax | 중간 (15-25건) | 낮음 (볼륨 노이즈) | 중간 | 중간 | 탈락: 볼륨 시그널 불안정 |
| D) Multi-factor Oversold | 높음 (20-40건) | 중간-높음 | 중간 | 낮음 | 최종 선택 |

**결정: D) Multi-factor Oversold -- BB + Consecutive Down 통합**

근거:
- consecutive_down의 검증된 로직(P2 +$3,952)을 흡수하여 검증된 엣지 보존
- BB oversold 게이트 추가로 진입 기회 확대
- OR 게이트 방식으로 두 시그널 소스가 독립적으로 거래 생성

### 1.3 전략 상세 스펙: `adaptive_mean_reversion`

**Strat-1 (Swing) -- 진입 설계**:

```python
name = "adaptive_mean_reversion"
direction = "long"  # Long only

# Required Indicators
indicators = [
    RSI(period=14),
    BBANDS(period=20, num_std=2.0),
    ADX(period=14),
    ATR(period=14),
    EMA(period=50),   # 장기 추세 필터
    EMA(period=5),    # 단기 exit target
]
```

**공통 필터 (모든 Gate에 적용)**:
```
FILTER_1: ADX < 25.0          # Non-trending market (breakout의 ADX>=25와 상보적)
FILTER_2: close > EMA(50)     # 장기 상승 추세 유지 (하락 추세 MR 회피)
FILTER_3: ADX slope check     # ADX 3-bar slope <= 2.0 (추세 전환 감지)
```

**Gate A -- "BB Oversold" (볼린저밴드 평균회귀)**:
```
GATE_A_1: BB %B < 0.20        # 하단 밴드 근처 (기존 0.05에서 완화)
GATE_A_2: RSI(14) < 40        # 과매도 영역 (기존 30에서 완화)
```

**Gate B -- "Consecutive Drop" (연속 하락 반등, cons_down 흡수)**:
```
GATE_B_1: 3+ consecutive down closes
GATE_B_2: RSI(14) < 50        # 모멘텀 약화 확인
```

**진입 로직**: `(공통 필터 ALL) AND (Gate A ALL OR Gate B ALL)`

**시그널 강도 계산**:
```python
if gate_a_triggered:
    rsi_score = (40.0 - rsi) / 40.0           # 0.0 ~ 1.0
    bb_score = (0.20 - pct_b) / 0.20          # 0.0 ~ 1.0
    strength = 0.5 * rsi_score + 0.5 * bb_score

if gate_b_triggered:
    days_score = min(1.0, (down_days - 2) * 0.20)   # 3일=0.2, 4일=0.4, 5일+=1.0
    rsi_score = (50.0 - rsi) / 50.0                  # 0.0 ~ 1.0
    strength = 0.4 * days_score + 0.6 * rsi_score

if both_triggered:
    strength = max(gate_a_strength, gate_b_strength) + 0.10  # 복합 보너스
    strength = min(1.0, strength)
```

**Strat-3 (Risk) -- Exit 설계**:

| Exit Rule | 조건 | 우선순위 |
|-----------|------|---------|
| Stop Loss | close <= entry_price - 1.5 * ATR | 1 (최우선) |
| Take Profit | close >= entry_price + 2.5 * ATR | 2 |
| Target (BB) | BB %B > 0.70 OR RSI > 60 | 3 |
| Target (EMA) | close > EMA(5) AND bars_held >= 2 | 4 |
| Time Exit | bars_held >= 7 | 5 |

**Exit 설계 근거 (Strat-1)**:
- SL 1.5 ATR: MR은 빠른 반등 기대. 진입 후 1.5 ATR 이상 하락하면 MR 전제 실패
- TP 2.5 ATR: MR의 realistic profit target. breakout(5.0 ATR)보다 보수적
- BB %B > 0.70: BB 중간선 이상 회복 = MR 완료
- EMA(5) 타겟: cons_down의 기존 exit 로직 보존 (2일 최소 보유 후)
- 7일 timeout: 기존 5일에서 약간 확장. 반등에 더 많은 시간 허용

### 1.4 예상 거래 수 및 성과

**Strat-2 (Quant) -- 거래 수 추정**:

유니버스 50종목 기준, 252 거래일/기간:

| Gate | symbol-day 충족률 | 포지션 cap 후 | 기간당 예상 |
|------|-------------------|-------------|------------|
| Gate A (BB %B<0.20, RSI<40, ADX<25, close>EMA50) | ~3-5% | 제한 적용 | 15-25건 |
| Gate B (3+down, RSI<50, ADX<25, close>EMA50) | ~1-3% | 제한 적용 | 8-15건 |
| 중복 제거 후 합산 | - | - | **20-35건** |

기존 rsi_mr(8-20건) + cons_down(16-20건) = 24-40건과 유사한 범위이나, 단일 전략으로 통합되어 포트폴리오 관리가 간결해짐.

**breakout_momentum과의 상관관계 분석**:

```
adaptive_mr 진입: ADX < 25, close > EMA50, RSI < 40~50
breakout     진입: ADX >= 25, close > EMA21, RSI 50~80

겹치는 구간: 없음 (ADX 25에서 깔끔하게 분리)
동일 종목 동시 시그널: 구조적으로 불가능
```

상관계수 추정: **< 0.15** (극히 낮은 양의 상관. 둘 다 long-only이므로 시장 beta 공유)

### 1.5 인디케이터 요구사항

`exit_rules.py`에 추가할 파라미터:

```python
# 신규 추가
_MAX_HOLD_DAYS["adaptive_mean_reversion"] = 7
_SL_ATR_MULT["adaptive_mean_reversion"] = {"long": 1.5}
_TP_ATR_MULT["adaptive_mean_reversion"] = 2.5
# _TRAILING_STRATEGIES에 미추가 (MR은 trailing stop 불사용)
```

`batch_simulator.py`에 추가할 상수:

```python
_STRATEGY_NAMES = ["adaptive_mean_reversion", "breakout_momentum"]

_STRATEGY_BASE_RISK = {
    "adaptive_mean_reversion": 0.015,   # 1.5% (cons_down 1.2% + rsi_mr 0.7%의 중간)
    "breakout_momentum": 0.020,         # 2.0% (기존 유지)
}

_STRATEGY_GDR_THRESHOLDS = {
    "adaptive_mean_reversion": (0.025, 0.05),  # Tier1 at 2.5% DD, Tier2 at 5% DD
    "breakout_momentum": (0.04, 0.08),          # 기존 유지
}
```

---

## Task 2: Active Allocation Framework 설계

### 2.1 설계 철학

**Strat-4 (Analyst)**:

21차 패널의 핵심 발견: batch_simulator는 regime-blind. 이것이 rsi_mr의 P1 대규모 손실의 근본 원인이다. TREND 시장에서 MR 전략이 full risk로 거래하면 손실이 누적된다.

해결책: regime에 따라 각 전략의 risk budget을 동적 조정.

```
TREND 시장    -> breakout에 자본 집중, MR 최소화
RANGING 시장  -> MR에 자본 집중, breakout 최소화
HIGH_VOL 시장 -> 전체 노출 축소, MR 약간 우위 (mean reversion 작동)
UNCERTAIN     -> 균등 배분 + 현금 버퍼
```

### 2.2 Regime별 배분 테이블

**Strat-2 (Quant) -- 정확한 수치**:

| Regime | breakout base_risk | adaptive_mr base_risk | max_positions | cash_buffer | 배분 비율 |
|--------|--------------------|-----------------------|---------------|-------------|----------|
| **TREND** | 0.025 (125%) | 0.005 (33%) | 5 | 10% | BK 83% : MR 17% |
| **RANGING** | 0.008 (40%) | 0.022 (147%) | 5 | 10% | BK 27% : MR 73% |
| **HIGH_VOL** | 0.008 (40%) | 0.012 (80%) | 3 | 35% | BK 40% : MR 60% |
| **UNCERTAIN** | 0.015 (75%) | 0.015 (100%) | 4 | 20% | BK 50% : MR 50% |

괄호 안 %는 기본값(breakout 0.020, mr 0.015) 대비 비율.

**배분 비율 산출 근거**:

TREND regime:
- breakout_momentum의 P1(+$387~$2,478), P2(+$648~$7,731) 성과가 trending 시장에서 발생
- ADX>25 환경에서 breakout의 엣지가 가장 강함
- MR은 ADX<25 필터로 자체적으로 진입이 줄지만, base_risk도 추가 축소하여 이중 안전망
- **breakout 0.025**: 기본 0.020에서 25% 증가. TREND에서 적극 활용
- **mr 0.005**: 기본 0.015에서 67% 감소. 혹시 ADX<25 종목이 있어도 소규모만

RANGING regime:
- MR 전략의 본거지. ADX<25 종목이 많아 진입 기회 풍부
- breakout은 ADX<25에서 자체 차단되지만, 간헐적 ADX>25 종목을 위해 최소 유지
- **mr 0.022**: 기본 0.015에서 47% 증가. RANGING에서 적극 활용
- **breakout 0.008**: 기본 0.020에서 60% 감소

HIGH_VOLATILITY regime:
- 전체 포지션 축소 (max_positions 5 -> 3)
- MR이 약간 유리: 급락 후 반등(mean reversion)이 high vol에서 발생
- 하지만 양쪽 다 보수적: SL hit 확률 높아짐
- **breakout 0.008**: 변동성 확대 시 breakout의 false signal 위험
- **mr 0.012**: 기본보다 약간 축소하되 MR 엣지 활용

UNCERTAIN regime:
- 균등 배분. 어느 전략이 유리한지 불명확
- 현금 버퍼 20% (max_positions 4)
- **양쪽 0.015**: 기본값 대비 breakout은 소폭 축소, MR은 동일

### 2.3 전환 규칙

**Strat-3 (Risk) -- 스무딩 메커니즘**:

```
Regime 전환 규칙:
1. 새 regime이 3일 연속 감지되어야 전환 확정
2. 확정 전까지는 이전 regime 유지
3. 확정 시 즉시 새 배분 적용 (batch simulator에서 점진적 전환은 불필요하게 복잡)
```

| 상황 | 처리 |
|------|------|
| Day 1-2: TREND 감지 | 이전 regime 유지 |
| Day 3: TREND 3일 연속 | regime = TREND 확정, 배분 즉시 적용 |
| Day 4: RANGING 감지 | regime_pending = RANGING, 카운트 시작 |
| Day 5: TREND 다시 | pending 리셋, TREND 유지 |

이 3일 확인 규칙은:
- 일시적 변동에 의한 잦은 전환 방지
- 포지션 슬롯 경쟁에서의 불안정성 제거
- 기존 RegimeDetector의 설계 철학과 일관

**위험 완화**: 전환 시 기존 포지션은 건드리지 않음. 새 진입에만 적용.
- TREND에서 RANGING으로 전환되어도 기존 breakout 포지션은 자체 exit rule로 관리
- "regime 변경으로 강제 청산"은 하지 않음 (과도한 거래비용 + whipsaw 위험)

### 2.4 Regime 배분의 P1/P2 예상 효과

**Strat-2 (Quant) -- 시나리오 분석**:

P1 (2024-03 ~ 2025-02, Bull market):
- 예상 regime 분포: TREND 50%, RANGING 20%, HIGH_VOL 10%, UNCERTAIN 20%
- breakout 가중평균 risk: 0.025*0.5 + 0.008*0.2 + 0.008*0.1 + 0.015*0.2 = **0.0179** (기존 0.020에서 소폭 감소)
- MR 가중평균 risk: 0.005*0.5 + 0.022*0.2 + 0.012*0.1 + 0.015*0.2 = **0.0111** (기존 rsi_mr 0.007 + cons_down 0.012의 가중 수준)
- **효과**: TREND 기간 동안 MR risk가 0.005로 급감 -> P1의 MR 대규모 손실 구조적 방지

P2 (2025-03 ~ 2026-02, Mixed market):
- 예상 regime 분포: TREND 30%, RANGING 35%, HIGH_VOL 15%, UNCERTAIN 20%
- breakout 가중평균 risk: 0.025*0.3 + 0.008*0.35 + 0.008*0.15 + 0.015*0.2 = **0.0145**
- MR 가중평균 risk: 0.005*0.3 + 0.022*0.35 + 0.012*0.15 + 0.015*0.2 = **0.0140**
- **효과**: RANGING이 많은 P2에서 MR이 적극적으로 거래 -> cons_down의 P2 수익 재현

핵심 가치: **P1에서 MR 손실을 구조적으로 제한하면서, P2에서 MR 수익을 보존**

이것이 기존 파라미터 튜닝(ADX_MAX 조정 등)과 근본적으로 다른 점이다. 파라미터 튜닝은 "MR의 진입 빈도를 줄임" (양날의 검), Active Allocation은 "MR의 포지션 크기를 regime에 따라 동적 조절" (정밀 타격).

---

## Task 3: Batch Simulator Regime Detection 구현

### 3.1 Regime 감지 방법

**Strat-4 (Analyst) -- 데이터 소스 선정**:

| 방법 | 장점 | 단점 | 판정 |
|------|------|------|------|
| SPY 단독 | 시장 전체 대표 | bars_by_symbol에 SPY 필요 | 후보 |
| 유니버스 ADX 중앙값 | 데이터 별도 불필요 | 유니버스 편향 가능 | **최종 선택** |
| VIX proxy (BB width) | 변동성 잡기 좋음 | 추세 판단 약함 | 보조 지표로 활용 |

**최종 방법: Universe-Wide Regime Detection**

매 거래일, 이미 계산된 심볼별 인디케이터에서 ADX와 BB width를 수집하여 유니버스 수준의 regime을 판단.

```python
def _detect_universe_regime(self, symbol_indicators: dict[str, dict]) -> MarketRegime:
    """유니버스 전체의 ADX, BB width 분포로 portfolio-level regime 결정."""

    adx_values = []
    bb_width_ratios = []
    atr_ratios = []

    for sym, ind in symbol_indicators.items():
        adx = ind.get("ADX_14")
        bb_width = ind.get("BBANDS_20", {}).get("width")
        atr = ind.get("ATR_14")
        close = ...  # current close price

        if adx is not None:
            adx_values.append(adx)
        if bb_width is not None and self._bb_width_avg.get(sym):
            bb_width_ratios.append(bb_width / self._bb_width_avg[sym])
        if atr is not None and close > 0:
            atr_ratios.append(atr / close)

    if not adx_values:
        return MarketRegime.UNCERTAIN

    median_adx = sorted(adx_values)[len(adx_values) // 2]
    median_bb_ratio = sorted(bb_width_ratios)[len(bb_width_ratios) // 2] if bb_width_ratios else 1.0
    median_atr_ratio = sorted(atr_ratios)[len(atr_ratios) // 2] if atr_ratios else 0.02

    # 기존 RegimeDetector와 동일한 분류 기준 적용
    return self._regime_detector.classify(
        adx=median_adx,
        bb_width=median_bb_ratio,   # 실제로는 ratio를 직접 넘김
        bb_width_avg=1.0,           # 이미 ratio 계산 완료이므로
        atr_ratio=median_atr_ratio,
    )
```

### 3.2 Regime 평가 빈도

**매일 (daily)**. 이유:
- batch_simulator는 일간 바 기반
- weekly로 하면 regime 전환 감지가 5-7일 지연 -> 손실 누적
- daily 감지 + 3일 확인 규칙 = 실질적으로 3일 지연 (적절)

### 3.3 구현 아키텍처

**Strat-2 (Quant) -- BatchBacktester 클래스 변경점**:

```python
class BatchBacktester:
    def __init__(self, ...):
        # 기존 상태 변수에 추가
        self._regime_detector = RegimeDetector()
        self._current_regime: MarketRegime = MarketRegime.UNCERTAIN
        self._pending_regime: MarketRegime | None = None
        self._pending_regime_days: int = 0
        self._regime_confirmation_days: int = 3   # 확인 필요 일수

        # BB width 이동평균 추적 (symbol별)
        self._bb_width_history: dict[str, deque[float]] = {}

        # Regime-aware 배분 테이블
        self._REGIME_ALLOCATION: dict[MarketRegime, dict] = {
            MarketRegime.TREND: {
                "base_risk": {"breakout_momentum": 0.025, "adaptive_mean_reversion": 0.005},
                "max_positions": 5,
            },
            MarketRegime.RANGING: {
                "base_risk": {"breakout_momentum": 0.008, "adaptive_mean_reversion": 0.022},
                "max_positions": 5,
            },
            MarketRegime.HIGH_VOLATILITY: {
                "base_risk": {"breakout_momentum": 0.008, "adaptive_mean_reversion": 0.012},
                "max_positions": 3,
            },
            MarketRegime.UNCERTAIN: {
                "base_risk": {"breakout_momentum": 0.015, "adaptive_mean_reversion": 0.015},
                "max_positions": 4,
            },
        }
```

**일간 루프 변경** (`run()` 메서드):

```python
for day_idx, trading_date in enumerate(all_dates):
    # ... 기존 Step 1-3 ...

    # === NEW: Step 3.5 -- Universe Regime Detection ===
    if day_bars:
        universe_indicators = self._collect_universe_indicators(
            day_bars, symbol_histories, symbol_ind_engines
        )
        raw_regime = self._detect_universe_regime(universe_indicators, day_bars)
        self._update_regime_state(raw_regime)

    # ... Step 4 (equity) ...

    # === MODIFIED: Step 5 -- Evening scan with regime-aware sizing ===
    # _calculate_qty() 내부에서 self._current_regime을 참조하여
    # base_risk를 동적으로 결정
```

**포지션 사이징 변경** (`_calculate_qty()` 메서드):

```python
def _calculate_qty(self, equity, fill_price, stop_distance, gdr_risk_mult, strategy):
    # 기존: 정적 _STRATEGY_BASE_RISK[strategy] 사용
    # 변경: regime에 따른 동적 base_risk 사용

    regime_alloc = self._REGIME_ALLOCATION[self._current_regime]
    base_risk = regime_alloc["base_risk"].get(strategy, _DEFAULT_BASE_RISK)

    # GDR/safety-net 로직은 기존과 동일하게 적용
    effective_risk = base_risk * gdr_risk_mult

    # ... 나머지 로직 동일 ...
```

**max_positions도 동적 적용**:

```python
# _execute_pending_entries()에서
regime_alloc = self._REGIME_ALLOCATION[self._current_regime]
effective_max_positions = regime_alloc["max_positions"]

if total_positions >= effective_max_positions:
    break
```

### 3.4 BB Width 이동평균 관리

RegimeDetector.classify()에 bb_width_avg가 필요하므로:

```python
def _update_bb_width_history(self, sym: str, bb_width: float) -> None:
    if sym not in self._bb_width_history:
        self._bb_width_history[sym] = deque(maxlen=20)
    self._bb_width_history[sym].append(bb_width)

def _get_bb_width_avg(self, sym: str) -> float:
    hist = self._bb_width_history.get(sym, deque())
    if len(hist) < 5:
        return 0.0
    return sum(hist) / len(hist)
```

### 3.5 Regime 상태 전환 로직

```python
def _update_regime_state(self, detected_regime: MarketRegime) -> None:
    """3일 연속 확인 규칙으로 regime 전환 관리."""

    if detected_regime == self._current_regime:
        # 현재 regime과 동일 -> pending 리셋
        self._pending_regime = None
        self._pending_regime_days = 0
        return

    if detected_regime == self._pending_regime:
        # 같은 새 regime 연속 감지
        self._pending_regime_days += 1
        if self._pending_regime_days >= self._regime_confirmation_days:
            # 3일 연속 확인 -> 전환 확정
            old_regime = self._current_regime
            self._current_regime = detected_regime
            self._pending_regime = None
            self._pending_regime_days = 0
            logger.info(
                "Regime transition: %s -> %s (confirmed after %d days)",
                old_regime.value, detected_regime.value,
                self._regime_confirmation_days,
            )
    else:
        # 다른 새 regime 감지 -> pending 리셋 후 새로 시작
        self._pending_regime = detected_regime
        self._pending_regime_days = 1
```

---

## 4. 통합 아키텍처 다이어그램

```
                    +-----------------------+
                    |   Universe Bars       |
                    |   (50 symbols/day)    |
                    +----------+------------+
                               |
                    +----------v------------+
                    | Indicator Engine      |
                    | (RSI, ADX, BB, ATR,   |
                    |  EMA5, EMA21, EMA50)  |
                    +----------+------------+
                               |
              +----------------+----------------+
              |                                 |
    +---------v----------+           +----------v---------+
    | Universe Regime    |           | Strategy Engine     |
    | Detection          |           |                     |
    | (median ADX/BB     |           | +- breakout_mom -+ |
    |  across universe)  |           | |  ADX >= 25     | |
    +--------+-----------+           | |  10d breakout  | |
             |                       | +----------------+ |
    +--------v-----------+           |                     |
    | Regime State       |           | +- adaptive_mr --+ |
    | (3-day confirm)    |           | |  ADX < 25      | |
    | TREND / RANGING /  |           | |  Gate A (BB)   | |
    | HIGH_VOL / UNCERT  |           | |  Gate B (cons) | |
    +--------+-----------+           | +----------------+ |
             |                       +--------+-----------+
             |                                |
    +--------v------------------------------- v----------+
    |              Active Allocation Engine               |
    |                                                     |
    |  TREND:    BK=0.025 / MR=0.005 / max_pos=5        |
    |  RANGING:  BK=0.008 / MR=0.022 / max_pos=5        |
    |  HIGH_VOL: BK=0.008 / MR=0.012 / max_pos=3        |
    |  UNCERTAIN:BK=0.015 / MR=0.015 / max_pos=4        |
    +---------------------+------------------------------+
                          |
               +----------v-----------+
               | Position Sizing      |
               | (regime_risk * GDR   |
               |  * ATR-based qty)    |
               +----------+-----------+
                          |
               +----------v-----------+
               | Signal Ranking       |
               | + Gap Filter         |
               | + Entry Execution    |
               +----------------------+
```

---

## 5. 제거 대상 전략 및 코드 정리

### 5.1 제거 전략

| 전략 | 현재 상태 | 제거 이유 |
|------|----------|----------|
| rsi_mean_reversion | Active | adaptive_mr로 대체 (더 넓은 진입 게이트) |
| consecutive_down | Active | adaptive_mr Gate B로 흡수 |
| ema_cross_trend | Disabled (주석 처리) | 이미 비활성. 정리 |

### 5.2 변경 파일 목록

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `autotrader/strategy/adaptive_mean_reversion.py` | **신규 생성** | 새 MR 전략 |
| `autotrader/backtest/batch_simulator.py` | **대규모 수정** | 2전략 + regime detection + active allocation |
| `autotrader/execution/exit_rules.py` | **수정** | adaptive_mr exit 파라미터 추가 |
| `autotrader/portfolio/regime_detector.py` | 수정 없음 | 기존 classify() 재활용 |
| `autotrader/strategy/rsi_mean_reversion.py` | 유지 (batch_sim에서 제외) | 코드는 보존, import만 제거 |
| `autotrader/strategy/consecutive_down.py` | 유지 (batch_sim에서 제외) | 코드는 보존, import만 제거 |

---

## 6. Risk Assessment

### Strat-3 (Risk Manager) -- 위험 분석

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| adaptive_mr이 cons_down보다 성과 약화 | Medium | High (P2 수익 감소) | Gate B가 cons_down 로직 정확히 복제. 추가 Gate A로 수익원 확대 |
| Regime 오판 (RANGING인데 TREND 판정) | Medium | Medium (MR risk 축소) | 3일 확인 규칙으로 완화. 오판 시에도 MR 자체 ADX<25 필터가 2중 안전망 |
| 유니버스 중앙값이 시장 전체를 대표 못함 | Low | Medium | 50종목이면 S&P500의 대표적 샘플. 충분히 robust |
| 2전략으로 축소 시 diversification 감소 | Low | Low | ADX 25 경계로 완전 상보적. 1전략이 침묵할 때 다른 전략이 활성 |
| Gate A + Gate B 동시 발동으로 과도한 진입 | Low | Low | 동일 심볼에서는 1회만 진입. 포지션 cap이 제한 |
| base_risk 동적 변경이 GDR와 충돌 | Low | Medium | GDR는 base_risk에 승수를 적용. 순서: regime_risk * gdr_mult. 호환됨 |

### 6.1 Overfitting Assessment

| 요소 | Overfitting 위험 | 근거 |
|------|-----------------|------|
| Gate A (BB %B<0.20, RSI<40) | Low | 학술적으로 검증된 MR 시그널. 기존보다 완화된 threshold |
| Gate B (3+down, RSI<50) | Very Low | cons_down의 검증된 로직 그대로 흡수 |
| Regime allocation 수치 | Medium | 정확한 % 선택은 judgment call. 극단적이지 않은 범위 사용 |
| 3일 확인 규칙 | Low | 일반적인 signal confirmation 패턴 |
| ADX 25 경계 | Very Low | breakout의 기존 ADX_MIN=25와 자연스럽게 정합 |

**총평**: 새 아키텍처의 핵심 설계 결정은 기존 검증된 로직(cons_down, breakout)에 기반하므로 overfitting 위험이 전반적으로 Low. regime allocation의 구체적 수치(0.025 vs 0.008 등)에 약간의 judgment가 포함되나, 방향성(TREND=breakout 우위, RANGING=MR 우위)은 자명하다.

---

## 7. 성공 기준

### 7.1 MVP 검증 (첫 백테스트)

| Metric | P1 Target | P2 Target | 근거 |
|--------|-----------|-----------|------|
| adaptive_mr 거래수 | 15-35건 | 15-35건 | 기존 rsi_mr+cons_down 합산과 유사 |
| adaptive_mr PnL | > -$500 | > +$2,000 | P1 손실 대폭 축소 (현재 -$3,562) |
| breakout PnL | > +$300 | > +$500 | 기존 수준 유지 |
| Portfolio Return | > -1.0% | > +4.0% | 양 기간 목표 |
| Sharpe | > 0.30 | > 0.40 | 현재 P1=0.233, P2=0.409에서 개선 |
| Regime 전환 횟수 | 3-8회 | 3-8회 | 과도한 전환 아님 확인 |
| TREND 기간 MR 손실 | > -$200 | N/A | regime 배분 효과 핵심 확인 |

### 7.2 장기 목표

| Metric | Target | 근거 |
|--------|--------|------|
| 양 기간 양수 수익 | 필수 | 시스템 robustness |
| Sharpe (양 기간 평균) | >= 0.40 | 21차 패널의 현실적 상한 추정 |
| MaxDD | < 10% | 소규모 계좌 보호 |
| MR-Breakout 상관계수 | < 0.20 | 상보적 전략 설계 확인 |

---

## 8. 구현 순서 권고

**Strat-1 (Swing) -- 단계적 구현 제안**:

### Phase 1: 전략 구현 (독립적)
1. `adaptive_mean_reversion.py` 생성 (Gate A + Gate B)
2. `exit_rules.py`에 adaptive_mr 파라미터 추가
3. 단위 테스트 작성 및 통과

### Phase 2: Batch Simulator 통합 (regime 없이)
1. batch_simulator에서 rsi_mr, cons_down 제거, adaptive_mr 추가
2. 정적 base_risk로 baseline 백테스트 실행
3. 결과 검증: 거래 수, Gate A/B 비율, exit reason 분포

### Phase 3: Regime Detection 추가
1. batch_simulator에 universe regime detection 추가
2. 3일 확인 규칙 구현
3. regime 로그 기록 (어떤 날에 어떤 regime인지)

### Phase 4: Active Allocation 연결
1. regime -> base_risk / max_positions 동적 조정
2. 전체 백테스트 실행 (P1, P2)
3. regime 배분 효과 분석

### Phase 5: 검증 및 조정
1. P1/P2 결과 비교 분석
2. 필요 시 regime allocation 수치 미세 조정
3. 패널 리뷰

---

## 9. Panel Vote

| Team Member | Vote | Comment |
|-------------|------|---------|
| Strat-1 (Swing) | **APPROVE** | "Gate B가 cons_down을 정확히 흡수하고, Gate A가 진입 기회를 넓힘. ADX 25 경계가 breakout과 깔끔하게 분리. 실전 관점에서 건전한 설계." |
| Strat-2 (Quant) | **APPROVE** | "Active allocation이 파라미터 튜닝의 천장을 구조적으로 돌파하는 방법. regime별 base_risk 조정은 수학적으로 Sharpe 분자(수익)와 분모(변동성)를 동시에 개선한다." |
| Strat-3 (Risk) | **APPROVE with NOTE** | "regime allocation 수치의 정확한 값은 첫 백테스트 후 미세 조정 필요. 방향성은 올바르나, TREND 시 mr=0.005가 너무 낮을 수 있다. 0.008까지 올리는 것도 고려." |
| Strat-4 (Analyst) | **APPROVE** | "유니버스 중앙값 기반 regime detection이 SPY 단독보다 robust. 21차 패널의 핵심 발견(batch sim regime-blind)을 정면으로 해결하는 구조." |

**전원 승인. 구현 진행.**

---

## 10. 부록: 정확한 파라미터 사전

### adaptive_mean_reversion 파라미터

```yaml
# Indicator parameters
RSI_PERIOD: 14
BB_PERIOD: 20
BB_STD: 2.0
ADX_PERIOD: 14
ATR_PERIOD: 14
EMA_LONG_PERIOD: 50      # 장기 추세 필터
EMA_SHORT_PERIOD: 5      # 단기 exit target

# Common filters
ADX_MAX: 25.0             # breakout의 ADX_MIN과 정확히 상보
ADX_SLOPE_MAX: 2.0        # 3-bar ADX slope 제한 (추세 전환 감지)

# Gate A: BB Oversold
GATE_A_PCT_B_MAX: 0.20    # BB %B 상한
GATE_A_RSI_MAX: 40.0      # RSI 상한

# Gate B: Consecutive Drop
GATE_B_MIN_DOWN_DAYS: 3   # 최소 연속 하락일
GATE_B_RSI_MAX: 50.0      # RSI 상한

# Exit parameters
SL_ATR_MULT: 1.5          # Stop Loss
TP_ATR_MULT: 2.5          # Take Profit
EXIT_BB_PCT_B: 0.70       # BB target exit
EXIT_RSI: 60.0            # RSI target exit
EXIT_EMA_MIN_BARS: 2      # EMA(5) exit 최소 보유일
MAX_HOLD_DAYS: 7          # 최대 보유일
```

### Regime Allocation 파라미터

```yaml
TREND:
  breakout_momentum: 0.025
  adaptive_mean_reversion: 0.005
  max_positions: 5

RANGING:
  breakout_momentum: 0.008
  adaptive_mean_reversion: 0.022
  max_positions: 5

HIGH_VOLATILITY:
  breakout_momentum: 0.008
  adaptive_mean_reversion: 0.012
  max_positions: 3

UNCERTAIN:
  breakout_momentum: 0.015
  adaptive_mean_reversion: 0.015
  max_positions: 4

REGIME_CONFIRMATION_DAYS: 3
```

### RegimeDetector 분류 기준 (기존 유지)

```yaml
TREND: ADX >= 25 AND bb_width_ratio >= threshold
RANGING: ADX < 20 AND bb_width_ratio <= 0.8
HIGH_VOLATILITY: ADX < 20 AND bb_width_ratio >= 1.0 AND atr_ratio > 0.03
UNCERTAIN: 위 어디에도 해당하지 않음
```

---

*Design session concluded. 전략팀 전원 승인. 개발팀 구현 대기.*
*Phase 1부터 순차적으로 진행할 것을 권고.*
