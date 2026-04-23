# TASK-008: Test Infrastructure & Fixtures

**Status:** Not started
**Spec sections:** SPEC-007 §13 (all subsections); SPEC-000 §5
**ADRs:** —
**Depends on:** TASK-001, TASK-002, TASK-003, TASK-007

## Objective

Build the test infrastructure: conftest fixtures for database sessions with transaction rollback isolation, async httpx test client with full middleware execution, test JWT key material + token-minting fixture, and the test factory pattern. Tests must run inside Docker against the `db-test` PostgreSQL instance. Wiring the auth middleware to validate against the test key is owned by TASK-014 (which lands the middleware itself); this task produces the key material and the token fixture the middleware will later consume.

## Acceptance Criteria

- [ ] `conftest.py` provides an async SQLAlchemy session fixture with per-test transaction rollback per SPEC-007 §13.2
- [ ] Test client uses `httpx.AsyncClient` with full middleware execution (no middleware bypass) per SPEC-007 §13.3
- [ ] Test auth fixture generates valid JWTs signed with a test-only RSA key pair per SPEC-007 §13.4
- [ ] Test RSA key pair is loaded from a fixed test location (env var `AUTH0_TEST_PRIVATE_KEY`/`AUTH0_TEST_PUBLIC_KEY` or file under `tests/fixtures/`), so TASK-014 can point the auth middleware at the same public key when it lands
- [ ] Token fixture accepts overrides (sub, exp, aud, custom claims) so negative-path tests (expired, wrong issuer, missing sub) are expressible without reimplementing the encoder
- [ ] Test factory pattern established with sensible defaults per SPEC-007 §13.5
- [ ] Tests run via `docker compose exec backend pytest` against `db-test` on port 5433
- [ ] Coverage measured by pytest-cov with `--cov-fail-under=90` enforced in pytest config (threshold: 90%)
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest]` configured with correct DB URL and coverage settings
- [ ] Factory modules scaffolded under `tests/factories/` per SPEC-007 §13.6

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
