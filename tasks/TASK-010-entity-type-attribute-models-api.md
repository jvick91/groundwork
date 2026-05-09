# TASK-010: EntityType & EntityAttribute Models, Seed Data, & API

**Status:** Complete (refactored to ADR-009 on 2026-05-09 — see merge commit and TASK-008A)
**Spec sections:** SPEC-001 §2 (EntityType, EntityAttribute), §3 (seed data), §4 (system type protection, required field enforcement), §6 (EntityType management, EntityAttribute management, slug change rules), §7
**ADRs:** ADR-001, ADR-002, ADR-009
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
- [x] UNIQUE(organization_id, slug) on EntityType per SPEC-001 §7
- [x] System type slugs (provider, client, admin) reserved globally across all orgs
- [x] Seed migration creates 3 system EntityTypes with is_system_type=true, is_person_subtype=true
- [x] Seed migration creates provider attributes (license_number, license_state, npi_number, specialty, taxonomy_code, dea_number), client attributes (intake_status enum, referral_source, emergency_contact_name, emergency_contact_phone, onboarded_at), admin attributes (department, title) per SPEC-001 §3
- [x] EntityType CRUD: GET/POST/PATCH/DELETE on `/entity-types` and `/entity-types/{slug}` with entity_types.read/write/delete permissions per SPEC-001 §6
- [x] List endpoint (GET `/api/v1/entity-types`) uses cursor-based pagination per TASK-004 and SPEC-007 §6
- [x] `POST /entity-types` for *custom* (non-system) types is gated behind `custom_entity_types_enabled` settings flag, default `False`. Returns HTTP 501 when off.
- [x] Test: `test_post_entity_type_returns_501_when_custom_types_disabled` covers the flag-off path
- [x] EntityAttribute CRUD: GET/POST/PATCH/DELETE on `/entity-types/{slug}/attributes` and `/entity-types/{slug}/attributes/{id}` per SPEC-001 §6
- [x] System types cannot be deleted or renamed (HTTP 409, `resource_locked`) per SPEC-001 §4
- [x] Seed attributes on system types cannot be deleted (HTTP 409) but new attributes can be added per SPEC-001 §4
- [x] Slug change on custom types updates EntityType.slug and writes AuditLog per SPEC-001 §6
- [x] Slug change on system types returns 409 per SPEC-001 §6
- [x] Duplicate slug in same org returns 409 per SPEC-001 §6
- [x] All state-changing operations write AuditLog entries per BR-07
- [x] Tests from SPEC-001 §9: `test_delete_system_entity_type_returns_409`, `test_rename_system_entity_type_returns_409`, `test_duplicate_slug_same_org_returns_409`, `test_system_type_slug_reserved_across_orgs`, `test_create_entity_type_writes_audit_log`, `test_delete_seed_attribute_on_system_type_returns_409`, `test_add_attribute_to_system_type_succeeds`

## Files (post-architecture-reset, ADR-009)

- `backend/app/models/eav.py` — `EntityType` (with `SYSTEM_SLUGS` class attribute and `assert_mutable()` mutator), `EntityAttribute`
- `backend/app/schemas/eav.py` — `EntityTypeCreate/Update/Response`, `EntityAttributeCreate/Update/Response`
- `backend/app/repositories/entity_type_repository.py` — `EntityTypeRepository`
- `backend/app/repositories/entity_attribute_repository.py` — `EntityAttributeRepository`
- `backend/app/services/entity_type_service.py` — `EntityTypeService` class
- `backend/app/services/entity_attribute_service.py` — `EntityAttributeService` class
- `backend/app/routers/entity_types.py` — endpoints (depend on `get_entity_type_service` / `get_entity_attribute_service`)
- `backend/app/core/dependencies.py` — Depends factories for the repos and services
- `backend/tests/test_eav/test_entity_types.py`, `backend/tests/test_eav/conftest.py` (seed fixture)
- `backend/alembic/versions/c3f5e7a9b1d2_seed_system_entity_types_and_attributes.py`

## Non-goals

- EntityInstance and AttributeValue (TASK-011)
- Auto-permission generation on custom type creation (TASK-019)
