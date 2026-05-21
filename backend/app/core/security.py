"""
Authentication and authorization primitives.

Three things live in this module:

  1. ``AuthContext`` — the resolved identity attached to ``request.state.auth``
     by the auth middleware (or by the stub when ``settings.auth_stub_enabled``).
  2. ``JWTClaims`` + ``JWKSResolver`` + ``decode_and_validate_jwt`` — the JWT
     pipeline used by ``app/middleware/auth.py``. The resolver fetches Auth0
     JWKS in production and falls back to a static PEM in tests / local dev
     (``settings.auth_jwt_static_public_key_pem``).
  3. The legacy ``get_auth_context`` / ``current_person`` / ``current_org`` /
     ``require_permission`` / ``require_type_permission`` dependencies —
     gated by ``settings.auth_stub_enabled``. When the flag is on they return
     fixed stub identities (preserved for existing tests). When off they read
     the ``AuthContext`` that the middleware attached to ``request.state.auth``
     and require a real authenticated session.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.params import Depends as DependsParam
from joserfc import jwt
from joserfc.errors import BadSignatureError, ExpiredTokenError, JoseError
from joserfc.jwk import KeySet, RSAKey
from joserfc.jwt import JWTClaimsRegistry

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

# Fixed test identity used while ``auth_stub_enabled = True``.
#
# Local development startup seeds these IDs when the auth stub is enabled so
# audit FK constraints pass while exercising endpoints without real auth.
_STUB_PERSON_ID = UUID("00000000-0000-0000-0000-0000000000b1")
_STUB_ORG_ID = UUID("00000000-0000-0000-0000-0000000000b2")
_STUB_AUTH_SUBJECT = "auth0|stub-test-subject"


@dataclass
class AuthContext:
    """Authenticated user context extracted from a validated JWT."""

    person_id: UUID | None
    auth_subject: str
    organization_id: UUID
    role_slugs: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)


@dataclass
class JWTClaims:
    """Validated claims extracted from a JWT — what the middleware exposes."""

    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    iat: int
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# JWKS resolver
# ---------------------------------------------------------------------------


class JWKSResolver:
    """Resolve signing keys for JWT validation.

    Two modes, selected at call time so test fixtures that monkeypatch
    ``settings`` take effect without a process restart:

    * **Static PEM mode** — ``settings.auth_jwt_static_public_key_pem`` is
      non-empty. The PEM is parsed once and returned for every ``kid``.
      Used by tests (the conftest sets this to the
      ``tests/fixtures/jwt_keys.PUBLIC_KEY_PEM``) and any local dev
      configuration that does not have an Auth0 tenant.

    * **Auth0 JWKS mode** — ``settings.oidc_domain`` is non-empty. The
      ``.well-known/jwks.json`` document is fetched and cached in process
      with a TTL. On cache miss for a requested ``kid``, the cache is
      refreshed once before giving up.
    """

    _jwks_ttl_seconds: float = 600.0  # 10 minutes

    def __init__(self) -> None:
        self._static_key: RSAKey | None = None
        self._static_pem: str = ""
        self._key_set: KeySet | None = None
        self._key_set_fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str | None) -> RSAKey:
        """Return the RSA key for ``kid``.

        Raises ``UnauthorizedError`` if no matching key can be found.
        """
        static_pem = settings.auth_jwt_static_public_key_pem
        if static_pem:
            return self._get_static_key(static_pem)
        # Need a configured issuer (or Auth0 domain, which derives one) for
        # OIDC discovery to locate the JWKS endpoint.
        if not settings.oidc_issuer and not settings.oidc_domain:
            raise UnauthorizedError(message="Authentication is not configured.")
        return await self._get_jwks_key(kid)

    def _get_static_key(self, pem: str) -> RSAKey:
        if self._static_key is None or pem != self._static_pem:
            self._static_pem = pem
            self._static_key = RSAKey.import_key(pem.encode())
        return self._static_key

    async def _get_jwks_key(self, kid: str | None) -> RSAKey:
        key_set = await self._load_key_set(force_refresh=False)
        key = self._find_kid(key_set, kid)
        if key is not None:
            return key
        # Unknown kid — refresh once in case the issuer rotated keys.
        key_set = await self._load_key_set(force_refresh=True)
        key = self._find_kid(key_set, kid)
        if key is None:
            raise UnauthorizedError(message="Signing key not found for token.")
        return key

    async def _load_key_set(self, *, force_refresh: bool) -> KeySet:
        now = time.monotonic()
        if (
            not force_refresh
            and self._key_set is not None
            and (now - self._key_set_fetched_at) < self._jwks_ttl_seconds
        ):
            return self._key_set
        async with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._key_set is not None
                and (now - self._key_set_fetched_at) < self._jwks_ttl_seconds
            ):
                return self._key_set
            # OIDC discovery: fetch /.well-known/openid-configuration and read
            # ``jwks_uri`` from it. This works against any compliant OIDC
            # provider (Auth0, Keycloak, Cognito, Clerk, Okta) — production
            # uses Auth0; tests use Keycloak (ADR-010).
            issuer_url = settings.oidc_issuer_url.rstrip("/")
            discovery_url = f"{issuer_url}/.well-known/openid-configuration"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    discovery = await client.get(discovery_url)
                    discovery.raise_for_status()
                    discovery_payload = discovery.json()
                    jwks_uri = discovery_payload.get("jwks_uri")
                    if not isinstance(jwks_uri, str) or not jwks_uri:
                        raise UnauthorizedError(message="OIDC discovery document missing jwks_uri.")
                    jwks_response = await client.get(jwks_uri)
                    jwks_response.raise_for_status()
                    payload = jwks_response.json()
            except UnauthorizedError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                raise UnauthorizedError(
                    message="Unable to fetch signing keys from identity provider."
                ) from exc
            self._key_set = KeySet.import_key_set(payload)
            self._key_set_fetched_at = time.monotonic()
            return self._key_set

    @staticmethod
    def _find_kid(key_set: KeySet, kid: str | None) -> RSAKey | None:
        if kid is None:
            keys = key_set.keys
            return cast(RSAKey, keys[0]) if keys else None
        try:
            return cast(RSAKey, key_set.get_by_kid(kid))
        except (KeyError, ValueError):
            return None

    async def health(self) -> str:
        """Probe the resolver. Returns ``ok`` when at least one key is loadable."""
        try:
            static_pem = settings.auth_jwt_static_public_key_pem
            if static_pem:
                self._get_static_key(static_pem)
                return "ok"
            if not settings.oidc_issuer and not settings.oidc_domain:
                return "error"
            key_set = await self._load_key_set(force_refresh=False)
            return "ok" if key_set.keys else "error"
        except Exception:
            return "error"


# ---------------------------------------------------------------------------
# JWT decode + claim validation
# ---------------------------------------------------------------------------


async def decode_and_validate_jwt(token: str, resolver: JWKSResolver) -> JWTClaims:
    """Decode and validate ``token`` against ``settings`` issuer / audience.

    Raises ``UnauthorizedError`` (HTTP 401) on any failure — malformed token,
    bad signature, expired, wrong issuer, wrong audience, missing ``sub``.
    """
    if not token:
        raise UnauthorizedError()

    try:
        header_segment = token.split(".", 1)[0]
    except (AttributeError, IndexError) as exc:
        raise UnauthorizedError() from exc

    # Peek at the header for the ``kid`` before full decode so we can fetch
    # the right key from the JWKS. joserfc's decode wants the key up front.
    try:
        padded = header_segment + "=" * (-len(header_segment) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise UnauthorizedError() from exc

    kid = header.get("kid") if isinstance(header, dict) else None
    try:
        key = await resolver.get_key(kid)
    except UnauthorizedError:
        raise
    except Exception as exc:
        raise UnauthorizedError() from exc

    try:
        decoded = jwt.decode(token, key, algorithms=["RS256"])
    except (BadSignatureError, JoseError, ValueError) as exc:
        raise UnauthorizedError() from exc

    claims = decoded.claims
    if not isinstance(claims, dict):
        raise UnauthorizedError()

    expected_issuer = (
        settings.oidc_issuer_url if (settings.oidc_issuer or settings.oidc_domain) else None
    )
    expected_audience = settings.oidc_audience or None

    registry_kwargs: dict[str, Any] = {
        "sub": {"essential": True},
        "exp": {"essential": True},
        "iat": {"essential": False},
    }
    if expected_issuer:
        registry_kwargs["iss"] = {"essential": True, "value": expected_issuer}
    if expected_audience:
        registry_kwargs["aud"] = {"essential": True, "value": expected_audience}

    registry = JWTClaimsRegistry(**registry_kwargs)
    try:
        registry.validate(claims)
    except ExpiredTokenError as exc:
        raise UnauthorizedError(message="Token has expired.") from exc
    except JoseError as exc:
        raise UnauthorizedError() from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise UnauthorizedError()

    return JWTClaims(
        sub=sub,
        iss=str(claims.get("iss", "")),
        aud=cast("str | list[str]", claims.get("aud", "")),
        exp=int(claims.get("exp", 0)),
        iat=int(claims.get("iat", 0)),
        raw=claims,
    )


# ---------------------------------------------------------------------------
# Legacy stub-aware dependencies
# ---------------------------------------------------------------------------


async def get_auth_context(request: Request) -> AuthContext:
    """Return the auth context for the current request.

    * Stub mode (``auth_stub_enabled = True``) — returns the fixed test
      identity so domain endpoints can be exercised without real JWTs.
      ``request`` is unused in this mode but is still required by the
      signature (FastAPI's introspection doesn't support
      ``Request | None``). Tests that exercise the stub path directly
      can pass a minimal Starlette Request constructed from a stub scope.
    * Middleware mode (``auth_stub_enabled = False``) — reads the
      ``AuthContext`` that ``app.middleware.auth.AuthMiddleware`` and
      ``app.middleware.organization.OrganizationMiddleware`` attached to
      ``request.state.auth``. Raises 401 if the middleware did not run
      (e.g. a misconfiguration).
    """
    if settings.auth_stub_enabled:
        return AuthContext(
            person_id=_STUB_PERSON_ID,
            auth_subject=_STUB_AUTH_SUBJECT,
            organization_id=_STUB_ORG_ID,
            role_slugs=["stub-admin"],
            permissions=set(),
        )
    auth = getattr(request.state, "auth", None)
    if isinstance(auth, AuthContext):
        return auth
    raise UnauthorizedError()


async def current_person(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current authenticated person as a documented stub shape."""
    return {
        "id": auth.person_id,
        "email": "stub@groundwork.test",
        "is_active": True,
    }


async def current_org(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current organization context as a documented stub shape."""
    return {
        "id": auth.organization_id,
        "name": "Stub Organization",
        "timezone": "UTC",
    }


def require_permission(permission_slug: str) -> DependsParam:
    """Dependency factory that checks a specific permission.

    Stub behavior (``auth_stub_enabled = True``): allow-lists every check.
    TASK-015 replaces ``_check_permission`` with the real RBAC resolver.
    """

    async def _check_permission(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if settings.auth_stub_enabled:
            return auth
        if permission_slug not in auth.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {permission_slug}",
            )
        return auth

    return cast(DependsParam, Depends(_check_permission))


def require_type_permission(action: str) -> DependsParam:
    """Dependency factory for dynamic ``{type_slug}.{action}`` permission checks.

    Stub behavior (``auth_stub_enabled = True``): allow-lists every check.
    TASK-015 wires in real RBAC resolution.
    """

    async def _check_type_permission(
        type_slug: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if settings.auth_stub_enabled:
            return auth
        permission = f"{type_slug}.{action}"
        if permission not in auth.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {permission}",
            )
        return auth

    return cast(DependsParam, Depends(_check_type_permission))
