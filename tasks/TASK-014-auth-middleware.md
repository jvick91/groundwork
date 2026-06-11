# TASK-014: Auth Middleware — Token Verification, Person Resolution, Org Context

**Status:** Not started
**Spec sections:** SPEC-007 §3.1 (authentication flow), §3.2 (organization context); SPEC-002 §4 (auth subject rule, soft delete rule), §9
**ADRs:** ADR-009 (layering), ADR-010 (auth policy — must be Accepted before this task starts), ADR-012 (permission cache invalidation; this task adds the supporting column), ADR-013 (identity provider ports — this middleware consumes `TokenVerifier`)
**Depends on:** TASK-012, TASK-013, TASK-014A, TASK-014K, TASK-014L

## Objective

Implement the auth middleware that runs on every authenticated request: verify the bearer token through the `TokenVerifier` port (ADR-013), resolve `Person` by `auth_subject = VerifiedIdentity.subject`, map `VerifiedIdentity.provider_org_ref` to the application `Organization` via `organizations.auth_provider_org_id`, verify an active `PersonRole` exists in that org, set `SET LOCAL app.org_id` for RLS, and attach `current_person` + `current_org` to the request context.

**Provider-blind by construction:** this task imports the port, never a concrete provider. Which provider verifies the token is decided by the TASK-014K composition root. All tests run against the `FakeIdentityProvider` (TASK-014L).

Bundles **one small schema migration**: add `Person.permissions_version INTEGER NOT NULL DEFAULT 0` per ADR-012. The column is used by TASK-015's cache and incremented by TASK-016/017/014J on every permission-affecting mutation.

Routine login and logout are entirely provider-handled; the invitation flow that writes `Person.auth_subject` is TASK-014F/G; this task only verifies already-issued tokens and enforces the per-request invariants.

## Middleware check sequence

1. **`TokenVerifier.verify(token)`** — the port performs full verification (pinned algorithm, `iss`, `aud`, `exp`/`nbf`/`iat` with bounded leeway, org scope present) and returns `VerifiedIdentity` or raises. The middleware maps port exceptions to responses; it never re-implements claim checks.
2. **`active_hint` fast path.** If the port returned `active_hint is False`, reject immediately; `None`/`True` proceeds — the DB check in step 3 is authoritative either way.
3. **Resolve `Person` by `auth_subject = subject`.** Reject if no match (401), soft-deleted (`deleted_at IS NOT NULL`, 401), or `is_active = false` (401).
4. **Resolve `Organization` by `auth_provider_org_id = provider_org_ref`.** Reject if no match (401).
5. **Active PersonRole in the resolved org.** Query DB for an unrevoked `PersonRole(person_id, organization_id)`. **Checked on every request, not derived from claims and not skipped on cache hit.**
6. **`SET LOCAL app.org_id = <organization_id>`** inside the request transaction so RLS policies key off the correct tenant. (Note: `SET LOCAL` is only an enforcement layer once RLS policies exist on tenant tables — tracked as a security-review follow-up, not silently assumed.)
7. **Attach `current_person` and `current_org` to the request context** for downstream services.

## Acceptance Criteria

- [ ] Token extracted from `Authorization: Bearer {token}` header per SPEC-007 §3.1
- [ ] Token verified exclusively through `TokenVerifier.verify()`; the middleware contains **no** JWT decoding, JWKS handling, or claim validation of its own
- [ ] Port exceptions map to responses: `TokenExpiredError` → 401 (`token_expired`), `OrgScopeMissingError` → 401 (`organization_required`), other `TokenInvalidError` → 401 (`unauthorized`)
- [ ] `Person` resolved by `auth_subject = subject`; no matching Person returns 401 (`unauthorized`)
- [ ] `Person.is_active = false` returns 401 (`account_inactive`); `Person.deleted_at IS NOT NULL` returns 401 (`account_inactive`)
- [ ] `Organization` resolved by `auth_provider_org_id = provider_org_ref`; no match returns 401 (`unauthorized`)
- [ ] Active `PersonRole` query in the resolved org returns 403 (`org_access_denied`) if no row found; **this check runs on every request**
- [ ] `SET LOCAL app.org_id = <organization_id>` issued at the start of the request transaction
- [ ] `current_person` and `current_org` attached to the request context (FastAPI dependency)
- [ ] **`Person.permissions_version INTEGER NOT NULL DEFAULT 0` column added via Alembic migration** per ADR-012
- [ ] `/health/ready` gains a provider-neutral `identity_provider` readiness key wired to the port's `healthcheck()` (replaces the previously planned `auth0_jwks` key)
- [ ] In the test environment, the middleware runs against the `FakeIdentityProvider`; the fake's negative-path tokens (expired, `nbf` violation, wrong audience, missing subject, missing org scope) produce real 401s through the live middleware
- [ ] The 008A auth stubs (`current_person`, `current_org`, `require_permission`) are flipped off by setting `AUTH_STUB_ENABLED=False` in the production path; tests may still opt into stub mode via a dedicated fixture where appropriate
- [ ] `/auth/me` exempted from the org-scope requirement per SPEC-007 §3.2; health endpoints exempted from all auth per SPEC-007 §8.8
- [ ] `X-Organization-Id` header is **no longer required**; org scope comes from the token. If the header is sent and disagrees with the token's org, return 400 (`organization_mismatch`).
- [ ] Tests from SPEC-002 §11: `test_person_without_auth_subject_cannot_authenticate`, `test_inactive_person_returns_401`, `test_person_role_cross_tenant_returns_403`
- [ ] **Deferred from TASK-012:** `test_soft_deleted_person_returns_401`
- [ ] Tests: missing token returns 401; expired token returns 401; token missing org scope returns 401; future-`nbf` token returns 401; wrong-audience token returns 401; `X-Organization-Id` disagreeing with token org returns 400; no concrete provider module imported by the middleware (assert via import graph or grep in test)

## Files

- `backend/app/middleware/auth.py` (port-driven verification, person resolution, RLS context setting)
- `backend/app/core/dependencies.py` (FastAPI dependencies for `current_person`, `current_org`)
- `backend/app/main.py` (middleware registration)
- `backend/app/models/identity.py` (`Person.permissions_version` column)
- `backend/alembic/versions/{ts}_person_permissions_version.py` (migration)
- `backend/tests/test_auth/test_token_verification.py`
- `backend/tests/test_auth/test_org_context.py`

## Non-goals

- Token verification internals (the adapters: TASK-014N, TASK-014O; the contract: TASK-014K)
- Permission resolution mechanics and caching (TASK-015 + TASK-014I)
- Invitation flow (TASK-014F, TASK-014G); bootstrap (TASK-014E); force-revoke (TASK-014J)
- RLS policy creation on tenant tables (security-review follow-up; step 6 documents the dependency)
- Routine logout (provider-handled; see TASK-014B / TASK-014M)
