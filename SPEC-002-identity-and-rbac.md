# SPEC-002: Identity and RBAC

**Status:** Draft
**Version:** 0.1.0
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

- Person: Canonical identity record for a human.
- PersonRole: Assignment of a person to a role in one organization.
- Role: Named role with optional parent role for hierarchy.
- Permission: A single action right, such as clients.read or billing.write.
- RolePermission: Junction table that grants permissions to roles.

---

## 2. Data Model Detail

### Person

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for the person. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant boundary for the person identity. |
| auth_subject | String | UNIQUE, NOT NULL | Stable external auth subject from Auth0. |
| first_name | String | NOT NULL | Legal first name. |
| last_name | String | NOT NULL | Legal last name. |
| email | String | NOT NULL | Primary email address for communication and login mapping. |
| phone | String | NULLABLE | Primary phone number. |
| date_of_birth | Date | NULLABLE | Date of birth, PHI-bearing. |
| is_active | Boolean | NOT NULL, default true | Soft toggle for account suspension without deletion. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

### PersonRole

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for the assignment record. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant boundary for the role assignment. |
| person_id | UUID | FK -> Person, NOT NULL | Person receiving the role. |
| role_id | UUID | FK -> Role, NOT NULL | Role granted to the person. |
| entity_instance_id | UUID | FK -> EntityInstance, NULLABLE | Optional profile scope when role is tied to a specific profile instance. |
| assigned_at | Timestamp | NOT NULL, default now | When the role was granted. |
| assigned_by_person_id | UUID | FK -> Person, NULLABLE | Which person granted the role. |
| revoked_at | Timestamp | NULLABLE | When the role was revoked. Null means active. |

**Unique constraint:** (organization_id, person_id, role_id, entity_instance_id, revoked_at-is-null active set). A person cannot hold duplicate active copies of the same scoped role.

### Role

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for role. |
| organization_id | UUID | FK -> Organization, NULLABLE | Null for system roles, set for practice-defined custom roles. |
| name | String | NOT NULL | Human-readable role name. |
| slug | String | NOT NULL | Stable machine identifier (for example therapist, practice_admin). |
| primary_domain | Enum | NOT NULL | One of: admin, provider, client. |
| parent_role_id | UUID | FK -> Role, NULLABLE | Enables hierarchy and inheritance. |
| is_system_role | Boolean | NOT NULL, default false | Protected seed role that cannot be deleted. |
| description | Text | NULLABLE | Human-readable purpose of the role. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time. |

**Unique constraint:** slug is unique within an organization; system role slugs are globally reserved.

### Permission

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for permission. |
| organization_id | UUID | FK -> Organization, NULLABLE | Null for system permissions, set for custom tenant permissions. |
| resource_slug | String | NOT NULL | Target resource or entity type slug (for example clients, sessions, billing, provider). |
| action | String | NOT NULL | Allowed operation (for example read, write, delete, sign, cosign, manage). |
| slug | String | NOT NULL | Canonical permission key built as resource.action. |
| description | Text | NULLABLE | Human-readable explanation of permission intent. |
| is_system_permission | Boolean | NOT NULL, default false | True for protected seed permissions. |
| created_at | Timestamp | NOT NULL, default now | Record creation time. |

**Unique constraint:** slug is unique within an organization; system permission slugs are globally reserved.

### RolePermission

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key for grant. |
| organization_id | UUID | FK -> Organization, NOT NULL | Tenant boundary for grant. |
| role_id | UUID | FK -> Role, NOT NULL | Role receiving permission. |
| permission_id | UUID | FK -> Permission, NOT NULL | Permission being granted. |
| granted_at | Timestamp | NOT NULL, default now | When grant became active. |
| granted_by_person_id | UUID | FK -> Person, NULLABLE | Who granted this permission. |
| revoked_at | Timestamp | NULLABLE | Null means active grant. |

**Unique constraint:** (organization_id, role_id, permission_id, revoked_at-is-null active set).

---

## 3. Seed Data

On platform initialization, the system seeds baseline roles and permissions. Seed rows are system-managed and cannot be deleted.

### Seed Roles

| Role slug | Domain | Parent role | Notes |
|---|---|---|---|
| admin | admin | none | Primary role root for operations. |
| practice_admin | admin | admin | Practice-level operational control. |
| system_admin | admin | admin | Platform-level and tenant management capabilities. |
| biller | admin | admin | Billing and claim-related operations. |
| receptionist | admin | admin | Scheduling and intake-focused operations. |
| provider | provider | none | Primary role root for clinical staff. |
| therapist | provider | provider | Clinical care and note authoring. |
| supervisor | provider | provider | Therapist permissions plus co-signing. |
| prescriber | provider | provider | Therapist permissions plus prescribing domain (future). |
| client | client | none | Primary role root for care recipients. |
| guardian | client | client | Dependent-scoped client portal access (post-MVP). |

### Seed Permissions (representative baseline)

| Permission slug | Meaning |
|---|---|
| clients.read | Read client records allowed by scope. |
| clients.write | Create or update client records allowed by scope. |
| sessions.read | Read session records. |
| sessions.write | Create, update, or cancel sessions. |
| notes.read | Read clinical notes. |
| notes.write | Draft and edit unsigned notes. |
| notes.sign | Sign notes as author. |
| notes.cosign | Co-sign notes as supervisor. |
| billing.read | Read invoices, payments, and coverage records. |
| billing.write | Create and update billing records. |
| settings.read | Read organization configuration. |
| settings.write | Update organization configuration. |
| tenants.manage | Create, suspend, or update tenant organizations. |
| system.configure | Platform-level operational configuration. |

The exact matrix of role-to-permission mappings is owned here and implemented as seed migration data.

---

## 4. Business Rules

- BR-06 (RBAC enforcement): Every protected API endpoint must resolve effective permissions from the authenticated person's active roles and role-permission grants.
- Role union rule: If a person has multiple active roles, effective permissions are the union across those roles and inherited parent roles.
- Tenant isolation rule: Person, PersonRole, Role, Permission, and RolePermission lookups must always filter by organization_id or system scope, and must never cross tenant boundaries.
- Hierarchy inheritance rule: Child roles inherit all permissions from parent roles unless explicitly revoked by policy design.
- Assignment integrity rule: A PersonRole assignment may only reference a role that belongs to the same organization or a system role valid for that organization.
- Revocation rule: Revoked PersonRole rows and revoked RolePermission rows immediately remove access from authorization decisions.
- Soft delete rule: Soft-deleted Person rows must not authenticate into active application access paths.

---

## 5. Authorization Resolution Model

Authorization is evaluated in four ordered steps:

1. Identify the authenticated person via Auth0 subject.
2. Load active PersonRole rows for the organization context.
3. Expand role hierarchy to include inherited parent role permissions.
4. Evaluate whether requested permission slug exists in the effective set.

Access decisions must be deterministic and auditable. Denied requests should return a standardized authorization error defined by SPEC-007.

---

## 6. API Surface

All endpoints require a valid Auth0 JWT unless explicitly marked public by platform policy.

### Person management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /people | List people in organization | people.read |
| POST | /people | Create person identity record | people.write |
| GET | /people/{id} | Retrieve person profile | people.read |
| PATCH | /people/{id} | Update person identity fields | people.write |
| DELETE | /people/{id} | Soft delete person | people.delete |

### Role and permission management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /roles | List system and organization roles | roles.read |
| POST | /roles | Create organization custom role | roles.write |
| PATCH | /roles/{id} | Update role metadata or parent | roles.write |
| DELETE | /roles/{id} | Delete custom role (system role blocked) | roles.delete |
| GET | /permissions | List available permissions | permissions.read |
| POST | /roles/{id}/permissions | Grant permission to role | roles.write |
| DELETE | /roles/{id}/permissions/{permission_id} | Revoke permission from role | roles.write |

### Person role assignment

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /people/{id}/roles | List active and historical role assignments | roles.read |
| POST | /people/{id}/roles | Assign role to person | roles.assign |
| DELETE | /people/{id}/roles/{person_role_id} | Revoke role assignment | roles.assign |

### Authz self-inspection

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /auth/me | Current person profile and role summary | authenticated |
| GET | /auth/me/permissions | Effective permission list for current session | authenticated |

---

## 7. Implementation Constraints

- Auth provider integration: JWT validation and subject resolution must follow ADR-007.
- Permission generation: EntityType-driven permissions for custom types must follow ADR-004, so new practice-defined types gain RBAC support automatically.
- Session-to-role consistency: Authorization checks for scheduling and clinical actions must align with session foreign key semantics in ADR-003.
- Audit requirements: Every role assignment, revocation, and role-permission change is a state-changing action and must write an AuditLog entry per BR-07.
- PHI-safe logging: Authorization failures and audit metadata must never include PHI fields, in line with BR-08.

---

## 8. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-004 | Permission auto-generation | Defines how dynamic EntityType permissions are created and maintained. Blocks full RBAC rollout. |
| ADR-007 | Auth provider and session management | Defines Auth0 integration, JWT validation, and person identity resolution. |
| ADR-011 | Multi-tenancy isolation | Defines tenant boundary strategy and authorization query scope. |
| ADR-003 | Session FK semantics | Ensures role-based session actors map correctly to identity and entity instances. |
| ADR-006 | Soft delete strategy | Defines delete semantics for Person and assignment lifecycle records. |

---

## 9. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Added full identity and RBAC ownership, model definitions, seed roles and permissions, authorization flow, API surface, business rules, and ADR mapping. |
