# TASK-001: Project Scaffolding & Docker Services

**Status:** Complete
**Spec sections:** SPEC-000 §2, SPEC-007 §2, §10, §12
**ADRs:** —
**Depends on:** —

## Objective

Establish the foundational project structure: Docker Compose services (backend, db, db-test), FastAPI application factory with `/api/v1/` prefix, async SQLAlchemy engine and session factory, Pydantic-based settings, and the directory layout defined in SPEC-007 §12. This task produces a running `docker compose up --build` that boots the API server and both Postgres instances.

## Acceptance Criteria

- [ ] `docker compose up --build` starts backend (port 8000), db (port 5432), and db-test (port 5433) with health checks
- [ ] FastAPI app serves all routes under `/api/v1/` prefix per SPEC-007 §2
- [ ] Async SQLAlchemy engine connects to PostgreSQL using env-based config
- [ ] Pydantic Settings class reads all env vars from `.env` files
- [ ] Alembic is configured with async engine support and can run `upgrade head`
- [ ] Entrypoint script runs `alembic upgrade head` before starting uvicorn
- [ ] Hot reload works via volume mounts
- [ ] Directory layout matches SPEC-007 §12.1 (app/core, models, schemas, services, routers, middleware)

## Files

- `docker-compose.yml`
- `backend/dockerfile`
- `docker-entrypoint.sh`
- `backend/app/main.py`
- `backend/app/core/settings.py`
- `backend/app/core/database.py`
- `backend/app/core/lifespan.py`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/pyproject.toml`
- `.env`

## Non-goals

- ORM model definitions (TASK-002+)
- Auth middleware (TASK-014)
- Any API endpoint beyond a placeholder mount
