# TASK-008B Log — CI Pipeline Configuration

**Agent:** claude-code
**Branch:** task-008b-ci-pipeline
**Date completed:** 2026-04-29

## What Was Done

Added two GitHub Actions workflows and a CI policy document.

1. **`.github/workflows/ci.yml`** — runs on every PR targeting `main` and every push to `main`. Two jobs:
   - `backend-checks` (lint → format check → type check → tests, in order, all `docker compose exec -T backend ...`).
   - `build` (`docker compose build backend`), runs in parallel.
   Concurrency group keyed on `github.ref` cancels superseded runs. Buildx layer cache keyed on `dockerfile` + `pyproject.toml` so reruns reuse the image when neither changed.
2. **`.github/workflows/migration-safety.yml`** — only runs when a PR/push touches `backend/alembic/versions/**` (workflow-level `paths:` filter, the cleanest way to scope path-based jobs in GHA). Runs apply → upgrade head idempotency check → downgrade -1 → re-apply.
3. **`docs/ci.md`** — describes the pipeline stages, PR merge requirements (SPEC-007 §14.2), and the manual branch-protection settings that GitHub UI must enforce on top of CI (workflow files cannot configure those themselves).

Final verification on the branch:
- `docker compose exec backend ruff check app/ tests/` — clean.
- `docker compose exec backend mypy app/` — Success, no issues in 24 source files.
- `docker compose exec backend pytest tests/` — 98 passed, coverage 93.62%.
- Both workflow YAML files parse with `yaml.safe_load` (basic structural sanity check; full validation will come from the first run on GitHub).

## Decisions Made

- **Two workflow files, not one with conditional jobs.** GitHub Actions supports `paths:` filtering only at the workflow level, not the job level. Putting the migration-safety job in its own workflow keeps the path filter declarative; trying to do it inline (e.g. `if: contains(toJSON(github.event.pull_request.changed_files), ...)` ) is fragile because `changed_files` is not a stable field on the event payload.
- **Format check (`ruff format --check`) included as a separate stage.** Not strictly required by the AC, but it costs nothing on top of an already-running container and prevents unformatted files from ever landing on `main`. Documented in `docs/ci.md`.
- **`build` runs in parallel with `backend-checks`, not sequentially.** SPEC-007 §14.1 lists stages in order, but does not require sequential execution. Running build in parallel halves wall-clock CI time and the `backend-checks` job rebuilds the image anyway. If they ever diverge (e.g. build needs a multi-arch matrix), splitting them keeps that change isolated.
- **`docker inspect --format='{{.State.Health.Status}}'` for healthchecks** rather than `docker compose ps --format json`. The compose CLI's JSON format has shifted between versions; `docker inspect` against the explicit container name is stable across compose 2.x.
- **Branch-protection settings documented, not enforced from code.** GitHub does not expose branch-protection configuration via workflow files; it is a repository setting only the owner can change. Documented in `docs/ci.md` rather than glossed over.
- **No coverage gate added to CI.** Per AC and SPEC-007 §14.1, `--cov-fail-under=90` lives in `pytest.ini` (TASK-008). CI runs `pytest` and inherits the gate.

## Deviations from Task

- None of substance. The AC's "ordered stages" is interpreted as logical ordering within the `backend-checks` job (lint → format → type → tests). The `build` stage runs as a parallel job; the AC does not require a strict serial dependency.

## Open Items

- **First-run friction expected.** The CI workflow has not yet executed against a real GitHub-hosted runner. Likely friction points: (a) compose `--wait` semantics, (b) container name conventions (`groundwork-backend-1` vs `groundwork_backend_1` depending on compose version), (c) potential Docker Buildx cache-restore quirks. These will surface on the first PR run; iterate as needed.
- **Branch protection must be enabled in GitHub UI.** Listed in `docs/ci.md` with the exact required settings. Until that is configured, CI failures are advisory rather than blocking.
- **Required-status-check names need to match what GitHub records.** GitHub's "required status checks" UI will populate the available check names after the first workflow run. Use the names from `docs/ci.md`'s required list.
