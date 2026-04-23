# TASK-017: Person Role Assignment API

**Status:** Not started
**Spec sections:** SPEC-002 §2 (PersonRole entity_instance_id rules), §8 (Person role assignment)
**ADRs:** ADR-002 (FK-only), ADR-003 (partial unique indexes for revocable PersonRole grants)
**Depends on:** TASK-012, TASK-013, TASK-015

## Objective

Implement the person role assignment API: listing role history, assigning roles with entity_instance_id validation, and revoking role assignments. Enforce all entity_instance_id rules from SPEC-002 §2 and the partial unique index from ADR-003.

## Acceptance Criteria

- [ ] `GET /api/v1/people/{id}/roles` lists active and historical role assignments with `roles.read` permission
- [ ] `POST /api/v1/people/{id}/roles` assigns a role with `roles.assign` permission
- [ ] `DELETE /api/v1/people/{id}/roles/{person_role_id}` revokes assignment (sets revoked_at) with `roles.assign` permission
- [ ] entity_instance_id required for roles where primary_domain maps to a person_subtype EntityType per SPEC-002 §2
- [ ] entity_instance_id must match expected EntityType for role's primary_domain per SPEC-002 §2
- [ ] entity_instance_id must belong to same organization_id as PersonRole per SPEC-002 §2
- [ ] entity_instance_id nullable for system_admin and other roles without EAV profile per SPEC-002 §2
- [ ] Role must belong to same org or be a system role per SPEC-002 §4
- [ ] Duplicate active assignment returns 409 per partial unique index
- [ ] Revoked rows are historical, do not conflict with new assignments
- [ ] All operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-002 §11: `test_duplicate_active_role_returns_409`, `test_assign_provider_role_without_entity_instance_returns_422`, `test_assign_provider_role_with_client_instance_returns_422`, `test_assign_provider_role_with_wrong_org_instance_returns_422`, `test_assign_system_admin_without_entity_instance_succeeds`, `test_revoke_role_sets_revoked_at`, `test_assign_role_writes_audit_log`, `test_revoke_role_writes_audit_log`
- [ ] Test: `test_assign_role_from_different_org_returns_422` — assigning a non-system role that belongs to a different org is rejected per SPEC-002 §4 (assignment integrity rule)

## Files

- `backend/app/services/identity_service.py` (assignment service methods)
- `backend/app/routers/identity.py` (assignment endpoints)
- `backend/tests/test_identity/test_role_assignment.py`

## Non-goals

- Permission resolution mechanics (TASK-015)
- Auth self-inspection (TASK-018)
