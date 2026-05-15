# TASK-011C: EntityInstance & AttributeValue Models, Migration, CRUD API, & Bridge Rules

**Status:** Shipped
**Parent:** TASK-011
**Spec sections:** SPEC-001 §2 (EntityInstance, AttributeValue), §4 (soft delete, multi-tenancy, bridge rule, required field enforcement), §6 (EntityInstance management), §7 (audit PHI filtering)
**ADRs:** ADR-001, ADR-002, ADR-009
**Depends on:** TASK-004, TASK-011A, TASK-008A

## Objective

Own the EntityInstance and AttributeValue models, their Alembic migration, and the CRUD endpoints. Consume TASK-011A's type casting engine and extend its fk validator with the existence / same-org / matching-type-slug check now that the EntityInstance model exists. The GET list endpoint uses a naive (non-aggregated) SQL query in this task; TASK-011B lands the JSONB-aggregated replacement afterward.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `EntityInstance` ORM model at `backend/app/models/models.py:193` (with `SoftDeleteMixin`); `AttributeValue` at `:211` (uses `IdMixin` only — no timestamps, no soft delete — as SPEC-001 §2 requires).
- Tables `entity_instances`, `attribute_values` created by initial migration `a68701f39fed_initial_schema.py`, with the UNIQUE(entity_instance_id, entity_attribute_id) constraint.
- Remaining work: Pydantic schemas, service (including fk-existence wire-up to TASK-011A's casting engine), router, factory, naive GET list, required-field enforcement, bridge-rule validation, PHI-filtered audit snapshots, tests.

## Acceptance Criteria

- [x] EntityInstance model with all SPEC-001 §2 fields: id, entity_type_id, organization_id, person_id (nullable), is_active, created_at, updated_at, deleted_at
- [x] AttributeValue model with all SPEC-001 §2 fields: id, entity_instance_id, entity_attribute_id, value (Text, nullable)
- [x] UNIQUE(entity_instance_id, entity_attribute_id) on AttributeValue
- [x] AttributeValue intentionally omits created_at, updated_at, deleted_at per SPEC-001 §2 design note
- [x] Alembic migration creates both tables and the unique constraint
- [ ] `GET /api/v1/entities/{type_slug}` lists instances using a naive join-based query, paginated (TASK-011B replaces this with the aggregated query)
- [ ] List endpoint (GET /api/v1/entities/{type_slug}) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; the envelope is stable across the TASK-011B swap.
- [ ] `POST /api/v1/entities/{type_slug}` creates instance with attribute values, validated by TASK-011A's casting engine
- [ ] `GET /api/v1/entities/{type_slug}/{id}` retrieves instance with all attribute values
- [ ] `PATCH /api/v1/entities/{type_slug}/{id}` updates attribute values with type validation
- [ ] `DELETE /api/v1/entities/{type_slug}/{id}` soft deletes
- [ ] Permissions dynamically resolved: `{type_slug}.read`, `{type_slug}.write`, `{type_slug}.delete`
- [ ] Wires `validate_fk_existence` (from TASK-011A) into the fk validator so referenced EntityInstance must exist, must not be soft-deleted, must belong to the same organization, and must match the EntityType slug in options
- [ ] Required field enforcement: all is_required attributes must have non-null values
- [ ] Bridge rule validation: concrete tables verify instance type and org match
- [ ] Multi-tenancy: all queries filter by organization_id
- [ ] `GET /api/v1/entities/{type_slug}` excludes soft-deleted instances (where deleted_at IS NOT NULL)
- [ ] AuditLog PHI filtering: AttributeValue snapshots exclude `value` field per SPEC-001 §7
- [ ] All SPEC-001 §9 integration tests for EntityInstance and AttributeValue: `test_soft_deleted_instance_excluded_from_list`, `test_list_instances_filters_by_org`, `test_create_instance_cross_tenant_returns_403`, `test_session_with_non_provider_instance_returns_422`, `test_session_with_wrong_org_instance_returns_422`, `test_duplicate_value_same_instance_attribute_returns_409`, `test_create_instance_missing_required_field_returns_422`, `test_create_value_wrong_type_returns_422`, `test_create_enum_value_not_in_options_returns_422`, `test_update_instance_writes_audit_log`, `test_delete_instance_writes_audit_log`

## Files

- `backend/app/models/models.py` (EntityInstance, AttributeValue models)
- `backend/app/schemas/eav.py` (instance request/response schemas)
- `backend/app/services/eav_service.py` (instance CRUD + fk existence wire-up)
- `backend/app/routers/eav.py` (instance endpoints)
- `backend/tests/factories/eav.py` (EntityInstance + AttributeValue factories)
- `backend/tests/test_eav/test_entity_instances.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Type casting validation rules (TASK-011A)
- JSONB aggregation query (TASK-011B — runs after this task and replaces the naive GET list implementation)
