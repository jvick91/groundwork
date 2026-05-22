# TASK-014C: Auth0 Post-Login Actions & Inactive-Person Sync

**Status:** Not started
**Spec sections:** SPEC-002 §4 (auth subject rule, soft delete rule), SPEC-007 §3.1
**ADRs:** ADR-010 §2 (MFA), §3 (TTL), §6 (Person.is_active surface)
**Depends on:** TASK-014B

## Objective

Implement the Auth0 Post-Login Action chain that enforces email-verification, universal MFA, and the inactive-Person gate before a JWT is issued. The inactive-Person gate must **not** call the backend synchronously per login — instead, `Person.is_active` is mirrored to Auth0 `app_metadata.is_active` via an event-driven backend webhook on every Person state change, and the Action reads the cached claim. Documents and enforces a fail-open vs fail-closed contract per Action; all three Actions in this task are fail-closed.

## Acceptance Criteria

- [ ] Auth0 Post-Login Action: **email verified gate** — rejects login if `email_verified === false`; fail-closed (no token issued)
- [ ] Auth0 Post-Login Action: **MFA enforcement** — rejects login if MFA has not been completed for the current session; fail-closed; WebAuthn preferred per ADR-010 §2
- [ ] Auth0 Post-Login Action: **inactive-Person gate** — rejects login if `app_metadata.is_active === false`; fail-closed when the claim is missing (treat as inactive)
- [ ] Auth0 Post-Login Action: **claim enrichment** — bakes `org_id`, `is_active` into the issued JWT for use by the backend middleware
- [ ] Backend webhook endpoint mirrors `Person.is_active` to `app_metadata.is_active` on every Person state change (activation, deactivation, soft-delete). Implemented as a service-method side effect, not a separate scheduler.
- [ ] Webhook failures (Auth0 Management API unreachable) are retried with exponential backoff; permanent failure raises a `GroundworkError` so the Person state change rolls back rather than leaving Auth0 stale
- [ ] Documented failure-mode contract for each Action (fail-open vs fail-closed) in `docs/auth0-post-login-actions.md`
- [ ] Propagation-staleness window documented in the same doc: 15-minute worst-case for `is_active` deactivation; immediate revocation uses TASK-014J force-kill
- [ ] Test: a Person whose `is_active` is set to `false` cannot acquire a new JWT after the next refresh cycle; existing access tokens continue to work until expiry (up to 15 min)

## Files

- `auth0/post-login-action.js` (Auth0-side; versioned alongside backend)
- `backend/app/services/identity_service.py` (mirror `is_active` on Person state change)
- `backend/app/services/auth0_sync_service.py` (new — webhook to Auth0 Management API)
- `docs/auth0-post-login-actions.md` (failure-mode contract, staleness window doc)
- `backend/tests/test_auth/test_app_metadata_sync.py`

## Non-goals

- Management API client itself (TASK-014D)
- Force-kill operator endpoint (TASK-014J)
- Permission claim enrichment beyond `org_id` and `is_active`
