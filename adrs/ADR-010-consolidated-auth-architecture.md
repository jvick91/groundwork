# ADR-010 — Consolidated Auth0 identity architecture

**Date:** 2026-05-21
**Author:** claude-code
**Status:** Accepted (supersedes ADR-008)

## Context

TASK-014 was scoped as "JWT validation middleware" with the assumption that an Auth0-issued token would arrive containing a `sub` claim that maps to a `Person.auth_subject`. Several decisions are implicit in that scope and need to be ratified before TASK-014 ships, because the JWT shape and the surrounding identity ceremony are load-bearing for everything downstream.

The implicit decisions:

- Whether Auth0 Organizations are adopted (org-bound JWTs vs tenant-agnostic JWTs with header scope).
- How users sign up and bind to a `Person` row (self-service vs invite-only; if invited, how `auth_subject` gets written).
- What MFA policy applies and which factors are acceptable for a HIPAA-bound clinical product.
- How access-token TTL is balanced against revocation latency.
- Whether multiple authentication connections (email/password, Google SSO, Microsoft SSO) can attach to the same user.
- Whether non-human callers (cron jobs, integrations, M2M services) get their own identity model now or later.

Leaving these as implementation-time decisions inside TASK-014 risks producing a system that is HIPAA-defensible only by accident. ADR-008 (Proposed) acknowledged the request-context part of this gap but parked it under a temporary stub seed. This ADR resolves it.

## Decision

The following six positions are adopted together. They are coupled in the sense that each one assumes the others; partial adoption produces an inconsistent JWT shape and a more complex middleware.

### 1. Auth0 Organizations: adopted

Every authenticated request carries an Auth0-issued JWT with an `org_id` claim that identifies the application `Organization` the token is scoped to. A token issued for org_1 is not valid against org_2 — the middleware rejects mismatched scope at the JWT layer, before any database read.

The application `Organization.id` remains the only tenant key used by domain FKs, audit logs, and RLS. Auth0's organization IDs are external identity IDs mapped to application organizations through `organizations.auth_provider_org_id` (nullable) per ADR-008's existing direction.

Consequence: org-switching is a fresh login against the target org, not a mid-session header swap. A clinician with roles in two practices acquires two distinct tokens, never one fungible token.

### 2. MFA: universal, WebAuthn/passkeys preferred

MFA is required for every authenticated user. No opt-out tier. Preferred factor is WebAuthn (passkeys, security keys); TOTP and SMS remain available as fallbacks but are not the default enrollment path. Enforcement happens inside an Auth0 Post-Login Action that fails closed when MFA has not been completed for the current session.

### 3. Token TTL: 5–15 minute access tokens with refresh rotation

Access tokens carry a 5–15 minute TTL. Refresh tokens use rotation with reuse/breach detection (Auth0's native feature): each refresh issues a new RT and invalidates the prior; parallel use of the same RT invalidates the entire family. No backend-maintained revocation list.

The 15-minute upper bound on access-token TTL is the worst-case staleness window for `Person.is_active = false` propagation. That window is acceptable for routine deactivation; immediate revocation after a security event uses the force-kill operator endpoint (TASK-014J), which calls Auth0 Management API to terminate sessions and refresh families.

### 4. First-login binding: nonce-only, never by email

Application Persons are bound to Auth0 `sub` claims exclusively through invitation-acceptance nonces:

1. An admin creates an `Invitation` row with a unique single-use nonce.
2. Auth0 emails the invitee using its own organization-invitation primitives.
3. After Auth0 signup, the frontend posts `{nonce, jwt}` to `POST /api/v1/invitations/accept`.
4. The backend resolves the invitation by nonce, validates state and TTL, writes `Person.auth_subject = JWT.sub`, creates the planned `PersonRole`, and transitions the invitation to `accepted`.

No email lookup, ever. There is no code path on the backend that resolves an Auth0 user to a `Person` via email matching. This eliminates the cross-tenant enumeration vector (an admin cannot probe whether an email already exists in another tenant) and gives every binding a tamper-evident, single-use token.

The full invitation lifecycle is detailed in ADR-011.

### 5. Auth0 `sub` stability: single connection per user (MVP)

Every Auth0 user belongs to exactly one connection (email/password + WebAuthn passkey for MVP). Users cannot link a Google or Microsoft identity to an existing account. New signups go through the configured connection.

Account-linking — Auth0's primary-user / secondary-user model that allows multiple identity providers to attach to one logical user — is the documented upgrade path when SSO becomes a customer requirement. It is not in MVP. Multiple `Principal` rows per human is explicitly rejected as a path forward.

Roadmap note: practices wanting Google Workspace or Microsoft 365 SSO at sign-up cannot have it under this decision. If early customer conversations surface SSO as a hard requirement, a follow-up ADR moves account-linking into scope.

### 6. Service caller identity: not modeled

One authenticated principal type — a human, identified by `Person.auth_subject`. System-originated events use `AuditLog.actor_person_id = NULL` per SPEC-006 §3. Inbound webhooks (Auth0 Log Streams, Stripe, etc.) are verified per the issuing vendor's signing standard, not via JWT or any custom scheme. No `Principal` or `ServicePrincipal` abstraction.

## Consequences

**For:**

- The JWT shape is fully specified before TASK-014 writes a line of code. Downstream tasks (014C–G, 014I, 014J, 015–019) compose against a stable contract.
- Stolen access tokens are bounded to one org for at most 15 minutes. Refresh token theft is detected and family-revoked by Auth0 natively.
- Tenant isolation has two layers: the JWT's `org_id` claim (issuance-time) and Postgres RLS keyed on `app.org_id` (query-time). Either layer alone would be insufficient; together they are HIPAA-defensible.
- The seam between Auth0 identity and our `Person` model is single-purpose: invitation-accept writes `auth_subject`, every other login resolves by `auth_subject`. There is no email-matching backdoor.
- MVP schema delta is minimal: one new table (`Invitation`, per ADR-011), one new column (`Person.permissions_version`, per ADR-012), four seed permission rows. No Principal abstraction.

**Against:**

- Practices wanting SSO from day one are not supported; the account-linking upgrade is post-MVP work.
- The 15-minute access-token TTL means routine deactivation propagation has a 15-minute worst-case window. For incident response, this is mitigated by the TASK-014J force-kill endpoint, but operators must remember the procedure exists.
- Org-switching as a fresh login is a worse UX than header-swap for clinicians who work across multiple practices. The security gain (bounded stolen-token blast radius) is judged to be worth the friction.

## Alternatives considered

**Tenant-agnostic JWT with `X-Organization-Id` header.** Earlier-drafted approach. Cheaper to implement (no Auth0 Orgs setup), but a stolen token is valid against every org the bearer has a role in. Rejected on security grounds.

**Backend-driven invitations using Auth0 Management API tickets.** A backend-controlled flow that creates the Auth0 user, generates a password-change ticket, sends the email itself. Works regardless of whether Auth0 Organizations are adopted. Rejected as the primary path because Auth0 Organizations' native invitation flow handles email delivery, TTL, and ticket lifecycle for free, and the org-scoping property makes it the natural fit.

**Email-fallback binding (try `sub`, then email).** Would let users sign up via Auth0 Universal Login without an invitation, then bind to an existing Person row by email match. Rejected: leaks cross-tenant existence and creates a path where any Auth0 user with a known email can bind to a Person they should not have access to.

**`Principal` / `ServicePrincipal` abstraction.** Rejected. One principal type is sufficient — webhooks verify per vendor signing standard, outbound and scheduled work runs as the backend itself. No parallel identity model.

**Long-lived access tokens (1+ hour) with backend revocation list.** Simpler refresh story, but requires us to maintain a revocation list and consult it per request — adding a database hit per auth check and a new failure mode (revocation list unavailable → fail-open or fail-closed?). Rejected: short TTLs + RT rotation gives equivalent security with no backend state.

## Phased plan

- [ ] Epic 1: Update SPEC-007 §3 (auth flow) to reference Auth0 Organizations and the nonce-binding model. Mark ADR-008 superseded.
- [ ] Epic 2: TASK-014A acceptance criteria reference this ADR as the foundational contract.
- [ ] Epic 3: TASK-014B (Auth0 tenant configuration) implements the Auth0-side configuration this ADR mandates (Organizations enabled, universal MFA policy, RT rotation + breach detection, single-connection setup).
- [ ] Epic 4: TASK-014 (JWT middleware) implements the JWT contract this ADR defines (validate `sub` + `org_id`, resolve `Person`, check active `PersonRole`, set `app.org_id`).

## References

- ADR-002 — no `relationship()`; FK-only with explicit joins.
- ADR-006 — consent expiry sweep endpoint; system-triggered invocation model.
- ADR-008 — request-context and auth-provider org boundary (superseded by this ADR).
- ADR-009 — service + model-as-entity layering; the architecture this ADR's middleware composes against.
- ADR-011 — invitation lifecycle and PersonRole post-accept (this ADR's binding mechanism is detailed there).
- ADR-012 — permission cache invalidation strategy (this ADR's permission resolution layer).
- SPEC-002 §3, §4, §5 — identity and RBAC model; auth subject rule, soft delete rule.
- SPEC-006 §3 — `AuditLog.actor_person_id` null semantics for system-triggered events.
- SPEC-007 §3 — authentication and organization context.
