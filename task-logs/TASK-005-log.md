# TASK-005 Log — Health Check Endpoints

**Agent:** cursor
**Branch:** health-check-endpoints
**Date completed:** 2026-03-26

## What Was Done

### `backend/app/routers/health.py` — new file
- `GET /health` (liveness): returns `{"status": "ok", "version": "..."}`.
- `GET /health/ready` (readiness): runs `SELECT 1` against the DB engine and returns `{"status": "ready"/"unhealthy", "checks": {"database": "ok"/"error"}}` with HTTP 200/503.
- The `checks` dict is intentionally open-ended — TASK-014 adds `auth0_jwks` without changing the envelope shape.
- DB check extracted into a standalone async dependency `_check_database` so tests can override it with `app.dependency_overrides` without needing mocks.

### `backend/app/main.py`
- Removed the inline `GET /api/v1/health` route returning `"healthy"`.
- Imported `health_router` and registered it at `/api/v1` prefix.

### `backend/tests/test_cross_cutting/test_health.py` — rewritten
- 9 tests: liveness 200 / `status == "ok"` / version present; readiness 200 / `"ready"` / `checks.database == "ok"`; DB-degraded 503 / `"unhealthy"` / `checks.database == "error"`; checks-dict extensibility assertion.

## Decisions Made

- **Injectable `_check_database` dependency:** The DB probe is a named FastAPI dependency overridable via `app.dependency_overrides`. This avoids patching `Database.get_engine` with `unittest.mock`, which would violate the no-mocks convention. Overriding a FastAPI dependency is idiomatic and tests the handler logic directly.

## Deviations from Task

None. All acceptance criteria implemented.

## Open Items

TASK-014 will add `auth0_jwks` to the `checks` dict and its corresponding dependency.
