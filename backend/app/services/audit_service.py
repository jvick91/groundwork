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
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog


# ---------------------------------------------------------------------------
# PHI exclusion list  (SPEC-006 §4 BR-08, SPEC-001 §7)
# ---------------------------------------------------------------------------
# Every top-level key in this set is stripped from previous_state and
# next_state before the AuditLog row is written.  The list is conservative
# by design: if a field name appears here it is excluded regardless of which
# resource type the snapshot came from.  It is always safer to over-exclude.

PHI_EXCLUDED_FIELDS: frozenset[str] = frozenset({
    # ClinicalNote — the entire content JSONB carries clinical notes (PHI)
    "content",
    # Person demographics
    "date_of_birth",
    "ssn",
    "emergency_contact_name",
    "emergency_contact_phone",
    # AttributeValue — SPEC-001 §7 explicitly requires value exclusion
    "value",
    # ClientConsent free-text
    "notes",
    # Document free-text
    "description",
    # Billing — diagnosis codes correlated to a specific client
    "diagnosis_codes",
})


def filter_phi(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip PHI fields from a state snapshot before writing to AuditLog.

    - Returns ``None`` if input is ``None``.
    - Never mutates the input dict.
    - Returns an empty dict ``{}`` if all fields were PHI.
    """
    if snapshot is None:
        return None
    return {k: v for k, v in snapshot.items() if k not in PHI_EXCLUDED_FIELDS}


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
        occurred_at=datetime.now(tz=timezone.utc),
    )
    db.add(entry)
    return entry
