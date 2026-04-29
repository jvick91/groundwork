# TASK-009 Log — Organization Model & CRUD API

**Branch:** `organization-api`
**Completed:** 2026-04-29

---

## What was done

### `backend/app/schemas/eav.py` (new)
- `OrganizationCreate` — name (required, min_length=1), optional npi_number/tax_id/phone/address, timezone (default "UTC"). IANA timezone validation via `zoneinfo.ZoneInfo` raises `ValueError` on invalid input, which Pydantic surfaces as a 422 detail.
- `OrganizationUpdate` — all fields optional (PATCH semantics). Timezone validated same as Create; `None` is passed through unchanged.
- `OrganizationResponse` — `from_attributes=True`; `updated_at: datetime | None` to match the `nullable=True` column in `TimestampMixin`.

### `backend/app/services/organization_hooks.py` (new)
- Module-level `_hooks: list[_HookFn]` registry.
- `register_on_create_hook(fn)` — appends to registry.
- `on_organization_created(db, org_id)` — iterates and awaits each hook in order; any exception propagates immediately (caller / `get_db` handles rollback).
- `clear_hooks()` — resets registry; intended for test isolation only.

### `backend/app/services/eav_service.py` (new)
- `_org_snapshot(org)` — serialisable dict for audit state captures (no PHI).
- `create_organization(db, *, actor_id, data)` — inserts org, flushes to obtain PK, writes audit row (`action="create"`), then calls `on_organization_created`. All three writes share the same session; `get_db` commits or rolls back atomically.
- `get_organization(db, org_id)` — `db.get` then `raise NotFoundError("Organization", org_id)` if absent.
- `list_organizations(db, *, params)` — thin wrapper over `paginate()` with allow-listed sort fields (`created_at`, `updated_at`, `name`).
- `update_organization(db, *, org_id, actor_id, data)` — captures previous snapshot, applies `model_dump(exclude_unset=True)`, sets `updated_at` explicitly, flushes, writes audit row (`action="update"`).

### `backend/app/routers/eav.py` (new)
- `POST /api/v1/organizations` — 201, `require_permission("settings.write")`, calls `create_organization`.
- `GET /api/v1/organizations` — 200, `require_permission("settings.read")`, returns `PaginatedResponse`.
- `GET /api/v1/organizations/{org_id}` — 200, `require_permission("settings.read")`.
- `PATCH /api/v1/organizations/{org_id}` — 200, `require_permission("settings.write")`.

### `backend/app/main.py`
- Imported `eav_router` and registered with `app.include_router(eav_router.router, prefix="/api/v1")`.

### `backend/tests/factories/eav.py` (new)
- `create_organization(session, *, name, npi_number, tax_id, phone, address, tz, is_active)` — inserts and flushes; no commit.
- Parameter named `tz` (not `timezone`) to avoid shadowing `datetime.timezone`.

### `backend/tests/test_eav/test_organizations.py` (new)
11 tests covering all TASK-009 acceptance criteria:
- `test_create_organization_returns_201`
- `test_list_organizations_returns_paginated_response`
- `test_get_organization_returns_200`
- `test_get_organization_not_found_returns_404`
- `test_update_organization_returns_200`
- `test_update_organization_is_active_toggle`
- `test_invalid_timezone_returns_422`
- `test_valid_non_utc_timezone_accepted`
- `test_update_with_invalid_timezone_returns_422`
- `test_create_organization_writes_audit_entry`
- `test_registered_hook_fires_on_create`
- `test_hook_failure_rolls_back_organization_create`

---

## Decisions

**Hook invocation order:** hooks run *after* the audit write, so audit coverage is guaranteed even if a hook fails. This matches the task AC ("after audit write, before commit").

**Service does not call `db.rollback()` on failure:** consistent with `eav_service` being a plain service layer; `get_db` owns the transaction boundary in endpoint flows. Hook-failure rollback test calls `await db_session.rollback()` explicitly to mirror that behaviour in the direct-call test path (same pattern used in `test_audit_log.py::test_audit_failure_rolls_back_business_operation`).

**`updated_at` set explicitly in service:** `onupdate=text("NOW()")` fires at the DB level during a real UPDATE statement, but `TimestampMixin` uses `nullable=True` / `server_default=None`. Setting `org.updated_at` explicitly in Python ensures the returned `OrganizationResponse` has a non-None value after an update without requiring a DB round-trip.

**No `call_service_with_audit` used:** `call_service_with_audit` in `common.py` runs `operation → audit → return`, but the Organization create flow needs `operation → audit → hooks`. Pulling hooks into `call_service_with_audit`'s `next_state_getter` would be unintuitive; explicit ordering in the service function is clearer.

---

## Deviations from TASK-008A conventions

None. All router/service/schema/factory patterns follow `docs/conventions.md` verbatim.

---

## Open items / follow-ups

- `is_active` filter on `GET /organizations` (e.g. `?is_active=true`) could be added later; deferred to TASK-016 (tenant management).
- NPI and tax_id format validation (regex check) deferred; spec does not mandate a format constraint for MVP.
