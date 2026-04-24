# TASK-005: Health Check Endpoints

**Status:** Complete
**Spec sections:** SPEC-007 §9, §8.8
**ADRs:** —
**Depends on:** TASK-001

## Objective

Implement the two health check endpoints: `/api/v1/health` (liveness) and `/api/v1/health/ready` (readiness). Neither requires authentication or the `X-Organization-Id` header. The readiness check verifies database connectivity only in this task; JWKS probe is added by TASK-014 once auth middleware exists.

## Acceptance Criteria

- [x] `GET /api/v1/health` returns 200 `{"status": "ok", "version": "..."}` — extracted to `app/routers/health.py`, registered via `include_router`
- [x] `GET /api/v1/health/ready` returns 200 `{"status": "ready", "checks": {"database": "ok"}}` when DB is reachable
- [x] `GET /api/v1/health/ready` returns 503 `{"status": "unhealthy", "checks": {...}}` when DB is unreachable
- [x] `checks` dict is structured to allow TASK-014 to add an `auth0_jwks` key without changing the envelope
- [x] Both endpoints are excluded from auth middleware (no auth middleware yet — implicitly satisfied until TASK-014)
- [x] Tests verify both happy path and DB-degraded states — 9 tests

## Files

- `backend/app/routers/health.py`
- `backend/app/main.py` (router registration)
- `backend/tests/test_cross_cutting/test_health.py`

## Non-goals

- Auth middleware implementation (TASK-014)
- JWKS cache probe — added by TASK-014 which owns the JWKS cache
