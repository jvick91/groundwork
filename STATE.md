# STATE.md — Session Entry Point

**Last updated:** 2026-05-21
**Active task:** TASK-011A (next — AttributeValue type casting engine, on the new ADR-009 pattern). Auth chain (TASK-014 series) is being designed in parallel on branch `task-014-auth-decomposition`.
**Branch:** main (auth-chain design work lives on `task-014-auth-decomposition`)
**Last architectural change:** 2026-05-21 — Auth chain decomposed. ADR-010 (consolidated Auth0 identity architecture: Organizations adopted, universal WebAuthn MFA, 5–15min access tokens + refresh rotation, nonce-only first-login binding, single-connection-per-user for MVP, ServicePrincipal deferred). ADR-011 (invitation lifecycle: PersonRole-at-accept; five-type discriminator; uniform response shape for enumeration mitigation). ADR-012 (`Person.permissions_version` column for zero-staleness permission cache). ADR-008 superseded by ADR-010. TASK-014 decomposed into TASK-014A–014J. Net schema delta for the full auth chain: +1 table (`Invitation`), +1 column (`Person.permissions_version`), +4 seed permissions (`invites.send/revoke/read`, `auth.force_revoke`). All other auth work is Auth0-side configuration or backend code.

**Previous architectural change:** 2026-05-09 — ADR-009 accepted; ADR-002 amended; Organization (TASK-009) and EntityType / EntityAttribute (TASK-010) refactored to class-per-aggregate Service + Model-as-Entity. AuditLog gained an `outcome` column. The route-level `GroundworkError` handler now writes failure audits in a fresh session. TASK-008A rewritten as the canonical conventions doc; all not-yet-shipped tasks reference ADR-009. **Same-day amendment:** Repository layer removed — each repo was a thin SQL wrapper called from one service; queries now inline in the service file under a `# Query helpers` section. Re-introduce a Repository only when queries are genuinely shared across services (e.g. role-hierarchy walks, JSONB projections).

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
| 004 | [Cursor pagination utility](tasks/TASK-004-cursor-pagination.md) | **Complete** | 001, 003 |
| 005 | [Health check endpoints](tasks/TASK-005-health-check-endpoints.md) | **Complete** | 001 |
| 006 | [AuditLog model & audit service](tasks/TASK-006-audit-log-model-and-service.md) | **Complete** | 001, 002 |
| 007 | [Structured logging & PHI exclusion filter](tasks/TASK-007-structured-logging-phi-filter.md) | **Complete** | 001 |
| 008 | [Test infrastructure & fixtures](tasks/TASK-008-test-infrastructure.md) | **Complete** (per-domain factories deferred) | 001, 002, 003, 007 |
| 008A | [Service & router layer conventions (shared plumbing only)](tasks/TASK-008A-service-router-conventions.md) | **Complete** | 002, 003, 004, 006, 007, 008 |
| 008B | [CI pipeline configuration (GitHub Actions: lint, type check, tests, build)](tasks/TASK-008B-ci-pipeline.md) | **Complete** (branch protection is a manual GH setting) | 001, 002, 007, 008, 008C |
| 008C | [Linter & type-check configuration (ruff + mypy strict in pyproject.toml)](tasks/TASK-008C-linter-config.md) | **Complete** | 001 |

**Partial status notes:**
- **003:** 7 exception classes exist (`GroundworkError`, `NotFoundError`, `ValidationError`, `ConflictError`, `ForbiddenError`, `OrganizationRequiredError`, `BridgeRuleViolation`, `StatusTransitionError`) + `ErrorResponse` schema + handler in `main.py`. Missing: `ResourceLockedError`, `PrerequisiteNotMetError`, `AccountInactiveError`, `UnauthorizedError`, `BadRequestError`, `OrgAccessDeniedError`, `RateLimitedError`, `InternalError`; Pydantic 422 handler; generic 500 handler. Error code `status_transition_error` should be `state_transition_denied` per SPEC-007.
- **004:** Pagination schemas exist (`PaginationMeta`, `PaginatedResponse`). Missing: request query-parameter model, Base64 cursor encode/decode, sort-field allow-list, query-builder, filter conventions.
- **005:** Basic `/health` endpoint + test exist but response is `{"status": "healthy", ...}` — rename to `"ok"` per spec. Missing: extract to `app/routers/health.py`, `/health/ready` with DB check, DB-degraded tests. JWKS probe is owned by TASK-014.
- **006:** AuditLog model (`models.py:686`) + `audit_logs` table shipped via TASK-002 scope expansion with correct immutable-row schema. Missing: audit service (`log_action`, PHI filtering, transactional rollback), DB-level UPDATE/DELETE rejection, list/detail endpoints, tests.
- **007:** structlog + `phi_filter` now consume the centralized `PHI_EXCLUDED_FIELDS` from `app/core/phi.py` (TASK-006 amendment 2026-04-23). Full BR-08 field list is covered: clinical-note format keys (`subjective`, `objective`, `assessment`, `plan`, `data`, `intervention`, `response`, `behavior`), demographic aliases (`dob`/`date_of_birth`, `ssn`/`social_security`), free-text fields (`notes`, `description`, `content`, `note_content`), EAV (`value`), billing codes (`diagnosis_codes`, `icd_codes`), and emergency contact fields. Missing: request logging middleware (method, path, status, duration); the two named tests from the SPEC-006 §9 table.
- **008:** conftest with transaction rollback, httpx client, factory scaffold (`tests/factories/app_factory.py`, `tests/factories/crud_factory.py`), per-domain test directories. Missing: JWT test key material + token-minting fixture, per-domain factories, `pytest.ini`/`pyproject.toml` coverage config with `--cov-fail-under=90`. (Wiring the middleware to validate against the test key is in TASK-014.)
- **008A:** `get_db` dependency shipped. `get_auth_context` and `require_permission` scaffolds exist in `app/core/security.py` but **raise 501 instead of allow-listing** — need `AUTH_STUB_ENABLED` flag + stub behavior. Missing: named `current_person` / `current_org` dependencies, `app/services/common.py` with `call_service_with_audit`, `app/utils/pagination.py` surface, router convention doc, `docs/conventions.md`, tests.

**TASK-002 scope expansion (recorded 2026-04-23):** TASK-002 shipped the entire 26-table schema in a single initial migration and defined every domain model in `backend/app/models/models.py`. See `tasks/TASK-002-base-orm-patterns.md` for the full inventory. Downstream domain tasks (006, 009, 010, 011C, 012, 013, 020, 021, 023, 025, 026, 027, 029, 030, 031, 032) have been re-scoped to tick off the model + initial migration ACs and now carry a **Pre-existing artifacts** section calling out what remains (schemas, services, routers, lifecycle rules, seed data, partial indexes where absent, tests).

### Phase 2: EAV Data Platform (SPEC-001)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 009 | [Organization model & CRUD API (first vertical slice)](tasks/TASK-009-organization-model-and-api.md) | **Complete** | 004, 008A |
| 010 | [EntityType & EntityAttribute models, seed data, & API](tasks/TASK-010-entity-type-attribute-models-api.md) | **Complete** | 004, 009 |
| 011 | [EntityInstance & AttributeValue (container — not executable)](tasks/TASK-011-entity-instance-attribute-value-api.md) | Container | — |
| ↳ 011A | [AttributeValue type casting engine (shape only; fk existence hook deferred)](tasks/TASK-011A-attribute-value-type-casting.md) | Not started | 010 |
| ↳ 011C | [EntityInstance & AttributeValue models, migration, CRUD, bridge rules](tasks/TASK-011C-entity-instance-crud-api.md) | Not started | 004, 011A, 008A |
| ↳ 011B | [JSONB aggregation query builder + GET list swap](tasks/TASK-011B-jsonb-aggregation-query.md) | Not started | 011C |

> **Parallelization note:** Phase 3 (Identity & RBAC) does **not** block on Phase 2 finishing. Once TASK-009 is complete, TASK-012 (Person) and TASK-013 (RBAC seed) can start in parallel with TASK-010/011A/B/C (EAV). Only TASK-014 (auth middleware) and later identity tasks require both Phase 2 and early Phase 3 foundations. The phase ordering below reflects conceptual grouping, not a strict sequential gate.

### Phase 3: Identity & RBAC (SPEC-002)

| # | Task | Status | Depends on |
|---|------|--------|------------|
| 012 | [Person model & CRUD API](tasks/TASK-012-person-model-and-api.md) | **Complete** (401 test deferred to TASK-014) | 004, 009, 006, 008 |
| 013 | [RBAC models & seed data](tasks/TASK-013-rbac-models-and-seed-data.md) | **Complete** (hierarchy invariant not enforced at model level — seed data conforms; revisit in TASK-016) | 009, 012 |
| 014 | [Auth middleware — JWT, person resolution, org context, `Person.permissions_version` migration](tasks/TASK-014-auth-middleware.md) | Not started | 012, 013, 014A |
| ↳ 014A | [Consolidated ADR ratification & SPEC-007 edits (ADR-010)](tasks/TASK-014A-auth-consolidated-adr.md) | Not started | — |
| ↳ 014B | [Auth0 tenant configuration & env doc](tasks/TASK-014B-auth0-tenant-configuration.md) | Not started | 014A |
| ↳ 014C | [Post-Login Actions & `is_active` mirroring](tasks/TASK-014C-post-login-actions.md) | Not started | 014B |
| ↳ 014D | [Auth0 Management API integration](tasks/TASK-014D-auth0-management-api.md) | Not started | 014B |
| ↳ 014E | [Bootstrap first admin (one-shot deploy-token endpoint)](tasks/TASK-014E-bootstrap-first-admin.md) | Not started | 014D |
| ↳ 014F | [Invitation resource (CRUD, state machine, the one new table)](tasks/TASK-014F-invitation-resource.md) | Not started | 014D |
| ↳ 014G | [Invitation accept + nonce binding](tasks/TASK-014G-invitation-accept-binding.md) | Not started | 014F |
| ↳ 014I | [Permission cache invalidation strategy](tasks/TASK-014I-permission-cache-invalidation.md) | Not started | 014, 015 |
| ↳ 014J | [Force-revoke operator endpoint](tasks/TASK-014J-force-revoke.md) | Not started | 014C, 014D, 014I |
| 015 | [Permission resolution, caching, & row-level filtering](tasks/TASK-015-permission-resolution-and-caching.md) | Not started | 013, 014 |
| 016 | [Role & permission management API (adds invites.* + auth.force_revoke seeds; permissions_version write discipline)](tasks/TASK-016-role-permission-management-api.md) | Not started | 013, 015 |
| 017 | [Person role assignment API (permissions_version write discipline)](tasks/TASK-017-person-role-assignment-api.md) | Not started | 012, 013, 015 |
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
  └→ 034 (indexes), 035 (tests), 037 (CORS + 006,007), 038 (HIPAA gate)
  │
  └→ 008C (ruff + mypy strict config) → 008B (CI: lands early in Phase 1, guards every downstream PR)
```

**Critical path:** 001✓ → 002✓ → 006 → 008A → 009 → 010 → 011A → 011C → 013 → 014 → 015 → 025 → 020 → 021 → 022 → 031 (after 029, 030, 032) → 033

Note: 025 is on the session critical path because AppointmentType.cpt_code_id FKs into CPTCode. 029/030/032 all precede 031 because ClientConsent FKs into DocumentType, Document, and FormTemplate.

Note: TASK-004 (cursor pagination) is an explicit upstream for every domain CRUD task (009, 010, 011C, 012, 020, 021, 023, 025, 026, 027, 029, 030, 031, 032) — their list endpoints consume the pagination utility directly. The graph above omits those edges for readability; see each task's `Depends on:` header for the authoritative list.

---

## Conventions (ADR-009)

**Authority:** [ADR-009](adrs/ADR-009-service-repository-model-as-entity.md) is the foundational architecture decision; [TASK-008A](tasks/TASK-008A-service-router-conventions.md) is the canonical conventions doc. The Organization slice and the EntityType slice are the two reference implementations.

- **Layering:** router → service → model. One direction. No `BaseService`, no `relationship()` (ADR-002). Repository layer was deferred until shared-query pressure justifies it.
- **Class per aggregate** for Service — one class per file (`<aggregate>_service.py`); all SQL for the aggregate inlined in a `# Query helpers` section at the bottom of the file.
- **Domain-grouped** Models, Schemas, Enums — one file per spec domain.
- **Constructor injection** via `core/dependencies.py`. Routers depend on `Depends(get_<aggregate>_service)` only — they do not import SQLAlchemy or take `db` / `auth` as route-handler args.
- **Models hold invariants** (`@validates`, `CheckConstraint`, partial unique indexes, mutators, `@classmethod` factories) — there is no separate domain layer.
- **Audit:** success path via injected `AuditWriter` (request session); failure path via the route-level `GroundworkError` handler in `app/main.py` (fresh session, `outcome="failure"`).
- **`get_db` owns commit/rollback;** nothing else commits.
- **`tenant_id` and `actor_id`** enter Services as primitive UUIDs — structured `RequestContext` lands via TASK-014/015 (see ADR-008).
- **No module-level mutable state** in `services/` / `repositories/` / `models/` / `enums/` / `schemas/` (ADR-009).

See ADR-009 for the full naming schema and forbidden-name list.

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
| SPEC-007 | §14 | 008B |
| SPEC-007 | §15 | 037 |
| SPEC-000 | §6 | 038 (composite); underlying controls in 013, 014, 029, 030, 035 |
