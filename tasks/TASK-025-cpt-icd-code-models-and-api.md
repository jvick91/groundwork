# TASK-025: CPTCode & ICDCode Models & API

**Status:** Not started
**Spec sections:** SPEC-005 §2 (CPTCode, ICDCode), §4 (code activity rule), §5 (reference code management)
**ADRs:** ADR-001, ADR-002, ADR-009
**Depends on:** TASK-004, TASK-009, TASK-015

## Objective

Implement the CPTCode and ICDCode reference tables and their management APIs. These are organization-scoped lookup tables used on invoice line items. DELETE deactivates (sets is_active=false) rather than soft-deleting, so historical line items retain valid references.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `CPTCode` ORM model at `backend/app/models/models.py:490`; `ICDCode` at `:507`.
- Tables `cpt_codes`, `icd_codes` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas, service, router, factory, search support, DELETE-deactivates semantics, audit calls, tests.

## Acceptance Criteria

- [x] CPTCode model with all SPEC-005 §2 fields: id, organization_id, code, description, default_rate_cents (nullable Integer), is_active, created_at
- [x] ICDCode model with all SPEC-005 §2 fields: id, organization_id, code, description, is_active, created_at
- [ ] UNIQUE(organization_id, code) on both tables per SPEC-005 §2
- [ ] `GET /api/v1/cpt-codes` list with search, `POST`, `PATCH /cpt-codes/{id}`, `DELETE /cpt-codes/{id}` (deactivates) per SPEC-005 §5
- [ ] `GET /api/v1/icd-codes` list with search, `POST`, `PATCH /icd-codes/{id}`, `DELETE /icd-codes/{id}` (deactivates) per SPEC-005 §5
- [ ] List endpoints (GET `/api/v1/cpt-codes` and GET `/api/v1/icd-codes`) use cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] Permissions: codes.read for GET, codes.write for POST/PATCH, codes.delete for DELETE per SPEC-005 §5
- [ ] DELETE /api/v1/cpt-codes/{id} sets is_active=false and does NOT set deleted_at — verified by `test_delete_cpt_code_deactivates_not_soft_deletes`
- [ ] Deactivated codes remain visible on historical line items
- [ ] Money values in cents (default_rate_cents) per SPEC-007 §4.4
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-005 §8: `test_duplicate_cpt_code_same_org_returns_409`, `test_duplicate_icd_code_same_org_returns_409`

## Files

- `backend/app/models/models.py` (CPTCode, ICDCode models)
- `backend/app/schemas/billing.py` (code schemas)
- `backend/app/services/billing_service.py` (code service methods)
- `backend/app/routers/billing.py` (code endpoints)
- `backend/tests/factories/billing.py` (code factories)
- `backend/tests/test_billing/test_reference_codes.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Invoice line items referencing codes (TASK-027)
