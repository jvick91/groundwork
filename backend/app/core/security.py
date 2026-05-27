"""
Authentication and authorization primitives.

Layering (TASK-014 / ADR-010):

  AuthMiddleware (app/middleware/auth.py)
      ↓ validates JWT signature, reads sub/org_id/is_active claims,
        checks X-Organization-Id mismatch, attaches JwtClaims to
        request.state.jwt_claims.

  get_auth_context (this file)
      ↓ FastAPI dependency: reads request.state.jwt_claims, hits the DB
        to resolve Person + Organization + PersonRole, issues
        SET LOCAL app.org_id inside the *request's* DB session so the
        RLS policy applies to all business-logic queries in the same
        transaction, then returns AuthContext.

  require_permission / require_type_permission (this file)
      ↓ thin dependency wrappers; TASK-015 replaces the body with
        the real RBAC resolver.

Stub mode (auth_stub_enabled = True):
  - AuthMiddleware short-circuits to a no-op and attaches stub claims.
  - get_auth_context returns the fixed _STUB_* identity without touching
    the DB.

JWKS cache (module-level):
  - fetch_jwks() fetches Auth0's JWKS once and re-fetches after the TTL.
  - Tests call set_test_jwks() to inject a static KeySet built from the
    test RSA public key, bypassing the network entirely.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.params import Depends as DependsParam
from joserfc import jwt as jose_jwt
from joserfc.jwk import KeySet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

# Fixed test identity used while ``auth_stub_enabled = True``.
#
# Local development startup seeds these IDs when the auth stub is enabled so
# audit FK constraints pass while exercising endpoints without real auth.
_STUB_PERSON_ID = UUID("00000000-0000-0000-0000-0000000000b1")
_STUB_ORG_ID = UUID("00000000-0000-0000-0000-0000000000b2")
_STUB_AUTH_SUBJECT = "auth0|stub-test-subject"

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_jwks_override: KeySet | None = None
_jwks_cache: KeySet | None = None
_jwks_fetched_at: float = 0.0


def set_test_jwks(key_set: KeySet) -> None:
    """Override the JWKS cache with a static KeySet for tests.

    Call once in a session-scoped conftest fixture after building a KeySet
    from ``jwt_keys.PUBLIC_KEY_PEM``. The override persists for the lifetime
    of the process and is never evicted by the TTL.
    """
    global _jwks_override
    _jwks_override = key_set


async def fetch_jwks() -> KeySet:
    """Return the cached JWKS KeySet, re-fetching after the TTL.

    If a test override is installed via ``set_test_jwks()`` it is returned
    immediately without any network call.
    """
    global _jwks_cache, _jwks_fetched_at

    if _jwks_override is not None:
        return _jwks_override

    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_fetched_at) < settings.jwks_cache_ttl_seconds:
        return _jwks_cache

    url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks_data = response.json()

    _jwks_cache = KeySet.import_key_set(jwks_data)
    _jwks_fetched_at = now
    return _jwks_cache


def jwks_cache_healthy() -> bool:
    """Return True if the JWKS cache has been populated (used by readiness probe)."""
    return _jwks_override is not None or _jwks_cache is not None


def decode_token(token: str, key_set: KeySet) -> dict[str, Any]:
    """Validate JWT signature and return the claims dict.

    Raises ``joserfc.errors.JoseError`` for any validation failure
    (expired, bad signature, wrong alg, etc.).
    """
    decoded = jose_jwt.decode(token, key_set)
    return dict(decoded.claims)


# ---------------------------------------------------------------------------
# AuthContext — the stable contract for all downstream dependencies
# ---------------------------------------------------------------------------


@dataclass
class AuthContext:
    """Authenticated user context attached to every authenticated request."""

    person_id: UUID | None
    auth_subject: str
    organization_id: UUID | None
    role_slugs: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)


# Paths where org_id in the JWT is not required (person-scoped only).
_ORG_EXEMPT_PATHS = {"/api/v1/auth/me"}


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Resolve the full AuthContext for the current request.

    Reads JWT claims attached to ``request.state.jwt_claims`` by
    AuthMiddleware, then performs the authoritative DB checks:
      - Person lookup by auth_subject
      - Soft-delete / is_active guard
      - Organisation resolution via auth_provider_org_id
      - Active PersonRole check (runs on every request, not cached)
      - SET LOCAL app.org_id on the *same* session used by business logic

    Stub mode: returns the fixed stub identity without any DB access.
    """
    if settings.auth_stub_enabled:
        return AuthContext(
            person_id=_STUB_PERSON_ID,
            auth_subject=_STUB_AUTH_SUBJECT,
            organization_id=_STUB_ORG_ID,
            role_slugs=["stub-admin"],
            permissions=set(),
        )

    claims: dict[str, Any] = getattr(request.state, "jwt_claims", None) or {}
    sub: str = claims.get("sub", "")
    org_id_claim: str | None = claims.get("org_id")
    is_org_exempt = request.url.path in _ORG_EXEMPT_PATHS

    # Lazy imports break the circular dependency at module load time.
    from app.models.eav import Organization
    from app.models.identity import Person, PersonRole

    # Person lookup (authoritative check — claim fast-path already ran in middleware)
    person_row = (
        await db.execute(select(Person).where(Person.auth_subject == sub))
    ).scalar_one_or_none()
    if person_row is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "No person found for auth subject."},
        )
    if not person_row.is_active or person_row.deleted_at is not None:
        raise HTTPException(
            status_code=401,
            detail={"error": "account_inactive", "message": "Account is inactive or deleted."},
        )

    org_row = None
    if org_id_claim and not is_org_exempt:
        org_row = (
            await db.execute(
                select(Organization).where(
                    Organization.auth_provider_org_id == org_id_claim
                )
            )
        ).scalar_one_or_none()
        if org_row is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "org_access_denied",
                    "message": "Organization not found or not linked to Auth0.",
                },
            )

        # Active PersonRole check — never skipped, never derived from claims
        active_role = (
            await db.execute(
                select(PersonRole).where(
                    PersonRole.person_id == person_row.id,
                    PersonRole.organization_id == org_row.id,
                    PersonRole.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if active_role is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "org_access_denied",
                    "message": "No active role in this organization.",
                },
            )

        # RLS: bind the request transaction to the correct tenant
        await db.execute(text(f"SET LOCAL app.org_id = '{org_row.id}'"))

    return AuthContext(
        person_id=person_row.id,
        auth_subject=sub,
        organization_id=org_row.id if org_row else None,
    )


async def current_person(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current authenticated person as a stable dict shape."""
    if settings.auth_stub_enabled:
        return {"id": auth.person_id, "email": "stub@groundwork.test", "is_active": True}
    return {"id": auth.person_id, "email": auth.auth_subject, "is_active": True}


async def current_org(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current organization context as a stable dict shape."""
    if settings.auth_stub_enabled:
        return {"id": auth.organization_id, "name": "Stub Organization", "timezone": "UTC"}
    return {"id": auth.organization_id, "name": "", "timezone": "UTC"}


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
