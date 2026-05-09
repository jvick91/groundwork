# TASK-011B: JSONB Aggregation Query Builder

**Status:** Not started
**Parent:** TASK-011
**Spec sections:** SPEC-001 §5 (canonical query patterns)
**ADRs:** ADR-004 (JSONB aggregation at query time), ADR-009
**Depends on:** TASK-011C

## Objective

Implement the canonical JSONB aggregation query pattern from ADR-004 as a reusable query builder, and swap the naive GET `/entities/{type_slug}` implementation (landed in TASK-011C) over to use it. This collapses the EntityInstance → AttributeValue → EntityAttribute three-table join into a single row with an `attributes` JSONB object per instance.

## Acceptance Criteria

- [ ] Query builder produces the canonical SQL from ADR-004: `jsonb_object_agg(ea.name, av.value) FILTER (WHERE ea.name IS NOT NULL)` with COALESCE to empty object
- [ ] Builder accepts org_id, entity_type_id, and optional cursor pagination params
- [ ] Soft-deleted instances excluded (`deleted_at IS NULL`)
- [ ] Result includes instance fields (id, org, type, is_active, timestamps) + aggregated `attributes` dict
- [ ] GET `/entities/{type_slug}` is switched from the naive query landed in TASK-011C to the aggregated builder; response shape is unchanged, so all TASK-011C tests continue to pass
- [ ] Test: aggregation returns correct attribute key-value pairs for a multi-attribute instance
- [ ] Test: instance with no attribute values returns empty attributes dict
- [ ] Test: soft-deleted instances excluded from results

## Files

- `backend/app/services/eav_queries.py` (JSONB aggregation query builder)
- `backend/app/services/eav_service.py` (swap list implementation)
- `backend/tests/test_eav/test_eav_queries.py`

## Non-goals

- Filtered EAV queries (find by attribute value) — deferred per ADR-004 upgrade path
- Materialized views
