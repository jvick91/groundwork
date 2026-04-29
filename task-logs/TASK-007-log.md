# TASK-007 Log — Structured Logging & PHI Exclusion Filter

**Agent:** claude-code
**Branch:** task-007-request-logging
**Date completed:** 2026-04-29

## What Was Done

The PHI exclusion filter and centralized field list shipped earlier (TASK-006 amendment 2026-04-23). This task closed the two remaining gaps:

1. **Request-logging middleware** — `app/middleware/request_logger.py` with `RequestLoggerMiddleware`, a pure-ASGI middleware that emits one structlog event per HTTP request with `method`, `path`, `status_code`, and `duration_ms`. Registered in `app/main.py` after `CORSMiddleware` so it wraps outermost and observes the client-visible status. The 5xx exception path is wrapped in try/except so a log line is still emitted (with `status_code=500`) before the exception is re-raised to FastAPI's handlers.
2. **Two named tests** — `tests/test_cross_cutting/test_phi_exclusion.py` covers `test_note_content_excluded_from_application_logs` (SPEC-004 §10) and `test_icd_codes_excluded_from_application_logs` (SPEC-005 §8), plus a third regression-guard test that asserts every name in `PHI_EXCLUDED_FIELDS` is stripped (catches drift between the centralized list and the filter implementation).
3. **Middleware tests** — `tests/test_cross_cutting/test_request_logging.py` exercises the 200 path (asserts the four required fields are present and correctly typed) and the 500 path (asserts an event is still emitted on unhandled exception). Uses `structlog.testing.capture_logs` rather than pytest's `caplog`, because structlog renders kwargs into the LogRecord message instead of attaching them as attributes.
4. **Readiness fixture fix** — `tests/conftest.py` now has a session-scoped autouse `initialize_database` fixture that calls `Database.initialize(settings.test_database_url)` before tests run, mirroring what the FastAPI lifespan does in production. The lifespan does not fire under `httpx.ASGITransport`, so `_check_database` in `app/routers/health.py` was previously seeing an uninitialized engine and reporting `"error"`. Three readiness tests that had been failing on `main` now pass.

Final state:
- `docker compose exec backend ruff check app/ tests/` — clean.
- `docker compose exec backend ruff format --check app/ tests/` — 43 files already formatted.
- `docker compose exec backend mypy app/` — Success, no issues in 24 source files.
- `docker compose exec backend pytest tests/ --no-cov` — 91 passed, 0 failed.

## Decisions Made

- **Pure ASGI middleware over `BaseHTTPMiddleware`.** `BaseHTTPMiddleware` interferes with streaming responses and swallows exceptions in ways that complicate the always-emit guarantee. The pure ASGI form is ~30 lines and avoids both pitfalls.
- **Logger added last in `create_app`.** Starlette wraps middleware in registration order with the *last* added being the *outermost*. Adding `RequestLoggerMiddleware` after CORS means it sees the client-visible status code (after CORS has run) rather than the inner-app status.
- **Did not log query strings.** `scope["path"]` only — query strings can carry PHI in poorly-designed clients (e.g. `?ssn=...`), and the PHI filter only inspects field names. Logging the path alone is the conservative default.
- **`structlog.testing.capture_logs` for middleware tests.** caplog is the obvious first choice but structlog's stdlib LoggerFactory renders kwargs into the message string rather than attaching them as record attributes, so caplog can't assert on individual fields. Documented in the test module docstring.
- **Third PHI test added beyond the spec's two.** `test_phi_filter_centralized_list_is_authoritative` is a regression guard that fails if a future edit adds a name to `PHI_EXCLUDED_FIELDS` but breaks the filter. Cheap to maintain, and mirrors the "single source of truth" intent of SPEC-006 §7.

## Deviations from Task

- **Task file `Files` section listed `app/middleware/` as the implementation home but the directory did not exist.** Created `backend/app/middleware/__init__.py` (empty) alongside `request_logger.py`. Impact: none; SPEC-007 §561 already lists `middleware/` in the expected layout.
- **Task description's "Remaining" line claimed the PHI list also needed expanding.** That work shipped under TASK-006 amendment 2026-04-23. The centralized list in `app/core/phi.py` already covers the full BR-08 set, so the AC bullet was simply ticked rather than re-implemented. Documented in the AC update.

## Open Items

- TASK-005 may now be effectively complete: `/health` returns `{"status": "ok", ...}`, `/health/ready` exists in `app/routers/health.py` with the DB probe, and all 9 health tests pass on this branch. Worth a separate review/flip in STATE.md.
- Request logger does not yet emit a `request_id` correlation ID — that's owned by TASK-014 (auth middleware) where request scoping is wired up. Not in scope here.
