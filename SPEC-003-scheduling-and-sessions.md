# SPEC-003: Scheduling and Sessions

**Status:** Draft
**Version:** 0.3.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Session scheduling, appointment types, availability, and cancellation lifecycle.

---

## 1. Domain Overview

This domain manages the scheduling layer of the platform. A session represents a planned or completed clinical encounter between a provider instance and a client instance inside an organization. AppointmentType is the reusable template that defines session defaults such as duration and billing code.

Sessions are the primary transactional unit connecting the identity layer (SPEC-002) to the clinical layer (SPEC-004) and the billing layer (SPEC-005). A session must exist before a clinical note can be authored or an invoice can be generated.

### Tables owned

- Session: A scheduled or completed encounter between a provider instance and a client instance.
- AppointmentType: Reusable template that defines default duration, billing code, and session category.

---

## 2. Data Model Detail

### AppointmentType

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes type to a tenant. |
| name | String | NOT NULL | Human label for the appointment kind (for example Initial Intake, Individual Therapy, Group Session). |
| default_duration_minutes | Integer | NOT NULL | Default session length in minutes. |
| cpt_code_id | UUID | FK -> CPTCode, NULLABLE | Default billing code associated with this appointment kind. |
| is_telehealth | Boolean | NOT NULL, default false | Whether this type is delivered via telehealth. |
| is_active | Boolean | NOT NULL, default true | Soft toggle. Inactive types cannot be used for new sessions. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |

### Session

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes session to a tenant. |
| appointment_type_id | UUID | FK -> AppointmentType, NOT NULL | Template used for this session. |
| provider_instance_id | UUID | FK -> EntityInstance, NOT NULL | Provider profile instance delivering the session. Must reference an EntityInstance of type provider. |
| client_instance_id | UUID | FK -> EntityInstance, NOT NULL | Client profile instance receiving the session. Must reference an EntityInstance of type client. |
| start_time | Timestamp | NOT NULL | Scheduled or actual start of the session in UTC. |
| end_time | Timestamp | NOT NULL | Scheduled or actual end of the session in UTC. |
| status | Enum | NOT NULL, default scheduled | One of: scheduled, confirmed, in_progress, completed, cancelled, no_show. |
| cancellation_reason | Text | NULLABLE | Required when status is cancelled or no_show. |
| cancelled_at | Timestamp | NULLABLE | When the cancellation was recorded in UTC. |
| cancelled_by_person_id | UUID | FK -> Person, NULLABLE | Which person recorded the cancellation. |
| location | String | NULLABLE | Physical address or telehealth platform identifier. |
| notes | Text | NULLABLE | Internal scheduling notes. Not PHI. Not a clinical note. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

---

## 3. Session Status Lifecycle

Sessions move through statuses in one direction. The allowed transitions are:

| From | Allowed transitions |
|---|---|
| scheduled | confirmed, cancelled, no_show |
| confirmed | in_progress, cancelled, no_show |
| in_progress | completed, cancelled |
| completed | none (terminal) |
| cancelled | none (terminal) |
| no_show | none (terminal) |

Terminal statuses cannot be updated. Any attempt to transition out of a terminal status must be rejected with a domain error.

---

## 4. Business Rules

- BR-01 (Time order): A session's end_time must be strictly after start_time. A zero-duration or negative-duration session is invalid.
- BR-02 (Org membership): A session's client_instance_id and provider_instance_id must both belong to the same organization_id as the session. Cross-tenant session creation is never permitted.
- BR-03 (Provider overlap): A provider instance cannot have two non-cancelled sessions whose time ranges overlap. Overlap is defined as: an existing session's start_time is before the new session's end_time, and the existing session's end_time is after the new session's start_time. The check applies to scheduled, confirmed, and in_progress sessions. Cancelled and no_show sessions do not count toward overlap.
- Bridge rule for provider: provider_instance_id must reference an EntityInstance whose EntityType slug is provider. The backend validates this at write time.
- Bridge rule for client: client_instance_id must reference an EntityInstance whose EntityType slug is client. The backend validates this at write time.
- Cancellation reason: When setting status to cancelled or no_show, cancellation_reason must be provided. Requests without a reason are rejected.
- AppointmentType guard: An inactive AppointmentType (is_active = false) cannot be used when creating a new Session. Existing sessions referencing a deactivated type are not affected.
- Soft delete rule: Soft-deleted sessions must not appear in list endpoints. Soft-deleted sessions are excluded from provider overlap checks.
- Consent gate: A session cannot be transitioned to completed unless the client has an active signed treatment consent on file (ConsentType slug = 'treatment', status = 'signed', and expiration_date is null or >= current date). This check is a service-layer call to the consent service defined in SPEC-006. Sessions may be scheduled, confirmed, and started without consent, but completion is blocked.

---

## 5. Scheduling Constraints

The following constraints apply at the service layer before a session is committed:

- The provider's organization membership must be confirmed active via their PersonRole assignment before a session is booked on their behalf.
- A client must have an EntityInstance with intake_status of complete or in_progress before a non-intake session type can be scheduled for them.
- End-to-end duration consistency: the difference between end_time and start_time must equal or exceed the AppointmentType's default_duration_minutes. Shorter durations are allowed only if explicitly set by a user with sessions.write permission.

---

## 6. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

### AppointmentType management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /appointment-types | List all active appointment types for the org | sessions.read |
| POST | /appointment-types | Create a new appointment type | settings.write |
| GET | /appointment-types/{id} | Retrieve appointment type detail | sessions.read |
| PATCH | /appointment-types/{id} | Update appointment type | settings.write |
| DELETE | /appointment-types/{id} | Deactivate appointment type (soft toggle) | settings.write |

### Session management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /sessions | List sessions (paginated, filterable by status, provider, client, date range) | sessions.read |
| POST | /sessions | Create a new session | sessions.write |
| GET | /sessions/{id} | Retrieve session detail | sessions.read |
| PATCH | /sessions/{id} | Update session fields or status | sessions.write |
| DELETE | /sessions/{id} | Soft delete session | sessions.write |

### Session status transitions

| Method | Path | Description | Permission |
|---|---|---|---|
| POST | /sessions/{id}/confirm | Transition scheduled to confirmed | sessions.write |
| POST | /sessions/{id}/start | Transition confirmed to in_progress | sessions.write |
| POST | /sessions/{id}/complete | Transition in_progress to completed | sessions.write |
| POST | /sessions/{id}/cancel | Transition to cancelled with required reason body | sessions.write |
| POST | /sessions/{id}/no-show | Transition to no_show with required reason body | sessions.write |

Explicit transition endpoints are preferred over a generic PATCH on status to enforce lifecycle rules at the routing layer rather than in application service logic.

---

## 7. Implementation Constraints

- Overlap detection: BR-03 must be enforced inside a database transaction to prevent race conditions on concurrent booking requests.
- Audit requirements: All state-changing calls (POST, PATCH, DELETE, and all transition endpoints) must write an AuditLog entry per BR-07.
- PHI-safe logging: Session.notes is not PHI, but client identity details must never appear in application logs per BR-08.
- Timezone handling: All session timestamps are stored and compared in UTC. Display conversion to the organization's timezone is a frontend concern.
- Clinical note link: When a session transitions to completed, the backend should not automatically create a ClinicalNote. Note creation is a separate intentional action by the provider. See SPEC-004.
- Invoice link: A completed session is eligible for invoice generation. Billing is not triggered automatically. See SPEC-005.

---

## 8. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-003 | Session FK semantics | Defines how provider and client are referenced as EntityInstance IDs rather than Person IDs, and the bridge rule validation responsibility. |
| ADR-001 | Core MVP data model | Establishes Session as a concrete table and AppointmentType as its template. |
| ADR-006 | Soft delete strategy | Defines delete semantics and how deleted sessions are excluded from overlap checks. |
| ADR-011 | Multi-tenancy isolation | Requires all session queries to filter by organization_id and prohibits cross-tenant access. |

---

## 9. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full model definitions for Session and AppointmentType. Status lifecycle, business rules BR-01 through BR-03, API surface, scheduling constraints, and ADR mapping. |
| 0.2.0 | Renamed conductor_instance_id to provider_instance_id and attendee_instance_id to client_instance_id. Aligns field naming with SPEC-005 Invoice and cross-spec consistency. |
| 0.3.0 | Added consent gate business rule: session completion requires active signed treatment consent per SPEC-006. |
