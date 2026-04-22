# TASK-007: Structured Logging & PHI Exclusion Filter

**Status:** Not started
**Spec sections:** SPEC-006 §4 (BR-08); SPEC-000 §6
**ADRs:** —
**Depends on:** TASK-001

## Objective

Configure structlog with JSON output and a PHI field exclusion filter at the serializer layer. The filter strips sensitive fields before any log record is emitted, ensuring application logs never contain PHI regardless of what domain code passes to the logger.

## Acceptance Criteria

- [ ] structlog configured with JSON output format
- [ ] PHI exclusion filter strips: clinical note content keys (subjective, objective, assessment, plan, data, intervention, response, behavior), diagnosis codes, date_of_birth, ClientConsent.notes, Document free-text, and AttributeValue.value
- [ ] Filter is applied at the serializer layer (not per-call) — no PHI can bypass the filter
- [ ] Filter is a single centralized list, not per-endpoint per SPEC-006 §4
- [ ] Test: `test_note_content_excluded_from_application_logs` (SPEC-004 §10)
- [ ] Test: `test_icd_codes_excluded_from_application_logs` (SPEC-005 §8)
- [ ] Log output includes request metadata: method, path, status code, duration

## Files

- `backend/app/core/logger.py`
- `backend/app/main.py` (middleware registration for request logging)
- `backend/tests/test_cross_cutting/test_phi_exclusion.py`

## Non-goals

- Audit log PHI filtering (that's in TASK-006's audit service)
