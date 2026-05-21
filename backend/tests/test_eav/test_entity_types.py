"""
Tests for EntityType API endpoints (TASK-010 Phase 1 / SPEC-001 §4, §6, §9).

Named tests from SPEC-001 §9 covered here:
  test_delete_system_entity_type_returns_409
  test_rename_system_entity_type_returns_409
  test_duplicate_slug_same_org_returns_409
  test_system_type_slug_reserved_across_orgs
  test_create_entity_type_writes_audit_log

Additional Phase 1 AC tests:
  test_post_entity_type_returns_501_when_custom_types_disabled
  test_list_entity_types_includes_seed_types
  test_get_entity_type_by_slug_returns_200
  test_get_entity_type_unknown_slug_returns_404
  test_delete_custom_entity_type_returns_204

Test strategy
-------------
HTTP-endpoint tests use the real ``get_db`` dependency (no session override).
The ``Database`` singleton is pointed at the test DB by ``initialize_database``
for the entire session.  ``get_auth_context`` is overridden with a system-actor
stub (person_id=None, organization_id stable UUID) to avoid FK violations on the
empty ``people`` table.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import AbstractContextManager
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# Stable org ID used as the auth-context org for all entity-type tests.
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def et_client() -> AsyncGenerator[AsyncClient, None]:
    """Session-scoped AsyncClient with real Keycloak auth (alice) in ``_ORG_ID``."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.database import Database
    from app.models.eav import Organization
    from tests.conftest import _fetch_keycloak_token, seed_authenticated_identity

    session_factory = Database.get_session_factory()
    async with session_factory() as setup_session:
        exists = await setup_session.execute(select(Organization).where(Organization.id == _ORG_ID))
        if exists.scalar_one_or_none() is None:
            setup_session.add(
                Organization(
                    id=_ORG_ID,
                    name="EntityTypes Test Org",
                    timezone="UTC",
                    is_active=True,
                    created_at=datetime.now(tz=UTC),
                )
            )
            await setup_session.commit()
        await seed_authenticated_identity(setup_session, _ORG_ID)

    token = await _fetch_keycloak_token("alice")
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(_ORG_ID),
        },
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _unique_slug() -> str:
    """Generate a unique, ruff-format-safe slug for each test run."""
    return f"test-type-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 501 feature-flag gate (TASK-010 AC)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_entity_type_returns_501_when_custom_types_disabled(
    et_client: AsyncClient,
) -> None:
    """POST /entity-types returns 501 when custom_entity_types_enabled is False."""
    from app.core import config as settings_module

    with mock.patch.object(settings_module.settings, "custom_entity_types_enabled", False):
        resp = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Nutritionist", "slug": _unique_slug()},
        )
    assert resp.status_code == 501, resp.text
    body = resp.json()
    assert body["error"] == "not_implemented"


# ---------------------------------------------------------------------------
# Seed data — list & get happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_entity_types_includes_seed_types(et_client: AsyncClient) -> None:
    """GET /entity-types returns at least the 3 seeded system types."""
    resp = await et_client.get("/api/v1/entity-types")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["data"]}
    assert {"provider", "client", "admin"}.issubset(slugs)


@pytest.mark.asyncio
async def test_get_entity_type_by_slug_returns_200(et_client: AsyncClient) -> None:
    """GET /entity-types/provider returns the provider system type."""
    resp = await et_client.get("/api/v1/entity-types/provider")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == "provider"
    assert body["is_system_type"] is True
    assert body["is_person_subtype"] is True


@pytest.mark.asyncio
async def test_get_entity_type_unknown_slug_returns_404(et_client: AsyncClient) -> None:
    """GET /entity-types/{unknown} returns 404."""
    resp = await et_client.get("/api/v1/entity-types/does-not-exist-xyz")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "not_found"


# ---------------------------------------------------------------------------
# System type protection (SPEC-001 §4, §9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_system_entity_type_returns_409(et_client: AsyncClient) -> None:
    """DELETE on a system type returns 409 resource_locked (SPEC-001 §9)."""
    resp = await et_client.delete("/api/v1/entity-types/provider")
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "resource_locked"


@pytest.mark.asyncio
async def test_rename_system_entity_type_returns_409(et_client: AsyncClient) -> None:
    """PATCH slug on a system type returns 409 resource_locked (SPEC-001 §9)."""
    resp = await et_client.patch(
        "/api/v1/entity-types/client",
        json={"name": "renamed-client"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "resource_locked"


# ---------------------------------------------------------------------------
# Custom type CRUD (flag on)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_custom_entity_type(et_client: AsyncClient) -> None:
    """Creating a custom type (flag on) then retrieving it returns consistent data."""
    slug = _unique_slug()
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        create_resp = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Dietitian", "slug": slug},
        )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["slug"] == slug
    assert body["is_system_type"] is False

    get_resp = await et_client.get(f"/api/v1/entity-types/{slug}")
    assert get_resp.status_code == 200
    assert get_resp.json()["slug"] == slug


@pytest.mark.asyncio
async def test_delete_custom_entity_type_returns_204(et_client: AsyncClient) -> None:
    """DELETE on a custom type returns 204."""
    slug = _unique_slug()
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Temp Type", "slug": slug},
        )
        resp = await et_client.delete(f"/api/v1/entity-types/{slug}")
    assert resp.status_code == 204, resp.text

    # Confirm gone
    get_resp = await et_client.get(f"/api/v1/entity-types/{slug}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Slug uniqueness (SPEC-001 §7, §9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_slug_same_org_returns_409(et_client: AsyncClient) -> None:
    """Creating two custom types with the same slug returns 409 on the second (SPEC-001 §9)."""
    slug = _unique_slug()
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        r1 = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "First", "slug": slug},
        )
        assert r1.status_code == 201, r1.text

        r2 = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Second", "slug": slug},
        )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"] == "conflict"


@pytest.mark.asyncio
async def test_system_type_slug_reserved_across_orgs(et_client: AsyncClient) -> None:
    """Attempting to create a custom type with a system slug returns 409 (SPEC-001 §9)."""
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        resp = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "My Provider", "slug": "provider"},
        )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "conflict"


# ---------------------------------------------------------------------------
# Audit log (SPEC-001 §9 / BR-07)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entity_type_writes_audit_log(et_client: AsyncClient) -> None:
    """Creating a custom EntityType writes a 'create' AuditLog entry (BR-07 / SPEC-001 §9)."""
    slug = _unique_slug()
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        create_resp = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Audited Type", "slug": slug},
        )
    assert create_resp.status_code == 201, create_resp.text
    et_id = create_resp.json()["id"]

    audit_resp = await et_client.get(
        "/api/v1/audit-log",
        params={
            "resource_type": "EntityType",
            "resource_id": et_id,
            "sort": "occurred_at",
        },
    )
    assert audit_resp.status_code == 200, audit_resp.text
    entries = audit_resp.json()["data"]
    create_entries = [e for e in entries if e["action"] == "create"]
    assert len(create_entries) >= 1, "Expected at least one 'create' AuditLog entry"
    assert create_entries[0]["resource_id"] == et_id
    assert create_entries[0]["next_state"] is not None


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_slug_format_returns_422(et_client: AsyncClient) -> None:
    """Slugs with uppercase or spaces are rejected at schema level."""
    with mock.patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "custom_entity_types_enabled",
        True,
    ):
        resp = await et_client.post(
            "/api/v1/entity-types",
            json={"name": "Bad Slug", "slug": "Bad Slug!"},
        )
    assert resp.status_code == 422, resp.text


# ===========================================================================
# EntityAttribute tests (Phase 2 — TASK-010)
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTINGS = __import__("app.core.config", fromlist=["settings"]).settings


def _flag_on() -> AbstractContextManager[Any]:
    """Context manager that temporarily enables custom EntityType creation."""
    return mock.patch.object(_SETTINGS, "custom_entity_types_enabled", True)


async def _create_custom_type(client: AsyncClient, name: str, slug: str) -> dict[str, Any]:
    """Create a custom EntityType (flag on) and return the response body."""
    with _flag_on():
        resp = await client.post(
            "/api/v1/entity-types",
            json={"name": name, "slug": slug},
        )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


# ---------------------------------------------------------------------------
# List attributes (SPEC-001 §6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_attributes_returns_seed_attributes(et_client: AsyncClient) -> None:
    """GET /{slug}/attributes for a system type returns its seed attributes."""
    resp = await et_client.get("/api/v1/entity-types/provider/attributes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {a["name"] for a in body["data"]}
    assert {"license_number", "license_state", "npi_number"}.issubset(names)


@pytest.mark.asyncio
async def test_list_attributes_unknown_type_returns_404(et_client: AsyncClient) -> None:
    """GET /{unknown}/attributes returns 404 when the type does not exist."""
    resp = await et_client.get("/api/v1/entity-types/does-not-exist/attributes")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "not_found"


# ---------------------------------------------------------------------------
# Get single attribute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_attribute_returns_200(et_client: AsyncClient) -> None:
    """GET /{slug}/attributes/{attr_id} returns the attribute with correct fields."""
    # Fetch the list first to grab a real attr_id from seed data.
    list_resp = await et_client.get("/api/v1/entity-types/client/attributes")
    assert list_resp.status_code == 200
    attrs = list_resp.json()["data"]
    assert attrs, "Expected at least one client attribute"
    attr_id = attrs[0]["id"]

    get_resp = await et_client.get(f"/api/v1/entity-types/client/attributes/{attr_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == attr_id
    assert "name" in body
    assert "field_type" in body


@pytest.mark.asyncio
async def test_get_attribute_wrong_type_returns_404(et_client: AsyncClient) -> None:
    """GET /{slug}/attributes/{attr_id} returns 404 when attr belongs to a different type."""
    # Grab a provider attribute ID.
    list_resp = await et_client.get("/api/v1/entity-types/provider/attributes")
    provider_attr_id = list_resp.json()["data"][0]["id"]

    # Try to access it via the client type path.
    resp = await et_client.get(f"/api/v1/entity-types/client/attributes/{provider_attr_id}")
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# test_add_attribute_to_system_type_succeeds (SPEC-001 §9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_attribute_to_system_type_succeeds(et_client: AsyncClient) -> None:
    """POST /{slug}/attributes on a system type succeeds.

    System types are extensible (SPEC-001 §4 / §9).
    """
    resp = await et_client.post(
        "/api/v1/entity-types/admin/attributes",
        json={
            "name": f"custom_field_{uuid.uuid4().hex[:6]}",
            "display_name": "Custom Field",
            "field_type": "TEXT",
            "is_required": False,
            "display_order": 99,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"].startswith("custom_field_")
    assert body["field_type"] == "TEXT"


# ---------------------------------------------------------------------------
# Create attribute on custom type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_attribute_on_custom_type_returns_201(et_client: AsyncClient) -> None:
    """POST /{slug}/attributes on a custom type returns 201 with the new attribute."""
    et = await _create_custom_type(et_client, "Attr Test Type", f"attr-test-{uuid.uuid4().hex[:6]}")
    slug = et["slug"]

    resp = await et_client.post(
        f"/api/v1/entity-types/{slug}/attributes",
        json={
            "name": "referral_date",
            "display_name": "Referral Date",
            "field_type": "DATE",
            "is_required": True,
            "display_order": 0,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "referral_date"
    assert body["field_type"] == "DATE"
    assert body["is_required"] is True
    assert body["entity_type_id"] == et["id"]


# ---------------------------------------------------------------------------
# Update attribute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_attribute_returns_200(et_client: AsyncClient) -> None:
    """PATCH /{slug}/attributes/{attr_id} partially updates the attribute."""
    et = await _create_custom_type(
        et_client, "Update Attr Type", f"upd-attr-{uuid.uuid4().hex[:6]}"
    )
    slug = et["slug"]

    create_resp = await et_client.post(
        f"/api/v1/entity-types/{slug}/attributes",
        json={"name": "old_name", "display_name": "Old Name", "field_type": "TEXT"},
    )
    assert create_resp.status_code == 201
    attr_id = create_resp.json()["id"]

    patch_resp = await et_client.patch(
        f"/api/v1/entity-types/{slug}/attributes/{attr_id}",
        json={"display_name": "New Display Name", "is_required": True},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert body["display_name"] == "New Display Name"
    assert body["is_required"] is True
    assert body["name"] == "old_name"  # unchanged


# ---------------------------------------------------------------------------
# Delete attribute on custom type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_attribute_on_custom_type_returns_204(et_client: AsyncClient) -> None:
    """DELETE /{slug}/attributes/{attr_id} on a custom type returns 204."""
    et = await _create_custom_type(et_client, "Del Attr Type", f"del-attr-{uuid.uuid4().hex[:6]}")
    slug = et["slug"]

    create_resp = await et_client.post(
        f"/api/v1/entity-types/{slug}/attributes",
        json={"name": "to_delete", "display_name": "To Delete", "field_type": "TEXT"},
    )
    assert create_resp.status_code == 201
    attr_id = create_resp.json()["id"]

    del_resp = await et_client.delete(f"/api/v1/entity-types/{slug}/attributes/{attr_id}")
    assert del_resp.status_code == 204, del_resp.text

    # Confirm gone
    get_resp = await et_client.get(f"/api/v1/entity-types/{slug}/attributes/{attr_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# test_delete_seed_attribute_on_system_type_returns_409 (SPEC-001 §9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_seed_attribute_on_system_type_returns_409(et_client: AsyncClient) -> None:
    """DELETE a seed attribute on a system type returns 409 resource_locked (SPEC-001 §9)."""
    # Fetch the list of provider attributes and pick the first seed one.
    list_resp = await et_client.get("/api/v1/entity-types/provider/attributes")
    assert list_resp.status_code == 200
    attrs = list_resp.json()["data"]
    assert attrs, "Expected seed provider attributes"
    attr_id = attrs[0]["id"]

    resp = await et_client.delete(f"/api/v1/entity-types/provider/attributes/{attr_id}")
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "resource_locked"


# ---------------------------------------------------------------------------
# Enum field_type options validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_attribute_with_enum_options(et_client: AsyncClient) -> None:
    """Creating an ENUM attribute with options stores and returns them correctly."""
    et = await _create_custom_type(et_client, "Enum Attr Type", f"enum-attr-{uuid.uuid4().hex[:6]}")
    slug = et["slug"]

    resp = await et_client.post(
        f"/api/v1/entity-types/{slug}/attributes",
        json={
            "name": "status",
            "display_name": "Status",
            "field_type": "ENUM",
            "options": ["active", "inactive", "pending"],
            "is_required": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["options"] == ["active", "inactive", "pending"]
    assert body["field_type"] == "ENUM"
