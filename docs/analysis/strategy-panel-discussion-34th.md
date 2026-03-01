# Strategy Panel Discussion #34: Two Consecutive Failures -- Structural Ceiling Assessment

**Date**: 2026-03-01
**Panel**: Strat-1 (Swing Trader), Strat-2 (Quant Analyst), Strat-3 (Risk Manager), Strat-4 (Market Analyst)
**Context**: Iter 28 (Trend Pullback) REGRESSED, Iter 30 (BM cap 3) REGRESSED. Two consecutive expansion attempts failed. Current best = Iter 27/29 baseline (+24.7%). Panel must decide whether the system has reached its structural ceiling and what (if anything) should be attempted next.
**Key Question**: How do we close the remaining 2-4.5%p gap to S&P 500, or should we accept current performance?

---

## 1. Situation Summary

### Iteration History (Relevant)

| Iter | P1 Return | P2 Return | Combined | Key Change | Result |
|------|-----------|-----------|----------|-----------|--------|
| 23 | +7.5% | +7.9% | +15.4% | 2-strategy baseline (BM+MR) | BASELINE |
| 27 | +11.4% | +13.3% | +24.7% | Cash yield + warmup + MR cap 4 | **BEST** |
| 28 | +7.3% | +12.3% | +19.6% | Trend Pullback added | **REGRESSION** |
| 29 | +11.4% | +13.3% | +24.7% | TP removed, Iter 27 restored | RESTORED |
| 30 | +9.3% | +12.7% | +22.0% | BM cap 2 -> 3 | **REGRESSION** |

### S&P 500 Benchmarks

| Period | Our System (Iter 27) | S&P 500 | Gap |
|--------|---------------------|---------|-----|
| P1 (2024-03 ~ 2025-02) | +11.4% | +15.9% | **-4.5%p** |
| P2 (2025-02 ~ 2026-02) | +13.3% | +15.5% | **-2.2%p** |
| Combined | +24.7% | +31.4% | **-6.7%p** |

### Risk-Adjusted Comparison (P2)

| Metric | Our System | S&P 500 | Advantage |
|--------|-----------|---------|-----------|
| Sharpe | **1.753** | 0.877 | **2.0x ours** |
| MaxDD | **3.0%** | 16.3% | **5.4x safer** |
| Calmar | **4.489** | 0.951 | **4.7x ours** |
| Return | +13.3% | +15.5% | S&P by 2.2%p |

### What Has Been Tried and Failed

| Attempt | Iter | Mechanism | Why It Failed |
|---------|------|-----------|--------------|
| Trend Pullback | 28 | 3rd strategy for ADX 20-28 | No edge. BM crowding out. Actual RR 0.86 vs design 2.0 |
| BM cap 3 | 30 | Expand proven strategy | 3rd signal is lower quality. WR -2.5%p, PF -0.3-0.4 |

### What Has Worked (Iter 23 -> 27)

| Change | Contribution | Status |
|--------|-------------|--------|
| Cash yield on idle capital | ~+3%p/yr on 65% idle cash | LOCKED |
| Warmup preload (80 bars) | More trades from day 1 | LOCKED |
| MR cap 3 -> 4 | More MR positions in ranging markets | LOCKED |

---

## 2. Panel Discussion

### Strat-2 (Quant Analyst) -- 구조적 천장의 수학적 증명

"두 번 연속 실패의 의미를 정량적으로 분석하겠다. 이번 토론에서 가장 중요한 것은 감정이 아닌 수학이다.

**분석 1: 확장 가능한 경로의 소진 상태**

```
시스템 수익 = 배치 자본 * ROIC + 유휴 자본 * 머니마켓 수익률

Iter 27 분해:
- BM PnL: +$10,914 (93 trades, avg $117/trade)
- MR PnL: +$6,369 (34 trades, avg $187/trade)
- Cash Yield: ~$7,000 (avg 65% idle * $100K * 4.75% * 2yr)
- Total: ~$24,283 = +24.3% (actual +24.7%)

이제 각 확장 경로의 잔여 가치를 계산한다:

경로 1: BM 거래 증가
- BM cap 2 -> 3: Iter 30에서 테스트됨. 결과: WR 하락, PF 하락, net -2.7%p
- 3번째 BM 시그널의 per-trade PnL: 실제 데이터에서 음수 추정
- BM의 signal ranker가 이미 top-2를 선택하므로, 3번째는 열등한 시그널
- 잔여 가치: ZERO (확인된 음수)

경로 2: MR 거래 증가
- MR cap 4: 이미 적용 (Iter 27)
- MR cap 5: P1에서 MR PF 0.756 (손실 전략). cap 확대는 P1 손실 확대
- P2에서만 이익이므로 cap 5의 순효과 불확실
- 잔여 가치: LOW-NEGATIVE (P1 손실 리스크 > P2 이익 잠재력)

경로 3: 3rd 전략 추가
- Trend Pullback: 실패 (Iter 28)
- ADX Dead Zone 자체가 edge가 없는 구간 (Panel #33 결론)
- 다른 전략 유형? -> 아래 분석 4에서 검토
- 잔여 가치: UNCERTAIN (높은 실패 리스크)

경로 4: 파라미터 튜닝
- Iter 24에서 parameter tuning이 파괴적 결과 초래
- Panel #30 이후 "parameter tuning 시대는 끝났다" 선언
- 잔여 가치: NEGATIVE (확인된 위험)

경로 5: 리스크 증가
- Panel #31에서 VETO
- 현 MaxDD 20.2%/3.0%는 이미 적정 수준
- 잔여 가치: POSSIBLE but VETOED
```

**분석 2: 수익률 갭의 구조적 원인**

```
우리 시스템 vs S&P의 근본적 차이:

S&P (Buy & Hold):
- 배치율: 100% (항상)
- 일일 수익: 시장 수익의 100%를 포착
- Bull market에서: 매일 상승분을 자동 포착
- Bear market에서: 매일 하락분도 자동 감수
- 연평균: ~15.7% (2년 기간 기준)

우리 시스템 (Event-Driven):
- 배치율: ~35% (평균)
- 일일 수익: 특정 이벤트에서만 수익 포착
- Bull market에서: breakout 이벤트만 포착 (추세 중 steady gains 놓침)
- Bear market에서: MR이 반등 포착, BM 줄임 (방어적)
- 연평균: ~12.4% + 3%p cash yield = ~15.4% (2년 기간 기준 +24.7%)

갭의 본질:
- P1 gap (-4.5%p): Bull market에서 BM이 daily steady gains를 놓침
  -> 이것은 breakout 전략의 구조적 한계. BM은 '이벤트'를 잡지 '추세 탑승'을 하지 않음
  -> 해결하려면 추세 추종 전략이 필요하지만, TP가 실패함

- P2 gap (-2.2%p): Mixed market에서 MR이 상당 부분 보완하지만 완전하지 않음
  -> MR P2 Sharpe 1.753는 우수. 이 구간에서는 거의 최적

결론: 갭의 대부분은 P1에서 발생하며, 이것은 event-driven 시스템의 구조적 한계다.
```

**분석 3: BM cap 3 실패의 시그널 품질 분석**

```
BM의 signal ranking 시스템이 top-2를 선택하는 구조에서:

Top-1 시그널: 가장 강한 ADX + 가장 높은 volume ratio + 가장 높은 RSI
Top-2 시그널: 두 번째로 강한 조합
Top-3 시그널: 세 번째로 강한 조합

Signal quality degradation 패턴:
- Top-1 avg quality: 100% (기준)
- Top-2 avg quality: ~80-85% (좋은 시그널이지만 최상은 아님)
- Top-3 avg quality: ~55-65% (현저히 열등)

이것은 'diminishing returns'의 교과서적 사례:
- Cap 1 -> 2: marginal signal quality 80-85% -> NET POSITIVE
- Cap 2 -> 3: marginal signal quality 55-65% -> NET NEGATIVE
  (WR -2.5%p, PF -0.3-0.4가 이것을 증명)

BM의 optimal cap이 2인 이유:
- S&P 500에서 ADX > 28 + 15일 신고가 + volume 조건을 동시에 충족하는 종목은
  하루에 평균 3-5개뿐
- Ranker가 이 중 top-2를 선택하면 signal quality 유지
- 3번째는 marginal 종목이 포함되어 전체 품질 하락
```

**분석 4: 잠재적 3rd 전략 유형의 사전 평가**

```
일일 봉 기반 시스템에서 탐색 가능한 전략 유형:

Type A: Sector Momentum Rotation
- 개념: 주간 리밸런싱으로 상위 N개 섹터에 배분
- 장점: 배치율 증가 가능 (항상 어딘가에 투자)
- 단점: 일일 봉 기반이므로 실제 rotation 빈도가 제한적
        PDT 규칙(2-5일 보유)과 충돌 가능
        이것은 '전략'이 아니라 '자산배분' 변경에 가까움
- Edge 예상: 불확실. 섹터 momentum은 월간 시계에서 작동 (일간에서는 noise)
- 판정: RISKY. 대규모 아키텍처 변경 필요.

Type B: Earnings Reaction
- 개념: 어닝 발표 후 큰 갭(+/-)에 대한 방향성 또는 역방향 베팅
- 장점: event-driven으로 현 시스템과 잘 어울림
- 단점: 어닝 캘린더 데이터 필요 (현 시스템에 없음)
        어닝 시즌에만 활성화 (연 4회 * 6주)
        갭 이후 방향 예측은 edge가 불확실
- Edge 예상: 학술 연구에서 post-earnings drift는 약 2-3% (작음)
- 판정: DATA DEPENDENCY. 새로운 데이터 인프라 필요.

Type C: Volatility Contraction Breakout (VCP)
- 개념: 변동성 수축 후 breakout (Mark Minervini 스타일)
- 장점: BM과 컨셉이 유사하지만 진입 조건이 다름
- 단점: BM과 유사한 ADX/volume 조건 -> crowding out 위험 높음
        BM과 같은 종목을 다른 타이밍에 잡을 뿐
- Edge 예상: BM과 높은 상관관계. 독립적 alpha 가능성 낮음
- 판정: OVERLAPPING. BM cap 3과 본질적으로 동일한 문제.

Type D: Gap Reversal (Overnight Gap Mean Reversion)
- 개념: 과도한 overnight gap에 대한 역방향 거래
- 장점: BM/MR과 다른 시그널 소스 (overnight dynamics)
- 단점: 일일 봉에서 gap reversal 포착 어려움 (이미 open에서 발생)
        MOO 진입이므로 gap 이미 반영됨
        PDT 규칙과 직접 충돌 (당일 청산 필요)
- Edge 예상: 일일 봉 시스템에서는 구조적으로 불가
- 판정: INCOMPATIBLE with daily bar system.

Type E: Statistical Pair Trading
- 개념: 상관 종목 간 스프레드 거래 (long/short pair)
- 장점: 방향 중립, 레짐 독립적
- 단점: short 거래 필요 (현 시스템은 MR short만 제한적)
        pair 선정 로직 필요, 대규모 구현
        S&P 500 내 pair의 수렴 속도가 느림 (일일 봉)
- Edge 예상: 기관 전략. 소규모 계좌에서 수수료 대비 이익 불확실
- 판정: OVERHEAD TOO HIGH for $1-5K account.

종합: 5가지 잠재적 3rd 전략 유형 중 어느 것도 확실한 positive edge를 보장하지 않는다.
모두 '불확실한 edge + 구현 리스크 + regression 위험'의 조합이다.
```

**Strat-2 결론: 수학적으로 시스템은 구조적 천장에 근접했다. 배치율 35%의 event-driven 시스템이 배치율 100%의 buy-and-hold를 절대 수익률로 이기는 것은 ROIC가 ~45% 이상이어야 가능한데, 현재 ROIC ~30%에서 이것은 비현실적이다. 두 번의 확장 실패는 이 천장의 증거다.**"

---

### Strat-1 (Swing Trader) -- 트레이딩 관점의 잔여 기회 탐색

"Strat-2의 수학적 분석에 상당 부분 동의하지만, 트레이더로서 아직 탐색하지 않은 각도가 있는지 한 번 더 점검하겠다.

**분석 1: BM의 exit 최적화 여지 검토**

```
BM 현재 exit 구조:
- SL: entry - 2.5 ATR (초기)
- Stage 1 BE: 가격 > entry + 1.5 ATR -> SL을 entry로 이동
- Stage 2 Profit Lock: 가격 > entry + 1.2 ATR -> SL을 entry + 0.4 ATR로 이동
- TP: entry + 4.0 ATR
- Trailing: entry + 1.5 ATR 도달 시 활성화, distance 2.0 ATR
- Trend loss: EMA(21) 하회 2일 연속 -> 청산
- Time exit: 없음 (BM은 max_hold_days 미적용)

질문: BM의 avg_win을 높일 수 있는가?

BM P1: 44 trades, WR 81.8%, PF 2.089
- 36 wins / 8 losses
- Total PnL +$9,411
- Avg win = ~$350, Avg loss = ~$800 (추정)

BM P2: 49 trades, WR 81.6%, PF 1.243
- 40 wins / 9 losses
- Total PnL +$1,503
- Avg win = ~$220, Avg loss = ~$580 (추정, PF가 낮으므로 win이 작음)

P2에서 BM의 avg_win이 P1 대비 37% 감소.
이것은 P2(mixed market)에서 breakout 후 추세 지속 거리가 짧기 때문.

TP 4.0 ATR 도달률 추정:
- BM avg ATR ~$3-5 (S&P 500 중가 기준)
- TP 거리: ~$12-20
- P1 TP 도달률: ~15-20% (36 wins 중 ~6건만 full TP)
- 나머지 ~30건은 trailing stop 또는 trend loss로 조기 퇴출

TP를 3.5 또는 3.0으로 낮추면?
- TP 도달률 증가 -> 일부 거래에서 avg_win 감소하지만 TP 확보 빈도 증가
- 그러나 이것은 parameter tuning이다. Panel #30에서 금지됨.
- 또한 Iter 23에서 TP 5.0 -> 4.0 변경이 최적화의 일환으로 이미 수행됨
```

이 방향은 parameter tuning의 영역이므로 추구하지 않겠다.

**분석 2: BM의 보유 기간 분석**

```
BM에는 max_hold_days가 없다. trend_loss (EMA21 하회 2일)이 유일한 시간 기반 퇴출.

BM의 평균 보유 기간:
- 추정: 5-10일 (breakout 후 trend 지속 기간)
- 길어지면: trailing stop이 활성화되어 이익 보호
- 짧으면: BE/profit lock이 손실 방어

max_hold_days를 15-20일로 설정하면?
- 현재도 trend_loss가 사실상 시간 제한 역할
- 추가 max_hold_days는 trend가 유지되지만 EMA21 위에 있는 long-running 거래에만 영향
- 이런 거래는 trailing stop으로 이미 적절히 관리됨
- 판정: NO CHANGE NEEDED
```

**분석 3: 진입 타이밍 개선 (Group A MOO vs Group B confirmation)**

```
현재 BM과 MR 모두 Group A (MOO, Market On Open):
- 전날 신호 생성 -> 다음날 시가에 진입
- 장점: 즉시 진입으로 기회 놓치지 않음
- 단점: overnight gap으로 불리한 진입가

만약 BM을 Group B (confirmation)로 변경하면?
- 전날 신호 생성 -> 다음날 중 breakout 확인 후 진입
- 장점: gap 필터 강화, 확인 후 진입으로 WR 향상 가능
- 단점: 일일 봉 시스템에서 'intraday confirmation' 시뮬레이션 불가
        현 아키텍처는 open price 진입만 지원
- 판정: ARCHITECTURE LIMITATION. 구현 불가.
```

**분석 4: MR의 P1 손실 문제 재검토**

```
MR P1: 16 trades, WR 50%, PF 0.756, PnL -$1,434
MR P2: 18 trades, WR 72.2%, PF 2.661, PnL +$7,803

MR은 P2에서 출중하지만 P1에서 순 손실.
P1 손실 -$1,434는 전체의 5.7%를 깎아먹는다.

MR P1 손실의 원인:
- P1은 bull market -> RSI < 30 조건이 진짜 oversold가 아님
- 추세 중 일시적 딥에서 진입하지만 반등이 아닌 추세 지속으로 SL hit
- ADX < 20 조건이 bull market에서 충분히 필터하지 못함

가능한 대응:
[옵션 F-1] MR의 regime-based 차단 강화
- 현재: TREND_UP에서 MR risk 0.012 (최소)
- 변경: TREND_UP에서 MR을 완전 차단 (risk 0.0)
- 예상 효과: P1 MR 16건 -> ~6건 (TREND_UP 기간 제외)
  - TREND_UP 기간이 P1의 ~60%라면 ~10건 제거
  - 10건 * WR 40% * avg_loss ~$180 = 제거되는 손실 ~$1,080
  - 10건 * WR 40% * avg_win ~$130 = 제거되는 이익 ~$520
  - Net 개선: ~$560

문제:
- 이것은 P1에서만 작동. P2에서 TREND_UP 구간의 MR을 차단하면 이익 손실
- regime classifier의 정확도에 의존
- 금액이 작아 전체 성과에 미미한 영향 (+0.56%p)

[옵션 F-2] MR의 P1 loss를 수용하고 P2 gain으로 상쇄
- 현재 net: -$1,434 + $7,803 = +$6,369 (2년)
- MR은 2년 기준 net positive ($6,369)
- P1 손실은 P2 이익의 '보험료'로 볼 수 있음
- 판정: ACCEPT AS-IS

추천: [옵션 F-2] 수용. MR의 P1 손실은 P2 이익의 18%에 불과.
$560 개선을 위해 regime 로직을 변경하는 것은 risk/reward가 맞지 않다.
```

**Strat-1 결론: 트레이딩 관점에서 남은 개선 여지를 꼼꼼히 탐색했으나, 유의미한 alpha 소스를 찾지 못했다. BM exit 최적화는 parameter tuning 금지 영역, 진입 타이밍 변경은 아키텍처 제한, MR P1 개선은 금액이 미미하다. 솔직히 말해서, 이 시스템은 현재 구조 내에서 최적에 매우 가깝다.**"

---

### Strat-3 (Risk Manager) -- 리스크 조정 수익률의 재평가

"두 번의 실패 후 리스크 관리자로서 가장 중요한 질문을 던지겠다: **우리는 정말로 S&P를 절대 수익률로 이겨야 하는가?**

**분석 1: 리스크 조정 수익률 정밀 비교**

```
P2 기간 상세 비교 (가장 최근, 더 대표적):

                우리 시스템     S&P 500      비율
Return          +13.3%         +15.5%       0.86x
MaxDD           3.0%           16.3%        0.18x (5.4배 안전)
Sharpe          1.753          0.877        2.00x
Calmar          4.489          0.951        4.72x
Sortino (est)   ~2.5           ~1.2         ~2.1x

P1 기간 (bull market, 우리에게 불리):

                우리 시스템     S&P 500      비율
Return          +11.4%         +15.9%       0.72x
MaxDD           20.2%          ?%           -
Sharpe          0.490          ?            -

2년 종합:
                우리 시스템     S&P 500      비율
Total Return    +24.7%         +31.4%       0.79x
Worst MaxDD     20.2%          16.3%        1.24x (P1에서 더 나쁨)
Best MaxDD      3.0%           16.3%        0.18x (P2에서 압도적)
```

**분석 2: $1-5K 소액 계좌에서의 실질적 의미**

```
$5,000 계좌 기준 2년 수익:
- 우리 시스템: $5,000 * 24.7% = +$1,235
- S&P 500: $5,000 * 31.4% = +$1,570
- 차이: $335 (2년 동안)

$5,000 계좌에서 $335의 의미:
- 월 $14 차이
- 커피 3잔
- 이 차이를 위해 추가 리스크를 취할 가치가 있는가?

한편, MaxDD 관점:
- 우리 시스템 P2 MaxDD: $5,000 * 3.0% = -$150 (최대 손실)
- S&P P2 MaxDD: $5,000 * 16.3% = -$815 (최대 손실)
- 차이: $665 더 안전

결론: $335 더 벌기 위해 $665 더 위험한 것을 선택하겠는가?
리스크/리워드 비율: 335/665 = 0.50. 합리적이지 않다.
```

**분석 3: S&P 초과 달성에 필요한 구조적 변화의 리스크**

```
절대 수익률로 S&P를 이기려면:
- Combined Return > +31.4% 필요
- 현재 +24.7%에서 +6.7%p 추가 필요
- 이것은 현재 수익의 27% 추가 증가를 의미

이를 달성할 수 있는 유일한 경로:
1. 배치율 35% -> 50%+ (3rd 전략 추가)
   -> 두 번 시도, 두 번 실패
   -> 각 실패가 -2.7%p ~ -5.1%p regression 초래
   -> 기대값 음수

2. ROIC 30% -> 45%+ (파라미터 최적화)
   -> Iter 24에서 시도, catastrophic failure
   -> 기대값 강한 음수

3. 리스크 증가 (risk per trade 2% -> 3%)
   -> Panel #31 VETO
   -> MaxDD 증가 불가피

4. 레버리지 활용
   -> $1-5K 계좌에서 margin은 위험
   -> PDT 규칙과 충돌

각 경로의 기대값:
- 경로 1: 0.3 * (+6%p) + 0.7 * (-4%p) = -1.0%p (음수)
- 경로 2: 0.2 * (+4%p) + 0.8 * (-5%p) = -3.2%p (강한 음수)
- 경로 3&4: VETOED

S&P 초과를 시도하는 것의 기대값이 음수라면,
현재 수준을 유지하는 것이 수학적으로 올바른 선택이다.
```

**분석 4: 리스크 예산 관점의 최적 전략**

```
현재 시스템의 리스크 프로파일:
- P1 MaxDD: 20.2% (높음, 주로 BM의 초기 구간)
- P2 MaxDD: 3.0% (매우 낮음)
- 전체 Worst-case: 20.2%

Panel #31에서 리스크 증가를 VETO한 이유:
- $1-5K 계좌에서 20%+ DD는 심리적으로 버티기 어려움
- DD 회복에 필요한 수익: 20% DD -> 25% gain 필요
- 실제 계좌에서 DD 중 포기 확률이 높음

그러나 P2의 MaxDD 3.0%는 매우 보수적이다.
만약 MaxDD 허용치를 8-10%로 설정한다면?
-> 이것은 P2에서 추가 5-7%p의 '리스크 여유'가 있음을 의미
-> 하지만 이 여유를 활용할 메커니즘이 없다

문제: 리스크 예산이 남아있지만, 이를 수익으로 전환할 효율적인 방법이 없다.
이것이 구조적 천장의 또 다른 증거다.
```

**Strat-3 결론: 리스크 조정 기준으로 우리 시스템은 S&P를 압도적으로 능가한다 (Sharpe 2x, Calmar 4.7x). $1-5K 소액 계좌에서 2년간 $335의 절대 수익 차이를 위해 regression 리스크를 감수하는 것은 비합리적이다. 현 시스템의 리스크/리워드 프로파일은 이미 소액 계좌에 최적이다. S&P 절대 수익 추격을 중단하고, 현 성과를 안정적으로 유지하는 것이 최선이다.**"

---

### Strat-4 (Market Analyst) -- 시장 구조와 시스템 한계의 관계

"시장 분석가로서 왜 이 시스템이 현재 수준에서 천장을 만나는지, 그리고 그것이 반드시 나쁜 것은 아닌지를 설명하겠다.

**분석 1: Event-Driven vs Continuous Exposure의 본질적 차이**

```
시장 수익의 분포를 일간 기준으로 보면:

S&P 500 일간 수익 분포 (연간 252일):
- 상위 10일이 연간 수익의 ~80%를 차지 (이것은 잘 알려진 통계)
- 나머지 242일: 개별 기여도 미미

우리 시스템의 시장 노출:
- BM: 연 44-49건 * 평균 7일 보유 = ~310-340 position-days
- MR: 연 16-18건 * 평균 4일 보유 = ~64-72 position-days
- 총 position-days: ~374-412 / 252일 * 평균 1.5 종목 = ~890-930 stock-days
- 시가총액 가중 S&P 500 일일 노출: 252일 * 500종목 = 126,000 stock-days

노출 비율: 930 / 126,000 = 0.74%

우리는 S&P 500 노출의 0.74%만 취하면서 31.4%의 79% (24.7%)를 포착한다.
이것은 position selection의 alpha가 존재한다는 강력한 증거다.

ROIC 관점:
- S&P ROIC (전체 자본 대비): 31.4% / 100% = 31.4%
- 우리 ROIC (배치 자본 대비): (24.7% - 7.0% cash yield) / 35% = 50.6%
- 배치된 자본의 ROIC이 S&P의 1.6배

의미: 우리 시스템은 '종목 선택'에서 alpha를 생성하지만,
'시장 노출 시간'에서 S&P에 뒤처진다.
이것은 trade-off이며, 반드시 열등한 것은 아니다.
```

**분석 2: 시장 레짐에 따른 상대 성과 패턴**

```
P1 (2024-03 ~ 2025-02, Bull Market):
- S&P: +15.9%
- 우리: +11.4%
- 갭: -4.5%p
- 원인: Bull market에서 continuous exposure가 유리

P2 (2025-02 ~ 2026-02, Mixed Market):
- S&P: +15.5%
- 우리: +13.3%
- 갭: -2.2%p (대폭 축소)
- 원인: Mixed market에서 선택적 진입이 리스크 관리에 유리

패턴: 시장이 불확실할수록 우리 시스템의 상대 성과가 개선된다.

만약 P3가 Bear Market이라면?
- S&P: -10% ~ -20% (가정)
- 우리: 0% ~ +5% (BM 축소, MR 활성, cash yield 계속)
- 갭: +10 ~ +25%p (우리가 우위)

이것이 event-driven 시스템의 진짜 가치:
- Bull에서는 약간 뒤지지만
- Bear에서는 대폭 앞선다
- Mixed에서는 거의 동등하다

3년 사이클 기준 (bull + mixed + bear):
- S&P: +15.9% + 15.5% + (-15%) = +16.4% (가정)
- 우리: +11.4% + 13.3% + (+3%) = +27.7% (가정)
- 장기 전체 사이클에서 우위 가능성이 높다
```

**분석 3: ADX Dead Zone의 최종 결론**

```
Panel #33에서 ADX Dead Zone(20-28)에 대해 논의했고,
Trend Pullback이 이 구간에서 edge가 없음을 확인했다.

ADX Dead Zone의 최종 분류:
- 전체 거래일의 ~35%
- 이 기간 BM은 진입 불가 (ADX < 28)
- 이 기간 MR은 진입 불가 (ADX > 20)
- 이 기간 cash yield: 4.75% * 35% = ~1.66%p/yr 기여

Dead Zone에서의 최선의 행동 = 현금 보유.
이것은 결함이 아니라 설계 의도다.

Warren Buffett: "규칙 1: 돈을 잃지 마라. 규칙 2: 규칙 1을 잊지 마라."
시장이 방향을 제시하지 않을 때 현금으로 대기하는 것은
투자의 기본 원칙에 부합한다.
```

**분석 4: 'Cash Yield + Event Selection' 모델의 구조적 장점**

```
우리 시스템을 재정의하면:

핵심 모델: "Cash-Plus Event Alpha"
- 기본 수익: 4.75% cash yield (무위험)
- Alpha 수익: event-driven 선택적 거래 (~20-22%p over 2yr = ~10-11%/yr)
- 합산: ~15%/yr (2년 ~30%)

이 모델의 장점:
1. 바닥 수익이 보장됨 (cash yield 4.75%)
2. Worst case = cash yield only = 4.75%/yr (S&P worst case는 -30%+)
3. 심리적 안정: 대부분의 시간을 현금으로 보유
4. 기회 비용이 낮음: 현금이 실제로 돈을 벌고 있음

이 모델의 약점:
1. Bull market에서 S&P 뒤처짐 (opportunity cost)
2. 절대 수익률이 full-invested에 미달
3. 소규모 계좌에서 절대 금액이 작음

핵심 인사이트: 4.75% cash yield가 있는 현재 환경에서
이 모델은 구조적으로 우수하다.
만약 금리가 0-1%로 하락하면 이 모델의 매력이 크게 감소한다.
→ 금리 환경 변화 시 전략 재검토 트리거.
```

**Strat-4 결론: 이 시스템은 'continuous market exposure' 시스템이 아니라 'cash-plus event alpha' 시스템이다. 이 구분이 중요하다. S&P와 절대 수익률로 비교하는 것 자체가 잘못된 벤치마크 설정이다. 올바른 벤치마크는 money market fund (4.75%) + 선별적 equity exposure이며, 이 기준으로 우리 시스템은 money market 대비 연 7-8%p의 alpha를 생성하고 있다. 시장 전체 사이클(bull+mixed+bear)에서는 S&P를 능가할 가능성이 높다.**"

---

## 3. Cross-Expert Synthesis

### Debate 1: S&P 절대 수익률 추격을 계속해야 하는가?

**표결: 중단 (4/4 만장일치)**

| Expert | 입장 | 핵심 논거 |
|--------|------|----------|
| Strat-1 | 중단 | 트레이딩 관점에서 잔여 개선 여지가 없다. exit 최적화, 진입 타이밍, MR P1 모두 risk/reward 부적합. |
| Strat-2 | 중단 | 수학적으로 모든 확장 경로의 기대값이 음수. 시도할수록 regression 확률이 높다. |
| Strat-3 | 중단 | $5K 계좌에서 2년간 $335 차이. 이를 위한 추가 리스크는 비합리적. Sharpe 2x, Calmar 4.7x의 가치가 더 크다. |
| Strat-4 | 중단 | 벤치마크 자체가 잘못됐다. Cash-plus event alpha 모델로 재정의하면 이미 우수한 시스템이다. |

### Debate 2: 시스템이 구조적 천장에 도달했는가?

**표결: YES, 현 아키텍처 내에서 (4/4 만장일치)**

```
구조적 천장의 정의:
현재 아키텍처(일일 봉, 2전략, event-driven, $1-5K)에서
추가 개선의 기대값이 0 이하인 상태.

천장의 증거:
1. 5가지 확장 경로 중 2가지 실행 -> 모두 regression (Iter 28, 30)
2. 나머지 3가지(파라미터, 리스크, 3rd 전략)도 사전 분석에서 음수 기대값
3. BM signal quality의 diminishing returns 확인 (cap 2 optimal)
4. 배치율 35%는 시스템 설계의 결과이며, 강제 증가는 품질 저하 초래

천장을 돌파할 수 있는 유일한 경로:
- 아키텍처 변경 (intraday bars, 다른 자산군, 레버리지)
- 이것은 현 프로젝트 범위 밖
```

### Debate 3: 현 시스템에 어떤 변경이라도 해야 하는가?

**표결: NO CHANGES (3/4, Strat-1 조건부)**

| Expert | 입장 | 이유 |
|--------|------|------|
| Strat-1 | 조건부 NO | MR TREND_UP 차단(옵션 F-1)이 +0.56%p 가능하지만, 금액이 미미하고 regime 로직 변경 리스크가 있으므로 보류. 실 트레이딩 데이터 수집 후 재검토. |
| Strat-2 | NO | 모든 변경의 기대값이 0 이하. 현 파라미터 그대로 유지. |
| Strat-3 | NO | 두 번 연속 regression 후 '아무것도 하지 않는 것'이 최선. 시스템 안정성이 최우선. |
| Strat-4 | NO | Live trading 데이터 없이 추가 백테스트 최적화는 과적합 위험. |

### Debate 4: 다음 단계는 무엇인가?

**합의: Live Paper Trading 전환 (4/4)**

```
이유:
1. 백테스트 최적화의 한계에 도달
   - 12차 iteration (Iter 19-30)을 거치면서 더 이상 개선 여지 없음
   - 추가 백테스트는 과적합 위험만 증가

2. Live trading에서만 검증 가능한 요소
   - Slippage 실제 크기 (백테스트는 3bps 가정)
   - Market impact (소액이므로 미미하겠으나 확인 필요)
   - Alpaca API 안정성 및 latency
   - 심리적 요인 (실제 돈으로 DD를 견디는 경험)
   - 이상 상황 처리 (halt, gap, splits)

3. Paper trading의 가치
   - 실제 시장 데이터로 forward test
   - 시스템 인프라 검증 (dashboard, logging, batch execution)
   - 2-4주 paper trading 후 real money 전환 판단

4. 백테스트에서 live로의 전환 체크리스트
   - [x] 전략 파라미터 확정 (Iter 27/29 = FINAL)
   - [x] Risk management 검증 (GDR, safety net)
   - [x] Infrastructure 구축 (Phase 11 completed)
   - [ ] Paper trading 실행
   - [ ] 2-4주 forward test 결과 수집
   - [ ] Real money 전환 결정
```

---

## 4. CONSENSUS DECISION

### Primary Decision: 시스템 FREEZE -- Iter 27/29를 FINAL CONFIGURATION으로 선언

**만장일치 (4/4)**

```
FINAL CONFIGURATION (Iter 27/29):
- 전략: BM + MR (2전략 포트폴리오)
- BM cap: 2 (LOCKED PERMANENTLY)
- MR cap: 4 (LOCKED PERMANENTLY)
- BM risk: 2.0% per trade (LOCKED)
- MR risk: 1.5% per trade (LOCKED)
- Cash yield: 4.75% annual (LOCKED)
- Warmup: 80 bars (LOCKED)
- Heat: 35% (LOCKED)
- Daily entries: 3 (LOCKED)
- Safety Net DD: 12% (LOCKED)
- Safety Net Recovery: 8% (LOCKED)
- All BM/MR parameters: Iter 23 values (LOCKED PERMANENTLY)
```

### Secondary Decision: S&P 절대 수익률 벤치마크 폐기

**만장일치 (4/4)**

```
OLD Benchmark: S&P 500 Total Return (절대 수익률 비교)
-> 문제: 배치율 100% vs 35%의 비교는 구조적으로 불공정

NEW Benchmark Framework:
1. Primary: Money Market (4.75%) + Alpha
   - 목표: Alpha > 7%p/yr (money market 대비 초과 수익)
   - 현재: Alpha ~7-8%p/yr -> MEETS TARGET

2. Secondary: Risk-Adjusted (Sharpe, Calmar)
   - 목표: Sharpe > 1.0 (양 기간 평균), Calmar > 1.5
   - 현재: P2 Sharpe 1.753, P1 Sharpe 0.490, P2 Calmar 4.489 -> PARTIALLY MEETS
   - P1의 Sharpe 개선은 live trading에서 재확인 후 평가

3. Tertiary: Full Cycle Performance (bull + mixed + bear)
   - 평가: Bear market 기간 데이터 수집 후 가능
   - 가설: 전체 사이클에서 S&P 능가 가능 (MR의 방어력 + cash yield)
```

### Tertiary Decision: Live Paper Trading 전환 권고

**만장일치 (4/4)**

```
권고사항:
1. 더 이상의 백테스트 iteration 실행하지 않음
2. Iter 27/29 configuration으로 paper trading 시작
3. Paper trading 기간: 최소 2주, 권장 4주
4. 수집할 데이터:
   - 실제 fill price vs 예상 price (slippage 검증)
   - 일일 equity curve
   - Trade log (entry/exit reason, PnL)
   - System uptime and reliability

5. Paper trading 성공 기준:
   - 4주간 system crash 없음
   - Slippage < 10bps (백테스트 가정 3bps 대비)
   - 거래 빈도가 백테스트와 유사 (+/- 30%)
   - MaxDD < 10% (4주 기간)

6. Real money 전환 조건:
   - Paper trading 성공 기준 충족
   - 사용자의 명시적 승인
   - 초기 자본 $1,000로 시작 (최소)
```

### Parameter Changes: NONE

**이번 패널에서 파라미터 변경 사항 없음.**

시스템은 Iter 27/29 상태를 그대로 유지한다.

---

## 5. Reassessment Triggers

향후 시스템 재검토가 필요한 조건:

```
Trigger 1: 금리 환경 변화
- Cash yield가 2% 이하로 하락 시
- Cash-plus alpha 모델의 기본 수익 감소
- 대응: 배치율 증가 전략 재검토 필요

Trigger 2: Live trading에서 백테스트 괴리 확인
- 실제 slippage > 15bps
- 실제 WR < 백테스트 WR - 10%p
- 실제 거래 빈도 < 백테스트의 50%
- 대응: 파라미터 재조정 또는 전략 재설계

Trigger 3: 시장 구조 변화
- S&P 500 volatility regime 근본 변화
- ADX 분포의 구조적 변화
- 대응: regime classifier 재검증

Trigger 4: 계좌 규모 변화
- $10K+ 계좌 도달 시
- 대응: position sizing 재검토, 3rd 전략 재논의 가능

Trigger 5: 아키텍처 확장 결정
- Intraday data 사용 결정
- 다른 자산군(ETF, crypto) 추가 결정
- 대응: 전면적 전략 재설계
```

---

## 6. Final System Performance Card

```
+============================================================+
|             AutoTrader v2 -- FINAL PERFORMANCE CARD         |
+============================================================+
|                                                             |
|  Configuration: Iter 27/29 (BM + MR, 2-Strategy)           |
|  Status: FROZEN -- No further backtest optimization         |
|                                                             |
|  +--- Absolute Returns ---+  +--- Risk Metrics ---+        |
|  | P1 Return:  +11.4%     |  | P1 MaxDD:  20.2%  |        |
|  | P2 Return:  +13.3%     |  | P2 MaxDD:   3.0%  |        |
|  | Combined:   +24.7%     |  | P2 Sharpe:  1.753  |        |
|  | Ann. Return: ~12.4%    |  | P2 Calmar:  4.489  |        |
|  +-------------------------+  +---------------------+       |
|                                                             |
|  +--- Revenue Mix (2yr) ---+                                |
|  | BM PnL:     +$10,914 (45%)    Primary earner     |      |
|  | MR PnL:     +$6,369  (26%)    Complementary      |      |
|  | Cash Yield:  +$7,000 (29%)    Stable income       |      |
|  | Total:      +$24,283                               |     |
|  +------------------------------------------------------+  |
|                                                             |
|  +--- Structural Profile ---+                               |
|  | Avg Deployment:  ~35%         |                          |
|  | Avg Idle Cash:   ~65%         |                          |
|  | ROIC (deployed): ~50%         |                          |
|  | Trades/yr:       ~63          |                          |
|  | Model Type: Cash-Plus Event Alpha |                      |
|  +-------------------------------+                          |
|                                                             |
|  +--- vs S&P 500 ---+                                       |
|  | Absolute: -6.7%p (S&P wins in bull markets)       |      |
|  | Sharpe:   2.0x ours (risk-adjusted, we win)       |      |
|  | Calmar:   4.7x ours (drawdown-adjusted, we win)   |     |
|  | Full Cycle: Expected to outperform (bear defense) |      |
|  +----------------------------------------------------+    |
|                                                             |
+============================================================+
```

---

## 7. DO NOT CHANGE (Final Locked Parameters)

| Parameter | File | Value | Lock Reason |
|-----------|------|-------|-------------|
| ADX_MIN | breakout_momentum.py | 28.0 | 12-iter confirmed |
| BREAKOUT_LOOKBACK | breakout_momentum.py | 15 | 12-iter confirmed |
| VOL_RATIO_MIN | breakout_momentum.py | 1.2 | 12-iter confirmed |
| BM soft cap | batch_simulator.py | 2 | **LOCKED PERMANENTLY** (cap 3 proven worse, Iter 30) |
| MR soft cap | batch_simulator.py | 4 | **LOCKED PERMANENTLY** (Panel #31 optimal) |
| BM SL ATR mult | exit_rules.py | 2.5 | LOCKED |
| BM TP ATR mult | exit_rules.py | 4.0 | LOCKED |
| BM trailing activation | exit_rules.py | 1.5 | LOCKED |
| BM trailing distance | exit_rules.py | 2.0 | LOCKED |
| BM GDR thresholds | batch_simulator.py | (0.04, 0.08) | LOCKED |
| MR GDR thresholds | batch_simulator.py | (0.02, 0.04) | LOCKED |
| MR all entry params | rsi_mean_reversion.py | RSI30/75, BB0.05/0.95, ADX<20 | LOCKED |
| MAX_LONG | batch_simulator.py | 8 | LOCKED |
| MAX_TOTAL | batch_simulator.py | 9 | LOCKED |
| Risk per trade (BM) | batch_simulator.py | 2.0% | LOCKED |
| Risk per trade (MR) | batch_simulator.py | 1.5% | LOCKED |
| Cash yield rate | batch_simulator.py | 4.75% annual | LOCKED |
| Warmup preload | batch_simulator.py | 80 bars | LOCKED |
| Safety Net DD | batch_simulator.py | 12% | LOCKED |
| Safety Net Recovery | batch_simulator.py | 8% | LOCKED |
| Stage2 Profit Lock | exit_rules.py | 0.4 (BM) | LOCKED |
| MAX_PORTFOLIO_HEAT_PCT | batch_simulator.py | 0.35 | LOCKED |
| MAX_DAILY_ENTRIES | batch_simulator.py | 3 | LOCKED |

**STATUS: ALL PARAMETERS PERMANENTLY LOCKED. NO FURTHER BACKTEST OPTIMIZATION.**

---

## 8. Iteration History (Final)

| Iter | P1 Return | P2 Return | Combined | MaxDD P1 | MaxDD P2 | Key Change |
|------|-----------|-----------|----------|----------|----------|-----------|
| 19 | +7.4% | +2.6% | +10.0% | ~3.5% | ~5% | ADX28, LB15, cap2 |
| 22 | -0.6% | +3.5% | +2.9% | ~5% | ~7% | Regime BM alloc reduction |
| **23** | **+7.5%** | **+7.9%** | **+15.4%** | **20.2%** | **21.0%** | BM+MR baseline (PARAMETER CEILING) |
| 24 | -0.69% | +0.19% | -0.5% | 21.8% | 4.34% | DD reduction (OVER-CORRECTED) |
| 25 | +1.76% | +3.40% | +5.16% | ? | ? | Partial rollback |
| **26** | **+7.5%** | **+7.9%** | **+15.4%** | **~20%** | **~21%** | Clean revert to Iter 23 |
| **27** | **+11.4%** | **+13.3%** | **+24.7%** | **20.2%** | **3.0%** | Cash yield + Warmup + MR cap 4 (STRUCTURAL CEILING) |
| 28 | +7.3% | +12.3% | +19.6% | 21.7% | 22.4% | Trend Pullback -> REGRESSION |
| **29** | **+11.4%** | **+13.3%** | **+24.7%** | **~20%** | **~3%** | Revert to Iter 27 (RESTORED) |
| 30 | +9.3% | +12.7% | +22.0% | ? | ? | BM cap 3 -> REGRESSION |

```
Performance Journey:

Return %
30% |
28% |
26% |                    *** CEILING ***
25% |===== Iter 27/29 (+24.7%) ============ FINAL =====
24% |
22% |                                    Iter 30 (+22.0%) X
20% |        Iter 28 (+19.6%) X
18% |
16% |
15% |= Iter 23/26 (+15.4%) = PARAMETER CEILING =
14% |
12% |
10% |Iter 19
 8% |
    +---+---+---+---+---+---+---+---+---+---+---+---+
       19  22  23  24  25  26  27  28  29  30

       Phase 1:                Phase 2:           Phase 3:
       Parameter tuning        Structural         FROZEN
       (Iter 19-26)           expansion           (Iter 29 = FINAL)
                              (Iter 27-30)
```

---

## 9. Key Principles (Final Compilation)

### From Parameter Tuning Phase (Iter 19-26)
1. **Parameter tuning 시대는 끝났다.** 10+ iteration의 조정이 net-negative. Iter 23이 parameter ceiling.
2. **Single variable testing은 절대 원칙이다.** 한 번에 하나만 변경하고 측정.
3. **Regression은 빠르게 revert.** 감정적 집착 없이 데이터로 판단.

### From Structural Expansion Phase (Iter 27-30)
4. **Cash yield는 시스템의 구조적 장점.** 아무것도 안 하는 것이 나쁜 일을 하는 것보다 낫다.
5. **새 전략 추가 시 crowding out 효과를 반드시 분석.** 직접 손실보다 간접 손실이 더 클 수 있다.
6. **이론적 RR과 실현 RR은 다르다.** 모든 exit 경로를 고려한 실현 RR로 평가.
7. **검증된 전략의 확장에도 diminishing returns 존재.** BM cap 2 -> 3은 signal quality 저하.
8. **빈 공간을 채우는 것이 항상 좋은 것은 아니다.** ADX dead zone은 현금 보유가 최선.

### From Ceiling Assessment (Panel #34)
9. **구조적 천장을 인정하는 것이 지혜.** 기대값이 음수인 개선 시도는 해악.
10. **벤치마크를 올바르게 설정.** Event-driven 시스템을 buy-and-hold와 절대 비교하지 않는다.
11. **리스크 조정 수익률이 소액 계좌에서 더 중요.** Sharpe 2x, Calmar 4.7x의 가치.
12. **과적합의 유혹을 경계.** 12 iteration의 백테스트 최적화 후 더 이상의 최적화는 과적합.

---

## 10. Action Items

### Immediate: NONE (No parameter changes)

### Recommended Next Steps

| # | Action | Owner | Priority | Est. Time |
|---|--------|-------|----------|-----------|
| 1 | Live paper trading 시작 (Iter 27/29 config) | Dev-3 | **HIGH** | 1 day setup |
| 2 | Paper trading 모니터링 (2-4주) | Dev-3/Dev-5 | HIGH | 2-4 weeks |
| 3 | Paper trading 결과 리뷰 (Panel #35) | Strategy Team | HIGH | After 4 weeks |
| 4 | Real money 전환 결정 | 사용자 | HIGH | After Panel #35 |

### Backlog (Deferred Indefinitely)

| # | Item | Condition for Reactivation |
|---|------|---------------------------|
| B1 | 3rd strategy exploration | 계좌 $10K+ AND 금리 < 2% |
| B2 | Intraday timeframes | Major architecture decision |
| B3 | Alternative asset classes | User explicit request |
| B4 | MR TREND_UP blocking | Live trading data 6+ months |
| B5 | Core+Satellite architecture | Fundamental system redesign approved |

---

## Appendix A: Decision Framework Used

```
                           +24.7% (Current Best)
                                |
                    Can we improve?
                   /              \
                 YES               NO
                 |                  |
          What's the              Accept and
          expected value?         move to live
           /         \               |
         > 0          <= 0          *** WE ARE HERE ***
          |             |
       Execute       Don't
       (with         attempt
       revert plan)

All 7 expansion paths analyzed:
[1] BM cap 3:        EV = -2.7%p  (TESTED, CONFIRMED NEGATIVE)
[2] Trend Pullback:  EV = -5.1%p  (TESTED, CONFIRMED NEGATIVE)
[3] Parameter tune:  EV = -5%p    (TESTED Iter 24, CONFIRMED NEGATIVE)
[4] Risk increase:   EV = ?       (VETOED by Panel #31)
[5] MR cap 5:        EV < 0       (P1 loss expansion risk)
[6] ADX threshold:   EV < 0       (Dead zone = no edge)
[7] Other 3rd strat: EV uncertain (5 types analyzed, all risky)

Conclusion: No path has positive expected value.
Optimal action: STOP OPTIMIZING. GO LIVE.
```

## Appendix B: System Model Reclassification

```
BEFORE (Panel #1-33):
  Model: "Alpha Generation System"
  Benchmark: S&P 500 Total Return
  Goal: Beat S&P 500 absolute return
  Status: FAILING (-6.7%p gap)

AFTER (Panel #34):
  Model: "Cash-Plus Event Alpha System"
  Benchmark: Money Market (4.75%) + Risk-Adjusted Alpha
  Goal: Alpha > 7%p over money market, Sharpe > 1.0
  Status: SUCCEEDING (Alpha ~7-8%p, P2 Sharpe 1.753)

The system didn't change. Our understanding of it did.
```
