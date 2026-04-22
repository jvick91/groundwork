# TASK-011: EntityInstance & AttributeValue Models & API

**Status:** Not started
**Subtasks:** TASK-011A (type casting), TASK-011B (JSONB aggregation), TASK-011C (CRUD API)
**Spec sections:** SPEC-001 §2 (EntityInstance, AttributeValue, type casting rules), §4 (soft delete, multi-tenancy, bridge rule, required field enforcement), §5 (canonical query patterns), §6 (EntityInstance management), §7
**ADRs:** ADR-001, ADR-002, ADR-004 (JSONB aggregation)
**Depends on:** TASK-010

## Objective

Implement EntityInstance and AttributeValue models with the full EAV query pipeline: JSONB aggregation at query time per ADR-004, type casting and validation for all 7 field types, required field enforcement, bridge rule validation, and CRUD API with dynamic permissions based on EntityType slug.

## Acceptance Criteria

- [ ] EntityInstance model with all SPEC-001 §2 fields: id, entity_type_id, organization_id, person_id (nullable), is_active, created_at, updated_at, deleted_at
- [ ] AttributeValue model with all SPEC-001 §2 fields: id, entity_instance_id, entity_attribute_id, value (Text, nullable)
- [ ] UNIQUE(entity_instance_id, entity_attribute_id) on AttributeValue
- [ ] AttributeValue intentionally omits created_at, updated_at, deleted_at per SPEC-001 §2 design note
- [ ] Type casting and validation for all 7 field types per SPEC-001 §2: text (max 10k chars), number (Decimal, max 10 sig digits/4 decimal), date (ISO 8601 YYYY-MM-DD), bool (exactly "true"/"false"), enum (case-sensitive options match), fk (valid UUID, existing non-deleted instance, same org, correct type), jsonb (valid JSON, object or array only, max 100KB)
- [ ] Invalid values return HTTP 422 with attribute name and reason per SPEC-001 §2
- [ ] Required field enforcement: all is_required attributes must have non-null values on create/update per SPEC-001 §4
- [ ] List endpoint uses JSONB aggregation query from ADR-004 §Decision
- [ ] EntityInstance CRUD: GET/POST/PATCH/DELETE on `/entities/{type_slug}` and `/entities/{type_slug}/{id}` per SPEC-001 §6
- [ ] Permissions are dynamically resolved: `{type_slug}.read`, `{type_slug}.write`, `{type_slug}.delete` per SPEC-001 §6
- [ ] Soft-deleted instances excluded from list endpoints per BR-05
- [ ] Multi-tenancy: all queries filter by organization_id per SPEC-001 §4
- [ ] Bridge rule validation: concrete tables verify instance type and org match per SPEC-001 §4
- [ ] AuditLog PHI filtering: AttributeValue snapshots exclude `value` field per SPEC-001 §7
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-001 §9: `test_soft_deleted_instance_excluded_from_list`, `test_list_instances_filters_by_org`, `test_create_instance_cross_tenant_returns_403`, `test_session_with_non_provider_instance_returns_422`, `test_session_with_wrong_org_instance_returns_422`, `test_duplicate_value_same_instance_attribute_returns_409`, `test_create_instance_missing_required_field_returns_422`, `test_create_value_wrong_type_returns_422`, `test_create_enum_value_not_in_options_returns_422`, `test_update_instance_writes_audit_log`, `test_delete_instance_writes_audit_log`

## Files

- `backend/app/models/models.py` (EntityInstance, AttributeValue models)
- `backend/app/schemas/eav.py` (instance/value schemas)
- `backend/app/services/eav_service.py` (instance service, type casting, JSONB query)
- `backend/app/routers/eav.py` (instance endpoints)
- `backend/tests/factories/eav.py` (instance factory)
- `backend/tests/test_eav/test_entity_instances.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Person-to-EntityInstance linkage workflow (TASK-012)
- Filtering by attribute value in list view (deferred per ADR-004 upgrade path)
