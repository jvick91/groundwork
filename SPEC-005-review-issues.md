# SPEC-005 Review: Issues vs SPEC-000

## TLDR Issue List

1. ~~**Void invoice blocks rebilling forever**~~ **RESOLVED** — Partial unique index: `UNIQUE(session_id) WHERE status != 'void'`. Void and rebill allowed.

2. ~~**`payments.record` permission missing from SPEC-002 seeds**~~ **RESOLVED** — 9 granular billing permissions added to SPEC-002: invoices.read, invoices.create, invoices.write, invoices.void, payments.read, payments.record, insurance.read, insurance.write, codes.read.

3. ~~**`invoices.create` / `insurance.read` in SPEC-000 persona table don't exist**~~ **RESOLVED** — Granular permissions now exist in SPEC-002. SPEC-000 persona table updated to match.

4. ~~**Reference tables have no org_id**~~ **RESOLVED** — Added organization_id to CPTCode, ICDCode, and InsurancePayer. SPEC-000 universal org-scoping restored (exception removed). Unique constraints updated to be per-org.

5. ~~**`InvoiceLineItem` has no `deleted_at`**~~ **RESOLVED** — Added deleted_at to InvoiceLineItem. Carries PHI (ICD codes).

6. ~~**`Payment` has no void/reversal mechanism**~~ **RESOLVED** — Added status (posted/voided), voided_at, voided_by_person_id, void_reason to Payment. Added void API endpoint, recalculation rules, and immutability rule.

7. **Overpayment invoice status undefined** — NOT ADDRESSED (per user decision). Left for future clarification.

8. ~~**provider/client vs conductor/attendee naming mismatch**~~ **RESOLVED** — SPEC-003 renamed conductor_instance_id → provider_instance_id and attendee_instance_id → client_instance_id. All cross-spec references updated (SPEC-000, SPEC-001, SPEC-002).

9. ~~**Client insurance URL pattern inconsistent with EAV routing**~~ **RESOLVED** — Updated to `/entities/{type_slug}/{id}/insurance` per SPEC-001 conventions. Non-client type_slug rejected with 422.

10. ~~**No test table**~~ **RESOLVED** — Test table added to SPEC-005 §8 with 43 test cases.

11. ~~**Invoice lifecycle not reflected in SPEC-000**~~ **RESOLVED** — SPEC-000 table inventory updated with invoice lifecycle statuses and payment void capability.
