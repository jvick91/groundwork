# SPEC-007: API Contract and Testing

**Status:** Draft
**Version:** 0.1.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Cross-cutting API conventions, endpoint inventory, error handling, authentication flow, pagination, background tasks, database indexing, CI pipeline, and test infrastructure.

---

## 1. Domain Overview

This spec owns no tables. It defines the contracts and conventions that all domain sub-specs must follow when exposing their functionality as a FastAPI application. Every endpoint in every sub-spec is subject to the rules defined here.

This is the implementation spec. It translates the domain models and business rules from SPEC-001 through SPEC-006 into a running FastAPI application with consistent behavior, predictable error responses, and a testable architecture.

---

## 2. API Versioning

All API endpoints are served under the `/api/v1/` prefix. Sub-spec endpoint tables list paths without this prefix for readability. The full production URL for any endpoint is `https://{host}/api/v1{path}`.

Example: SPEC-003 lists `GET /sessions`. The actual URL is `GET /api/v1/sessions`.

Versioning strategy follows ADR-010. When breaking changes are introduced, a new version prefix (`/api/v2/`) is added while the previous version remains available for a deprecation period.

---

## 3. Authentication and Organization Context

### 3.1 Authentication flow

Every API request (except `/api/v1/health`) must include a valid Auth0 JWT in the `Authorization: Bearer {token}` header. The backend never generates tokens — Auth0 is the sole token issuer.

Request lifecycle:

1. FastAPI middleware extracts the JWT from the `Authorization` header.
2. The JWT signature is validated against Auth0's JWKS (JSON Web Key Set) endpoint. The JWKS is cached in-process with a TTL to avoid per-request network calls.
3. The `sub` claim is extracted from the validated token.
4. The backend queries `Person` where `auth_subject = sub`. If no match, return 401.
5. If `Person.is_active = false` or `Person.deleted_at` is not null, return 401.
6. The organization context is resolved from the `X-Organization-Id` header (see 3.2).
7. The backend loads active `PersonRole` rows for `(person_id, organization_id)` where `revoked_at IS NULL`.
8. If no active PersonRole exists for the requested org, return 403.
9. The effective permission set is computed (see 3.3) and attached to the request context.

### 3.2 Organization context

The frontend sends the `X-Organization-Id` header on every request. This header is required on all endpoints except `/api/v1/auth/me` and `/api/v1/health`.

Organization selection happens at login:

1. After Auth0 authentication, the frontend calls `GET /api/v1/auth/me` (no org header required).
2. The response includes all organizations the person has active roles in.
3. If the person belongs to one org, the frontend auto-selects it.
4. If the person belongs to multiple orgs, the frontend presents an org picker.
5. The selected org ID is stored client-side and sent as `X-Organization-Id` on all subsequent requests.

Org switching does not require re-authentication. The frontend updates the stored org ID and the next request uses the new context. The backend verifies the person has an active PersonRole in the requested org on every request.

Missing or invalid `X-Organization-Id` returns:

```json
{
  "error": "organization_required",
  "message": "X-Organization-Id header is required.",
  "status": 400
}
```

### 3.3 Permission resolution and caching

The effective permission set for a request is the union of all permissions across the person's active roles in the requested org, including inherited permissions from parent roles.

Resolution steps:

1. Load active PersonRole rows for (person_id, org_id).
2. For each role, walk the `parent_role_id` chain to collect the full role hierarchy.
3. Load all active RolePermission grants for every role in the hierarchy.
4. Union all permission slugs into the effective set.
5. Attach the effective set and any row-level conditions to the request context.

**Caching:** The resolved permission set is cached in-process using a TTL cache keyed by `(person_id, organization_id)`. TTL is 60 seconds. Cache entries are invalidated immediately when the current request modifies PersonRole, RolePermission, or Role records. This prevents stale permissions within the same process. Cross-process staleness is bounded by the TTL.

The cache implementation must use a thread-safe LRU cache with TTL (e.g., `cachetools.TTLCache`). Maximum cache size is 10,000 entries.

### 3.4 /auth/me response

`GET /api/v1/auth/me` does not require `X-Organization-Id`. It returns all organizations and roles for the authenticated person.

```json
{
  "person": {
    "id": "uuid",
    "first_name": "string",
    "last_name": "string",
    "email": "string"
  },
  "organizations": [
    {
      "id": "uuid",
      "name": "string",
      "roles": [
        {
          "role_slug": "string",
          "role_name": "string",
          "primary_domain": "admin | provider | client",
          "entity_instance_id": "uuid | null"
        }
      ]
    }
  ]
}
```

### 3.5 /auth/me/permissions response

`GET /api/v1/auth/me/permissions` requires `X-Organization-Id`. Returns the resolved permission set for the current org context.

```json
{
  "organization_id": "uuid",
  "permissions": [
    {
      "slug": "string",
      "resource": "string",
      "action": "string",
      "conditions": {}
    }
  ]
}
```

---

## 4. Request and Response Conventions

### 4.1 Content type

All requests and responses use `Content-Type: application/json`. File uploads use the two-step presigned URL pattern defined in SPEC-006 — binary data never flows through the API server.

### 4.2 Timestamps

All timestamps in request and response bodies are ISO 8601 strings in UTC with timezone designator: `2026-04-01T14:30:00Z`. The backend stores all timestamps in UTC. Timezone display is a frontend concern.

### 4.3 UUIDs

All resource IDs are UUID v4 strings. The backend generates IDs at creation time. Clients never supply their own IDs.

### 4.4 Money

All monetary values are integers representing cents. No floating-point money values appear in any request or response. Field names use the `_cents` suffix (e.g., `amount_cents`, `total_cents`).

### 4.5 Pydantic everywhere

Every request body, response body, query parameter set, and internal service contract is defined as a Pydantic model. No endpoint accepts or returns raw dicts or untyped JSON. All Pydantic models use strict mode where applicable.

---

## 5. Pagination

All list endpoints use cursor-based pagination. The contract is consistent across every domain.

### Request parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| limit | Integer | 25 | Number of items to return. Maximum 100. |
| cursor | String | null | Opaque cursor from a previous response. Null or omitted for the first page. |
| sort | String | created_at | Field to sort by. Must be an indexed column. |
| sort_dir | String | desc | Sort direction: `asc` or `desc`. |

### Response envelope

Every list endpoint returns this structure:

```json
{
  "data": [],
  "pagination": {
    "next_cursor": "string | null",
    "previous_cursor": "string | null",
    "has_next": true,
    "has_previous": false,
    "limit": 25
  }
}
```

### Cursor encoding

Cursors are Base64-encoded JSON containing the sort column value and the record ID of the last item. Example decoded: `{"created_at": "2026-04-01T14:30:00Z", "id": "uuid"}`. Cursors are opaque to clients — the format is an implementation detail and may change.

### Stability guarantee

Cursor-based pagination produces stable results even when records are inserted or deleted between page requests. A record will never appear on two different pages or be skipped due to concurrent writes.

---

## 6. Filtering and Sorting

### 6.1 Filter query parameters

List endpoints accept filter parameters as query strings. Each sub-spec defines which filters are available for its endpoints. The general conventions are:

| Pattern | Example | Meaning |
|---|---|---|
| Exact match | `?status=draft` | Field equals value |
| Multiple values | `?status=draft,sent` | Field is one of the values (OR) |
| Date range | `?date_from=2026-01-01&date_to=2026-03-31` | Field is within the range (inclusive) |
| FK reference | `?client_instance_id=uuid` | Filter by foreign key |
| Search | `?q=smith` | Text search across relevant fields (endpoint-specific) |

### 6.2 Sorting

Sort parameters use the `sort` and `sort_dir` query params defined in section 5. Only indexed columns may be used as sort fields. Attempts to sort by non-indexed columns return 400.

### 6.3 Empty results

An empty result set returns 200 with `"data": []`, not 404. A 404 means the resource path itself is invalid, not that the query returned no results.

---

## 7. Error Response Contract

### 7.1 Error envelope

All error responses use this Pydantic model:

```json
{
  "error": "string",
  "message": "string",
  "status": 422,
  "details": []
}
```

| Field | Type | Description |
|---|---|---|
| error | String | Machine-readable error code (snake_case). Stable across versions. |
| message | String | Human-readable description. May change between versions. |
| status | Integer | HTTP status code (duplicated in body for convenience). |
| details | Array | Optional. Field-level validation errors or additional context. |

### 7.2 Validation error details

For 422 validation errors, the `details` array contains field-level errors:

```json
{
  "error": "validation_error",
  "message": "Request validation failed.",
  "status": 422,
  "details": [
    {
      "field": "end_time",
      "message": "end_time must be after start_time",
      "code": "invalid_time_range"
    }
  ]
}
```

### 7.3 Standard error codes

| HTTP Status | Error Code | When |
|---|---|---|
| 400 | `bad_request` | Malformed request, missing required header |
| 400 | `organization_required` | Missing `X-Organization-Id` header |
| 401 | `unauthorized` | Missing, expired, or invalid JWT |
| 401 | `account_inactive` | Person.is_active = false or deleted_at is not null |
| 403 | `forbidden` | Valid auth but insufficient permissions |
| 403 | `org_access_denied` | Person has no active PersonRole in the requested org |
| 404 | `not_found` | Resource does not exist or is soft-deleted |
| 409 | `conflict` | Unique constraint violation, duplicate resource, or invalid state transition |
| 409 | `state_transition_denied` | Status transition not allowed (e.g., signing a cosigned note) |
| 409 | `resource_locked` | Record is in a state that prevents modification (e.g., signed note content) |
| 422 | `validation_error` | Pydantic validation or business rule violation |
| 422 | `bridge_rule_violation` | EntityInstance type mismatch (e.g., non-provider as session conductor) |
| 422 | `prerequisite_not_met` | Required precondition missing (e.g., no treatment consent for session completion) |
| 429 | `rate_limited` | Too many requests (post-MVP) |
| 500 | `internal_error` | Unhandled server error. Message is generic; details are logged, not exposed. |

### 7.4 Error response PHI safety

Error messages and details must never contain PHI. A validation error on a clinical note's `subjective` field returns `{"field": "content.subjective", "message": "Field is required"}` — never the field's value.

---

## 8. Complete Endpoint Inventory

All paths are relative to `/api/v1/`. Every endpoint requires Auth0 JWT and `X-Organization-Id` unless noted.

### 8.1 Auth (SPEC-002)

| Method | Path | Description | Permission | Org Header |
|---|---|---|---|---|
| GET | /auth/me | Person profile with all orgs and roles | authenticated | No |
| GET | /auth/me/permissions | Effective permissions for current org | authenticated | Yes |

### 8.2 EAV Platform (SPEC-001)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /entity-types | List entity types | entity_types.read |
| POST | /entity-types | Create custom entity type | entity_types.write |
| GET | /entity-types/{slug} | Retrieve entity type with attributes | entity_types.read |
| PATCH | /entity-types/{slug} | Update entity type | entity_types.write |
| DELETE | /entity-types/{slug} | Delete custom entity type | entity_types.delete |
| POST | /entity-types/{slug}/attributes | Add attribute to entity type | entity_types.write |
| PATCH | /entity-types/{slug}/attributes/{attr_id} | Update attribute | entity_types.write |
| DELETE | /entity-types/{slug}/attributes/{attr_id} | Delete attribute | entity_types.delete |
| GET | /entities/{type_slug} | List entity instances of a type | {type_slug}.read |
| POST | /entities/{type_slug} | Create entity instance | {type_slug}.write |
| GET | /entities/{type_slug}/{id} | Retrieve entity instance with attribute values | {type_slug}.read |
| PATCH | /entities/{type_slug}/{id} | Update entity instance attribute values | {type_slug}.write |
| DELETE | /entities/{type_slug}/{id} | Soft delete entity instance | {type_slug}.delete |

### 8.3 Identity and RBAC (SPEC-002)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /people | List people in org | people.read |
| POST | /people | Create person | people.write |
| GET | /people/{id} | Retrieve person | people.read |
| PATCH | /people/{id} | Update person | people.write |
| DELETE | /people/{id} | Soft delete person | people.delete |
| GET | /people/{id}/roles | List role assignments | roles.read |
| POST | /people/{id}/roles | Assign role | roles.assign |
| DELETE | /people/{id}/roles/{person_role_id} | Revoke role | roles.assign |
| GET | /roles | List roles | roles.read |
| POST | /roles | Create custom role | roles.write |
| PATCH | /roles/{id} | Update role | roles.write |
| DELETE | /roles/{id} | Delete custom role | roles.delete |
| GET | /permissions | List permissions | roles.read |
| POST | /roles/{id}/permissions | Grant permission to role | roles.write |
| DELETE | /roles/{id}/permissions/{permission_id} | Revoke permission | roles.write |

### 8.4 Scheduling and Sessions (SPEC-003)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /appointment-types | List appointment types | sessions.read |
| POST | /appointment-types | Create appointment type | settings.write |
| GET | /appointment-types/{id} | Retrieve appointment type | sessions.read |
| PATCH | /appointment-types/{id} | Update appointment type | settings.write |
| DELETE | /appointment-types/{id} | Deactivate appointment type | settings.write |
| GET | /sessions | List sessions | sessions.read |
| POST | /sessions | Create session | sessions.write |
| GET | /sessions/{id} | Retrieve session | sessions.read |
| PATCH | /sessions/{id} | Update session | sessions.write |
| DELETE | /sessions/{id} | Soft delete session | sessions.write |
| POST | /sessions/{id}/confirm | Transition to confirmed | sessions.write |
| POST | /sessions/{id}/start | Transition to in_progress | sessions.write |
| POST | /sessions/{id}/complete | Transition to completed | sessions.write |
| POST | /sessions/{id}/cancel | Cancel with reason | sessions.write |
| POST | /sessions/{id}/no-show | Mark no-show with reason | sessions.write |

### 8.5 Clinical Notes (SPEC-004)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /notes | List notes (cross-session) | notes.read |
| GET | /sessions/{session_id}/note | Retrieve note for session | notes.read |
| POST | /sessions/{session_id}/note | Create draft note | notes.write |
| PATCH | /sessions/{session_id}/note | Update draft note | notes.write |
| DELETE | /sessions/{session_id}/note | Soft delete draft note | notes.write |
| POST | /sessions/{session_id}/note/sign | Sign note | notes.sign |
| POST | /sessions/{session_id}/note/cosign | Co-sign note | notes.cosign |
| POST | /sessions/{session_id}/note/amend | Submit amendment | notes.write |

### 8.6 Billing and Payments (SPEC-005)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /cpt-codes | List CPT codes | codes.read |
| GET | /icd-codes | List ICD codes | codes.read |
| GET | /insurance-payers | List payers | insurance.read |
| POST | /insurance-payers | Create payer | insurance.write |
| GET | /insurance-payers/{id} | Retrieve payer | insurance.read |
| PATCH | /insurance-payers/{id} | Update payer | insurance.write |
| GET | /entities/{type_slug}/{id}/insurance | List client coverage | insurance.read |
| POST | /entities/{type_slug}/{id}/insurance | Add coverage | insurance.write |
| PATCH | /entities/{type_slug}/{id}/insurance/{coverage_id} | Update coverage | insurance.write |
| DELETE | /entities/{type_slug}/{id}/insurance/{coverage_id} | Deactivate coverage | insurance.write |
| GET | /invoices | List invoices | invoices.read |
| POST | /invoices | Create invoice | invoices.create |
| GET | /invoices/{id} | Retrieve invoice with line items | invoices.read |
| PATCH | /invoices/{id} | Update invoice metadata | invoices.write |
| DELETE | /invoices/{id} | Soft delete draft invoice | invoices.write |
| POST | /invoices/{id}/send | Transition to sent | invoices.write |
| POST | /invoices/{id}/void | Void with reason | invoices.void |
| GET | /invoices/{id}/line-items | List line items | invoices.read |
| POST | /invoices/{id}/line-items | Add line item | invoices.write |
| PATCH | /invoices/{id}/line-items/{item_id} | Update line item | invoices.write |
| DELETE | /invoices/{id}/line-items/{item_id} | Remove line item | invoices.write |
| GET | /invoices/{id}/payments | List payments for invoice | payments.read |
| POST | /invoices/{id}/payments | Record payment | payments.record |
| POST | /invoices/{id}/payments/{payment_id}/void | Void payment | payments.record |
| GET | /payments | List all payments | payments.read |

### 8.7 Documents, Consent, Compliance (SPEC-006)

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /document-types | List document types | documents.read |
| POST | /document-types | Create document type | documents.write |
| PATCH | /document-types/{id} | Update document type | documents.write |
| DELETE | /document-types/{id} | Deactivate document type | documents.write |
| GET | /documents | List documents | documents.read |
| POST | /documents | Initiate upload | documents.write |
| POST | /documents/{id}/confirm | Confirm upload | documents.write |
| GET | /documents/{id} | Retrieve with presigned URL | documents.read |
| DELETE | /documents/{id} | Soft delete | documents.delete |
| GET | /consent-types | List consent types | consents.read |
| POST | /consent-types | Create consent type | consents.write |
| PATCH | /consent-types/{id} | Update consent type | consents.write |
| DELETE | /consent-types/{id} | Deactivate consent type | consents.write |
| GET | /entities/{type_slug}/{id}/consents | List consents | consents.read |
| POST | /entities/{type_slug}/{id}/consents | Create consent | consents.write |
| GET | /entities/{type_slug}/{id}/consents/{consent_id} | Retrieve consent | consents.read |
| PATCH | /entities/{type_slug}/{id}/consents/{consent_id} | Update pending consent | consents.write |
| POST | /entities/{type_slug}/{id}/consents/{consent_id}/sign | Sign consent | consents.sign |
| POST | /entities/{type_slug}/{id}/consents/{consent_id}/revoke | Revoke consent | consents.revoke |
| GET | /form-templates | List templates | forms.read |
| POST | /form-templates | Create template | forms.write |
| GET | /form-templates/{id} | Retrieve template | forms.read |
| PATCH | /form-templates/{id} | Update template | forms.write |
| DELETE | /form-templates/{id} | Deactivate template | forms.write |
| GET | /audit-log | Query audit log | audit.read |
| GET | /audit-log/{id} | Retrieve audit entry | audit.read |

### 8.8 System (SPEC-007)

| Method | Path | Description | Permission | Org Header |
|---|---|---|---|---|
| GET | /health | Health check | none (public) | No |
| GET | /health/ready | Readiness check (DB + Redis) | none (public) | No |

---

## 9. Health Check Endpoints

### GET /api/v1/health

Returns 200 if the API process is running. No authentication required. No database or external service checks. Used by container orchestrators for liveness probes.

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

### GET /api/v1/health/ready

Returns 200 if the API can serve requests: database is reachable, Redis is connected, Auth0 JWKS is cached. Returns 503 if any dependency is unhealthy. Used for readiness probes.

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "auth0_jwks": "ok"
  }
}
```

---

## 10. Background Task Infrastructure

### 10.1 Stack

Background tasks use Celery with Redis as the message broker. This provides task queuing, scheduling, retries, and monitoring.

| Component | Role |
|---|---|
| Redis | Message broker for Celery. Also used for permission cache when scaling to multiple API replicas (post-MVP). |
| Celery Worker | Processes queued tasks. Runs as a separate Docker container with access to the same database. |
| Celery Beat | Scheduler for periodic tasks. Runs inside the worker container. |

### 10.2 Docker services

The development Docker Compose file defines six services:

| Service | Image | Port | Purpose |
|---|---|---|---|
| frontend | Next.js dev server | 3000 | Frontend with hot reload |
| backend | FastAPI via uvicorn | 8000 | API server with hot reload |
| db | PostgreSQL 16 | 5432 | Persistent development database |
| db-test | PostgreSQL 16 | 5433 | Ephemeral test database |
| redis | Redis 7 | 6379 | Celery broker and cache |
| worker | Celery worker + Beat | — | Background task processing and scheduling |

The test compose override adds:

| Service | Purpose |
|---|---|
| test-backend | Executes pytest against db-test |
| test-e2e | Executes Playwright against live frontend + backend |

### 10.3 Registered tasks

| Task | Schedule | Description | Source |
|---|---|---|---|
| `expire_consents` | Daily at 00:00 UTC | Transitions expired ClientConsent records to `expired` status. Writes AuditLog with null actor. | SPEC-006 |

Additional tasks will be registered as needed (e.g., email notifications, PDF generation, claim submission). All tasks must be idempotent — running the same task twice with the same inputs must produce the same result.

### 10.4 Task conventions

- All tasks are defined in a `tasks/` module within the backend package.
- Every task accepts a Pydantic model as input, not raw dicts.
- Every task that modifies data must write an AuditLog entry.
- Failed tasks retry up to 3 times with exponential backoff (10s, 60s, 300s).
- Task results are not stored in Redis by default. Tasks that need to report results use the database.

---

## 11. Database Indexing Strategy

Indexes are critical for query performance. Every table must have the indexes defined here in addition to primary keys and unique constraints defined in sub-specs.

### 11.1 Universal indexes

Every table with `organization_id` must have an index on `organization_id`. This is the most frequently filtered column due to multi-tenant isolation.

Every table with `deleted_at` must have a partial index: `WHERE deleted_at IS NULL`. Most queries exclude soft-deleted records — this index makes that filter free.

Every table with `created_at` must have an index on `(organization_id, created_at DESC)` to support paginated list queries sorted by creation time.

### 11.2 Domain-specific indexes

| Table | Index | Rationale |
|---|---|---|
| Person | `(auth_subject)` | Auth flow: JWT sub → Person lookup on every request |
| Person | `(email)` | Unique lookup by email |
| PersonRole | `(person_id, organization_id) WHERE revoked_at IS NULL` | Auth flow: load active roles for person in org |
| PersonRole | `(organization_id, role_id) WHERE revoked_at IS NULL` | List people by role in an org |
| RolePermission | `(role_id) WHERE revoked_at IS NULL` | Permission resolution: load grants for a role |
| Role | `(organization_id, slug)` | Role lookup by slug |
| Permission | `(slug)` | Permission lookup by slug |
| EntityInstance | `(organization_id, entity_type_id) WHERE deleted_at IS NULL` | List instances of a type in an org |
| AttributeValue | `(entity_instance_id)` | Load all values for an instance |
| Session | `(organization_id, provider_instance_id, start_time, end_time) WHERE deleted_at IS NULL` | Overlap detection (BR-03) |
| Session | `(organization_id, client_instance_id) WHERE deleted_at IS NULL` | List sessions for a client |
| Session | `(organization_id, status) WHERE deleted_at IS NULL` | Filter sessions by status |
| ClinicalNote | `(session_id)` | One-to-one lookup from session |
| ClinicalNote | `(organization_id, author_instance_id) WHERE deleted_at IS NULL` | List notes by author |
| Invoice | `(session_id) WHERE status != 'void'` | Partial unique enforcement |
| Invoice | `(organization_id, status) WHERE deleted_at IS NULL` | Filter invoices by status |
| Invoice | `(organization_id, client_instance_id) WHERE deleted_at IS NULL` | List invoices for a client |
| InvoiceLineItem | `(invoice_id) WHERE deleted_at IS NULL` | List line items for an invoice |
| Payment | `(invoice_id) WHERE status = 'posted'` | Sum posted payments for an invoice |
| ClientInsurance | `(organization_id, client_instance_id) WHERE is_active = true` | Active coverage for a client |
| ClientConsent | `(organization_id, client_instance_id, consent_type_id) WHERE status = 'signed'` | Consent gate: check active signed consent |
| AuditLog | `(organization_id, occurred_at DESC)` | Paginated audit log queries |
| AuditLog | `(organization_id, resource_type, resource_id)` | Audit history for a specific record |
| Document | `(organization_id, document_type_id) WHERE deleted_at IS NULL` | List documents by type |

### 11.3 EAV query performance

The EAV join pattern (EntityInstance → AttributeValue per field) is inherently expensive for list views. The indexing above helps, but ADR-002 must define the full query strategy. Options under consideration include materialized views, JSONB aggregation, or denormalized search columns. SPEC-007 does not prescribe the solution — ADR-002 owns this decision.

---

## 12. Application Structure

### 12.1 FastAPI project layout

```
backend/
├── app/
│   ├── main.py                  # FastAPI app factory, middleware registration
│   ├── config.py                # Pydantic Settings (env-based configuration)
│   ├── database.py              # SQLAlchemy async engine and session factory
│   ├── middleware/
│   │   ├── auth.py              # JWT validation, Person resolution
│   │   ├── organization.py      # X-Organization-Id extraction and verification
│   │   └── audit.py             # Audit log middleware
│   ├── models/                  # SQLAlchemy ORM models (one file per table)
│   │   ├── organization.py
│   │   ├── person.py
│   │   ├── person_role.py
│   │   ├── role.py
│   │   ├── permission.py
│   │   ├── role_permission.py
│   │   ├── entity_type.py
│   │   ├── entity_attribute.py
│   │   ├── entity_instance.py
│   │   ├── attribute_value.py
│   │   ├── session.py
│   │   ├── appointment_type.py
│   │   ├── clinical_note.py
│   │   ├── invoice.py
│   │   ├── invoice_line_item.py
│   │   ├── payment.py
│   │   ├── insurance_payer.py
│   │   ├── client_insurance.py
│   │   ├── cpt_code.py
│   │   ├── icd_code.py
│   │   ├── audit_log.py
│   │   ├── document_type.py
│   │   ├── document.py
│   │   ├── consent_type.py
│   │   ├── client_consent.py
│   │   └── form_template.py
│   ├── schemas/                 # Pydantic request/response models (per domain)
│   │   ├── auth.py
│   │   ├── eav.py
│   │   ├── identity.py
│   │   ├── sessions.py
│   │   ├── notes.py
│   │   ├── billing.py
│   │   └── compliance.py
│   ├── services/                # Business logic (per domain)
│   │   ├── auth_service.py
│   │   ├── eav_service.py
│   │   ├── identity_service.py
│   │   ├── session_service.py
│   │   ├── note_service.py
│   │   ├── billing_service.py
│   │   ├── consent_service.py
│   │   ├── document_service.py
│   │   └── audit_service.py
│   ├── routers/                 # FastAPI route handlers (per domain)
│   │   ├── auth.py
│   │   ├── eav.py
│   │   ├── identity.py
│   │   ├── sessions.py
│   │   ├── notes.py
│   │   ├── billing.py
│   │   └── compliance.py
│   ├── tasks/                   # Celery task definitions
│   │   └── consent_tasks.py
│   ├── permissions.py           # Permission checking utilities
│   └── exceptions.py            # Custom exception classes mapping to error codes
├── migrations/                  # Alembic migration files
│   └── versions/
├── tests/
│   ├── conftest.py              # Shared fixtures (db session, auth, test client)
│   ├── factories/               # Test data factories (one per domain)
│   ├── test_auth/
│   ├── test_eav/
│   ├── test_identity/
│   ├── test_sessions/
│   ├── test_notes/
│   ├── test_billing/
│   └── test_compliance/
├── alembic.ini
├── pyproject.toml
├── Dockerfile
└── celery_app.py                # Celery app factory and configuration
```

### 12.2 Layer responsibilities

| Layer | Responsibility | Rules |
|---|---|---|
| Routers | HTTP concerns: parse request, call service, return response | No business logic. No direct DB access. No SQLAlchemy imports. |
| Schemas | Request/response shapes, validation | Pydantic models only. No ORM dependencies. |
| Services | Business logic, domain rules, cross-domain coordination | May call other services. Owns transaction boundaries. All business rules enforced here. |
| Models | Database schema, relationships, column definitions | SQLAlchemy models only. No business logic. |
| Middleware | Cross-cutting concerns: auth, org context, audit | Runs before/after every request. |
| Tasks | Async/scheduled background work | Must be idempotent. Uses services for logic. |

### 12.3 Dependency injection

FastAPI's dependency injection system is used for:
- Database session (async SQLAlchemy session per request)
- Current authenticated person (resolved from JWT)
- Current organization context (resolved from header)
- Effective permission set (resolved and cached)
- Service instances (injected into routers)

---

## 13. Test Infrastructure

### 13.1 Philosophy

From SPEC-000: no mocks, tests are the spec, failing test first, test pyramid, Docker-first.

### 13.2 Test database

Tests run against a real PostgreSQL instance (`db-test` on port 5433). Each test function gets a clean database state via transaction rollback: the test runs inside a transaction that is rolled back after the test completes. This is faster than truncating tables and provides isolation between tests.

### 13.3 Test client

Tests use `httpx.AsyncClient` with FastAPI's `TestClient` integration. The test client sends real HTTP requests to the FastAPI application with full middleware execution (auth, org context, audit). No middleware is bypassed in tests.

### 13.4 Auth in tests

Tests do not call Auth0. A test fixture generates valid JWTs signed with a test-only RSA key. The auth middleware is configured to validate against the test key in the test environment. This provides real JWT validation without an external dependency.

### 13.5 Test factories

Each domain has a factory module that creates valid test data with sensible defaults. Factories use the ORM models directly and commit to the test database. Example:

```python
async def create_test_session(
    db: AsyncSession,
    organization: Organization,
    provider_instance: EntityInstance,
    client_instance: EntityInstance,
    status: str = "scheduled",
    **overrides,
) -> Session:
    ...
```

### 13.6 Test organization

```
tests/
├── conftest.py                  # Global fixtures: db session, test client, auth helpers
├── factories/
│   ├── eav.py                   # Organization, EntityType, EntityInstance factories
│   ├── identity.py              # Person, Role, PersonRole factories
│   ├── sessions.py              # Session, AppointmentType factories
│   ├── notes.py                 # ClinicalNote factories
│   ├── billing.py               # Invoice, Payment, CPTCode, ICDCode factories
│   └── compliance.py            # Document, ClientConsent, FormTemplate factories
├── test_auth/
│   ├── test_jwt_validation.py
│   ├── test_org_context.py
│   └── test_permission_resolution.py
├── test_eav/
│   ├── test_entity_types.py
│   └── test_entity_instances.py
├── test_identity/
│   ├── test_people.py
│   ├── test_roles.py
│   └── test_role_assignment.py
├── test_sessions/
│   ├── test_appointment_types.py
│   ├── test_session_crud.py
│   ├── test_session_lifecycle.py
│   └── test_overlap_detection.py
├── test_notes/
│   ├── test_note_crud.py
│   ├── test_note_lifecycle.py
│   ├── test_note_formats.py
│   └── test_amendments.py
├── test_billing/
│   ├── test_invoices.py
│   ├── test_line_items.py
│   ├── test_payments.py
│   ├── test_insurance.py
│   └── test_reference_codes.py
├── test_compliance/
│   ├── test_documents.py
│   ├── test_consents.py
│   ├── test_consent_lifecycle.py
│   ├── test_form_templates.py
│   └── test_audit_log.py
└── test_cross_cutting/
    ├── test_pagination.py
    ├── test_error_responses.py
    ├── test_phi_exclusion.py
    └── test_multi_tenancy.py
```

### 13.7 Coverage targets

From SPEC-000:

| Layer | Minimum |
|---|---|
| Models and services | 95% |
| API routers and schemas | 90% |
| Frontend components | 80% |
| E2E critical paths | All BRs covered |

Coverage is measured by pytest-cov and enforced in CI. A PR that drops coverage below the threshold is blocked.

---

## 14. CI Pipeline

### 14.1 Pipeline stages

Every PR triggers the following stages in order:

| Stage | Tool | Fails on |
|---|---|---|
| Lint | ruff | Any lint error |
| Type check | mypy (strict mode) | Any type error |
| Backend tests | pytest inside Docker | Any test failure or coverage below threshold |
| Frontend tests | Vitest inside Docker | Any test failure |
| E2E tests | Playwright inside Docker | Any test failure |
| Build | Docker image build | Build failure |

All stages run inside Docker containers. No CI runner installs Python or Node directly.

### 14.2 PR requirements

A PR may only be merged when:
- All CI stages pass
- At least one reviewer has approved
- The branch is up to date with main
- No unresolved review comments

### 14.3 Alembic migration safety

Every PR that includes an Alembic migration must:
- Run the migration against a fresh database (verify it applies cleanly)
- Run the migration against the current schema (verify it upgrades correctly)
- Run `alembic downgrade -1` (verify rollback works)
- Include the migration in the test suite so it is exercised automatically

---

## 15. Security Constraints

### 15.1 CORS

The backend configures CORS to allow requests only from the frontend origin. In development, this is `http://localhost:3000`. In production, this is the deployed frontend domain. Wildcard origins (`*`) are never used.

### 15.2 Rate limiting

Post-MVP. When implemented, rate limits will be enforced per (person_id, organization_id) combination using Redis as the counter store. Rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) will be included in responses.

### 15.3 Input validation

All input validation is performed by Pydantic models at the schema layer. Additional business rule validation is performed at the service layer. No endpoint trusts client-supplied data without validation.

String fields that accept free-form text (notes, descriptions, amendment_note) are sanitized to prevent stored XSS if the content is ever rendered in a browser context.

### 15.4 SQL injection prevention

All database queries use SQLAlchemy ORM or Core with parameterized queries. Raw SQL strings with user input are never constructed.

### 15.5 PHI in responses

API responses must never include fields marked as PHI-excluded in BR-08 in contexts where they don't belong (error messages, log output, audit snapshots). PHI fields are allowed in their owning resource's direct API response (e.g., `GET /sessions/{id}/note` returns clinical content).

---

## 16. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-002 | EAV query performance | Defines the query optimization strategy for EAV joins. Blocks efficient list views. |
| ADR-003 | Session FK semantics | Defines bridge rule validation approach used across scheduling, clinical, and billing domains. |
| ADR-010 | API versioning strategy | Defines the versioning prefix, deprecation policy, and breaking change criteria. |
| ADR-011 | Multi-tenancy isolation | Defines the tenant boundary enforcement strategy that this spec's middleware implements. |
| ADR-013 | CI/CD and deployment | Defines the full deployment pipeline, container registry, and environment management. |
| ADR-014 | Monitoring and observability | Defines logging, metrics, and alerting infrastructure. |

---

## 17. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. API versioning (/api/v1/), org context via X-Organization-Id header, cursor-based pagination, standard error envelope, complete 100+ endpoint inventory, auth flow, permission caching, Celery + Redis background tasks, database indexing strategy, application structure, test infrastructure, CI pipeline, security constraints, and health check endpoints. |
