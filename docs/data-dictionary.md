# Data Dictionary

Derived from SPEC-000 through SPEC-006 and the conventions in CLAUDE.md.

## Conventions applied uniformly

- All timestamps are stored and transmitted in UTC (`DateTime(timezone=True)`).
- All monetary values are stored as integer cents; column names carry the `_cents` suffix.
- Enums are `StrEnum` stored as VARCHAR (`native_enum=False`); the enum values listed in each table are the authoritative set.
- Models are FK-only (no ORM `relationship()`); every FK column below is declared directly on the model.
- Soft delete is applied to PHI-bearing or clinically significant tables via a nullable `deleted_at`. Reference and junction tables use `is_active` or `revoked_at` instead.
- "Audit-logged" means the table is listed in the SPEC-006 §5 audit coverage matrix; every create/update/delete/state-transition writes an AuditLog row in the same transaction.

Legend for the field tables:

- **Nullable**: Y means the column allows NULL.
- **Unit/Enum**: for numeric fields with a unit (cents, minutes, bytes), or the full enum value set.
- **PHI**: Y when the column's content is PHI per SPEC-006 BR-08 (or PHI-bearing in practice-defined cases).
- **Spec**: the spec section that defines the field.

---

## SPEC-001 — EAV data platform

### Organization — `organizations`

The root tenant record. Every other record in the platform scopes to an Organization.

Soft-deleted: No (uses `is_active` for suspension). Audit-logged: Ambiguous — see flagged items. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-001 §2 |
| name | String | N | max 255 chars | N | SPEC-001 §2 |
| npi_number | String | Y | API regex `^\d{10}$` (10 digits) | N | SPEC-001 §2 |
| tax_id | String | Y | API regex `^\d{2}-\d{7}$` (EIN) | N | SPEC-001 §2 |
| phone | String | Y | API regex `^[\d\s\-+().]{7,20}$` (loose shape) | N | SPEC-001 §2 |
| address_line1 | String(255) | Y | — | N | SPEC-001 §2, ADR-007 |
| address_line2 | String(255) | Y | — | N | SPEC-001 §2, ADR-007 |
| city | String(100) | Y | — | N | SPEC-001 §2, ADR-007 |
| state | String(2) | Y | API regex `^[A-Z]{2}$` (ISO-3166-2:US) | N | SPEC-001 §2, ADR-007 |
| postal_code | String(20) | Y | — | N | SPEC-001 §2, ADR-007 |
| country | String(2) | N | API regex `^[A-Z]{2}$` (ISO-3166-1 alpha-2), default `US` | N | SPEC-001 §2, ADR-007 |
| timezone | String | N | IANA tz, default `UTC` | N | SPEC-001 §2 |
| is_active | Boolean | N | default true | N | SPEC-001 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |

### EntityType — `entity_types`

Defines a kind of thing a practice can describe (e.g., provider, client, nutritionist). Seed types (provider, client, admin) have `is_system_type = true` and are protected.

Soft-deleted: No. Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-001 §2 |
| organization_id | UUID (FK → Organization) | Y | null for system types | N | SPEC-001 §2 |
| name | String | N | — | N | SPEC-001 §2 |
| slug | String | N | unique per org; system slugs globally reserved | N | SPEC-001 §2 |
| is_system_type | Boolean | N | default false | N | SPEC-001 §2 |
| is_person_subtype | Boolean | N | default false | N | SPEC-001 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |

### EntityAttribute — `entity_attributes`

Defines one field on an EntityType. Seed attributes on system types cannot be removed but new ones can be added.

Soft-deleted: No. Audit-logged: Yes. PHI: No (metadata only).

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-001 §2 |
| entity_type_id | UUID (FK → EntityType) | N | — | N | SPEC-001 §2 |
| name | String | N | machine name | N | SPEC-001 §2 |
| display_name | String | N | — | N | SPEC-001 §2 |
| field_type | Enum (StrEnum / VARCHAR) | N | `text`, `number`, `date`, `bool`, `enum`, `fk`, `jsonb` | N | SPEC-001 §2 |
| is_required | Boolean | N | default false | N | SPEC-001 §2 |
| options | JSONB | Y | enum choices or FK target slug | N | SPEC-001 §2 |
| display_order | Integer | N | default 0 | N | SPEC-001 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |

### EntityInstance — `entity_instances`

One actual record of an EntityType (e.g., a specific provider profile). Bridges to Person when the parent type has `is_person_subtype = true`.

Soft-deleted: Yes. Audit-logged: Yes. PHI: No on this row itself, but PHI lives on linked AttributeValues.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-001 §2 |
| entity_type_id | UUID (FK → EntityType) | N | — | N | SPEC-001 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-001 §2 |
| person_id | UUID (FK → Person) | Y | required when parent EntityType.is_person_subtype = true | N | SPEC-001 §2 |
| is_active | Boolean | N | default true | N | SPEC-001 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-001 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-001 §2 |

### AttributeValue — `attribute_values`

One field value on one instance. Stored as text and cast per the parent EntityAttribute's `field_type`. Unique on `(entity_instance_id, entity_attribute_id)`.

Soft-deleted: No (intentional — values are overwritten in place; lineage tracked via AuditLog on parent EntityInstance). Audit-logged: Yes, but the `value` content is stripped from `previous_state` / `next_state` snapshots. PHI: Potentially yes when the practice marks the parent attribute PHI.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-001 §2 |
| entity_instance_id | UUID (FK → EntityInstance) | N | — | N | SPEC-001 §2 |
| entity_attribute_id | UUID (FK → EntityAttribute) | N | — | N | SPEC-001 §2 |
| value | Text | Y | raw string; cast per `field_type` | Potentially | SPEC-001 §2 |

---

## SPEC-002 — Identity and RBAC

### Person — `persons`

Canonical identity record for a human, independent of any tenant. Tenant scoping is enforced through PersonRole.

Soft-deleted: Yes. Audit-logged: Yes. PHI: Yes via `date_of_birth`.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-002 §2 |
| auth_subject | String | Y | unique; null for non-authenticating personas | N | SPEC-002 §2 |
| first_name | String | N | — | N | SPEC-002 §2 |
| last_name | String | N | — | N | SPEC-002 §2 |
| email | String | N | unique | N | SPEC-002 §2 |
| phone | String | Y | — | N | SPEC-002 §2 |
| date_of_birth | Date | Y | — | **Y** | SPEC-002 §2 |
| is_active | Boolean | N | default true | N | SPEC-002 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-002 §2 |

### PersonRole — `person_roles`

Three-way binding: a Person holds a Role in an Organization, optionally scoped to an EntityInstance profile. Partial unique index `(organization_id, person_id, role_id, entity_instance_id) WHERE revoked_at IS NULL`.

Soft-deleted: No (uses `revoked_at`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-002 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-002 §2 |
| person_id | UUID (FK → Person) | N | — | N | SPEC-002 §2 |
| role_id | UUID (FK → Role) | N | — | N | SPEC-002 §2 |
| entity_instance_id | UUID (FK → EntityInstance) | Y | required when role's primary_domain is a person_subtype; nullable for system_admin | N | SPEC-002 §2 |
| assigned_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |
| assigned_by_person_id | UUID (FK → Person) | Y | null for system-seeded assignments | N | SPEC-002 §2 |
| revoked_at | Timestamp (UTC) | Y | null = active | N | SPEC-002 §2 |

### Role — `roles`

A named role in the RBAC model. System roles have globally reserved slugs. Custom roles are per-org.

Soft-deleted: No (see flagged items). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-002 §2 |
| organization_id | UUID (FK → Organization) | Y | null for system roles | N | SPEC-002 §2 |
| name | String | N | — | N | SPEC-002 §2 |
| slug | String | N | unique per org; system slugs globally reserved | N | SPEC-002 §2 |
| primary_domain | Enum (StrEnum / VARCHAR) | N | `admin`, `provider`, `client` | N | SPEC-002 §2 |
| parent_role_id | UUID (FK → Role) | Y | self-reference for hierarchy | N | SPEC-002 §2 |
| is_system_role | Boolean | N | default false | N | SPEC-002 §2 |
| description | Text | Y | — | N | SPEC-002 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |

### Permission — `permissions`

Single action right (e.g., `clients.read`). System permissions have globally reserved slugs. Custom permissions are auto-generated when a custom EntityType is created.

Soft-deleted: No. Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-002 §2 |
| organization_id | UUID (FK → Organization) | Y | null for system permissions | N | SPEC-002 §2 |
| resource_slug | String | N | — | N | SPEC-002 §2 |
| action | String | N | one of: `read`, `write`, `delete`, `sign`, `cosign`, `manage`, `assign`, `export` | N | SPEC-002 §2 |
| slug | String | N | `{resource_slug}.{action}`; unique per org | N | SPEC-002 §2 |
| description | Text | Y | — | N | SPEC-002 §2 |
| is_system_permission | Boolean | N | default false | N | SPEC-002 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |

### RolePermission — `role_permissions`

Grants a Permission to a Role, with optional row-level `conditions`. Partial unique index `(organization_id, role_id, permission_id) WHERE revoked_at IS NULL`.

Soft-deleted: No (uses `revoked_at`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-002 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-002 §2 |
| role_id | UUID (FK → Role) | N | — | N | SPEC-002 §2 |
| permission_id | UUID (FK → Permission) | N | — | N | SPEC-002 §2 |
| conditions | JSONB | Y | row-level filter: `{"scope": "own_clients"}`, `{"scope": "own_sessions"}`, `{"scope": "own_notes"}`, `{"scope": "own_profile"}`, or null | N | SPEC-002 §6 |
| granted_at | Timestamp (UTC) | N | — | N | SPEC-002 §2 |
| granted_by_person_id | UUID (FK → Person) | Y | null for system-seeded grants | N | SPEC-002 §2 |
| revoked_at | Timestamp (UTC) | Y | null = active | N | SPEC-002 §2 |

---

## SPEC-003 — Scheduling and sessions

### AppointmentType — `appointment_types`

Reusable template that defines session defaults. Deactivation via `is_active = false` instead of soft delete.

Soft-deleted: No. Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-003 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-003 §2 |
| name | String | N | — | N | SPEC-003 §2 |
| default_duration_minutes | Integer | N | minutes | N | SPEC-003 §2 |
| cpt_code_id | UUID (FK → CPTCode) | Y | — | N | SPEC-003 §2 |
| is_telehealth | Boolean | N | default false | N | SPEC-003 §2 |
| is_intake | Boolean | N | default false | N | SPEC-003 §2 |
| is_active | Boolean | N | default true | N | SPEC-003 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-003 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-003 §2 |

### Session — `sessions`

A scheduled or completed encounter between a provider EntityInstance and a client EntityInstance. `notes` here is internal scheduling text, explicitly not PHI.

Soft-deleted: Yes. Audit-logged: Yes. PHI: No on row metadata (but membership links to a client, so correlate with caution per BR-08).

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-003 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-003 §2 |
| appointment_type_id | UUID (FK → AppointmentType) | N | — | N | SPEC-003 §2 |
| provider_instance_id | UUID (FK → EntityInstance) | N | must be a `provider` type | N | SPEC-003 §2 |
| client_instance_id | UUID (FK → EntityInstance) | N | must be a `client` type | N | SPEC-003 §2 |
| start_time | Timestamp (UTC) | N | — | N | SPEC-003 §2 |
| end_time | Timestamp (UTC) | N | must be > start_time | N | SPEC-003 §2 |
| status | Enum (StrEnum / VARCHAR) | N | `scheduled`, `confirmed`, `in_progress`, `completed`, `cancelled`, `no_show`; default `scheduled` | N | SPEC-003 §2 |
| cancellation_reason | Text | Y | required when status is cancelled or no_show | N | SPEC-003 §2 |
| cancelled_at | Timestamp (UTC) | Y | — | N | SPEC-003 §2 |
| cancelled_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-003 §2 |
| location | String | Y | address or telehealth identifier | N | SPEC-003 §2 |
| notes | Text | Y | internal scheduling notes; not PHI, max 2,000 chars | N | SPEC-003 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-003 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-003 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-003 §2 |

---

## SPEC-004 — Clinical notes

### ClinicalNote — `clinical_notes`

SOAP / DAP / BIRP documentation of a Session. One note per Session, including soft-deleted notes.

Soft-deleted: Yes (drafts only; signed, cosigned, and amendment_pending notes are protected). Audit-logged: Yes. PHI: Yes (entire `content` JSONB and `amendment_note`).

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-004 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-004 §2 |
| session_id | UUID (FK → Session) | N | unique (one note per session) | N | SPEC-004 §2 |
| author_instance_id | UUID (FK → EntityInstance) | N | must be a `provider` type | N | SPEC-004 §2 |
| note_format | Enum (StrEnum / VARCHAR) | N | `soap`, `dap`, `birp`; immutable after create | N | SPEC-004 §2 |
| status | Enum (StrEnum / VARCHAR) | N | `draft`, `signed`, `cosigned`, `amendment_pending`; default `draft` | N | SPEC-004 §2 |
| content | JSONB | N | shape determined by `note_format` (see SPEC-004 §3) | **Y** | SPEC-004 §2 |
| signed_at | Timestamp (UTC) | Y | set once, immutable | N | SPEC-004 §2 |
| signed_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-004 §2 |
| cosigned_at | Timestamp (UTC) | Y | — | N | SPEC-004 §2 |
| cosigned_by_person_id | UUID (FK → Person) | Y | person must hold notes.cosign | N | SPEC-004 §2 |
| cosign_required | Boolean | N | default false | N | SPEC-004 §2 |
| amendment_note | Text | Y | append-only; server-formatted per SPEC-004 §7 | **Y** | SPEC-004 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-004 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-004 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker (drafts only) | N | SPEC-004 §2 |

---

## SPEC-005 — Billing and payments

### CPTCode — `cpt_codes`

Procedure code reference directory, per-org. Deactivated (not soft-deleted) to preserve historical line items.

Soft-deleted: No. Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| code | String | N | unique per org | N | SPEC-005 §2 |
| description | String | N | — | N | SPEC-005 §2 |
| default_rate_cents | Integer | Y | cents | N | SPEC-005 §2 |
| is_active | Boolean | N | default true | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |

### ICDCode — `icd_codes`

Diagnosis code reference directory, per-org. Deactivated rather than soft-deleted.

Soft-deleted: No. Audit-logged: Yes. PHI: No at this level (code + description only).

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| code | String | N | unique per org | N | SPEC-005 §2 |
| description | String | N | — | N | SPEC-005 §2 |
| is_active | Boolean | N | default true | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |

### InsurancePayer — `insurance_payers`

Reference directory of insurance companies, per-org.

Soft-deleted: No (uses `is_active`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| name | String | N | — | N | SPEC-005 §2 |
| payer_id | String | Y | electronic payer ID | N | SPEC-005 §2 |
| phone | String | Y | — | N | SPEC-005 §2 |
| address | Text | Y | — | N | SPEC-005 §2 |
| is_active | Boolean | N | default true | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |

### ClientInsurance — `client_insurances`

Links a client EntityInstance to an InsurancePayer with policy details.

Soft-deleted: No (uses `is_active`). Audit-logged: Yes. PHI: member_id, group_number, plan_name are PHI when correlated to a client.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| client_instance_id | UUID (FK → EntityInstance) | N | must be a `client` type | N | SPEC-005 §2 |
| insurance_payer_id | UUID (FK → InsurancePayer) | N | — | N | SPEC-005 §2 |
| member_id | String | N | — | Y (when correlated to client) | SPEC-005 §2 |
| group_number | String | Y | — | Y (when correlated to client) | SPEC-005 §2 |
| plan_name | String | Y | — | N | SPEC-005 §2 |
| priority | Enum (StrEnum / VARCHAR) | N | `primary`, `secondary` | N | SPEC-005 §2 |
| copay_cents | Integer | Y | cents | N | SPEC-005 §2 |
| deductible_cents | Integer | Y | cents | N | SPEC-005 §2 |
| deductible_met_cents | Integer | Y | cents | N | SPEC-005 §2 |
| effective_date | Date | Y | — | N | SPEC-005 §2 |
| termination_date | Date | Y | — | N | SPEC-005 §2 |
| is_active | Boolean | N | default true | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |

### Invoice — `invoices`

Bill generated from a completed Session. Partial unique index `(session_id) WHERE status != 'void'` — void-and-rebill is allowed.

Soft-deleted: Yes (drafts only; non-drafts must be voided). Audit-logged: Yes. PHI: No at this level.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| session_id | UUID (FK → Session) | N | one non-voided invoice per session | N | SPEC-005 §2 |
| client_instance_id | UUID (FK → EntityInstance) | N | must be a `client` type; derived from session | N | SPEC-005 §2 |
| provider_instance_id | UUID (FK → EntityInstance) | N | must be a `provider` type; derived from session | N | SPEC-005 §2 |
| status | Enum (StrEnum / VARCHAR) | N | `draft`, `sent`, `partial`, `paid`, `void`; default `draft` | N | SPEC-005 §2 |
| issued_date | Date | Y | — | N | SPEC-005 §2 |
| due_date | Date | Y | — | N | SPEC-005 §2 |
| total_cents | Integer | N | cents; recomputed atomically on line item writes | N | SPEC-005 §2 |
| amount_paid_cents | Integer | N | cents; sum of posted payments | N | SPEC-005 §2 |
| balance_cents | Integer | N | cents; `total_cents - amount_paid_cents` | N | SPEC-005 §2 |
| notes | Text | Y | internal billing notes | N | SPEC-005 §2 |
| voided_at | Timestamp (UTC) | Y | — | N | SPEC-005 §2 |
| voided_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-005 §2 |
| void_reason | Text | Y | required when status is void | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete (drafts only) | N | SPEC-005 §2 |

### InvoiceLineItem — `invoice_line_items`

Individual charge on an invoice, linked to a CPTCode and optionally an ICDCode.

Soft-deleted: Yes (line items carry PHI via ICD links). Audit-logged: Yes. PHI: Yes via `icd_code_id` when correlated to the invoice's client.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| invoice_id | UUID (FK → Invoice) | N | — | N | SPEC-005 §2 |
| cpt_code_id | UUID (FK → CPTCode) | N | must be active | N | SPEC-005 §2 |
| icd_code_id | UUID (FK → ICDCode) | Y | must be active when set | **Y** | SPEC-005 §2 |
| description | String | Y | override of CPT default | N | SPEC-005 §2 |
| unit_rate_cents | Integer | N | cents | N | SPEC-005 §2 |
| units | Integer | N | default 1 | N | SPEC-005 §2 |
| amount_cents | Integer | N | cents; `unit_rate_cents * units` | N | SPEC-005 §2 |
| service_date | Date | N | defaults to the session date | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-005 §2 |

### Payment — `payments`

Money received against an Invoice. Posted payments are immutable; corrections are handled by voiding and re-recording.

Soft-deleted: No (uses `status = 'voided'`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-005 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-005 §2 |
| invoice_id | UUID (FK → Invoice) | N | — | N | SPEC-005 §2 |
| amount_cents | Integer | N | cents; must be > 0 | N | SPEC-005 §2 |
| payment_method | Enum (StrEnum / VARCHAR) | N | `cash`, `check`, `card`, `ach`, `insurance`, `other` | N | SPEC-005 §2 |
| payer_type | Enum (StrEnum / VARCHAR) | N | `client`, `insurance`, `other` | N | SPEC-005 §2 |
| insurance_payer_id | UUID (FK → InsurancePayer) | Y | required when payer_type = insurance; must be null otherwise | N | SPEC-005 §2 |
| reference_number | String | Y | check number, txn ID, EOB reference | N | SPEC-005 §2 |
| payment_date | Date | N | — | N | SPEC-005 §2 |
| notes | Text | Y | internal notes | N | SPEC-005 §2 |
| recorded_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-005 §2 |
| status | Enum (StrEnum / VARCHAR) | N | `posted`, `voided`; default `posted` | N | SPEC-005 §2 |
| voided_at | Timestamp (UTC) | Y | — | N | SPEC-005 §2 |
| voided_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-005 §2 |
| void_reason | Text | Y | required when status is voided | N | SPEC-005 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-005 §2 |

---

## SPEC-006 — Documents, consent, and compliance

### AuditLog — `audit_logs`

Immutable record of every user-initiated state change. Append-only: the table has no update or delete path and no `updated_at` / `deleted_at`.

Soft-deleted: No (immutable). Audit-logged: No (it is the log). PHI: PHI fields are stripped from `previous_state` / `next_state` by the audit service per BR-08.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| actor_person_id | UUID (FK → Person) | Y | null for system-initiated events | N | SPEC-006 §2 |
| action | String | N | e.g., `created`, `updated`, `deleted`, `signed`, `voided`, `assigned` | N | SPEC-006 §2 |
| resource_type | String | N | affected table or domain object | N | SPEC-006 §2 |
| resource_id | UUID | N | affected record's PK | N | SPEC-006 §2 |
| previous_state | JSONB | Y | PHI-filtered snapshot before change | N (filtered) | SPEC-006 §2 |
| next_state | JSONB | Y | PHI-filtered snapshot after change | N (filtered) | SPEC-006 §2 |
| ip_address | String | Y | — | N | SPEC-006 §2 |
| user_agent | String | Y | — | N | SPEC-006 §2 |
| occurred_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |

### DocumentType — `document_types`

Org-scoped reference table defining valid document categories. System types are protected.

Soft-deleted: No (uses `is_active`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| name | String | N | — | N | SPEC-006 §2 |
| slug | String | N | unique per org; system slugs globally reserved | N | SPEC-006 §2 |
| linked_resource_table | String | Y | one of: `session`, `clinical_note`, `invoice`, `entity_instance`, `person`; null for unlinked types | N | SPEC-006 §2 |
| is_system_type | Boolean | N | default false | N | SPEC-006 §2 |
| is_active | Boolean | N | default true | N | SPEC-006 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |

### Document — `documents`

Metadata for a file stored in S3. `s3_key` is never serialized to API responses; access is via presigned URL only (15-min download, 60-min upload).

Soft-deleted: Yes (S3 object retained per ADR-005). Audit-logged: Yes. PHI: Document contents are PHI-bearing; metadata fields (`file_name`, `mime_type`) can indirectly disclose PHI.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| document_type_id | UUID (FK → DocumentType) | N | type must be active | N | SPEC-006 §2 |
| uploaded_by_person_id | UUID (FK → Person) | N | — | N | SPEC-006 §2 |
| linked_resource_id | UUID | Y | both-or-neither rule with DocumentType.linked_resource_table | N | SPEC-006 §2 |
| file_name | String | N | sanitized server-side; max 255 chars | Possibly | SPEC-006 §2 |
| mime_type | String | N | allowlist: `application/pdf`, `image/jpeg`, `image/png`, `image/tiff`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | N | SPEC-006 §2 |
| size_bytes | Integer | N | bytes; ≤ 25 MB | N | SPEC-006 §2 |
| s3_key | String | N | never returned in API responses | N | SPEC-006 §2 |
| s3_bucket | String | N | — | N | SPEC-006 §2 |
| is_encrypted | Boolean | N | default true | N | SPEC-006 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete; S3 object not removed | N | SPEC-006 §2 |

### ConsentType — `consent_types`

Org-scoped reference table defining valid consent categories. System types are protected.

Soft-deleted: No (uses `is_active`). Audit-logged: Yes. PHI: No.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| name | String | N | — | N | SPEC-006 §2 |
| slug | String | N | unique per org; system slugs globally reserved (`treatment`, `telehealth`, `release_of_information`, ...) | N | SPEC-006 §2 |
| is_system_type | Boolean | N | default false | N | SPEC-006 §2 |
| is_active | Boolean | N | default true | N | SPEC-006 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |

### ClientConsent — `client_consents`

A consent agreement recorded for a client. Expiry is enforced at read time; the `expired` status is set lazily via a system-triggered transition.

Soft-deleted: Yes. Audit-logged: Yes. PHI: Yes via `notes`.

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| client_instance_id | UUID (FK → EntityInstance) | N | must be a `client` type | N | SPEC-006 §2 |
| consent_type_id | UUID (FK → ConsentType) | N | type must be active | N | SPEC-006 §2 |
| status | Enum (StrEnum / VARCHAR) | N | `pending`, `signed`, `revoked`, `expired` | N | SPEC-006 §2 |
| signed_at | Timestamp (UTC) | Y | — | N | SPEC-006 §2 |
| signed_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-006 §2 |
| effective_date | Date | Y | — | N | SPEC-006 §2 |
| expiration_date | Date | Y | null = no expiry | N | SPEC-006 §2 |
| revoked_at | Timestamp (UTC) | Y | — | N | SPEC-006 §2 |
| revoked_by_person_id | UUID (FK → Person) | Y | — | N | SPEC-006 §2 |
| revocation_reason | Text | Y | required when status is revoked | N | SPEC-006 §2 |
| document_id | UUID (FK → Document) | Y | — | N | SPEC-006 §2 |
| form_template_id | UUID (FK → FormTemplate) | Y | — | N | SPEC-006 §2 |
| notes | Text | Y | internal notes | **Y** | SPEC-006 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-006 §2 |

### FormTemplate — `form_templates`

A reusable form definition for intake, assessment, or consent workflows. System templates are protected; schema changes auto-increment `version`.

Soft-deleted: Yes. Audit-logged: Yes. PHI: No (templates are structural, not client-bound).

| Field | Type | Nullable | Unit/Enum | PHI | Spec |
|---|---|---|---|---|---|
| id | UUID | N | — | N | SPEC-006 §2 |
| organization_id | UUID (FK → Organization) | N | — | N | SPEC-006 §2 |
| name | String | N | — | N | SPEC-006 §2 |
| slug | String | N | unique per org; system slugs globally reserved | N | SPEC-006 §2 |
| form_type | Enum (StrEnum / VARCHAR) | N | `intake`, `assessment`, `consent`, `custom` | N | SPEC-006 §2 |
| schema | JSONB | N | structure per SPEC-006 §2 "FormTemplate Schema Structure" | N | SPEC-006 §2 |
| version | String | N | semantic version, default `"1.0.0"` | N | SPEC-006 §2 |
| is_system_template | Boolean | N | default false | N | SPEC-006 §2 |
| is_active | Boolean | N | default true | N | SPEC-006 §2 |
| created_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| updated_at | Timestamp (UTC) | N | — | N | SPEC-006 §2 |
| deleted_at | Timestamp (UTC) | Y | soft delete marker | N | SPEC-006 §2 |

---

## Fields flagged as ambiguous in the specs

Items where the specs are silent, inconsistent, or leave a decision unresolved. These should be read as "needs a spec clarification or ADR," not as implementation guidance.

- **Organization auditing.** SPEC-006 §5 lists audit coverage for every domain but does not explicitly list the Organization table (tenant creation, rename, suspension). Whether Organization state changes write AuditLog rows is implied by BR-07 but not stated.
- **Organization currency.** SPEC-005 §6 says "All monetary values are stored as integer cents in the currency of the organization's locale," but Organization has no `currency` or `locale` column. The currency per tenant is effectively unspecified.
- **Organization soft delete.** Organization uses `is_active` for suspension and has no `deleted_at`. There is no defined path to delete a tenant; whether tenant deletion is soft or hard is not specified.
- **Role / Permission / RolePermission deletion.** None have `deleted_at`. System rows are protected, and RolePermission uses `revoked_at`, but whether a custom Role or Permission hard-deletes or soft-deletes on DELETE is not stated.
- **AttributeValue lineage without timestamps.** AttributeValue intentionally has no `created_at`, `updated_at`, or `deleted_at` (design note in SPEC-001 §2). Lineage is expected to be reconstructable from AuditLog on the parent EntityInstance, but the AttributeValue-level audit snapshot also excludes `value` per SPEC-001 §7, so the prior value is not recoverable from either source.
- **EntityType / EntityAttribute deletion.** Neither carries `deleted_at`. System types and seed attributes are protected from deletion, but the DELETE endpoints for custom rows are not explicit about hard vs soft delete semantics.
- **Document updatability.** Document has `created_at` but no `updated_at`. The two-step upload pattern (POST then `/confirm`) appears to mutate the record, and soft-delete sets `deleted_at`, yet no `updated_at` column is defined to track either.
- **AuditLog organization scope for platform events.** AuditLog.organization_id is NOT NULL, but some actions (tenant creation by system_admin, cross-tenant platform ops) may have no natural organization. The spec does not describe how these are logged.
- **ClientInsurance unique constraint.** SPEC-005 §2 states the unique constraint as `(organization_id, client_instance_id, insurance_payer_id, priority, is_active-is-true active set)`. The phrase "is_active-is-true active set" is unclear; it presumably means a partial unique index filtered on `is_active = true`, but the exact index definition is not given.
- **ClientInsurance PHI marking.** `member_id` and `group_number` are insurance identifiers linked to a specific client. They are not named in the BR-08 exclusion list but are PHI under HIPAA when correlated to a patient. The specs do not classify them either way.
- **Document file_name PHI handling.** `file_name` is user-supplied and can contain a client's name or identifier. It is not named in the BR-08 exclusion list; handling in audit snapshots and logs is unspecified.
- **Consent lazy expiry correctness under reads without writes.** SPEC-006 §3 says expired transitions happen "when a consent is queried and found to be past its expiration date," but also says `test_cron_job_transitions_expired_consents` is a test case. The spec references a cron job without defining its schedule, ownership, or invocation path — only the per-record error handling is described.
- **Role.updated_at vs Role versioning.** Role has `updated_at` but no history table; it is unclear how a role rename or hierarchy change is reconstructable beyond AuditLog snapshots.

---

## Cross-entity foreign key relationships

All FKs are declared as plain columns (no `relationship()`). Joins are written explicitly in the query layer.

**Every tenanted table → Organization.** `organization_id` is NOT NULL on every table except Person, EntityType (nullable for system types), Role (nullable for system roles), and Permission (nullable for system permissions).

**EAV internal.**
- EntityAttribute.entity_type_id → EntityType.id
- EntityInstance.entity_type_id → EntityType.id
- EntityInstance.person_id → Person.id (when EntityType.is_person_subtype = true)
- AttributeValue.entity_instance_id → EntityInstance.id
- AttributeValue.entity_attribute_id → EntityAttribute.id

**Identity and RBAC.**
- PersonRole.person_id → Person.id
- PersonRole.role_id → Role.id
- PersonRole.entity_instance_id → EntityInstance.id (profile binding)
- PersonRole.assigned_by_person_id → Person.id
- Role.parent_role_id → Role.id (self-reference for hierarchy)
- RolePermission.role_id → Role.id
- RolePermission.permission_id → Permission.id
- RolePermission.granted_by_person_id → Person.id

**Scheduling.**
- AppointmentType.cpt_code_id → CPTCode.id
- Session.appointment_type_id → AppointmentType.id
- Session.provider_instance_id → EntityInstance.id (must be a `provider` type)
- Session.client_instance_id → EntityInstance.id (must be a `client` type)
- Session.cancelled_by_person_id → Person.id

**Clinical.**
- ClinicalNote.session_id → Session.id (unique: one per session)
- ClinicalNote.author_instance_id → EntityInstance.id (must be a `provider` type)
- ClinicalNote.signed_by_person_id → Person.id
- ClinicalNote.cosigned_by_person_id → Person.id

**Billing.**
- ClientInsurance.client_instance_id → EntityInstance.id (must be a `client` type)
- ClientInsurance.insurance_payer_id → InsurancePayer.id
- Invoice.session_id → Session.id (partial unique excluding voided)
- Invoice.client_instance_id → EntityInstance.id (must match session; must be a `client` type)
- Invoice.provider_instance_id → EntityInstance.id (must match session; must be a `provider` type)
- Invoice.voided_by_person_id → Person.id
- InvoiceLineItem.invoice_id → Invoice.id
- InvoiceLineItem.cpt_code_id → CPTCode.id
- InvoiceLineItem.icd_code_id → ICDCode.id
- Payment.invoice_id → Invoice.id
- Payment.insurance_payer_id → InsurancePayer.id (required when payer_type = insurance)
- Payment.recorded_by_person_id → Person.id
- Payment.voided_by_person_id → Person.id

**Compliance.**
- AuditLog.actor_person_id → Person.id
- AuditLog.resource_id → (untyped; stores the PK of whichever table is named in resource_type; no declarative FK)
- Document.document_type_id → DocumentType.id
- Document.uploaded_by_person_id → Person.id
- Document.linked_resource_id → (untyped; stores the PK of whichever table is named in DocumentType.linked_resource_table; no declarative FK, validated at the application layer)
- ClientConsent.client_instance_id → EntityInstance.id (must be a `client` type)
- ClientConsent.consent_type_id → ConsentType.id
- ClientConsent.signed_by_person_id → Person.id
- ClientConsent.revoked_by_person_id → Person.id
- ClientConsent.document_id → Document.id
- ClientConsent.form_template_id → FormTemplate.id

**Bridge rules (validated at application layer, not enforced by FK):**

| Context | Column | Required EntityType |
|---|---|---|
| Session | provider_instance_id | provider |
| Session | client_instance_id | client |
| ClinicalNote | author_instance_id | provider |
| Invoice | provider_instance_id | provider |
| Invoice | client_instance_id | client |
| ClientInsurance | client_instance_id | client |
| ClientConsent | client_instance_id | client |
| PersonRole | entity_instance_id | must match the role's `primary_domain` |

**Polymorphic references (no FK, validated at application layer):**

- AuditLog.(resource_type, resource_id) points at any audited table.
- Document.linked_resource_id points at the table named in the parent DocumentType.linked_resource_table (one of `session`, `clinical_note`, `invoice`, `entity_instance`, `person`).
