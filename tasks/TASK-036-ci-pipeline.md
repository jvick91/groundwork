# TASK-036: CI Pipeline Configuration

**Status:** Not started
**Spec sections:** SPEC-007 §14 (all subsections)
**ADRs:** —
**Depends on:** TASK-008

## Objective

Configure the CI pipeline that runs on every PR per SPEC-007 §14.1: lint (ruff), type check (mypy strict), backend tests (pytest in Docker), and Docker image build. All stages run inside Docker containers. Define the PR merge requirements per SPEC-007 §14.2 and Alembic migration safety checks per SPEC-007 §14.3.

## Acceptance Criteria

- [ ] CI config (GitHub Actions or equivalent) with ordered stages per SPEC-007 §14.1: lint → type check → backend tests → build
- [ ] Lint stage: `ruff check app/ tests/` fails on any lint error
- [ ] Type check stage: `mypy app/` in strict mode fails on any type error
- [ ] Backend test stage: `pytest` inside Docker against db-test, fails on any test failure or coverage below threshold
- [ ] Build stage: Docker image build succeeds
- [ ] All stages run inside Docker containers — no direct Python/Node install on CI runner per SPEC-007 §14.1
- [ ] Coverage threshold enforced: models/services 95%, routers/schemas 90% per SPEC-007 §13.7
- [ ] Alembic migration safety per SPEC-007 §14.3: fresh apply, upgrade, downgrade verified for any migration in the PR
- [ ] PR requirements documented: all stages pass, reviewer approval, branch up to date per SPEC-007 §14.2

## Files

- `.github/workflows/ci.yml` (or equivalent CI config)
- `backend/pyproject.toml` (ruff, mypy, pytest config sections)

## Non-goals

- Frontend test stages (post-MVP)
- E2E Playwright stages (post-MVP)
- Deployment pipeline
