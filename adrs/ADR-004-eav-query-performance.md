# ADR-004 — EAV query performance: JSONB aggregation at query time

**Date:** 2026-04-19
**Author:** claude-code
**Status:** Accepted

## Context

The EAV pattern (EntityInstance → AttributeValue → EntityAttribute) requires a three-table join for every filtered or listed query. A "list all providers with their fields" call joins EntityInstance to N AttributeValue rows, each joined to EntityAttribute for the field name and type. This is inherently expensive compared to `SELECT * FROM providers`.

The question: what strategy keeps list views fast enough without sacrificing EAV flexibility?

## Options considered

### A: Materialized views

Pre-compute the EAV join into a flat view refreshed on write or periodically.

- (+) Read performance matches a concrete table.
- (-) Refresh logic adds write-path complexity (triggers or async jobs).
- (-) Stale data between refreshes unless refresh is synchronous (which slows writes).
- (-) One materialized view per EntityType, or a single wide view with NULLs.

### B: Denormalized search columns

Add indexed VARCHAR columns to EntityInstance for commonly queried fields (e.g., `_search_license_number`).

- (+) Fast filtered queries on known fields.
- (-) Defeats EAV flexibility — must know which fields to denormalize ahead of time.
- (-) Custom practice-defined fields can't be denormalized without migrations.

### C: JSONB aggregation at query time

Use a SQL subquery to aggregate each instance's AttributeValues into a JSONB object inline.

- (+) No extra tables, views, or refresh logic.
- (+) Works for all EntityTypes including custom ones with zero configuration.
- (+) PostgreSQL JSONB operators allow filtering on aggregated values.
- (-) Slower than pre-computed approaches at high row counts.
- (-) Cannot index into the aggregated JSONB (it's computed per query).

## Decision

**Option C — JSONB aggregation at query time** for MVP.

The canonical query pattern:

```sql
SELECT ei.id, ei.organization_id, ei.entity_type_id, ei.is_active,
       ei.created_at, ei.updated_at,
       COALESCE(
         jsonb_object_agg(ea.name, av.value) FILTER (WHERE ea.name IS NOT NULL),
         '{}'::jsonb
       ) AS attributes
FROM entity_instance ei
LEFT JOIN attribute_value av ON av.entity_instance_id = ei.id
LEFT JOIN entity_attribute ea ON ea.id = av.entity_attribute_id
WHERE ei.organization_id = :org_id
  AND ei.entity_type_id = :type_id
  AND ei.deleted_at IS NULL
GROUP BY ei.id
ORDER BY ei.created_at DESC
LIMIT :limit;
```

For filtered queries (e.g., "providers where license_state = NJ"), add a `HAVING` clause or a filtered subquery on AttributeValue before aggregation.

### Why this is sufficient for MVP

- MVP serves small practices: tens of providers, hundreds of clients.
- At this scale, the three-table join with proper indexes (ADR-017's `entity_instance(organization_id, entity_type_id)` and `attribute_value(entity_instance_id)`) executes in single-digit milliseconds.
- No operational overhead from materialized view refresh or denormalization sync.

### Upgrade path

If list views degrade as data grows (10k+ instances per type), layer materialized views (Option A) on top without changing the API contract. The service layer switches from inline aggregation to reading from the materialized view. This is an additive change, not a rewrite.

## Consequences

- (+) Zero additional infrastructure or maintenance for MVP.
- (+) Custom EntityTypes work out of the box — no per-type configuration.
- (+) Clear upgrade path to materialized views if performance becomes an issue.
- (-) Filtered EAV queries (find by attribute value) are O(n) scans on the aggregated result. Acceptable at MVP scale, not at 100k+ rows.
- (-) Cannot create database indexes on dynamically aggregated JSONB. Filtered queries depend on AttributeValue indexes and pre-aggregation filtering.
