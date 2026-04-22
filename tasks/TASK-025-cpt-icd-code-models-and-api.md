# TASK-025: CPTCode & ICDCode Models & API

**Status:** Not started
**Spec sections:** SPEC-005 §2 (CPTCode, ICDCode), §4 (code activity rule), §5 (reference code management)
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-009, TASK-015

## Objective

Implement the CPTCode and ICDCode reference tables and their management APIs. These are organization-scoped lookup tables used on invoice line items. DELETE deactivates (sets is_active=false) rather than soft-deleting, so historical line items retain valid references.

## Acceptance Criteria

- [ ] CPTCode model with all SPEC-005 §2 fields: id, organization_id, code, description, default_rate_cents (nullable Integer), is_active, created_at
- [ ] ICDCode model with all SPEC-005 §2 fields: id, organization_id, code, description, is_active, created_at
- [ ] UNIQUE(organization_id, code) on both tables per SPEC-005 §2
- [ ] `GET /api/v1/cpt-codes` list with search, `POST`, `PATCH /cpt-codes/{id}`, `DELETE /cpt-codes/{id}` (deactivates) per SPEC-005 §5
- [ ] `GET /api/v1/icd-codes` list with search, `POST`, `PATCH /icd-codes/{id}`, `DELETE /icd-codes/{id}` (deactivates) per SPEC-005 §5
- [ ] Permissions: codes.read for GET, codes.write for POST/PATCH, codes.delete for DELETE per SPEC-005 §5
- [ ] DELETE sets is_active=false, does not soft-delete per SPEC-005 §5
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
