# SPEC-006: Documents, Consent, and Compliance — Entity Relationship Diagram

Tables owned by SPEC-006 and their relationships to tables from other domains.

```mermaid
erDiagram
    Organization {
        UUID id PK
    }

    Person {
        UUID id PK
        String first_name
        String last_name
        String email
    }

    EntityType {
        UUID id PK
        UUID organization_id FK
        String slug
    }

    EntityInstance {
        UUID id PK
        UUID organization_id FK
        UUID entity_type_id FK
    }

    Session {
        UUID id PK
        UUID organization_id FK
        Enum status
    }

    ClinicalNote {
        UUID id PK
        UUID organization_id FK
        UUID session_id FK
    }

    AuditLog {
        UUID id PK
        UUID organization_id FK "tenant context"
        UUID actor_person_id FK "null for system events"
        String action "created | updated | deleted | signed | voided | etc"
        String resource_type "table name of affected record"
        UUID resource_id "PK of affected record"
        JSONB previous_state "field diff before — PHI excluded"
        JSONB next_state "field diff after — PHI excluded"
        String ip_address
        String user_agent
        Timestamp occurred_at "immutable — no updated_at or deleted_at"
    }

    Document {
        UUID id PK
        UUID organization_id FK
        UUID uploaded_by_person_id FK
        String linked_resource_type "Session | ClinicalNote | ClientConsent | EntityInstance"
        UUID linked_resource_id "PK of linked record — polymorphic"
        String file_name
        String mime_type
        Integer size_bytes
        String s3_key "never exposed in API responses"
        String s3_bucket
        Boolean is_encrypted "default true"
        Boolean is_active
        Timestamp created_at
        Timestamp deleted_at "soft delete — S3 object retained"
    }

    ClientConsent {
        UUID id PK
        UUID organization_id FK
        UUID client_instance_id FK "must be client EntityInstance"
        Enum consent_type "treatment | telehealth | release_of_information | minor_assent | guardian_consent"
        Enum status "pending | signed | revoked | expired"
        Timestamp signed_at
        UUID signed_by_person_id FK
        Date effective_date
        Date expiration_date "null = no fixed expiry"
        Timestamp revoked_at
        UUID revoked_by_person_id FK
        String revocation_reason "required when revoked"
        UUID document_id FK "signed consent form upload"
        UUID form_template_id FK "template used to generate consent"
        Text notes
        Timestamp created_at
        Timestamp updated_at
    }

    FormTemplate {
        UUID id PK
        UUID organization_id FK "null for system templates"
        String name
        String slug
        Enum form_type "intake | assessment | consent | custom"
        JSONB schema "field definitions"
        String version "semver"
        Boolean is_system_template
        Boolean is_active
        Timestamp created_at
        Timestamp updated_at
    }

    %% Ownership / tenancy
    Organization ||--o{ AuditLog : "scopes"
    Organization ||--o{ Document : "scopes"
    Organization ||--o{ ClientConsent : "scopes"
    Organization ||--o| FormTemplate : "scopes (nullable for system templates)"

    %% AuditLog relationships
    Person ||--o{ AuditLog : "actor_person_id"

    %% Document relationships
    Person ||--o{ Document : "uploaded_by_person_id"

    %% Document polymorphic links (application-level, not FK)
    Session ||--o{ Document : "linked_resource (polymorphic)"
    ClinicalNote ||--o{ Document : "linked_resource (polymorphic)"
    ClientConsent ||--o{ Document : "linked_resource (polymorphic)"
    EntityInstance ||--o{ Document : "linked_resource (polymorphic)"

    %% ClientConsent relationships
    EntityInstance ||--o{ ClientConsent : "client_instance_id"
    EntityType ||--o{ EntityInstance : "type check (slug = client)"
    Person ||--o{ ClientConsent : "signed_by_person_id"
    Person ||--o{ ClientConsent : "revoked_by_person_id"
    Document ||--o| ClientConsent : "document_id (uploaded consent form)"
    FormTemplate ||--o{ ClientConsent : "form_template_id"

    %% Cross-domain audit writes (every domain writes here)
    Session ||--o{ AuditLog : "resource_type = Session"
    ClinicalNote ||--o{ AuditLog : "resource_type = ClinicalNote"
```

## Relationship summary

| Relationship | Cardinality | Rule |
|---|---|---|
| Organization → AuditLog | 1 : 0..N | All audit entries scoped to tenant. |
| Person → AuditLog (actor) | 1 : 0..N | Null for system-triggered events. |
| Organization → Document | 1 : 0..N | All documents scoped to tenant. |
| Person → Document (uploader) | 1 : 0..N | Person who uploaded the file. |
| Document → linked resource | 0..1 : 0..N | Polymorphic link via `linked_resource_type` + `linked_resource_id`. Application-level validation, no DB FK. |
| Organization → ClientConsent | 1 : 0..N | All consent records scoped to tenant. |
| EntityInstance → ClientConsent | 1 : 0..N | Client instance who gave consent. Must be client EntityType. |
| Person → ClientConsent (signer) | 1 : 0..N | Person who recorded the signature. |
| Person → ClientConsent (revoker) | 1 : 0..N | Person who revoked consent. |
| Document → ClientConsent | 0..1 : 0..1 | Optional uploaded signed consent form. |
| FormTemplate → ClientConsent | 1 : 0..N | Template used to generate the consent form. |
| Organization → FormTemplate | 1 : 0..N | Nullable for system-provided templates (no org owner). |
| All domain tables → AuditLog | 1 : 0..N | Every state change across all domains writes an audit entry (BR-07). |
