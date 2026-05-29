"""
JWT validation middleware (TASK-014 / ADR-010).

Responsibility: stateless JWT checks only — no DB access.

  1. Skip health endpoints entirely (no auth required).
  2. If AUTH_STUB_ENABLED=True: attach stub JWT claims and pass through
     so get_auth_context returns the fixed dev identity.
  3. Extract Authorization: Bearer <token>.  Missing token → 401.
  4. Decode and validate JWT signature against the JWKS cache.
  5. Validate required claims (iss, aud, sub).  Missing → 401.
  6. Read is_active claim: if False or missing → 401 (account_inactive).
  7. Read org_id claim.  Missing on a non-exempt path → 401
     (organization_required).
  8. If X-Organization-Id header is present and disagrees with JWT
     org_id → 400 (organization_mismatch).
  9. Attach validated claims to request.state.jwt_claims so
     get_auth_context (FastAPI dependency layer) can do the DB work
     without re-decoding the token.

Paths exempt from org_id requirement (person-scoped):
  /api/v1/auth/me

Health paths exempt from all auth:
  /api/v1/health  (and any sub-path)
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from joserfc.errors import JoseError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.security import _STUB_AUTH_SUBJECT, _STUB_ORG_ID, fetch_jwks, decode_token

# Paths that skip the org_id check (still require a valid JWT).
_ORG_EXEMPT_PATHS = {"/api/v1/auth/me"}

# Path prefixes that bypass authentication entirely.
# /api/v1/invitations/accept is unauthenticated: the invitee has no existing
# session; the JWT arrives in the request body and is validated by the service.
_AUTH_SKIP_PREFIXES = ("/api/v1/health", "/api/v1/invitations/accept")

# Stub claims injected when auth_stub_enabled=True.
_STUB_CLAIMS: dict[str, Any] = {
    "sub": _STUB_AUTH_SUBJECT,
    "org_id": str(_STUB_ORG_ID),
    "is_active": True,
    "iss": "stub",
    "aud": "stub",
}


def _error(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": error, "message": message, "status": status, "details": []},
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates JWTs and populates request.state."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        path = request.url.path

        # Health endpoints are always public.
        if any(path.startswith(prefix) for prefix in _AUTH_SKIP_PREFIXES):
            return await call_next(request)  # type: ignore[return-value]

        # Stub mode: skip all validation and inject a fixed identity.
        if settings.auth_stub_enabled:
            request.state.jwt_claims = _STUB_CLAIMS
            return await call_next(request)  # type: ignore[return-value]

        # --- Real JWT validation path ---

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error(401, "unauthorized", "Authorization header with Bearer token is required.")

        token = auth_header[len("Bearer "):]

        try:
            key_set = await fetch_jwks()
            claims = decode_token(token, key_set)
        except JoseError as exc:
            msg = str(exc)
            if "expired" in msg.lower():
                return _error(401, "token_expired", "JWT has expired.")
            return _error(401, "unauthorized", "JWT validation failed.")
        except Exception:
            return _error(401, "unauthorized", "JWT validation failed.")

        # Validate issuer
        expected_issuer = settings.auth0_issuer_url
        if claims.get("iss") != expected_issuer:
            return _error(401, "unauthorized", "JWT issuer is invalid.")

        # Validate audience
        aud_claim = claims.get("aud")
        expected_aud = settings.auth0_audience
        aud_list = [aud_claim] if isinstance(aud_claim, str) else (aud_claim or [])
        if expected_aud not in aud_list:
            return _error(401, "unauthorized", "JWT audience is invalid.")

        # Validate sub claim
        if not claims.get("sub"):
            return _error(401, "unauthorized", "JWT is missing the sub claim.")

        # is_active fast-path (fail-closed: missing claim → reject)
        if not claims.get("is_active", False):
            return _error(401, "account_inactive", "Account is inactive.")

        # org_id requirement
        org_id_claim: str | None = claims.get("org_id")
        is_org_exempt = path in _ORG_EXEMPT_PATHS
        if not org_id_claim and not is_org_exempt:
            return _error(
                401,
                "organization_required",
                "JWT is missing the org_id claim. A token issued for a specific "
                "Auth0 Organization is required.",
            )

        # X-Organization-Id header mismatch guard (ADR-010 §3.2)
        header_org_id = request.headers.get("X-Organization-Id")
        if header_org_id and org_id_claim and header_org_id != org_id_claim:
            return _error(
                400,
                "organization_mismatch",
                "X-Organization-Id header does not match the org_id claim in the JWT.",
            )

        request.state.jwt_claims = claims
        return await call_next(request)  # type: ignore[return-value]
