# Contributing to Groundwork

## Source of Truth

**Specs (`specs/`) are the sole source of truth.** All implementation derives from specs.

**Specs must have zero open questions.** No TBD, no unresolved alternatives, no pending decisions. If you find an open question in a spec, stop and resolve it (update the spec, write an ADR if architectural) before proceeding.

## Development Workflow

1. **Read `STATE.md`** — find your active task or the next unclaimed one.
2. **Read the task file** in `tasks/` — it references specific spec sections, dependencies, and acceptance criteria.
3. **Read the spec sections cited by the task** (in `specs/`).
4. **Read any ADRs cited by the task** (in `adrs/`) — these explain architectural constraints.
5. **Write failing tests first, then implementation.**
6. **On task completion:** write a completion log in `task-logs/`, mark task complete, update `STATE.md`, commit.

## Artifact Hierarchy

```
specs/      — WHAT (authoritative requirements, zero open questions)
adrs/       — WHY (architectural decisions only, not implementation details)
tasks/      — HOW (ordered work items derived from specs, written before code)
task-logs/  — WHAT HAPPENED (agent writes after completing a task)
code        — the implementation
```

**Authority flows downward.** Specs override everything. Tasks cannot contradict specs or ADRs. Task logs record what actually happened — they don't change what the task required.

## Tasks (`tasks/`)

Written before any code. Derived from resolved specs. Each task is an ordered, dependency-aware unit of work. Tasks form a tree — top-level tasks contain subtasks, creating a natural hierarchy without needing separate artifact types.

- **A task cannot start until:** all tasks it depends on are complete, and all spec sections it references have zero open questions.
- **Naming:** `TASK-NNN-<slug>.md` — numbered in execution order.
- **Task format:**

```markdown
# TASK-NNN: <Title>

**Status:** Not started | In progress | Complete
**Parent:** TASK-NNN (omit if top-level)
**Subtasks:** TASK-NNN, TASK-NNN (omit if leaf)
**Spec sections:** SPEC-NNN §Section
**ADRs:** ADR-NNN, ADR-NNN
**Depends on:** TASK-NNN (must be complete before this starts)

## Objective
What this task produces. One paragraph.

## Acceptance Criteria
- [ ] Criterion 1

## Files
Expected files to create or modify.

## Non-goals
What is explicitly out of scope for this task.
```

## Task Logs (`task-logs/`)

Written by the agent immediately after completing a task. Records what was actually done, decisions made during implementation, and any deviations from the task or spec.

- **One log per completed task.** Naming: `TASK-NNN-log.md`.
- **Deviations must be explained:** what changed, why, and whether it requires updating the task, spec, or another artifact.
- **Log format:**

```markdown
# TASK-NNN Log — <Title>

**Agent:** <claude-code | cursor | human>
**Branch:** <branch-name>
**Date completed:** YYYY-MM-DD

## What Was Done
Summary of implementation. Files created/modified, tests written, migrations generated.

## Decisions Made
Any non-obvious choices and why they were made.

## Deviations from Task
For each deviation:
- **What changed:** ...
- **Why:** ...
- **Impact:** Does this require updating the task, spec, or another artifact?

## Open Items
Anything discovered during implementation that needs follow-up.
```

## ADRs (`adrs/`)

ADRs document architectural decisions — the WHY behind constraints that shape implementation. They do not carry implementation details or task-level decisions.

- **When to write one:** when you make an architectural decision where the "why" is not obvious from reading the spec and code together.
- **Not ADR material:** implementation-detail choices (helper naming, index additions, test structure). Those go in the task log.
- **Naming:** chronological — `ADR-009-<slug>.md`, `ADR-010-<slug>.md`, etc. Never renumber.

## Coordination

Branch-per-task-group. Task dependencies define execution order. `STATE.md` tracks what's active, complete, and next.

## Build & Run

All services run via Docker Compose. The backend hot-reloads via volume mounts.

```bash
docker compose up --build              # start everything
docker compose up -d --build backend   # rebuild + restart backend only
docker compose logs backend -f         # tail backend logs
```

The entrypoint runs `alembic upgrade head` before starting uvicorn.

## Testing

Tests run inside the backend container against a real ephemeral PostgreSQL instance (`db-test`, internal port 5432, host port 5433). No mocks for data access.

```bash
docker compose exec backend pytest                                        # all tests + coverage
docker compose exec backend pytest tests/ -v --no-cov                     # skip coverage gate
docker compose exec backend pytest tests/test_cross_cutting/test_health.py -v --no-cov
docker compose exec backend pytest -k "test_health" --no-cov              # by name pattern
```

Coverage threshold is 90% (`--cov-fail-under`). Use `--no-cov` during development.

## Linting

```bash
docker compose exec backend ruff check app/ tests/
docker compose exec backend ruff format app/ tests/
docker compose exec backend mypy app/
```

## Migrations

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1
```

## Code Conventions

- **Pydantic everywhere.** No raw dicts for API I/O. Request/response bodies are Pydantic models.
- **UTC timestamps.** All datetime fields stored and transmitted in UTC. Column type is `DateTime(timezone=True)`.
- **Money in cents.** All monetary values stored as `Integer` cents, never floats. Column names carry a `_cents` suffix.
- **Cursor pagination.** All list endpoints use cursor-based pagination, never offset.
- **Standard error envelope.** All errors return `{"error": "...", "message": "...", "status": ..., "detail": {...}}`.
- **Soft deletes on PHI.** PHI-containing records use `deleted_at`, never hard delete. (See ADR-003.)
- **PHI excluded from logs.** The structlog PHI filter strips sensitive fields (`note_content`, `dob`, `ssn`, `diagnosis_codes`, etc.) before a record is emitted.
- **Audit log on state changes.** Every create/update/delete on a domain entity writes an `AuditLog` row in the same transaction.
- **No mocks in tests.** Real database with transaction rollback isolation. No `unittest.mock` for data access.
- **FK-only models.** Models expose foreign-key columns only, never `relationship()`. Joins are written explicitly in the query layer. (See ADR-005.)
- **Enums via `StrEnum` + `native_enum=False`.** Stored as VARCHAR for migration-friendliness. (See ADR-004.)

## Project Layout

- `STATE.md` — session entry point (read first)
- `specs/` — domain specifications (SPEC-000 through SPEC-007) — sole source of truth
- `adrs/` — architectural decision records, chronologically numbered — WHY
- `tasks/` — ordered work items derived from specs — HOW (pre-code)
- `task-logs/` — agent completion records, one per task — WHAT HAPPENED (post-code)
- `backend/app/core/` — database, settings, auth, logging, lifespan, exceptions
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/routers/` — FastAPI route handlers
- `backend/app/schemas/` — Pydantic request/response models
- `backend/app/services/` — business logic layer
- `backend/tests/` — organized by domain (`test_cross_cutting/`, etc.)
