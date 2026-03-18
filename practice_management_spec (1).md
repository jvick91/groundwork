# Practice Management App — TDD Specification
**Version:** 0.2.0  
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

```
docker-compose.yml (dev)
  frontend      → Next.js dev server (port 3000), hot reload via volume mount
  backend       → FastAPI via uvicorn (port 8000), hot reload via volume mount
  db            → PostgreSQL 16 (port 5432), persisted via named volume
  db-test       → PostgreSQL 16 (port 5433), ephemeral, used only during test runs

docker-compose.test.yml (test override)
  backend-test  → runs pytest against db-test, exits when done
  e2e           → runs Playwright against live frontend + backend containers
```

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

FastAPI has no Django test client. Instead, tests use `httpx.AsyncClient` pointed at a real running FastAPI app backed by a real PostgreSQL test database (`db-test` container). SQLAlchemy sessions are transaction-wrapped and rolled back after each test.

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

**Key pytest settings (pytest.ini)**
```ini
[pytest]
asyncio_mode = auto
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --strict-markers
markers =
    slow: marks tests as slow (deselect with -m "not slow")
    auth: tests related to authentication/authorization
```

**conftest.py (top-level fixtures)**
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_session
from app.models import Base, Provider

# Points at the db-test container (port 5433)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db-test:5433/test"

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Each test gets a real async DB session, rolled back on teardown."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()
    await engine.dispose()

@pytest_asyncio.fixture
async def provider(db_session):
    p = Provider(
        auth0_user_id="auth0|test_provider",
        email="provider@test.com",
        full_name="Test Provider",
        role="provider",
    )
    db_session.add(p)
    await db_session.flush()
    return p

@pytest_asyncio.fixture
async def admin_user(db_session):
    a = Provider(
        auth0_user_id="auth0|test_admin",
        email="admin@test.com",
        full_name="Test Admin",
        role="admin",
    )
    db_session.add(a)
    await db_session.flush()
    return a

@pytest_asyncio.fixture
async def client(provider, db_session):
    """Returns an httpx AsyncClient wired to the FastAPI app with provider auth."""
    app.dependency_overrides[get_session] = lambda: db_session
    # Override JWT dependency to inject the test provider directly
    app.dependency_overrides[get_current_provider] = lambda: provider
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def admin_client(admin_user, db_session):
    """Returns an httpx AsyncClient authenticated as admin."""
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_current_provider] = lambda: admin_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

> **Note on dependency overrides:** FastAPI's `dependency_overrides` replaces the JWT validation dependency with one that returns a real DB-backed Provider fixture. This is the FastAPI-idiomatic equivalent of `force_authenticate` — no mocks, just swapping the auth dependency for a test-controlled one that still touches the real DB.

### Frontend: Vitest

```
frontend/
  vitest.config.ts
  tests/
    unit/
      components/
      hooks/
      utils/
    integration/
      api-client.test.ts   ← real fetch calls to backend container
  Dockerfile
```

### E2E: Playwright

Playwright runs inside its own container and drives a real browser against the live `frontend` and `backend` containers.

```
e2e/
  playwright.config.ts
  fixtures/
    auth.fixture.ts       ← real Auth0 login flow
  tests/
    auth.spec.ts
    clients.spec.ts
    appointments.spec.ts
    notes.spec.ts
  Dockerfile
```

**Playwright config key settings**
```typescript
// playwright.config.ts
export default defineConfig({
  use: {
    baseURL: 'http://frontend:3000',  // container service name
    serviceWorkers: 'block',
  },
  // No webServer block — containers are already up via docker compose
});
```

### Docker Compose Test Workflow

```bash
# Run all backend unit + integration tests
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test

# Run frontend unit tests
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm frontend-test

# Run E2E tests (spins up all services first)
docker compose -f docker-compose.yml -f docker-compose.test.yml up --exit-code-from e2e e2e

# Run a specific backend test file
docker compose run --rm backend-test pytest tests/integration/test_clients_api.py -v
```

---

## 5. Feature Specs

---

### 5.1 Authentication & Authorization

**Summary:** Auth is handled by Auth0. The FastAPI backend validates JWTs on every request via a `get_current_provider` dependency injected into all protected routes. Role-based access control (RBAC) is enforced at the router layer.

#### Unit Tests

```python
# tests/unit/test_auth.py

class TestJWTValidation:
    async def test_valid_token_authenticates_provider(self, db_session, valid_jwt_token):
        """A well-formed Auth0 JWT resolves to the correct Provider record."""

    async def test_expired_token_returns_401(self, unauthenticated_client, expired_jwt):
        """An expired JWT returns HTTP 401."""

    async def test_malformed_token_returns_401(self, unauthenticated_client):
        """A non-JWT string in Authorization header returns HTTP 401."""

    async def test_unknown_sub_returns_401(self, db_session, jwt_for_unknown_user):
        """A valid JWT whose sub does not match any Provider returns HTTP 401."""
```

#### Integration Tests

```python
# tests/integration/test_auth.py

class TestRBAC:
    async def test_provider_cannot_access_other_providers_clients(
        self, client, other_provider_client
    ):
        """GET /clients/{other_client_id} returns 404 for a different provider's client."""

    async def test_admin_can_access_all_clients(self, admin_client, client_obj):
        """Admin GET /clients/{any_id} returns 200 regardless of assigned provider."""

    async def test_unauthenticated_request_returns_401(self, unauthenticated_client):
        """Any endpoint without Authorization header returns HTTP 401."""

    async def test_provider_cannot_escalate_to_admin(self, client):
        """Provider cannot set role=admin on their own profile via PATCH /me."""
```

#### E2E Tests

```typescript
// e2e/tests/auth.spec.ts

test('login redirects to dashboard', async ({ page }) => {
  // Real Auth0 login flow using test credentials
});

test('unauthenticated user is redirected to login', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/login/);
});

test('logout clears session and redirects to login', async ({ page, loggedIn }) => {
  await page.click('[data-testid="logout-button"]');
  await expect(page).toHaveURL(/login/);
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/login/);
});
```

---

### 5.2 Client/Patient Management

**Summary:** Providers manage their own client roster. Clients are never hard-deleted.

#### Unit Tests

```python
# tests/unit/test_models.py

class TestClientModel:
    async def test_full_name_property(self, db_session):
        """Client.full_name returns 'First Last'."""

    async def test_soft_delete_sets_deleted_at(self, db_session, client_obj):
        """client.soft_delete() sets deleted_at and is_active=False."""

    async def test_soft_deleted_client_excluded_from_active_query(self, db_session, client_obj):
        """Query with active_only=True excludes soft-deleted records."""

    async def test_soft_deleted_client_visible_in_all_query(self, db_session, client_obj):
        """Query without active filter includes soft-deleted records."""

# tests/unit/test_schemas.py

class TestClientSchema:
    def test_valid_data_passes(self):
        """Pydantic ClientCreate schema accepts valid client data."""

    def test_date_of_birth_cannot_be_in_future(self):
        """date_of_birth in the future raises Pydantic ValidationError."""

    def test_phone_format_validated(self):
        """Phone number must be E.164 format or raise ValidationError."""

    def test_diagnosis_codes_must_be_valid_icd10(self):
        """Non-ICD-10 strings in diagnosis_codes raise ValidationError."""
```

#### Integration Tests

```python
# tests/integration/test_clients_api.py

class TestClientList:
    async def test_list_returns_only_own_clients(self, client, provider, other_provider):
        """GET /clients returns only clients belonging to the authenticated provider."""

    async def test_list_excludes_soft_deleted(self, client, deleted_client):
        """GET /clients does not include soft-deleted clients."""

    async def test_list_supports_search_by_name(self, client, clients):
        """GET /clients?search=John returns matching clients only."""

    async def test_list_supports_pagination(self, client, many_clients):
        """GET /clients returns paginated results with next/previous links."""

class TestClientCreate:
    async def test_create_client_success(self, client):
        """POST /clients with valid data returns 201 and creates DB record."""

    async def test_create_requires_first_name(self, client):
        """POST /clients without first_name returns 422."""

    async def test_create_requires_last_name(self, client):
        """POST /clients without last_name returns 422."""

    async def test_create_requires_date_of_birth(self, client):
        """POST /clients without date_of_birth returns 422."""

    async def test_create_assigns_to_authenticated_provider(self, client, provider):
        """POST /clients always assigns client to the authenticated provider, ignoring any provider field in body."""

class TestClientRetrieve:
    async def test_retrieve_own_client(self, client, client_obj):
        """GET /clients/{id} returns 200 for own client."""

    async def test_retrieve_other_providers_client_returns_404(
        self, client, other_client
    ):
        """GET /clients/{id} returns 404 for client belonging to another provider."""

class TestClientUpdate:
    async def test_partial_update_succeeds(self, client, client_obj):
        """PATCH /clients/{id} with valid partial data returns 200."""

    async def test_cannot_change_provider(self, client, client_obj, other_provider):
        """PATCH /clients/{id} with a new provider field is silently ignored."""

class TestClientDelete:
    async def test_delete_soft_deletes(self, client, client_obj):
        """DELETE /clients/{id} returns 204 and sets deleted_at; DB record persists."""

    async def test_deleted_client_not_accessible(self, client, client_obj):
        """After DELETE, GET /clients/{id} returns 404."""
```

#### E2E Tests

```typescript
// e2e/tests/clients.spec.ts

test('provider can create a new client', async ({ page, loggedIn }) => {
  // Navigate to /clients/new, fill form, submit, verify appears in list
});

test('search filters client list in real time', async ({ page, loggedIn }) => {
  // Type in search box, assert only matching rows visible
});

test('soft-deleted client disappears from list', async ({ page, loggedIn }) => {
  // Delete a client, assert it is no longer in the list
});
```

---

### 5.3 Scheduling & Appointments

**Summary:** Providers schedule appointments for their clients. No double-booking allowed.

#### Unit Tests

```python
# tests/unit/test_models.py

class TestAppointmentModel:
    async def test_duration_in_minutes(self, db_session, appointment):
        """appointment.duration_minutes returns correct integer."""

    async def test_end_before_start_raises(self, db_session, provider, client_obj):
        """Creating an Appointment with end_time <= start_time raises ValueError. (BR-01)"""

    async def test_client_must_belong_to_provider(self, db_session, provider, other_client):
        """Creating an Appointment with a client not belonging to provider raises ValueError. (BR-02)"""

class TestAppointmentOverlap:
    async def test_overlapping_appointment_raises(self, db_session, appointment):
        """A second non-cancelled appointment overlapping in time raises ValueError. (BR-03)"""

    async def test_cancelled_appointment_does_not_block_slot(self, db_session, cancelled_appt):
        """A new appointment in the same slot as a cancelled appointment succeeds. (BR-03)"""

    async def test_adjacent_appointments_do_not_overlap(self, db_session, appointment):
        """An appointment starting exactly when another ends does not raise. (BR-03)"""

    async def test_overlap_check_scoped_to_provider(self, db_session, appointment, other_provider):
        """Two providers can have appointments in the same slot without conflict."""
```

#### Integration Tests

```python
# tests/integration/test_appointments_api.py

class TestAppointmentCreate:
    async def test_create_valid_appointment(self, client, client_obj):
        """POST /appointments with valid data returns 201."""

    async def test_create_with_past_start_time_succeeds(self, client, client_obj):
        """Past appointments are allowed (for recording completed sessions)."""

    async def test_create_overlapping_returns_409(self, client, client_obj, existing_appt):
        """POST /appointments that overlaps existing returns 409 Conflict."""

    async def test_create_for_other_providers_client_returns_422(
        self, client, other_client
    ):
        """POST /appointments with a client from another provider returns 422."""

class TestAppointmentStatusTransitions:
    async def test_cancel_appointment(self, client, appointment):
        """PATCH /appointments/{id} with status=cancelled returns 200."""

    async def test_complete_appointment(self, client, appointment):
        """PATCH /appointments/{id} with status=completed returns 200."""

    async def test_cannot_reopen_cancelled_appointment(self, client, cancelled_appt):
        """PATCH /appointments/{id} with status=scheduled on cancelled returns 422."""

class TestAppointmentList:
    async def test_list_filtered_by_date_range(self, client, appointments):
        """GET /appointments?start=2024-01-01&end=2024-01-31 returns only that range."""

    async def test_list_filtered_by_client(self, client, client_obj, appointments):
        """GET /appointments?client_id={id} returns only that client's appointments."""

    async def test_list_excludes_other_providers_appointments(
        self, client, other_appointment
    ):
        """GET /appointments never includes another provider's appointments."""
```

#### E2E Tests

```typescript
// e2e/tests/appointments.spec.ts

test('provider can schedule a new appointment', async ({ page, loggedIn }) => {
  // Open calendar, pick slot, select client, save, verify on calendar
});

test('double-booking shows conflict error', async ({ page, loggedIn }) => {
  // Book same slot twice, assert error message visible
});

test('cancelling appointment updates calendar display', async ({ page, loggedIn }) => {
  // Cancel appointment, assert slot no longer shows as booked
});
```

---

### 5.4 Clinical Notes (SOAP)

**Summary:** Providers write SOAP notes linked to sessions. Once signed, notes are immutable.

#### Unit Tests

```python
# tests/unit/test_models.py

class TestSOAPNoteModel:
    async def test_sign_note_sets_signed_at(self, db_session, draft_note):
        """note.sign() sets status=signed and signed_at to current UTC time."""

    async def test_signed_note_cannot_be_modified(self, db_session, signed_note):
        """Calling note.update() on a signed note raises PermissionError. (BR-04)"""

    async def test_soft_delete_note(self, db_session, draft_note):
        """note.soft_delete() sets deleted_at; note excluded from active query."""

    async def test_signed_note_cannot_be_soft_deleted(self, db_session, signed_note):
        """Attempting to soft_delete a signed note raises PermissionError."""

# tests/unit/test_schemas.py

class TestSOAPNoteSchema:
    def test_all_four_sections_required_to_sign(self):
        """Signing a note with any empty SOAP section raises Pydantic ValidationError."""

    def test_draft_allows_empty_sections(self):
        """Saving a draft with empty sections succeeds."""
```

#### Integration Tests

```python
# tests/integration/test_notes_api.py

class TestSOAPNoteCreate:
    async def test_create_draft_note(self, client, client_obj):
        """POST /notes with status=draft returns 201."""

    async def test_create_note_linked_to_appointment(self, client, appointment):
        """POST /notes with appointment_id field links to that appointment in DB."""

    async def test_create_note_for_other_providers_client_returns_403(
        self, client, other_client
    ):
        """POST /notes for another provider's client returns 403."""

class TestSOAPNoteUpdate:
    async def test_update_draft_note(self, client, draft_note):
        """PATCH /notes/{id} on a draft returns 200 and updates content."""

    async def test_cannot_update_signed_note(self, client, signed_note):
        """PATCH /notes/{id} on a signed note returns 403. (BR-04)"""

    async def test_sign_note_with_all_sections_filled(self, client, complete_draft_note):
        """PATCH /notes/{id} with status=signed returns 200 and sets signed_at."""

    async def test_sign_note_with_missing_section_returns_422(
        self, client, incomplete_draft_note
    ):
        """PATCH /notes/{id} with status=signed but empty sections returns 422."""

class TestSOAPNoteDelete:
    async def test_delete_draft_note(self, client, draft_note):
        """DELETE /notes/{id} on a draft returns 204 (soft delete)."""

    async def test_cannot_delete_signed_note(self, client, signed_note):
        """DELETE /notes/{id} on a signed note returns 403."""

    async def test_deleted_note_not_in_list(self, client, draft_note):
        """After DELETE, note does not appear in GET /notes."""

class TestSOAPNoteAccess:
    async def test_list_returns_only_own_notes(self, client, provider, other_provider_note):
        """GET /notes returns only notes by authenticated provider."""

    async def test_retrieve_other_providers_note_returns_404(
        self, client, other_provider_note
    ):
        """GET /notes/{id} for another provider's note returns 404."""

    async def test_list_filtered_by_client(self, client, client_obj):
        """GET /notes?client_id={id} returns only notes for that client."""

    async def test_list_filtered_by_date_range(self, client, notes):
        """GET /notes?start=2024-01-01&end=2024-01-31 returns only that range."""
```

#### E2E Tests

```typescript
// e2e/tests/notes.spec.ts

test('provider can create and save a draft SOAP note', async ({ page, loggedIn }) => {
  // Navigate to notes, fill in all four SOAP sections, save as draft
  // Assert draft appears in notes list
});

test('signing a note makes it read-only', async ({ page, loggedIn }) => {
  // Open draft note, sign it
  // Assert all SOAP fields become read-only / inputs are disabled
  // Assert "Sign" button is no longer visible
});

test('attempting to sign note with empty section shows error', async ({ page, loggedIn }) => {
  // Leave one SOAP section empty, attempt to sign
  // Assert validation error message is displayed
});

test('signed note cannot be edited via direct navigation', async ({ page, loggedIn }) => {
  // Navigate directly to /notes/{signedId}/edit
  // Assert redirect to read-only view or 403 page
});
```

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

```json
// 422 Unprocessable Entity (FastAPI validation failure)
{
  "detail": [
    { "loc": ["body", "field_name"], "msg": "Error message.", "type": "value_error" }
  ]
}

// 401 Unauthorized
{ "detail": "Not authenticated" }

// 403 Forbidden
{ "detail": "Not enough permissions" }

// 404 Not Found
{ "detail": "Not found" }

// 409 Conflict (double booking)
{ "detail": "This time slot conflicts with an existing appointment" }
```

---

## 7. Test Suite Reference

### Running Tests

```bash
# Backend — all tests (inside Docker)
docker compose run --rm backend-test pytest

# Backend — unit tests only (fast)
docker compose run --rm backend-test pytest tests/unit/

# Backend — with coverage report
docker compose run --rm backend-test pytest --cov=app --cov-report=html

# Frontend — unit tests
docker compose run --rm frontend-test npx vitest run

# E2E — all (spins up full stack)
docker compose -f docker-compose.yml -f docker-compose.test.yml up --exit-code-from e2e e2e

# E2E — specific feature
docker compose run --rm e2e npx playwright test notes.spec.ts

# Run a specific backend test file
docker compose run --rm backend-test pytest tests/integration/test_clients_api.py -v
```

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
| BR-01 | end_time after start_time | `test_models.py::TestAppointmentModel::test_end_before_start_raises` |
| BR-02 | Client must belong to provider | `test_models.py::TestAppointmentModel::test_client_must_belong_to_provider` |
| BR-03 | No overlapping appointments | `test_models.py::TestAppointmentOverlap::*` |
| BR-04 | Signed notes immutable | `test_models.py::TestSOAPNoteModel::test_signed_note_cannot_be_modified` |
| BR-05 | Soft-deleted clients excluded | `test_clients_api.py::TestClientList::test_list_excludes_soft_deleted` |
| BR-06 | Provider isolation | `test_auth.py::TestRBAC::test_provider_cannot_access_other_providers_clients` |

---

## 8. CI/CD & Compliance Notes

### CI Pipeline (GitHub Actions)

All CI steps run entirely inside Docker — no Python or Node is installed directly on the runner.

```yaml
on: push, pull_request

jobs:
  backend-tests:
    steps:
      - docker compose -f docker-compose.yml -f docker-compose.test.yml
          run --rm backend-test pytest --cov=app --cov-fail-under=90

  frontend-tests:
    steps:
      - docker compose run --rm frontend-test npx vitest run

  e2e-tests:
    steps:
      - docker compose -f docker-compose.yml -f docker-compose.test.yml
          up --exit-code-from e2e e2e
      - Upload Playwright HTML report as artifact

  lint:
    steps:
      - docker compose run --rm backend-test ruff check app/
      - docker compose run --rm frontend npx eslint . && npx tsc --noEmit
```

### Docker Image Strategy

```
backend/Dockerfile        ← multi-stage: builder installs deps, runtime is slim
frontend/Dockerfile       ← multi-stage: builder runs next build, runtime serves
e2e/Dockerfile            ← based on mcr.microsoft.com/playwright, includes browsers
docker-compose.yml        ← dev: volume mounts for hot reload, db-test sidecar
docker-compose.test.yml   ← test overrides: no volume mounts, exit-code-from
```

**Key rules:**
- Images must build reproducibly from a clean checkout with no secrets baked in
- `.env.example` committed to repo; `.env` in `.gitignore`
- `db-test` container is separate from `db` — test runs never touch dev data

### HIPAA-Ready Design Decisions (v1)

- **Auth0**: Handles MFA, SSO, session management, audit logs of auth events
- **Soft deletes**: PHI is never hard-deleted; deleted_at flag used instead
- **No logging of PHI**: Application logs must not include note content, DOB, or diagnosis codes
- **FastAPI structured logging**: Use `structlog` with JSON output; PHI fields excluded at the serializer layer
- **Future**: AWS S3 with SSE-S3 or SSE-KMS for file attachments; audit log table for all record access

### Spec Versioning

This spec lives in the repository at `docs/spec.md`. Every PR that changes behavior **must** update this spec in the same commit. The spec version bumps with each feature addition.

| Version | Changes |
|---|---|
| 0.1.0 | Initial spec (Django + DRF) |
| 0.2.0 | Migrated to FastAPI + Docker; async tests; Pydantic schemas; no trailing slashes; 422 replaces 400 for validation errors |
