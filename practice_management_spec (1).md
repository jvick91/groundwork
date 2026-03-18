# Groundwork — Practice Management App Specification
**Version:** 0.3.0  
**Stack:** Next.js (App Router) · FastAPI · PostgreSQL · Docker  
**Test Frameworks:** pytest + httpx (backend) · Vitest (frontend unit) · Playwright (E2E)  
**No mocks policy:** All tests run against real DBs, real HTTP, real browser.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Domain Model](#3-domain-model)
4. [Testing Strategy](#4-testing-strategy)
5. [Feature Specs](#5-feature-specs)
   - 5.1 Authentication & Authorization
   - 5.2 Client/Patient Management
   - 5.3 Scheduling & Appointments
   - 5.4 Clinical Notes (SOAP)
6. [API Contract](#6-api-contract)
7. [Test Suite Reference](#7-test-suite-reference)
8. [CI/CD & Compliance Notes](#8-cicd--compliance-notes)

---

## 1. Project Overview

A web-based practice management platform for independent therapists and small mental health practices. v1 covers three core domains: managing clients, scheduling appointments, and writing clinical (SOAP) notes. HIPAA compliance is the long-term target; v1 is designed to be HIPAA-ready via third-party services.

### Personas

| Persona | Role | Key Needs |
|---|---|---|
| **Provider** | Therapist / clinician | Manage own clients, schedule sessions, write notes |
| **Admin** | Practice admin | Manage all providers, clients, and schedules |
| **Client** | Patient (future) | Self-schedule, view invoices (post-v1) |

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
    Auth0 (SSO/MFA)                                             │
                                                     ┌──────────────────────────┐
                                                     │   PostgreSQL             │
                                                     └──────────────────────────┘
                                                     AWS S3 (note attachments, future)
```

### Docker Services

All services run in Docker containers orchestrated by Docker Compose. There is no "run it locally outside Docker" workflow — Docker is the development environment.

The development compose file defines four services: a Next.js frontend dev server with hot reload on port 3000, a FastAPI backend via uvicorn with hot reload on port 8000, a persistent PostgreSQL 16 database on port 5432, and an ephemeral PostgreSQL 16 test database on port 5433 used only during test runs.

A separate test compose override defines a backend test runner that executes pytest against the test database and exits when complete, and an E2E runner that executes Playwright against the live frontend and backend containers.

**Key principle:** Tests always run inside containers via `docker compose run` or `docker compose up`. There is no CI step that installs Python or Node directly on the host runner.

### Key Constraints
- All API endpoints require a valid Auth0 JWT (`Authorization: Bearer <token>`)
- Providers can only access their own clients/notes; Admins can access all
- All timestamps stored in UTC; displayed in user's local timezone
- Soft deletes on all clinical records (never hard-delete PHI)
- All environment secrets (DB credentials, Auth0 keys) injected via `.env` files — never baked into images

---

## 3. Domain Model

### Entities

```
Provider
  id: UUID PK
  auth0_user_id: str UNIQUE (links to Auth0)
  email: str UNIQUE
  full_name: str
  license_number: str
  license_state: str (2-char)
  role: enum [provider, admin]
  is_active: bool
  created_at: datetime
  updated_at: datetime

Client
  id: UUID PK
  provider: FK → Provider
  first_name: str
  last_name: str
  date_of_birth: date
  email: str (nullable)
  phone: str (nullable)
  emergency_contact_name: str (nullable)
  emergency_contact_phone: str (nullable)
  diagnosis_codes: str[] (ICD-10, nullable)
  is_active: bool
  created_at: datetime
  updated_at: datetime
  deleted_at: datetime (nullable, soft delete)

Appointment
  id: UUID PK
  provider: FK → Provider
  client: FK → Client
  start_time: datetime (UTC)
  end_time: datetime (UTC)
  status: enum [scheduled, completed, cancelled, no_show]
  appointment_type: enum [individual, group, intake, consultation]
  location: enum [in_person, telehealth]
  notes: str (nullable, brief provider note, not clinical)
  created_at: datetime
  updated_at: datetime

SOAPNote
  id: UUID PK
  appointment: FK → Appointment (nullable, can exist standalone)
  provider: FK → Provider
  client: FK → Client
  session_date: date
  subjective: text
  objective: text
  assessment: text
  plan: text
  status: enum [draft, signed]
  signed_at: datetime (nullable)
  created_at: datetime
  updated_at: datetime
  deleted_at: datetime (nullable, soft delete)
```

### Business Rules (Invariants)
- BR-01: An Appointment's `end_time` must be after `start_time`
- BR-02: An Appointment's `client.provider` must match `appointment.provider`
- BR-03: A Provider cannot have two non-cancelled appointments that overlap in time
- BR-04: A SOAPNote's `signed` status is irreversible — signed notes cannot be edited
- BR-05: Soft-deleted Clients do not appear in any list endpoints
- BR-06: A Provider can only access Clients and Notes assigned to them (unless Admin)

---

## 4. Testing Strategy

### Philosophy
- **No mocks.** Every test exercises real code paths: real DB, real HTTP, real browser.
- **Tests are the spec.** Every business rule (BR-xx) maps to at least one test.
- **Failing test first.** No implementation code is written without a failing test.
- **Test pyramid:** Many unit tests, fewer integration tests, fewer E2E tests.
- **Docker-first.** All tests run inside containers. `docker compose run backend-test pytest` is the canonical test command.

### Backend: pytest + httpx

Backend tests use an async HTTP client pointed at a real running FastAPI app, backed by a dedicated PostgreSQL test database. Each test function receives its own database session, which is rolled back after the test completes so tests remain isolated.

**Project structure**

```
backend/
  app/
    main.py              ← FastAPI app factory
    models/              ← SQLAlchemy ORM models
    schemas/             ← Pydantic request/response schemas
    routers/             ← FastAPI routers (clients, appointments, notes)
    services/            ← Business logic (overlap checks, signing, etc.)
    db.py                ← SQLAlchemy engine + session dependency
    auth.py              ← Auth0 JWT validation dependency
  alembic/               ← DB migrations
  tests/
    conftest.py
    unit/
      test_models.py
      test_schemas.py
      test_services.py
    integration/
      test_auth.py
      test_clients_api.py
      test_appointments_api.py
      test_notes_api.py
  pytest.ini
  Dockerfile
  requirements.txt
```

**Test configuration** declares async mode, marks slow tests for optional exclusion, and marks auth-related tests for targeted execution.

**Test fixtures** provide the following shared setup:

- A real async database session per test, rolled back on teardown, pointed at the test database container.
- A Provider fixture representing a standard authenticated provider, seeded into the test database.
- An Admin fixture representing a provider with the admin role, seeded into the test database.
- An HTTP client fixture authenticated as the standard provider, with the auth dependency replaced by the test-backed provider (no mocks — the provider record is real in the DB).
- An HTTP client fixture authenticated as the admin user, following the same pattern.

> **Note on auth in tests:** FastAPI's dependency override system replaces the JWT validation dependency with one that returns a real DB-backed Provider fixture. This is the FastAPI-idiomatic equivalent of `force_authenticate` — no mocks, just swapping the auth dependency for a test-controlled one that still reads from the real database.

### Frontend: Vitest

Frontend unit tests cover React components, custom hooks, and utility functions. Integration tests make real fetch calls to the backend container. Tests are organized under `frontend/tests/` with subdirectories for unit and integration tests.

### E2E: Playwright

Playwright runs inside its own container and drives a real browser against the live frontend and backend containers. Tests are organized by feature area (auth, clients, appointments, notes). The auth fixture performs a real Auth0 login flow using test credentials. The Playwright config points `baseURL` at the frontend container's service name; no `webServer` block is needed because containers are already running via Docker Compose.

### Docker Compose Test Workflow

All test commands invoke Docker Compose to run tests inside containers. Backend unit and integration tests run against the test database container. Frontend unit tests run in an isolated frontend container. E2E tests spin up the full stack and run Playwright against it, with the process exit code driven by the E2E container result. Individual backend test files can be targeted by specifying the file path to pytest.

---

## 5. Feature Specs

---

### 5.1 Authentication & Authorization

**Summary:** Auth is handled by Auth0. The FastAPI backend validates JWTs on every request via a `get_current_provider` dependency injected into all protected routes. Role-based access control (RBAC) is enforced at the router layer.

#### Unit Tests

These tests verify JWT validation logic in isolation against the real database.

| Test | Input | Expected Output |
|---|---|---|
| Valid token authenticates provider | A well-formed Auth0 JWT for an existing provider | The JWT resolves to the correct Provider record |
| Expired token is rejected | An expired JWT in the Authorization header | HTTP 401 |
| Malformed token is rejected | A non-JWT string in the Authorization header | HTTP 401 |
| Unknown subject is rejected | A valid JWT whose `sub` does not match any Provider in the database | HTTP 401 |

#### Integration Tests

These tests verify RBAC enforcement across the full HTTP stack.

| Test | Input | Expected Output |
|---|---|---|
| Provider cannot access another provider's client | Authenticated provider requests a client record belonging to a different provider | HTTP 404 |
| Admin can access any client | Admin-authenticated request for a client belonging to any provider | HTTP 200 with client data |
| Unauthenticated request is rejected | Any endpoint called without an Authorization header | HTTP 401 |
| Provider cannot self-escalate to admin | Provider submits `PATCH /me` with `role=admin` | Request is rejected or the role field is silently ignored; provider role remains unchanged |

#### E2E Tests

These tests exercise the full authentication flow through a real browser.

| Test | Steps | Expected Outcome |
|---|---|---|
| Login redirects to dashboard | Complete the real Auth0 login flow with test credentials | User lands on the dashboard |
| Unauthenticated access redirects to login | Navigate directly to `/dashboard` without being logged in | Browser is redirected to the login page |
| Logout clears session | Click the logout button; then navigate to `/dashboard` | User is redirected to login; session is fully cleared |

---

### 5.2 Client/Patient Management

**Summary:** Providers manage their own client roster. Clients are never hard-deleted.

#### Unit Tests

**Model tests** verify data behavior at the ORM layer.

| Test | Input | Expected Output |
|---|---|---|
| Full name property | A Client with a first and last name | `Client.full_name` returns "First Last" |
| Soft delete sets fields | Call `soft_delete()` on an active client | `deleted_at` is set and `is_active` is False |
| Soft-deleted client excluded from active query | Query clients with `active_only=True` after soft-deleting a client | Soft-deleted client does not appear |
| Soft-deleted client visible in unfiltered query | Query clients without an active filter | Soft-deleted client is included |

**Schema validation tests** verify input validation at the Pydantic layer.

| Test | Input | Expected Output |
|---|---|---|
| Valid data passes | A complete, valid `ClientCreate` payload | Schema accepts the data without error |
| Future date of birth rejected | `date_of_birth` set to a future date | Pydantic `ValidationError` is raised |
| Invalid phone format rejected | A phone number not in E.164 format | Pydantic `ValidationError` is raised |
| Invalid ICD-10 codes rejected | Strings in `diagnosis_codes` that are not valid ICD-10 codes | Pydantic `ValidationError` is raised |

#### Integration Tests

**List**

| Test | Input | Expected Output |
|---|---|---|
| Returns only own clients | Authenticated provider with clients from multiple providers in the DB | Response contains only clients assigned to the authenticated provider |
| Excludes soft-deleted clients | A soft-deleted client exists in the DB | Response does not include the deleted client |
| Search by name | `GET /clients?search=John` with matching and non-matching clients present | Response contains only clients whose name matches the search term |
| Pagination | More clients than fit on one page | Response includes paginated results with `next` and `previous` links |

**Create**

| Test | Input | Expected Output |
|---|---|---|
| Valid creation | `POST /clients` with all required fields | HTTP 201; record created in DB |
| Missing first name | `POST /clients` without `first_name` | HTTP 422 |
| Missing last name | `POST /clients` without `last_name` | HTTP 422 |
| Missing date of birth | `POST /clients` without `date_of_birth` | HTTP 422 |
| Provider assignment is enforced | `POST /clients` with a different `provider` field in the body | Client is always assigned to the authenticated provider regardless of body content |

**Retrieve**

| Test | Input | Expected Output |
|---|---|---|
| Own client accessible | `GET /clients/{id}` for a client owned by the authenticated provider | HTTP 200 with client data |
| Other provider's client returns 404 | `GET /clients/{id}` for a client owned by a different provider | HTTP 404 |

**Update**

| Test | Input | Expected Output |
|---|---|---|
| Partial update succeeds | `PATCH /clients/{id}` with a subset of valid fields | HTTP 200; updated fields reflected in response |
| Provider field cannot be changed | `PATCH /clients/{id}` with a new `provider` value | Request succeeds but provider assignment is silently ignored |

**Delete**

| Test | Input | Expected Output |
|---|---|---|
| Delete soft-deletes the record | `DELETE /clients/{id}` | HTTP 204; `deleted_at` is set; the database record still exists |
| Deleted client is no longer accessible | `GET /clients/{id}` after deletion | HTTP 404 |

#### E2E Tests

| Test | Steps | Expected Outcome |
|---|---|---|
| Create a new client | Navigate to `/clients/new`, fill and submit the form | New client appears in the client list |
| Search filters list in real time | Type a search term in the search box | Only matching client rows are visible |
| Soft-delete removes client from list | Delete a client via the UI | The client no longer appears in the list |

---

### 5.3 Scheduling & Appointments

**Summary:** Providers schedule appointments for their clients. No double-booking allowed.

#### Unit Tests

**Model tests**

| Test | Input | Expected Output |
|---|---|---|
| Duration calculation | An appointment with a known `start_time` and `end_time` | `duration_minutes` returns the correct integer value |
| End before start rejected | An appointment where `end_time` is before or equal to `start_time` | `ValueError` is raised (BR-01) |
| Client must belong to provider | An appointment where the client belongs to a different provider | `ValueError` is raised (BR-02) |

**Overlap tests**

| Test | Input | Expected Output |
|---|---|---|
| Overlapping appointment rejected | A second non-cancelled appointment whose time window overlaps an existing one | `ValueError` is raised (BR-03) |
| Cancelled appointment does not block slot | A new appointment in the same time slot as a cancelled appointment | Appointment is created successfully (BR-03) |
| Adjacent appointments are allowed | An appointment that starts exactly when another ends | Appointment is created successfully; no overlap (BR-03) |
| Overlap check is provider-scoped | Two different providers with appointments in the same time slot | Both appointments are created successfully; no conflict |

#### Integration Tests

**Create**

| Test | Input | Expected Output |
|---|---|---|
| Valid creation | `POST /appointments` with valid data for own client | HTTP 201 |
| Past appointments allowed | `POST /appointments` with a `start_time` in the past | HTTP 201 (past sessions may be recorded) |
| Overlapping slot returns conflict | `POST /appointments` that overlaps an existing non-cancelled appointment | HTTP 409 Conflict |
| Client from another provider rejected | `POST /appointments` referencing a client owned by a different provider | HTTP 422 |

**Status transitions**

| Test | Input | Expected Output |
|---|---|---|
| Cancel appointment | `PATCH /appointments/{id}` with `status=cancelled` | HTTP 200 |
| Complete appointment | `PATCH /appointments/{id}` with `status=completed` | HTTP 200 |
| Cannot reopen cancelled appointment | `PATCH /appointments/{id}` with `status=scheduled` on a cancelled appointment | HTTP 422 |

**List**

| Test | Input | Expected Output |
|---|---|---|
| Filter by date range | `GET /appointments?start=YYYY-MM-DD&end=YYYY-MM-DD` | Only appointments within that date range are returned |
| Filter by client | `GET /appointments?client_id={id}` | Only appointments for that client are returned |
| Other providers' appointments excluded | A mix of own and other-provider appointments in the DB | Only the authenticated provider's appointments are returned |

#### E2E Tests

| Test | Steps | Expected Outcome |
|---|---|---|
| Schedule a new appointment | Open the calendar, pick a slot, select a client, save | The appointment appears on the calendar |
| Double-booking shows conflict error | Attempt to book a slot that is already occupied | An error message describing the conflict is displayed |
| Cancelling updates the calendar | Cancel an existing appointment via the UI | The slot no longer shows as booked on the calendar |

---

### 5.4 Clinical Notes (SOAP)

**Summary:** Providers write SOAP notes linked to sessions. Once signed, notes are immutable.

#### Unit Tests

**Model tests**

| Test | Input | Expected Output |
|---|---|---|
| Signing sets status and timestamp | Call `sign()` on a draft note | `status` is set to `signed` and `signed_at` is set to the current UTC time |
| Signed note cannot be modified | Call `update()` on a signed note | `PermissionError` is raised (BR-04) |
| Soft delete a draft note | Call `soft_delete()` on a draft note | `deleted_at` is set and the note is excluded from active queries |
| Signed note cannot be soft-deleted | Call `soft_delete()` on a signed note | `PermissionError` is raised |

**Schema validation tests**

| Test | Input | Expected Output |
|---|---|---|
| All four sections required to sign | A `SOAPNote` payload with `status=signed` and one or more empty SOAP sections | Pydantic `ValidationError` is raised |
| Draft allows empty sections | A `SOAPNote` payload with `status=draft` and empty SOAP sections | Schema accepts the data without error |

#### Integration Tests

**Create**

| Test | Input | Expected Output |
|---|---|---|
| Create draft note | `POST /notes` with `status=draft` | HTTP 201 |
| Note linked to appointment | `POST /notes` with a valid `appointment_id` | HTTP 201; the note is linked to that appointment in the database |
| Note for another provider's client rejected | `POST /notes` referencing a client belonging to a different provider | HTTP 403 |

**Update**

| Test | Input | Expected Output |
|---|---|---|
| Update draft note content | `PATCH /notes/{id}` on a draft with new content | HTTP 200; updated content is reflected |
| Cannot update signed note | `PATCH /notes/{id}` on a signed note | HTTP 403 (BR-04) |
| Sign note with all sections filled | `PATCH /notes/{id}` with `status=signed` on a complete draft | HTTP 200; `signed_at` is set in the response |
| Sign note with missing section rejected | `PATCH /notes/{id}` with `status=signed` on a draft that has one or more empty sections | HTTP 422 |

**Delete**

| Test | Input | Expected Output |
|---|---|---|
| Delete a draft note | `DELETE /notes/{id}` on a draft | HTTP 204; soft delete applied |
| Cannot delete a signed note | `DELETE /notes/{id}` on a signed note | HTTP 403 |
| Deleted note not in list | `GET /notes` after deleting a draft | The deleted note does not appear in the response |

**Access control**

| Test | Input | Expected Output |
|---|---|---|
| List returns only own notes | Provider with notes from multiple providers in the DB | Response contains only notes authored by the authenticated provider |
| Cannot retrieve another provider's note | `GET /notes/{id}` for a note authored by a different provider | HTTP 404 |
| Filter by client | `GET /notes?client_id={id}` | Only notes for that client are returned |
| Filter by date range | `GET /notes?start=YYYY-MM-DD&end=YYYY-MM-DD` | Only notes within that session date range are returned |

#### E2E Tests

| Test | Steps | Expected Outcome |
|---|---|---|
| Create and save a draft SOAP note | Navigate to notes, fill in all four SOAP sections, save as draft | The draft appears in the notes list |
| Signing makes note read-only | Open a draft note and sign it | All SOAP fields become read-only; the Sign button is no longer visible |
| Cannot sign with empty section | Leave one SOAP section empty and attempt to sign | A validation error message is displayed |
| Signed note cannot be edited via direct navigation | Navigate directly to `/notes/{signedId}/edit` | User is redirected to the read-only view or shown a 403 page |

---

## 6. API Contract

### Base URL
`/api/v1/`

### Authentication
All endpoints require:
```
Authorization: Bearer <auth0_access_token>
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/me` | Authenticated provider profile |
| PATCH | `/me` | Update own profile (not role) |
| GET | `/clients` | List own clients (paginated, searchable) |
| POST | `/clients` | Create client |
| GET | `/clients/{id}` | Retrieve client |
| PATCH | `/clients/{id}` | Update client |
| DELETE | `/clients/{id}` | Soft-delete client |
| GET | `/appointments` | List appointments (filterable) |
| POST | `/appointments` | Create appointment |
| GET | `/appointments/{id}` | Retrieve appointment |
| PATCH | `/appointments/{id}` | Update / change status |
| DELETE | `/appointments/{id}` | Cancel appointment |
| GET | `/notes` | List SOAP notes (filterable) |
| POST | `/notes` | Create SOAP note |
| GET | `/notes/{id}` | Retrieve SOAP note |
| PATCH | `/notes/{id}` | Update draft / sign |
| DELETE | `/notes/{id}` | Soft-delete draft note |

### Standard Error Responses

| Status | Condition | Response body key |
|---|---|---|
| 401 Unauthorized | Missing or invalid Authorization header | `detail: "Not authenticated"` |
| 403 Forbidden | Authenticated but insufficient permissions | `detail: "Not enough permissions"` |
| 404 Not Found | Resource does not exist or is not accessible to the caller | `detail: "Not found"` |
| 409 Conflict | Double-booking attempt | `detail: "This time slot conflicts with an existing appointment"` |
| 422 Unprocessable Entity | Request body fails validation | `detail` array with field-level error messages |

---

## 7. Test Suite Reference

### Running Tests

All test commands run inside Docker containers. The canonical commands are:

- **Backend — all tests:** Run pytest inside the backend-test container
- **Backend — unit tests only:** Run pytest targeting the `tests/unit/` directory
- **Backend — with coverage:** Run pytest with `--cov=app` and generate an HTML report
- **Frontend — unit tests:** Run Vitest inside the frontend-test container
- **E2E — all:** Spin up the full stack via the test compose override; exit code is driven by the E2E container
- **E2E — specific feature:** Run Playwright targeting a single spec file (e.g., `notes.spec.ts`)
- **Specific backend file:** Run pytest targeting a single integration test file with verbose output

### Coverage Targets

| Layer | Min Coverage Target |
|---|---|
| Models + services | 95% |
| API routers + schemas | 90% |
| Frontend components | 80% |
| E2E (critical paths) | All BRs covered |

### Business Rule → Test Mapping

| Rule | Description | Test Location |
|---|---|---|
| BR-01 | end_time after start_time | `test_models.py` — Appointment model, end-before-start test |
| BR-02 | Client must belong to provider | `test_models.py` — Appointment model, client-provider mismatch test |
| BR-03 | No overlapping appointments | `test_models.py` — Appointment overlap test group |
| BR-04 | Signed notes immutable | `test_models.py` — SOAP note model, signed-note modification test |
| BR-05 | Soft-deleted clients excluded | `test_clients_api.py` — Client list, soft-delete exclusion test |
| BR-06 | Provider isolation | `test_auth.py` — RBAC, cross-provider access test |

---

## 8. CI/CD & Compliance Notes

### CI Pipeline (GitHub Actions)

All CI steps run entirely inside Docker — no Python or Node is installed directly on the runner. The pipeline consists of four jobs:

- **backend-tests:** Runs pytest inside the test compose configuration with a minimum coverage threshold of 90%.
- **frontend-tests:** Runs Vitest inside the frontend-test container.
- **e2e-tests:** Spins up the full stack via the test compose override and runs Playwright. The Playwright HTML report is uploaded as a build artifact.
- **lint:** Runs `ruff` on the backend source and ESLint + TypeScript type checking on the frontend.

### Docker Image Strategy

The project uses three Dockerfiles. The backend image is multi-stage: a builder stage installs dependencies, and a slim runtime stage runs the app. The frontend image is similarly multi-stage: a builder stage runs `next build`, and a runtime stage serves the output. The E2E image is based on the official Playwright image and includes browser binaries. The development compose file uses volume mounts for hot reload. The test compose override removes volume mounts and uses `exit-code-from` to signal test completion.

**Key rules:**
- Images must build reproducibly from a clean checkout with no secrets baked in
- `.env.example` committed to repo; `.env` in `.gitignore`
- `db-test` container is separate from `db` — test runs never touch dev data

### HIPAA-Ready Design Decisions (v1)

- **Auth0**: Handles MFA, SSO, session management, audit logs of auth events
- **Soft deletes**: PHI is never hard-deleted; `deleted_at` flag used instead
- **No logging of PHI**: Application logs must not include note content, DOB, or diagnosis codes
- **FastAPI structured logging**: Use `structlog` with JSON output; PHI fields excluded at the serializer layer
- **Future**: AWS S3 with SSE-S3 or SSE-KMS for file attachments; audit log table for all record access

### Spec Versioning

This spec lives in the repository at `docs/spec.md`. Every PR that changes behavior **must** update this spec in the same commit. The spec version bumps with each feature addition.

| Version | Changes |
|---|---|
| 0.1.0 | Initial spec (Django + DRF) |
| 0.2.0 | Migrated to FastAPI + Docker; async tests; Pydantic schemas; no trailing slashes; 422 replaces 400 for validation errors |
| 0.3.0 | Renamed to Groundwork; removed implementation code from all testing sections; test requirements now described in plain English with input/output tables |
