# TASK-014E: Bootstrap First Admin

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow), SPEC-002 §8 (Person management)
**ADRs:** ADR-008 Epic 4 (resolves the cold-start gap), ADR-010
**Depends on:** TASK-014D

## Objective

One-shot operator endpoint that provisions the first `Organization`, first `Person`, first `PersonRole(system_admin)`, plus the corresponding Auth0 Organization, Auth0 user, and Auth0 Org membership. Gated by a deploy-time provisioning token file at a known path on disk (e.g., `/var/run/groundwork/bootstrap.token`); the endpoint reads the token from the file, validates it against the inbound header, and **deletes the file on success**. Subsequent calls return `410 Gone`. No env-var fallback — env vars persist and would allow re-bootstrap.

The bootstrap transaction spans both the application DB and Auth0. The two sides must succeed together; failure leaves the marker file in place so the operator can retry without leaving a half-provisioned tenant.

## Acceptance Criteria

- [ ] `POST /api/v1/system/bootstrap` endpoint exists; unauthenticated (no Auth0 JWT required) but requires `X-Bootstrap-Token` header
- [ ] Token validation reads from `BOOTSTRAP_TOKEN_PATH` env var (configurable; defaults to a known path); endpoint compares header value to file contents (constant-time)
- [ ] Endpoint returns `404 Not Found` if the marker file does not exist (no info leakage about whether bootstrap has been done)
- [ ] Endpoint returns `410 Gone` if the marker file exists but the inbound token does not match
- [ ] Endpoint returns `409 Conflict` if any `Person` already exists (defensive — should be impossible if marker file is managed correctly)
- [ ] On success: creates `Organization`, `Person`, `PersonRole(system_admin)`, Auth0 Organization, Auth0 user, and Auth0 Org membership — all in one transaction across both systems
- [ ] On success: deletes the marker file before returning 201
- [ ] On any failure (DB or Auth0 side): rolls back DB changes; if Auth0-side mutations occurred, they are reversed via Management API compensating calls; marker file is **not** deleted so the operator can retry
- [ ] Response includes the bootstrapped Person's Auth0 user ID and the password-change ticket URL (the operator delivers this to the human admin out-of-band)
- [ ] Writes `AuditLog` row with `action='system.bootstrap'`, `actor_person_id` = the newly-created Person (self-attributed)
- [ ] Tests: `test_bootstrap_succeeds_when_marker_exists_and_no_persons`, `test_bootstrap_returns_404_when_marker_absent`, `test_bootstrap_returns_410_when_token_mismatch`, `test_bootstrap_returns_409_when_persons_exist`, `test_bootstrap_rolls_back_db_on_auth0_failure`

## Files

- `backend/app/routers/system.py` (new — bootstrap endpoint)
- `backend/app/services/bootstrap_service.py` (new — orchestrates the two-side transaction)
- `backend/app/core/config.py` (`bootstrap_token_path` setting)
- `backend/tests/test_system/test_bootstrap.py`

## Non-goals

- Invitation flow (TASK-014F)
- Routine admin creation post-bootstrap (use TASK-014F invitations)
- Any UI for triggering bootstrap (operator uses curl/script with the token file)
