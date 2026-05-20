# TASK-014: Auth Middleware — JWT Validation, Person Resolution, Org Context

**Status:** Complete (pending commit + task log)
**Spec sections:** SPEC-007 §3.1 (authentication flow), §3.2 (organization context), §13.4 (auth in tests, amended by ADR-010); SPEC-002 §4 (auth subject rule, soft delete rule), §9
**ADRs:** ADR-009, ADR-010
**Depends on:** TASK-012, TASK-013

## Objective

Implement the three-layer auth middleware: JWT validation against Auth0 JWKS, person resolution from `auth_subject`, and organization context extraction from the `X-Organization-Id` header. This middleware runs on every request except health checks and `/auth/me`. It attaches the resolved identity and org context to the request for downstream permission checking.

## Acceptance Criteria

- [x] JWT extracted from `Authorization: Bearer {token}` header per SPEC-007 §3.1
- [x] JWT validated against Auth0 JWKS endpoint with in-process cache per SPEC-007 §3.1 step 2
- [x] `sub` claim extracted and matched to `Person.auth_subject` per SPEC-007 §3.1 step 3-4
- [x] No matching Person returns 401 (`unauthorized`)
- [x] `Person.is_active = false` returns 401 (`account_inactive`) per SPEC-007 §3.1 step 5
- [x] `Person.deleted_at IS NOT NULL` returns 401 (`account_inactive`) per SPEC-007 §3.1 step 5
- [x] `X-Organization-Id` required on all endpoints except `/auth/me` and `/health*` per SPEC-007 §3.2
- [x] Missing/invalid `X-Organization-Id` returns 400 (`organization_required`) per SPEC-007 §3.2
- [x] No active PersonRole in requested org returns 403 (`org_access_denied`) per SPEC-007 §3.1 step 8
- [x] Resolved person, org, and active roles attached to request context (FastAPI dependency)
- [x] `/health/ready` gains a real JWKS probe against the cache (reports healthy once the cache has loaded at least one key set). This is the first task that adds an `auth0_jwks` key to the readiness `checks` dict scaffolded in TASK-005
- [x] In the test environment, the auth middleware validates JWTs against a containerized Keycloak realm's JWKS endpoint per ADR-010. Negative-path cases that test our code — expired tokens (real Keycloak 1-second-lifespan client + sleep), tampered signatures, missing tokens, missing `sub`, missing matching Person, inactive Person, soft-deleted Person — all produce real 401s through the live middleware. Wrong-audience and wrong-issuer claim checks are **not** tested here because those failures are produced inside `joserfc`'s `JWTClaimsRegistry` (third-party); our code's exception-to-401 conversion is already covered by the invalid-signature and expired-token tests, and our config wiring is exercised end-to-end by every happy-path test. The TASK-008 local-keypair fixture (`tests/fixtures/jwt_keys.py`) and the test that pinned its shape (`tests/test_cross_cutting/test_jwt_fixture.py`) are removed by this task
- [x] The 008A auth stubs (`current_person`, `current_org`, `require_permission`) are flipped off by setting `AUTH_STUB_ENABLED=false` in `backend/.env.backend` (applies to dev, test, and production paths). No test fixture opts back into stub mode — every test authenticates through real Keycloak via the default `client` fixture which seeds alice and bakes her token into requests. The stub code in `app/core/security.py` remains as a defensive fallback (returns a fixed identity if the flag is ever flipped on); no test exercises that fallback
- [x] `/auth/me` exempted from org header requirement per SPEC-007 §3.2
- [x] Health endpoints exempted from all auth per SPEC-007 §8.8
- [x] Tests from SPEC-002 §11: `test_person_without_auth_subject_cannot_authenticate`, `test_inactive_person_returns_401`, `test_person_role_cross_tenant_returns_403`
- [x] **Deferred from TASK-012:** `test_soft_deleted_person_returns_401` (SPEC-002 §11, "soft delete rule" / §4 auth subject rule). TASK-012 listed this in its AC but could not implement it because the 401 path is owned by this middleware. Add it here alongside `test_inactive_person_returns_401` — same shape, different precondition (`Person.deleted_at IS NOT NULL`).
- [x] Test: missing JWT returns 401
- [x] Test: expired JWT returns 401
- [x] Test: missing X-Organization-Id returns 400

## Files

- `backend/app/middleware/auth.py` (JWT validation, person resolution)
- `backend/app/middleware/organization.py` (org context extraction)
- `backend/app/core/security.py` (JWKS cache, JWT decode, OIDC discovery)
- `backend/app/core/dependencies.py` (FastAPI dependencies for current_person, current_org, JWKS resolver factory)
- `backend/app/core/config.py` (Keycloak-mode config knobs)
- `backend/app/core/lifespan.py` (production-config startup warning)
- `backend/app/main.py` (middleware registration)
- `backend/app/routers/health.py` (auth0_jwks readiness check)
- `backend/tests/conftest.py` (Keycloak token-factory fixtures)
- `backend/tests/test_auth/test_jwt_validation.py`
- `backend/tests/test_auth/test_org_context.py`
- `adrs/ADR-009-service-repository-model-as-entity.md` (amendment permitting `middleware/`)
- `adrs/ADR-010-auth-test-infrastructure-keycloak.md` (new)
- `specs/SPEC-007-api-contract-and-testing.md` (§13.4 amendment)
- `docker-compose.yml` (new `keycloak` service)
- `docker/keycloak/realm-groundwork-test.json` (realm import — new)
- `.claude/skills/task-finish/scripts/docker_test.sh` (wait on Keycloak health)
- `docker-entrypoint.sh` (CRLF → LF; was breaking the backend container on Windows checkouts)
- `backend/.env.backend` (`AUTH_STUB_ENABLED=false`; `OIDC_*` env vars pointing at Keycloak realm)
- `backend/tests/test_identity/test_people.py` (`http_client` fixture migrated to real Keycloak auth)
- `backend/tests/test_eav/test_organizations.py` (`http_client` fixture migrated)
- `backend/tests/test_eav/test_entity_types.py` (`et_client` fixture migrated)
- `backend/tests/test_compliance/test_audit_log.py` (dead `audit_client` fixture removed)
- `backend/tests/test_cross_cutting/test_error_responses.py` (`ec` fixture seeds alice + auth headers)
- `backend/tests/test_cross_cutting/test_request_logging.py` (inline `AsyncClient` in 500-test gets auth headers)
- `STATE.md` (active-task pointer, branch, last architectural change)

### Files removed by this task

- `backend/tests/fixtures/jwt_keys.py` (TASK-008 local-keypair fixture; replaced by Keycloak per ADR-010)
- `backend/tests/test_cross_cutting/test_jwt_fixture.py` (TASK-008 fixture self-test; obsolete)
- `backend/tests/test_cross_cutting/test_stub_dependencies.py` (pinned the stub-mode return shape; stub is now disabled everywhere via `.env.backend`, so this test asserts a precondition that never holds)

## In-flight scope expansion (recorded 2026-05-20)

This task expanded beyond its original SPEC-007 §3.1/§3.2 scope to make the
"no mocks, no monkeypatch, real auth" constraint workable end-to-end across
the whole test suite. The additional work landed under TASK-014 rather than
a separate task because the existing tests would have been broken in a
half-migrated state otherwise.

- **OIDC env-var rename.** `AUTH0_DOMAIN` / `AUTH0_AUDIENCE` / `AUTH0_ISSUER`
  (+ matching settings fields) renamed to `OIDC_*`. Vendor-neutral; same
  middleware code works against Auth0 in production and Keycloak in tests
  by changing only the issuer URL. ADR-010 flagged this rename as a
  follow-up; it landed in lockstep.
- **Permission-resolution preview in `OrganizationMiddleware`.** Walks
  `PersonRole` → role hierarchy (`parent_role_id`) → `RolePermission` →
  `Permission` and populates `AuthContext.permissions` with the real slug
  set. No caching, no row-level filtering — those remain TASK-015's job.
  Implemented here because the alternative (empty permissions set) would
  have failed every legacy `require_permission(...)` check and broken ~190
  existing tests. TASK-015 will wrap this with the 60-second TTL cache and
  add condition-evaluation per SPEC-002 §6.
- **Default `client` fixture auto-authenticates.** Seeds alice
  (`Person.id = _STUB_PERSON_ID`, `auth_subject =
  11111111-1111-1111-1111-111111111111` matching Keycloak), her org
  (`Organization.id = _STUB_ORG_ID`), a `test-admin` role with every
  permission slug declared by any router, the grants linking them, and
  alice's `PersonRole`. Idempotent across tests. Fetches her Keycloak
  token via Direct Access Grants (password flow) and bakes
  `Authorization` + `X-Organization-Id` headers into the `AsyncClient` so
  legacy tests authored against the stub identity (~190 of them) keep
  working without per-file rework. Per-file `http_client` / `et_client` /
  `ec` fixtures were migrated to the same pattern.
- **`docker_test.sh` simplified.** Single pytest invocation. The earlier
  two-pass (stub-mode + Keycloak-mode) design was discarded after the user
  chose "one mode" — `.env.backend` carries the Keycloak config so every
  pytest process inherits it.

Final suite state at task close: **307 passed, 0 xfailed, 0 skipped, 0
failed**. 86.11% coverage. The shortfall under the 90% target is the
defensive stub-mode fallback paths in `app/core/security.py` and
`app/middleware/*.py` — they never fire while `AUTH_STUB_ENABLED=false`.

## Non-goals

- Permission checking (TASK-015)
- Role hierarchy resolution (TASK-015)
