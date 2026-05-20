"""
AuthMiddleware — JWT validation and person resolution (TASK-014).

Pure ASGI middleware (no ``BaseHTTPMiddleware``). Mirrors the shape of
``app.core.request_logger.RequestLoggerMiddleware`` so streaming and
exception-propagation behavior is consistent.

Pipeline per request:

  1. Skip non-HTTP scopes, ``OPTIONS`` (CORS preflight), and exempt paths
     (``/api/v1/health*``).
  2. When ``settings.auth_stub_enabled = True``, pass through without touching
     the request. ``app.core.security.get_auth_context`` returns the fixed
     stub identity in that mode; this middleware is a no-op so existing
     tests keep working.
  3. Extract ``Authorization: Bearer <token>``. Missing → 401 ``unauthorized``.
  4. ``decode_and_validate_jwt`` against the JWKS resolver. Any failure → 401.
  5. Look up ``Person`` by ``auth_subject``. Missing → 401 ``unauthorized``.
     ``is_active = false`` or ``deleted_at IS NOT NULL`` → 401
     ``account_inactive``.
  6. Attach to ``request.state``: ``jwt_claims``, ``person_id``,
     ``auth_subject``. ``request.state.auth`` is assembled by
     ``OrganizationMiddleware`` once the org context resolves.

The 401 response uses the canonical SPEC-007 §7 envelope so the client
sees the same shape as a route-level ``GroundworkError``.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.database import Database
from app.core.security import (
    JWKSResolver,
    JWTClaims,
    decode_and_validate_jwt,
)
from app.models.identity import Person

# Paths exempted from auth entirely (SPEC-007 §8.8 — health endpoints).
_AUTH_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/health",
)


class AuthMiddleware:
    """ASGI middleware that validates the JWT and resolves the Person."""

    def __init__(self, app: ASGIApp, resolver: JWKSResolver | None = None) -> None:
        self.app = app
        self.resolver = resolver or JWKSResolver()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Stub mode: skip auth entirely. get_auth_context returns the stub
        # identity directly, no middleware involvement needed.
        if settings.auth_stub_enabled:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if _path_is_exempt(path):
            await self.app(scope, receive, send)
            return

        token = _extract_bearer_token(scope)
        if token is None:
            await _emit_error(send, 401, "unauthorized", "Authentication is required.")
            return

        try:
            claims = await decode_and_validate_jwt(token, self.resolver)
        except Exception as exc:
            message = getattr(exc, "message", None) or "Authentication failed."
            await _emit_error(send, 401, "unauthorized", message)
            return

        person_lookup = await _lookup_person(claims.sub)
        if person_lookup is None:
            await _emit_error(send, 401, "unauthorized", "Authentication is required.")
            return

        person_id, is_active, deleted_at = person_lookup
        if not is_active or deleted_at is not None:
            await _emit_error(
                send,
                401,
                "account_inactive",
                "This account is inactive or has been deleted.",
            )
            return

        # Attach resolved identity to request state for downstream middleware
        # (organization context) and FastAPI dependencies (get_auth_context).
        state = scope.setdefault("state", {})
        state["jwt_claims"] = claims
        state["person_id"] = person_id
        state["auth_subject"] = claims.sub

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_is_exempt(path: str) -> bool:
    """True when the path is in the no-auth exemption list."""
    return any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES)


def _extract_bearer_token(scope: Scope) -> str | None:
    """Pull the bearer token from the ``Authorization`` header.

    Returns ``None`` if the header is missing, not bearer-typed, or has no
    token after the scheme.
    """
    headers = scope.get("headers", [])
    for name, value in headers:
        if name == b"authorization":
            try:
                header_value = value.decode("latin-1")
            except UnicodeDecodeError:
                return None
            parts = header_value.split(None, 1)
            if len(parts) != 2:
                return None
            scheme, token = parts
            if scheme.lower() != "bearer" or not token:
                return None
            return token
    return None


async def _lookup_person(auth_subject: str) -> tuple[UUID, bool, object] | None:
    """Look up ``Person`` by ``auth_subject``.

    Returns ``(person_id, is_active, deleted_at)`` on hit, ``None`` on miss.
    Uses a fresh session because middleware runs before FastAPI's
    ``get_db`` dependency — the request transaction has not opened yet.
    """
    session_factory = Database.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Person.id, Person.is_active, Person.deleted_at).where(
                Person.auth_subject == auth_subject
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        person_id, is_active, deleted_at = row
        return person_id, bool(is_active), deleted_at


async def _emit_error(send: Send, status: int, error: str, message: str) -> None:
    """Emit a SPEC-007 §7 error envelope as the response."""
    body = json.dumps(
        {
            "error": error,
            "message": message,
            "status": status,
            "details": [],
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["AuthMiddleware", "JWTClaims"]
