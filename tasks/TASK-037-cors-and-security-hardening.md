# TASK-037: CORS & Security Hardening

**Status:** Not started
**Spec sections:** SPEC-007 §15 (all subsections)
**ADRs:** ADR-009
**Depends on:** TASK-001, TASK-006, TASK-007, TASK-014

## Dependency Note

SPEC-007 §15.5 requires API responses, error messages, logs, and audit snapshots to be free of PHI. The audit-snapshot filter ships in TASK-006 and the log filter ships in TASK-007, so those tasks are load-bearing dependencies for this task's §15.5 AC. 001 and 014 remain required for CORS wiring and for exercising the live middleware end-to-end.

## Objective

Configure CORS to allow only the frontend origin (no wildcard), verify SQL injection prevention via parameterized queries, and ensure input sanitization on free-text fields to prevent stored XSS. This task hardens the security posture per SPEC-007 §15.

## Acceptance Criteria

- [ ] CORS configured: development allows `http://localhost:3000`, production allows deployed frontend domain only per SPEC-007 §15.1
- [ ] Wildcard origins (`*`) never used per SPEC-007 §15.1
- [ ] SQL injection prevention: all database queries use SQLAlchemy ORM/Core with parameterized queries, no raw SQL with user input per SPEC-007 §15.4
- [ ] Input validation: all input validated by Pydantic schemas at schema layer, business rules at service layer per SPEC-007 §15.3
- [ ] Free-text fields (notes, descriptions, amendment_note, and all other user-supplied strings written to the DB) are passed through `html.escape(text, quote=True)` in the service layer before persistence per SPEC-007 §15.3. Test `test_security/test_xss_sanitization.py` posts a payload containing `<script>alert(1)</script>` and `"` and asserts the stored value (and the value returned by GET) reads `&lt;script&gt;alert(1)&lt;/script&gt;` and `&quot;` respectively.
- [ ] API responses never include PHI-excluded fields in error messages, logs, or audit snapshots per SPEC-007 §15.5
- [ ] Test: CORS headers present on responses from allowed origin
- [ ] Test: CORS rejects requests from disallowed origin

## Files

- `backend/app/main.py` (CORS middleware configuration)
- `backend/app/core/settings.py` (CORS origin settings)
- `backend/tests/test_cross_cutting/test_security.py`

## Non-goals

- Rate limiting (post-MVP per SPEC-007 §15.2)
- WAF or network-level security (infrastructure concern)
- S3 bucket CORS configuration — the bucket policy permitting browser-based presigned PUT/GET from the frontend origin is infrastructure (set via IaC / bucket policy) per ADR-005, not application code
