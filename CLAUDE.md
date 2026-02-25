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

## Project Docs

- System design: `docs/plans/2026-02-24-autotrader-v2-design.md`
- Implementation plan: `docs/plans/2026-02-24-autotrader-v2-implementation.md`
- Agent team design: `docs/plans/2026-02-24-agent-team-design.md`
