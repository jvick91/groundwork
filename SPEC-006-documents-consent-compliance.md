# SPEC-006: Documents, Consent, and Compliance

**Status:** Draft
**Version:** 0.1.0
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
- Document: Metadata record for an uploaded file stored in S3.
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

### Document

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes document to a tenant. |
| uploaded_by_person_id | UUID | FK -> Person, NOT NULL | Person who uploaded the file. |
| linked_resource_type | String | NULLABLE | The type of record this document is attached to (for example Session, ClinicalNote, ClientConsent, EntityInstance). |
| linked_resource_id | UUID | NULLABLE | Primary key of the linked record. |
| file_name | String | NOT NULL | Original filename as provided at upload. |
| mime_type | String | NOT NULL | MIME type of the file (for example application/pdf, image/jpeg). |
| size_bytes | Integer | NOT NULL | File size in bytes at time of upload. |
| s3_key | String | NOT NULL | Full object key in S3. Never exposed directly to clients. |
| s3_bucket | String | NOT NULL | S3 bucket name. Allows bucket migration without data loss. |
| is_encrypted | Boolean | NOT NULL, default true | Confirms server-side encryption is applied. |
| is_active | Boolean | NOT NULL, default true | Soft toggle. Inactive documents are not surfaced in normal queries. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. S3 object is not removed on soft delete. See ADR-009. |

The s3_key is never returned in any API response. File access is provided via a time-limited presigned URL generated at request time.

### ClientConsent

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes consent to a tenant. |
| client_instance_id | UUID | FK -> EntityInstance, NOT NULL | Client profile instance who gave or for whom consent was recorded. Must reference an EntityInstance of type client. |
| consent_type | Enum | NOT NULL | One of: treatment, telehealth, release_of_information, minor_assent, guardian_consent. |
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
| notes | Text | NULLABLE | Internal notes on the consent record. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

### FormTemplate

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NULLABLE | Null for system-provided templates, set for practice-created templates. |
| name | String | NOT NULL | Human label for the form (for example New Client Intake, Telehealth Consent). |
| slug | String | NOT NULL | Stable machine identifier. |
| form_type | Enum | NOT NULL | One of: intake, assessment, consent, custom. |
| schema | JSONB | NOT NULL | Form field definitions. Describes field names, types, labels, and required flags. |
| version | String | NOT NULL, default "1.0.0" | Semantic version of this template. Incremented when schema changes. |
| is_system_template | Boolean | NOT NULL, default false | Protected templates provided by the platform. Cannot be deleted. |
| is_active | Boolean | NOT NULL, default true | Inactive templates cannot be sent to new clients. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

**Unique constraint:** slug is unique within an organization; system template slugs are globally reserved.

---

## 3. Consent Status Lifecycle

| From | Allowed transitions | Trigger |
|---|---|---|
| pending | signed, revoked | Explicit action by authorized user |
| signed | revoked, expired | Revocation action or expiration_date passing |
| revoked | none (terminal) | — |
| expired | none (terminal) | — |

Expiry is a computed transition. When the current date surpasses expiration_date, the status is treated as expired in all application reads. A background job or read-time check may persist the status change. Either approach must write an AuditLog entry.

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
- Documents linked to soft-deleted records remain accessible to authorized users until explicitly deactivated.
- File size and MIME type must be validated server-side before the S3 upload is initiated. Client-supplied values are not trusted.

### Consent rules

- A client without a signed treatment consent record cannot have a session status transitioned to completed. The billing domain must check for active signed treatment consent before allowing invoice creation.
- Revocation reason is required when setting status to revoked.
- A client may have multiple consent records of the same consent_type over time (for example after annual renewal), but only one may be in signed status at a time per type. The backend must reject a sign action if an active signed record of the same type already exists for the client.

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
| SPEC-005 Billing | Invoice, InvoiceLineItem, Payment, ClientInsurance | created, updated, deleted, sent, voided, payment_recorded |
| SPEC-006 Compliance | Document, ClientConsent, FormTemplate | created, updated, deleted, signed, revoked, uploaded |

---

## 6. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

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
| GET | /entities/client/{id}/consents | List all consent records for a client | clients.read |
| POST | /entities/client/{id}/consents | Create a consent record | clients.write |
| GET | /entities/client/{id}/consents/{consent_id} | Retrieve a consent record | clients.read |
| PATCH | /entities/client/{id}/consents/{consent_id} | Update a pending consent record | clients.write |
| POST | /entities/client/{id}/consents/{consent_id}/sign | Record consent as signed | clients.write |
| POST | /entities/client/{id}/consents/{consent_id}/revoke | Revoke a signed consent with required reason | clients.write |

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
- Consent session gate: The session completion and invoice creation paths in SPEC-003 and SPEC-005 must consult the consent service to verify an active signed treatment consent exists before allowing the action. This check is a service-layer dependency, not enforced by a foreign key.
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

## 9. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full model definitions for AuditLog, Document, ClientConsent, and FormTemplate. Consent lifecycle, BR-07 and BR-08 full specifications, audit coverage matrix, two-step document upload pattern, API surface, and ADR mapping. |
