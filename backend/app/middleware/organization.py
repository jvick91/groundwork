"""
OrganizationMiddleware — X-Organization-Id extraction and role check (TASK-014).

Runs after ``AuthMiddleware`` in the request pipeline. Reads the
``X-Organization-Id`` header, verifies the authenticated Person has at
least one active ``PersonRole`` in that organization, and assembles the
``AuthContext`` attached to ``request.state.auth`` that downstream FastAPI
dependencies (``get_auth_context``, ``get_audit_writer``, etc.) consume.

Pipeline per request:

  1. Skip non-HTTP scopes, ``OPTIONS``, and exempt paths (``/api/v1/health*``
     and ``/api/v1/auth/me``).
  2. When ``settings.auth_stub_enabled = True``, pass through.
  3. Confirm ``AuthMiddleware`` populated ``request.state.person_id``. If not
     (mis-configured pipeline or missing auth), 401 ``unauthorized``.
  4. Read ``X-Organization-Id``. Missing or not a UUID → 400
     ``organization_required``.
  5. Look up active ``PersonRole`` rows for ``(person, org, revoked_at IS
     NULL)`` and join ``Role.slug``. Empty → 403 ``org_access_denied``.
  6. Build and attach the ``AuthContext``.

Permission resolution is deferred to TASK-015; the ``AuthContext.permissions``
set is left empty here.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.database import Database
from app.core.security import AuthContext
from app.models.identity import Permission, PersonRole, Role, RolePermission

# Paths exempted from org-context entirely.
#   /api/v1/health* — public per SPEC-007 §8.8
#   /api/v1/auth/me — must work before org selection (SPEC-007 §3.2)
_ORG_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/health",
    "/api/v1/auth/me",
)


class OrganizationMiddleware:
    """ASGI middleware that resolves the org context for the request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

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

        state = scope.setdefault("state", {})
        person_id = state.get("person_id")
        auth_subject = state.get("auth_subject")
        if not isinstance(person_id, UUID) or not isinstance(auth_subject, str):
            # AuthMiddleware did not run or failed to populate state. Fail
            # closed: respond 401 so the client retries with credentials.
            await _emit_error(send, 401, "unauthorized", "Authentication is required.")
            return

        org_header = _read_header(scope, b"x-organization-id")
        if not org_header:
            await _emit_error(
                send,
                400,
                "organization_required",
                "X-Organization-Id header is required.",
            )
            return

        try:
            organization_id = UUID(org_header)
        except ValueError:
            await _emit_error(
                send,
                400,
                "organization_required",
                "X-Organization-Id header is required.",
            )
            return

        role_slugs, permissions = await _lookup_roles_and_permissions(
            person_id, organization_id
        )
        if not role_slugs:
            await _emit_error(
                send,
                403,
                "org_access_denied",
                "You do not have an active role in the requested organization.",
            )
            return

        state["organization_id"] = organization_id
        state["auth"] = AuthContext(
            person_id=person_id,
            auth_subject=auth_subject,
            organization_id=organization_id,
            role_slugs=role_slugs,
            permissions=permissions,
        )

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _ORG_EXEMPT_PREFIXES)


def _read_header(scope: Scope, name: bytes) -> str | None:
    """Return the first matching header value as a string, or ``None``."""
    headers = scope.get("headers", [])
    for hname, hvalue in headers:
        if hname == name:
            try:
                return hvalue.decode("latin-1").strip()
            except UnicodeDecodeError:
                return None
    return None


async def _lookup_roles_and_permissions(
    person_id: UUID, organization_id: UUID
) -> tuple[list[str], set[str]]:
    """Resolve active role slugs + effective permission slugs.

    Implements SPEC-002 §5 steps 2-4: load active PersonRoles, walk the
    ``parent_role_id`` hierarchy to collect inherited roles, then union all
    active ``RolePermission`` grants. ADR-002 — explicit joins, no
    ``relationship()``.

    Permission caching, TTL invalidation, and row-level filtering are
    deferred to TASK-015. This implementation is uncached and walks the
    hierarchy per request — acceptable for MVP and for tests; TASK-015
    will wrap this with a TTL cache and add condition evaluation.
    """
    session_factory = Database.get_session_factory()
    async with session_factory() as session:
        # Step 1 — direct active roles for (person, org)
        direct = await session.execute(
            select(Role.id, Role.slug)
            .join(PersonRole, PersonRole.role_id == Role.id)
            .where(
                PersonRole.person_id == person_id,
                PersonRole.organization_id == organization_id,
                PersonRole.revoked_at.is_(None),
            )
        )
        rows = direct.all()
        if not rows:
            return [], set()
        direct_slugs = [row[1] for row in rows]
        all_role_ids: set[UUID] = {row[0] for row in rows}

        # Step 2 — walk parent_role_id chain. Bounded by the number of
        # distinct roles in the system; in practice the depth is shallow
        # (admin → practice_admin → role-without-parent is the typical
        # tree). The loop terminates because we only add unseen IDs.
        frontier = set(all_role_ids)
        while frontier:
            parents = await session.execute(
                select(Role.parent_role_id)
                .where(Role.id.in_(frontier))
                .where(Role.parent_role_id.is_not(None))
            )
            parent_ids = {p[0] for p in parents.all() if p[0] is not None}
            new_ids = parent_ids - all_role_ids
            if not new_ids:
                break
            all_role_ids |= new_ids
            frontier = new_ids

        # Step 3 — union of active RolePermission grants. System grants
        # (organization_id IS NULL) apply across all orgs.
        perm_result = await session.execute(
            select(Permission.slug)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(all_role_ids))
            .where(RolePermission.revoked_at.is_(None))
        )
        permission_slugs = {p[0] for p in perm_result.all()}

    return direct_slugs, permission_slugs


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


__all__ = ["OrganizationMiddleware"]
