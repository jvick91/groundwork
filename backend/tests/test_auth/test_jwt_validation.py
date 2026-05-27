"""
Auth middleware tests — JWT validation (TASK-014).

Tests run with AUTH_STUB_ENABLED=False so the real middleware executes.
The test JWKS is installed in conftest.py (session-scoped autouse fixture).
Settings (issuer, audience) are set to match ``jwt_keys`` defaults once in
the session-scoped ``real_auth_settings`` fixture.

DB-dependent checks (Person lookup, PersonRole) live in test_org_context.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from tests.fixtures import jwt_keys


# ---------------------------------------------------------------------------
# Session-scoped settings override — applies to all tests in this module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def real_auth_settings():
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
    """httpx client backed by the test DB, with real auth middleware active."""
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health endpoints bypass auth entirely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_liveness_no_auth_required(real_auth_client: AsyncClient) -> None:
    resp = await real_auth_client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_ready_no_auth_required(real_auth_client: AsyncClient) -> None:
    resp = await real_auth_client.get("/api/v1/health/ready")
    assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# Missing / malformed Authorization header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401(real_auth_client: AsyncClient) -> None:
    resp = await real_auth_client.get("/api/v1/people")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_malformed_bearer_token_returns_401(real_auth_client: AsyncClient) -> None:
    resp = await real_auth_client.get(
        "/api/v1/people", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_token_returns_401(real_auth_client: AsyncClient) -> None:
    token = jwt_keys.mint_token(exp_offset=-60)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] in ("token_expired", "unauthorized")


# ---------------------------------------------------------------------------
# Wrong issuer / audience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_issuer_returns_401(real_auth_client: AsyncClient) -> None:
    token = jwt_keys.mint_token(iss="https://attacker.example.com/")
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_audience_returns_401(real_auth_client: AsyncClient) -> None:
    token = jwt_keys.mint_token(aud="https://wrong.example.com/")
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Missing org_id claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_org_id_returns_401(real_auth_client: AsyncClient) -> None:
    """Org-tagless tokens are rejected on non-exempt paths (ADR-010 §3.2)."""
    token = jwt_keys.mint_token(org_id=None)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] == "organization_required"


# ---------------------------------------------------------------------------
# is_active claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactive_claim_returns_401(real_auth_client: AsyncClient) -> None:
    token = jwt_keys.mint_token(is_active=False)
    resp = await real_auth_client.get("/api/v1/people", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"] == "account_inactive"


# ---------------------------------------------------------------------------
# X-Organization-Id header mismatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_id_header_mismatch_returns_400(real_auth_client: AsyncClient) -> None:
    """Header org disagrees with JWT org_id → 400 organization_mismatch."""
    token = jwt_keys.mint_token()
    resp = await real_auth_client.get(
        "/api/v1/people",
        headers={**bearer(token), "X-Organization-Id": "completely-different-org-id"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "organization_mismatch"


@pytest.mark.asyncio
async def test_org_id_header_matching_jwt_passes_middleware(real_auth_client: AsyncClient) -> None:
    """Header matching JWT org_id passes middleware (may still fail at auth_context)."""
    token = jwt_keys.mint_token()
    resp = await real_auth_client.get(
        "/api/v1/people",
        headers={**bearer(token), "X-Organization-Id": jwt_keys.TEST_ORG_ID},
    )
    # Must not be a 400 mismatch error; 401 from auth_context is acceptable here.
    assert resp.status_code != 400
