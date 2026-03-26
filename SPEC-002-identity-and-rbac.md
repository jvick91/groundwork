# SPEC-002: Identity and RBAC

**Status:** Draft
**Version:** 0.2.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Human identity, role assignment, permission grants, and access enforcement across all domains.

---

## 1. Domain Overview

This domain separates who a person is from what they can do. A person can have one or more profiles in the EAV layer and one or more roles in the identity layer. Permissions are granted to roles, not directly to people.

The system must support two independent concepts:

- EntityType defines profile shape (for example provider, client, or admin profile data).
- Role defines permission scope (for example therapist, supervisor, or practice admin).

This separation allows a single person to operate in multiple capacities without duplicate identity records.

### Tables owned

- Person: Canonical identity record for a human. Exists independent of any tenant.
- PersonRole: Assignment of a person to a role in one organization, optionally bound to a specific EntityInstance profile.
- Role: Named role with optional parent role for hierarchy and a primary_domain linking to EntityType family.
- Permission: A single action right, such as clients.read or billing.write.
- RolePermission: Junction table that grants permissions to roles, with optional row-level conditions.

---

## 2. Data Model Detail

### Person

Person is tenant-independent. A human exists once regardless of how many organizations they belong to. Tenant scoping is enforced at the PersonRole level.

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for the person. |
| auth_subject | String | UNIQUE, NULLABLE | Stable external auth subject from Auth0. Null for personas that do not authenticate (clients, guardians during MVP). See ADR-007. |
| first_name | String | NOT NULL | Legal first name. |
| last_name | String | NOT NULL | Legal last name. |
| email | String | NOT NULL, UNIQUE | Primary email address for communication and login mapping. |
| phone | String | NULLABLE | Primary phone number. |
| date_of_birth | Date | NULLABLE | Date of birth. PHI-bearing field, excluded from logs per BR-08. |
| is_active | Boolean | NOT NULL, default true | Soft toggle for account suspension without deletion. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

Design note: Person has no organization_id. A therapist who works at two practices has one Person row and two PersonRole rows (one per org). Duplicating Person per tenant would defeat the polymorphic identity model.

### PersonRole

PersonRole is the three-way binding that connects identity, permissions, and profile: Person (who you are) + Role (what you can do) + EntityInstance (your profile data in the EAV layer).

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for the assignment record. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant boundary for the role assignment. This is where org scoping is enforced. |
| person_id | UUID | FK -> Person, NOT NULL | Person receiving the role. |
| role_id | UUID | FK -> Role, NOT NULL | Role granted to the person. |
| entity_instance_id | UUID | FK -> EntityInstance, NULLABLE | Profile scope. See entity_instance_id rules below. |
| assigned_at | Timestamp | NOT NULL, default now | When the role was granted. |
| assigned_by_person_id | UUID | FK -> Person, NULLABLE | Which person granted the role. Null for system-seeded assignments. |
| revoked_at | Timestamp | NULLABLE | When the role was revoked. Null means active. |

**entity_instance_id rules:**

- Required when the role's primary_domain maps to a person_subtype EntityType. A therapist PersonRole must point to a provider EntityInstance. A client PersonRole must point to a client EntityInstance.
- The referenced EntityInstance must match the expected EntityType for the role's primary_domain (e.g., a role with primary_domain = provider must reference an EntityInstance of type "provider").
- The referenced EntityInstance must belong to the same organization_id as the PersonRole.
- Nullable only for system_admin roles or other roles where no EAV profile is needed.

**Unique constraint:** Partial unique index: `UNIQUE (organization_id, person_id, role_id, entity_instance_id) WHERE revoked_at IS NULL`. A person cannot hold duplicate active copies of the same scoped role. Revoked rows are historical and do not conflict.

### Role

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for role. |
| organization_id | UUID | FK -> Organization, NULLABLE | Null for system roles, set for practice-defined custom roles. |
| name | String | NOT NULL | Human-readable role name. |
| slug | String | NOT NULL | Stable machine identifier (e.g., therapist, practice_admin). |
| primary_domain | Enum | NOT NULL | One of: admin, provider, client. Maps to the EntityType family this role belongs to. |
| parent_role_id | UUID | FK -> Role, NULLABLE | Enables hierarchy and inheritance. |
| is_system_role | Boolean | NOT NULL, default false | Protected seed role that cannot be deleted. |
| description | Text | NULLABLE | Human-readable purpose of the role. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time. |

**Unique constraint:** slug is unique within an organization. System role slugs are globally reserved across all orgs.

**Hierarchy invariant:** A child role must have the same primary_domain as its parent role. A custom role with primary_domain = provider cannot be parented under an admin-domain role. This is enforced at the application layer on create and update.

### Permission

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for permission. |
| organization_id | UUID | FK -> Organization, NULLABLE | Null for system permissions, set for custom tenant permissions. |
| resource_slug | String | NOT NULL | Target resource or entity type slug (e.g., clients, sessions, billing, provider). |
| action | String | NOT NULL | Allowed operation. One of: read, write, delete, sign, cosign, manage, assign, export. |
| slug | String | NOT NULL | Canonical permission key built as resource_slug.action (e.g., clients.read). |
| description | Text | NULLABLE | Human-readable explanation of permission intent. |
| is_system_permission | Boolean | NOT NULL, default false | True for protected seed permissions. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |

**Unique constraint:** slug is unique within an organization. System permission slugs are globally reserved.

**Naming convention (contract with SPEC-001):** Permission slugs follow the pattern `{resource_slug}.{action}`. The resource_slug matches an EntityType slug for entity-scoped permissions (e.g., provider.read, client.write) or a domain keyword for cross-cutting permissions (e.g., billing.read, settings.write). Both SPEC-001 and SPEC-002 must follow this convention.

### RolePermission

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for grant. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant boundary for grant. |
| role_id | UUID | FK -> Role, NOT NULL | Role receiving permission. |
| permission_id | UUID | FK -> Permission, NOT NULL | Permission being granted. |
| conditions | JSONB | NULLABLE | Row-level filtering rules. See row-level filtering section below. |
| granted_at | Timestamp | NOT NULL, default now | When grant became active. |
| granted_by_person_id | UUID | FK -> Person, NULLABLE | Who granted this permission. Null for system-seeded grants. |
| revoked_at | Timestamp | NULLABLE | Null means active grant. |

**Unique constraint:** Partial unique index: `UNIQUE (organization_id, role_id, permission_id) WHERE revoked_at IS NULL`.

---

## 3. Seed Data

On platform initialization, the system seeds baseline roles, permissions, and role-permission grants. Seed rows have is_system_role = true or is_system_permission = true and cannot be deleted.

### Seed roles

| Slug | Domain | Parent | Notes |
|---|---|---|---|
| admin | admin | none | Primary role root for operations. |
| practice_admin | admin | admin | Practice-level operational control. |
| system_admin | admin | admin | Platform-level and tenant management. |
| biller | admin | admin | Billing and claim-related operations. |
| receptionist | admin | admin | Scheduling and intake-focused operations. |
| provider | provider | none | Primary role root for clinical staff. |
| therapist | provider | provider | Clinical care and note authoring. |
| supervisor | provider | provider | Therapist permissions plus co-signing. |
| prescriber | provider | provider | Therapist permissions plus prescribing (future). |
| client | client | none | Primary role root for care recipients. |
| guardian | client | client | Dependent-scoped client portal access (post-MVP). |

### Seed permissions

| Slug | Resource | Action | Description |
|---|---|---|---|
| clients.read | clients | read | Read client records allowed by scope. |
| clients.write | clients | write | Create or update client records allowed by scope. |
| clients.delete | clients | delete | Soft delete client records. |
| sessions.read | sessions | read | Read session records. |
| sessions.write | sessions | write | Create, update, or cancel sessions. |
| notes.read | notes | read | Read clinical notes. |
| notes.write | notes | write | Draft and edit unsigned notes. |
| notes.sign | notes | sign | Sign notes as author. |
| notes.cosign | notes | cosign | Co-sign notes as supervisor. |
| billing.read | billing | read | Read invoices, payments, and coverage records. |
| billing.write | billing | write | Create and update billing records. |
| settings.read | settings | read | Read organization configuration. |
| settings.write | settings | write | Update organization configuration. |
| people.read | people | read | Read person identity records. |
| people.write | people | write | Create or update person records. |
| people.delete | people | delete | Soft delete person records. |
| roles.read | roles | read | List and view roles and permissions. |
| roles.write | roles | write | Create or update custom roles and permission grants. |
| roles.delete | roles | delete | Delete custom roles. |
| roles.assign | roles | assign | Assign or revoke roles on people. |
| entity_types.read | entity_types | read | List and view entity types and attributes. |
| entity_types.write | entity_types | write | Create or update custom entity types. |
| entity_types.delete | entity_types | delete | Delete custom entity types. |
| tenants.manage | tenants | manage | Create, suspend, or update tenant organizations. |
| system.configure | system | manage | Platform-level operational configuration. |

### Seed role-permission matrix

Y = granted. Blank = not granted. Child roles inherit all parent grants (inheritance shown as "inh").

| Permission | admin | practice_admin | system_admin | biller | receptionist | provider | therapist | supervisor | prescriber | client | guardian |
|---|---|---|---|---|---|---|---|---|---|---|---|
| clients.read | Y | inh | inh | | Y | Y | inh | inh | inh | | |
| clients.write | Y | inh | inh | | Y | Y | inh | inh | inh | | |
| clients.delete | Y | inh | inh | | | | | | | | |
| sessions.read | Y | inh | inh | | Y | Y | inh | inh | inh | | |
| sessions.write | Y | inh | inh | | Y | Y | inh | inh | inh | | |
| notes.read | | | | | | Y | inh | inh | inh | | |
| notes.write | | | | | | Y | inh | inh | inh | | |
| notes.sign | | | | | | | Y | inh | inh | | |
| notes.cosign | | | | | | | | Y | | | |
| billing.read | Y | inh | inh | inh | | | | | | | |
| billing.write | Y | inh | inh | inh | | | | | | | |
| settings.read | Y | inh | inh | | | | | | | | |
| settings.write | Y | inh | inh | | | | | | | | |
| people.read | Y | inh | inh | | Y | | | | | | |
| people.write | Y | inh | inh | | | | | | | | |
| people.delete | Y | inh | inh | | | | | | | | |
| roles.read | Y | inh | inh | | | | | | | | |
| roles.write | Y | inh | inh | | | | | | | | |
| roles.delete | Y | inh | inh | | | | | | | | |
| roles.assign | Y | inh | inh | | | | | | | | |
| entity_types.read | Y | inh | inh | | | | | | | | |
| entity_types.write | | | Y | | | | | | | | |
| entity_types.delete | | | Y | | | | | | | | |
| tenants.manage | | | Y | | | | | | | | |
| system.configure | | | Y | | | | | | | | |

Notes on the matrix:

- admin is the root. practice_admin, system_admin, biller, and receptionist inherit from it via parent_role_id.
- provider is the root for clinical. therapist, supervisor, and prescriber inherit from it.
- "inh" means the permission comes from the parent chain, not a direct grant. The seed migration only creates direct grants (Y). Inheritance is resolved at runtime.
- Biller inherits admin's billing grants but does not get clients.write, sessions.write, or any clinical permissions. The biller role only receives the grants its parent (admin) has that fall within billing scope. This means biller must NOT inherit all admin grants. See inheritance model below.
- Receptionist gets clients.read, clients.write, sessions.read, sessions.write, and people.read as direct grants. It does NOT inherit admin's full permission set. See inheritance model below.

### Inheritance model clarification

The matrix above reveals a design tension: if biller and receptionist inherit everything from admin, they get permissions they shouldn't have (billers shouldn't manage people, receptionists shouldn't manage billing). Two options:

**Option A (selective inheritance):** Child roles inherit all parent permissions. Biller and receptionist are NOT children of admin. They are standalone roles with primary_domain = admin but parent_role_id = null. Their permissions are direct grants only. The admin hierarchy is: admin -> practice_admin, admin -> system_admin. Biller and receptionist are siblings in the admin domain but not in the admin hierarchy.

**Option B (full inheritance + deny rules):** Keep the hierarchy but add a deny mechanism to RolePermission. This adds complexity.

This spec recommends Option A. The updated seed roles table becomes:

| Slug | Domain | Parent | Notes |
|---|---|---|---|
| admin | admin | none | Primary role root. |
| practice_admin | admin | admin | Inherits all admin grants. |
| system_admin | admin | admin | Inherits all admin grants + platform-level. |
| biller | admin | none | Standalone. Direct billing grants only. |
| receptionist | admin | none | Standalone. Direct scheduling and intake grants only. |
| provider | provider | none | Primary role root for clinical staff. |
| therapist | provider | provider | Inherits all provider grants + notes.sign. |
| supervisor | provider | provider | Inherits all provider grants + notes.sign + notes.cosign. |
| prescriber | provider | provider | Inherits all provider grants + notes.sign + prescriptions (future). |
| client | client | none | Primary role root for care recipients. |
| guardian | client | client | Inherits client grants, scoped to dependent. |

Under Option A, the corrected matrix for biller and receptionist uses direct grants (Y), not inheritance:

| Permission | biller | receptionist |
|---|---|---|
| clients.read | | Y |
| clients.write | | Y |
| sessions.read | | Y |
| sessions.write | | Y |
| billing.read | Y | |
| billing.write | Y | |
| people.read | | Y |

---

## 4. Business Rules

- BR-06 (RBAC enforcement): Every protected API endpoint must resolve effective permissions from the authenticated person's active PersonRole rows and their associated RolePermission grants.
- Role union rule: If a person has multiple active roles, effective permissions are the union across those roles and inherited parent role permissions.
- Tenant isolation rule: PersonRole, Role, Permission, and RolePermission lookups must always filter by organization_id or system scope, and must never cross tenant boundaries. Person is tenant-independent; tenant scoping is enforced through PersonRole.organization_id.
- Hierarchy invariant: A child role must have the same primary_domain as its parent role. Enforced on create and update.
- Hierarchy inheritance rule: Child roles inherit all permissions from their parent roles. Inheritance is resolved at runtime by walking the parent_role_id chain.
- Assignment integrity rule: A PersonRole assignment may only reference a role that belongs to the same organization or is a system role. The entity_instance_id must reference an EntityInstance of the correct EntityType for the role's primary_domain, within the same organization.
- Revocation rule: Revoked PersonRole rows (revoked_at is not null) and revoked RolePermission rows immediately remove access from authorization decisions.
- Soft delete rule: Soft-deleted Person rows (deleted_at is not null) must not authenticate into active application access paths.
- Auth subject rule: Only Person rows with a non-null auth_subject can authenticate via Auth0. Persons without auth_subject (clients, guardians during MVP) cannot log in.

---

## 5. Authorization Resolution Model

Authorization is evaluated in four ordered steps:

1. Identify the authenticated person via Auth0 subject (match auth_subject on Person table). Reject if Person.is_active = false or Person.deleted_at is not null.
2. Load active PersonRole rows for the request's organization context (filter by organization_id, revoked_at IS NULL).
3. Expand role hierarchy by walking parent_role_id chain on each active role. Collect all RolePermission grants (where revoked_at IS NULL) for every role in the expanded set.
4. Evaluate whether the requested permission slug exists in the effective permission set. If RolePermission.conditions is not null, evaluate row-level filter against the requested resource.

Access decisions must be deterministic and auditable. Denied requests return HTTP 403 with the standard error response defined in SPEC-007.

---

## 6. Row-Level Filtering

Row-level filtering controls which specific records a role can access within a permitted resource. It is stored in RolePermission.conditions as JSONB.

### Condition structure

Conditions are evaluated as conjunctive (AND) filters applied to the query. Example:

A therapist's `clients.read` grant has conditions: `{"scope": "own_clients"}`. The backend interprets this as: "filter client EntityInstances to only those where the therapist's EntityInstance is the assigned provider."

A practice_admin's `clients.read` grant has conditions: `null`. Null conditions mean unrestricted access within the organization.

### Supported condition types for MVP

| Condition key | Meaning | Applied to |
|---|---|---|
| scope: own_clients | Filter to clients assigned to the requesting provider instance. | clients.read, clients.write |
| scope: own_sessions | Filter to sessions where the requesting provider is the conductor. | sessions.read, sessions.write |
| scope: own_notes | Filter to notes authored by the requesting provider. | notes.read, notes.write |
| scope: own_profile | Filter to the requesting person's own Person and EntityInstance records. | Post-MVP client portal. |
| null | Unrestricted within organization. | Admin and practice_admin grants. |

### Seed conditions on role-permission grants

| Role | Permission | Conditions |
|---|---|---|
| provider (and children) | clients.read | {"scope": "own_clients"} |
| provider (and children) | clients.write | {"scope": "own_clients"} |
| provider (and children) | sessions.read | {"scope": "own_sessions"} |
| provider (and children) | sessions.write | {"scope": "own_sessions"} |
| provider (and children) | notes.read | {"scope": "own_notes"} |
| provider (and children) | notes.write | {"scope": "own_notes"} |
| admin | all grants | null (unrestricted) |
| receptionist | clients.read | null (all clients for intake) |
| receptionist | sessions.read | null (all sessions for scheduling) |
| biller | billing.read | null (all billing records) |

---

## 7. SPEC-001 Integration Contract

SPEC-001 (EAV Data Platform) and SPEC-002 share three integration points. Both specs must remain consistent on these contracts.

### Permission naming convention

Permission slugs follow the pattern `{resource_slug}.{action}`. When SPEC-001 defines an API endpoint requiring a permission, the resource_slug must match either an EntityType slug (e.g., provider, client, nutritionist) or a domain keyword (e.g., billing, settings). The action must be one of: read, write, delete, sign, cosign, manage, assign, export. Both specs reference this convention.

### Auto-generation trigger

When SPEC-001's `POST /entity-types` creates a new custom EntityType with slug "nutritionist", three Permission rows must be created automatically: nutritionist.read, nutritionist.write, nutritionist.delete. These permissions have organization_id set to the creating org, is_system_permission = false, and are immediately available for assignment via RolePermission. The auto-generation logic is defined in ADR-004.

### Row-level filtering integration

SPEC-001's `GET /entities/{type_slug}` returns EntityInstance records. When the requesting user's RolePermission grant for `{type_slug}.read` includes a conditions JSONB, SPEC-001's query layer must apply the filter. The condition evaluation logic is owned by SPEC-002 but executed within SPEC-001's query path. The supported condition types are defined in section 6 of this spec.

---

## 8. API Surface

All endpoints require a valid Auth0 JWT unless explicitly marked.

### Person management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /people | List people in organization (via PersonRole org scope) | people.read |
| POST | /people | Create person identity record | people.write |
| GET | /people/{id} | Retrieve person profile | people.read |
| PATCH | /people/{id} | Update person identity fields | people.write |
| DELETE | /people/{id} | Soft delete person | people.delete |

### Role and permission management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /roles | List system and organization roles | roles.read |
| POST | /roles | Create organization custom role | roles.write |
| PATCH | /roles/{id} | Update role metadata or parent (hierarchy invariant enforced) | roles.write |
| DELETE | /roles/{id} | Delete custom role (system roles blocked) | roles.delete |
| GET | /permissions | List available permissions | permissions.read |
| POST | /roles/{id}/permissions | Grant permission to role | roles.write |
| DELETE | /roles/{id}/permissions/{permission_id} | Revoke permission from role | roles.write |

### Person role assignment

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /people/{id}/roles | List active and historical role assignments | roles.read |
| POST | /people/{id}/roles | Assign role to person (entity_instance_id rules enforced) | roles.assign |
| DELETE | /people/{id}/roles/{person_role_id} | Revoke role assignment (sets revoked_at) | roles.assign |

### Auth self-inspection

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /auth/me | Current person profile, active roles, and org context | authenticated |
| GET | /auth/me/permissions | Effective permission list for current session | authenticated |

### /auth/me response shape

The response includes person identity, active roles with their EntityInstance bindings, and the current organization context.

| Field | Type | Description |
|---|---|---|
| person.id | UUID | Person primary key. |
| person.first_name | String | First name. |
| person.last_name | String | Last name. |
| person.email | String | Email address. |
| organization.id | UUID | Current org context. |
| organization.name | String | Practice name. |
| roles | Array | Active PersonRole records. |
| roles[].role_slug | String | Role machine identifier. |
| roles[].role_name | String | Role display name. |
| roles[].primary_domain | Enum | admin, provider, or client. |
| roles[].entity_instance_id | UUID, nullable | Bound profile instance. |
| effective_permissions | Array of String | Flattened list of permission slugs (e.g., ["clients.read", "notes.sign"]). |

### /auth/me/permissions response shape

| Field | Type | Description |
|---|---|---|
| permissions | Array | Detailed permission grants. |
| permissions[].slug | String | Permission key (e.g., clients.read). |
| permissions[].resource | String | Resource slug. |
| permissions[].action | String | Action slug. |
| permissions[].conditions | JSONB, nullable | Row-level filter if present. |

---

## 9. Implementation Constraints

- Auth provider integration: JWT validation and subject resolution must follow ADR-007. The auth middleware extracts auth_subject from the JWT, queries Person, loads PersonRoles, and attaches the resolved identity to the request context.
- Permission auto-generation: EntityType-driven permissions for custom types must follow ADR-004, so new practice-defined types gain RBAC support automatically.
- Session-to-role consistency: Authorization checks for scheduling and clinical actions must align with session foreign key semantics in ADR-003.
- Audit requirements: Every role assignment, revocation, role-permission grant, and role-permission revocation is a state-changing action and must write an AuditLog entry per BR-07.
- PHI-safe logging: Authorization failures and audit metadata must never include PHI fields, per BR-08.
- Person query scoping: Since Person has no organization_id, the `GET /people` endpoint must join through PersonRole to find people with active roles in the requesting user's organization. A person with no PersonRole in the org is invisible to that org.

---

## 10. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-004 | Permission auto-generation | Defines how dynamic EntityType permissions are created and maintained. Blocks full RBAC rollout. |
| ADR-007 | Auth provider and session management | Defines Auth0 integration, JWT validation, and person identity resolution. |
| ADR-011 | Multi-tenancy isolation | Defines tenant boundary strategy and authorization query scope. |
| ADR-003 | Session FK semantics | Ensures role-based session actors map correctly to identity and entity instances. |
| ADR-006 | Soft delete strategy | Defines delete semantics for Person and assignment lifecycle records. |

---

## 11. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full identity and RBAC ownership, model definitions, seed roles and permissions, authorization flow, API surface, business rules, and ADR mapping. |
| 0.2.0 | Removed organization_id from Person (tenant scoping via PersonRole). Made auth_subject nullable for non-authenticating personas. Documented entity_instance_id rules on PersonRole. Specified partial unique indexes for PersonRole and RolePermission. Added primary_domain hierarchy invariant. Added role-permission seed matrix. Added missing seed permissions (people.*, roles.*, entity_types.*). Added row-level filtering section with conditions JSONB on RolePermission. Added SPEC-001 integration contract. Added /auth/me and /auth/me/permissions response shapes. Resolved biller/receptionist inheritance model (Option A: standalone roles, not admin children). Added auth subject rule for non-authenticating personas. Added Person query scoping constraint. |