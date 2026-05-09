# TASK-016: Role & Permission Management API

**Status:** Not started
**Spec sections:** SPEC-002 §8 (Role and permission management)
**ADRs:** ADR-002 (FK-only), ADR-003 (partial unique indexes for revocable RolePermission grants), ADR-009
**Depends on:** TASK-013, TASK-015

## Objective

Implement the role and permission management API: CRUD for custom roles, permission listing, and grant/revoke of permissions on roles. System roles and permissions are protected from deletion.

## Acceptance Criteria

- [ ] `GET /api/v1/roles` lists system and org-scoped roles with `roles.read` permission
- [ ] `POST /api/v1/roles` creates org-scoped custom role with `roles.write` permission
- [ ] `PATCH /api/v1/roles/{id}` updates role metadata or parent with hierarchy invariant enforced per SPEC-002 §4
- [ ] `DELETE /api/v1/roles/{id}` deletes custom role (system roles blocked) with `roles.delete` permission
- [ ] `GET /api/v1/permissions` lists available permissions with `roles.read` permission
- [ ] `POST /api/v1/roles/{id}/permissions` grants permission to role with `roles.write` permission
- [ ] `DELETE /api/v1/roles/{id}/permissions/{permission_id}` revokes permission (sets revoked_at) with `roles.write` permission
- [ ] Hierarchy invariant enforced: child role primary_domain must match parent per SPEC-002 §4
- [ ] System role deletion returns 409 (`resource_locked`)
- [ ] Duplicate role slug in same org returns 409 (`conflict`)
- [ ] Duplicate active grant returns 409 per partial unique index
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-002 §11: `test_create_child_role_different_domain_returns_422`, `test_delete_system_role_returns_409`, `test_duplicate_role_slug_same_org_returns_409`, `test_duplicate_active_grant_returns_409`, `test_grant_permission_writes_audit_log`

## Files

- `backend/app/services/identity_service.py` (role/permission service methods)
- `backend/app/routers/identity.py` (role/permission endpoints)
- `backend/tests/test_identity/test_roles.py`

## Non-goals

- PersonRole assignment (TASK-017)
- Auth self-inspection (TASK-018)
