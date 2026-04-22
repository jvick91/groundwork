# TASK-011C: EntityInstance CRUD API & Bridge Rules

**Status:** Not started
**Parent:** TASK-011
**Spec sections:** SPEC-001 §4 (soft delete, multi-tenancy, bridge rule, required field enforcement), §6 (EntityInstance management), §7 (audit PHI filtering)
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-011A, TASK-011B, TASK-008A

## Objective

Implement the EntityInstance CRUD endpoints that consume the type casting engine (TASK-011A) and JSONB aggregation builder (TASK-011B). Enforce bridge rules, required fields, dynamic permissions, multi-tenancy isolation, and audit logging with PHI-safe AttributeValue snapshots.

## Acceptance Criteria

- [ ] `GET /api/v1/entities/{type_slug}` lists instances using JSONB aggregation, paginated
- [ ] `POST /api/v1/entities/{type_slug}` creates instance with attribute values, validated by type casting engine
- [ ] `GET /api/v1/entities/{type_slug}/{id}` retrieves instance with all attribute values
- [ ] `PATCH /api/v1/entities/{type_slug}/{id}` updates attribute values with type validation
- [ ] `DELETE /api/v1/entities/{type_slug}/{id}` soft deletes
- [ ] Permissions dynamically resolved: `{type_slug}.read`, `{type_slug}.write`, `{type_slug}.delete`
- [ ] Required field enforcement: all is_required attributes must have non-null values
- [ ] Bridge rule validation: concrete tables verify instance type and org match
- [ ] Multi-tenancy: all queries filter by organization_id
- [ ] Soft-deleted excluded from list
- [ ] AuditLog PHI filtering: AttributeValue snapshots exclude `value` field per SPEC-001 §7
- [ ] All SPEC-001 §9 integration tests for EntityInstance and AttributeValue

## Files

- `backend/app/services/eav_service.py` (instance CRUD using type casting + aggregation)
- `backend/app/schemas/eav.py` (instance request/response schemas)
- `backend/app/routers/eav.py` (instance endpoints)
- `backend/tests/test_eav/test_entity_instances.py`

## Non-goals

- Type casting validation rules (TASK-011A)
- JSONB aggregation query (TASK-011B)
