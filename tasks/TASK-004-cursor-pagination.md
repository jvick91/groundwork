# TASK-004: Cursor Pagination Utility

**Status:** Complete
**Spec sections:** SPEC-007 §5, §6
**ADRs:** —
**Depends on:** TASK-001, TASK-003

## Objective

Implement the cursor-based pagination contract defined in SPEC-007 §5 as a reusable utility that all list endpoints will use. Includes the pagination response envelope, cursor encoding/decoding, sort field validation, and filter query parameter conventions from SPEC-007 §6.

## Acceptance Criteria

- [x] Pagination request parameters: `limit` (default 25, max 100), `cursor` (opaque string), `sort` (indexed column), `sort_dir` (asc/desc) — `PaginationParams` + `SortDir` added to `app/schemas/schemas.py`
- [x] Response envelope: `{data: [], pagination: {next_cursor, previous_cursor, has_next, has_previous, limit}}` — `PaginatedResponse` + `PaginationMeta` in `app/schemas/schemas.py`
- [x] Cursor is Base64-encoded JSON with sort value and record ID per SPEC-007 §5 — `encode_cursor` / `decode_cursor` in `app/utils/pagination.py`
- [x] Sort by non-indexed column returns 400 per SPEC-007 §6.2 — `paginate()` validates `params.sort` against caller-provided `sort_fields` allow-list
- [x] Filter conventions supported: exact match, multiple values (comma-separated OR), date range (`date_from`/`date_to`), FK reference, text search (`q`) per SPEC-007 §6.1 — helpers in `app/utils/pagination.py`
- [x] Pagination produces stable results under concurrent inserts/deletes per SPEC-007 §5 — verified by `test_paginate_stable_after_insert`
- [x] Tests verify cursor encode/decode round-trip, boundary conditions, and stability — 22 tests in `test_pagination.py`

## Files

- `backend/app/schemas/schemas.py` (pagination request/response models)
- `backend/app/utils/pagination.py` (cursor encode/decode, query builder)
- `backend/tests/test_cross_cutting/test_pagination.py`

## Non-goals

- Domain-specific filter definitions (those live in domain tasks)
