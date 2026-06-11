# TASK-014J: Force-Kill (Operator-Triggered Session/Refresh Revocation)

**Status:** Not started
**Spec sections:** SPEC-002 §4 (soft delete and revocation), SPEC-007 §8 (endpoint inventory)
**ADRs:** ADR-009, ADR-010 §3 (policy), ADR-012, ADR-013 (provider operations through `IdentityProviderAdmin`)
**Depends on:** TASK-014B, TASK-014C, TASK-014I

## Objective

Administrative endpoint for security-incident response: revoke **all** provider sessions and refresh token families for a specific Person across every device, immediately. Triggered manually by an operator with the new `auth.force_revoke` permission (`system_admin` only by default). Bypasses the routine 15-minute access-token TTL window when the situation demands it (clinician termination after a breach, suspected credential compromise, regulatory hold).

This is the operational counterpart to routine `set_login_eligibility` propagation: eligibility handles routine deactivation within the TTL window; this endpoint handles the "now, across all devices" path.

**Provider-blind:** the service calls `IdentityProviderAdmin.revoke_all_sessions` and `set_login_eligibility`; which provider executes them is the composition root's concern. Tests run against the `FakeIdentityProvider`.

## Acceptance Criteria

- [ ] `POST /api/v1/people/{id}/force-revoke` endpoint exists; requires `auth.force_revoke` permission
- [ ] Endpoint flow (in one transaction):
  1. Call `revoke_all_sessions(subject)` on the port to terminate the target Person's sessions and refresh-token families
  2. Set `Person.is_active = false` and call `set_login_eligibility(subject, False)` so the provider refuses new logins
  3. Increment `Person.permissions_version` so any in-flight cached permissions are invalidated on next request (per ADR-012)
  4. Write `AuditLog` row: `action='auth.force_revoke'`, `actor_person_id = operator`, `resource_type='Person'`, `resource_id = target Person's id`
- [ ] If a port call fails permanently (`IdentityProviderError`): the transaction rolls back (no `is_active=false` write, no version bump, no audit row) and the error propagates as 502 Bad Gateway
- [ ] Endpoint returns 404 if the target Person does not exist
- [ ] Endpoint returns 422 if the operator tries to force-revoke themselves (defensive — `system_admin` should not self-revoke through this path)
- [ ] Endpoint returns 409 if the target Person is already `is_active=false` (idempotent semantics: surface the no-op explicitly rather than silently re-running)
- [ ] Tests: `test_force_revoke_succeeds_for_active_person`, `test_force_revoke_rolls_back_on_provider_failure`, `test_force_revoke_requires_permission`, `test_force_revoke_self_returns_422`, `test_force_revoke_already_inactive_returns_409`, `test_force_revoke_increments_permissions_version`, `test_force_revoke_writes_audit_log`

## Files

- `backend/app/services/identity_service.py` (add `force_revoke` method)
- `backend/app/routers/identity.py` (add force-revoke endpoint)
- `backend/tests/test_identity/test_force_revoke.py`

## Non-goals

- Routine logout (provider-handled; see TASK-014M / TASK-014K)
- Routine deactivation via `PATCH /people/{id}` setting `is_active=false` (TASK-012; covered by `set_login_eligibility` propagation)
- Bulk revocation (single Person only; multi-target would be a separate task if needed)
