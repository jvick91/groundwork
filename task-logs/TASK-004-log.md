# TASK-004 Log — Cursor Pagination Utility

**Agent:** cursor
**Branch:** cursor-pagination
**Date completed:** 2026-03-26

## What Was Done

### `backend/app/schemas/schemas.py`
- Added `SortDir` StrEnum (`ASC = "asc"`, `DESC = "desc"`).
- Added `PaginationParams` Pydantic model: `limit` (1–100, default 25), `cursor` (nullable str), `sort` (default `"created_at"`), `sort_dir` (default `SortDir.DESC`). Designed as a FastAPI `Depends()` target.

### `backend/app/utils/pagination.py` — new file
- `encode_cursor(sort_value, record_id)` — serialises (sort_value, id) to URL-safe Base64 JSON. Handles `datetime`, `date`, `UUID`, and plain values.
- `decode_cursor(cursor)` — deserialises cursor; raises `BadRequestError` on any malformed input.
- `_coerce_cursor_value(raw, sort_col)` — converts the raw JSON string back to a typed Python value (datetime, date, or passthrough) by inspecting the SQLAlchemy column type.
- `paginate(session, stmt, *, params, sort_fields, id_col)` — applies cursor WHERE clause, `ORDER BY (sort_col, id)`, and `LIMIT limit+1` probe. Returns `(items, PaginationMeta)`. `sort_fields` dict serves as both the allow-list and the string→column mapping.
- Filter helpers: `apply_exact_filter`, `apply_in_filter`, `apply_date_range_filter`, `apply_text_search`.

### `backend/tests/test_cross_cutting/test_pagination.py` — new file
- 22 tests across three groups:
  - **Unit tests** — cursor encode/decode round-trips, malformed input, `PaginationParams` validation bounds.
  - **Integration tests** — `paginate()` correctness using real `Organization` rows: first page, `has_next`, no next on last page, multi-page traversal without duplicates, stability after insert, ascending sort, invalid sort field → 400.
  - **Filter helper smoke tests** — each helper tested for no-op on None/empty and clause-building on real values.

## Decisions Made

- **`sort_fields` dict as allow-list:** Rather than a separate `allow_list: set[str]`, the `sort_fields: dict[str, InstrumentedAttribute]` parameter serves as both allow-list and string→column mapping. Callers define it per endpoint, keeping domain knowledge out of the utility.
- **`previous_cursor` encodes the first item of the current page:** This enables backwards navigation — the caller can pass `previous_cursor` as the cursor on a reverse-sorted query. It is `None` on the first page.
- **`has_previous = cursor is not None`:** Simple and correct. There was a previous page iff a cursor was supplied.
- **`LIMIT limit+1` probe:** Standard keyset pagination technique — fetch one extra row to determine `has_next` without a separate COUNT query.
- **Type coercion via column inspection:** `_coerce_cursor_value` reads the SQLAlchemy column type so datetime/date comparisons work correctly without requiring callers to specify types.

## Deviations from Task

None. All acceptance criteria implemented.

## Open Items

None.
