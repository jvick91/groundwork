# TASK-003 Log — Error Response Contract & Exception Handling

**Agent:** cursor
**Branch:** error-response-contract
**Date completed:** 2026-03-26

## What Was Done

### `backend/app/core/exceptions.py` — complete rewrite
- Updated `GroundworkError` base: `detail: dict` → `details: list[dict[str, Any]]` to match SPEC-007 §7.1 array shape.
- Added 8 missing exception classes: `BadRequestError`, `UnauthorizedError`, `AccountInactiveError`, `OrgAccessDeniedError`, `StateTransitionDeniedError`, `ResourceLockedError`, `PrerequisiteNotMetError`, `RateLimitedError`, `InternalError`.
- Renamed `StatusTransitionError` → `StateTransitionDeniedError`; error code corrected from `status_transition_error` → `state_transition_denied` per SPEC-007 §7.3.
- Renamed `ValidationError` → `DomainValidationError` to prevent name collision with `pydantic.ValidationError` at the handler import site; error code remains `validation_error`.
- All exception `details` are now lists of dicts, matching the response envelope.

### `backend/app/schemas/schemas.py`
- Added `ValidationDetail` Pydantic model (`field`, `message`, `code`) for the structured shape described in SPEC-007 §7.2.
- Updated `ErrorResponse`: `detail: dict` → `details: list[dict[str, Any]] = []` to match spec §7.1.

### `backend/app/main.py`
- Updated `groundwork_error_handler` to serialize `exc.details` (list) instead of `exc.detail` (dict).
- Added `RequestValidationError` handler: extracts per-field `{field, message, code}` from Pydantic errors, strips the leading `body` path segment, returns 422 with standard envelope.
- Added catch-all `Exception` handler: logs the full traceback internally via stdlib `logging`, returns generic `internal_error` 500 with empty `details` — no internal information exposed.

### `backend/tests/test_cross_cutting/test_error_responses.py` — new file
- Module-scoped `error_app` fixture adds one trigger route per error code to a fresh app instance (no DB dependency needed).
- 18 tests cover all 15 error codes from SPEC-007 §7.3 plus the Pydantic 422 field-detail shape and the generic 500 no-leak assertion.

## Decisions Made

- **`DomainValidationError` naming:** Renamed from `ValidationError` to avoid shadowing `pydantic.ValidationError` in handler imports. The on-wire error code is still `validation_error` as required by the spec.
- **`details` as `list[dict]` not `list[ValidationDetail]`:** Domain errors (e.g., `NotFoundError`) include contextual metadata (`resource`, `resource_id`) that doesn't fit the `{field, message, code}` shape. Using `list[dict]` keeps the response field flexible while `ValidationDetail` is available as a typed helper for callers that need it.
- **`RequestValidationError` vs `pydantic.ValidationError`:** FastAPI wraps Pydantic errors in `RequestValidationError` before they reach exception handlers, so only `RequestValidationError` needs to be handled here.

## Deviations from Task

- **`detail` → `details` rename on `ErrorResponse`:** The pre-existing `ErrorResponse` used `detail: dict` but SPEC-007 §7.1 specifies `details: []` (array). Updated to match the spec; the task AC noted this as a required revisit.

## Open Items

None. All TASK-003 acceptance criteria are complete.
