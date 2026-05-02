"""
Authentication and authorization primitives.

Until TASK-014 (auth middleware) and TASK-015 (permission resolution) land,
the dependencies here run as **stubs** gated by ``settings.auth_stub_enabled``.
While the flag is on:

  * ``get_auth_context`` returns a fixed test identity instead of validating
    a JWT.
  * ``require_permission(slug)`` allow-lists every check.

When the flag is off, both raise HTTP 501 — that path is unreachable in MVP
and will be replaced wholesale by TASK-014/015. The stub shape is intentional:
downstream domain tasks (TASK-009 onward) wire against these dependencies now,
and TASK-014/015 will swap the implementation without touching call sites.
"""

from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.params import Depends as DependsParam

from app.core.settings import settings

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


async def get_auth_context() -> AuthContext:
    """Return the auth context for the current request.

    Stub behavior (``auth_stub_enabled = True``): returns a fixed test
    identity so domain endpoints can be exercised without wiring real auth.
    TASK-014 replaces this with Auth0 JWT validation.
    """
    if settings.auth_stub_enabled:
        return AuthContext(
            person_id=_STUB_PERSON_ID,
            auth_subject=_STUB_AUTH_SUBJECT,
            organization_id=_STUB_ORG_ID,
            role_slugs=["stub-admin"],
            permissions=set(),
        )
    raise HTTPException(
        status_code=501,
        detail="Authentication not implemented. See Phase 2 (SPEC-002).",
    )


async def current_person(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current authenticated person as a documented stub shape.

    Until TASK-012 (Person model) lands, returning a dict keeps callers
    decoupled from the ORM. TASK-014/015 will swap the implementation to a
    real Person row lookup; the keys (``id``, ``email``, ``is_active``) are
    the stable contract.
    """
    return {
        "id": auth.person_id,
        "email": "stub@groundwork.test",
        "is_active": True,
    }


async def current_org(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """Return the current organization context as a documented stub shape.

    TASK-014 will resolve ``organization_id`` from the ``X-Organization-Id``
    header against the authenticated person's roles. The keys (``id``,
    ``name``, ``timezone``) are the stable contract.
    """
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
