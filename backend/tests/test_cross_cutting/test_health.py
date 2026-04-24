"""
Tests for health check endpoints (SPEC-007 §9).

GET /api/v1/health        — liveness (always 200)
GET /api/v1/health/ready  — readiness (200 when DB ok, 503 when DB unreachable)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.routers.health import _check_database


# ---------------------------------------------------------------------------
# Liveness  —  GET /api/v1/health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liveness_returns_200(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_liveness_status_is_ok(client: AsyncClient):
    data = (await client.get("/api/v1/health")).json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_liveness_includes_version(client: AsyncClient):
    data = (await client.get("/api/v1/health")).json()
    assert "version" in data
    assert data["version"]


# ---------------------------------------------------------------------------
# Readiness (happy path)  —  GET /api/v1/health/ready
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_returns_200_when_db_ok(client: AsyncClient):
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_status_is_ready_when_db_ok(client: AsyncClient):
    data = (await client.get("/api/v1/health/ready")).json()
    assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_readiness_checks_dict_contains_database_ok(client: AsyncClient):
    data = (await client.get("/api/v1/health/ready")).json()
    assert "checks" in data
    assert data["checks"]["database"] == "ok"


# ---------------------------------------------------------------------------
# Readiness (DB-degraded path)  —  503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_returns_503_when_db_unreachable():
    """Override the DB check dependency to simulate an unreachable database."""
    app = create_app()
    app.dependency_overrides[_check_database] = lambda: "error"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as degraded_client:
        response = await degraded_client.get("/api/v1/health/ready")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_readiness_status_is_unhealthy_when_db_unreachable():
    app = create_app()
    app.dependency_overrides[_check_database] = lambda: "error"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as degraded_client:
        data = (await degraded_client.get("/api/v1/health/ready")).json()

    assert data["status"] == "unhealthy"
    assert data["checks"]["database"] == "error"


@pytest.mark.asyncio
async def test_readiness_checks_dict_extensible_for_task_014():
    """The checks dict must accommodate the future auth0_jwks key (TASK-014)."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        data = (await c.get("/api/v1/health/ready")).json()

    assert isinstance(data["checks"], dict)
