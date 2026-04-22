# TASK-011B: JSONB Aggregation Query Builder

**Status:** Not started
**Parent:** TASK-011
**Spec sections:** SPEC-001 §5 (canonical query patterns)
**ADRs:** ADR-004 (JSONB aggregation at query time)
**Depends on:** TASK-010

## Objective

Implement the canonical JSONB aggregation query pattern from ADR-004 as a reusable query builder. This collapses the EntityInstance → AttributeValue → EntityAttribute three-table join into a single row with an `attributes` JSONB object per instance.

## Acceptance Criteria

- [ ] Query builder produces the canonical SQL from ADR-004: `jsonb_object_agg(ea.name, av.value) FILTER (WHERE ea.name IS NOT NULL)` with COALESCE to empty object
- [ ] Builder accepts org_id, entity_type_id, and optional cursor pagination params
- [ ] Soft-deleted instances excluded (`deleted_at IS NULL`)
- [ ] Result includes instance fields (id, org, type, is_active, timestamps) + aggregated `attributes` dict
- [ ] Test: aggregation returns correct attribute key-value pairs for a multi-attribute instance
- [ ] Test: instance with no attribute values returns empty attributes dict
- [ ] Test: soft-deleted instances excluded from results

## Files

- `backend/app/services/eav_queries.py` (JSONB aggregation query builder)
- `backend/tests/test_eav/test_eav_queries.py`

## Non-goals

- Filtered EAV queries (find by attribute value) — deferred per ADR-004 upgrade path
- Materialized views
