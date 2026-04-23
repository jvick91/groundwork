# STATE.md — Session Entry Point

**Last updated:** 2026-03-26
**Active task:** TASK-004
**Branch:** error-response-contract

---

## How to use this file

1. Find your active task or the next unclaimed one below.
2. Read the task file in `tasks/`.
3. Read the spec sections and ADRs cited by the task.
4. Write failing tests first, then implementation.
5. On completion: write a log in `task-logs/`, mark the task complete here, commit.

---

## Task Index

### Phase 1: Foundation & Cross-Cutting

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 001 | [Project scaffolding & Docker services](tasks/TASK-001-project-scaffolding.md) | **Complete** | — |
| 002 | [Base ORM patterns, enums, Alembic config](tasks/TASK-002-base-orm-patterns.md) | **Complete** | 001 |
| 003 | [Error response contract & exception handling](tasks/TASK-003-error-response-contract.md) | **Complete** | 001 |
| 004 | [Cursor pagination utility](tasks/TASK-004-cursor-pagination.md) | Partial | 001, 003 |
| 005 | [Health check endpoints](tasks/TASK-005-health-check-endpoints.md) | Partial | 001 |
| 006 | [AuditLog model & audit service](tasks/TASK-006-audit-log-model-and-service.md) | Partial | 001, 002 |
| 007 | [Structured logging & PHI exclusion filter](tasks/TASK-007-structured-logging-phi-filter.md) | Partial | 001 |
| 008 | [Test infrastructure & fixtures](tasks/TASK-008-test-infrastructure.md) | Partial | 001, 002, 003, 007 |
| 008A | [Service & router layer conventions (shared plumbing only)](tasks/TASK-008A-service-router-conventions.md) | Partial | 002, 003, 004, 006, 007, 008 |

**Partial status notes:**
- **003:** 7 exception classes exist (`GroundworkError`, `NotFoundError`, `ValidationError`, `ConflictError`, `ForbiddenError`, `OrganizationRequiredError`, `BridgeRuleViolation`, `StatusTransitionError`) + `ErrorResponse` schema + handler in `main.py`. Missing: `ResourceLockedError`, `PrerequisiteNotMetError`, `AccountInactiveError`, `UnauthorizedError`, `BadRequestError`, `OrgAccessDeniedError`, `RateLimitedError`, `InternalError`; Pydantic 422 handler; generic 500 handler. Error code `status_transition_error` should be `state_transition_denied` per SPEC-007.
- **004:** Pagination schemas exist (`PaginationMeta`, `PaginatedResponse`). Missing: request query-parameter model, Base64 cursor encode/decode, sort-field allow-list, query-builder, filter conventions.
- **005:** Basic `/health` endpoint + test exist but response is `{"status": "healthy", ...}` — rename to `"ok"` per spec. Missing: extract to `app/routers/health.py`, `/health/ready` with DB check, DB-degraded tests. JWKS probe is owned by TASK-014.
- **006:** AuditLog model (`models.py:686`) + `audit_logs` table shipped via TASK-002 scope expansion with correct immutable-row schema. Missing: audit service (`log_action`, PHI filtering, transactional rollback), DB-level UPDATE/DELETE rejection, list/detail endpoints, tests.
- **007:** structlog + `phi_filter` with 7 fields. Missing: full BR-08 field list (note content keys: subjective, objective, assessment, plan, data, intervention, response, behavior; plus `ClientConsent.notes`, `Document` free-text, `AttributeValue.value`), request logging middleware, the two named tests.
- **008:** conftest with transaction rollback, httpx client, factory scaffold (`tests/factories/app_factory.py`, `tests/factories/crud_factory.py`), per-domain test directories. Missing: JWT test key material + token-minting fixture, per-domain factories, `pytest.ini`/`pyproject.toml` coverage config with `--cov-fail-under=90`. (Wiring the middleware to validate against the test key is in TASK-014.)
- **008A:** `get_db` dependency shipped. `get_auth_context` and `require_permission` scaffolds exist in `app/core/security.py` but **raise 501 instead of allow-listing** — need `AUTH_STUB_ENABLED` flag + stub behavior. Missing: named `current_person` / `current_org` dependencies, `app/services/common.py` with `call_service_with_audit`, `app/utils/pagination.py` surface, router convention doc, `docs/conventions.md`, tests.

**TASK-002 scope expansion (recorded 2026-04-23):** TASK-002 shipped the entire 26-table schema in a single initial migration and defined every domain model in `backend/app/models/models.py`. See `tasks/TASK-002-base-orm-patterns.md` for the full inventory. Downstream domain tasks (006, 009, 010, 011C, 012, 013, 020, 021, 023, 025, 026, 027, 029, 030, 031, 032) have been re-scoped to tick off the model + initial migration ACs and now carry a **Pre-existing artifacts** section calling out what remains (schemas, services, routers, lifecycle rules, seed data, partial indexes where absent, tests).

### Phase 2: EAV Data Platform (SPEC-001)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 009 | [Organization model & CRUD API (first vertical slice)](tasks/TASK-009-organization-model-and-api.md) | Not started | 004, 008A |
| 010 | [EntityType & EntityAttribute models, seed data, & API](tasks/TASK-010-entity-type-attribute-models-api.md) | Not started | 004, 009 |
| 011 | [EntityInstance & AttributeValue (container — not executable)](tasks/TASK-011-entity-instance-attribute-value-api.md) | Container | — |
| ↳ 011A | [AttributeValue type casting engine (shape only; fk existence hook deferred)](tasks/TASK-011A-attribute-value-type-casting.md) | Not started | 010 |
| ↳ 011C | [EntityInstance & AttributeValue models, migration, CRUD, bridge rules](tasks/TASK-011C-entity-instance-crud-api.md) | Not started | 004, 011A, 008A |
| ↳ 011B | [JSONB aggregation query builder + GET list swap](tasks/TASK-011B-jsonb-aggregation-query.md) | Not started | 011C |

> **Parallelization note:** Phase 3 (Identity & RBAC) does **not** block on Phase 2 finishing. Once TASK-009 is complete, TASK-012 (Person) and TASK-013 (RBAC seed) can start in parallel with TASK-010/011A/B/C (EAV). Only TASK-014 (auth middleware) and later identity tasks require both Phase 2 and early Phase 3 foundations. The phase ordering below reflects conceptual grouping, not a strict sequential gate.

### Phase 3: Identity & RBAC (SPEC-002)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 012 | [Person model & CRUD API](tasks/TASK-012-person-model-and-api.md) | Not started | 004, 009, 006, 008 |
| 013 | [RBAC models & seed data](tasks/TASK-013-rbac-models-and-seed-data.md) | Not started | 009, 012 |
| 014 | [Auth middleware — JWT, person resolution, org context](tasks/TASK-014-auth-middleware.md) | Not started | 012, 013 |
| 015 | [Permission resolution, caching, & row-level filtering](tasks/TASK-015-permission-resolution-and-caching.md) | Not started | 013, 014 |
| 016 | [Role & permission management API](tasks/TASK-016-role-permission-management-api.md) | Not started | 013, 015 |
| 017 | [Person role assignment API](tasks/TASK-017-person-role-assignment-api.md) | Not started | 012, 013, 015 |
| 018 | [Auth self-inspection endpoints](tasks/TASK-018-auth-self-inspection.md) | Not started | 014, 015 |
| 019 | [Auto-permission generation on EntityType creation](tasks/TASK-019-auto-permission-generation.md) | Not started | 010, 013 |

### Phase 4: Scheduling & Sessions (SPEC-003)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 020 | [AppointmentType model & API](tasks/TASK-020-appointment-type-model-and-api.md) | Not started | 004, 009, 015, 025 |
| 021 | [Session model & CRUD API](tasks/TASK-021-session-model-and-crud-api.md) | Not started | 004, 011C, 015, 020 |
| 022 | [Session lifecycle transitions & overlap detection](tasks/TASK-022-session-lifecycle-and-overlap.md) | Not started | 006, 021 |

### Phase 5: Clinical Notes (SPEC-004)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 023 | [ClinicalNote model & CRUD API](tasks/TASK-023-clinical-note-model-and-crud-api.md) | Not started | 004, 021, 015 |
| 024 | [Note lifecycle — sign, cosign, amend](tasks/TASK-024-note-lifecycle-sign-cosign-amend.md) | Not started | 023 |

### Phase 6: Billing & Payments (SPEC-005)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 025 | [CPTCode & ICDCode models & API](tasks/TASK-025-cpt-icd-code-models-and-api.md) | Not started | 004, 009, 015 |
| 026 | [InsurancePayer & ClientInsurance models & API](tasks/TASK-026-insurance-payer-client-insurance-api.md) | Not started | 004, 011C, 015 |
| 027 | [Invoice & InvoiceLineItem models & CRUD API](tasks/TASK-027-invoice-line-item-models-and-api.md) | Not started | 004, 021, 025, 015 |
| 028 | [Invoice lifecycle, payment recording, & void](tasks/TASK-028-invoice-lifecycle-payment-void.md) | Not started | 006, 026, 027 |

### Phase 7: Documents, Consent, & Compliance (SPEC-006)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 029 | [DocumentType & ConsentType models, seed data, & API](tasks/TASK-029-document-type-consent-type-models-api.md) | Not started | 004, 009, 015 |
| 030 | [Document model & S3 upload flow API](tasks/TASK-030-document-model-and-upload-flow.md) | Not started | 004, 012, 021, 023, 027, 029 |
| 031 | [ClientConsent model & lifecycle API](tasks/TASK-031-client-consent-model-and-lifecycle.md) | Not started | 004, 006, 011C, 029, 030, 032 |
| 032 | [FormTemplate model & API](tasks/TASK-032-form-template-model-and-api.md) | Not started | 004, 009, 015 |
| 033 | [Consent session gate & expiry sweep](tasks/TASK-033-consent-session-gate-and-expiry-cron.md) | Not started | 022, 031 |

### Phase 8: Cross-Cutting Verification (SPEC-007)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 034 | [Database indexing migration](tasks/TASK-034-database-indexing.md) | Not started | 011C, 013, 020, 021, 023, 025, 026, 027, 028, 029, 030, 031, 032 |
| 035 | [Cross-cutting integration tests](tasks/TASK-035-cross-cutting-integration-tests.md) | Not started | 003, 004, 006, 007, 008, 011C, 014, 015, 021, 023, 027, 030, 031 |
| 036 | [CI pipeline configuration](tasks/TASK-036-ci-pipeline.md) | Not started | 008 |
| 037 | [CORS & security hardening](tasks/TASK-037-cors-and-security-hardening.md) | Not started | 001, 006, 007, 014 |
| 038 | [HIPAA-ready acceptance gate verification](tasks/TASK-038-hipaa-ready-acceptance-verification.md) | Not started | 013, 014, 029, 030, 035 |

---

## Implementation Milestones

### Milestone 1 — Auth Gate (foundation for all protected endpoints)
**Tasks:** 003 (finish) → 006 → 007 (finish) → 008 (finish) → 008A → 013 → 014 → 015
**Unlocks:** Every domain API endpoint

### Milestone 2 — EAV API (first full domain)
**Tasks:** 009 → 010 → 011A → 011C → 011B → 019
**Unlocks:** Entity management, dynamic permissions. Note: 011C owns the EntityInstance/AttributeValue models and ships a naive GET list; 011B swaps it to JSONB aggregation after 011C is live. 019 flips the `CUSTOM_ENTITY_TYPES_ENABLED` flag introduced in 010.

### Milestone 3 — Identity API (platform foundation complete)
**Tasks:** 012 → 016 → 017 → 018
**Unlocks:** User management, role assignment, self-inspection

### Milestone 4 — Clinical Flow (core business workflow)
**Tasks:** 020 → 021 → 022 → 023 → 024 → 033
**Unlocks:** Scheduling → notes → signed documentation

### Milestone 5 — Billing + Compliance (can parallelize)
**Tasks:** 025-028 (billing) ∥ 029-032 (compliance)
**Unlocks:** Invoicing, payments, documents, consents, forms

---

## Dependency Graph (Critical Path)

```
001 ✓ → 002 ✓ → 006 ──→ 008A (plumbing) ──→ 009 (Org) → 010 ──→ 011A → 011C → 011B
  │                ↑              ↑
  ├→ 003 (finish)──┤         008 (finish)
  ├→ 007 (finish)──┘              ↓
  │                          013 (seed) → 014 (auth) → 015 (perms)
  │                            ↑                         ↓
  ├→ 012 (Person) ─────────────┘                   016, 017, 018, 019
  │
  ├→ 025 (codes) ─→ 020 (appt type) → 021 → 022 ──→ 033 (consent gate)
  │       ↘                                               ↑
  │        → 027 (invoice) → 028                    031 (consent)
  │        ↗                                              ↑
  ├→ 026 (insurance)                                 029 (types, seeds to 009 hook)
  │                                                       ↑
  ├→ 023 → 024 (notes)                             030 (documents) ──┤
  │                                                 032 (forms, seeds to 009 hook) ──┘
  │
  └→ 034 (indexes), 035 (tests), 036 (CI), 037 (CORS + 006,007), 038 (HIPAA gate)
```

**Critical path:** 001✓ → 002✓ → 006 → 008A → 009 → 010 → 011A → 011C → 013 → 014 → 015 → 025 → 020 → 021 → 022 → 031 (after 029, 030, 032) → 033

Note: 025 is on the session critical path because AppointmentType.cpt_code_id FKs into CPTCode. 029/030/032 all precede 031 because ClientConsent FKs into DocumentType, Document, and FormTemplate.

Note: TASK-004 (cursor pagination) is an explicit upstream for every domain CRUD task (009, 010, 011C, 012, 020, 021, 023, 025, 026, 027, 029, 030, 031, 032) — their list endpoints consume the pagination utility directly. The graph above omits those edges for readability; see each task's `Depends on:` header for the authoritative list.

---

## Service & Router Conventions (established in TASK-008A, first exercised in TASK-009)

### Router layer
- One file per domain in `app/routers/`, registered via `app.include_router()` in `main.py`
- No SQLAlchemy imports, no business logic, no direct DB access
- Permission: `Depends(require_permission("slug"))`
- Calls service functions, returns Pydantic response models

### Service layer
- Plain async functions in `app/services/` — not classes
- Signature: `async def create_X(db: AsyncSession, org_id: UUID, data: CreateSchema) -> Model`
- `db` passed from router dependency — service never creates its own session
- Raises domain exceptions from `app.core.exceptions`
- Calls `audit_service.log_action()` in the same session before commit

### Audit integration
- `await audit_service.log_action(db, org_id, actor_id, action, resource_type, resource_id, prev, next)`
- PHI exclusion applied automatically by audit service
- Same session = atomic with business operation

---

## Spec Coverage Matrix

| Spec | Sections | Covered by tasks |
|------|----------|-----------------|
| SPEC-000 | §2 | 001 ✓ |
| SPEC-000 | §3 | 002 ✓ |
| SPEC-000 | §4 | Domain tasks |
| SPEC-000 | §5 | 008, 035 |
| SPEC-000 | §6 | 006, 007, 030, 031, 033 |
| SPEC-001 | §2-§3 | 009, 010 |
| SPEC-001 | §4-§5 | 010, 011A, 011B, 011C |
| SPEC-001 | §6 | 009, 010, 011C |
| SPEC-001 | §7, §9 | 010, 011A, 011C |
| SPEC-002 | §2-§3 | 012, 013 |
| SPEC-002 | §4-§6 | 015, 016, 017 |
| SPEC-002 | §7 | 019 |
| SPEC-002 | §8 | 012, 016, 017, 018 |
| SPEC-002 | §9, §11 | 014, 015, 016, 017 |
| SPEC-003 | §1-§2 | 020, 021 |
| SPEC-003 | §3-§5 | 021, 022 |
| SPEC-003 | §6-§7, §9 | 020, 021, 022 |
| SPEC-004 | §1-§3 | 023 |
| SPEC-004 | §4-§6 | 024 |
| SPEC-004 | §7-§8, §10 | 023, 024 |
| SPEC-005 | §1-§2 | 025, 026, 027, 028 |
| SPEC-005 | §3-§4 | 027, 028 |
| SPEC-005 | §5-§6, §8 | 025, 026, 027, 028 |
| SPEC-006 | §1-§2 | 006, 029, 030, 031, 032 |
| SPEC-006 | §3-§4 | 006, 007, 029, 030, 031, 032, 033 |
| SPEC-006 | §5-§6 | 006, 029, 030, 031, 032 |
| SPEC-006 | §7, §9 | 006, 030, 031, 033 |
| SPEC-007 | §2-§3 | 001 ✓, 014, 015, 018 |
| SPEC-007 | §4-§6 | 002 ✓, 003, 004 |
| SPEC-007 | §7 | 003 |
| SPEC-007 | §8 | Verified across domain tasks |
| SPEC-007 | §9 | 005 |
| SPEC-007 | §10, §12 | 001 ✓, 008A |
| SPEC-007 | §11 | 034 |
| SPEC-007 | §13 | 008, 035 |
| SPEC-007 | §14 | 036 |
| SPEC-007 | §15 | 037 |
| SPEC-000 | §6 | 038 (composite); underlying controls in 013, 014, 029, 030, 035 |
