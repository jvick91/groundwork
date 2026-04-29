"""
Tests for the request-logging middleware (TASK-007).

Asserts that every HTTP request produces one structlog event whose
fields include `method`, `path`, `status_code`, and `duration_ms`,
and that the same event is emitted on the 5xx unhandled-exception
path so monitoring is not blind during outages.

Uses ``structlog.testing.capture_logs`` rather than pytest's caplog,
because structlog kwargs are rendered into the LogRecord message — they
are not preserved as record attributes for caplog to inspect.
"""

from collections.abc import MutableMapping
from typing import Any

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest_asyncio.fixture
async def app_with_failing_route() -> FastAPI:
    """App that has an extra route which raises so we can exercise the 500 path."""
    app = create_app()

    @app.get("/test/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    return app


def _request_events(
    captured: list[MutableMapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    """Filter captured events down to the ones emitted by the middleware."""
    return [e for e in captured if e.get("event") == "request"]


@pytest.mark.asyncio
async def test_request_logger_emits_required_fields_on_200(client: AsyncClient) -> None:
    """The middleware emits method/path/status_code/duration_ms on a successful request."""
    with structlog.testing.capture_logs() as captured:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200

    events = _request_events(captured)
    assert len(events) >= 1

    event = events[-1]
    assert event["method"] == "GET"
    assert event["path"] == "/api/v1/health"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], float)
    assert event["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_request_logger_emits_event_on_unhandled_500(
    app_with_failing_route: FastAPI,
) -> None:
    """Unhandled exceptions still produce a request-log event with status_code=500.

    ``raise_app_exceptions=False`` so the test sees the 500 response from
    Starlette's ServerErrorMiddleware rather than re-raising into pytest.
    """
    transport = ASGITransport(app=app_with_failing_route, raise_app_exceptions=False)
    with structlog.testing.capture_logs() as captured:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/test/explode")

    assert response.status_code == 500

    events = _request_events(captured)
    explode_events = [e for e in events if e.get("path") == "/test/explode"]
    assert len(explode_events) >= 1

    event = explode_events[-1]
    assert event["method"] == "GET"
    assert event["status_code"] == 500
    assert isinstance(event["duration_ms"], float)
