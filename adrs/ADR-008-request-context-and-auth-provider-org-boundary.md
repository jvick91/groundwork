# ADR-008: Request Context and Auth Provider Organization Boundary

## Status

Superseded by ADR-010 (Consolidated Auth0 Identity Architecture, accepted 2026-05-27)

## Problem

The current auth stub exposes a single `AuthContext` with `person_id` and
`organization_id`, implying every authenticated request has both a human actor
and a tenant organization scope. That is only true for ordinary tenant-scoped
requests.

Several valid workflows do not fit that shape:

- Bootstrap/onboarding: the first Organization and first Person may not exist yet.
- Platform-admin operations: a person may act across tenants without one active tenant scope.
- System-initiated actions: the actor is the system, not a human Person.

The stub currently hides that mismatch by forcing `person_id = None` for audit
FK safety while still providing a fixed `organization_id`. Routers then learn to
read `auth.person_id` and `auth.organization_id` directly even when the endpoint
does not actually require both concepts.

There is a related but separate identity architecture decision: an auth-provider
organization, such as an Auth0 Organization, is not the same as the application
`organizations` row. The auth-provider org owns identity-side concerns such as
SSO connections, invitations, and login branding. The application org owns
domain concerns such as patients, appointments, roles, audit logs, settings, and
tenant isolation. If both exist, they should be linked explicitly rather than
merged into one concept.

## Options

### Option A: Keep One Universal AuthContext

Keep a single context object with optional `person_id` and `organization_id`.
Add helper functions such as `require_tenant_context()` and
`require_person_actor()` for endpoints that need stricter guarantees.

Pros:

- Smallest near-term refactor.
- Preserves most existing router signatures.
- Can model system and platform actions by setting fields to `None`.

Cons:

- Routers can still bypass helpers and read optional fields directly.
- Illegal states remain representable.
- The codebase keeps one object pretending to cover actor identity and request scope.

### Option B: Split Dependencies by Request Type

Define separate dependencies for the major request shapes:

- `get_tenant_context()` for a person acting within an application org.
- `get_platform_context()` for a platform actor without a tenant scope.
- `get_system_context()` for system-initiated work.
- `get_bootstrap_context()` for onboarding flows that create the first org/person.

Pros:

- Router signatures clearly document endpoint requirements.
- Illegal request shapes are rejected at the dependency boundary.
- TASK-014/015 can replace each dependency with real Auth0/RBAC logic without
  changing endpoint business code.

Cons:

- More dependency types and test fixtures.
- Does not by itself separate actor semantics from scope semantics inside shared services.

### Option C: Separate Actor from Scope

Replace the universal context shape with explicit actor and scope concepts:

- `ActorContext`: who caused the action (`person`, `system`) and optional `person_id`.
- `RequestScope`: where the action applies (`tenant`, `platform`, `bootstrap`) and optional
  application `organization_id`.
- `RequestContext`: composed of `actor` and `scope`.

Router dependencies still expose purpose-specific entry points, but the shared
service contract receives precise concepts:

- Audit logging receives an actor.
- Tenant isolation receives an application organization scope.
- Bootstrap/platform/system flows do not fake either one.

Pros:

- Models the domain accurately.
- Keeps audit actor and tenant scope distinct.
- Makes Auth0 Organization integration an identity-resolution concern, not a domain-service concern.
- Gives future TASK-014/015 a clean target contract.

Cons:

- Larger refactor than Option A.
- Requires touching routers, audit call sites, tests, and auth dependency stubs.

### Option D: Seed Stub Org and Person

Keep the existing context shape and seed the stub IDs into dev/test databases.

Pros:

- Fastest way to eliminate local FK errors.
- Minimal code change.

Cons:

- Does not fix the underlying contract problem.
- Encourages production code to depend on fake tenant/person assumptions.
- Bootstrap, platform-admin, and system actions remain ambiguous.

## Chosen Approach

Choose Option D as a temporary local-development bridge.

The current implementation will keep the existing `AuthContext` shape and seed
the fixed stub Organization and Person only when the local auth stub is enabled.
This removes FK failures while exercising endpoints in Docker without committing
the platform to a final request-context architecture.

This is explicitly not the long-term design. Option C, with Option B's router
ergonomics, remains the recommended direction before TASK-014/015 replaces the
auth stub. At that point, the application should model actor and scope
separately rather than preserving the current universal context shape.

The application `organizations.id` remains the only tenant key used by domain
services, foreign keys, audit logs, and tenant isolation. Auth-provider
organization IDs, if introduced, are treated as external identity IDs and mapped
to application organizations through an explicit nullable column such as
`organizations.auth_provider_org_id`.

## Phased Plan

- [ ] Epic 1: Add a local-development seed step that creates the fixed auth-stub
  Organization and Person only when `auth_stub_enabled` is true in development.
- [ ] Epic 2: Point the auth stub at the seeded Person so audit FK constraints are
  satisfied during local endpoint testing.
- [ ] Epic 3: Before TASK-014/015, revisit Option C and define separate actor/scope
  context contracts so the permanent auth implementation does not inherit the
  temporary stub shape.
- [ ] Epic 4: If Auth0 Organizations are adopted later, map their IDs to
  application `organizations.id` through an explicit external ID column rather
  than using auth-provider org IDs in domain tables.

## Deviation Notes

SPEC-000 currently states that all API endpoints require a valid Auth0 JWT and
that every record scopes to an Organization. The temporary stub seed keeps local
development moving under the existing implementation, but it does not resolve
the final bootstrap, platform-admin, or system-action request shapes.

The domain tenant remains the application `organizations` row. Auth-provider
organizations are optional external identity records and must not replace
application organization IDs in domain tables or audit logs.
