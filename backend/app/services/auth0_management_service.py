"""
Auth0 Management API client (TASK-014D / ADR-010).

Provides a typed async wrapper around the Auth0 Management API operations
needed by this project. Downstream services (TASK-014C, 014E, 014F, 014J)
inject this service and call its methods; they are responsible for writing
AuditLog entries — this client is intentionally audit-agnostic.

Design:
  - Client Credentials grant for the M2M access token, cached in-process
    with a conservative TTL. Automatically refreshed on expiry or on a 401
    from the API.
  - Exponential backoff retry on 429 (rate-limit) and 5xx errors.
  - Permanent failures or exhausted retries raise ``Auth0ManagementError``
    so callers can roll back in-flight DB transactions.

Usage:
    service = Auth0ManagementService(client=httpx.AsyncClient(), config=settings)
    user = await service.get_user("auth0|abc123")
    await service.update_app_metadata("auth0|abc123", {"is_active": False})
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.core.config import settings as _settings
from app.core.exceptions import Auth0ManagementError
from app.core.logger import get_logger

logger = get_logger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds; doubled on each retry


class Auth0ManagementService:
    """Typed async wrapper around the Auth0 Management API.

    Inject via ``get_auth0_management_service()`` FastAPI dependency or
    construct directly in tests with a mock ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        domain: str | None = None,
        management_client_id: str | None = None,
        management_client_secret: str | None = None,
        management_audience: str | None = None,
    ) -> None:
        self._client = client
        self._domain = domain or _settings.auth0_domain
        self._client_id = management_client_id or _settings.auth0_management_client_id
        self._client_secret = management_client_secret or _settings.auth0_management_client_secret
        self._audience = management_audience or _settings.auth0_management_audience
        self._token: str | None = None
        # Conservative: expire our cached token 60s before Auth0 would.
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a valid M2M access token, refreshing if needed."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        url = f"https://{self._domain}/oauth/token"
        response = await self._client.post(
            url,
            json={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "audience": self._audience,
            },
        )
        if response.status_code != 200:
            raise Auth0ManagementError(
                f"Failed to acquire Management API token: {response.status_code}",
                status_code=502,
            )
        data = response.json()
        self._token = data["access_token"]
        # expires_in is in seconds; subtract 60s safety margin
        self._token_expires_at = time.monotonic() + data.get("expires_in", 86400) - 60
        return self._token  # type: ignore[return-value]

    def _invalidate_token(self) -> None:
        self._token = None
        self._token_expires_at = 0.0

    # ------------------------------------------------------------------
    # Core request helper with retry + token refresh
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200, 201, 204),
    ) -> dict[str, Any] | None:
        """Execute a Management API request with retry and token refresh.

        Returns the parsed JSON body, or ``None`` for 204 responses.
        Raises ``Auth0ManagementError`` on permanent failure or exhausted retries.
        """
        url = f"https://{self._domain}/api/v2{path}"
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}
            try:
                response = await self._client.request(
                    method, url, headers=headers, json=json
                )
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "auth0_management_request_error",
                    attempt=attempt + 1,
                    path=path,
                    error=str(exc),
                )
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
                continue

            if response.status_code in expected_statuses:
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()  # type: ignore[no-any-return]

            if response.status_code == 401:
                # Token may have been revoked; invalidate and retry once.
                self._invalidate_token()
                if attempt == 0:
                    continue
                raise Auth0ManagementError(
                    "Management API returned 401 after token refresh.",
                    status_code=502,
                )

            if response.status_code == 404:
                raise Auth0ManagementError(
                    f"Auth0 resource not found: {path}",
                    status_code=404,
                )

            if response.status_code == 409:
                raise Auth0ManagementError(
                    f"Auth0 conflict on {path}: {response.text}",
                    status_code=409,
                )

            if response.status_code == 429 or response.status_code >= 500:
                # Transient — retry with backoff
                logger.warning(
                    "auth0_management_transient_error",
                    attempt=attempt + 1,
                    status=response.status_code,
                    path=path,
                )
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
                last_exc = Auth0ManagementError(
                    f"Auth0 Management API error {response.status_code} on {path}",
                    status_code=502,
                )
                continue

            # Any other 4xx is a permanent client error.
            raise Auth0ManagementError(
                f"Auth0 Management API returned {response.status_code}: {response.text}",
                status_code=502,
            )

        raise Auth0ManagementError(
            f"Auth0 Management API request failed after {_MAX_RETRIES} attempts: {path}",
            status_code=502,
        ) from last_exc

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    async def create_user(
        self,
        email: str,
        password: str,
        *,
        connection: str = "Username-Password-Authentication",
        app_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new Auth0 user and return the user object."""
        body: dict[str, Any] = {
            "email": email,
            "password": password,
            "connection": connection,
            "email_verified": False,
        }
        if app_metadata:
            body["app_metadata"] = app_metadata
        result = await self._request("POST", "/users", json=body, expected_statuses=(201,))
        return result  # type: ignore[return-value]

    async def get_user(self, auth0_user_id: str) -> dict[str, Any]:
        """Return the Auth0 user object for the given user ID (e.g. ``auth0|abc123``)."""
        result = await self._request("GET", f"/users/{auth0_user_id}")
        return result  # type: ignore[return-value]

    async def update_app_metadata(
        self, auth0_user_id: str, app_metadata: dict[str, Any]
    ) -> None:
        """Merge ``app_metadata`` fields into the user's Auth0 profile.

        Auth0 merges at the top level — existing keys not in ``app_metadata``
        are preserved. Pass ``None`` as a value to clear a key.
        """
        await self._request(
            "PATCH",
            f"/users/{auth0_user_id}",
            json={"app_metadata": app_metadata},
            expected_statuses=(200,),
        )

    async def delete_sessions(self, auth0_user_id: str) -> None:
        """Invalidate all active sessions for the user (force-logout)."""
        await self._request(
            "DELETE",
            f"/users/{auth0_user_id}/sessions",
            expected_statuses=(204,),
        )

    async def revoke_refresh_tokens(self, auth0_user_id: str) -> None:
        """Revoke all refresh token families for the user."""
        await self._request(
            "DELETE",
            f"/users/{auth0_user_id}/refresh-tokens",
            expected_statuses=(204,),
        )

    # ------------------------------------------------------------------
    # Organization operations
    # ------------------------------------------------------------------

    async def create_organization(
        self, name: str, display_name: str
    ) -> dict[str, Any]:
        """Create an Auth0 Organization and return the org object."""
        result = await self._request(
            "POST",
            "/organizations",
            json={"name": name, "display_name": display_name},
            expected_statuses=(201,),
        )
        return result  # type: ignore[return-value]

    async def add_organization_member(
        self, auth0_org_id: str, auth0_user_id: str
    ) -> None:
        """Add a user as a member of an Auth0 Organization."""
        await self._request(
            "POST",
            f"/organizations/{auth0_org_id}/members",
            json={"members": [auth0_user_id]},
            expected_statuses=(204,),
        )

    async def remove_organization_member(
        self, auth0_org_id: str, auth0_user_id: str
    ) -> None:
        """Remove a user from an Auth0 Organization."""
        await self._request(
            "DELETE",
            f"/organizations/{auth0_org_id}/members",
            json={"members": [auth0_user_id]},
            expected_statuses=(204,),
        )

    # ------------------------------------------------------------------
    # Invitation operations
    # ------------------------------------------------------------------

    async def create_organization_invitation(
        self,
        auth0_org_id: str,
        *,
        inviter_name: str,
        invitee_email: str,
        client_id: str,
        ttl_seconds: int = 604800,  # 7 days
    ) -> dict[str, Any]:
        """Create an Auth0 Organization invitation and return the invitation object."""
        result = await self._request(
            "POST",
            f"/organizations/{auth0_org_id}/invitations",
            json={
                "inviter": {"name": inviter_name},
                "invitee": {"email": invitee_email},
                "client_id": client_id,
                "ttl_sec": ttl_seconds,
            },
            expected_statuses=(201,),
        )
        return result  # type: ignore[return-value]

    async def revoke_organization_invitation(
        self, auth0_org_id: str, invitation_id: str
    ) -> None:
        """Revoke a pending Auth0 Organization invitation."""
        await self._request(
            "DELETE",
            f"/organizations/{auth0_org_id}/invitations/{invitation_id}",
            expected_statuses=(204,),
        )
