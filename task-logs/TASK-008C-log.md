# TASK-008C Log — Linter & Type-Check Configuration

**Agent:** claude-code
**Branch:** phase1-finish
**Date completed:** 2026-04-29

## What Was Done

Added `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.format]`, `[tool.mypy]`, and `[[tool.mypy.overrides]]` sections to `backend/pyproject.toml`.

- ruff rule selection: `E, F, W, I, B, UP, SIM, RUF`
- ruff line-length: 100; target Python: 3.12; `alembic/versions` excluded
- per-file-ignores: tests allow `S101`, `B011`, `RUF001`; alembic relaxes `E501`, `F401`, `I001`, `UP`
- mypy: `strict = true`, `python_version = "3.12"`, pydantic plugin enabled, `alembic/versions/` excluded
- mypy overrides: tests relax `disallow_untyped_defs` / `disallow_incomplete_defs` / `disallow_untyped_decorators`; `factory.*` / `factory_boy.*` get `ignore_missing_imports`

Brought the existing codebase up to the new strictness:

- Annotated `__init__` returns in `app/core/exceptions.py` (5 classes).
- Replaced untyped `dict` annotations and added `EventDict` / `WrappedLogger` in `app/core/logger.py`; assigned local for the `BoundLogger` return.
- Added `AsyncEngine` annotation on `Database.get_engine()` in `app/core/database.py`.
- Added `dict[str, str]` on `liveness()` return in `app/routers/health.py`.
- Added `DependsParam` annotation on `require_permission()` and a `cast` on its return in `app/core/security.py`.
- Parameterized `Select` and `InstrumentedAttribute` generics in `app/utils/pagination.py`; annotated `decode_cursor` local; added `from exc` to the re-raise.
- Replaced tuple-form `isinstance(..., (X, Y))` with `X | Y` in `app/services/audit_service.py` and `app/utils/pagination.py`.
- Broke 3 long lines in `app/models/models.py`, `app/schemas/schemas.py`, and `tests/test_cross_cutting/test_error_responses.py`.
- Auto-fix from `ruff --fix` removed unused imports in `app/core/database.py`, `app/routers/compliance.py`, `tests/test_compliance/test_audit_log.py`, `tests/test_cross_cutting/test_pagination.py`, and reorganized import blocks per `I001`.
- Ran `ruff format` once across `app/` and `tests/` to baseline formatting (15 files reformatted, 24 already correct).

Final state:
- `docker compose exec backend ruff check app/ tests/` — clean.
- `docker compose exec backend ruff format --check app/ tests/` — 39 files already formatted.
- `docker compose exec backend mypy app/` — Success, no issues in 22 source files.
- `pytest tests/ --no-cov` — 77 passed (3 pre-existing health-readiness failures on `tests/test_cross_cutting/test_health.py` exist on `main` and are unrelated to this task).

## Decisions Made

- **Ruff rule selection kept pragmatic per task notes** — `E, F, W, I, B, UP, SIM, RUF` only. No `S` (bandit), `D` (docstrings), `ANN` (annotations) — those are noisy on this codebase and would force ignores rather than improvements.
- **`B008` ignored globally** — FastAPI relies on `Depends(...)` defaults in handler signatures; the rule fires throughout otherwise.
- **`SIM117` ignored globally** — combined `with` statements obscure async context boundaries; the existing nested style is intentional.
- **`UP` excluded from alembic** — auto-generated migrations should not be rewritten to look modern; their literal form is part of their audit value.
- **`pydantic.mypy` plugin enabled** — strict mode without it produces dozens of false positives on `BaseModel` subclasses, and we use Pydantic across schemas and settings.
- **Tests kept under strict mode for return-type checking, but constructor and decorator strictness relaxed** — the suite uses pytest fixtures and `@pytest.fixture`/`@pytest_asyncio.fixture` decorators that don't carry strict-friendly signatures.
- **`ruff format` applied once** — baseline the codebase now so CI (TASK-008B) can enforce formatting. The diff touches 15 files but is mechanical.

## Deviations from Task

- **Codebase changes beyond pyproject.toml**: the AC required the existing codebase to pass strict mypy and ruff. Achieving that required source edits across 17 files. The `Files` section of TASK-008C only listed `backend/pyproject.toml` — call this an under-specification rather than a deviation. Impact: none; the touched files are all annotated or formatted to match the new rules, and no behavior changed.
- **`ruff format` baseline applied**: not explicitly required by the AC, but `ruff format --check` would otherwise fail in CI. Applying it once now is cheaper than spreading the formatting churn across every future PR. Impact: future PRs will see a clean format baseline.

## Open Items

- Three pre-existing readiness tests in `tests/test_cross_cutting/test_health.py` fail on both `main` and this branch (`test_readiness_returns_200_when_db_ok`, `test_readiness_status_is_ready_when_db_ok`, `test_readiness_checks_dict_contains_database_ok`). Not in scope here — TASK-005 still has open ACs for `/health/ready`. Will need to be addressed before TASK-008B can ship a fully-green CI.
