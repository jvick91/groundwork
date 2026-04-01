# SPEC-005: Billing and Payments

**Status:** Draft
**Version:** 0.1.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Invoice generation, line item coding, payment recording, insurance coverage, and reference code tables.

---

## 1. Domain Overview

This domain manages the financial lifecycle of a session from billable encounter to payment settlement. Billing begins after a session reaches completed status. An invoice is generated, populated with line items carrying procedure and diagnosis codes, and then payments are recorded against it as money is received from clients or payers.

The domain also maintains two reference directories — CPTCode and ICDCode — that provide standardized procedure and diagnosis codes used on claims and invoices. These are platform-level reference tables, not tenant-specific.

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
| code | String | NOT NULL, UNIQUE | Standard five-character CPT code (for example 90837). |
| description | String | NOT NULL | Plain-language description of the procedure. |
| default_rate_cents | Integer | NULLABLE | Optional platform default rate in cents. Practices may override. |
| is_active | Boolean | NOT NULL, default true | Inactive codes cannot be used on new line items. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |

### ICDCode

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| code | String | NOT NULL, UNIQUE | Standard ICD-10 diagnosis code (for example F32.1). |
| description | String | NOT NULL | Plain-language description of the diagnosis. |
| is_active | Boolean | NOT NULL, default true | Inactive codes cannot be used on new line items. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |

### InsurancePayer

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
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
| session_id | UUID | FK -> Session, NOT NULL, UNIQUE | The session this invoice bills for. One invoice per session. |
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

**Unique constraint:** (session_id). Only one Invoice may exist per session.

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

- One invoice per session: An invoice may not be created for a session that already has one. The backend must enforce this regardless of whether an existing invoice is in void or soft-deleted state.
- Session completion prerequisite: An invoice can only be created for a session with status completed. Draft, in-progress, or cancelled sessions cannot be invoiced.
- Line item total consistency: After any line item is created, updated, or deleted, invoice.total_cents must be recomputed as the sum of all InvoiceLineItem.amount_cents on that invoice and saved atomically in the same transaction.
- Payment amount guard: A payment's amount_cents must be greater than zero. Zero or negative payment amounts must be rejected.
- Overpayment handling: A payment that would cause amount_paid_cents to exceed total_cents is not automatically rejected, as insurance adjustments may result in credit balances, but it must generate a warning in the audit log for biller review.
- Void reason required: When setting invoice status to void, void_reason must be provided. Requests without a reason are rejected.
- Locked invoice editing: Line items cannot be added, updated, or deleted on an invoice in paid or void status. Only draft and sent invoices allow line item modification.
- CPT and ICD code activity: Only active CPT and ICD codes (is_active = true) may be used when creating or updating line items.
- Client bridge rule: client_instance_id on Invoice must reference an EntityInstance of type client. Validated at write time.
- Provider bridge rule: provider_instance_id on Invoice must reference an EntityInstance of type provider. Validated at write time.
- Soft delete rule: Soft-deleted invoices must not appear in list endpoints.

---

## 5. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

### Reference code management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /cpt-codes | List active CPT codes (searchable) | billing.read |
| GET | /icd-codes | List active ICD-10 codes (searchable) | billing.read |

CPT and ICD codes are platform-managed reference data. Creation and deactivation of codes is a system-admin operation not exposed to practice tenants in MVP.

### Insurance payer management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /insurance-payers | List insurance payers (searchable) | billing.read |
| POST | /insurance-payers | Create a new payer record | billing.write |
| GET | /insurance-payers/{id} | Retrieve payer detail | billing.read |
| PATCH | /insurance-payers/{id} | Update payer information | billing.write |

### Client insurance management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entities/client/{id}/insurance | List coverage records for a client | billing.read |
| POST | /entities/client/{id}/insurance | Add a coverage record | billing.write |
| PATCH | /entities/client/{id}/insurance/{coverage_id} | Update a coverage record | billing.write |
| DELETE | /entities/client/{id}/insurance/{coverage_id} | Deactivate a coverage record | billing.write |

### Invoice management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices | List invoices (paginated, filterable by status, client, provider, date range) | billing.read |
| POST | /invoices | Create an invoice for a completed session | billing.write |
| GET | /invoices/{id} | Retrieve invoice with line items | billing.read |
| PATCH | /invoices/{id} | Update invoice metadata (notes, due date) | billing.write |
| DELETE | /invoices/{id} | Soft delete a draft invoice | billing.write |
| POST | /invoices/{id}/send | Transition draft to sent | billing.write |
| POST | /invoices/{id}/void | Void an invoice with required reason | billing.write |

### Invoice line item management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices/{id}/line-items | List line items for an invoice | billing.read |
| POST | /invoices/{id}/line-items | Add a line item | billing.write |
| PATCH | /invoices/{id}/line-items/{item_id} | Update a line item | billing.write |
| DELETE | /invoices/{id}/line-items/{item_id} | Remove a line item | billing.write |

### Payment management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /invoices/{id}/payments | List payments for an invoice | billing.read |
| POST | /invoices/{id}/payments | Record a payment against an invoice | payments.record |
| GET | /payments | List all payments (paginated, filterable by payer type, date range) | billing.read |

---

## 6. Implementation Constraints

- Atomic total recomputation: Any write to InvoiceLineItem must recompute and persist invoice.total_cents and balance_cents within the same database transaction. These values must never be computed on-the-fly at read time.
- Payment status automation: Recording a payment must trigger invoice status recalculation (partial or paid) inside the same transaction as the payment insert.
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

## 8. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full model definitions for all 7 tables. Invoice lifecycle, business rules, API surface, implementation constraints, and ADR mapping. |
