# TASK-026: InsurancePayer & ClientInsurance Models & API

**Status:** Not started
**Spec sections:** SPEC-005 §2 (InsurancePayer, ClientInsurance), §4 (client bridge rule), §5 (insurance payer management, client insurance management)
**ADRs:** ADR-001, ADR-002, ADR-003 (partial unique index for one-active-priority per client/payer)
**Depends on:** TASK-004, TASK-011C, TASK-015

## Objective

Implement InsurancePayer (reference directory) and ClientInsurance (client-to-payer linkage) models and APIs. ClientInsurance endpoints follow EAV routing conventions (`/entities/{type_slug}/{id}/insurance`).

## Pre-existing artifacts (from TASK-002 scope expansion)

- `InsurancePayer` ORM model at `backend/app/models/models.py:523`; `ClientInsurance` at `:538`.
- `InsurancePriority` enum at `:87`.
- Tables `insurance_payers`, `client_insurances` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas, service, router, factory, partial unique index for one-active-priority per client/payer (ADR-003) — verify in migration; follow-up migration if missing; client-bridge validation, audit calls, tests.

## Acceptance Criteria

- [x] InsurancePayer model with all SPEC-005 §2 fields: id, organization_id, name, payer_id (nullable), phone, address, is_active, created_at, updated_at
- [x] ClientInsurance model with all SPEC-005 §2 fields: id, organization_id, client_instance_id, insurance_payer_id, member_id, group_number, plan_name, priority (InsurancePriority enum: primary/secondary), copay_cents, deductible_cents, deductible_met_cents, effective_date, termination_date, is_active, created_at, updated_at
- [ ] Unique constraint: no two active records of same priority with same payer for same client per SPEC-005 §2
- [ ] Money fields use Integer cents per SPEC-007 §4.4
- [ ] InsurancePayer CRUD: GET/POST/GET/{id}/PATCH per SPEC-005 §5 with insurance.read/write permissions
- [ ] ClientInsurance CRUD: GET/POST/PATCH/DELETE on `/entities/{type_slug}/{id}/insurance` per SPEC-005 §5
- [ ] List endpoints (GET `/api/v1/insurance-payers` and GET `/entities/{type_slug}/{id}/insurance`) use cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] type_slug must resolve to client; non-client type_slug rejected with 422 per SPEC-005 §5
- [ ] Client bridge rule: client_instance_id must reference client-type EntityInstance per SPEC-005 §4
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-005 §8: `test_duplicate_active_coverage_same_priority_returns_409`, `test_add_coverage_non_client_type_returns_422`

## Files

- `backend/app/models/models.py` (InsurancePayer, ClientInsurance models)
- `backend/app/schemas/billing.py` (insurance schemas)
- `backend/app/services/billing_service.py` (insurance service methods)
- `backend/app/routers/billing.py` (insurance endpoints)
- `backend/tests/factories/billing.py` (insurance factories)
- `backend/tests/test_billing/test_insurance.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Payment-to-payer linkage (TASK-028)
