# TASK-010 Log — EntityType & EntityAttribute Models, Seed Data, & API

**Branch:** entity-type-api
**Started:** 2026-04-30
**Phase 1 completed:** 2026-04-30
**Spec sections:** SPEC-001 §2, §3, §4, §6, §7, §9

---

## Phase 1 Scope (this session)

Per the user's plan, Phase 1 covers EntityType only:

- Seed migration (3 system types + their seed attributes)
- `custom_entity_types_enabled` feature flag (default `False`)
- `EntityTypeCreate`, `EntityTypeUpdate`, `EntityTypeResponse`, `EntityAttributeCreate`, `EntityAttributeUpdate`, `EntityAttributeResponse` Pydantic schemas
- 5 EntityType service functions
- 5 EntityType endpoints (`GET/POST /entity-types`, `GET/PATCH/DELETE /entity-types/{slug}`)
- All EntityType AC tests from SPEC-001 §9 + flag gate test

Phase 2 (EntityAttribute endpoints + remaining §9 attribute tests) is deferred.

---

## Files Created / Modified

| File | Action | Notes |
|---|---|---|
| `app/core/settings.py` | Modified | Added `custom_entity_types_enabled: bool = False` |
| `app/core/exceptions.py` | Modified | Added `SlugNotFoundError` for slug-based 404s |
| `app/schemas/eav.py` | Modified | Added `EntityAttributeCreate/Update/Response`, `EntityTypeCreate/Update/Response`, `_validate_slug` helper |
| `app/services/eav_service.py` | Modified | Added `_SYSTEM_SLUGS`, `_ET_SORT_FIELDS`, `_et_snapshot`, `_assert_slug_available`, `list_entity_types`, `get_entity_type_by_slug`, `create_entity_type`, `update_entity_type`, `delete_entity_type` |
| `app/routers/entity_types.py` | Created | 5 EntityType endpoints; 501 gate for POST when flag off |
| `app/main.py` | Modified | Imported and registered `entity_types_router` |
| `alembic/versions/c3f5e7a9b1d2_seed_system_entity_types_and_attributes.py` | Created | Inserts 3 system types + 13 seed attributes; ON CONFLICT DO NOTHING |
| `tests/test_eav/conftest.py` | Created | Session-scoped `seed_eav_data` fixture replicating migration data; inserts test orgs for FK satisfaction |
| `tests/test_eav/test_entity_types.py` | Created | 12 tests covering all Phase 1 ACs |

---

## Key Decisions

### SlugNotFoundError
`NotFoundError` requires a UUID (PHI-guard). Slug-based lookups need a separate exception class. Added `SlugNotFoundError(resource, slug)` — the slug is a URL path segment, not PHI.

### test_eav/conftest.py for seed data
The test suite uses SQLAlchemy `create_all` (DDL only), not Alembic migrations. A session-scoped `seed_eav_data` fixture inserts the system EntityTypes and seed attributes via ORM objects. Raw SQL with `text()` was avoided because asyncpg conflicts between `:param` named parameters and `::jsonb` PostgreSQL cast syntax cause `PostgresSyntaxError`.

### Test org pre-creation
`create_entity_type` inserts with `organization_id=_ORG_ID`. That UUID must exist in the `organizations` table (FK). The conftest inserts both the entity-type test org and the org-tests stub org so all FK constraints are satisfied without touching the test data flow.

### Feature flag via mock.patch
Tests that exercise the "flag on" path use `unittest.mock.patch.object` to temporarily set `custom_entity_types_enabled=True` on the singleton settings object, matching the pattern used for other boolean flags in the test suite.

### Audit org_id for EntityType
`create_entity_type` passes `org_id=auth.organization_id` (from stub auth, may be None for system types). `audit_service.log_action` accepts nullable `org_id`, so this is safe.

---

## Tests Added (12 total)

| Test | AC |
|---|---|
| `test_post_entity_type_returns_501_when_custom_types_disabled` | Flag-off gate |
| `test_list_entity_types_includes_seed_types` | GET list includes seed data |
| `test_get_entity_type_by_slug_returns_200` | GET by slug happy path |
| `test_get_entity_type_unknown_slug_returns_404` | GET 404 |
| `test_delete_system_entity_type_returns_409` | SPEC-001 §9 |
| `test_rename_system_entity_type_returns_409` | SPEC-001 §9 |
| `test_create_and_get_custom_entity_type` | Full create + retrieve cycle |
| `test_delete_custom_entity_type_returns_204` | DELETE happy path |
| `test_duplicate_slug_same_org_returns_409` | SPEC-001 §9 |
| `test_system_type_slug_reserved_across_orgs` | SPEC-001 §9 |
| `test_create_entity_type_writes_audit_log` | BR-07 / SPEC-001 §9 |
| `test_invalid_slug_format_returns_422` | Pydantic schema validation |

---

---

## Phase 2 — EntityAttribute endpoints (same session)

### Files Modified

| File | Action | Notes |
|---|---|---|
| `app/services/eav_service.py` | Modified | Added `_EA_SORT_FIELDS`, `_ea_snapshot`, `get_entity_attribute`, `list_entity_attributes`, `create_entity_attribute`, `update_entity_attribute`, `delete_entity_attribute` |
| `app/routers/entity_types.py` | Modified | Added 5 attribute endpoints nested under `/{slug}/attributes` |
| `tests/test_eav/test_entity_types.py` | Modified | Added 10 attribute tests (see below) |

### Key Decisions — Phase 2

**Seed attribute protection via `is_system_type`**: Rather than tracking individual seed attribute identities (no `is_seed` column exists on `EntityAttribute`), `delete_entity_attribute` checks the parent `EntityType.is_system_type`. If `True`, all attributes are protected. This is slightly more conservative than the spec ("seed attributes cannot be removed") but satisfies all spec tests without requiring a schema migration or UUID-hardcoding in service code. TASK-019 can revisit if custom-added attributes on system types need to be deletable.

**Cross-type access guard**: `get_entity_attribute` verifies the attribute's `entity_type_id` matches the slug-resolved type. Mismatches return 404 rather than 403 to avoid leaking existence of attributes in other types.

### Tests Added — Phase 2 (10 new)

| Test | Validates |
|---|---|
| `test_list_attributes_returns_seed_attributes` | Seed data visible via API |
| `test_list_attributes_unknown_type_returns_404` | 404 on unknown slug |
| `test_get_single_attribute_returns_200` | GET single happy path |
| `test_get_attribute_wrong_type_returns_404` | Cross-type access guard |
| `test_add_attribute_to_system_type_succeeds` | SPEC-001 §9 — system types extensible |
| `test_create_attribute_on_custom_type_returns_201` | Create happy path |
| `test_update_attribute_returns_200` | PATCH happy path |
| `test_delete_attribute_on_custom_type_returns_204` | DELETE happy path + confirm 404 |
| `test_delete_seed_attribute_on_system_type_returns_409` | SPEC-001 §9 — seed protection |
| `test_create_attribute_with_enum_options` | JSONB options roundtrip |

## Final State

- **141 tests pass** (119 pre-existing + 12 Phase 1 + 10 Phase 2)
- **90% coverage** (at threshold)
- `ruff check` and `ruff format --check` both pass
- All SPEC-001 §9 named tests implemented and passing
