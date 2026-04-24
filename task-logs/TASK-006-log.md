# TASK-006 Log — AuditLog Model & Audit Service

**Agent:** cursor
**Branch:** audit-log-service
**Date completed:** 2026-03-26

## What Was Done

### `backend/app/services/audit_service.py` — new file
- `PHI_EXCLUDED_FIELDS: frozenset[str]` — centralized exclusion list per BR-08 and SPEC-001 §7. Covers: `content` (ClinicalNote JSONB), `date_of_birth`, `ssn`, `emergency_contact_name`, `emergency_contact_phone` (Person), `value` (AttributeValue), `notes` (ClientConsent), `description` (Document), `diagnosis_codes` (billing).
- `filter_phi(snapshot)` — strips PHI fields from a state dict before writing. Non-mutating. Returns None if input is None.
- `log_action(db, *, org_id, actor_id, action, resource_type, resource_id, ...)` — creates and `db.add()`s an AuditLog entry in the caller's session. Does not commit. Caller and audit write share the same transaction per SPEC-006 §7.

### `backend/alembic/versions/b2e4f6a8c0d1_audit_log_immutability_trigger.py` — new migration
- Creates `prevent_audit_log_mutation()` trigger function.
- Installs `audit_log_immutable_update` and `audit_log_immutable_delete` BEFORE triggers on `audit_logs`.
- `downgrade()` drops both triggers and the function.

### `backend/app/routers/compliance.py` — new file
- `GET /api/v1/audit-log` — paginated list with filters: `actor_person_id`, `resource_type`, `resource_id`, `date_from`, `date_to`. Uses `paginate()` utility. Requires `audit.read` permission.
- `GET /api/v1/audit-log/{id}` — single entry by UUID, raises `NotFoundError` on miss. Requires `audit.read` permission.
- Inline `_serialize()` helper; full Pydantic response schemas deferred to TASK-008A.

### `backend/app/main.py`
- Registered `compliance_router` at `/api/v1` prefix.

### `backend/tests/test_compliance/test_audit_log.py` — new file
- `install_immutability_trigger` — module-scoped autouse fixture that installs the trigger DDL against the test DB (mirrors the Alembic migration without requiring `upgrade head`).
- All 7 named tests from SPEC-006 §9: `test_state_change_writes_audit_entry`, `test_audit_failure_rolls_back_business_operation`, `test_audit_snapshot_excludes_phi_fields`, `test_update_audit_log_row_rejected`, `test_delete_audit_log_row_rejected`, `test_system_triggered_audit_has_null_actor`, `test_audit_log_filters_by_org`.
- `TestFilterPhi` — 5 unit tests for `filter_phi()` covering None, empty, all-PHI, non-mutation, and safe-field passthrough.

## Decisions Made

- **Trigger over REVOKE:** Used a `BEFORE` trigger rather than `REVOKE UPDATE, DELETE` because the trigger does not require knowledge of the application DB role name, works across all roles uniformly, and produces a clear, descriptive error message. The `downgrade()` path is also cleaner.
- **`filter_phi()` is conservative:** Fields are excluded by name regardless of the resource type the snapshot came from. This avoids any per-resource logic and ensures new resources with PHI-bearing field names are automatically protected without a code change.
- **`audit.read` permission on router with 501 stub:** `require_permission("audit.read")` is wired in now so the permission requirement is visible and enforced as soon as TASK-014/015 land. Endpoint tests override `get_auth_context` to inject a stub `AuthContext` with `audit.read` — this is consistent with how error handler tests inject stubs.
- **Trigger installed in test fixture, not via Alembic:** The test conftest uses `Base.metadata.create_all` which does not run migrations. A module-scoped autouse fixture runs the same DDL as the migration against the test DB. This avoids restructuring the conftest while still exercising the real trigger behavior.

## Deviations from Task

None. All acceptance criteria implemented.

## Open Items

- Full Pydantic response schemas for `/audit-log` endpoints deferred to TASK-008A per scope.
- Auth enforcement (501 → real RBAC check) is wired but inert until TASK-014.
