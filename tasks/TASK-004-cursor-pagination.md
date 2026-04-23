# TASK-004: Cursor Pagination Utility

**Status:** Partial
**Spec sections:** SPEC-007 §5, §6
**ADRs:** —
**Depends on:** TASK-001, TASK-003

## Objective

Implement the cursor-based pagination contract defined in SPEC-007 §5 as a reusable utility that all list endpoints will use. Includes the pagination response envelope, cursor encoding/decoding, sort field validation, and filter query parameter conventions from SPEC-007 §6.

## Acceptance Criteria

- [ ] Pagination request parameters: `limit` (default 25, max 100), `cursor` (opaque string), `sort` (indexed column), `sort_dir` (asc/desc)
- [x] Response envelope: `{data: [], pagination: {next_cursor, previous_cursor, has_next, has_previous, limit}}` — shipped as `PaginatedResponse` + `PaginationMeta` in `app/schemas/schemas.py`
- [ ] Cursor is Base64-encoded JSON with sort value and record ID per SPEC-007 §5
- [ ] Sort by non-indexed column returns 400 per SPEC-007 §6.2
- [ ] Filter conventions supported: exact match, multiple values (comma-separated OR), date range (`date_from`/`date_to`), FK reference, text search (`q`) per SPEC-007 §6.1
- [ ] Pagination produces stable results under concurrent inserts/deletes per SPEC-007 §5
- [ ] Tests verify cursor encode/decode round-trip, boundary conditions, and stability

**Done so far (in code):** response envelope schemas (`PaginationMeta`, `PaginatedResponse`) in `app/schemas/schemas.py`.

**Remaining:** request query-parameter model, Base64 cursor encode/decode, sort-field allow-list validation, filter-builder helpers, `app/utils/pagination.py` module, and all tests.

## Files

- `backend/app/schemas/schemas.py` (pagination request/response models)
- `backend/app/utils/pagination.py` (cursor encode/decode, query builder)
- `backend/tests/test_cross_cutting/test_pagination.py`

## Non-goals

- Domain-specific filter definitions (those live in domain tasks)
