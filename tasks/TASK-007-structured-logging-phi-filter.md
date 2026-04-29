# TASK-007: Structured Logging & PHI Exclusion Filter

**Status:** Complete
**Spec sections:** SPEC-006 §4 (BR-08); SPEC-000 §6
**ADRs:** —
**Depends on:** TASK-001

## Objective

Configure structlog with JSON output and a PHI field exclusion filter at the serializer layer. The filter strips sensitive fields before any log record is emitted, ensuring application logs never contain PHI regardless of what domain code passes to the logger.

## Acceptance Criteria

- [x] structlog configured with JSON output format — `setup_logging()` in `app/core/logger.py`
- [x] PHI exclusion filter strips: clinical note content keys (subjective, objective, assessment, plan, data, intervention, response, behavior), diagnosis codes, date_of_birth, ClientConsent.notes, Document free-text, and AttributeValue.value — full BR-08 list shipped via `PHI_EXCLUDED_FIELDS` in `app/core/phi.py`
- [x] Filter is applied at the serializer layer (not per-call) — no PHI can bypass the filter — `phi_filter` wired into the structlog processor chain
- [x] Filter is a single centralized list, not per-endpoint per SPEC-006 §4 — `PHI_FIELDS` frozenset in `app/core/logger.py`
- [x] Test: `test_note_content_excluded_from_application_logs` (SPEC-004 §10)
- [x] Test: `test_icd_codes_excluded_from_application_logs` (SPEC-005 §8)
- [x] Log output includes request metadata: method, path, status code, duration — `RequestLoggerMiddleware` in `app/middleware/request_logger.py`

**Done so far (in code):** structlog + JSON processor + `phi_filter` with 7 fields, wired via `setup_logging()`.

**Remaining:** expand `PHI_FIELDS` to the full BR-08 list (add `subjective, objective, assessment, plan, data, intervention, response, behavior, client_consent_notes, document_content, attribute_value`); add request-logging middleware (method, path, status, duration); add the two named tests.

## Files

- `backend/app/core/logger.py`
- `backend/app/main.py` (middleware registration for request logging)
- `backend/tests/test_cross_cutting/test_phi_exclusion.py`

## Non-goals

- Audit log PHI filtering (that's in TASK-006's audit service)
