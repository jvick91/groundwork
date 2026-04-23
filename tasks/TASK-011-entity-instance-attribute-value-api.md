# TASK-011: EntityInstance & AttributeValue (Container)

**Status:** Container — not directly executable
**Subtasks:** TASK-011A (type casting engine), TASK-011C (models + migration + CRUD + full fk check), TASK-011B (JSONB aggregation + GET list optimization)
**Spec sections:** SPEC-001 §2, §4, §5, §6, §7
**ADRs:** ADR-001, ADR-002, ADR-004

## Purpose

This file is a container describing the EntityInstance/AttributeValue work as a single logical unit. It has no acceptance criteria of its own — all work is owned by the three subtasks below. It exists so a reviewer can see the rollup in one place.

## Subtask execution order

1. **TASK-011A** — AttributeValue type casting engine (pure in-process validation; fk field validates UUID format only — the existence/org/type check is deferred to TASK-011C where the model exists).
2. **TASK-011C** — EntityInstance + AttributeValue models, migration, CRUD API, bridge rule enforcement, full fk existence/org/type check. Uses a naive non-aggregated SQL query for GET list.
3. **TASK-011B** — JSONB aggregation query builder per ADR-004; refactors GET `/entities/{type_slug}` to use the aggregated query.

## Why the split

The previous version of this file duplicated every subtask's AC. It also left model ownership ambiguous, so 011A's fk existence check and 011B's aggregation query both referenced tables that no subtask had created. The new structure makes model ownership unambiguous (011C) and breaks the circular dep between 011B and 011C by deferring query optimization to after the CRUD endpoint ships with a naive implementation.
