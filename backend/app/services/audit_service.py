"""
Audit collaborator — BR-07 compliance (SPEC-006 §4, §7).

``AuditWriter`` is the injected collaborator every Service holds in its
constructor (ADR-009). On the success path the writer adds an ``AuditLog``
row to the same ``AsyncSession`` the service operates in, so the audit
write commits or rolls back atomically with the business mutation. The
``get_db`` dependency owns the commit; this module never commits.

On the failure path the route-level exception handler (registered in
``app/main.py``) constructs a fresh session, instantiates an
``AuditWriter`` with ``outcome="failure"``, writes the row, and commits
that fresh session — independent of the request transaction (ADR-009).

PHI field exclusion (BR-08) is enforced before write via
``app.core.phi.filter_phi``. The ``PHI_EXCLUDED_FIELDS`` frozenset is the
single platform-wide source of truth.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phi import PHI_EXCLUDED_FIELDS, filter_phi
from app.models.compliance import AuditLog


@dataclass(slots=True)
class _AuditScope:
    """Per-request audit metadata (org, actor, request envelope)."""

    org_id: UUID
    actor_id: UUID | None
    ip_address: str | None = None
    user_agent: str | None = None


_audit_scope: ContextVar[_AuditScope | None] = ContextVar("_audit_scope", default=None)


class AuditWriter:
    """Writes BR-07 audit rows to a session.

    On the success path the session is the request session shared with the
    business mutation. On the failure path the session is a fresh one
    opened by the route-level exception handler — see ADR-009.
    """

    def __init__(self, session: AsyncSession, scope: _AuditScope) -> None:
        self._session = session
        self._scope = scope

    async def write(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: UUID,
        organization_id: UUID | None = None,
        previous_state: dict[str, Any] | None = None,
        next_state: dict[str, Any] | None = None,
        outcome: str = "success",
    ) -> AuditLog:
        """Add an AuditLog row to the session and flush.

        PHI is stripped from ``previous_state`` and ``next_state`` via
        ``filter_phi`` before the row is added. The caller's transaction
        owns the commit; this method only flushes.

        Parameters
        ----------
        action:
            Verb describing the operation: ``"create"``, ``"update"``,
            ``"delete"``, ``"sign"``, ``"void"``, ``"expire"``, etc.
        resource_type:
            Python class name of the resource (e.g. ``"Organization"``).
        resource_id:
            Primary key of the changed resource.
        organization_id:
            Override for the scope's ``org_id`` — needed when the audit
            row belongs to a different tenant than the request's auth
            context, most notably when the resource being audited *is*
            an Organization (tenant creation). Defaults to the scope's
            ``org_id``.
        previous_state, next_state:
            PHI-stripped JSON snapshots before/after the change.
        outcome:
            ``"success"`` (default — used by domain services on the
            success path) or ``"failure"`` (used by the route-level
            exception handler when translating ``GroundworkError`` to
            HTTP).
        """
        entry = AuditLog(
            organization_id=organization_id if organization_id is not None else self._scope.org_id,
            actor_person_id=self._scope.actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            previous_state=filter_phi(previous_state),
            next_state=filter_phi(next_state),
            ip_address=self._scope.ip_address,
            user_agent=self._scope.user_agent,
            outcome=outcome,
            occurred_at=datetime.now(tz=UTC),
        )
        self._session.add(entry)
        await self._session.flush()
        return entry


__all__ = [
    "PHI_EXCLUDED_FIELDS",
    "AuditWriter",
    "_AuditScope",
    "_audit_scope",
    "filter_phi",
]
