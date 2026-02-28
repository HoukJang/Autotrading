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

## Project Docs

- System design: `docs/plans/2026-02-24-autotrader-v2-design.md`
- Implementation plan: `docs/plans/2026-02-24-autotrader-v2-implementation.md`
- Agent team design: `docs/plans/2026-02-24-agent-team-design.md`
