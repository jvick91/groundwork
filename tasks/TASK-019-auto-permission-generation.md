# TASK-019: Auto-Permission Generation on EntityType Creation

**Status:** Not started
**Spec sections:** SPEC-002 §7 (SPEC-001 integration contract — auto-generation trigger); SPEC-001 §6 (dynamic permissions), §9
**ADRs:** ADR-009
**Depends on:** TASK-010, TASK-013

## Objective

When a custom EntityType is created via `POST /entity-types`, automatically generate three Permission rows — `{slug}.read`, `{slug}.write`, `{slug}.delete` — so the new type immediately gains RBAC support. This is the integration contract between SPEC-001 and SPEC-002.

## Acceptance Criteria

- [ ] Creating a custom EntityType with slug "nutritionist" auto-generates permissions: `nutritionist.read`, `nutritionist.write`, `nutritionist.delete` per SPEC-002 §7
- [ ] Auto-generated permissions have `organization_id` set to the creating org, `is_system_permission = false` per SPEC-002 §7
- [ ] Permissions are immediately available for assignment via RolePermission
- [ ] Slug rename cascade (SPEC-001 §6) updates all downstream Permission.resource_slug and recomputes Permission.slug in the same transaction
- [ ] Deleting a custom EntityType removes or deactivates its auto-generated permissions
- [ ] System EntityTypes do not trigger auto-generation (they use seed permissions)
- [ ] This task flips `CUSTOM_ENTITY_TYPES_ENABLED` to `True` (the feature flag introduced by TASK-010). With auto-generation now live, `POST /entity-types` for custom types succeeds and the 501 path is retired
- [ ] Test: `test_post_entity_type_custom_succeeds_with_flag_on` exercises the flag-on path
- [ ] Tests from SPEC-001 §9: `test_create_custom_type_generates_three_permissions`
- [ ] Tests from SPEC-002 §11: `test_create_entity_type_generates_read_write_delete_permissions`

## Files

- `backend/app/services/eav_service.py` (auto-generation hook in EntityType create)
- `backend/app/services/identity_service.py` (permission creation helper)
- `backend/tests/test_eav/test_entity_types.py` (auto-permission tests)

## Non-goals

- Auto-granting generated permissions to any role (admin assigns manually)
- Custom permission actions beyond read/write/delete
