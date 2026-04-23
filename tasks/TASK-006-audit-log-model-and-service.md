# TASK-006: AuditLog Model & Audit Service

**Status:** Not started
**Spec sections:** SPEC-006 §2 (AuditLog), §4 (BR-07), §5 (audit coverage matrix), §7
**ADRs:** ADR-002
**Depends on:** TASK-001, TASK-002

## Objective

Implement the AuditLog model and a centralized audit service that all domain services will call for BR-07 compliance. The audit service writes an immutable log row in the same transaction as every state change. It applies the PHI field exclusion list to `previous_state` and `next_state` snapshots before writing. AuditLog rows can never be updated or deleted.

## Acceptance Criteria

- [ ] AuditLog model has all fields from SPEC-006 §2: id, organization_id, actor_person_id, action, resource_type, resource_id, previous_state (JSONB), next_state (JSONB), ip_address, user_agent, occurred_at
- [ ] No `updated_at` or `deleted_at` columns on AuditLog — rows are immutable
- [ ] Audit service provides a `log_action()` method accepting resource, action, actor, previous/next state
- [ ] PHI exclusion list is centralized and applied automatically before writing snapshots per SPEC-006 §4 BR-08
- [ ] AttributeValue audit snapshots exclude the `value` field entirely per SPEC-001 §7
- [ ] Audit writes are transactional — if the audit write fails, the business operation rolls back per SPEC-006 §7
- [ ] Database-level rejection of UPDATE and DELETE on `audit_log`: Alembic migration either (a) revokes UPDATE, DELETE on `audit_log` from the application DB role, or (b) installs a trigger that raises on UPDATE/DELETE. Verified by a test that issues a direct UPDATE/DELETE via SQLAlchemy Core and asserts the statement fails per SPEC-006 §2
- [ ] `GET /api/v1/audit-log` and `GET /api/v1/audit-log/{id}` endpoints with `audit.read` permission per SPEC-006 §6
- [ ] Audit log list endpoint supports pagination and filtering by actor, resource_type, resource_id, date range
- [ ] Tests: `test_state_change_writes_audit_entry`, `test_audit_failure_rolls_back_business_operation`, `test_audit_snapshot_excludes_phi_fields`, `test_update_audit_log_row_rejected` (application + DB), `test_delete_audit_log_row_rejected` (application + DB), `test_system_triggered_audit_has_null_actor`, `test_audit_log_filters_by_org`

## Files

- `backend/app/models/models.py` (AuditLog model)
- `backend/app/services/audit_service.py`
- `backend/app/routers/compliance.py` (audit-log endpoints)
- `backend/tests/test_compliance/test_audit_log.py`

## Non-goals

- Audit coverage for specific domains (tested in each domain's task)
- AuditLog write endpoints — entries are created only by internal service calls
