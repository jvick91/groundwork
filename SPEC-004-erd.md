# SPEC-004: Clinical Notes — Entity Relationship Diagram

Tables owned by SPEC-004 and their relationships to tables from other domains.

```mermaid
erDiagram
    Organization {
        UUID id PK
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

    Person {
        UUID id PK
        String name
        String email
        String phone
        Date dob
    }

    Session {
        UUID id PK
        UUID organization_id FK
        UUID provider_instance_id FK
        UUID client_instance_id FK
        Enum status
        Timestamp start_time
        Timestamp end_time
    }

    ClinicalNote {
        UUID id PK
        UUID organization_id FK
        UUID session_id FK "UNIQUE — one note per session"
        UUID author_instance_id FK "must be provider EntityInstance"
        Enum note_format "soap | dap | birp — immutable after creation"
        Enum status "draft | signed | cosigned | amendment_pending"
        JSONB content "structured body — locked after first signing"
        Timestamp signed_at "set once at signing — immutable"
        UUID signed_by_person_id FK
        Timestamp cosigned_at
        UUID cosigned_by_person_id FK
        Boolean cosign_required "default false"
        Text amendment_note "append-only after signing"
        Timestamp created_at
        Timestamp updated_at
        Timestamp deleted_at "soft delete"
    }

    Role {
        UUID id PK
        String name
    }

    Permission {
        UUID id PK
        String action
        String entity_type
    }

    RolePermission {
        UUID role_id FK
        UUID permission_id FK
    }

    AuditLog {
        UUID id PK
        UUID organization_id FK
        UUID person_id FK
        String action
        String resource_type
        UUID resource_id
        Timestamp created_at
    }

    %% Ownership / tenancy
    Organization ||--o{ ClinicalNote : "scopes"
    Organization ||--o{ Session : "scopes"
    Organization ||--o{ EntityInstance : "scopes"

    %% Core relationships
    Session ||--o| ClinicalNote : "one note per session"
    EntityInstance ||--o{ ClinicalNote : "author_instance_id"
    Person ||--o{ ClinicalNote : "signed_by_person_id"
    Person ||--o{ ClinicalNote : "cosigned_by_person_id"

    %% Author validation chain
    EntityType ||--o{ EntityInstance : "type check (slug = provider)"

    %% Permission chain for sign / cosign
    Role ||--o{ RolePermission : "grants"
    Permission ||--o{ RolePermission : "granted to"

    %% Audit trail
    ClinicalNote ||--o{ AuditLog : "all state changes logged"
```

## Relationship summary

| Relationship | Cardinality | Rule |
|---|---|---|
| Session → ClinicalNote | 1 : 0..1 | One note per session (UNIQUE on session_id). Soft-deleted notes still block creation of a replacement. |
| EntityInstance → ClinicalNote (author) | 1 : 0..N | Author must be a provider-type EntityInstance in the same org. |
| Person → ClinicalNote (signer) | 1 : 0..N | Person who signed. Requires `notes.sign` permission. |
| Person → ClinicalNote (co-signer) | 1 : 0..N | Person who co-signed. Requires `notes.cosign` permission. |
| Organization → ClinicalNote | 1 : 0..N | Multi-tenant scoping. All queries filter by org. |
| ClinicalNote → AuditLog | 1 : 0..N | Every POST/PATCH/DELETE/transition writes an audit entry (BR-07). |
