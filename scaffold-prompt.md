# Scaffold Prompt

Generate the initial repository scaffold for Groundwork, a multi-tenant mental health practice management platform. Do not implement any domain logic. Only create the skeleton files with stubs, docstrings, and TODOs marking where each phase fills in.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) with asyncpg, psycopg2-binary (sync, for Celery tasks)
- PostgreSQL 16
- Alembic (async migrations)
- Auth0 JWT validation via auth0-fastapi-api
- Pydantic 2 + pydantic-settings
- Redis 7 + Celery 5 (background tasks)
- structlog (JSON logging)
- Poetry for dependency management
- Docker Compose for all services (no local install workflow)
- pytest + httpx (async) for testing, no mocks

## Repository Structure

```
groundwork/
├── specs/                              # Domain specs (I will copy these in)
├── adrs/
│   └── ADR-TEMPLATE.md                 # ADR template with sections: Problem, Options, Chosen Approach, Phased Plan (checkboxed), Deviation Notes
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app factory with create_app()
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── settings.py             # pydantic-settings: db, auth0, redis, celery, cors, logging
│   │   │   ├── database.py             # async engine, async_session_factory, Base declarative, get_db dependency
│   │   │   ├── security.py             # AuthContext dataclass, get_auth_context dependency (stub), require_permission factory
│   │   │   ├── dependencies.py         # re-exports get_db, get_auth_context, require_permission
│   │   │   ├── exceptions.py           # GroundworkError base, NotFoundError, ValidationError, ConflictError, ForbiddenError, OrganizationRequiredError, BridgeRuleViolation, StatusTransitionError
│   │   │   ├── logger.py               # structlog setup with PHI field exclusion filter
│   │   │   ├── lifespan.py             # FastAPI lifespan context manager (startup/shutdown)
│   │   │   └── celery_app.py           # Celery instance configured with Redis broker
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py               # Empty, docstring listing models to add per phase
│   │   ├── routers/
│   │   │   └── __init__.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py              # PaginationMeta, PaginatedResponse, ErrorResponse
│   │   ├── services/
│   │   │   └── __init__.py
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   └── tasks.py                # Stub module for Celery task definitions
│   │   └── utils/
│   │       └── __init__.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Async test engine, transaction-rollback db_session fixture, httpx AsyncClient fixture
│   │   ├── factories/
│   │   │   ├── __init__.py
│   │   │   ├── app_factory.py          # create_test_app wrapper
│   │   │   └── crud_factory.py         # make_uuid helper, docstring for per-phase factories
│   │   ├── test_auth/__init__.py
│   │   ├── test_eav/__init__.py
│   │   ├── test_identity/__init__.py
│   │   ├── test_sessions/__init__.py
│   │   ├── test_notes/__init__.py
│   │   ├── test_billing/__init__.py
│   │   ├── test_compliance/__init__.py
│   │   └── test_cross_cutting/
│   │       ├── __init__.py
│   │       └── test_health.py          # Smoke test: GET /api/v1/health returns 200
│   ├── logs/                           # Empty directory (gitkeep)
│   ├── settings/                       # Empty directory (gitkeep)
│   ├── alembic/
│   │   ├── env.py                      # Async alembic env importing Base and all models
│   │   ├── script.py.mako              # Migration template
│   │   └── versions/                   # Empty
│   ├── alembic.ini
│   ├── pytest.ini                      # asyncio_mode=auto, testpaths=tests, cov config
│   ├── .coveragerc                     # source=app, fail_under=90, omit celery/alembic/tests
│   ├── pyproject.toml                  # Poetry config with all deps listed above + dev deps (pytest, ruff, mypy, factory-boy)
│   ├── dockerfile                      # Python 3.12-slim, Poetry install, copy app
│   ├── .env.backend                    # Dev defaults for all settings
│   └── README.MD
├── docker-compose.yml                  # 6 services: backend (8000), db (5432), db-test (5433), redis (6379), celery-worker, celery-beat
├── docker-entrypoint.sh                # Runs alembic upgrade head then exec "$@"
├── .env                                # Postgres credentials for compose
├── .env.example                        # Safe-to-commit template
├── .gitignore                          # Python, venv, .env, coverage, IDE, OS, Docker
├── .cursorrules                        # Two-mode workflow (architect/coder), phasing, code conventions, testing rules
└── readme.md
```

## Key Implementation Details

### main.py
- `create_app()` factory function returning FastAPI instance
- CORS middleware using settings.cors_origins
- Exception handler catching GroundworkError and returning standard JSON envelope: `{"error": "...", "message": "...", "status": ..., "detail": {...}}`
- `GET /api/v1/health` endpoint (no auth required)
- Docs at /api/v1/docs only when debug=true
- Stub comments marking where routers are added per phase

### core/security.py
- `AuthContext` dataclass with fields: person_id (UUID), auth_subject (str), organization_id (UUID), role_slugs (list[str]), permissions (set[str])
- `get_auth_context` dependency that raises 501 Not Implemented (stub for Phase 2)
- `require_permission(permission_slug)` dependency factory that checks AuthContext.permissions

### core/exceptions.py
- `GroundworkError(error, message, status_code, detail)` base
- Subclasses: `NotFoundError(resource, resource_id)`, `ValidationError(message, detail)`, `ConflictError(message, detail)`, `ForbiddenError(message)`, `OrganizationRequiredError()`, `BridgeRuleViolation(field, expected_type, actual_type)`, `StatusTransitionError(resource, current_status, target_status)`

### core/logger.py
- PHI_FIELDS frozenset: note_content, date_of_birth, dob, diagnosis_codes, icd_codes, ssn, social_security
- `phi_filter` structlog processor that strips these fields
- `setup_logging()` configuring structlog with JSON or console renderer based on settings
- `get_logger(name)` returning a bound logger

### core/settings.py
- pydantic-settings loading from .env.backend
- Fields: app_name, app_version, debug, environment, database_url (async), database_url_sync (sync, for Celery tasks), test_database_url, auth0_domain, auth0_audience, auth0_issuer, redis_url, celery_broker_url, celery_result_backend, cors_origins, log_level, log_json
- Property: auth0_issuer_url built from domain if issuer not set
- database_url uses postgresql+asyncpg:// (for FastAPI async sessions)
- database_url_sync uses postgresql+psycopg2:// or postgresql:// (for Celery worker sync sessions)

### core/database.py
- Async engine from settings.database_url with pool_pre_ping
- async_session_factory using async_sessionmaker
- `Base` declarative base class
- `get_db` async generator dependency yielding session with commit/rollback/close

### core/celery_app.py
- Celery instance named "groundwork"
- Broker: settings.celery_broker_url (Redis)
- Result backend: settings.celery_result_backend (Redis)
- Task serializer: json, accept_content: json, timezone: UTC
- This module is imported by three separate processes: the FastAPI server (to publish tasks), the Celery worker (to execute tasks), and Celery beat (to schedule periodic tasks). They communicate through Redis as the message broker.

### tasks/tasks.py
- Stub module for Celery task definitions. Tasks are added per phase as domain requirements surface.
- Import the celery_app instance from core/celery_app.py
- Each task is a function decorated with `@celery_app.task`
- Tasks run in the Celery worker process, NOT inside the FastAPI process. They must create their own synchronous SQLAlchemy sessions when they need database access, since they run in a separate process from the async FastAPI app.
- Task arguments must be JSON-serializable (strings, ints, UUIDs as strings, dicts). Do not pass Pydantic models or ORM objects directly.
- Include a `get_sync_session` helper that creates a synchronous SQLAlchemy session for use within tasks, using a sync engine built from settings.
- Docstring should list candidate task areas from the specs: audit log writes, document processing callbacks, consent expiry checks, scheduled report generation, invoice batch operations.

### schemas/schemas.py
- `PaginationMeta`: next_cursor, previous_cursor, has_next, has_previous, limit
- `PaginatedResponse`: data (list), pagination (PaginationMeta)
- `ErrorResponse`: error, message, status, detail

### tests/conftest.py
- Session-scoped `test_engine` fixture creating tables from Base.metadata
- Per-test `db_session` fixture using transaction rollback for isolation
- `client` fixture: httpx AsyncClient with ASGITransport, overrides get_db with test session
- TODO comment for Phase 2 JWT test fixture

### docker-compose.yml
- backend: builds from backend/dockerfile, port 8000, mounts app/ and tests/, depends on db and redis healthy. This is the FastAPI process. It publishes tasks to Redis but does not execute them.
- db: postgres:16-alpine, port 5432, named volume pgdata, healthcheck
- db-test: postgres:16-alpine, port 5433, tmpfs (ephemeral), healthcheck
- redis: redis:7-alpine, port 6379, healthcheck. Serves as the Celery message broker (task queue) and result backend (task outcomes). Future use: permission caching, rate limiting.
- celery-worker: same build as backend, command `celery -A app.core.celery_app worker --loglevel=info`. Subscribes to Redis queues, pulls task messages, executes task functions. Runs in its own process with its own database connections.
- celery-beat: same build as backend, command `celery -A app.core.celery_app beat --loglevel=info`. Scheduler that publishes periodic tasks to Redis on a defined schedule. Does not execute tasks itself.

The three backend processes (FastAPI, worker, beat) all share the same codebase and import the same celery_app instance. They are separate containers so they scale independently.

### .cursorrules
Define two modes:
- ARCHITECT MODE (triggered by "plan", "epic", "ADR"): reads specs, outputs ADRs with Problem/Options/Chosen Approach/Phased Plan (checkboxed epics)/Deviation Notes. ADRs must NEVER contain code of any kind.
- CODER MODE (triggered by "Go", "implement"): finds first incomplete ADR checkbox, implements it, writes failing test first, notes deviations.

Include phasing order:
- Phase 1: EAV (SPEC-001), blocking ADRs: 002, 005, 006, 011
- Phase 2: Identity/RBAC (SPEC-002), blocking ADRs: 004, 007
- Phase 3: Scheduling (SPEC-003)
- Phase 4: Clinical/billing/compliance (SPEC-004, 005, 006)
- Phase 5: API hardening (SPEC-007)

Include code conventions: Pydantic everywhere, no raw dicts, UTC timestamps, money in cents, cursor pagination, standard error envelope, soft deletes on PHI records, PHI excluded from logs, audit log on state changes, no mocks in tests.

## Rules

- Do NOT write any domain models, routers, services, or domain schemas. Only the skeleton.
- Every stub file should have a docstring explaining what goes there and which phase fills it in.
- All __init__.py files in empty test directories should be empty files.
- The health check smoke test should be a real working test.
- Use `.gitkeep` files in empty directories (logs/, settings/, alembic/versions/).
