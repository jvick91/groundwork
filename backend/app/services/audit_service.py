"""
Audit service — BR-07 compliance (SPEC-006 §4, §7).

Provides a single ``log_action()`` function that every domain service calls
to write an immutable AuditLog entry in the same transaction as the business
operation it records.

PHI field exclusion (BR-08) is enforced here.  Callers supply raw state
snapshots; this module strips PHI before the row is written.  Individual
callers must never attempt their own PHI filtering — the exclusion list here
is the single platform-wide source of truth.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phi import PHI_EXCLUDED_FIELDS
from app.models.compliance import AuditLog

__all__ = ["PHI_EXCLUDED_FIELDS", "filter_phi", "log_action"]


def filter_phi(
    snapshot: dict[str, Any] | list[Any] | None,
) -> dict[str, Any] | list[Any] | None:
    """Strip PHI fields from a state snapshot before writing to AuditLog.

    Recurses into nested dicts and lists so PHI hidden inside JSONB blobs
    (e.g. ``content.subjective`` or ``items[].dob``) is also stripped.

    - Returns ``None`` if input is ``None``.
    - Never mutates the input.
    - Returns an empty dict ``{}`` if all fields were PHI.
    """
    if snapshot is None:
        return None
    if isinstance(snapshot, list):
        return [filter_phi(item) if isinstance(item, dict | list) else item for item in snapshot]
    return {
        k: (filter_phi(v) if isinstance(v, dict | list) else v)
        for k, v in snapshot.items()
        if k not in PHI_EXCLUDED_FIELDS
    }


# ---------------------------------------------------------------------------
# Core audit function
# ---------------------------------------------------------------------------


async def log_action(
    db: AsyncSession,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID,
    previous_state: dict[str, Any] | None = None,
    next_state: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Write an AuditLog entry in the current session (same transaction as caller).

    The caller **must not** commit the session before calling this function.
    The audit entry and the triggering business operation are committed
    atomically.  If this function raises, the caller's transaction rolls back
    and the business operation is also undone (SPEC-006 §7 audit atomicity).

    Parameters
    ----------
    db:
        Active ``AsyncSession`` — must be in an open, uncommitted transaction.
    org_id:
        Organization that owns the changed resource.
    actor_id:
        Person who triggered the change.  Pass ``None`` for system- or
        cron-initiated events (e.g., ``expire_consents``).
    action:
        Verb describing the operation: ``"create"``, ``"update"``,
        ``"delete"``, ``"sign"``, ``"void"``, ``"expire"``, etc.
    resource_type:
        Python class name of the resource (e.g. ``"ClinicalNote"``).
    resource_id:
        Primary key of the changed resource.
    previous_state:
        Snapshot of relevant fields *before* the change.  PHI is stripped
        automatically via ``filter_phi()``.
    next_state:
        Snapshot of relevant fields *after* the change.  PHI is stripped.
    ip_address:
        Forwarded IP from the request context, if available.
    user_agent:
        ``User-Agent`` header from the request context, if available.
    """
    entry = AuditLog(
        id=uuid.uuid4(),
        organization_id=org_id,
        actor_person_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        previous_state=filter_phi(previous_state),
        next_state=filter_phi(next_state),
        ip_address=ip_address,
        user_agent=user_agent,
        occurred_at=datetime.now(tz=UTC),
    )
    db.add(entry)
    return entry
