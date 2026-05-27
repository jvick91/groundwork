"""
Auth0 Management API client tests (TASK-014D).

All Auth0 HTTP calls are mocked — no real network traffic per SPEC-007 §13.4.
Tests verify: token acquisition, in-process token caching, automatic token
refresh on 401, exponential backoff retry on 429 / 5xx, permanent error
propagation, and each wrapped operation method.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import Auth0ManagementError
from app.services.auth0_management_service import Auth0ManagementService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status: int, body: dict[str, Any] | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.content = b"x" if body is not None else b""
    resp.json.return_value = body or {}
    resp.text = str(body)
    return resp


def token_response(expires_in: int = 86400) -> MagicMock:
    return make_response(200, {"access_token": "test-token", "expires_in": expires_in})


def service(post_side_effect: Any = None, request_side_effect: Any = None) -> tuple[Auth0ManagementService, AsyncMock, AsyncMock]:
    """Build a service with a mock httpx client."""
    client = MagicMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=token_response())
    client.request = AsyncMock(return_value=make_response(200, {"user_id": "auth0|abc"}))
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    if request_side_effect is not None:
        client.request.side_effect = request_side_effect
    svc = Auth0ManagementService(
        client,
        domain="test.us.auth0.com",
        management_client_id="client-id",
        management_client_secret="client-secret",
        management_audience="https://test.us.auth0.com/api/v2/",
    )
    return svc, client.post, client.request


# ---------------------------------------------------------------------------
# Token acquisition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_acquired_on_first_request() -> None:
    svc, mock_post, mock_request = service()
    mock_request.return_value = make_response(200, {"user_id": "auth0|abc"})

    await svc.get_user("auth0|abc")

    mock_post.assert_called_once()
    call_json = mock_post.call_args.kwargs["json"]
    assert call_json["grant_type"] == "client_credentials"
    assert call_json["client_id"] == "client-id"


@pytest.mark.asyncio
async def test_token_cached_across_calls() -> None:
    svc, mock_post, mock_request = service()
    mock_request.return_value = make_response(200, {"user_id": "auth0|abc"})

    await svc.get_user("auth0|abc")
    await svc.get_user("auth0|abc")

    # Token fetched only once even though we made two API calls.
    assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_token_refreshed_after_expiry() -> None:
    svc, mock_post, mock_request = service()
    mock_request.return_value = make_response(200, {"user_id": "auth0|abc"})
    mock_post.return_value = token_response(expires_in=1)

    await svc.get_user("auth0|abc")
    # Manually expire the cached token
    svc._token_expires_at = time.monotonic() - 1

    await svc.get_user("auth0|abc")
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_token_refreshed_on_401() -> None:
    svc, mock_post, mock_request = service()
    # First call returns 401, second returns success after token refresh.
    mock_request.side_effect = [
        make_response(401),
        make_response(200, {"user_id": "auth0|abc"}),
    ]

    result = await svc.get_user("auth0|abc")

    assert result["user_id"] == "auth0|abc"
    # Token was invalidated and re-fetched once.
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_double_401_raises_management_error() -> None:
    svc, mock_post, mock_request = service()
    mock_request.return_value = make_response(401)

    with pytest.raises(Auth0ManagementError) as exc_info:
        await svc.get_user("auth0|abc")

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_on_429() -> None:
    svc, _, mock_request = service()
    mock_request.side_effect = [
        make_response(429),
        make_response(429),
        make_response(200, {"user_id": "auth0|abc"}),
    ]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await svc.get_user("auth0|abc")

    assert result["user_id"] == "auth0|abc"
    assert mock_request.call_count == 3


@pytest.mark.asyncio
async def test_retries_on_500() -> None:
    svc, _, mock_request = service()
    mock_request.side_effect = [
        make_response(500),
        make_response(200, {"user_id": "auth0|abc"}),
    ]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await svc.get_user("auth0|abc")

    assert result["user_id"] == "auth0|abc"


@pytest.mark.asyncio
async def test_exhausted_retries_raises_management_error() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(503)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Auth0ManagementError) as exc_info:
            await svc.get_user("auth0|abc")

    assert exc_info.value.status_code == 502
    assert mock_request.call_count == 3


@pytest.mark.asyncio
async def test_network_error_retries_and_raises() -> None:
    svc, _, mock_request = service()
    mock_request.side_effect = httpx.ConnectError("connection refused")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Auth0ManagementError):
            await svc.get_user("auth0|abc")


# ---------------------------------------------------------------------------
# Permanent 4xx errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_raises_management_error() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(404)

    with pytest.raises(Auth0ManagementError) as exc_info:
        await svc.get_user("auth0|nonexistent")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_409_raises_management_error() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(409, {"message": "already exists"})

    with pytest.raises(Auth0ManagementError) as exc_info:
        await svc.create_organization("test-org", "Test Org")

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(201, {"user_id": "auth0|new"})

    result = await svc.create_user("user@example.com", "S3cur3P@ss!")

    assert result["user_id"] == "auth0|new"
    body = mock_request.call_args.kwargs["json"]
    assert body["email"] == "user@example.com"
    assert body["connection"] == "Username-Password-Authentication"


@pytest.mark.asyncio
async def test_update_app_metadata() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(200, {})

    await svc.update_app_metadata("auth0|abc", {"is_active": False})

    body = mock_request.call_args.kwargs["json"]
    assert body["app_metadata"]["is_active"] is False


@pytest.mark.asyncio
async def test_delete_sessions() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(204)

    await svc.delete_sessions("auth0|abc")

    assert mock_request.call_args.args[0] == "DELETE"
    assert "sessions" in mock_request.call_args.args[1]


@pytest.mark.asyncio
async def test_revoke_refresh_tokens() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(204)

    await svc.revoke_refresh_tokens("auth0|abc")

    assert "refresh-tokens" in mock_request.call_args.args[1]


# ---------------------------------------------------------------------------
# Organization operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_organization() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(201, {"id": "org_abc", "name": "test-org"})

    result = await svc.create_organization("test-org", "Test Org")

    assert result["id"] == "org_abc"


@pytest.mark.asyncio
async def test_add_organization_member() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(204)

    await svc.add_organization_member("org_abc", "auth0|user1")

    body = mock_request.call_args.kwargs["json"]
    assert "auth0|user1" in body["members"]


@pytest.mark.asyncio
async def test_remove_organization_member() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(204)

    await svc.remove_organization_member("org_abc", "auth0|user1")

    assert mock_request.call_args.args[0] == "DELETE"


# ---------------------------------------------------------------------------
# Invitation operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_organization_invitation() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(
        201, {"id": "inv_abc", "invitee": {"email": "invited@example.com"}}
    )

    result = await svc.create_organization_invitation(
        "org_abc",
        inviter_name="Admin User",
        invitee_email="invited@example.com",
        client_id="spa-client-id",
    )

    assert result["id"] == "inv_abc"
    body = mock_request.call_args.kwargs["json"]
    assert body["invitee"]["email"] == "invited@example.com"
    assert body["inviter"]["name"] == "Admin User"


@pytest.mark.asyncio
async def test_revoke_organization_invitation() -> None:
    svc, _, mock_request = service()
    mock_request.return_value = make_response(204)

    await svc.revoke_organization_invitation("org_abc", "inv_abc")

    assert mock_request.call_args.args[0] == "DELETE"
    assert "inv_abc" in mock_request.call_args.args[1]
