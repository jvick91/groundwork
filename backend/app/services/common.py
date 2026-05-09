"""
Shared service-layer plumbing.

``call_service_with_audit`` encapsulates the "do the work, then write an
audit row, then commit — or roll back everything if anything fails" dance
that BR-07 (SPEC-006 §4) requires of every state-changing endpoint. Domain
services pass it the business write closure and the audit metadata; the
helper handles ordering, atomicity, and failure semantics.

Why this lives here: re-implementing the same try/audit/commit/rollback
block in every service is the kind of repetition that causes BR-07
violations to slip in. Centralising it means every domain wires the audit
write at the same point in the transaction, and TASK-035's cross-cutting
audit-coverage assertions only need to verify one helper.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import audit_service

T = TypeVar("T")


async def call_service_with_audit(  # noqa: UP047
    db: AsyncSession,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id_getter: Callable[[T], UUID],
    operation: Callable[[], Awaitable[T]],
    previous_state: dict[str, Any] | None = None,
    next_state_getter: Callable[[T], dict[str, Any] | None] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> T:
    """Run ``operation``, write an AuditLog row in the same transaction, and return the result.

    The caller's ``operation`` produces the business artefact (e.g. the
    newly-created ORM object). The helper then derives ``resource_id`` and
    ``next_state`` from the result and writes the audit row. Both writes
    share the caller's ``db`` session so they commit or roll back atomically:
    if either the operation or the audit write raises, the entire
    transaction is rolled back and the exception propagates.

    Parameters
    ----------
    db:
        Active ``AsyncSession`` provided by the router's ``get_db`` dependency.
        The helper does not commit — that is the dependency's job, so failures
        in HTTP layers above can still trigger a rollback.
    org_id:
        Tenant scope for the audit row.
    actor_id:
        Person who triggered the change. ``None`` for system-initiated events.
    action:
        Verb describing the operation (``"create"``, ``"update"``, etc.) per
        SPEC-006 §6 and the audit coverage matrix.
    resource_type:
        Python class name of the resource (``"Organization"``).
    resource_id_getter:
        Callable that pulls the resource's primary key off the operation
        result. For most ORM models this is ``lambda x: x.id``.
    operation:
        Awaitable that performs the business write. The result is what the
        caller wants returned and what feeds the audit metadata.
    previous_state:
        Optional pre-write snapshot. ``None`` for ``create`` actions.
    next_state_getter:
        Optional callable that produces the post-write snapshot from the
        operation result. PHI is stripped automatically by the audit service.
    ip_address, user_agent:
        Forwarded request metadata, if available.

    Raises
    ------
    Any exception ``operation`` or ``audit_service.log_action`` raises is
    re-raised after the session rolls back. The helper does not swallow.
    """
    try:
        result = await operation()
        await audit_service.log_action(
            db,
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id_getter(result),
            previous_state=previous_state,
            next_state=next_state_getter(result) if next_state_getter else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return result
    except Exception:
        await db.rollback()
        raise
