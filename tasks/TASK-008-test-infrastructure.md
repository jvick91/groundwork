# TASK-008: Test Infrastructure & Fixtures

**Status:** Not started
**Spec sections:** SPEC-007 §13 (all subsections); SPEC-000 §5
**ADRs:** —
**Depends on:** TASK-001, TASK-002, TASK-003, TASK-007

## Objective

Build the test infrastructure: conftest fixtures for database sessions with transaction rollback isolation, async httpx test client with full middleware execution, test JWT generation with a test-only RSA key, and the test factory pattern. Tests must run inside Docker against the `db-test` PostgreSQL instance.

## Acceptance Criteria

- [ ] `conftest.py` provides an async SQLAlchemy session fixture with per-test transaction rollback per SPEC-007 §13.2
- [ ] Test client uses `httpx.AsyncClient` with full middleware execution (no middleware bypass) per SPEC-007 §13.3
- [ ] Test auth fixture generates valid JWTs signed with a test-only RSA key per SPEC-007 §13.4
- [ ] Auth middleware validates against the test key in test environment
- [ ] Test factory pattern established with sensible defaults per SPEC-007 §13.5
- [ ] Tests run via `docker compose exec backend pytest` against `db-test` on port 5433
- [ ] Coverage measured by pytest-cov with threshold enforcement per SPEC-007 §13.7
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest]` configured with correct DB URL and coverage settings
- [ ] Factory modules scaffolded under `tests/factories/` per SPEC-007 §13.6

## Files

- `backend/tests/conftest.py`
- `backend/tests/factories/__init__.py`
- `backend/tests/factories/eav.py` (Organization factory)
- `backend/tests/factories/identity.py` (Person factory)
- `backend/app/core/security.py` (test key configuration)
- `backend/pytest.ini` or `backend/pyproject.toml`
- `backend/.coveragerc`

## Non-goals

- Domain-specific test factories (created in each domain task)
- Actual test cases (each domain task writes its own)
