# TASK-011A: AttributeValue Type Casting Engine

**Status:** Not started
**Parent:** TASK-011
**Spec sections:** SPEC-001 §2 (AttributeValue type casting rules)
**ADRs:** —
**Depends on:** TASK-010

## Objective

Implement the type casting and validation engine for all 7 AttributeValue field types. This is a standalone module consumed by the EntityInstance CRUD service. Each field_type has distinct storage format, Python type, and validation rules.

## Acceptance Criteria

- [ ] Validator function per field_type, dispatched by EntityAttribute.field_type
- [ ] `text`: max 10,000 chars, empty string is not null
- [ ] `number`: valid Decimal, max 10 significant digits, max 4 decimal places, no NaN/Infinity/exponent
- [ ] `date`: ISO 8601 YYYY-MM-DD, real calendar date, no time component
- [ ] `bool`: exactly "true" or "false" (lowercase only); "True", "1", "yes" rejected with 422
- [ ] `enum`: exact case-sensitive match to EntityAttribute.options array; options must be non-empty
- [ ] `fk`: valid UUID v4, referenced EntityInstance must exist, not soft-deleted, same org, matching type slug from options
- [ ] `jsonb`: valid JSON, top-level must be object or array (no scalar), max 100KB serialized
- [ ] All failures return HTTP 422 with attribute name and reason per SPEC-001 §2
- [ ] Unit tests for each field_type's happy path and each rejection reason

## Files

- `backend/app/services/eav_type_casting.py` (type casting module)
- `backend/tests/test_eav/test_type_casting.py`

## Non-goals

- EntityInstance CRUD endpoints (TASK-011C)
- JSONB aggregation query (TASK-011B)
