# TASK-027: Invoice & InvoiceLineItem Models & CRUD API

**Status:** Not started
**Spec sections:** SPEC-005 §2 (Invoice, InvoiceLineItem), §4 (one active invoice per session, session prerequisite, line item total consistency, locked invoice editing, CPT/ICD activity, bridge rules, session-invoice consistency, soft delete restriction), §5 (invoice management, line item management, POST /invoices request body)
**ADRs:** ADR-002, ADR-003 (partial unique index)
**Depends on:** TASK-021, TASK-025, TASK-015

## Objective

Implement Invoice and InvoiceLineItem models with CRUD endpoints. Enforce one-active-invoice-per-session via partial unique index, session completion prerequisite, atomic line item total recomputation, locked invoice editing rules, and session-invoice actor consistency.

## Acceptance Criteria

- [ ] Invoice model with all SPEC-005 §2 fields: id, organization_id, session_id, client_instance_id, provider_instance_id, status (InvoiceStatus enum, default DRAFT), issued_date, due_date, total_cents (default 0), amount_paid_cents (default 0), balance_cents (default 0), notes, voided_at, voided_by_person_id, void_reason, created_at, updated_at, deleted_at
- [ ] Partial unique index: `UNIQUE(session_id) WHERE status != 'void'` per ADR-003, SPEC-005 §2
- [ ] InvoiceLineItem model with all SPEC-005 §2 fields: id, organization_id, invoice_id, cpt_code_id, icd_code_id (nullable), description, unit_rate_cents, units (default 1), amount_cents, service_date, created_at, updated_at, deleted_at
- [ ] `POST /api/v1/invoices` accepts session_id, notes, due_date — derives client/provider from session per SPEC-005 §5
- [ ] Session must be completed for invoice creation per SPEC-005 §4
- [ ] Session-invoice consistency: client_instance_id and provider_instance_id must match session per SPEC-005 §4
- [ ] Only one non-voided invoice per session; duplicate returns 409 per SPEC-005 §4
- [ ] `GET /api/v1/invoices` list with pagination, filterable by status, client, provider, date range per SPEC-005 §5
- [ ] `GET /api/v1/invoices/{id}` retrieves invoice with line items per SPEC-005 §5
- [ ] `PATCH /api/v1/invoices/{id}` updates metadata (notes, due_date) per SPEC-005 §5
- [ ] `DELETE /api/v1/invoices/{id}` soft-deletes draft invoices only; non-draft returns 409 `state_transition_denied` per SPEC-005 §4
- [ ] Line item CRUD: GET/POST/PATCH/DELETE on `/invoices/{id}/line-items` per SPEC-005 §5
- [ ] Line items only modifiable on draft/sent invoices; partial/paid/void return 409 `resource_locked` per SPEC-005 §4
- [ ] CPT/ICD activity check: only active codes allowed on new line items per SPEC-005 §4
- [ ] Atomic total recomputation: total_cents = sum(line_item.amount_cents), balance_cents = total_cents - amount_paid_cents, updated in same transaction per SPEC-005 §6
- [ ] amount_cents = unit_rate_cents * units per SPEC-005 §2
- [ ] All money in Integer cents per SPEC-007 §4.4
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-005 §8: `test_create_second_invoice_same_session_returns_409`, `test_create_invoice_after_void_succeeds`, `test_create_invoice_on_non_completed_session_returns_422`, `test_create_invoice_on_completed_session_succeeds`, `test_create_invoice_client_not_client_type_returns_422`, `test_create_invoice_provider_not_provider_type_returns_422`, `test_create_invoice_mismatched_session_actors_returns_422`, `test_add_line_item_recomputes_total_cents`, `test_delete_line_item_recomputes_total_cents`, `test_update_line_item_recomputes_total_and_balance`, `test_add_line_item_to_paid_invoice_returns_409`, `test_add_line_item_to_void_invoice_returns_409`, `test_add_line_item_to_draft_invoice_succeeds`, `test_soft_delete_draft_invoice_succeeds`, `test_soft_deleted_invoice_excluded_from_list`, `test_list_invoices_filters_by_org`, `test_create_line_item_with_inactive_cpt_returns_422`, `test_create_line_item_with_inactive_icd_returns_422`, `test_line_item_amount_equals_rate_times_units`, `test_soft_deleted_line_item_excluded_from_list`, `test_invoice_create_writes_audit_log`

## Files

- `backend/app/models/models.py` (Invoice, InvoiceLineItem models)
- `backend/app/schemas/billing.py` (invoice schemas)
- `backend/app/services/billing_service.py` (invoice/line item service)
- `backend/app/routers/billing.py` (invoice/line item endpoints)
- `backend/tests/factories/billing.py` (Invoice, LineItem factories)
- `backend/tests/test_billing/test_invoices.py`
- `backend/tests/test_billing/test_line_items.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Invoice status transitions beyond draft (TASK-028)
- Payment recording (TASK-028)
