# TASK-028: Invoice Lifecycle, Payment Recording, & Void

**Status:** Not started
**Spec sections:** SPEC-005 §2 (Payment), §3 (invoice status lifecycle), §4 (payment rules, void rules, overpayment handling, insurance payer required), §5 (invoice lifecycle endpoints, payment management)
**ADRs:** ADR-002, ADR-003, ADR-009
**Depends on:** TASK-006, TASK-026, TASK-027

## Objective

Implement invoice status transitions (send, void), payment recording and voiding, and the automatic invoice status recalculation triggered by payment events. Payments are immutable once posted — corrections require voiding and re-recording.

## Acceptance Criteria

- [ ] Payment model with all SPEC-005 §2 fields: id, organization_id, invoice_id, amount_cents, payment_method (PaymentMethod enum), payer_type (PayerType enum), insurance_payer_id (nullable), reference_number, payment_date, notes, recorded_by_person_id, status (PaymentStatus enum, default POSTED), voided_at, voided_by_person_id, void_reason, created_at
- [ ] `POST /api/v1/invoices/{id}/send` transitions draft→sent per SPEC-005 §3
- [ ] `POST /api/v1/invoices/{id}/void` voids with required reason per SPEC-005 §3/§4
- [ ] Void without reason returns 422 per SPEC-005 §4
- [ ] Void is terminal — transitions out of void return 409 per SPEC-005 §3
- [ ] `GET /api/v1/invoices/{id}/payments` lists payments per SPEC-005 §5
- [ ] `POST /api/v1/invoices/{id}/payments` records payment with `payments.record` permission per SPEC-005 §5
- [ ] `POST /api/v1/invoices/{id}/payments/{payment_id}/void` voids payment with `payments.record` per SPEC-005 §5
- [ ] `GET /api/v1/payments` cross-invoice listing with pagination per SPEC-005 §5
- [ ] Payment amount_cents must be > 0; zero/negative rejected per SPEC-005 §4
- [ ] Insurance payer required: payer_type="insurance" requires non-null insurance_payer_id; payer_type="client"/"other" requires null per SPEC-005 §4
- [ ] Automatic status recalculation: amount_paid_cents==total_cents→PAID, 0<amount_paid_cents<total_cents→PARTIAL per SPEC-005 §3
- [ ] Overpayment: amount_paid_cents > total_cents generates audit warning, not rejected per SPEC-005 §4
- [ ] Payment void recalculation: recomputes amount_paid_cents from posted payments only, recalculates invoice status per SPEC-005 §4
- [ ] Voiding payment on paid invoice may transition back to partial or sent per SPEC-005 §4
- [ ] Payment void reason required per SPEC-005 §4
- [ ] Posted payments are immutable — PATCH returns 409 per SPEC-005 §4
- [ ] All operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-005 §8: `test_send_draft_transitions_to_sent`, `test_void_invoice_requires_reason`, `test_void_invoice_without_reason_returns_422`, `test_transition_out_of_void_returns_409`, `test_record_payment_zero_amount_returns_422`, `test_record_payment_negative_amount_returns_422`, `test_record_payment_updates_invoice_amount_paid`, `test_payment_completing_balance_transitions_to_paid`, `test_partial_payment_transitions_to_partial`, `test_overpayment_generates_audit_warning`, `test_void_payment_requires_reason`, `test_void_payment_recalculates_invoice_totals`, `test_void_payment_on_paid_invoice_transitions_to_partial`, `test_patch_posted_payment_returns_409`, `test_insurance_payment_without_payer_id_returns_422`, `test_payment_record_writes_audit_log`, `test_payment_void_writes_audit_log`, `test_invoice_void_writes_audit_log`

## Files

- `backend/app/models/models.py` (Payment model)
- `backend/app/schemas/billing.py` (payment schemas)
- `backend/app/services/billing_service.py` (payment, void, recalculation logic)
- `backend/app/routers/billing.py` (payment/lifecycle endpoints)
- `backend/tests/factories/billing.py` (Payment factory)
- `backend/tests/test_billing/test_payments.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Automated payment processing (post-MVP per SPEC-005 §6)
- Multi-currency support
