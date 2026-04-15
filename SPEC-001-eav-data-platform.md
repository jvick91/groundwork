# SPEC-001: EAV Data Platform

**Status:** Draft
**Version:** 0.6.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Core data flexibility, multi-tenancy, and persona metadata.

---

## 1. Domain Overview

The EAV (Entity-Attribute-Value) system is the architectural foundation that allows Groundwork to remain flexible without constant database migrations. While transactional events (sessions, notes, invoices) use concrete tables, the descriptive data for personas (providers, clients, admins, and any custom types a practice invents) is stored here.

### Tables owned

- Organization: The root tenant record. Every other record scopes to this.
- EntityType: Defines the template (e.g., provider, client, or a custom type like nutritionist).
- EntityAttribute: Defines specific fields on a type (e.g., license_number, npi_number).
- EntityInstance: An individual record of a type (e.g., Dr. Jane Smith's provider profile).
- AttributeValue: The specific data points for an instance (e.g., license_number = "NJ12345").

---

## 2. Data Model Detail

### Organization

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for the tenant. |
| name | String | NOT NULL | Legal name of the practice. |
| npi_number | String | NULLABLE | Organization-level NPI (Type 2). |
| tax_id | String | NULLABLE | EIN or tax identifier. |
| phone | String | NULLABLE | Main practice phone number. |
| address | Text | NULLABLE | Full mailing address. |
| timezone | String | NOT NULL, default "UTC" | IANA timezone (e.g., "America/New_York"). |
| is_active | Boolean | NOT NULL, default true | Soft toggle for tenant suspension. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time. |

### EntityType

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Unique identifier for the type. |
| organization_id | UUID | FK -> Organization, NULLABLE | NULL for system types, set for practice-created types. |
| name | String | NOT NULL | Human name (e.g., "provider", "client", "nutritionist"). |
| slug | String | NOT NULL, UNIQUE per org | URL-safe identifier (e.g., "provider", "custom-nutritionist"). |
| is_system_type | Boolean | NOT NULL, default false | True for seed types (provider, client, admin). Cannot be deleted. |
| is_person_subtype | Boolean | NOT NULL, default false | When true, EntityInstance links to a Person row. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |

### EntityAttribute

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Unique identifier for the field definition. |
| entity_type_id | UUID | FK -> EntityType, NOT NULL | The type this field belongs to. |
| name | String | NOT NULL | Machine name (e.g., "license_number"). |
| display_name | String | NOT NULL | Human label (e.g., "License Number"). |
| field_type | Enum | NOT NULL | One of: text, number, date, bool, enum, fk, jsonb. |
| is_required | Boolean | NOT NULL, default false | Whether the field must have a value on every instance. |
| options | JSONB | NULLABLE | Enum choices (e.g., ["NJ","NY","PA"]) or FK target type slug. |
| display_order | Integer | NOT NULL, default 0 | Sort position in forms and detail views. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |

### EntityInstance

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Unique identifier for the profile instance. |
| entity_type_id | UUID | FK -> EntityType, NOT NULL | The type this instance belongs to. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes record to a tenant. |
| person_id | UUID | FK -> Person, NULLABLE | Set when EntityType.is_person_subtype is true. Bridges to identity layer. |
| is_active | Boolean | NOT NULL, default true | Soft toggle for deactivation without deletion. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05. |

### AttributeValue

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Unique identifier for the value. |
| entity_instance_id | UUID | FK -> EntityInstance, NOT NULL | The instance this value belongs to. |
| entity_attribute_id | UUID | FK -> EntityAttribute, NOT NULL | The field definition this value satisfies. |
| value | Text | NULLABLE | Stored as text, cast by field_type at app layer. See ADR-005. |

**Unique constraint:** (entity_instance_id, entity_attribute_id). One value per field per instance.

**Design note:** AttributeValue intentionally omits `created_at`, `updated_at`, and `deleted_at`. Value changes are tracked exclusively through AuditLog entries on the parent EntityInstance. Values are overwritten in place. To delete a value, set it to null. There is no soft-delete mechanism on individual values.

### AttributeValue Type Casting Rules

The `value` column is always stored as text. The application layer casts and validates the value against the parent EntityAttribute's `field_type` before saving. The rules below are the authoritative mapping from field_type to Python type and validation constraints. This supersedes ADR-005 (pending) for MVP.

| field_type | Storage format | Python type after cast | Validation rules |
|---|---|---|---|
| text | Raw string | str | Max 10,000 characters. Empty string is not a valid substitute for null — use null to represent absence. |
| number | Decimal string, e.g. "123.45" | Decimal | Must parse as a valid decimal number. Max 10 significant digits, max 4 decimal places. No NaN, Infinity, or exponential notation. |
| date | ISO 8601 date string, e.g. "2026-04-15" | date | Must parse as YYYY-MM-DD. Must be a real calendar date. No time component. |
| bool | Lowercase string "true" or "false" | bool | Must be exactly the string "true" or "false". Any other value, including "True", "1", "yes", is rejected with HTTP 422. |
| enum | One of the string values listed in EntityAttribute.options | str | Must be an exact case-sensitive match to a value in the options array. The options array must be non-empty when field_type is enum. |
| fk | UUID string in standard 8-4-4-4-12 format | UUID | Must parse as a valid UUID v4. The referenced EntityInstance must exist, must not be soft-deleted, must belong to the same organization, and must match the EntityType slug specified in EntityAttribute.options. |
| jsonb | Valid JSON string | dict or list | Must parse as valid JSON. The top-level value must be an object (dict) or array (list). Scalar JSON values (strings, numbers) are not permitted at the top level. Max serialized size 100 KB. |

**Error behavior:** A value that fails its field_type validation returns HTTP 422 with error code `validation_error`. The error detail must identify the attribute name and the reason (e.g., "license_expiry: date value '2026-13-01' is not a valid calendar date").

---

## 3. Seed Data

On platform initialization, the following system types and attributes are created. These rows have is_system_type = true and cannot be deleted.

### System EntityTypes

| name | slug | is_system_type | is_person_subtype |
|---|---|---|---|
| provider | provider | true | true |
| client | client | true | true |
| admin | admin | true | true |

### Provider EntityAttributes

| name | display_name | field_type | is_required |
|---|---|---|---|
| license_number | License Number | text | true |
| license_state | License State | text | true |
| npi_number | NPI Number | text | false |
| specialty | Specialty | text | false |
| taxonomy_code | Taxonomy Code | text | false |

### Client EntityAttributes

| name | display_name | field_type | is_required |
|---|---|---|---|
| intake_status | Intake Status | enum | true |
| referral_source | Referral Source | text | false |
| emergency_contact_name | Emergency Contact Name | text | false |
| emergency_contact_phone | Emergency Contact Phone | text | false |
| onboarded_at | Onboarded At | date | false |

intake_status options: ["new", "in_progress", "complete"]

### Admin EntityAttributes

| name | display_name | field_type | is_required |
|---|---|---|---|
| department | Department | text | false |
| title | Title | text | false |

---

## 4. Business Rules

- BR-05 (Soft delete): EntityInstance includes a deleted_at column. API list endpoints must exclude records where deleted_at is not null. See ADR-006 for the full soft delete strategy across EAV tables.
- Multi-tenancy isolation: All EntityInstance queries must filter by organization_id. No query may return instances belonging to a different tenant. See ADR-011.
- Bridge rule validation: When a concrete table (e.g., Session) references an EntityInstance, the backend must verify two things: (1) the instance belongs to the expected EntityType (e.g., provider_instance_id must be a provider type), and (2) the instance belongs to the same Organization as the requesting user.
- System type protection: EntityTypes with is_system_type = true cannot be deleted or renamed. Their EntityAttributes can be extended (new fields added) but seed attributes cannot be removed.
- Required field enforcement: When creating or updating an EntityInstance, the backend must verify that all EntityAttributes with is_required = true on the instance's EntityType have a corresponding non-null AttributeValue.

---

## 5. Canonical Query Patterns

The primary cost of EAV is query complexity. The canonical join path for reading an instance's data is:

**Get all field values for one instance:** EntityInstance -> AttributeValue (join on entity_instance_id) -> EntityAttribute (join on entity_attribute_id for field names and types).

**Find all instances of a type matching a field value** (e.g., "all providers where license_state = NJ"): EntityInstance (filter by entity_type_id) -> AttributeValue (filter by value) -> EntityAttribute (filter by name = "license_state"). This requires a three-table join for every filtered query.

See ADR-002 for the performance strategy (denormalization, materialized views, or search index). This decision must be finalized before Phase 1 implementation begins.

---

## 6. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's Organization.

### EntityType management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entity-types | List all types for the org (system + custom) | entity_types.read |
| POST | /entity-types | Create a custom type | entity_types.write |
| GET | /entity-types/{slug} | Retrieve a type with its attributes | entity_types.read |
| PATCH | /entity-types/{slug} | Update a custom type (system types blocked) | entity_types.write |
| DELETE | /entity-types/{slug} | Delete a custom type (system types blocked) | entity_types.delete |

Note: Slug is used as the path parameter because it is the natural lookup key across the system — permission generation, instance routing, and bridge rule validation all reference entity types by slug. When a PATCH changes a custom type's slug, the request must use the old slug in the path.

### EntityAttribute management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entity-types/{slug}/attributes | List attributes for a type | entity_types.read |
| POST | /entity-types/{slug}/attributes | Add a field to a type | entity_types.write |
| PATCH | /entity-types/{slug}/attributes/{id} | Update a field definition | entity_types.write |
| DELETE | /entity-types/{slug}/attributes/{id} | Remove a field (seed attributes on system types blocked) | entity_types.delete |

### EntityInstance management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entities/{type_slug} | List instances of a type (paginated, filterable) | {type_slug}.read |
| POST | /entities/{type_slug} | Create an instance with attribute values | {type_slug}.write |
| GET | /entities/{type_slug}/{id} | Retrieve an instance with all values | {type_slug}.read |
| PATCH | /entities/{type_slug}/{id} | Update attribute values | {type_slug}.write |
| DELETE | /entities/{type_slug}/{id} | Soft delete an instance | {type_slug}.delete |

Note: Permissions are dynamically resolved based on the EntityType slug. When a practice creates a custom type with slug "nutritionist", the system generates permissions: nutritionist.read, nutritionist.write, nutritionist.delete. See ADR-004.

---

## 7. Implementation Constraints

- Type safety: FastAPI Pydantic schemas must use EntityAttribute.field_type to perform runtime validation of values before saving to AttributeValue. See ADR-005 for the decision on whether DB-level constraints supplement this.
- Audit trails: Every state-changing API call (POST, PATCH, DELETE) on EAV tables must generate a record in AuditLog per BR-07.
- Timestamps: All timestamps stored in UTC. Organization.timezone used for display only at the frontend layer.
- Unique slugs: EntityType.slug must be unique within an organization. System types use global slugs (provider, client, admin) that are reserved across all orgs.

---

## 8. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-001 | Core MVP data model | Defines the 26-table inventory and EAV + concrete hybrid decision. |
| ADR-002 | EAV query performance | Determines denormalization strategy for filtered queries. Blocks Phase 1. |
| ADR-005 | AttributeValue type safety | Decides DB constraints vs app-only casting. Blocks Phase 1. |
| ADR-006 | Soft delete strategy | Decides where deleted_at lives across EAV tables. Blocks Phase 1. |
| ADR-011 | Multi-tenancy isolation | Decides shared DB + org_id vs schema-per-tenant. Blocks Phase 1. |
| ADR-004 | Permission auto-generation | Decides how custom EntityTypes get RBAC permissions. Blocks SPEC-002. |

---

## 9. Test Table

Every business rule and constraint maps to at least one test case per SPEC-000 §5.

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| EntityType | `is_system_type` | `test_delete_system_entity_type_returns_409` | Integration | System type protection |
| EntityType | `is_system_type` | `test_rename_system_entity_type_returns_409` | Integration | System type protection |
| EntityType | `UNIQUE(organization_id, slug)` | `test_duplicate_slug_same_org_returns_409` | Integration | Unique slug constraint |
| EntityType | `slug` | `test_system_type_slug_reserved_across_orgs` | Integration | Global slug reservation |
| EntityAttribute | `is_system_type` parent | `test_delete_seed_attribute_on_system_type_returns_409` | Integration | Seed attribute protection |
| EntityAttribute | `is_system_type` parent | `test_add_attribute_to_system_type_succeeds` | Integration | System types are extensible |
| EntityInstance | `deleted_at` | `test_soft_deleted_instance_excluded_from_list` | Integration | BR-05 |
| EntityInstance | `organization_id` | `test_list_instances_filters_by_org` | Integration | Multi-tenancy isolation |
| EntityInstance | `organization_id` | `test_create_instance_cross_tenant_returns_403` | Integration | Multi-tenancy isolation |
| EntityInstance | `entity_type_id` bridge | `test_session_with_non_provider_instance_returns_422` | Integration | Bridge rule validation |
| EntityInstance | `entity_type_id` bridge | `test_session_with_wrong_org_instance_returns_422` | Integration | Bridge rule + org check |
| AttributeValue | `UNIQUE(entity_instance_id, entity_attribute_id)` | `test_duplicate_value_same_instance_attribute_returns_409` | Integration | Unique constraint |
| AttributeValue | `is_required` parent | `test_create_instance_missing_required_field_returns_422` | Integration | Required field enforcement |
| AttributeValue | `field_type` | `test_create_value_wrong_type_returns_422` | Integration | Type validation (ADR-005) |
| AttributeValue | `field_type` enum | `test_create_enum_value_not_in_options_returns_422` | Integration | Enum option validation |
| EntityType | POST auto-permissions | `test_create_custom_type_generates_three_permissions` | Integration | ADR-004 auto-generation |
| All EAV tables | all state changes | `test_create_entity_type_writes_audit_log` | Integration | BR-07 |
| All EAV tables | all state changes | `test_update_instance_writes_audit_log` | Integration | BR-07 |
| All EAV tables | all state changes | `test_delete_instance_writes_audit_log` | Integration | BR-07 |

---

## 10. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Lean table definitions, basic business rules. |
| 0.2.0 | Full field definitions for all 5 tables. Added seed data section, API surface, canonical query patterns, implementation constraints. Added missing fields: Organization (npi, timezone, etc.), EntityType (slug, is_system_type, is_person_subtype, organization_id), EntityAttribute (is_required, options, display_order, display_name, field_type expanded), EntityInstance (person_id, is_active, deleted_at), AttributeValue unique constraint. |
| 0.3.0 | Changed EntityType and EntityAttribute path parameters from {id}/{type_id} to {slug} throughout API surface. Added slug-change note for PATCH. Aligns with SPEC-007 endpoint inventory and system-wide slug-based lookup convention. |
| 0.4.0 | Updated ADR-001 table count from 24 to 26 (DocumentType and ConsentType added in SPEC-000 v1.1.0). Added design note to AttributeValue clarifying intentional omission of timestamps — value changes tracked through AuditLog on parent EntityInstance. |
| 0.5.0 | Added Test Table (Section 9) with 19 test cases covering system type protection, slug uniqueness, multi-tenancy isolation, bridge rule validation, required field enforcement, type validation, enum validation, ADR-004 auto-permission generation, and BR-07 audit logging. |
| 0.6.0 | Added AttributeValue Type Casting Rules table to Section 2. Defines storage format, Python type, and validation constraints for all 7 field_type values (text, number, date, bool, enum, fk, jsonb). Supersedes ADR-005 pending for MVP. Includes error behavior specification (HTTP 422 with attribute name and reason). |