# TASK-008: Test Infrastructure & Fixtures

**Status:** Partial
**Spec sections:** SPEC-007 §13 (all subsections); SPEC-000 §5
**ADRs:** —
**Depends on:** TASK-001, TASK-002, TASK-003, TASK-007

## Objective

Build the test infrastructure: conftest fixtures for database sessions with transaction rollback isolation, async httpx test client with full middleware execution, test JWT key material + token-minting fixture, and the test factory pattern. Tests must run inside Docker against the `db-test` PostgreSQL instance. Wiring the auth middleware to validate against the test key is owned by TASK-014 (which lands the middleware itself); this task produces the key material and the token fixture the middleware will later consume.

## Acceptance Criteria

- [x] `conftest.py` provides an async SQLAlchemy session fixture with per-test transaction rollback per SPEC-007 §13.2 — `db_session` fixture wraps each test in a transaction and rolls back
- [x] Test client uses `httpx.AsyncClient` with full middleware execution (no middleware bypass) per SPEC-007 §13.3 — `client` fixture via `ASGITransport(app=create_app())`
- [ ] Test auth fixture generates valid JWTs signed with a test-only RSA key pair per SPEC-007 §13.4
- [ ] Test RSA key pair is loaded from a fixed test location (env var `AUTH0_TEST_PRIVATE_KEY`/`AUTH0_TEST_PUBLIC_KEY` or file under `tests/fixtures/`), so TASK-014 can point the auth middleware at the same public key when it lands
- [ ] Token fixture accepts overrides (sub, exp, aud, custom claims) so negative-path tests (expired, wrong issuer, missing sub) are expressible without reimplementing the encoder
- [~] Test factory pattern established with sensible defaults per SPEC-007 §13.5 — generic `app_factory.py` + `crud_factory.py` scaffolds exist under `tests/factories/`; per-domain factories (Organization, Person, etc.) not yet written
- [x] Tests run via `docker compose exec backend pytest` against `db-test` on port 5433
- [ ] Coverage measured by pytest-cov with `--cov-fail-under=90` enforced in pytest config (threshold: 90%)
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest]` configured with correct DB URL and coverage settings
- [x] Factory modules scaffolded under `tests/factories/` per SPEC-007 §13.6 — directory + scaffolds present; per-domain modules deferred to the respective domain tasks

**Done so far (in code):** `conftest.py` with session-scoped engine, session-scoped table create/drop, per-test `db_session` with transaction rollback, `client` fixture with dependency override; `tests/factories/` scaffold with `app_factory.py` and `crud_factory.py`; domain test directories (`test_eav/`, `test_identity/`, `test_sessions/`, `test_notes/`, `test_billing/`, `test_compliance/`, `test_auth/`, `test_cross_cutting/`) exist.

**Remaining:** JWT test-key material (RSA keypair or env-driven), token-minting fixture with overrides, pytest.ini/pyproject coverage config with `--cov-fail-under=90`, per-domain factory modules (delivered by their respective domain tasks).

## Files

- `backend/tests/conftest.py`
- `backend/tests/factories/__init__.py`
- `backend/tests/factories/eav.py` (Organization factory)
- `backend/tests/factories/identity.py` (Person factory)
- `backend/tests/fixtures/jwt_keys/` (test RSA key material; may be generated at setup rather than committed)
- `backend/pytest.ini` or `backend/pyproject.toml`
- `backend/.coveragerc`

## Non-goals

- Domain-specific test factories (created in each domain task)
- Actual test cases (each domain task writes its own)
- Wiring the auth middleware to validate JWTs against the test key — that's TASK-014's responsibility, since the middleware does not yet exist
