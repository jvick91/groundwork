# SPEC-001: EAV Data Platform

**Status:** Draft  
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)  
**Scope:** Core data flexibility, multi-tenancy, and persona metadata.

---

## 1. Domain Overview
The EAV (Entity-Attribute-Value) system is the architectural foundation that allows Groundwork to remain flexible without constant database migrations. While transactional events (sessions, notes) use concrete tables, the descriptive data for "Personas" (Providers, Clients, Admins) is stored here.

### Tables Owned
* **Organization:** The root tenant record.
* **EntityType:** Defines the "template" (e.g., Provider, Client).
* **EntityAttribute:** Defines specific fields (e.g., NPI Number, License State).
* **EntityInstance:** An individual record of a type (e.g., Jane Doe's Provider Profile).
* **AttributeValue:** The specific data points for an instance.

---

## 2. Data Model Detail

| Table | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| **Organization** | `id` | UUID (PK) | Primary key for the tenant. |
| | `name` | String | Legal name of the practice. |
| **EntityType** | `id` | UUID (PK) | Unique identifier for the type. |
| | `name` | String | Human name (e.g., "provider", "client", "admin"). |
| **EntityAttribute** | `id` | UUID (PK) | Unique identifier for the field. |
| | `entity_type_id` | UUID (FK) | References `EntityType`. |
| | `name` | String | Machine name (e.g., `license_number`). |
| | `data_type` | Enum | Validates value as string, int, bool, or date. |
| **EntityInstance** | `id` | UUID (PK) | Unique identifier for the profile instance. |
| | `entity_type_id` | UUID (FK) | References `EntityType`. |
| | `org_id` | UUID (FK) | Scopes record to an `Organization`. |
| **AttributeValue** | `id` | UUID (PK) | Unique identifier for the value. |
| | `instance_id` | UUID (FK) | References `EntityInstance`. |
| | `attribute_id` | UUID (FK) | References `EntityAttribute`. |
| | `value` | Text | The data stored as text (cast by app layer). |

---

## 3. Business Rules
* **BR-05 (Soft Delete):** All tables must include a `deleted_at` column. API endpoints must exclude these records by default.
* **Multi-Tenancy Isolation:** All `EntityInstance` queries must include an `org_id` filter to prevent cross-tenant data leaks.
* **Bridge Rule Validation:** When a concrete table (e.g., `Session`) references an `EntityInstance`, the backend must verify the instance belongs to the correct `EntityType` (e.g., checking that the conductor is a "provider" type).

---

## 4. Implementation Constraints
* **Type Safety:** FastAPI Pydantic schemas must use the `EntityAttribute.data_type` to perform runtime validation of values before they are saved to `AttributeValue`.
* **Audit Trails:** Every state-changing API call (POST/PATCH/DELETE) on EAV tables must generate a record in the `AuditLog`.

---

## 5. Relevant ADRs
* **ADR-001:** Core MVP data model
* **ADR-002:** EAV query performance
* **ADR-005:** AttributeValue type safety
* **ADR-011:** Multi-tenancy isolation