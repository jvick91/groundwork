# CI & PR merge requirements

This document describes the CI pipeline that guards every PR to `main`,
the merge requirements imposed on top of CI, and the manual GitHub
settings that round out the policy.

Source of truth: SPEC-007 §14.

## Pipeline stages

GitHub Actions runs the following workflows on every PR targeting `main`
and every push to `main`. All stages run inside Docker containers — no
Python is installed directly on the runner (SPEC-007 §14.1).

### `ci.yml` — runs on every PR

| Stage | Tool | Fails on |
|---|---|---|
| Lint | `ruff check app/ tests/` | Any lint error |
| Format check | `ruff format --check app/ tests/` | Any unformatted file |
| Type check | `mypy app/` (strict mode) | Any type error |
| Backend tests | `pytest` inside the backend container against `db-test` | Any test failure or coverage below 90% |
| Build | `docker compose build backend` | Build failure |

The coverage threshold (`--cov-fail-under=90`) is enforced by
`backend/pytest.ini`, not by a separate CI gate (SPEC-007 §14.1).

### `migration-safety.yml` — runs only when `backend/alembic/versions/` changes

Per SPEC-007 §14.3, every PR that touches an Alembic revision must:

- Apply the migration against a fresh database (verify it applies cleanly)
- Run `alembic upgrade head` against the current schema (verify idempotence)
- Run `alembic downgrade -1` (verify rollback works)
- Re-run `alembic upgrade head` to confirm the round-trip is clean

Triggered automatically by a path filter on the workflow.

## PR merge requirements

A PR may only be merged when (SPEC-007 §14.2):

- All CI stages pass (`backend-checks`, `build`, and `migration-safety` if applicable)
- At least one reviewer has approved
- The branch is up to date with `main`
- No unresolved review comments

These rules are enforced by branch protection on `main`, configured
manually in **GitHub → Settings → Branches → Branch protection rules**.

### Required branch-protection settings

The workflow file cannot configure these — they live in GitHub UI:

- **Require a pull request before merging**
  - Require approvals: at least 1
  - Dismiss stale pull request approvals when new commits are pushed
  - Require review from Code Owners (optional; activate once `CODEOWNERS` exists)
- **Require status checks to pass before merging**
  - Require branches to be up to date before merging
  - Status checks required:
    - `Lint, type check, tests (backend)`
    - `Docker image build`
    - `Apply, upgrade, downgrade` (only if migrations changed — mark as required-when-applicable)
- **Require conversation resolution before merging**
- **Do not allow bypassing the above settings** (admins included)

## Out of scope (post-MVP)

These stages are specified in SPEC-007 §14.1 but are not active during
the MVP because the repository does not yet contain a frontend. They
activate when a frontend lands:

- Frontend tests (Vitest inside Docker)
- E2E tests (Playwright inside Docker)
- Deployment pipeline
