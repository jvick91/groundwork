# TASK-014J: Force-Kill (Operator-Triggered Session/Refresh Revocation)

**Status:** Not started
**Spec sections:** SPEC-002 §4 (soft delete and revocation), SPEC-007 §8 (endpoint inventory)
**ADRs:** ADR-009, ADR-010 §3, ADR-012
**Depends on:** TASK-014C (provides the `app_metadata.is_active` mirroring webhook), TASK-014D (provides Management API client), TASK-014I (provides cache invalidation discipline)

## Objective

Administrative endpoint for security-incident response: revoke **all** Auth0 sessions and refresh token families for a specific Person across every device, immediately. Triggered manually by an operator with the new `auth.force_revoke` permission (`system_admin` only by default). Bypasses the routine 15-minute access-token TTL window when the situation demands it (clinician termination after a breach, suspected credential compromise, regulatory hold).

This is the operational counterpart to TASK-014C's routine `app_metadata.is_active` mirroring: `is_active` propagation handles routine deactivation within the TTL window; this endpoint handles the "now, across all devices" path.

## Acceptance Criteria

- [ ] `POST /api/v1/people/{id}/force-revoke` endpoint exists; requires `auth.force_revoke` permission
- [ ] Endpoint flow (in one transaction):
  1. Call Auth0 Management API (via TASK-014D client) to revoke the target Person's sessions and refresh-token families for our application
  2. Set `Person.is_active = false` (the Post-Login Action sync from TASK-014C will mirror to `app_metadata`)
  3. Increment `Person.permissions_version` so any in-flight cached permissions are invalidated on next request (per ADR-012)
  4. Write `AuditLog` row: `action='auth.force_revoke'`, `actor_person_id = operator`, `resource_type='Person'`, `resource_id = target Person's id`
- [ ] If Auth0 Management API call fails: the transaction rolls back (no `is_active=false` write, no version bump, no audit row) and a `GroundworkError` propagates as 502 Bad Gateway
- [ ] Endpoint returns 404 if the target Person does not exist
- [ ] Endpoint returns 422 if the operator tries to force-revoke themselves (defensive — `system_admin` should not self-revoke through this path)
- [ ] Endpoint returns 409 if the target Person is already `is_active=false` (idempotent semantics: surface the no-op explicitly rather than silently re-running)
- [ ] Tests: `test_force_revoke_succeeds_for_active_person`, `test_force_revoke_rolls_back_on_auth0_failure`, `test_force_revoke_requires_permission`, `test_force_revoke_self_returns_422`, `test_force_revoke_already_inactive_returns_409`, `test_force_revoke_increments_permissions_version`, `test_force_revoke_writes_audit_log`

## Files

- `backend/app/services/identity_service.py` (add `force_revoke` method)
- `backend/app/routers/identity.py` (add force-revoke endpoint)
- `backend/tests/test_identity/test_force_revoke.py`

## Non-goals

- Routine logout (Auth0 + SPA SDK; see TASK-014B)
- Routine deactivation via `PATCH /people/{id}` setting `is_active=false` (TASK-012; covered by `app_metadata` sync)
- Bulk revocation (single Person only; multi-target would be a separate task if needed)
