# TASK-014: Auth Middleware — JWT Validation, Person Resolution, Org Context

**Status:** In progress
**Spec sections:** SPEC-007 §3.1 (authentication flow), §3.2 (organization context); SPEC-002 §4 (auth subject rule, soft delete rule), §9
**ADRs:** ADR-009 (layering), ADR-010 (consolidated auth architecture — must be Accepted before this task starts), ADR-012 (permission cache invalidation; this task adds the supporting column)
**Depends on:** TASK-012, TASK-013, TASK-014A (ADR-010 must be ratified first)

## Objective

Implement the JWT validation middleware that runs on every authenticated request: validate against Auth0 JWKS, read `sub` and `org_id` claims (Auth0 Organizations per ADR-010), resolve `Person` by `auth_subject`, verify an active `PersonRole` exists in the requested org, set `SET LOCAL app.org_id` for RLS, and attach `current_person` + `current_org` to the request context.

Bundles **one small schema migration**: add `Person.permissions_version INTEGER NOT NULL DEFAULT 0` per ADR-012. The column is used by TASK-015's cache and incremented by TASK-016/017/014J on every permission-affecting mutation.

Routine login and logout are entirely Auth0-handled (TASK-014B configures the Auth0 side); the invitation flow that writes `Person.auth_subject` is TASK-014F/G; this task only validates already-issued tokens and enforces the per-request invariants.

## Middleware check sequence (per design notes §5)

Pulled out here so reviewers can audit one ordered list:

1. **JWKS signature validation** against cached JWKS.
2. **Required claims present.** Read `sub`, `org_id`, `is_active` (enriched by TASK-014C Post-Login Action). Reject if `org_id` is missing — org-tagless tokens are invalid post-Auth0-Orgs adoption.
3. **`is_active` claim check.** Reject if false; fail-closed when missing.
4. **Resolve `Person` by `auth_subject = sub`.** Reject if no match (401), or if the row is soft-deleted (`deleted_at IS NOT NULL`) or `is_active = false` (401). The `is_active` claim from step 3 is a fast path; the DB check is authoritative.
5. **Active PersonRole in the JWT's `org_id`.** Query DB for an unrevoked `PersonRole(person_id, org_id)`. **Checked on every request, not derived from claims and not skipped on cache hit.**
6. **`SET LOCAL app.org_id = <org_id>`** inside the request transaction so RLS policies key off the correct tenant.
7. **Attach `current_person` and `current_org` to the request context** for downstream services.

## Acceptance Criteria

- [ ] JWT extracted from `Authorization: Bearer {token}` header per SPEC-007 §3.1
- [ ] JWT validated against Auth0 JWKS endpoint with in-process cache per SPEC-007 §3.1 step 2
- [ ] `sub`, `org_id`, and `is_active` claims read from validated token; missing `org_id` returns 401 (`organization_required`)
- [ ] `Person` resolved by `auth_subject = sub`; no matching Person returns 401 (`unauthorized`)
- [ ] `Person.is_active = false` returns 401 (`account_inactive`)
- [ ] `Person.deleted_at IS NOT NULL` returns 401 (`account_inactive`)
- [ ] Active `PersonRole` query in the JWT's `org_id` returns 403 (`org_access_denied`) if no row found; **this check runs on every request**, not derived from claims
- [ ] `SET LOCAL app.org_id = <org_id>` issued at the start of the request transaction so RLS policies enforce tenant scope
- [ ] `current_person` and `current_org` attached to the request context (FastAPI dependency)
- [ ] **`Person.permissions_version INTEGER NOT NULL DEFAULT 0` column added via Alembic migration** per ADR-012
- [ ] `/health/ready` gains a real JWKS probe against the cache (first task to add `auth0_jwks` to the readiness `checks` dict scaffolded in TASK-005)
- [ ] In the test environment, the auth middleware validates JWTs against the test-only public key produced by TASK-008's key fixture. All of TASK-008's negative-path token fixtures (expired, wrong audience, missing `sub`, missing `org_id`) produce real 401s through the live middleware
- [ ] The 008A auth stubs (`current_person`, `current_org`, `require_permission`) are flipped off by setting `AUTH_STUB_ENABLED=False` in the production path; tests may still opt into stub mode via a dedicated fixture where appropriate
- [ ] `/auth/me` exempted from `org_id` claim requirement per SPEC-007 §3.2
- [ ] Health endpoints exempted from all auth per SPEC-007 §8.8
- [ ] `X-Organization-Id` header is **no longer required**; `org_id` is read from the JWT claim. If the header is sent and disagrees with the JWT's `org_id`, return 400 (`organization_mismatch`).
- [ ] Tests from SPEC-002 §11: `test_person_without_auth_subject_cannot_authenticate`, `test_inactive_person_returns_401`, `test_person_role_cross_tenant_returns_403`
- [ ] **Deferred from TASK-012:** `test_soft_deleted_person_returns_401` — same shape as `test_inactive_person_returns_401`, different precondition (`Person.deleted_at IS NOT NULL`)
- [ ] Test: missing JWT returns 401
- [ ] Test: expired JWT returns 401
- [ ] Test: JWT missing `org_id` claim returns 401
- [ ] Test: `X-Organization-Id` header disagreeing with JWT `org_id` returns 400

## Files

- `backend/app/middleware/auth.py` (JWT validation, person resolution, RLS context setting)
- `backend/app/core/security.py` (JWKS cache, JWT decode)
- `backend/app/core/dependencies.py` (FastAPI dependencies for `current_person`, `current_org`)
- `backend/app/main.py` (middleware registration)
- `backend/app/models/identity.py` (`Person.permissions_version` column)
- `backend/alembic/versions/{ts}_person_permissions_version.py` (migration)
- `backend/tests/test_auth/test_jwt_validation.py`
- `backend/tests/test_auth/test_org_context.py`

## Non-goals

- Permission resolution mechanics and caching (TASK-015 + TASK-014I)
- Role hierarchy resolution (TASK-015)
- Invitation flow (TASK-014F, TASK-014G)
- Bootstrap (TASK-014E)
- Post-Login Actions / app_metadata sync (TASK-014C)
- Auth0 Management API client (TASK-014D)
- Force-kill endpoint (TASK-014J)
- Routine logout (Auth0 + SPA SDK; see TASK-014B)
