# TASK-014E: Bootstrap First Admin

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow), SPEC-002 §8 (Person management)
**ADRs:** ADR-008 Epic 4 (resolves the cold-start gap), ADR-010 (policy), ADR-013 (provider operations go through `IdentityProviderAdmin`)
**Depends on:** TASK-014K, TASK-014L

## Objective

One-shot operator endpoint that provisions the first `Organization`, first `Person`, first `PersonRole(system_admin)`, plus the corresponding provider-side org, user, and org membership — all through the `IdentityProviderAdmin` port (`create_org`, `create_user`, `add_org_member`, `create_signup_ticket`). Gated by a deploy-time provisioning token file at a known path on disk (e.g., `/var/run/groundwork/bootstrap.token`); the endpoint reads the token from the file, validates it against the inbound header, and **deletes the file on success**. Subsequent calls return `410 Gone`. No env-var fallback — env vars persist and would allow re-bootstrap.

The bootstrap transaction spans the application DB and the identity provider. The two sides must succeed together; failure leaves the marker file in place so the operator can retry without leaving a half-provisioned tenant.

**Provider-blind:** this task imports the port, never a concrete provider. Tests run against the `FakeIdentityProvider` (TASK-014L), including the compensation paths.

## Acceptance Criteria

- [ ] `POST /api/v1/system/bootstrap` endpoint exists; unauthenticated (no bearer token required) but requires `X-Bootstrap-Token` header
- [ ] Token validation reads from `BOOTSTRAP_TOKEN_PATH` env var (configurable; defaults to a known path); endpoint compares header value to file contents (constant-time)
- [ ] Endpoint returns `404 Not Found` if the marker file does not exist (no info leakage about whether bootstrap has been done)
- [ ] Endpoint returns `410 Gone` if the marker file exists but the inbound token does not match
- [ ] Endpoint returns `409 Conflict` if any `Person` already exists (defensive — should be impossible if marker file is managed correctly)
- [ ] On success: creates `Organization` (with `auth_provider_org_id` set from the port's `create_org` return), `Person`, `PersonRole(system_admin)`, and the provider-side org, user, and membership — one logical transaction across both systems
- [ ] On success: deletes the marker file before returning 201
- [ ] On any failure (DB or provider side): rolls back DB changes; provider-side mutations already performed are reversed via compensating port calls; marker file is **not** deleted so the operator can retry
- [ ] Response includes the bootstrapped Person's provider subject and the credential-setup URL from `create_signup_ticket` (the operator delivers this to the human admin out-of-band — no email is sent for bootstrap)
- [ ] Writes `AuditLog` row with `action='system.bootstrap'`, `actor_person_id` = the newly-created Person (self-attributed)
- [ ] Tests: `test_bootstrap_succeeds_when_marker_exists_and_no_persons`, `test_bootstrap_returns_404_when_marker_absent`, `test_bootstrap_returns_410_when_token_mismatch`, `test_bootstrap_returns_409_when_persons_exist`, `test_bootstrap_rolls_back_db_on_provider_failure`, `test_bootstrap_compensates_provider_side_on_db_failure`

## Files

- `backend/app/routers/system.py` (new — bootstrap endpoint)
- `backend/app/services/bootstrap_service.py` (new — orchestrates the two-side transaction against the port)
- `backend/app/core/config.py` (`bootstrap_token_path` setting)
- `backend/tests/test_system/test_bootstrap.py`

## Non-goals

- Invitation flow (TASK-014F); routine admin creation post-bootstrap (use TASK-014F invitations)
- Provider-specific provisioning mechanics (adapters: TASK-014N, TASK-014O)
- Any UI for triggering bootstrap (operator uses curl/script with the token file)
