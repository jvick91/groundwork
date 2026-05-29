# TASK-014F: Invitation Resource (Model, CRUD, State Machine)

**Status:** Shipped
**Spec sections:** SPEC-002 §2 (PersonRole entity_instance rules), §4 (assignment integrity), SPEC-007 §8 (endpoint inventory)
**ADRs:** ADR-002 (FK-only), ADR-003 (partial unique index pattern), ADR-009 (service/model layering), ADR-010, ADR-011
**Depends on:** TASK-014D

## Objective

Introduce the `Invitation` table — the **one new table for the entire auth chain** — with full CRUD endpoints, state machine, audit hooks, and the four-type discriminator. Implements the send side of the invitation flow per ADR-011: validates the type-specific payload, creates the Invitation row in `pending` state with a generated nonce, calls Auth0 Management API (TASK-014D) to add organization membership if needed (type 4) and create the Auth0 Organization invitation, and returns the uniform response envelope that closes the cross-tenant email enumeration vector.

`PersonRole` is **not** created in this task — the planned role lives on the Invitation row until the accept transaction in TASK-014G fires.

## Acceptance Criteria

- [ ] `Invitation` model added per ADR-011 schema: `id`, `organization_id`, `type` enum, `email`, `first_name`, `last_name`, `planned_role_slug`, `planned_entity_instance_id`, `planned_entity_instance_payload` (JSONB), `nonce`, `state` enum, `auth0_invitation_id`, `created_by_person_id`, timestamps (`created_at`, `accepted_at`, `expired_at`, `revoked_at`, `expires_at`)
- [ ] Partial unique index `(organization_id, email) WHERE state = 'pending'` per ADR-003
- [ ] `POST /api/v1/invitations` creates an invite; requires `invites.send` permission; discriminates on `type` field
- [ ] Provider invites (type 1) require `planned_entity_instance_payload` or `planned_entity_instance_id`; admin and system_admin invites (types 2 and 3) reject either
- [ ] System_admin invites (type 3) callable only by an existing `system_admin`
- [ ] Cross-org invites (type 4) require an existing `Person` with `auth_subject` set; backend calls Auth0 Management API to add the existing Auth0 user as a member of the target Auth0 Organization **before** creating the Auth0 invitation
- [ ] All invite types: backend calls Auth0 Management API to create the Auth0 organization invitation; stores the returned Auth0 invitation ID on the Invitation row
- [ ] `GET /api/v1/invitations` lists invitations for the requesting org; filterable by state; requires `invites.read`
- [ ] `GET /api/v1/invitations/{id}` retrieves single invitation; requires `invites.read`
- [ ] `POST /api/v1/invitations/{id}/resend` rotates the nonce, revokes the previous Auth0 invitation, creates a new one, refreshes `expires_at`; requires `invites.send`; only valid on `state = 'pending'`
- [ ] `DELETE /api/v1/invitations/{id}` sets `state = 'revoked'`, revokes the Auth0 invitation; requires `invites.revoke`; only valid on `state = 'pending'`
- [ ] All state transitions write `AuditLog` rows
- [ ] **Uniform response shape** per ADR-011: `POST /invitations` returns `{status: "pending", invitation_id: "<uuid>"}` regardless of whether the email maps to an existing Person, was newly provisioned, or is a cross-org reactivation
- [ ] `organization_id` is stamped from request context, never accepted from request body
- [ ] Tests: `test_create_provider_invite_succeeds`, `test_create_admin_invite_succeeds`, `test_create_system_admin_invite_requires_system_admin_permission`, `test_create_cross_org_invite_adds_auth0_org_membership`, `test_duplicate_pending_invite_same_email_returns_409`, `test_resend_rotates_nonce`, `test_revoke_invite_sets_revoked_state`, `test_uniform_response_shape_regardless_of_existing_person`, `test_organization_id_in_body_ignored`

## Files

- `backend/app/models/identity.py` (add `Invitation` model)
- `backend/app/enums/identity.py` (add `InvitationType`, `InvitationState`)
- `backend/app/schemas/identity.py` (add `InvitationCreate*`, `InvitationResponse`)
- `backend/app/services/invitation_service.py` (new)
- `backend/app/routers/invitations.py` (new)
- `backend/alembic/versions/{ts}_invitation_table.py` (migration)
- `backend/tests/test_invitations/test_create.py`
- `backend/tests/test_invitations/test_resend_revoke.py`
- `backend/tests/test_invitations/test_uniform_response.py`

## Non-goals

- The accept endpoint and binding logic (TASK-014G)
- Seeding `invites.send`, `invites.revoke`, `invites.read` permissions in the catalog (TASK-016 follow-on migration)
- Type 5 (bootstrap) — that lives in TASK-014E with a different auth model
