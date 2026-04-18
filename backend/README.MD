# Groundwork Backend

Multi-tenant mental health practice management platform backend.

## Stack

- **Framework**: FastAPI + Uvicorn
- **Database**: PostgreSQL 16 with SQLAlchemy 2.0 (async)
- **Migrations**: Alembic (async)
- **Auth**: Auth0 JWT validation
- **Logging**: structlog (JSON)

## Development

All services run via Docker Compose from the project root:

```bash
docker compose up --build
```

### Services

| Service       | Port | Purpose                        |
|---------------|------|--------------------------------|
| backend       | 8000 | FastAPI application            |
| db            | 5432 | PostgreSQL (development)       |
| db-test       | 5433 | PostgreSQL (testing, ephemeral)|

### Running Tests

```bash
docker compose exec backend pytest
```

## Phased Implementation

- **Phase 1**: EAV (SPEC-001)
- **Phase 2**: Identity/RBAC (SPEC-002)
- **Phase 3**: Scheduling (SPEC-003)
- **Phase 4**: Clinical, Billing, Compliance (SPEC-004, 005, 006)
- **Phase 5**: API Hardening (SPEC-007)
