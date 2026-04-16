"""Smoke test for the health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_200(client: AsyncClient):
    """GET /api/v1/health should return 200 with status and version."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
