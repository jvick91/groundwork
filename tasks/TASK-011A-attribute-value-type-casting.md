# TASK-011A: AttributeValue Type Casting Engine

**Status:** Not started
**Parent:** TASK-011
**Spec sections:** SPEC-001 §2 (AttributeValue type casting rules)
**ADRs:** —
**Depends on:** TASK-010

## Objective

Implement the pure, in-process type casting and validation engine for all 7 AttributeValue field types. This is a standalone module consumed by the EntityInstance CRUD service (TASK-011C). Each field_type has a distinct storage format, Python type, and validation rules. For the `fk` field type, this task validates *shape* only (UUID v4 format); the existence / same-org / matching-type-slug check is deferred to TASK-011C because it requires the EntityInstance model — which this task does not have as a dependency.

## Acceptance Criteria

- [ ] Validator function per field_type, dispatched by EntityAttribute.field_type
- [ ] `text`: max 10,000 chars, empty string is not null
- [ ] `number`: valid Decimal, max 10 significant digits, max 4 decimal places, no NaN/Infinity/exponent
- [ ] `date`: ISO 8601 YYYY-MM-DD, real calendar date, no time component
- [ ] `bool`: exactly "true" or "false" (lowercase only); "True", "1", "yes" rejected with 422
- [ ] `enum`: exact case-sensitive match to EntityAttribute.options array; options must be non-empty
- [ ] `fk`: valid UUID v4 format only (this task). TASK-011C extends the `fk` validator with the existence/soft-delete/same-org/type-slug-match checks once the EntityInstance model exists
- [ ] `jsonb`: valid JSON, top-level must be object or array (no scalar), max 100KB serialized
- [ ] All failures return HTTP 422 with attribute name and reason per SPEC-001 §2
- [ ] Public API exposes a composable `validate_fk_existence(db, value, options, org_id)` hook that TASK-011C will wire into the fk validator — this keeps the casting module a pure unit that does not import any model
- [ ] Unit tests for each field_type's happy path and each rejection reason (no DB required)

## Files

- `backend/app/services/eav_type_casting.py` (type casting module — no model imports)
- `backend/tests/test_eav/test_type_casting.py`

## Non-goals

- EntityInstance CRUD endpoints (TASK-011C)
- fk existence / same-org / matching-type-slug check (TASK-011C, via the `validate_fk_existence` hook)
- JSONB aggregation query (TASK-011B)
