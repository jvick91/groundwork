"""
Tests for the shared service-layer plumbing (TASK-008A).

Covers ``call_service_with_audit``: the helper must
  * write an AuditLog row in the same session as the business write,
  * propagate exceptions (and roll the session back) when the business
    operation raises,
  * propagate exceptions (and roll the session back) when the audit
    write raises.

Atomicity end-to-end is exercised by the existing audit-log integration
tests in ``tests/test_compliance/test_audit_log.py``; here we only
verify the helper's contract.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import AuditLog
from app.models.eav import Organization
from app.services import audit_service
from app.services.common import call_service_with_audit

pytestmark = pytest.mark.asyncio


async def _new_org(db: AsyncSession, name: str = "Acme") -> Organization:
    """Create + flush an Organization. Used as the "business write" in tests."""
    org = Organization(id=uuid.uuid4(), name=name, timezone="UTC")
    db.add(org)
    await db.flush()
    return org


async def test_call_service_with_audit_writes_audit_row(db_session: AsyncSession) -> None:
    """Happy path: business write succeeds, audit row is recorded in the same session."""
    org = await _new_org(db_session, name="Acme Inc")

    result = await call_service_with_audit(
        db_session,
        org_id=org.id,
        actor_id=None,  # System-initiated; skips people FK
        action="create",
        resource_type="Organization",
        resource_id_getter=lambda o: o.id,
        operation=lambda: _new_org(db_session, name="Acme Subsidiary"),
        next_state_getter=lambda o: {"name": o.name, "timezone": o.timezone},
    )

    assert result.name == "Acme Subsidiary"
    await db_session.flush()

    audit_rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.resource_id == result.id)))
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    audit = audit_rows[0]
    assert audit.action == "create"
    assert audit.resource_type == "Organization"
    assert audit.organization_id == org.id
    assert audit.actor_person_id is None
    assert audit.next_state == {"name": "Acme Subsidiary", "timezone": "UTC"}


async def test_call_service_with_audit_propagates_when_operation_raises(
    db_session: AsyncSession,
) -> None:
    """If the business operation raises, the helper rolls back and re-raises."""
    org = await _new_org(db_session, name="Tenant")

    async def _explode() -> Organization:
        await _new_org(db_session, name="Doomed")
        raise RuntimeError("business write failed mid-flight")

    with pytest.raises(RuntimeError, match="business write failed"):
        await call_service_with_audit(
            db_session,
            org_id=org.id,
            actor_id=None,
            action="create",
            resource_type="Organization",
            resource_id_getter=lambda o: o.id,
            operation=_explode,
        )


async def test_call_service_with_audit_propagates_when_audit_write_raises(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the audit write raises, the helper rolls back and re-raises (atomicity)."""

    async def _broken_log_action(
        db: AsyncSession,
        **_: Any,
    ) -> AuditLog:
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(audit_service, "log_action", _broken_log_action)

    org = await _new_org(db_session, name="Tenant")

    with pytest.raises(RuntimeError, match="audit write failed"):
        await call_service_with_audit(
            db_session,
            org_id=org.id,
            actor_id=None,
            action="create",
            resource_type="Organization",
            resource_id_getter=lambda o: o.id,
            operation=lambda: _new_org(db_session, name="Will be rolled back"),
        )


async def test_call_service_with_audit_returns_operation_result(
    db_session: AsyncSession,
) -> None:
    """The helper returns whatever the operation returned, unchanged."""
    sentinel: dict[str, UUID] = {"id": uuid.uuid4()}

    async def _op() -> dict[str, UUID]:
        return sentinel

    result = await call_service_with_audit(
        db_session,
        org_id=uuid.uuid4(),
        actor_id=None,
        action="noop",
        resource_type="Sentinel",
        resource_id_getter=lambda d: d["id"],
        operation=_op,
    )
    assert result is sentinel
