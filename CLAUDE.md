# AutoTrader v2 - Project Rules

## Branch Strategy

| Branch | Purpose | Merge Target |
|--------|---------|-------------|
| `main` | Production (stable releases only) | - |
| `beta` | Testing / QA | main |
| `development` | Active development | beta |

- 모든 개발 작업은 `development`에서 feature branch를 따서 진행
- feature branch -> `development` (PR/merge)
- `development` -> `beta` (테스트 통과 후)
- `beta` -> `main` (QA 완료 후)
- `main`에 직접 커밋 금지

## Commit Convention

- Format: `type: short description`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`
- 한국어 커밋 메시지 금지 (영어만)

## Work Delegation

- 오케스트레이터(메인 에이전트)에서 직접 구현 작업을 하지 않는다
- 작업은 적절한 팀/서브에이전트를 호출해서 위임한다
- 적절한 팀이 없으면 새로 생성한다

## Strategy Team Rules

- 전략팀 리뷰/분석 수행 시 반드시 `docs/analysis/` 에 문서를 남긴다
- 파일명 형식: `strategy-panel-discussion-{N}th.md` (N = 백테스트 차수)
- 문서 포함 내용:
  - 백테스트 결과 요약 (거래수, WR, PF, MaxDD, Sharpe, Return)
  - 전략별 성과 분석
  - 전략팀 진단 및 권고사항
  - 다음 단계 결정 사항
  - 시장 레짐 분석 결과 (해당 시)
- 리뷰 없이 다음 백테스트 차수로 넘어가지 않는다

## Code Review Rules (Dev-5)

- 모든 코드 변경 후 반드시 Dev-5 (code-reviewer) impact review를 수행한다
- Impact review 체크 항목:
  1. **Broken callers**: 변경된 함수 시그니처/리턴값이 호출자를 깨뜨리는지
  2. **Missing matching changes**: 파일 A 변경 시 의존하는 파일 B도 수정 필요한지
  3. **Variable scope**: 수정된 코드의 변수가 항상 정의되어 있는지
  4. **New edge cases**: 수정이 새로운 실패 모드를 만드는지
  5. **Cross-system consistency**: 여러 tracking 시스템(held_positions, strategy_map, position_monitor, open_position_tracker) 간 일관성
  6. **N+1 API calls**: 루프 내 불필요한 반복 API 호출이 없는지
- P0/P1 수정 후에는 반드시 impact review를 수행한 뒤 커밋한다
- Review 결과 발견된 이슈는 같은 커밋 또는 직후 커밋에서 함께 수정한다

## Project Docs

- System design: `docs/plans/2026-02-24-autotrader-v2-design.md`
- Implementation plan: `docs/plans/2026-02-24-autotrader-v2-implementation.md`
- Agent team design: `docs/plans/2026-02-24-agent-team-design.md`
