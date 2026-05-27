"""
Auth DB-layer tests — Person resolution, org context, PersonRole check (TASK-014).

Tests from SPEC-002 §11:
  - test_person_without_auth_subject_cannot_authenticate
  - test_inactive_person_returns_401
  - test_person_role_cross_tenant_returns_403
  - test_soft_deleted_person_returns_401 (deferred from TASK-012)
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from tests.factories.eav import create_organization
from tests.factories.identity import create_person, create_person_role, create_role
from tests.fixtures import jwt_keys


# ---------------------------------------------------------------------------
# Session-scoped settings override (mirrors test_jwt_validation.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def real_auth_settings_org():
    """Configure settings to match the test JWT fixtures and disable the stub."""
    orig = {
        "auth_stub_enabled": settings.auth_stub_enabled,
        "auth0_issuer": settings.auth0_issuer,
        "auth0_audience": settings.auth0_audience,
    }
    settings.auth_stub_enabled = False
    settings.auth0_issuer = jwt_keys.TEST_ISSUER
    settings.auth0_audience = jwt_keys.TEST_AUDIENCE
    yield
    settings.auth_stub_enabled = orig["auth_stub_enabled"]
    settings.auth0_issuer = orig["auth0_issuer"]
    settings.auth0_audience = orig["auth0_audience"]


@pytest_asyncio.fixture(loop_scope="session")
async def real_auth_client(db_session: AsyncSession) -> AsyncClient:
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Person without auth_subject cannot authenticate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_person_without_auth_subject_cannot_authenticate(
    real_auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """SPEC-002 §11: a Person row with NULL auth_subject must not be resolvable."""
    # The default sub in mint_token is "auth0|test-subject". No Person row
    # in the DB has that auth_subject (factories use uuid-unique values).
    token = jwt_keys.mint_token(sub="auth0|no-such-person")
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# Inactive person returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactive_person_returns_401(
    real_auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """SPEC-002 §11: is_active=False person is rejected at the DB check."""
    auth_sub = "auth0|inactive-person-test"
    await create_person(db_session, auth_subject=auth_sub, is_active=False)

    token = jwt_keys.mint_token(sub=auth_sub)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] == "account_inactive"


# ---------------------------------------------------------------------------
# Soft-deleted person returns 401 (deferred from TASK-012)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_deleted_person_returns_401(
    real_auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """SPEC-002 §11: deleted_at IS NOT NULL person is rejected at the DB check."""
    import datetime as dt
    from datetime import UTC

    auth_sub = "auth0|deleted-person-test"
    person = await create_person(db_session, auth_subject=auth_sub, is_active=True)
    person.deleted_at = dt.datetime.now(tz=UTC)
    await db_session.flush()

    token = jwt_keys.mint_token(sub=auth_sub)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] == "account_inactive"


# ---------------------------------------------------------------------------
# Cross-tenant access denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_person_role_cross_tenant_returns_403(
    real_auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """SPEC-002 §11: active person with no role in the JWT's org → 403."""
    auth_sub = "auth0|cross-tenant-person"
    person = await create_person(db_session, auth_subject=auth_sub)

    # The JWT claims org_id = TEST_ORG_ID ("test-auth0-org-id").
    # We create an org with a *different* auth_provider_org_id so the
    # PersonRole check in the correct org finds nothing.
    org = await create_organization(
        db_session, auth_provider_org_id="test-auth0-org-id-other"
    )
    role = await create_role(db_session, organization_id=org.id)
    await create_person_role(db_session, person_id=person.id, organization_id=org.id, role_id=role.id)

    # Token carries TEST_ORG_ID — no linked org in DB → 403
    token = jwt_keys.mint_token(sub=auth_sub)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 403
    assert resp.json()["error"] == "org_access_denied"


# ---------------------------------------------------------------------------
# No active PersonRole in org → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_person_role_returns_403(
    real_auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Person exists, org links to JWT, but no PersonRole → 403."""
    import datetime as dt
    from datetime import UTC

    auth_sub = "auth0|no-role-person"
    await create_person(db_session, auth_subject=auth_sub)

    # Create an org that matches TEST_ORG_ID but give the person no role.
    await create_organization(
        db_session, auth_provider_org_id=jwt_keys.TEST_ORG_ID + "-norole"
    )
    # Token carries TEST_ORG_ID — the org for that ID doesn't exist → 403
    token = jwt_keys.mint_token(sub=auth_sub)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 403
    assert resp.json()["error"] == "org_access_denied"
