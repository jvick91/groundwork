# TASK-015: Permission Resolution, Caching, & Row-Level Filtering

**Status:** Not started
**Spec sections:** SPEC-002 §5 (authorization resolution model), §6 (row-level filtering), §4 (role union rule, hierarchy inheritance); SPEC-007 §3.3 (caching)
**ADRs:** ADR-009
**Depends on:** TASK-013, TASK-014

## Objective

Implement the four-step authorization resolution model from SPEC-002 §5, including role hierarchy traversal, permission union across multiple roles, TTL-based caching per SPEC-007 §3.3, and row-level filtering with conditions JSONB from SPEC-002 §6. This produces the effective permission set attached to each request.

## Acceptance Criteria

- [ ] Four-step resolution per SPEC-002 §5: identify person → load active PersonRoles → expand hierarchy → collect RolePermission grants
- [ ] Hierarchy walk follows parent_role_id chain to collect inherited permissions per SPEC-002 §4
- [ ] Multi-role union: person with multiple active roles gets union of all permissions per SPEC-002 §4
- [ ] Only active grants considered: revoked_at IS NULL on both PersonRole and RolePermission per SPEC-002 §4
- [ ] Permission cache: in-process TTL cache keyed by (person_id, organization_id) with 60-second TTL per SPEC-007 §3.3
- [ ] Cache is thread-safe, supports TTL expiration, max 10,000 entries per SPEC-007 §3.3
- [ ] Cache invalidated immediately when PersonRole, RolePermission, or Role records are modified in the same process per SPEC-007 §3.3
- [ ] Permission check utility: given a required permission slug, returns allow/deny against the effective set
- [ ] Row-level filtering: conditions JSONB evaluated as conjunctive filters per SPEC-002 §6
- [ ] Supported conditions: `scope: own_clients`, `scope: own_sessions`, `scope: own_notes` (filter by requesting provider instance), `null` (unrestricted) per SPEC-002 §6
- [ ] `scope: own_profile` is deferred post-MVP per SPEC-002 §6 and is not implemented by this task
- [ ] Test: null-scope grant (e.g., admin's `clients.read`) returns unrestricted rows within the org
- [ ] Denied requests return 403 with standard error response per SPEC-002 §5
- [ ] FastAPI dependency for permission-gated endpoints (e.g., `Depends(require_permission("sessions.write"))`)
- [ ] Tests from SPEC-002 §11: `test_person_with_two_roles_gets_union_permissions`, `test_child_role_inherits_parent_permissions`, `test_revoked_role_excluded_from_permission_resolution`, `test_revoked_grant_excluded_from_effective_permissions`
- [ ] Test: cache hit within TTL, cache miss after TTL
- [ ] Test: cache invalidation on role/grant modification

## Files

- `backend/app/services/auth_service.py` (permission resolution, hierarchy walk, caching)
- `backend/app/core/dependencies.py` (require_permission dependency)
- `backend/app/permissions.py` (permission checking utilities)
- `backend/tests/test_auth/test_permission_resolution.py`

## Non-goals

- Individual endpoint permission decoration (done per-domain task)
- Row-level filter implementations for specific domains (done in each domain's list endpoint task)
