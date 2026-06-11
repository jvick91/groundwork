# TASK-014O: Auth0 Adapter

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow), SPEC-002 §4 (soft delete rule — eligibility propagation)
**ADRs:** ADR-009 (layering), ADR-010 (mechanism sections this adapter implements), ADR-013 (ports)
**Depends on:** TASK-014K, TASK-014L, TASK-014B

## Objective

Implement the Auth0 subclasses of both ports. This task **absorbs** the former TASK-014D (Management API client) and TASK-014C (Post-Login Actions + `app_metadata.is_active` mirror) — both are Auth0 *mechanism* per ADR-013 and belong inside the adapter, not in application tasks. The Management API client internals already written on the `auth-middleware` branch (`auth0_management_service.py`) are the starting point: same HTTP/M2M/retry machinery, reshaped behind the port interface.

Auth0 remains the proven fallback provider; this adapter must stay green in conformance even while SuperTokens (TASK-014N) is primary.

## Acceptance Criteria

- [ ] `backend/app/services/identity_providers/auth0.py` — `Auth0TokenVerifier(TokenVerifier)` and `Auth0ProviderAdmin(IdentityProviderAdmin)` per ADR-009; constructor injects HTTP client and config
- [ ] `Auth0TokenVerifier.verify()`: JWKS fetch with in-process cache and key rollover handling; full validation per ADR-013 contract — RS256 pinned, `iss`, `aud`, `exp`/`nbf`/`iat` with bounded leeway; `org_id` claim → `VerifiedIdentity.provider_org_ref`, missing → `OrgScopeMissingError`; `is_active` claim → `active_hint`
- [ ] Management API client (from former 014D): M2M Client Credentials token cached in-process, auto-refresh on expiry or 401; retry with exponential backoff on 429/5xx; permanent failure raises `IdentityProviderError`
- [ ] Port method mapping: `create_user`, `create_org` (Auth0 Organization), `add_org_member`, `revoke_all_sessions` (sessions + refresh-token families), `set_login_eligibility` (writes `app_metadata.is_active`), `create_signup_ticket` / `revoke_signup_ticket` (Organization invitation tickets with **provider email suppressed** — the ticket URL goes into our email per ADR-013), `healthcheck` (JWKS reachability)
- [ ] Post-Login Actions (from former 014C) versioned in `auth0/post-login-action.js`: email-verified gate, universal MFA enforcement (WebAuthn preferred), inactive-Person gate reading `app_metadata.is_active` (fail-closed when missing), claim enrichment (`org_id`, `is_active`); failure-mode contract documented in `docs/auth0-post-login-actions.md`
- [ ] Propagation-staleness window documented: 15-minute worst case for `is_active` via claim; immediate revocation is `revoke_all_sessions` (TASK-014J)
- [ ] Conformance suite (TASK-014L) passes under the `auth0_live` marker against the test tenant — per the standing rule, no Auth0 HTTP mocks
- [ ] No Auth0 imports/URLs anywhere outside this module, the TASK-014K factory, and `auth0/`
- [ ] `/health/ready` key is provider-neutral (`identity_provider`), implemented by `healthcheck()`

## Files

- `backend/app/services/identity_providers/auth0.py` (new — reshaped from `auth-middleware` branch's `auth0_management_service.py` + JWKS logic from its `core/security.py`)
- `auth0/post-login-action.js` (salvaged from `auth-middleware` branch)
- `docs/auth0-post-login-actions.md` (salvaged from `auth-middleware` branch)
- `backend/app/core/dependencies.py` (register in factory)
- `backend/tests/conformance/conftest.py` (auth0 live-tenant fixture, `auth0_live` marker)

## Non-goals

- Auth0 tenant configuration (TASK-014B)
- Application-side eligibility call sites (`identity_service` calls the port; TASK-012/014J scope)
- Invitation email content/delivery (TASK-014P)
