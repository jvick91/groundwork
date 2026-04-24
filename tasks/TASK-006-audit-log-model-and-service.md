# TASK-006: AuditLog Model & Audit Service

**Status:** Complete
**Spec sections:** SPEC-006 §2 (AuditLog), §4 (BR-07), §5 (audit coverage matrix), §7
**ADRs:** ADR-002
**Depends on:** TASK-001, TASK-002

## Objective

Implement the AuditLog model and a centralized audit service that all domain services will call for BR-07 compliance. The audit service writes an immutable log row in the same transaction as every state change. It applies the PHI field exclusion list to `previous_state` and `next_state` snapshots before writing. AuditLog rows can never be updated or deleted.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `AuditLog` ORM model already exists at `backend/app/models/models.py:686` with all SPEC-006 §2 fields (organization_id, actor_person_id nullable, action, resource_type, resource_id, previous_state/next_state JSONB, ip_address, user_agent, occurred_at) and **no `updated_at`/`deleted_at`** — matches the immutable-row requirement.
- Table `audit_logs` is created by the initial migration (`a68701f39fed_initial_schema.py`).
- No DB-level revoke/trigger yet, no service, no endpoints, no tests.

## Acceptance Criteria

- [x] AuditLog model has all fields from SPEC-006 §2: id, organization_id, actor_person_id, action, resource_type, resource_id, previous_state (JSONB), next_state (JSONB), ip_address, user_agent, occurred_at
- [x] No `updated_at` or `deleted_at` columns on AuditLog — rows are immutable
- [x] Audit service provides `log_action()` — `app/services/audit_service.py`
- [x] `PHI_EXCLUDED_FIELDS` centralized in `audit_service.py`; `filter_phi()` applied automatically per BR-08
- [x] `AttributeValue.value` included in `PHI_EXCLUDED_FIELDS` per SPEC-001 §7
- [x] Audit writes are transactional — `log_action()` uses `db.add()` in the caller's session; no commit; verified by `test_audit_failure_rolls_back_business_operation`
- [x] DB-level immutability trigger installed via migration `b2e4f6a8c0d1`; verified by `test_update_audit_log_row_rejected` and `test_delete_audit_log_row_rejected`
- [x] `GET /api/v1/audit-log` and `GET /api/v1/audit-log/{id}` in `app/routers/compliance.py` with `audit.read` permission
- [x] List endpoint supports cursor pagination and filtering by `actor_person_id`, `resource_type`, `resource_id`, `date_from`/`date_to`
- [x] All 7 named tests implemented in `tests/test_compliance/test_audit_log.py`; `filter_phi()` unit tests added

## Files

- `backend/app/models/models.py` (AuditLog model)
- `backend/app/services/audit_service.py`
- `backend/app/routers/compliance.py` (audit-log endpoints)
- `backend/tests/test_compliance/test_audit_log.py`

## Non-goals

- Audit coverage for specific domains (tested in each domain's task)
- AuditLog write endpoints — entries are created only by internal service calls
