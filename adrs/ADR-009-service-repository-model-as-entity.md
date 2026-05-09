# ADR-009 — Service + Model-as-Entity for multi-tenant FastAPI

**Date:** 2026-05-09
**Author:** claude-code
**Status:** Accepted (amended 2026-05-09 — Repository layer removed; see "Amendment" below)

## Amendment 2026-05-09 — Repository layer removed

The original decision below introduced a per-aggregate `<Aggregate>Repository` class as the single owner of every SQL statement for that aggregate. After landing the first three services (Organization, EntityType, EntityAttribute), the repositories proved to be thin SQL wrappers — three to five methods each, each called from exactly one service. They added indirection without behavior, file count without payoff.

**The amendment:** drop the Repository layer. Services hold the `AsyncSession` directly. All SQL for one aggregate lives in a `# Query helpers` section at the bottom of `services/<aggregate>_service.py`, alongside the use-case methods that call it. ADR-002's "explicit joins reviewable in one auditable place per aggregate" property is preserved because each aggregate has exactly one Service file.

**The architecture is now three layers:** router → service → model. Services orchestrate use cases, hold their session, and own their queries. Models hold schema and invariants. Routers are thin HTTP adapters that depend on a single `Depends(get_<aggregate>_service)`.

**When to re-introduce a Repository:** the trigger is *queries shared across multiple services or multiple methods in different services* — not "the service file is getting big." Concrete signals:
- Permission resolution and `current_org` both walk the role hierarchy → extract a `RoleRepository`.
- Audit-log read paths needed by both the compliance API and an export job → extract an `AuditLogRepository`.
- A complex projection (e.g., the JSONB EntityInstance aggregation in TASK-011B) consumed by more than one caller.

Until that signal fires, queries inline in the service file under the `# Query helpers` section.

The remainder of this document records the original decision and the reasoning that led to the Repository layer; it is preserved because the Model-as-Entity, AuditWriter, lifecycle dispatcher, no-module-level-state, and naming-schema portions are still in force. Read the sections about Repository as historical context for the amendment above.

---

## Context

The repository carries one shipped vertical slice (Organization, TASK-009) plus
foundational plumbing (audit, exceptions, pagination, logging, auth stub). The
existing convention — TASK-008A's "plain async functions in `app/services/`",
plus a `call_service_with_audit(...)` wrapper in `app/services/common.py` — was
chosen when no slices had landed and the cost of revisiting was zero. With
twenty-five domain tasks ahead, the cost of revisiting will only grow. The
moment to lock the pattern is now, before the second slice ships.

Three forces shape the decision:

1. **Multi-tenant correctness.** Every query against tenant-scoped data must
   carry a tenant filter. ADR-002 already requires explicit joins (no
   `relationship()`). Without a structural home for queries, the policy is a
   convention; a forgotten filter is a PHI breach. Centralizing queries in a
   per-aggregate Repository class makes the audit surface scannable and turns
   the policy into something a code reviewer can verify by opening one file.

2. **Audit atomicity.** SPEC-006 §7 requires that every create/update/delete on
   a domain entity write an `AuditLog` row in the same transaction. The current
   `call_service_with_audit` wrapper achieves this for success paths but does
   not address failure-path audits (the request transaction has rolled back by
   the time anyone could write one). Failure audits demand a fresh session
   owned by the route-level exception handler — not a service-layer concern.

3. **Invariant locality.** The Organization slice currently spreads invariants
   across three layers: regex patterns in Pydantic schemas (router boundary),
   field mapping in service helpers (`_ADDRESS_FIELD_MAP`), and column types in
   the model. A reader must hold all three in mind to reason about whether an
   Organization is well-formed. Pulling invariants onto the model — `@validates`
   for field shape, `CheckConstraint` for SQL-level invariants, partial unique
   indexes for revocability rules, instance mutators for state transitions,
   `@classmethod` factories for non-trivial construction — gives the entity a
   single home. The Pydantic schema becomes a translation layer at the HTTP
   boundary, not a duplicate source of truth.

ADR-002 forward-referenced "a future ADR on `BaseRepository` (where the
explicit-join policy is operationalized)." This ADR is that document, with one
deviation: there is no `BaseRepository`. A generic base would abstract away the
joins ADR-002 mandates be explicit. The operationalization is a per-aggregate
class, not a base class.

## Decision

Four-layer architecture. Dependencies flow in one direction:

```
router → service → repository → model
```

### Router

A thin HTTP layer. Per spec domain (one file, multiple endpoints).

- Parses the request, validates with a Pydantic schema, calls one Service
  method via `Depends`, serializes the response with a Pydantic schema.
- Does not contain business logic. Does not call repositories directly. Does
  not commit. Does not import SQLAlchemy.
- Does not catch domain exceptions. The route-level FastAPI exception handler
  registered on `app` startup is the single owner of domain-exception → HTTP
  translation and failure-audit writes (see "Failure audits" below).

### Service

A class per aggregate (`<Aggregate>Service`, one class per file under
`services/`).

- Constructor takes its repositories, an `AuditWriter`, a lifecycle dispatcher
  (where applicable), `tenant_id: UUID`, and `actor_id: UUID | None`. All via
  `Depends`. No service constructs its own collaborators.
- Orchestrates the use case: load via repository → mutate via model methods →
  persist via repository → write success audit via `AuditWriter`.
- Does not commit. Does not import `select()` or call `session.execute()`.
  Does not raise `HTTPException`. Raises domain exceptions
  (subclasses of `GroundworkError`).
- Method names are use-case verb phrases (`create_organization`,
  `archive_entity_type`, `void_invoice`).

### Repository

A class per aggregate (`<Aggregate>Repository`, one class per file under
`repositories/`).

- Constructor takes an `AsyncSession` via `Depends(get_db)`. That is the only
  dependency.
- Owns every `select` / `insert` / `update` / `delete` and every explicit join
  (preserving ADR-002 — no `relationship()`, no `back_populates`).
- Returns Model instances. Does not commit. Does not enforce business rules.
  Does not write audit.
- Method names follow intent: `get`, `list_for_<scope>`, `find_by_<field>`
  for reads; `save` for writes (delete is rare; soft-delete via a model
  mutator is the usual path).

### Model

SQLAlchemy ORM class. The Model **is** the domain entity. There is no separate
domain layer. Per spec domain (one file, multiple model classes).

- **Schema:** FK-only columns (ADR-002), mixins, `__table_args__`.
- **Invariants:**
  - `@validates(...)` for field-level shape (length, format, case).
  - `CheckConstraint(...)` for SQL-level invariants.
  - Partial unique indexes (`postgresql_where=...`) for revocability rules
    (ADR-003).
  - Instance mutator methods that guard state transitions
    (`org.deactivate()`, `invoice.void()`, `note.sign(by=person_id)`).
    Mutators raise domain exceptions on guard violations.
  - `@classmethod` factories named after intent
    (`Organization.from_signup(data)`, `Invoice.from_session(session)`)
    where bare `Cls(...)` requires non-trivial mapping.
- Mutation happens in place within the service's transaction scope. The
  repository's `save` flushes; `get_db` commits.

### Pydantic schemas

Live at the router boundary only. Never imported in services or repositories.

- `<Aggregate>Create`, `<Aggregate>Update`, `<Aggregate>Response` per aggregate
  in `schemas/<domain>.py`.
- Cross-cutting schemas (pagination, error envelope) in
  `schemas/<purpose>.py` — `pagination.py`, `errors.py`.

### Transactions

`get_db` (in `core/dependencies.py`) owns the transaction lifecycle: commit on
successful return, rollback on exception. **Nothing else commits.** Services
and repositories do not call `await session.commit()` or
`await session.rollback()`. Atomicity comes from the dependency, not from a
wrapper.

### Audit (success path)

`AuditWriter` is an injected collaborator on every service that mutates state.

- Constructor takes the same `AsyncSession` the service operates in (the
  request session) plus an `_AuditScope` (org_id, actor_id, ip_address,
  user_agent).
- `await self._audit.write(action=..., resource_type=..., resource_id=...,
  previous_state=..., next_state=...)` adds an `AuditLog` row to the request
  session and flushes. The dependency commits both rows together.
- PHI is filtered before write via `core/phi.filter_phi`.

### Audit (failure path)

The route-level FastAPI exception handler for `GroundworkError` writes a
**failure audit** in a **fresh session** (not the rolling-back request
session), then translates to HTTP.

- `GroundworkError` carries optional audit-context kwargs:
  `audit_action`, `audit_entity_type`, `audit_entity_id`, `audit_actor_id`.
  Subclasses with structural context (`NotFoundError`, `ForbiddenError`,
  `StateTransitionDeniedError`) populate them automatically; ad-hoc raises
  may pass them at the call site.
- The handler opens a new session via `Database.get_session_factory()`,
  constructs an `AuditWriter` with `outcome="failure"`, writes the row,
  commits, and closes — independent of the request transaction.
- Domain exceptions never write audit themselves. Services raise; the handler
  audits and translates.

### Tenant and actor context

`tenant_id: UUID` and `actor_id: UUID | None` enter services as primitive
UUIDs in the constructor. Forward reference: ADR-008 (reserved) is expected to
introduce structured `TenantContext` / `ActorContext` objects when
TASK-014 (auth middleware) and TASK-015 (permission resolution) land. Until
then, primitive UUIDs are the contract.

### What this architecture is not

- **No `BaseRepository`.** A generic base would invert the explicit-join
  policy. Each `<Aggregate>Repository` writes its own queries.
- **No `BaseService`.** Cross-cutting concerns (audit, lifecycle) are
  injected, not inherited.
- **No separate domain entity layer.** The Model is the entity. Invariants
  live on the Model.
- **No `relationship()`** anywhere — preserves ADR-002.

### File-layout corollaries

The architecture imposes a folder layout that is part of the decision, not a
separate document.

```
backend/app/
├── main.py                    framework-required boilerplate
├── core/                      single-purpose, no subdirectories
│   ├── config.py              app config (settings)
│   ├── database.py            async engine + session factory + Base + mixins
│   ├── dependencies.py        cross-cutting Depends factories
│   ├── exceptions.py          GroundworkError + subclasses
│   ├── lifespan.py            FastAPI lifespan
│   ├── logger.py              structlog config
│   ├── pagination.py          cursor pagination utility
│   ├── phi.py                 PHI_EXCLUDED_FIELDS + filter_phi
│   ├── request_logger.py      ASGI middleware
│   └── security.py            auth context + permission stubs
├── enums/                     one file per spec domain
│   └── <domain>.py            multiple StrEnum classes
├── models/                    one file per spec domain
│   └── <domain>.py            multiple ORM classes
├── repositories/              one file per aggregate
│   └── <aggregate>_repository.py   one Repository class
├── routers/                   one file per spec domain
│   └── <domain>.py            FastAPI routes
├── schemas/                   one file per domain or shared purpose
│   ├── <domain>.py            domain Pydantic models
│   ├── pagination.py          shared pagination shapes
│   └── errors.py              shared error envelope
└── services/                  one file per aggregate
    └── <aggregate>_service.py one Service class
```

`<domain>` is the spec domain (`eav`, `identity`, `scheduling`, `clinical`,
`billing`, `compliance`). `<aggregate>` is the singular domain entity
(`organization`, `entity_type`, `client`, `invoice`).

The asymmetry — multi-class per spec for models/schemas/enums, one-class per
aggregate for services/repositories — is deliberate. Models, schemas, and
enums often share imports and concepts within a spec domain; bundling them
reduces import noise. Services and repositories own behavior per aggregate;
splitting them keeps each file under cognitive load.

### Class and function naming

| Kind | Pattern | Examples |
|---|---|---|
| Service class | `<Aggregate>Service` | `OrganizationService` |
| Repository class | `<Aggregate>Repository` | `OrganizationRepository` |
| Model class | `<Aggregate>` | `Organization`, `Invoice` |
| Schema class | `<Aggregate>Create / Update / Response` | `OrganizationResponse` |
| Enum class | `<Concept>` | `SessionStatus`, `InvoiceStatus` |
| Domain exception | `<Concept>Error` or `<Aggregate><State>` | `TenantMismatch`, `OrganizationAlreadyInactive` |
| Collaborator | `<Concept>Writer / Dispatcher / Client` | `AuditWriter`, `LifecycleDispatcher`, `S3Client` |
| Depends factory | `get_<thing>` | `get_db`, `get_organization_service` |
| Model mutator | imperative verb | `org.deactivate()`, `invoice.void()` |
| Model factory | `@classmethod` named after intent | `Organization.from_signup(data)` |
| Repository read | `get` / `list_for_<scope>` / `find_by_<field>` | `repo.list_for_tenant(tid, params)` |
| Repository write | `save` (delete rare; prefer mutator + soft-delete) | `repo.save(org)` |
| Service method | use-case verb phrase | `service.create_organization(data)` |
| Lifecycle hook registration | `register_post_<event>` / `register_pre_<event>` | `lifecycle.register_post_create(fn)` |
| Lifecycle hook callback | `on_<event>` | `lifecycle.on_create(session, org_id)` |

### Forbidden names

- **Filenames:** `common.py`, `utils.py`, `helpers.py`, `misc.py`, `lib.py`,
  `shared.py`, `manager.py`, `handler.py`, `processor.py`, `worker.py`,
  `_lifecycle.py`, `_hooks.py`, `_transaction.py`.
- **Class names:** `BaseService`, `BaseRepository`, `GenericRepository`,
  `<X>Manager`, `<X>Helper`, `<X>Util`.
- **Folders:** `helpers/`, `utils/`, `common/`, `lib/`, `misc/`, `managers/`,
  `handlers/`, `processors/`, `middleware/`.

If code does not fit a category, the answer is never a new folder or a generic
file name. Either the code belongs in an existing category (find which) or it
introduces a cross-cutting concern that requires an architectural decision —
escalated as a new ADR, not a file.

### No module-level mutable state (governed files)

Files under `services/`, `repositories/`, `models/`, `enums/`, and `schemas/`
declare no top-level data: lookup dicts, allowlists, registries, type aliases,
regex patterns used by `Field(pattern=...)`, and `__all__` all live inside
the function, class, or `Field(...)` call that uses them. State that must
persist between calls (callback registries) is encapsulated as a class
attribute on a private class in the same file; the singleton instance is
created by an `lru_cache`d factory in `core/dependencies.py`, not by
module-level binding.

Imports, function defs, and class defs are not "variables" for this rule.
Framework-required boilerplate (`alembic/env.py`, `app/main.py`, Alembic
migration `revision` / `down_revision`) is out of scope.

## Consequences

**For:**
- Tenant filters are enforced at every query construction site — and there is
  exactly one site per aggregate (the `<Aggregate>Repository`). A reviewer
  audits one file, not a service.
- Invariants live with the entity. A reader of `Organization` sees field
  validation, state transitions, and SQL constraints in one place.
- Audit atomicity is a structural property: success audits ride the request
  transaction; failure audits ride a fresh transaction owned by the handler.
  Neither path can be skipped by forgetting a wrapper call.
- The router-handler-service-repository-model layering matches FastAPI's grain:
  routes are thin, dependencies inject collaborators, services orchestrate,
  repositories query, models hold state. Each layer has one responsibility.
- The path forward when complexity grows (sagas, projections, read models) is
  to introduce a new ADR for the new concern, not to retrofit a generic base
  class.

**Against:**
- Four layers means more files per slice. A trivial CRUD slice creates a
  router endpoint, a service class, a repository class, and a model — plus
  schemas. The cost is paid once per aggregate; the benefit accrues for the
  life of the codebase.
- Mutator methods on the Model demand discipline. They must stay thin
  (state transition + invariant guard), not grow into use-case orchestration.
  Use-case orchestration belongs on the Service. A failure mode is a Model
  method that loads from a repository or writes audit — both are forbidden.
- The `OrganizationService` cannot be tested in isolation without injecting a
  real `AuditWriter` (or a fake). The codebase does not mock the database
  (CLAUDE.md "No mocks in tests"); audit writes are part of the
  integration-tested transaction. This is the same posture as before; what
  changes is the explicit injection rather than a wrapper helper.

## Alternatives considered

**Full DDD with separate domain entities mapped to ORM.** Two layers of
classes (entity + ORM) means a mapping pass on every load and persist. The
domain complexity does not warrant the cost: most aggregates have invariants
expressible in `@validates` / `CheckConstraint` / mutator methods directly on
the ORM class. Rejected.

**Pure no-repository mainstream FastAPI (services hold queries inline).**
Queries scatter across services. ADR-002's explicit-join policy becomes a
convention with no structural enforcement — a reviewer must audit every
service touching a given table. Rejected: explicit query centralization is
exactly the property the ADR-002 rationale demands.

**Generic `BaseRepository` with a query-builder DSL.** A base class abstracts
joins behind helper methods (`base.find_with_org_filter(...)`). The joins
ADR-002 mandates be explicit are now hidden inside a base class. The
escape-hatch when a repository needs an unusual query is to drop into raw
SQLAlchemy, at which point the base class becomes parallel infrastructure
rather than a single source of truth. Rejected.

**Keep TASK-008A's plain-async-function services with the
`call_service_with_audit` wrapper.** Function services have no constructor,
so collaborators can't be injected; every dependency is a positional argument
on every call. As the dependency list grows (audit, lifecycle, tenant
context, future S3 client, future feature flags), every signature in the
service mushrooms. The class-with-constructor form scales; the
function-with-positional-args form does not. Rejected.

## References

- ADR-001 — hybrid EAV + concrete data model.
- ADR-002 — no `relationship()`; FK-only with explicit joins (amended
  2026-05-09 to align with this ADR).
- ADR-003 — partial unique indexes for revocable records (operationalized
  here as a Model-level invariant).
- ADR-008 — reserved for future TenantContext / ActorContext decision
  (TASK-014, TASK-015).
- TASK-008A (rewritten 2026-05-09) — service & router conventions, now
  pointing at this ADR as authority.
- SPEC-006 §7 — audit-log atomicity requirement.
- SPEC-007 §10, §12 — service architecture and testing posture.
- Code anchor: the Organization slice (`backend/app/routers/eav.py`,
  `services/organization_service.py`,
  `repositories/organization_repository.py`,
  `models/eav.py`) is the canonical reference implementation.
