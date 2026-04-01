# SPEC-005: Billing and Payments

**Status:** Draft
**Version:** 0.3.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Invoice generation, line item coding, payment recording, insurance coverage, and reference code tables.

---

## 1. Domain Overview

This domain manages the financial lifecycle of a session from billable encounter to payment settlement. Billing begins after a session reaches completed status. An invoice is generated, populated with line items carrying procedure and diagnosis codes, and then payments are recorded against it as money is received from clients or payers.

The domain also maintains two reference directories — CPTCode and ICDCode — that provide standardized procedure and diagnosis codes used on claims and invoices. These tables are scoped to an organization like all other records in the platform.

Insurance coverage is tracked per client via ClientInsurance, which links a client's EntityInstance to an InsurancePayer with policy details. This information is available at invoice time to determine the expected payer split.

### Tables owned

- InsurancePayer: Reference directory of insurance companies.
- ClientInsurance: Links a client instance to an insurance payer with policy and coverage details.
- Invoice: The bill generated from a completed session.
- InvoiceLineItem: An individual charge on an invoice with procedure and diagnosis codes.
- Payment: A money receipt recorded against an invoice.
- CPTCode: Procedure code reference table.
- ICDCode: Diagnosis code reference table.

---

## 2. Data Model Detail

### CPTCode

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes code to a tenant. |
| code | String | NOT NULL | Standard five-character CPT code (for example 90837). |
| description | String | NOT NULL | Plain-language description of the procedure. |
| default_rate_cents | Integer | NULLABLE | Optional default rate in cents for this organization. |
| is_active | Boolean | NOT NULL, default true | Inactive codes cannot be used on new line items. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |

**Unique constraint:** (organization_id, code). A CPT code is unique within an organization. Multiple organizations may have the same code with different rates.

### ICDCode

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes code to a tenant. |
| code | String | NOT NULL | Standard ICD-10 diagnosis code (for example F32.1). |
| description | String | NOT NULL | Plain-language description of the diagnosis. |
| is_active | Boolean | NOT NULL, default true | Inactive codes cannot be used on new line items. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |

**Unique constraint:** (organization_id, code). An ICD code is unique within an organization.

### InsurancePayer

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes payer to a tenant. |
| name | String | NOT NULL | Legal name of the insurance company. |
| payer_id | String | NULLABLE | Electronic payer ID used for claim submission. |
| phone | String | NULLABLE | Payer contact phone for verification. |
| address | Text | NULLABLE | Payer mailing address. |
| is_active | Boolean | NOT NULL, default true | Inactive payers cannot be assigned to new ClientInsurance records. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

### ClientInsurance

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes record to a tenant. |
| client_instance_id | UUID | FK -> EntityInstance, NOT NULL | Client profile instance holding the coverage. Must reference an EntityInstance of type client. |
| insurance_payer_id | UUID | FK -> InsurancePayer, NOT NULL | The payer providing coverage. |
| member_id | String | NOT NULL | Client's insurance member ID. |
| group_number | String | NULLABLE | Group policy number, if applicable. |
| plan_name | String | NULLABLE | Name of the specific plan (for example Gold PPO). |
| priority | Enum | NOT NULL | One of: primary, secondary. Determines claim submission order. |
| copay_cents | Integer | NULLABLE | Fixed copay amount in cents, if known. |
| deductible_cents | Integer | NULLABLE | Annual deductible in cents, if known. |
| deductible_met_cents | Integer | NULLABLE | Amount of deductible already met in cents. |
| effective_date | Date | NULLABLE | Date coverage begins. |
| termination_date | Date | NULLABLE | Date coverage ends. Null means open-ended. |
| is_active | Boolean | NOT NULL, default true | Soft toggle for inactive coverage periods. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

**Unique constraint:** (organization_id, client_instance_id, insurance_payer_id, priority, is_active-is-true active set). A client cannot have two active records of the same priority with the same payer.

### Invoice

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes invoice to a tenant. |
| session_id | UUID | FK -> Session, NOT NULL | The session this invoice bills for. One active invoice per session (partial unique index excludes voided invoices). |
| client_instance_id | UUID | FK -> EntityInstance, NOT NULL | Client being billed. Must reference an EntityInstance of type client. |
| provider_instance_id | UUID | FK -> EntityInstance, NOT NULL | Provider who delivered the service. Must reference an EntityInstance of type provider. |
| status | Enum | NOT NULL, default draft | One of: draft, sent, partial, paid, void. |
| issued_date | Date | NULLABLE | Date the invoice was formally sent to the client or payer. |
| due_date | Date | NULLABLE | Payment due date. |
| total_cents | Integer | NOT NULL, default 0 | Sum of all line item amounts in cents. Computed and stored at write time. |
| amount_paid_cents | Integer | NOT NULL, default 0 | Running total of payments received in cents. |
| balance_cents | Integer | NOT NULL, default 0 | Remaining unpaid balance in cents. Computed as total_cents minus amount_paid_cents. |
| notes | Text | NULLABLE | Internal billing notes. Not visible to client. |
| voided_at | Timestamp | NULLABLE | When the invoice was voided. |
| voided_by_person_id | UUID | FK -> Person, NULLABLE | Which person voided the invoice. |
| void_reason | Text | NULLABLE | Required when status is void. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

**Unique constraint:** Partial unique index: `UNIQUE (session_id) WHERE status != 'void'`. Only one non-voided Invoice may exist per session. Voided invoices do not block creation of a replacement. A session may accumulate multiple voided invoices over time.

### InvoiceLineItem

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes line item to a tenant. |
| invoice_id | UUID | FK -> Invoice, NOT NULL | The invoice this line item belongs to. |
| cpt_code_id | UUID | FK -> CPTCode, NOT NULL | Procedure code for this service. |
| icd_code_id | UUID | FK -> ICDCode, NULLABLE | Primary diagnosis code. |
| description | String | NULLABLE | Override description if different from CPT default. |
| unit_rate_cents | Integer | NOT NULL | Rate per unit in cents. |
| units | Integer | NOT NULL, default 1 | Number of units billed. |
| amount_cents | Integer | NOT NULL | Total charge computed as unit_rate_cents multiplied by units. |
| service_date | Date | NOT NULL | Date the service was delivered. Defaults to the session date. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. Line items carry PHI (ICD codes). See BR-05 and ADR-006. |

### Payment

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes payment to a tenant. |
| invoice_id | UUID | FK -> Invoice, NOT NULL | The invoice this payment is applied to. |
| amount_cents | Integer | NOT NULL | Amount received in cents. Must be greater than zero. |
| payment_method | Enum | NOT NULL | One of: cash, check, card, ach, insurance, other. |
| payer_type | Enum | NOT NULL | One of: client, insurance, other. Identifies who sent the payment. |
| insurance_payer_id | UUID | FK -> InsurancePayer, NULLABLE | Set when payer_type is insurance. |
| reference_number | String | NULLABLE | Check number, transaction ID, or EOB reference. |
| payment_date | Date | NOT NULL | Date payment was received. |
| notes | Text | NULLABLE | Internal payment notes. |
| recorded_by_person_id | UUID | FK -> Person, NULLABLE | Person who recorded this payment. |
| status | Enum | NOT NULL, default posted | One of: posted, voided. |
| voided_at | Timestamp | NULLABLE | When the payment was voided. |
| voided_by_person_id | UUID | FK -> Person, NULLABLE | Person who voided this payment. |
| void_reason | Text | NULLABLE | Required when status is voided. Explanation for the reversal. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |

---

## 3. Invoice Status Lifecycle

| From | Allowed transitions | Trigger |
|---|---|---|
| draft | sent, void | Manual action by biller or practice admin |
| sent | partial, paid, void | Payment recorded against invoice |
| partial | paid, void | Additional payment recorded bringing balance to zero |
| paid | void | Manual void with reason (rare) |
| void | none (terminal) | — |

Status transitions to partial and paid are computed automatically when payments are recorded. When amount_paid_cents equals total_cents, status transitions to paid. When amount_paid_cents is greater than zero but less than total_cents, status is partial. The status field must not be manually set by callers for these computed transitions.

---

## 4. Business Rules

- One active invoice per session: A session may have at most one non-voided invoice. A new invoice can be created for a session only if all prior invoices for that session are in void status. The partial unique index on session_id (excluding voided rows) enforces this at the database level.
- Session completion prerequisite: An invoice can only be created for a session with status completed. Draft, in-progress, or cancelled sessions cannot be invoiced.
- Line item total consistency: After any line item is created, updated, or deleted, invoice.total_cents must be recomputed as the sum of all InvoiceLineItem.amount_cents on that invoice and saved atomically in the same transaction.
- Payment amount guard: A payment's amount_cents must be greater than zero. Zero or negative payment amounts must be rejected.
- Overpayment handling: A payment that would cause amount_paid_cents to exceed total_cents is not automatically rejected, as insurance adjustments may result in credit balances, but it must generate a warning in the audit log for biller review.
- Void reason required: When setting invoice status to void, void_reason must be provided. Requests without a reason are rejected.
- Locked invoice editing: Line items cannot be added, updated, or deleted on an invoice in paid or void status. Only draft and sent invoices allow line item modification.
- CPT and ICD code activity: Only active CPT and ICD codes (is_active = true) may be used when creating or updating line items.
- Client bridge rule: client_instance_id on Invoice must reference an EntityInstance of type client. Validated at write time.
- Provider bridge rule: provider_instance_id on Invoice must reference an EntityInstance of type provider. Validated at write time.
- Session-invoice consistency: Invoice's client_instance_id and provider_instance_id must match the linked Session's client_instance_id and provider_instance_id. The backend must validate this at invoice creation time. These values are derived from the session, not accepted as independent input.
- Soft delete rule: Soft-deleted invoices and soft-deleted line items must not appear in list endpoints.
- Payment void reason required: When voiding a payment, void_reason must be provided. Requests without a reason are rejected.
- Payment void recalculation: When a payment is voided, invoice.amount_paid_cents must be recomputed by summing only posted (non-voided) payments, and invoice status must be recalculated in the same transaction. A voided payment on a paid invoice may transition the invoice back to partial or sent.
- Payment immutability: A posted payment cannot be edited. To correct a payment, void it and record a new one.

---

## 5. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

### Reference code management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /cpt-codes | List active CPT codes (searchable) | codes.read |
| GET | /icd-codes | List active ICD-10 codes (searchable) | codes.read |

CPT and ICD codes are organization-scoped reference data. Practices manage their own code tables. All queries filter by organization_id.

### Insurance payer management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /insurance-payers | List insurance payers (searchable) | insurance.read |
| POST | /insurance-payers | Create a new payer record | insurance.write |
| GET | /insurance-payers/{id} | Retrieve payer detail | insurance.read |
| PATCH | /insurance-payers/{id} | Update payer information | insurance.write |

### Client insurance management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entities/{type_slug}/{id}/insurance | List coverage records for a client instance | insurance.read |
| POST | /entities/{type_slug}/{id}/insurance | Add a coverage record | insurance.write |
| PATCH | /entities/{type_slug}/{id}/insurance/{coverage_id} | Update a coverage record | insurance.write |
| DELETE | /entities/{type_slug}/{id}/insurance/{coverage_id} | Deactivate a coverage record | insurance.write |

Client insurance endpoints follow EAV routing conventions from SPEC-001. The `type_slug` must resolve to client; requests with a non-client type_slug are rejected with 422.

### Invoice management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices | List invoices (paginated, filterable by status, client, provider, date range) | invoices.read |
| POST | /invoices | Create an invoice for a completed session | invoices.create |
| GET | /invoices/{id} | Retrieve invoice with line items | invoices.read |
| PATCH | /invoices/{id} | Update invoice metadata (notes, due date) | invoices.write |
| DELETE | /invoices/{id} | Soft delete a draft invoice | invoices.write |
| POST | /invoices/{id}/send | Transition draft to sent | invoices.write |
| POST | /invoices/{id}/void | Void an invoice with required reason | invoices.void |

### Invoice line item management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices/{id}/line-items | List line items for an invoice | invoices.read |
| POST | /invoices/{id}/line-items | Add a line item | invoices.write |
| PATCH | /invoices/{id}/line-items/{item_id} | Update a line item | invoices.write |
| DELETE | /invoices/{id}/line-items/{item_id} | Remove a line item | invoices.write |

### Payment management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices/{id}/payments | List payments for an invoice | payments.read |
| POST | /invoices/{id}/payments | Record a payment against an invoice | payments.record |
| POST | /invoices/{id}/payments/{payment_id}/void | Void a payment with required reason | payments.record |
| GET | /payments | List all payments (paginated, filterable by payer type, status, date range) | payments.read |

---

## 6. Implementation Constraints

- Atomic total recomputation: Any write to InvoiceLineItem must recompute and persist invoice.total_cents and balance_cents within the same database transaction. These values must never be computed on-the-fly at read time.
- Payment status automation: Recording or voiding a payment must trigger invoice status recalculation (sent, partial, or paid) inside the same transaction as the payment insert or void. Only posted (non-voided) payments count toward amount_paid_cents.
- Audit requirements: All state-changing calls (POST, PATCH, DELETE, void, send) must write an AuditLog entry per BR-07.
- PHI considerations: Diagnosis codes (ICD) linked to a client are PHI. They must not appear in application logs per BR-08.
- Payment processor: MVP records payments manually. Automated payment processing is deferred to a later phase. See ADR-008 for the decision on payment processor integration.
- Currency: All monetary values are stored as integer cents in the currency of the organization's locale. No floating-point money values are permitted anywhere in the system.

---

## 7. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-001 | Core MVP data model | Establishes billing tables as part of the concrete layer and scopes them to the MVP. |
| ADR-008 | Payment processor integration | Decides whether automated payment collection is in scope and which processor is used. Blocks post-MVP payment automation. |
| ADR-006 | Soft delete strategy | Defines delete semantics for invoices. |
| ADR-011 | Multi-tenancy isolation | Requires all billing queries to filter by organization_id. |
| ADR-003 | Session FK semantics | Defines how session-to-provider and session-to-client linkage is resolved; used by invoice bridge rule validation. |

---

## 8. Test Table

Every business rule and constraint maps to at least one test case per SPEC-000 §5.

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| Invoice | `UNIQUE(session_id) WHERE status != 'void'` | `test_create_second_invoice_same_session_returns_409` | Integration | One active invoice per session |
| Invoice | `UNIQUE(session_id) WHERE status != 'void'` | `test_create_invoice_after_void_succeeds` | Integration | Void-and-rebill allowed |
| Invoice | `session_id` FK → Session | `test_create_invoice_on_non_completed_session_returns_422` | Integration | Session must be completed |
| Invoice | `session_id` FK → Session | `test_create_invoice_on_completed_session_succeeds` | Integration | Valid session status accepted |
| Invoice | `client_instance_id` FK → EntityInstance | `test_create_invoice_client_not_client_type_returns_422` | Integration | Client bridge rule |
| Invoice | `provider_instance_id` FK → EntityInstance | `test_create_invoice_provider_not_provider_type_returns_422` | Integration | Provider bridge rule |
| Invoice | `client_instance_id` + `provider_instance_id` | `test_create_invoice_mismatched_session_actors_returns_422` | Integration | Session-invoice consistency |
| Invoice | `total_cents` | `test_add_line_item_recomputes_total_cents` | Integration | Line item total consistency |
| Invoice | `total_cents` | `test_delete_line_item_recomputes_total_cents` | Integration | Line item total consistency |
| Invoice | `total_cents` + `balance_cents` | `test_update_line_item_recomputes_total_and_balance` | Integration | Atomic recomputation |
| Invoice | `status` lifecycle | `test_send_draft_transitions_to_sent` | Integration | draft → sent |
| Invoice | `status` lifecycle | `test_void_invoice_requires_reason` | Integration | Void reason required |
| Invoice | `status` lifecycle | `test_void_invoice_without_reason_returns_422` | Integration | Void reason required |
| Invoice | `status` lifecycle | `test_transition_out_of_void_returns_409` | Integration | Void is terminal |
| Invoice | `status` + line items | `test_add_line_item_to_paid_invoice_returns_409` | Integration | Locked invoice editing |
| Invoice | `status` + line items | `test_add_line_item_to_void_invoice_returns_409` | Integration | Locked invoice editing |
| Invoice | `status` + line items | `test_add_line_item_to_draft_invoice_succeeds` | Integration | Draft/sent allow edits |
| Invoice | `deleted_at` | `test_soft_delete_draft_invoice_succeeds` | Integration | Soft delete |
| Invoice | `deleted_at` | `test_soft_deleted_invoice_excluded_from_list` | Integration | BR-05 |
| Invoice | `organization_id` | `test_list_invoices_filters_by_org` | Integration | Multi-tenant isolation |
| InvoiceLineItem | `cpt_code_id` FK → CPTCode | `test_create_line_item_with_inactive_cpt_returns_422` | Integration | CPT code activity check |
| InvoiceLineItem | `icd_code_id` FK → ICDCode | `test_create_line_item_with_inactive_icd_returns_422` | Integration | ICD code activity check |
| InvoiceLineItem | `amount_cents` | `test_line_item_amount_equals_rate_times_units` | Unit | Computed field |
| InvoiceLineItem | `deleted_at` | `test_soft_deleted_line_item_excluded_from_list` | Integration | BR-05 |
| Payment | `amount_cents` | `test_record_payment_zero_amount_returns_422` | Integration | Payment amount guard |
| Payment | `amount_cents` | `test_record_payment_negative_amount_returns_422` | Integration | Payment amount guard |
| Payment | `amount_cents` → Invoice `amount_paid_cents` | `test_record_payment_updates_invoice_amount_paid` | Integration | Payment status automation |
| Payment | `amount_cents` → Invoice `status` | `test_payment_completing_balance_transitions_to_paid` | Integration | Auto-transition to paid |
| Payment | `amount_cents` → Invoice `status` | `test_partial_payment_transitions_to_partial` | Integration | Auto-transition to partial |
| Payment | `amount_cents` → Invoice `status` | `test_overpayment_generates_audit_warning` | Integration | Overpayment handling |
| Payment | `status` void | `test_void_payment_requires_reason` | Integration | Payment void reason required |
| Payment | `status` void | `test_void_payment_recalculates_invoice_totals` | Integration | Payment void recalculation |
| Payment | `status` void | `test_void_payment_on_paid_invoice_transitions_to_partial` | Integration | Invoice status recalculation on void |
| Payment | posted immutability | `test_patch_posted_payment_returns_409` | Integration | Payment immutability |
| Payment | `insurance_payer_id` | `test_insurance_payment_without_payer_id_returns_422` | Integration | Payer required when payer_type is insurance |
| ClientInsurance | `UNIQUE(org, client, payer, priority)` | `test_duplicate_active_coverage_same_priority_returns_409` | Integration | Unique constraint |
| ClientInsurance | `client_instance_id` FK → EntityInstance | `test_add_coverage_non_client_type_returns_422` | Integration | Client bridge rule |
| CPTCode | `UNIQUE(organization_id, code)` | `test_duplicate_cpt_code_same_org_returns_409` | Integration | Unique constraint |
| ICDCode | `UNIQUE(organization_id, code)` | `test_duplicate_icd_code_same_org_returns_409` | Integration | Unique constraint |
| All tables | all state changes | `test_invoice_create_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_payment_record_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_payment_void_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_invoice_void_writes_audit_log` | Integration | BR-07 |
| InvoiceLineItem | `icd_code_id` | `test_icd_codes_excluded_from_application_logs` | Unit | BR-08: PHI not in logs |

---

## 9. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full model definitions for all 7 tables. Invoice lifecycle, business rules, API surface, implementation constraints, and ADR mapping. |
| 0.2.0 | Changed one-invoice-per-session from absolute UNIQUE to partial unique index excluding voided invoices. Billers can now void and rebill a session. Replaced coarse billing.read/billing.write with granular permissions: invoices.read, invoices.create, invoices.write, invoices.void, payments.read, payments.record, insurance.read, insurance.write, codes.read. All API endpoints updated to use granular permissions. |
| 0.3.0 | Added organization_id to CPTCode, ICDCode, InsurancePayer (all tables now org-scoped). Added deleted_at to InvoiceLineItem. Added Payment void mechanism (status, voided_at, voided_by_person_id, void_reason) with recalculation rules. Added session-invoice consistency rule. Updated client insurance URLs to EAV routing convention. Added test table with 43 test cases. Renamed conductor/attendee to provider/client across SPEC-003 for naming consistency. |
