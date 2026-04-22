# TASK-005: Health Check Endpoints

**Status:** Not started
**Spec sections:** SPEC-007 §9, §8.8
**ADRs:** —
**Depends on:** TASK-001

## Objective

Implement the two health check endpoints: `/api/v1/health` (liveness) and `/api/v1/health/ready` (readiness). Neither requires authentication or the `X-Organization-Id` header. The readiness check verifies database connectivity and Auth0 JWKS cache status.

## Acceptance Criteria

- [ ] `GET /api/v1/health` returns 200 `{"status": "ok", "version": "1.0.0"}` with no auth required
- [ ] `GET /api/v1/health/ready` returns 200 when DB is reachable and Auth0 JWKS is cached
- [ ] `GET /api/v1/health/ready` returns 503 `{"status": "unhealthy", "checks": {...}}` when any dependency is down
- [ ] Both endpoints are excluded from auth middleware
- [ ] Tests verify both happy path and degraded states

## Files

- `backend/app/routers/health.py`
- `backend/app/main.py` (router registration)
- `backend/tests/test_cross_cutting/test_health.py`

## Non-goals

- Auth middleware implementation (TASK-014)
- JWKS caching implementation (TASK-014) — readiness check stubs the JWKS check until auth middleware exists
