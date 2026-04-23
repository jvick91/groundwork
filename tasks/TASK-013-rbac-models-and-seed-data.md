# TASK-013: RBAC Models & Seed Data

**Status:** Not started
**Spec sections:** SPEC-002 §2 (Role, Permission, PersonRole, RolePermission), §3 (seed roles, seed permissions, seed role-permission matrix, inheritance model), §4 (hierarchy invariant, revocation rule)
**ADRs:** ADR-002, ADR-003 (partial unique indexes)
**Depends on:** TASK-009, TASK-012

## Objective

Implement the four RBAC tables — Role, Permission, PersonRole, RolePermission — with their partial unique indexes, and seed all 11 roles, 44 permissions, and the complete role-permission grant matrix from SPEC-002 §3. This includes the standalone biller/receptionist model (not children of admin) per SPEC-002 §3 inheritance model.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `Role` ORM model at `backend/app/models/models.py:257`; `Permission` at `:282`; `PersonRole` at `:302`; `RolePermission` at `:342`.
- `RoleDomain` enum at `:56` — note: shipped as `RoleDomain`, not `PrimaryDomain` as originally specced; update any references accordingly.
- Tables `roles`, `permissions`, `person_roles`, `role_permissions` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: **seed migration** (11 roles, all system permissions, full role-permission matrix with conditions), verify partial unique indexes per ADR-003 are present (check migration; add a follow-up migration if missing), Pydantic schemas, factory. No API endpoints in this task — those belong to 016/017.

## Acceptance Criteria

- [x] Role model with all SPEC-002 §2 fields: id, organization_id (nullable), name, slug, primary_domain (`RoleDomain` enum — renamed from `PrimaryDomain` during implementation), parent_role_id (self-FK), is_system_role, description, created_at, updated_at
- [x] Permission model with all SPEC-002 §2 fields: id, organization_id (nullable), resource_slug, action (String — see TASK-002 rationale; the §2 enum description is advisory, the §3 seed matrix is authoritative), slug, description, is_system_permission, created_at
- [x] PersonRole model with all SPEC-002 §2 fields: id, organization_id, person_id, role_id, entity_instance_id (nullable), assigned_at, assigned_by_person_id (nullable), revoked_at
- [x] RolePermission model with all SPEC-002 §2 fields: id, organization_id, role_id, permission_id, conditions (JSONB, nullable), granted_at, granted_by_person_id (nullable), revoked_at
- [ ] Partial unique index on PersonRole: `UNIQUE(organization_id, person_id, role_id, entity_instance_id) WHERE revoked_at IS NULL` per ADR-003
- [ ] Partial unique index on RolePermission: `UNIQUE(organization_id, role_id, permission_id) WHERE revoked_at IS NULL` per ADR-003
- [ ] UNIQUE(organization_id, slug) on Role; system role slugs globally reserved
- [ ] UNIQUE(organization_id, slug) on Permission; system permission slugs globally reserved
- [ ] Hierarchy invariant: child role must share parent's primary_domain per SPEC-002 §4
- [ ] Seed migration: 11 roles (admin, practice_admin, system_admin, biller, receptionist, provider, therapist, supervisor, prescriber, client, guardian) with correct parent_role_id per SPEC-002 §3
- [ ] Biller and receptionist are standalone (parent_role_id = null) per SPEC-002 §3 inheritance model
- [ ] Seed migration: all system permissions per SPEC-002 §3, including the nine EntityType-slug permissions for system types (`provider.read`, `provider.write`, `provider.delete`, `client.read`, `client.write`, `client.delete`, `admin.read`, `admin.write`, `admin.delete`) so SPEC-001 §6's `{type_slug}.read/write/delete` contract is satisfied for system types without running TASK-019
- [ ] Seed migration: full role-permission grant matrix with correct conditions (own_clients, own_sessions, own_notes for provider roles; null for admin) per SPEC-002 §3/§6
- [ ] All seed roles/permissions have is_system_role/is_system_permission = true

## Files

- `backend/app/models/models.py` (Role, Permission, PersonRole, RolePermission models)
- `backend/app/schemas/identity.py` (RBAC schemas)
- `backend/tests/factories/identity.py` (Role, Permission factories)
- `backend/alembic/versions/` (model + seed migrations)

## Non-goals

- Permission resolution logic (TASK-015)
- Role/permission management API endpoints (TASK-016)
- PersonRole assignment API (TASK-017)
