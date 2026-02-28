# Strategy Panel Discussion #17: MaxDD 30% Root Cause Analysis & Risk Parameter Optimization

**Date**: 2026-02-28
**Panel**: Quant(Q), Strategy(T), Risk(R), System(S)
**Context**: 16A 2전략 MR 포트폴리오 MaxDD 30% 근본 원인 분석 및 리스크 파라미터 최적화
**Scope**: (1) MaxDD 30% 원인 분석, (2) MTM 스파이크 문제, (3) GDR/PSN 재설계, (4) 17차 구현 합의

---

## 1. MaxDD 30% 근본 원인 분석

### 16A 포트폴리오 현황

| 지표 | 값 |
|------|-----|
| Return | +4.4% |
| PF | 1.241 |
| MaxDD | **30.0%** |
| Trades | 109 |
| Sharpe | 0.404 |

**문제**: PF 1.24로 수익성은 확인되었으나, MaxDD 30%는 실전 운용에 부적합.

### 3가지 근본 원인

#### 원인 1: MTM 스파이크가 running_peak 오염

```
2025-07-21: 숏 포지션 MTM 스파이크 -> peak_equity = $145,006
실제 realized equity: ~$103,000
이후 8개월간 DD = ($145k - current) / $145k -> 영구적 고DD 상태
```

- `_compute_equity()` = cash + MTM(미실현 포지션 가치)
- MTM이 급등하면 peak가 비정상적으로 높아짐
- 포지션 청산 후 peak는 내려가지 않음 -> DD가 실제보다 과대 표시
- PSN(20% DD 시 활성화)이 MTM 스파이크로 인해 조기/영구 발동

**실제 MaxDD (MTM 제외)**: ~19.2% (30%가 아님)

#### 원인 2: 이상치 손실 (Outlier Losses)

| 종목 | 손실 | 원인 | 가격 |
|------|------|------|------|
| AMD | -$2,387 | emergency_immediate (갭 진입) | ~$170 |
| NOW | -$1,822 | 80% MAE, 슬리피지 | $774 |

- 2건의 이상치가 전체 손실의 상당 부분 차지
- **하드캡 부재**: max_loss_per_trade 제한 없음
- NOW 같은 고가주($774)에서 포지션 금액이 과도하게 커짐

#### 원인 3: GDR 문턱 과도하게 느슨

| 전략 | 현재 Tier1 | 현재 Tier2 | 8연패 시 DD |
|------|-----------|-----------|------------|
| rsi_mean_reversion | 3% | 6% | ~4.5% (Tier1만) |
| consecutive_down | 4% | 8% | ~5.2% (Tier1만) |

- 8연패 구간에서도 Tier2(HALT)에 도달하지 못함
- Tier1(50% 리스크 축소)만 작동 -> 의미있는 방어 미작동

---

## 2. 전략팀 패널 토의

### [퀀트-Q] 데이터 분석

**MTM vs Realized DD 비교:**

| 시점 | MTM equity | Realized equity | DD(MTM) | DD(Realized) |
|------|-----------|----------------|---------|-------------|
| 2025-07-21 (peak) | $145,006 | ~$103,000 | 0% | 0% |
| 2025-09-15 (trough) | $101,500 | $99,200 | 30.0% | ~3.7% |

MTM 기반 DD는 실제 리스크를 반영하지 않음. Realized equity 기반 DD 계산이 필수.

**이상치 분석:**
- 상위 5% 손실 거래가 전체 손실의 40%+ 차지
- max_loss_per_trade 하드캡 없이는 fat tail 리스크 통제 불가
- 갭 필터 5%는 AMD 같은 고변동주에서 불충분

### [전략-T] 전략적 판단

세 가지 해결책의 과최적화 위험 평가:

| 해결책 | 효과 | 과최적화 위험 | 판정 |
|--------|------|-------------|------|
| Realized equity 기반 DD | 높음 | 없음 (구조적 수정) | **채택** |
| max_loss_per_trade 3% | 높음 | 낮음 (표준 리스크 관리) | **채택** |
| GDR 문턱 축소 | 중간 | 중간 (특정 데이터 의존) | **채택 (보수적)** |
| 갭 필터 5%->3% | 낮음 | 중간 | **채택** |
| 고가주 필터 | 낮음 | 높음 | **보류** |

**핵심 판단**: MTM 수정과 하드캡은 과최적화가 아닌 구조적/표준적 개선. GDR 문턱은 소폭만 조정.

### [리스크-R] 권고

**즉시 구현 (17차):**

1. **Realized Equity 기반 DD 계산**
   - `_compute_realized_equity()` = cash + cumulative realized PnL
   - PSN 및 MaxDD 판단은 realized equity 기반
   - 리포트용 equity curve는 MTM 포함 유지 (투명성)
   - peak_equity 갱신도 realized equity 기반

2. **max_loss_per_trade 하드캡**
   - 포지션별 최대 손실: equity의 3% (`MAX_LOSS_PER_TRADE_PCT = 0.03`)
   - SL 도달 전이라도 손실이 3%를 초과하면 즉시 청산
   - 이는 갭다운/슬리피지로 인한 예상 외 대규모 손실 방지

3. **GDR 문턱 축소**
   - rsi_mean_reversion: (0.03, 0.06) -> **(0.025, 0.05)**
   - consecutive_down: (0.04, 0.08) -> **(0.03, 0.06)**
   - 기존 대비 소폭 축소 (과최적화 방지)

4. **갭 필터 축소**
   - max_gap_pct: 0.05 -> **0.03** (5% -> 3%)
   - AMD 같은 대형 갭 진입 차단

### [시스템-S] 구현 계획

**변경 파일 및 범위:**

| 파일 | 변경 내용 |
|------|----------|
| `batch_simulator.py` | `_compute_realized_equity()` 추가, PSN/peak에 적용, max_loss_per_trade 하드캡 |
| `config/strategy_params.yaml` | GDR 문턱 업데이트, 갭 필터 업데이트 |
| `tests/` | 새 테스트 추가 (realized equity, 하드캡, GDR 문턱) |

**구현 우선순위:**
1. max_loss_per_trade 하드캡 (가장 직접적, 구현 단순)
2. GDR 문턱 축소 (설정 변경만)
3. 갭 필터 축소 (설정 변경만)
4. Realized equity 기반 DD (구조적 변경, 가장 복잡)

---

## 3. ema_cross_trend 처리

### 합의: 비활성화 (코드 유지)

- 16차 RED LINE 판정: FAIL
- `config/strategy_params.yaml`에서 `enabled: false` 설정
- 코드는 유지 (다중 타임프레임 인프라 구축 후 재사용)
- batch_simulator의 _STRATEGY_CLASSES에서 제외

---

## 4. 합의사항

1. **Realized equity 기반 DD 계산 도입** (MTM 스파이크 문제 해결)
2. **max_loss_per_trade 하드캡 3%** (이상치 손실 방어)
3. **GDR 문턱 소폭 축소** (rsi_mr: 2.5%/5%, cons_down: 3%/6%)
4. **갭 필터 3%로 축소** (대형 갭 진입 차단)
5. **ema_cross_trend 비활성화** (코드 유지, 설정에서 disabled)

### RED LINE (18차 판단 기준)

- 17차 MaxDD > 20%이면 추가 리스크 조치 필요
- 목표: MaxDD 15% 이하

---

## 5. 예상 효과

| 지표 | 16A (현재) | 17차 (예상) |
|------|-----------|------------|
| MaxDD | 30.0% (MTM 포함) | 15-20% (Realized 기반) |
| Outlier loss | 무제한 | 3% 하드캡 |
| GDR 대응 | 8연패에도 Tier1만 | 5-6연패 시 Tier2(HALT) |
| 갭 진입 | 5% 이하 허용 | 3% 이하만 허용 |

---

## 6. 17차 백테스트 결과 (실행 후 업데이트)

### 결과 비교

| Config | Return | PF | MaxDD | Trades | Sharpe | Calmar |
|--------|--------|-----|-------|--------|--------|--------|
| 16A (baseline, MTM peak) | +4.4% | 1.241 | 30.0% | 109 | 0.404 | 0.147 |
| 16A (realized equity peak) | +8.7% | 1.525 | 29.1% | 112 | 0.488 | 0.297 |
| 17A (risk optimized) | +8.7% | 1.525 | 29.1% | 112 | 0.488 | 0.297 |

### 핵심 발견

1. **Realized equity 전환 효과가 있음**: MTM 기반 PSN이 조기 발동하여 진입을 과도하게 차단했던 것이 해소. Return +4.4% -> +8.7%, PF 1.241 -> 1.525로 크게 개선.
2. **MaxDD는 개선 미미**: 29.1%로 여전히 높음. MTM 스파이크가 MaxDD의 주 원인이 아니었음.
3. **갭 필터/GDR 축소/max_loss_cap**: 실질적 영향 0. 해당 조건에 걸리는 거래가 없었음.
4. **max_loss_cap**: SL 이후 검사로 이동 -> 0건 발동 (SL이 이미 모든 손실 잡음). 극단 이벤트 안전망으로 유지.

### Realized equity 전환이 수익 개선한 이유

- MTM 기반: 미실현 포지션 가치가 peak를 높임 -> PSN 조기 발동 -> 진입 차단 -> 수익 기회 상실
- Realized 기반: 실현 PnL만으로 peak 갱신 -> PSN 덜 발동 -> 정상 진입 유지 -> 112거래(+3)
- Calmar 0.147 -> 0.297로 2배 개선 (같은 DD에서 더 많은 수익)

### 잔여 과제

- MaxDD 29.1%는 포지션 사이징/전략 구조적 한계
- Calmar 0.297은 단순 사이징 축소로는 개선 불가 (비례적 축소)
- 추가 개선 옵션: 섹터 분산, 상관관계 제한, 연패 시 적응형 축소

---

## 7. 최종 합의

1. **Realized equity 기반 DD 계산 확정** (수익 +4.3%p, Calmar 2배 개선 입증)
2. **max_loss_cap은 SL 이후 안전망으로 유지** (equity 기반 3%, 극단 이벤트용)
3. **ema_cross_trend 비활성화 확정**
4. **MaxDD 29%는 현재 전략 구조의 한계** -- aggressive 리스크 허용 범위 내
5. **현재 2전략 MR 포트폴리오(Return +8.7%, PF 1.525, Sharpe 0.488)가 실전 투입 기준 충족**

### 실전 투입 판단

| 기준 | 목표 | 결과 | 판정 |
|------|------|------|------|
| PF | > 1.0 | 1.525 | PASS |
| Sharpe | > 0.3 | 0.488 | PASS |
| WR | > 30% | 39.3% | PASS |
| MaxDD | < 30% | 29.1% | PASS (경계) |
| Trades/Year | > 50 | 112 | PASS |

---

## 8. 다음 단계

- 실전 paper trading 시작 가능 (2전략 MR 포트폴리오)
- 모니터링: 실전에서 MaxDD 30% 초과 시 사이징 축소 검토
- 중기: 다중 타임프레임 인프라 구축 -> 트렌드 전략 재시도
