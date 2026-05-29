# ADR-011 — Invitation lifecycle and PersonRole post-accept

**Date:** 2026-05-21
**Author:** claude-code
**Status:** Accepted

## Context

ADR-010 ratifies that `Person.auth_subject` is bound exclusively through invitation acceptance — there is no email-matching fallback, no self-service signup path. That ratification leaves the invitation resource itself unspecified: what its shape is, what states it transitions through, when `PersonRole` is created, and how the five distinct invite types share an endpoint without becoming a tangle of conditionals.

Several sub-decisions cluster here:

- Whether `PersonRole` is created when the invite is sent (with a "pending" status column) or only when the invite is accepted (no pending state on PersonRole).
- Whether email and role are inferred from existing `Person` rows or always carried on the invite itself.
- How the cross-org existing-Person case (type 4) differs from new-Person invites in side effects.
- What the audit log records at each transition.
- How response shapes prevent cross-tenant email enumeration.

Resolving these as a single design is cheaper than handling each at implementation time, because PersonRole's state shape and Invitation's state machine are coupled.

## Decision

### Invitation as a first-class resource

`Invitation` is a new table backing `POST /api/v1/invitations` and the surrounding CRUD endpoints. It is scoped to one `Organization` (the `organization_id` is stamped from the request context, never from the body). The row carries the *planned* identity changes that will land on accept, plus a single-use nonce that is the only binding key.

Schema (load-bearing fields only):

- `id` — UUID PK
- `organization_id` — FK, NOT NULL, set from request context
- `type` — enum `('provider', 'admin', 'system_admin', 'cross_org')`
- `email` — NOT NULL (used by Auth0 to send the invite; never by our backend to resolve a Person)
- `first_name`, `last_name` — nullable, populated for types 1–3, null for type 4
- `planned_role_slug` — NOT NULL, the role to grant on accept
- `planned_entity_instance_id` — nullable; required when the role's `primary_domain` maps to a person_subtype EntityType (see SPEC-002 §2)
- `planned_entity_instance_payload` — JSONB nullable; if set, an `EntityInstance` is created on accept from this payload
- `nonce` — opaque single-use string, indexed unique
- `state` — enum `('pending', 'accepted', 'expired', 'revoked')`
- `auth0_invitation_id` — nullable; populated after Auth0's invitation API is called (for revocation cleanup)
- `created_by_person_id` — NOT NULL (FK to Person; the inviter)
- `created_at`, `accepted_at`, `expired_at`, `revoked_at` — timestamps
- `expires_at` — NOT NULL; aligned to Auth0's invitation TTL

A partial unique index `(organization_id, email) WHERE state = 'pending'` prevents two pending invites for the same email in the same org. Revoked and expired rows are historical and do not conflict with new sends.

### State machine

```
pending → accepted    (nonce posted, Person + PersonRole written, terminal)
pending → expired     (TTL hit, terminal)
pending → revoked     (admin canceled, terminal)
```

All transitions write an `AuditLog` row. `accepted` is immutable. The invitation may not be resurrected from `expired` or `revoked` — a new invitation row is created instead (the partial unique index on pending rows does not conflict with the historical row).

### PersonRole is created at accept, never at send

The Invitation row carries the *planned* `PersonRole` shape (`planned_role_slug`, `planned_entity_instance_id`, `planned_entity_instance_payload`). No `PersonRole` row exists until the accept transition fires. Inside the accept transaction:

1. Resolve the invitation by nonce; verify `state = 'pending'` and `now() < expires_at`.
2. For new-Person invites (types 1–3): create the `Person` row with `auth_subject = JWT.sub`. For cross-org invites (type 4): confirm a `Person` with matching `auth_subject` already exists and reuse it.
3. For provider invites (type 1): create the `EntityInstance` from `planned_entity_instance_payload` (or verify `planned_entity_instance_id` exists and matches the role's domain).
4. Create the `PersonRole(person_id, role_slug, organization_id, entity_instance_id)`.
5. Transition the invitation: `state = 'accepted'`, `accepted_at = now()`.
6. Increment `Person.permissions_version` (per ADR-012) so any cached permissions for the new Person are invalidated.
7. Write `AuditLog` row: `action = 'invitation.accepted'`, `actor_person_id = newly-bound Person`, `previous_state = pending`, `next_state = accepted`.

The whole sequence is one transaction. Partial failure rolls back; the invitation stays `pending` and can be retried (until TTL).

### Why PersonRole-at-accept rather than at-send

Two designs were considered:

- **Option 1 (chosen):** PersonRole exists only after accept. Invitation carries the planned role; commit happens at accept. `PersonRole.revoked_at IS NULL` continues to mean "active" — no third state.
- **Option 2:** PersonRole created at invite send with a new `accepted_at` (nullable) column. Active grants require both `revoked_at IS NULL` and `accepted_at IS NOT NULL`.

Option 1 is chosen because Option 2 requires every permission resolution query in TASK-015, every PersonRole listing in TASK-017, and every reporting query downstream to filter on `accepted_at IS NOT NULL` in addition to `revoked_at IS NULL`. One forgotten filter and a pending-but-not-accepted PersonRole leaks effective permissions. Option 1 makes the rule simpler ("active" = `revoked_at IS NULL`) and removes a class of mistake.

The cost of Option 1 is that the invitation row carries duplicate role/instance data (planned vs eventual). That cost is bounded: the invitation row is short-lived (7 days TTL) and the duplication is read-only once accepted.

### Five invite types, one endpoint

`POST /api/v1/invitations` discriminates on the `type` field. The five types are documented in `auth0-design-notes.md` §3 and reproduced in TASK-014F's acceptance criteria. Key points:

- **Type 1 (provider)** — requires `planned_entity_instance_payload` or `planned_entity_instance_id`. Creates Person + Auth0 user + EntityInstance + PersonRole on accept.
- **Type 2 (admin)** — no entity_instance. Creates Person + Auth0 user + PersonRole on accept.
- **Type 3 (system_admin)** — same as admin but role is platform-scoped (no `organization_id` on PersonRole). Callable only by an existing `system_admin`.
- **Type 4 (cross_org)** — existing `Person` with `auth_subject` already set. Creates only PersonRole on accept. Before sending the Auth0 invitation, the backend calls Auth0 Management API to add the existing Auth0 user as a member of the target Auth0 Organization (Auth0 will not issue an org-scoped JWT until membership exists).
- **Type 5 (bootstrap)** — exists outside the `/invitations` endpoint. See `POST /api/v1/system/bootstrap` (TASK-014E); gated by a one-shot deploy token, not by an authenticated invitation flow.

### Uniform response shape (enumeration mitigation)

Every successful `POST /api/v1/invitations` response returns the same envelope:

```json
{ "status": "pending", "invitation_id": "<uuid>" }
```

regardless of whether the target email maps to an existing `Person` in another tenant, was newly provisioned, or was a cross-org reactivation. The sender cannot distinguish the cases. Differentiating logic lives entirely on the accept path (where the actor is the invitee themselves, not the inviter).

This is a load-bearing privacy property for a HIPAA-bound platform: an admin must not be able to probe whether a clinician works at a competing practice by typing their email into the invite form.

### Resend rotates the nonce

`POST /api/v1/invitations/{id}/resend` is permitted only when `state = 'pending'`. The action:

1. Generates a new nonce.
2. Calls Auth0 Management API to revoke the existing Auth0 invitation and create a new one (so the old email link is dead).
3. Updates `expires_at` to a fresh TTL from now.
4. Writes an `AuditLog` row.

The old nonce is unrecoverable. Anyone holding the old email link gets a 410 Gone from `POST /invitations/accept`.

### Revoke is non-destructive

`DELETE /api/v1/invitations/{id}` sets `state = 'revoked'` and `revoked_at = now()`. The row is preserved for audit. The Auth0 invitation is revoked via Management API. The partial unique index on `(organization_id, email) WHERE state = 'pending'` allows a fresh invitation to be sent immediately.

## Consequences

**For:**

- Permission queries downstream of this ADR have one rule for "active grant": `revoked_at IS NULL`. No "pending invite" hidden state.
- Cross-tenant enumeration is closed at the response-shape layer, not by convention.
- The nonce binding is single-use, single-purpose, and impossible to confuse with email lookup.
- Type 4 (cross-org existing Person) shares the same endpoint shape as other invites, so the invitation resource is uniform. The type-specific work happens behind the API.
- Bootstrap (type 5) lives at a separate endpoint with a different auth model (deploy token, not JWT), so the `/invitations` endpoint never has to consider unauthenticated callers.

**Against:**

- Invitation rows carry duplicated identity data (planned vs eventual). This is acceptable because invitations are short-lived (7-day TTL).
- The accept transaction does six things in sequence (resolve, create-Person, create-EntityInstance, create-PersonRole, transition-invitation, audit) plus the `permissions_version` increment. It must be transactional; partial commit produces an unusable Person row.
- Type 4 (cross-org) requires the backend to call Auth0 Management API twice (add-to-Org, then create-invitation) on the send path. Missing the first step produces an invitation that delivers a token without the target org scope.

## Alternatives considered

**PersonRole created at invite send with `accepted_at` column (Option 2 above).** Already covered. Rejected because every downstream permission query becomes a two-filter query, and one forgotten filter leaks permissions.

**Auth0-driven invitation only, no application Invitation table.** Use Auth0's invitation primitives end-to-end; backend reads invitation state from Auth0. Rejected: application-level state (planned role, planned entity_instance, audit trail) has nowhere to live, and querying Auth0 per request to resolve an in-flight invitation is operationally fragile.

**Multiple type-specific endpoints (`POST /invitations/provider`, `/invitations/admin`, etc.).** Each endpoint validates its own payload shape. Rejected as ceremony: the four types share more than they differ, and the discriminator-on-`type` pattern is well-established. The complexity that the multiple-endpoints option would push out is real but lives at the validator layer, where it belongs.

**Allow `Person.auth_subject` rebinding via invitation.** Would let an invitation overwrite `auth_subject` if the Person already had one. Rejected: makes the invitation a credential-takeover vector. Cross-org invites (type 4) confirm the existing `auth_subject` matches the JWT's `sub`; they do not write a new one.

## Phased plan

- [ ] Epic 1: TASK-014F (Invitation resource) implements the table, CRUD endpoints, and state machine.
- [ ] Epic 2: TASK-014G (accept binding) implements the accept transaction in full.
- [ ] Epic 3: TASK-016 seed catalog migration adds `invites.send`, `invites.revoke`, `invites.read` permissions.
- [ ] Epic 4: TASK-017 acceptance criteria explicitly note that PersonRole creation via invite-accept is a separate code path from `POST /people/{id}/roles` direct assignment, and both must increment `permissions_version`.
- [ ] Epic 5: SPEC-007 §8.1 endpoint inventory updated with the `/invitations` endpoints.

## References

- ADR-002 — FK-only with explicit joins.
- ADR-003 — partial unique indexes for revocable records (the `WHERE state = 'pending'` index follows this pattern).
- ADR-009 — service + model-as-entity; the `Invitation` model lives as one aggregate under that pattern.
- ADR-010 — consolidated auth architecture; this ADR is its binding-mechanism detail.
- ADR-012 — permission cache invalidation; the accept transaction's `permissions_version` increment is defined there.
- SPEC-002 §2 — `PersonRole` and `entity_instance_id` rules.
- SPEC-002 §4 — auth subject rule, assignment integrity rule.
- SPEC-006 §3, §7 — `AuditLog` semantics, audit atomicity requirement.
