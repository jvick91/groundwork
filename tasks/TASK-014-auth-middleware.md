# TASK-014: Auth Middleware — JWT Validation, Person Resolution, Org Context

**Status:** Not started
**Spec sections:** SPEC-007 §3.1 (authentication flow), §3.2 (organization context); SPEC-002 §4 (auth subject rule, soft delete rule), §9
**ADRs:** —
**Depends on:** TASK-012, TASK-013

## Objective

Implement the three-layer auth middleware: JWT validation against Auth0 JWKS, person resolution from `auth_subject`, and organization context extraction from the `X-Organization-Id` header. This middleware runs on every request except health checks and `/auth/me`. It attaches the resolved identity and org context to the request for downstream permission checking.

## Acceptance Criteria

- [ ] JWT extracted from `Authorization: Bearer {token}` header per SPEC-007 §3.1
- [ ] JWT validated against Auth0 JWKS endpoint with in-process cache per SPEC-007 §3.1 step 2
- [ ] `sub` claim extracted and matched to `Person.auth_subject` per SPEC-007 §3.1 step 3-4
- [ ] No matching Person returns 401 (`unauthorized`)
- [ ] `Person.is_active = false` returns 401 (`account_inactive`) per SPEC-007 §3.1 step 5
- [ ] `Person.deleted_at IS NOT NULL` returns 401 (`account_inactive`) per SPEC-007 §3.1 step 5
- [ ] `X-Organization-Id` required on all endpoints except `/auth/me` and `/health*` per SPEC-007 §3.2
- [ ] Missing/invalid `X-Organization-Id` returns 400 (`organization_required`) per SPEC-007 §3.2
- [ ] No active PersonRole in requested org returns 403 (`org_access_denied`) per SPEC-007 §3.1 step 8
- [ ] Resolved person, org, and active roles attached to request context (FastAPI dependency)
- [ ] `/health/ready` JWKS stub from TASK-005 is replaced with a real probe against the JWKS cache (reports healthy once the cache has loaded at least one key set)
- [ ] `/auth/me` exempted from org header requirement per SPEC-007 §3.2
- [ ] Health endpoints exempted from all auth per SPEC-007 §8.8
- [ ] Tests from SPEC-002 §11: `test_person_without_auth_subject_cannot_authenticate`, `test_inactive_person_returns_401`, `test_person_role_cross_tenant_returns_403`
- [ ] Test: missing JWT returns 401
- [ ] Test: expired JWT returns 401
- [ ] Test: missing X-Organization-Id returns 400

## Files

- `backend/app/middleware/auth.py` (JWT validation, person resolution)
- `backend/app/middleware/organization.py` (org context extraction)
- `backend/app/core/security.py` (JWKS cache, JWT decode)
- `backend/app/core/dependencies.py` (FastAPI dependencies for current_person, current_org)
- `backend/app/main.py` (middleware registration)
- `backend/tests/test_auth/test_jwt_validation.py`
- `backend/tests/test_auth/test_org_context.py`

## Non-goals

- Permission checking (TASK-015)
- Role hierarchy resolution (TASK-015)
