# SPEC-006: Documents, Consent, and Compliance

**Status:** Draft
**Version:** 0.2.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** File storage, client consent tracking, audit logging, and intake form management.

---

## 1. Domain Overview

This domain owns the compliance and documentation infrastructure that cuts across all other domains. It is responsible for four distinct concerns that are grouped here because they share a common purpose: producing and preserving the evidence trail required for HIPAA-ready operation.

- AuditLog is the immutable record that every other domain writes to when state changes occur. It is append-only and owned exclusively here.
- Document manages uploaded files stored in AWS S3, encrypted at rest, and linked to clinical or organizational records.
- ClientConsent tracks the formal consent agreements a client signs before receiving care.
- FormTemplate defines reusable intake and assessment form structures that can be sent to clients.

No other domain may own these tables or define their structure. Other domains reference them but do not modify their schema.

### Tables owned

- AuditLog: Immutable record of every user-initiated state change in the platform.
- DocumentType: Organization-scoped reference table defining valid document categories.
- Document: Metadata record for an uploaded file stored in S3, linked to a DocumentType.
- ConsentType: Organization-scoped reference table defining valid consent categories.
- ClientConsent: A consent agreement of a specific type, signed by or on behalf of a client.
- FormTemplate: A reusable form structure for intake, assessment, or consent workflows.

---

## 2. Data Model Detail

### AuditLog

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant context of the action. |
| actor_person_id | UUID | FK -> Person, NULLABLE | Person who performed the action. Null for system-initiated events. |
| action | String | NOT NULL | Verb describing the operation (for example created, updated, deleted, signed, voided, assigned). |
| resource_type | String | NOT NULL | The table or domain object that was affected (for example Session, ClinicalNote, Invoice, PersonRole). |
| resource_id | UUID | NOT NULL | Primary key of the affected record. |
| previous_state | JSONB | NULLABLE | Snapshot of relevant fields before the change. Must exclude PHI fields. See BR-08. |
| next_state | JSONB | NULLABLE | Snapshot of relevant fields after the change. Must exclude PHI fields. See BR-08. |
| ip_address | String | NULLABLE | IP address of the request origin. |
| user_agent | String | NULLABLE | Browser or client agent string. |
| occurred_at | Timestamp | NOT NULL, default now | When the action occurred in UTC. |

AuditLog rows are never updated or deleted. There are no updated_at or deleted_at columns. Any operation that attempts to modify or remove an existing AuditLog row must be rejected at the database and application layer.

### DocumentType

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes document type to a tenant. |
| name | String | NOT NULL | Human label (for example Session Document, Consent Form, Insurance Card, Referral Letter). |
| slug | String | NOT NULL | Stable machine identifier (for example session_document, consent_form). |
| linked_resource_table | String | NULLABLE | The table name this type links to (for example Session, ClinicalNote, ClientConsent, EntityInstance). Null means the type can be used for unlinked documents. |
| is_system_type | Boolean | NOT NULL, default false | Protected seed types that cannot be deleted. |
| is_active | Boolean | NOT NULL, default true | Inactive types cannot be used on new documents. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

**Unique constraint:** (organization_id, slug). Slug is unique within an organization. System type slugs are globally reserved.

**Seed document types:** session_document, clinical_attachment, consent_form, insurance_card, referral_letter, prior_authorization, identification, intake_form.

### Document

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes document to a tenant. |
| document_type_id | UUID | FK -> DocumentType, NOT NULL | Categorizes the document. Replaces free-form resource type string. |
| uploaded_by_person_id | UUID | FK -> Person, NOT NULL | Person who uploaded the file. |
| linked_resource_id | UUID | NULLABLE | Primary key of the linked record. When set, the linked record must exist in the table specified by the DocumentType's linked_resource_table. Validated at application layer. |
| file_name | String | NOT NULL | Original filename. Sanitized server-side: path components stripped, max 255 characters, no null bytes or control characters. |
| mime_type | String | NOT NULL | MIME type, validated server-side against allowlist. See file upload constraints below. |
| size_bytes | Integer | NOT NULL | File size in bytes at time of upload. Validated against maximum before S3 upload. |
| s3_key | String | NOT NULL | Full object key in S3. Never exposed directly to clients. |
| s3_bucket | String | NOT NULL | S3 bucket name. Allows bucket migration without data loss. |
| is_encrypted | Boolean | NOT NULL, default true | Confirms server-side encryption is applied. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. S3 object is not removed on soft delete. See ADR-009. |

The s3_key is never returned in any API response. File access is provided via a time-limited presigned URL generated at request time.

### File upload constraints

| Constraint | Value |
|---|---|
| Maximum file size | 25 MB |
| Allowed MIME types | application/pdf, image/jpeg, image/png, image/tiff, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| Filename max length | 255 characters |
| Filename sanitization | Strip path components, reject null bytes and control characters |

All constraints are enforced server-side before the presigned S3 upload URL is generated. Client-supplied values are not trusted.

### ConsentType

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes consent type to a tenant. |
| name | String | NOT NULL | Human label (for example Treatment Consent, Telehealth Consent, Release of Information). |
| slug | String | NOT NULL | Stable machine identifier (for example treatment, telehealth, release_of_information). |
| is_system_type | Boolean | NOT NULL, default false | Protected seed types that cannot be deleted. |
| is_active | Boolean | NOT NULL, default true | Inactive types cannot be used on new consent records. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

**Unique constraint:** (organization_id, slug). Slug is unique within an organization. System type slugs are globally reserved.

**Seed consent types:** treatment, telehealth, release_of_information, minor_assent, guardian_consent, hipaa_privacy_notice, financial_responsibility, medication_consent, group_therapy_consent.

### ClientConsent

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes consent to a tenant. |
| client_instance_id | UUID | FK -> EntityInstance, NOT NULL | Client profile instance who gave or for whom consent was recorded. Must reference an EntityInstance of type client. |
| consent_type_id | UUID | FK -> ConsentType, NOT NULL | Type of consent. References the organization-scoped ConsentType table. |
| status | Enum | NOT NULL | One of: pending, signed, revoked, expired. |
| signed_at | Timestamp | NULLABLE | When consent was formally recorded. |
| signed_by_person_id | UUID | FK -> Person, NULLABLE | Person who recorded or co-signed the consent. |
| effective_date | Date | NULLABLE | Date consent becomes active. |
| expiration_date | Date | NULLABLE | Date consent expires automatically. Null means no fixed expiry. |
| revoked_at | Timestamp | NULLABLE | When consent was revoked. |
| revoked_by_person_id | UUID | FK -> Person, NULLABLE | Person who recorded the revocation. |
| revocation_reason | Text | NULLABLE | Required when status is revoked. |
| document_id | UUID | FK -> Document, NULLABLE | Signed consent form document, if uploaded. |
| form_template_id | UUID | FK -> FormTemplate, NULLABLE | Form template used to generate the consent, if applicable. |
| notes | Text | NULLABLE | Internal notes on the consent record. PHI — excluded from logs per BR-08. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

### FormTemplate

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes template to a tenant. System templates are seeded per-org on organization creation. |
| name | String | NOT NULL | Human label for the form (for example New Client Intake, Telehealth Consent). |
| slug | String | NOT NULL | Stable machine identifier. |
| form_type | Enum | NOT NULL | One of: intake, assessment, consent, custom. |
| schema | JSONB | NOT NULL | Form field definitions. Describes field names, types, labels, and required flags. |
| version | String | NOT NULL, default "1.0.0" | Semantic version of this template. Incremented when schema changes. |
| is_system_template | Boolean | NOT NULL, default false | Protected templates provided by the platform. Cannot be deleted or have slug/form_type changed. |
| is_active | Boolean | NOT NULL, default true | Inactive templates cannot be sent to new clients. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

**Unique constraint:** (organization_id, slug). Slug is unique within an organization. System template slugs are globally reserved.

---

## 3. Consent Status Lifecycle

| From | Allowed transitions | Trigger |
|---|---|---|
| pending | signed, revoked | Explicit action by authorized user |
| signed | revoked, expired | Revocation action or expiration_date passing |
| revoked | none (terminal) | — |
| expired | none (terminal) | — |

Expiry is handled by a Celery Beat scheduled task (`expire_consents`). The task runs daily at 00:00 UTC, queries all ClientConsent records where `status = 'signed'` and `expiration_date < CURRENT_DATE`, transitions each to `expired`, and writes an AuditLog entry per record with `actor_person_id = NULL` (system-triggered event). See SPEC-007 §10 for task infrastructure. As a defense-in-depth measure, all consent gate checks must also verify `expiration_date IS NULL OR expiration_date >= CURRENT_DATE` in addition to checking `status = 'signed'`, so an expired consent is never treated as valid even if the cron job has not yet run.

---

## 4. Business Rules

### BR-07 (Audit log every state change)

Every API call that results in a create, update, delete, or status transition on any table in any domain must write an AuditLog row before returning a success response. The audit write is part of the same database transaction as the change. If the audit write fails, the entire transaction rolls back.

The following fields govern what is logged safely:
- resource_type and resource_id identify what changed.
- action names the operation.
- previous_state and next_state capture field-level diffs, excluding PHI fields defined under BR-08.
- actor_person_id and occurred_at establish accountability and timing.

### BR-08 (No PHI in logs)

Application logs and AuditLog state snapshots must never contain the following categories of PHI:

- Clinical note content (all format keys: subjective, objective, assessment, plan, data, intervention, response, behavior).
- Diagnosis codes linked to a specific person (ICDCode values on InvoiceLineItem when correlated to a client).
- Date of birth (Person.date_of_birth).
- Any free-text field on ClientConsent.notes or Document records.
- AttributeValue content for any attribute marked as PHI-bearing by the practice.

The AuditLog previous_state and next_state snapshots must be filtered at the application layer before the row is written. A field exclusion list must be defined and applied by the audit service, not left to individual callers.

### Document rules

- The s3_key must never appear in any API response. File access is always mediated by a presigned URL with a short expiry window. See ADR-009.
- Documents linked to soft-deleted records remain accessible to authorized users until explicitly soft-deleted themselves.
- File size and MIME type must be validated server-side against the allowlist defined in the file upload constraints table before the presigned S3 upload URL is generated. Client-supplied values are not trusted.
- DocumentType activity: Only active DocumentType records (is_active = true) may be used when creating new documents.
- DocumentType system protection: System document types (is_system_type = true) cannot be deleted or have their slug changed.
- Linked resource validation: When linked_resource_id is set, the application layer must verify that the referenced record exists in the table specified by the DocumentType's linked_resource_table and belongs to the same organization. When linked_resource_id is null, the document is unlinked (filed by type only).
- Both-or-neither rule: If a DocumentType has a non-null linked_resource_table, documents of that type must provide a linked_resource_id. If linked_resource_table is null, linked_resource_id must also be null.

### Consent rules

- A client without a signed treatment consent record cannot have a session status transitioned to completed. This gate is enforced in SPEC-003's session completion path. Since invoice creation requires a completed session (SPEC-005), the consent requirement is transitively enforced for billing without a separate check.
- Revocation reason is required when setting status to revoked.
- A client may have multiple consent records of the same consent_type_id over time (for example after annual renewal), but only one may be in signed status at a time per type. The backend must reject a sign action if an active signed record of the same consent_type_id already exists for the client.
- ConsentType activity: Only active ConsentType records (is_active = true) may be used when creating new consent records.
- ConsentType system protection: System consent types (is_system_type = true) cannot be deleted or have their slug changed.

### FormTemplate rules

- System templates (is_system_template = true) cannot be deleted or have their slug or form_type changed.
- When a FormTemplate schema changes, version must be incremented. Old versions are not retained in this table; version history is tracked via AuditLog.

---

## 5. Audit Coverage Matrix

Every domain must produce audit log entries for the following action types. This section defines the authoritative coverage expectation.

| Domain | Resource types audited | Actions audited |
|---|---|---|
| SPEC-001 EAV | EntityType, EntityAttribute, EntityInstance, AttributeValue | created, updated, deleted |
| SPEC-002 Identity | Person, PersonRole, Role, Permission, RolePermission | created, updated, deleted, assigned, revoked |
| SPEC-003 Scheduling | Session, AppointmentType | created, updated, deleted, status_changed |
| SPEC-004 Clinical | ClinicalNote | created, updated, deleted, signed, cosigned, amended |
| SPEC-005 Billing | Invoice, InvoiceLineItem, Payment, ClientInsurance, InsurancePayer, CPTCode, ICDCode | created, updated, deleted, sent, voided, payment_recorded, payment_voided |
| SPEC-006 Compliance | DocumentType, Document, ConsentType, ClientConsent, FormTemplate | created, updated, deleted, signed, revoked, expired, uploaded |

---

## 6. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

### DocumentType management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /document-types | List active document types for the org | documents.read |
| POST | /document-types | Create a custom document type | documents.write |
| PATCH | /document-types/{id} | Update a custom document type (system types blocked) | documents.write |
| DELETE | /document-types/{id} | Deactivate a custom document type (system types blocked) | documents.write |

### ConsentType management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /consent-types | List active consent types for the org | consents.read |
| POST | /consent-types | Create a custom consent type | consents.write |
| PATCH | /consent-types/{id} | Update a custom consent type (system types blocked) | consents.write |
| DELETE | /consent-types/{id} | Deactivate a custom consent type (system types blocked) | consents.write |

### Document management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /documents | List documents for the org (filterable by linked resource) | documents.read |
| POST | /documents | Initiate upload: validate metadata, return presigned S3 URL | documents.write |
| POST | /documents/{id}/confirm | Confirm upload complete and activate the document record | documents.write |
| GET | /documents/{id} | Retrieve document metadata and a fresh presigned download URL | documents.read |
| DELETE | /documents/{id} | Soft delete the document record | documents.delete |

File upload follows a two-step pattern. The caller first posts metadata to receive a presigned S3 upload URL. After the client uploads directly to S3, the caller confirms completion to activate the document record. This avoids routing file bytes through the API server.

### ClientConsent management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entities/{type_slug}/{id}/consents | List all consent records for a client | consents.read |
| POST | /entities/{type_slug}/{id}/consents | Create a consent record | consents.write |
| GET | /entities/{type_slug}/{id}/consents/{consent_id} | Retrieve a consent record | consents.read |
| PATCH | /entities/{type_slug}/{id}/consents/{consent_id} | Update a pending consent record | consents.write |
| POST | /entities/{type_slug}/{id}/consents/{consent_id}/sign | Record consent as signed | consents.sign |
| POST | /entities/{type_slug}/{id}/consents/{consent_id}/revoke | Revoke a signed consent with required reason | consents.revoke |

Client consent endpoints follow EAV routing conventions from SPEC-001. The `type_slug` must resolve to client; requests with a non-client type_slug are rejected with 422.

### FormTemplate management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /form-templates | List all active templates for the org | forms.read |
| POST | /form-templates | Create a custom template | forms.write |
| GET | /form-templates/{id} | Retrieve template with schema | forms.read |
| PATCH | /form-templates/{id} | Update a custom template (system templates blocked) | forms.write |
| DELETE | /form-templates/{id} | Deactivate a custom template | forms.write |

### AuditLog access

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /audit-log | Query audit log (paginated, filterable by actor, resource type, resource id, date range) | audit.read |
| GET | /audit-log/{id} | Retrieve a single audit log entry | audit.read |

AuditLog has no write endpoints. Entries are written only by internal service calls, never by direct API request.

---

## 7. Implementation Constraints

- Audit atomicity: AuditLog writes must be in the same database transaction as the state change they record. An audit failure must roll back the whole transaction. Callers must never suppress audit errors to allow a business operation to succeed silently.
- PHI field exclusion list: A single centralized exclusion list must define which fields are stripped from previous_state and next_state before the AuditLog row is written. This list is a platform configuration concern, not a per-endpoint concern.
- Presigned URL expiry: S3 presigned download URLs must have a short expiry. The exact window is defined in ADR-009 but must be measured in minutes, not hours.
- S3 key opacity: The s3_key column must be marked as excluded from all serialization schemas that produce API responses. It is only used internally when generating presigned URLs.
- Consent session gate: The session completion path in SPEC-003 must consult the consent service to verify an active signed treatment consent exists before allowing the transition to completed. The check must verify `status = 'signed'` AND `expiration_date IS NULL OR expiration_date >= CURRENT_DATE` on a ConsentType with slug = 'treatment'. This is a service-layer dependency, not enforced by a foreign key.
- FormTemplate versioning: Any PATCH to a FormTemplate schema field must increment the version automatically if the caller does not supply an updated version. Auto-increment uses semantic minor version bumping.

---

## 8. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-009 | File storage and encryption | Defines S3 bucket configuration, SSE strategy, presigned URL lifetime, and key management. Blocks Document implementation. |
| ADR-006 | Soft delete strategy | Defines how document and consent records are soft-deleted and whether S3 objects are removed on deletion. |
| ADR-011 | Multi-tenancy isolation | Requires all document, consent, and audit queries to filter by organization_id. |
| ADR-014 | Monitoring and observability | Defines how audit log data feeds into platform observability and alerting pipelines. |

---

## 9. Test Table

Every business rule and constraint maps to at least one test case per SPEC-000 §5.

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| AuditLog | immutability | `test_update_audit_log_row_rejected` | Integration | Audit rows cannot be modified |
| AuditLog | immutability | `test_delete_audit_log_row_rejected` | Integration | Audit rows cannot be deleted |
| AuditLog | transactional write | `test_state_change_writes_audit_entry` | Integration | BR-07: every state change logged |
| AuditLog | transactional write | `test_audit_failure_rolls_back_business_operation` | Integration | Audit atomicity |
| AuditLog | `previous_state` + `next_state` | `test_audit_snapshot_excludes_phi_fields` | Integration | BR-08: PHI excluded from snapshots |
| AuditLog | `actor_person_id` | `test_system_triggered_audit_has_null_actor` | Integration | Cron-triggered events have null actor |
| AuditLog | `organization_id` | `test_audit_log_filters_by_org` | Integration | Multi-tenant isolation |
| DocumentType | `UNIQUE(organization_id, slug)` | `test_duplicate_document_type_slug_same_org_returns_409` | Integration | Unique constraint |
| DocumentType | `is_system_type` | `test_delete_system_document_type_returns_409` | Integration | System type protection |
| DocumentType | `is_active` | `test_create_document_with_inactive_type_returns_422` | Integration | Activity check |
| Document | `document_type_id` FK → DocumentType | `test_create_document_with_valid_type_succeeds` | Integration | FK integrity |
| Document | `linked_resource_id` | `test_create_document_linked_resource_not_found_returns_422` | Integration | Linked resource validation |
| Document | `linked_resource_id` | `test_create_document_linked_resource_wrong_org_returns_422` | Integration | Cross-tenant validation |
| Document | both-or-neither rule | `test_create_document_linkable_type_without_resource_id_returns_422` | Integration | Both-or-neither rule |
| Document | both-or-neither rule | `test_create_document_unlinkable_type_with_resource_id_returns_422` | Integration | Both-or-neither rule |
| Document | `s3_key` | `test_document_api_response_excludes_s3_key` | Integration | S3 key opacity |
| Document | presigned URL | `test_document_download_returns_presigned_url` | Integration | Presigned URL access |
| Document | `mime_type` | `test_upload_disallowed_mime_type_returns_422` | Integration | MIME type allowlist |
| Document | `size_bytes` | `test_upload_exceeding_max_size_returns_422` | Integration | 25 MB limit |
| Document | `file_name` | `test_upload_filename_sanitized` | Unit | Path traversal prevention |
| Document | `deleted_at` | `test_soft_deleted_document_excluded_from_list` | Integration | BR-05 |
| Document | `organization_id` | `test_list_documents_filters_by_org` | Integration | Multi-tenant isolation |
| ConsentType | `UNIQUE(organization_id, slug)` | `test_duplicate_consent_type_slug_same_org_returns_409` | Integration | Unique constraint |
| ConsentType | `is_system_type` | `test_delete_system_consent_type_returns_409` | Integration | System type protection |
| ConsentType | `is_active` | `test_create_consent_with_inactive_type_returns_422` | Integration | Activity check |
| ClientConsent | `consent_type_id` FK → ConsentType | `test_create_consent_with_valid_type_succeeds` | Integration | FK integrity |
| ClientConsent | `client_instance_id` FK → EntityInstance | `test_create_consent_non_client_type_returns_422` | Integration | Client bridge rule |
| ClientConsent | `status` lifecycle | `test_sign_pending_transitions_to_signed` | Integration | pending → signed |
| ClientConsent | `status` lifecycle | `test_revoke_signed_transitions_to_revoked` | Integration | signed → revoked |
| ClientConsent | `status` lifecycle | `test_revoke_without_reason_returns_422` | Integration | Revocation reason required |
| ClientConsent | `status` lifecycle | `test_transition_out_of_revoked_returns_409` | Integration | Revoked is terminal |
| ClientConsent | `status` lifecycle | `test_transition_out_of_expired_returns_409` | Integration | Expired is terminal |
| ClientConsent | unique signed per type | `test_sign_consent_when_active_signed_exists_returns_409` | Integration | One signed per type per client |
| ClientConsent | `expiration_date` | `test_expired_consent_not_treated_as_valid` | Integration | Read-time expiry check |
| ClientConsent | `expiration_date` | `test_cron_job_transitions_expired_consents` | Integration | Cron job persistence |
| ClientConsent | `expiration_date` | `test_cron_job_writes_audit_entry_for_expiry` | Integration | Audit on system-triggered expiry |
| ClientConsent | consent gate | `test_complete_session_without_treatment_consent_returns_422` | Integration | Consent session gate (SPEC-003) |
| ClientConsent | consent gate | `test_complete_session_with_expired_consent_returns_422` | Integration | Expired consent blocks completion |
| ClientConsent | `deleted_at` | `test_soft_deleted_consent_excluded_from_list` | Integration | BR-05 |
| ClientConsent | `organization_id` | `test_list_consents_filters_by_org` | Integration | Multi-tenant isolation |
| FormTemplate | `UNIQUE(organization_id, slug)` | `test_duplicate_form_template_slug_same_org_returns_409` | Integration | Unique constraint |
| FormTemplate | `is_system_template` | `test_delete_system_template_returns_409` | Integration | System template protection |
| FormTemplate | `schema` + `version` | `test_patch_schema_auto_increments_version` | Integration | Auto-version on schema change |
| FormTemplate | `deleted_at` | `test_soft_deleted_template_excluded_from_list` | Integration | BR-05 |
| FormTemplate | `organization_id` | `test_list_templates_filters_by_org` | Integration | Multi-tenant isolation |

---

## 10. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full model definitions for AuditLog, Document, ClientConsent, and FormTemplate. Consent lifecycle, BR-07 and BR-08 full specifications, audit coverage matrix, two-step document upload pattern, API surface, and ADR mapping. |
| 0.2.0 | Added DocumentType and ConsentType reference tables replacing free-form strings and hardcoded enums. Made FormTemplate organization_id NOT NULL (system templates seeded per-org). Added deleted_at to ClientConsent and FormTemplate. Defined cron job for consent expiry with defense-in-depth read-time check. Added file upload constraints (25MB max, MIME allowlist, filename sanitization). Updated consent URLs to EAV routing. Added DocumentType and ConsentType management APIs. Updated audit coverage matrix. Clarified consent session gate (SPEC-003 only, not billing). Added test table with 45 test cases. Introduced granular consent permissions (consents.read, consents.write, consents.sign, consents.revoke). |
