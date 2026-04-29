# TASK-008B: CI Pipeline Configuration

**Status:** Complete (branch protection settings remain a manual GitHub configuration step — documented in `docs/ci.md`)
**Spec sections:** SPEC-007 §14 (all subsections)
**ADRs:** —
**Depends on:** TASK-001 (Docker services), TASK-002 (migrations), TASK-007 (logging), TASK-008 (test fixtures — partial is sufficient), TASK-008C (ruff & mypy config — so lint/type-check stages enforce real rules, not defaults)

## Objective

Stand up the CI pipeline **as early as possible** so every PR to `main` is guarded by lint, type check, tests, and a Docker image build. This task lands in Phase 1 alongside the foundation work — not at the end of the project — because CI's value compounds with every task it guards. All stages run inside Docker containers per SPEC-007 §14.1. The differentiated coverage threshold (models/services 95%, routers/schemas 90%) activates automatically once TASK-008 ships the `--cov-fail-under` pytest config; CI does not need a separate gate for it.

## Acceptance Criteria

- [x] GitHub Actions workflow at `.github/workflows/ci.yml` triggers on pull requests targeting `main` and on pushes to `main`
- [x] Ordered stages per SPEC-007 §14.1: lint → type check → backend tests → build — `backend-checks` job runs lint → format check → mypy → pytest in order; `build` job runs in parallel
- [x] Lint stage: `docker compose exec -T backend ruff check app/ tests/` — fails on any lint error
- [x] Type check stage: `docker compose exec -T backend mypy app/` — fails on any type error (mypy strict mode per existing config)
- [x] Backend test stage: `docker compose exec -T backend pytest` — runs inside the backend container against `db-test`, fails on any test failure
- [x] Coverage threshold enforcement is inherited from TASK-008's pytest config (`--cov-fail-under`); CI does not duplicate the gate
- [x] Build stage: `docker compose build backend` succeeds
- [x] All stages run inside Docker containers — no direct Python install on the CI runner per SPEC-007 §14.1
- [x] Alembic migration safety per SPEC-007 §14.3: for any PR touching `backend/alembic/versions/`, CI runs fresh apply → upgrade → downgrade and fails if any step errors — `.github/workflows/migration-safety.yml` with a `paths:` filter
- [x] PR merge requirements documented per SPEC-007 §14.2 in `docs/ci.md` (or equivalent): all stages pass, reviewer approval, branch up to date
- [x] Branch protection on `main` is documented as a manual GitHub setting (not enforceable from the workflow file itself) — see `docs/ci.md`

## Files

- `.github/workflows/ci.yml`
- `docs/ci.md` (PR merge requirements; create if missing)

## Non-goals

- Frontend test stages — post-MVP, activate once a frontend lands per SPEC-007 §14.1
- E2E Playwright stages — post-MVP
- Deployment pipeline — out of scope for this task
- Adding a separate `--cov-fail-under` flag in CI — the threshold lives in the pytest config shipped by TASK-008
- Differentiated per-layer coverage thresholds — enforced by TASK-008's pytest config once it lands; CI just runs `pytest`

## Notes

Task renamed from TASK-036 on 2026-04-23 and moved from Phase 8 to Phase 1 so CI guards every downstream task rather than only the final polish pass. The original TASK-036 scope is preserved verbatim above except that the coverage-threshold AC was merged into TASK-008's remaining work (it was already listed there) to avoid duplication.
