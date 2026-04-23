# TASK-010: EntityType & EntityAttribute Models, Seed Data, & API

**Status:** Not started
**Spec sections:** SPEC-001 §2 (EntityType, EntityAttribute), §3 (seed data), §4 (system type protection, required field enforcement), §6 (EntityType management, EntityAttribute management, slug change rules), §7
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-004, TASK-009

## Objective

Implement EntityType and EntityAttribute models with full CRUD APIs, seed data for the three system types (provider, client, admin) and their attributes, system type protection rules, and the atomic slug-change cascade for custom types.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `EntityType` ORM model at `backend/app/models/models.py:152`; `EntityAttribute` at `:174`.
- `FieldType` enum at `:45`.
- Tables `entity_types`, `entity_attributes` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: seed migration (3 system types + their attributes), Pydantic schemas, service, router, feature-flag (`CUSTOM_ENTITY_TYPES_ENABLED`), system-type protection rules, slug-change cascade, audit calls, tests.

## Acceptance Criteria

- [x] EntityType model with all SPEC-001 §2 fields: id, organization_id (nullable for system types), name, slug, is_system_type, is_person_subtype, created_at
- [x] EntityAttribute model with all SPEC-001 §2 fields: id, entity_type_id, name, display_name, field_type (FieldType enum), is_required, options (JSONB), display_order, created_at
- [ ] UNIQUE(organization_id, slug) on EntityType per SPEC-001 §7
- [ ] System type slugs (provider, client, admin) reserved globally across all orgs
- [ ] Seed migration creates 3 system EntityTypes with is_system_type=true, is_person_subtype=true
- [ ] Seed migration creates provider attributes (license_number, license_state, npi_number, specialty, taxonomy_code, dea_number), client attributes (intake_status enum, referral_source, emergency_contact_name, emergency_contact_phone, onboarded_at), admin attributes (department, title) per SPEC-001 §3
- [ ] EntityType CRUD: GET/POST/PATCH/DELETE on `/entity-types` and `/entity-types/{slug}` with entity_types.read/write/delete permissions per SPEC-001 §6
- [ ] List endpoints (GET `/api/v1/entity-types` and GET `/api/v1/entity-types/{slug}/attributes`) use cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `POST /entity-types` for *custom* (non-system) types is gated behind a `CUSTOM_ENTITY_TYPES_ENABLED` settings flag, default `False`. When the flag is off, `POST /entity-types` returns HTTP 501 `{"error": "not_implemented", "message": "Custom EntityType creation is not available until auto-permission generation (TASK-019) lands."}`. Rationale: SPEC-001 §6 / SPEC-002 §7 make auto-generated read/write/delete permissions part of the creation contract; shipping the endpoint without them would violate the spec. GET/PATCH/DELETE on *system* types and seed-managed state work normally regardless of the flag. TASK-019 flips the flag to `True` when auto-generation is live
- [ ] Test: `test_post_entity_type_returns_501_when_custom_types_disabled` covers the flag-off path
- [ ] EntityAttribute CRUD: GET/POST/PATCH/DELETE on `/entity-types/{slug}/attributes` and `/entity-types/{slug}/attributes/{id}` per SPEC-001 §6
- [ ] System types cannot be deleted or renamed (HTTP 409, `resource_locked`) per SPEC-001 §4
- [ ] Seed attributes on system types cannot be deleted (HTTP 409) but new attributes can be added per SPEC-001 §4
- [ ] Slug change on custom types updates EntityType.slug and writes AuditLog per SPEC-001 §6; the downstream Permission.resource_slug + Permission.slug cascade is owned by TASK-019 and runs in the same transaction
- [ ] Slug change on system types returns 409 per SPEC-001 §6
- [ ] Duplicate slug in same org returns 409 per SPEC-001 §6
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-001 §9: `test_delete_system_entity_type_returns_409`, `test_rename_system_entity_type_returns_409`, `test_duplicate_slug_same_org_returns_409`, `test_system_type_slug_reserved_across_orgs`, `test_delete_seed_attribute_on_system_type_returns_409`, `test_add_attribute_to_system_type_succeeds`, `test_create_entity_type_writes_audit_log`

## Files

- `backend/app/models/models.py` (EntityType, EntityAttribute models)
- `backend/app/schemas/eav.py` (EntityType, EntityAttribute schemas)
- `backend/app/services/eav_service.py` (type/attribute service methods)
- `backend/app/routers/eav.py` (type/attribute endpoints)
- `backend/tests/test_eav/test_entity_types.py`
- `backend/alembic/versions/` (model + seed migrations)

## Non-goals

- EntityInstance and AttributeValue (TASK-011)
- Auto-permission generation on custom type creation (TASK-019)
