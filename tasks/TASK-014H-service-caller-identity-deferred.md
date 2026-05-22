# TASK-014H: Service Caller Identity — DEFERRED

**Status:** Deferred (not in MVP)
**Spec sections:** SPEC-002 §4, SPEC-006 §3, SPEC-007 §3.1
**ADRs:** ADR-010 §6
**Depends on:** (TBD when reactivated)

## Status note

This task is **deferred** per ADR-010 §6. MVP has no inbound machine-to-machine callers:

- Webhook receivers (Stripe and similar, when they exist) authenticate by shared-secret signature, not JWT
- Outbound integrations (insurance eligibility checks, appointment reminders) run *as* the Groundwork backend itself, not as separate authenticated clients
- Scheduled work (consent expiry sweep per ADR-006) is invoked as an authenticated admin HTTP request; the human operator is the audit actor

Introducing a `ServicePrincipal` abstraction now, before any real caller exists, would be speculative design.

## When to reactivate

Reactivate this task when the first real inbound M2M caller is proposed:

- A separate analytics service querying our API on its own credentials
- A partner integration that authenticates server-to-server (not via shared-secret webhook signature)
- An internal microservice extracted from the monolith

## Scope when reactivated

The work is well-defined; it is additive to the existing schema:

- [ ] `ServicePrincipal` table: `id`, `name`, `auth0_client_id`, `is_active`, timestamps
- [ ] `ServicePrincipalPermission` table — direct permission grants (OAuth scope pattern, no role layer); columns `(service_principal_id, permission_slug, conditions)` with the same conditions JSONB as `RolePermission`
- [ ] `AuditLog` migration: add `actor_type` enum (`'human' | 'service'`) and `actor_service_principal_id` nullable FK; existing rows default to `actor_type='human'`; check constraint that exactly one of `actor_person_id` / `actor_service_principal_id` is non-null (or both null for system-triggered events)
- [ ] Middleware branch on JWT claim shape: tokens with `gty=client_credentials` and no user `sub` resolve to a `ServicePrincipal` by `auth0_client_id`
- [ ] Permission resolution branch: service principals skip the role hierarchy walk and consult `ServicePrincipalPermission` directly
- [ ] `/auth/me` returns 404 for service principal callers (per ADR-010 documented as human-only)
- [ ] Admin endpoints (`POST /api/v1/service-principals`, list, revoke) gated by a new `service_principals.manage` permission held only by `system_admin`
- [ ] Tests covering each branch

## Reference

The migration path is documented in detail in ADR-010 §6. Read that section before reactivating this task.

## Non-goals

(All deferred; reactivate when first inbound M2M caller is proposed.)
