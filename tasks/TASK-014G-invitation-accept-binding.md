# TASK-014G: Invitation Accept Endpoint & Nonce Binding

**Status:** Not started
**Spec sections:** SPEC-002 §2 (PersonRole entity_instance rules), §4 (auth subject rule, assignment integrity), SPEC-007 §3.1 (auth flow), §8 (endpoint inventory)
**ADRs:** ADR-009, ADR-010 §4, ADR-011, ADR-012
**Depends on:** TASK-014F

## Objective

Implement `POST /api/v1/invitations/accept`, the only path that writes `Person.auth_subject`. Takes `{nonce, jwt}`, resolves the `Invitation` by nonce, validates state and TTL, performs the type-specific identity binding inside one transaction, and transitions the invitation to `accepted`. **Nonce-only — no email lookup, ever.** Increments `Person.permissions_version` (ADR-012) as part of the same transaction so any cached permissions for the newly bound Person are correct on the next request.

## Acceptance Criteria

- [ ] `POST /api/v1/invitations/accept` endpoint accepts `{nonce: string, jwt: string}` body; does **not** require an `X-Organization-Id` header (the invitation row carries the org)
- [ ] Endpoint validates the inbound JWT against Auth0 JWKS (same path as TASK-014 middleware); reads `sub` and `org_id` claims
- [ ] Endpoint resolves the `Invitation` by `nonce`; returns `410 Gone` if not found, expired, revoked, or already accepted
- [ ] Endpoint verifies `Invitation.organization_id == JWT.org_id`; returns `422` on mismatch
- [ ] For types 1–3 (new Person): creates the `Person` row with `auth_subject = JWT.sub`, plus first_name/last_name from the Invitation
- [ ] For type 1 (provider): also creates the `EntityInstance` from `planned_entity_instance_payload` (or validates the existing `planned_entity_instance_id` belongs to the same org)
- [ ] For type 4 (cross-org existing Person): looks up the `Person` by `auth_subject = JWT.sub`; returns `409 Conflict` if no matching Person exists (the type-4 invite was created for a Person that does not actually have a Person row yet)
- [ ] Creates `PersonRole(person_id, planned_role_slug, organization_id, planned_entity_instance_id)`
- [ ] Increments `Person.permissions_version` in the same transaction (per ADR-012)
- [ ] Transitions the `Invitation` to `accepted` with `accepted_at = now()`
- [ ] Writes `AuditLog` row: `action='invitation.accepted'`, `actor_person_id = newly-bound Person`, snapshots of previous and next state
- [ ] Entire flow is one transaction; any failure rolls back all DB changes; the Invitation stays `pending` and can be retried (until TTL)
- [ ] **No email matching anywhere in this code path.** Code review must reject any `WHERE email = ?` SELECT in the accept service method.
- [ ] Tests: `test_accept_with_valid_nonce_and_jwt_writes_auth_subject_and_person_role`, `test_accept_with_unknown_nonce_returns_410`, `test_accept_with_expired_nonce_returns_410`, `test_accept_with_revoked_nonce_returns_410`, `test_accept_with_already_accepted_nonce_returns_410`, `test_accept_provider_creates_entity_instance`, `test_accept_cross_org_existing_person_creates_only_person_role`, `test_accept_cross_org_unknown_auth_subject_returns_409`, `test_accept_org_id_mismatch_returns_422`, `test_accept_increments_permissions_version`, `test_accept_writes_audit_log`

## Files

- `backend/app/services/invitation_service.py` (extend with `accept_invitation` method)
- `backend/app/routers/invitations.py` (add `accept` endpoint)
- `backend/tests/test_invitations/test_accept.py`

## Non-goals

- The send/list/resend/revoke endpoints (TASK-014F)
- Any email-based lookup or fallback (explicitly forbidden — see AC)
- Direct `POST /people/{id}/roles` assignment (that's TASK-017)
