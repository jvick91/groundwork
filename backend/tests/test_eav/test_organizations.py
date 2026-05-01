"""
Tests for Organization model, service, and API endpoints (TASK-009 / SPEC-001 §2).

Acceptance criteria from TASK-009:
  test_create_organization_returns_201
  test_list_organizations_returns_paginated_response
  test_get_organization_returns_200
  test_update_organization_returns_200
  test_invalid_timezone_returns_422
  test_create_organization_writes_audit_entry
  test_registered_hook_fires_on_create
  test_hook_failure_rolls_back_organization_create

Test strategy
-------------
HTTP-endpoint tests use the real ``get_db`` dependency (no session override).
``get_db`` is backed by the ``Database`` singleton which ``initialize_database``
pointed at the test DB for the whole session.  Each request gets its own fresh
session and commits normally.  Sharing a ``db_session`` across the
``ASGITransport`` boundary causes asyncpg's protocol to see a Future from a
different event-loop context; avoiding that sharing is simpler than patching it.

Service/hook tests call the service layer directly with ``db_session`` so they
still benefit from transaction-rollback isolation.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.services import organization_hooks

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    """Session-scoped AsyncClient using the real get_db (no session override).

    ASGITransport does NOT run the app lifespan, so the Database singleton
    initialised by conftest.initialize_database remains in effect throughout
    the session.  Each request creates its own DB session via the normal
    get_db dependency, commits on success, and is fully independent.

    ``get_auth_context`` is overridden to use ``person_id=None`` (system-actor
    semantics) because the ``people`` table is empty during TASK-009 tests and
    the stub UUID would fail the ``audit_logs.actor_person_id`` FK check.
    ``actor_person_id`` is nullable by design (SPEC-006 §7: system events have
    no actor), so this is semantically correct.
    """
    from app.core.security import AuthContext, get_auth_context

    app = create_app()

    stub_auth = AuthContext(
        person_id=None,  # type: ignore[arg-type]  — system actor; people table empty
        auth_subject="test|stub",
        organization_id=uuid.UUID("00000000-0000-0000-0000-0000000000b2"),
    )
    app.dependency_overrides[get_auth_context] = lambda: stub_auth

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_hooks():
    """Clear the hook registry before and after each test."""
    organization_hooks.clear_hooks()
    yield
    organization_hooks.clear_hooks()


# ---------------------------------------------------------------------------
# CRUD happy path (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_organization_returns_201(http_client: AsyncClient):
    """POST /organizations creates a tenant and returns 201 + full schema."""
    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Acme Therapy {uuid.uuid4()}", "timezone": "America/New_York"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["timezone"] == "America/New_York"
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_list_organizations_returns_paginated_response(http_client: AsyncClient):
    """GET /organizations returns {data, pagination}."""
    marker = str(uuid.uuid4())
    await http_client.post(
        "/api/v1/organizations",
        json={"name": f"List Test Org {marker}"},
    )

    resp = await http_client.get("/api/v1/organizations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)
    names = [o["name"] for o in body["data"]]
    assert any(marker in n for n in names), f"Expected org with marker {marker}"


@pytest.mark.asyncio
async def test_get_organization_returns_200(http_client: AsyncClient):
    """GET /organizations/{id} returns the correct record."""
    marker = str(uuid.uuid4())
    create_resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Get Me Org {marker}"},
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["id"]

    resp = await http_client.get(f"/api/v1/organizations/{org_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == org_id
    assert marker in resp.json()["name"]


@pytest.mark.asyncio
async def test_get_organization_not_found_returns_404(http_client: AsyncClient):
    """GET /organizations/{unknown_id} returns 404 not_found."""
    resp = await http_client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


@pytest.mark.asyncio
async def test_update_organization_returns_200(http_client: AsyncClient):
    """PATCH /organizations/{id} applies partial updates and returns updated record."""
    create_resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Before Update {uuid.uuid4()}"},
    )
    org_id = create_resp.json()["id"]

    resp = await http_client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "After Update", "phone": "555-0100"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "After Update"
    assert body["phone"] == "555-0100"
    assert body["timezone"] == "UTC"  # unchanged field preserved


@pytest.mark.asyncio
async def test_update_organization_is_active_toggle(http_client: AsyncClient):
    """PATCH can toggle is_active for tenant suspension."""
    create_resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Suspend Me {uuid.uuid4()}"},
    )
    org_id = create_resp.json()["id"]

    resp = await http_client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Timezone validation (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_timezone_returns_422(http_client: AsyncClient):
    """POST with a non-IANA timezone returns 422 validation_error."""
    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": "Bad TZ Org", "timezone": "Not/A/Timezone"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"] == "validation_error"
    tz_errors = [d for d in body["details"] if "timezone" in d.get("field", "")]
    assert tz_errors, "Expected a timezone field error in details"


@pytest.mark.asyncio
async def test_valid_non_utc_timezone_accepted(http_client: AsyncClient):
    """POST with a valid IANA non-UTC timezone (e.g. 'America/Chicago') succeeds."""
    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Chicago Clinic {uuid.uuid4()}", "timezone": "America/Chicago"},
    )
    assert resp.status_code == 201
    assert resp.json()["timezone"] == "America/Chicago"


@pytest.mark.asyncio
async def test_update_with_invalid_timezone_returns_422(http_client: AsyncClient):
    """PATCH with an invalid timezone returns 422."""
    create_resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"TZ Update Test {uuid.uuid4()}"},
    )
    org_id = create_resp.json()["id"]

    resp = await http_client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"timezone": "Garbage/Zone"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"


# ---------------------------------------------------------------------------
# Audit logging (verified via the audit-log API endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_organization_writes_audit_entry(http_client: AsyncClient):
    """BR-07: creating an org via the API writes a corresponding AuditLog row.

    Verification uses the GET /audit-log endpoint rather than querying
    db_session directly, which avoids the asyncpg event-loop mismatch that
    occurs when a connection is eagerly established in fixture setup and then
    used in a later test task.
    """
    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Audited Org {uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    org_id = resp.json()["id"]

    audit_resp = await http_client.get(
        "/api/v1/audit-log",
        params={
            "resource_type": "Organization",
            "resource_id": org_id,
            "sort": "occurred_at",
        },
    )
    assert audit_resp.status_code == 200, audit_resp.text
    entries = audit_resp.json()["data"]
    create_entries = [e for e in entries if e["action"] == "create"]
    assert len(create_entries) >= 1, "Expected at least one 'create' audit entry"
    assert create_entries[0]["resource_id"] == org_id
    assert create_entries[0]["next_state"] is not None


# ---------------------------------------------------------------------------
# Hook lifecycle (verified via HTTP — hooks fire in the request's transaction)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registered_hook_fires_on_create(http_client: AsyncClient):
    """A hook registered with register_on_create_hook is invoked after org create.

    The hook appends the org_id to a list.  We verify the org was created
    (201) AND the hook was called by checking the list after the request.
    The hook runs in the same request transaction as the INSERT.
    """
    fired: list[uuid.UUID] = []

    async def _my_hook(db: AsyncSession, org_id: uuid.UUID) -> None:
        fired.append(org_id)

    organization_hooks.register_on_create_hook(_my_hook)

    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": f"Hook Org {uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    created_id = uuid.UUID(resp.json()["id"])

    assert len(fired) == 1, f"Expected 1 hook call, got {len(fired)}"
    assert fired[0] == created_id, "Hook received wrong org_id"


@pytest.mark.asyncio
async def test_hook_failure_rolls_back_organization_create(http_client: AsyncClient):
    """A hook that raises must roll back the entire transaction (org + audit).

    The endpoint returns 500 (unhandled exception), and a subsequent GET
    must confirm the org was not persisted.
    """

    async def _failing_hook(db: AsyncSession, org_id: uuid.UUID) -> None:
        raise RuntimeError("seed data unavailable — intentional test failure")

    organization_hooks.register_on_create_hook(_failing_hook)

    doomed_name = f"Doomed Org {uuid.uuid4()}"
    resp = await http_client.post(
        "/api/v1/organizations",
        json={"name": doomed_name},
    )
    assert resp.status_code == 500, f"Expected 500 from hook failure, got {resp.status_code}"
    assert resp.json()["error"] == "internal_error"

    # Verify no org was persisted by listing and checking name is absent.
    list_resp = await http_client.get("/api/v1/organizations")
    names = [o["name"] for o in list_resp.json()["data"]]
    assert doomed_name not in names, "Organization should have been rolled back on hook failure"
