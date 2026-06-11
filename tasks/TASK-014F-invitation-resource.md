# TASK-014F: Invitation Resource (Model, CRUD, State Machine)

**Status:** Not started
**Spec sections:** SPEC-002 §2 (PersonRole entity_instance rules), §4 (assignment integrity), SPEC-007 §8 (endpoint inventory)
**ADRs:** ADR-002 (FK-only), ADR-003 (partial unique index pattern), ADR-009 (service/model layering), ADR-010 (policy), ADR-011 (lifecycle — email ownership amended by ADR-013), ADR-013 (provider operations through the port; application owns the email)
**Depends on:** TASK-014B, TASK-014C, TASK-014D

## Objective

Introduce the `Invitation` table — the **one new table for the entire auth chain** — with full CRUD endpoints, state machine, audit hooks, and the four-type discriminator. Implements the send side of the invitation flow per ADR-011 as amended by ADR-013: validates the type-specific payload, creates the Invitation row in `pending` state with a generated nonce, obtains a credential-setup URL from the provider via `IdentityProviderAdmin.create_signup_ticket` (adding org membership first via `add_org_member` for type 4), sends **our own** invitation email (TASK-014D) containing the accept URL + ticket URL, and returns the uniform response envelope that closes the cross-tenant email enumeration vector.

`PersonRole` is **not** created in this task — the planned role lives on the Invitation row until the accept transaction in TASK-014G fires.

**Provider-blind:** imports the ports only; tests run against the `FakeIdentityProvider` and the `CapturingEmailSender`.

## Acceptance Criteria

- [ ] `Invitation` model added per ADR-011 schema: `id`, `organization_id`, `type` enum, `email`, `first_name`, `last_name`, `planned_role_slug`, `planned_entity_instance_id`, `planned_entity_instance_payload` (JSONB), `nonce`, `state` enum, `external_invitation_id` (stores `SignupTicket.external_ref`; renamed from ADR-011's `auth0_invitation_id` per ADR-013), `created_by_person_id`, timestamps (`created_at`, `accepted_at`, `expired_at`, `revoked_at`, `expires_at`)
- [ ] Partial unique index `(organization_id, email) WHERE state = 'pending'` per ADR-003
- [ ] `POST /api/v1/invitations` creates an invite; requires `invites.send` permission; discriminates on `type` field
- [ ] Provider invites (type 1) require `planned_entity_instance_payload` or `planned_entity_instance_id`; admin and system_admin invites (types 2 and 3) reject either
- [ ] System_admin invites (type 3) callable only by an existing `system_admin`
- [ ] Cross-org invites (type 4) require an existing `Person` with `auth_subject` set; the service calls `add_org_member(org_ref, subject)` **before** `create_signup_ticket` (the provider will not issue org-scoped tokens until membership exists)
- [ ] All invite types: the service calls `create_signup_ticket(org_ref, email, ttl)` and stores `external_ref` on the Invitation row; `expires_at` aligns with the ticket TTL
- [ ] Invitation email sent via TASK-014D containing the accept URL (with nonce) and the ticket URL; email send failure rolls the send transaction back (no orphaned pending Invitation)
- [ ] `GET /api/v1/invitations` lists invitations for the requesting org; filterable by state; requires `invites.read`
- [ ] `GET /api/v1/invitations/{id}` retrieves single invitation; requires `invites.read`
- [ ] `POST /api/v1/invitations/{id}/resend` rotates the nonce, calls `revoke_signup_ticket(old_ref)` then `create_signup_ticket` for a fresh one, refreshes `expires_at`, sends a new email; requires `invites.send`; only valid on `state = 'pending'`
- [ ] `DELETE /api/v1/invitations/{id}` sets `state = 'revoked'` and calls `revoke_signup_ticket`; requires `invites.revoke`; only valid on `state = 'pending'`
- [ ] All state transitions write `AuditLog` rows
- [ ] **Uniform response shape** per ADR-011: `POST /invitations` returns `{status: "pending", invitation_id: "<uuid>"}` regardless of whether the email maps to an existing Person, was newly provisioned, or is a cross-org reactivation
- [ ] `organization_id` is stamped from request context, never accepted from request body
- [ ] Tests: `test_create_provider_invite_succeeds`, `test_create_admin_invite_succeeds`, `test_create_system_admin_invite_requires_system_admin_permission`, `test_create_cross_org_invite_adds_org_membership_before_ticket`, `test_duplicate_pending_invite_same_email_returns_409`, `test_resend_rotates_nonce_and_ticket`, `test_revoke_invite_sets_revoked_state_and_revokes_ticket`, `test_uniform_response_shape_regardless_of_existing_person`, `test_organization_id_in_body_ignored`, `test_email_send_failure_rolls_back_invitation`

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
- Email transport and templates (TASK-014D — this task calls it)
- Seeding `invites.send`, `invites.revoke`, `invites.read` permissions in the catalog (TASK-016 follow-on migration)
- Type 5 (bootstrap) — that lives in TASK-014E with a different auth model
