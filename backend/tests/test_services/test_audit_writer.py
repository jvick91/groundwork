"""
Tests for ``AuditWriter`` (ADR-009).

The AuditWriter is the success-path collaborator injected into every
service. These tests verify the write contract independent of any
particular domain service: PHI is filtered, ``outcome`` defaults to
``success``, the row is added and flushed, the writer never commits, and
``organization_id`` can be overridden for tenant-creation paths.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import AuditLog
from app.models.eav import Organization
from app.services.audit_service import AuditWriter, _AuditScope

pytestmark = pytest.mark.asyncio


async def _make_org(session: AsyncSession, name: str = "Test Org") -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        timezone="UTC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(org)
    await session.flush()
    return org


def _writer(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    ip: str | None = None,
    ua: str | None = None,
) -> AuditWriter:
    return AuditWriter(
        session,
        _AuditScope(org_id=org_id, actor_id=actor_id, ip_address=ip, user_agent=ua),
    )


async def test_write_adds_a_row_and_flushes_without_commit(db_session: AsyncSession):
    org = await _make_org(db_session)
    writer = _writer(db_session, org.id)
    resource_id = uuid.uuid4()

    entry = await writer.write(
        action="create",
        resource_type="Widget",
        resource_id=resource_id,
        next_state={"name": "Wrench"},
    )

    # The row exists in the session — flush happened, but commit did not
    # (the rollback fixture would erase it on test teardown).
    fetched = await db_session.get(AuditLog, entry.id)
    assert fetched is not None
    assert fetched.action == "create"
    assert fetched.resource_type == "Widget"
    assert fetched.resource_id == resource_id


async def test_write_default_outcome_is_success(db_session: AsyncSession):
    org = await _make_org(db_session)
    entry = await _writer(db_session, org.id).write(
        action="create",
        resource_type="Widget",
        resource_id=uuid.uuid4(),
    )
    assert entry.outcome == "success"


async def test_write_failure_outcome_persisted(db_session: AsyncSession):
    org = await _make_org(db_session)
    entry = await _writer(db_session, org.id).write(
        action="read",
        resource_type="Widget",
        resource_id=uuid.uuid4(),
        outcome="failure",
    )
    assert entry.outcome == "failure"


async def test_write_filters_phi_from_snapshots(db_session: AsyncSession):
    org = await _make_org(db_session)
    phi_payload = {"name": "Jane", "ssn": "111-22-3333", "value": "PHI"}

    entry = await _writer(db_session, org.id).write(
        action="update",
        resource_type="Person",
        resource_id=uuid.uuid4(),
        previous_state=phi_payload,
        next_state={"status": "active", "subjective": "PHI text"},
    )

    assert "ssn" not in (entry.previous_state or {})
    assert "value" not in (entry.previous_state or {})
    assert (entry.previous_state or {}).get("name") == "Jane"
    assert "subjective" not in (entry.next_state or {})
    assert (entry.next_state or {}).get("status") == "active"


async def test_write_persists_request_envelope_metadata(db_session: AsyncSession):
    org = await _make_org(db_session)
    entry = await _writer(db_session, org.id, ip="10.0.0.5", ua="pytest").write(
        action="create",
        resource_type="Widget",
        resource_id=uuid.uuid4(),
    )
    assert entry.ip_address == "10.0.0.5"
    assert entry.user_agent == "pytest"


async def test_write_organization_id_override_used_for_tenant_creation(
    db_session: AsyncSession,
):
    """When the audited resource *is* an Organization, the audit row's
    ``organization_id`` is the just-created tenant — not the scope's org.
    """
    scope_org = await _make_org(db_session, "Scope Org")
    new_tenant = await _make_org(db_session, "New Tenant")

    entry = await _writer(db_session, scope_org.id).write(
        action="create",
        resource_type="Organization",
        resource_id=new_tenant.id,
        organization_id=new_tenant.id,
        next_state={"name": "New Tenant"},
    )

    assert entry.organization_id == new_tenant.id


async def test_write_does_not_commit(db_session: AsyncSession):
    """Rollback after a write must remove the audit row. Atomicity is owned
    by ``get_db``, not by the writer.
    """
    org = await _make_org(db_session)
    entry = await _writer(db_session, org.id).write(
        action="create",
        resource_type="Widget",
        resource_id=uuid.uuid4(),
    )

    await db_session.rollback()

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))).scalars().all()
    )
    assert rows == []
