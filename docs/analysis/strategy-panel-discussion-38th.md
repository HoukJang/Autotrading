# Strategy Panel Discussion #38: Market -> Limit Order Migration

## Date: 2026-03-10

## Issue
COO (RSI Mean Reversion, score 0.94) 주문이 ghost fill prevention 로직에 의해 1초 만에 취소됨.
- 09:30:39 Market buy 324주 submitted
- 09:30:40 Cancelled (status=new -> ghost fill guard triggered)

Root cause: Alpaca API에서 market order 응답이 `new` 상태로 돌아오는 것은 정상 비동기 처리인데, 코드가 이를 "ghost fill 위험"으로 오판하여 즉시 취소.

## Strategy Team Consensus

### Decision: Market Order -> Limit Order 전환

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| order_type | limit | Ghost fill 구조적 제거 |
| limit_price (long) | prev_close * 1.03 | GAP_THRESHOLD와 일치 |
| limit_price (short) | prev_close * 0.97 | 갭다운 3% 이상 숏 차단 |
| time_in_force | day | 장 마감 자동 취소 |
| cancel_after | 30 min | LIMIT_ORDER_CANCEL_MINUTES |

### Risk Assessment
- Ghost fill risk: HIGH -> LOW (구조적 제거)
- Slippage risk: MEDIUM -> NONE (가격 상한 존재)
- Non-fill risk: NONE -> LOW (~4%, 3% 이상 갭업 = 진입 안 하는 게 맞음)

### Gap Filter 이중 보호
- gap_filter: 시그널 시점 사전 필터 (전일 데이터 기반)
- limit_price: 주문 시점 실시간 보호 (실제 개장가 기준)
- 중복이 아닌 상호 보완

## Implementation Summary

### Files Changed
1. `autotrader/trading/constants.py`: LIMIT_ORDER_CANCEL_MINUTES = 30
2. `autotrader/execution/entry_manager.py`: limit order 전환, pending order tracking, fill polling
3. `autotrader/execution/order_manager.py`: ghost fill guard 제거, pending state handling
4. `autotrader/main.py`: pending fill polling scheduler

### Dev-5 Impact Review Results
- P0 (1): _pending_limit_orders persistence -> FIXED (snapshot save/restore)
- P1 (4): daily count reservation, new day clear, encapsulation, batch_results -> FIXED
- P2 (2): cancel-race guard, polling constant -> FIXED
- All 1871 tests passing

## Next Actions
- Live paper trading에서 limit order 동작 확인 (내일 마켓 오픈)
- Fill rate 모니터링 (목표: >95%)
