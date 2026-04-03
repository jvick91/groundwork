# Groundwork — Practice Management Platform Specification

**Version:** 1.0.0
**Status:** Draft
**Supersedes:** practice_management_spec v0.3.0
**Stack:** Next.js (App Router) · FastAPI · PostgreSQL · Redis · Celery · Docker
**Type System:** Pydantic for all data validation, serialization, and API schemas. Every model, request body, response body, and internal service contract uses Pydantic types. No untyped dicts or raw JSON handling.
**Test Frameworks:** pytest + httpx (backend) · Vitest (frontend unit) · Playwright (E2E)
**No mocks policy:** All tests run against real DBs, real HTTP, real browser.

---

## What changed from v0.3.0

The v0.3.0 spec described a single-practice app with four hardcoded tables (Provider, Client, Appointment, SOAPNote). This spec replaces it with a multi-tenant platform architecture. The core changes are:

- Provider, Client, and Admin are no longer fixed tables. They are seed rows in a flexible Entity-Attribute-Value system that allows practices to define custom persona types without code changes.
- A Person can hold multiple roles simultaneously via a PersonRole junction table.
- Role-based access control is decoupled from hardcoded persona types. Permissions reference entity types, so custom types get RBAC automatically.
- Multi-tenancy is built in. Every record scopes to an Organization.
- Billing tables (Invoice, Payment, InsurancePayer, ClientInsurance) are part of the MVP.

Everything else carries forward: the stack, Docker-first development, no-mocks testing, HIPAA-ready design, and the business rules from v0.3.0 (renumbered below).

---

## 1. Project overview

A multi-tenant web platform for mental health practices of any size. Practices can define custom persona types, custom fields, and custom roles. The platform handles scheduling, clinical documentation, and billing. HIPAA compliance is the long-term target; MVP is HIPAA-ready via third-party services and audit logging.

### Personas and table resolution

Every persona resolves through three tables: Person (who you are), EntityInstance of an EntityType (your profile data), and PersonRole pointing to a Role (your permissions). EntityType and Role are two independent axes. EntityType determines profile shape (what fields describe you). Role determines permission set (what you can do).

There are only 3 EntityTypes (provider, client, admin) but 9+ Roles. A therapist and a supervisor share the same EntityType (provider) with the same profile fields. The only difference is which Role their PersonRole points to.

| Persona | EntityType (profile) | Role (permissions) | Key profile fields | Key permissions |
|---|---|---|---|---|
| Therapist | provider | therapist | license_number, license_state, npi_number, specialty | clients.rw, sessions.rw, notes.rw, notes.sign |
| Supervisor | provider | supervisor | license_number, license_state, npi_number, specialty | Everything therapist has + notes.cosign |
| Prescriber | provider | prescriber | license_number, license_state, npi_number, specialty, dea_number | Everything therapist has + prescriptions.write (future) |
| Practice admin | admin | practice_admin | department, title | clients.rw, sessions.rw, providers.read, invoices.*, payments.*, insurance.*, codes.read, settings.rw |
| System admin | admin | system_admin | department, title | Everything practice_admin has + tenants.manage, system.configure |
| Biller | admin | biller | department, title | invoices.*, payments.*, insurance.*, codes.read |
| Receptionist | admin | receptionist | department, title | sessions.rw, clients.rw (intake only), consents.rw, consents.sign, forms.read, forms.send |
| Client | client | client | intake_status, referral_source, emergency_contact, onboarded_at | Post-MVP: own_profile.read, own_sessions.read, own_invoices.read |
| Guardian | client | guardian | intake_status, referral_source, relationship_to_minor | Post-MVP: same as client, scoped to dependent's records |

A single person can hold multiple roles. A solo practice owner who is both a therapist and a practice admin gets one Person row, two EntityInstance rows (provider profile + admin profile), and two PersonRole rows (therapist + practice_admin). Their effective permissions are the union of both roles.

Sub-spec: SPEC-002 (Identity and RBAC)

### Role hierarchy

Three primary roles. All others are subordinate to one of them.

| Primary | Subordinates | Domain | EntityType |
|---|---|---|---|
| Admin | Practice admin, System admin, Biller, Receptionist | Operations and staff | admin |
| Provider | Therapist, Supervisor, Prescriber | Clinical delivery | provider |
| Client | Portal user, Guardian | Receives care | client |

---

## 2. Architecture

```
┌─────────────────────────┐      HTTPS / JSON       ┌──────────────────────────┐
│   Next.js (App Router)  │ ◄─────────────────────► │   FastAPI                │
│   - React Server Comps  │                          │   - REST API             │
│   - Client components   │                          │   - SQLAlchemy ORM       │
│   - Auth0 SDK (client)  │                          │   - Alembic migrations   │
└─────────────────────────┘                          │   - Auth0 JWT validation │
         │                                           └──────────────────────────┘
    Auth0 (SSO/MFA)                                      │              │
                                                ┌────────┘              └────────┐
                                                │                                │
                                       ┌──────────────────┐          ┌──────────────────┐
                                       │  PostgreSQL 16   │          │  Redis 7         │
                                       └──────────────────┘          │  - Celery broker │
                                                                     │  - Cache (future)│
                                       ┌──────────────────┐          └──────────────────┘
                                       │  Celery Worker   │                  │
                                       │  - Task queue    │◄─────────────────┘
                                       │  - Beat scheduler│
                                       └──────────────────┘
                                       AWS S3 (documents, encrypted at rest)
```

### Docker services

All services run in Docker containers orchestrated by Docker Compose. There is no "run it locally outside Docker" workflow. Docker is the development environment.

The development compose file defines six services: a Next.js frontend dev server with hot reload on port 3000, a FastAPI backend via uvicorn with hot reload on port 8000, a persistent PostgreSQL 16 database on port 5432, an ephemeral PostgreSQL 16 test database on port 5433 used only during test runs, a Redis 7 instance on port 6379 for the Celery broker, and a Celery worker with Beat scheduler for background tasks.

A separate test compose override defines a backend test runner that executes pytest against the test database and exits when complete, and an E2E runner that executes Playwright against the live frontend and backend containers.

Tests always run inside containers. There is no CI step that installs Python or Node directly on the host runner.

### Key constraints

- All API endpoints require a valid Auth0 JWT
- Access control is enforced by role and entity type via RBAC, not hardcoded persona checks
- All timestamps stored in UTC, displayed in user's local timezone
- Soft deletes on all clinical and PHI-bearing records
- All environment secrets injected via .env files, never baked into images
- Every record scopes to an Organization (multi-tenant isolation)
- All backend data validation, API request/response schemas, and service-layer contracts use Pydantic models. No raw dicts, untyped JSON, or manual validation. Python type hints are mandatory throughout.

ADR: ADR-007 (Auth provider), ADR-011 (Multi-tenancy isolation), ADR-013 (CI/CD)

---

## 3. Data model overview

The data model is a hybrid of two patterns. See ADR-001 for the full rationale.

**EAV layer (practice-configurable):** Defines what kinds of things exist and what fields they have. A practice can create new entity types, add fields, and assign RBAC without code changes. The three primary persona types (admin, provider, client) are seed data in this system, not hardcoded tables.

**Concrete layer (transactional):** Records events and transactions with real columns, real foreign keys, and database-level constraints. Sessions, clinical notes, invoices, and payments live here.

**Bridge rule:** Concrete tables reference EntityInstance IDs. Application-level validation ensures the referenced instance matches the expected entity type.

### MVP table inventory (26 tables)

| Layer | Table | One-line purpose |
|---|---|---|
| EAV | Organization | The practice or tenant. All data scopes to this. |
| EAV | EntityType | Defines a kind of thing (provider, client, or custom). |
| EAV | EntityAttribute | Defines one field on a type. |
| EAV | EntityInstance | One actual record of a type. |
| EAV | AttributeValue | One field value on one instance. |
| Identity | Person | A human being. Name, email, phone, DOB. |
| Identity | PersonRole | Assigns a person to a role within an organization. |
| Identity | Role | Primary or subordinate role with self-referencing hierarchy. |
| Identity | Permission | An action on an entity type. |
| Identity | RolePermission | Grants a permission to a role. |
| Clinical | Session | A scheduled or completed encounter between provider and client instances. |
| Clinical | ClinicalNote | SOAP/DAP/BIRP documentation of a session. |
| Clinical | AppointmentType | Template for session kinds with default duration and CPT code. |
| Billing | InsurancePayer | Reference directory of insurance companies. |
| Billing | ClientInsurance | Links a client instance to a payer with coverage details. |
| Billing | Invoice | Bill generated from a completed session. Lifecycle: draft, sent, partial, paid, void. One active (non-voided) invoice per session. |
| Billing | InvoiceLineItem | Individual charge with CPT and ICD codes. |
| Billing | Payment | Money received against an invoice. Can be voided with reason for corrections. |
| Billing | CPTCode | Procedure code reference table, scoped to organization. |
| Billing | ICDCode | Diagnosis code reference table, scoped to organization. |
| Compliance | AuditLog | Immutable record of every user action. HIPAA required. |
| Compliance | DocumentType | Organization-scoped reference table defining valid document categories. |
| Compliance | Document | Uploaded file with S3 key, encrypted at rest. Linked to DocumentType. |
| Compliance | ConsentType | Organization-scoped reference table defining valid consent categories. |
| Compliance | ClientConsent | Consent tracking with type, signed date, expiry. Lifecycle: pending, signed, revoked, expired. |
| Compliance | FormTemplate | Custom form definition for intake and assessments. System templates seeded per-org. |

ADR: ADR-001 (Core data model), ADR-002 (EAV query performance), ADR-005 (AttributeValue type safety), ADR-006 (Soft delete strategy)

---

## 4. Business rules

These carry forward from v0.3.0 and apply to the new model. Entity-specific rules live in their sub-specs.

| Rule | Description | Sub-spec |
|---|---|---|
| BR-01 | A Session's end_time must be after start_time | SPEC-003 |
| BR-02 | A Session's client must be assigned to the provider's organization | SPEC-003 |
| BR-03 | A provider instance cannot have two non-cancelled sessions that overlap in time | SPEC-003 |
| BR-04 | A ClinicalNote's signed content is immutable. Post-signing changes follow an addendum-only model: the original content is never overwritten, amendments are append-only, and the note re-enters the signing cycle. Notes transition through draft, signed, cosigned, and amendment_pending statuses. Co-signing is required for supervisees and optional otherwise. Any person with the notes.cosign permission may co-sign. | SPEC-004 |
| BR-05 | Soft-deleted records do not appear in any list endpoints. Only draft ClinicalNotes may be soft-deleted; signed, cosigned, and amendment_pending notes are protected from deletion. | SPEC-001, SPEC-004 |
| BR-06 | Access control is enforced by RBAC. A role can only access entity instances and records permitted by its RolePermission grants. | SPEC-002 |
| BR-07 | Every state-changing API call writes an AuditLog entry | SPEC-006 |
| BR-08 | Application logs must not contain PHI (note content, DOB, diagnosis codes) | SPEC-006 |

---

## 5. Testing strategy

Carries forward from v0.3.0 with no changes to philosophy.

- No mocks. Every test exercises real code paths: real DB, real HTTP, real browser.
- Tests are the spec. Every business rule maps to at least one test.
- Failing test first. No implementation code is written without a failing test.
- Test pyramid. Many unit tests, fewer integration tests, fewer E2E tests.
- Docker-first. All tests run inside containers.

Sub-spec: SPEC-007 (API contract and testing)

### Coverage targets

| Layer | Minimum |
|---|---|
| Models and services | 95% |
| API routers and schemas | 90% |
| Frontend components | 80% |
| E2E critical paths | All BRs covered |

---

## 6. HIPAA-ready design (MVP)

- Auth0 handles MFA, SSO, session management, and audit logs of auth events
- Soft deletes on all PHI-bearing records
- AuditLog table records every state change with user, action, resource, IP, timestamp
- Application logs exclude PHI via structlog with JSON output and PHI field exclusion at the serializer layer
- AWS S3 with SSE-S3 or SSE-KMS for document storage
- ClientConsent table tracks treatment, telehealth, and ROI consent with expiry and revocation

ADR: ADR-009 (File storage and encryption)

---

## 7. Domain sub-specs

Each sub-spec owns its domain completely: entity definitions, field-level detail, business rules, API endpoints, request/response schemas, error codes, and test tables.

| Sub-spec | Domain | Tables owned |
|---|---|---|
| SPEC-001 | EAV data platform | Organization, EntityType, EntityAttribute, EntityInstance, AttributeValue |
| SPEC-002 | Identity and RBAC | Person, PersonRole, Role, Permission, RolePermission |
| SPEC-003 | Scheduling and sessions | Session, AppointmentType |
| SPEC-004 | Clinical notes | ClinicalNote |
| SPEC-005 | Billing and payments | InsurancePayer, ClientInsurance, Invoice, InvoiceLineItem, Payment, CPTCode, ICDCode |
| SPEC-006 | Documents, consent, compliance | AuditLog, DocumentType, Document, ConsentType, ClientConsent, FormTemplate |
| SPEC-007 | API contract and testing | No tables. Cross-cutting: endpoint inventory, error codes, test strategy, CI pipeline. |

---

## 8. ADR index

| ADR | Title | Blocks | Status |
|---|---|---|---|
| ADR-001 | Core MVP data model | Phase 1 | Proposed |
| ADR-002 | EAV query performance | Phase 1 | Pending |
| ADR-003 | Session FK semantics | Phase 2, API contract | Pending |
| ADR-004 | Permission auto-generation | Phase 1 seed logic | Pending |
| ADR-005 | AttributeValue type safety | Phase 1 | Pending |
| ADR-006 | Soft delete strategy | Phase 1, compliance | Pending |
| ADR-007 | Auth provider and session management | SPEC-002 | Pending |
| ADR-008 | Payment processor integration | SPEC-005 | Pending |
| ADR-009 | File storage and encryption | SPEC-006 | Pending |
| ADR-010 | API versioning strategy | SPEC-007 | Pending |
| ADR-011 | Multi-tenancy isolation | Phase 1 | Pending |
| ADR-012 | Migration from v1 schema | Phase 1 | Pending |
| ADR-013 | CI/CD and deployment | All phases | Pending |
| ADR-014 | Monitoring and observability | All phases | Pending |

---

## 9. Spec versioning

This spec lives in the repository at docs/SPEC-000-platform-overview.md. Every PR that changes behavior must update the relevant sub-spec in the same commit. Sub-specs version independently. This master spec versions when the table inventory, domain boundaries, or architecture changes.

| Version | Changes |
|---|---|
| 0.1.0 | Initial spec (Django + DRF) |
| 0.2.0 | Migrated to FastAPI + Docker |
| 0.3.0 | Renamed to Groundwork. Removed implementation code from test sections. |
| 1.0.0 | Platform rewrite. EAV + concrete hybrid. Multi-tenancy. RBAC. 24 MVP tables. Master/sub-spec/ADR document structure. Supersedes monolithic spec. |
| 1.1.0 | Updated BR-04 (amendment model), BR-05 (draft-only delete for notes). Added Pydantic type system requirement. Added granular billing permissions. Renamed conductor/attendee to provider/client in sessions. Added DocumentType and ConsentType reference tables (26 MVP tables). Updated persona permissions. Universal org-scoping enforced on all tables. |
