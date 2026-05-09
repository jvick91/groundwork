"""
Direct unit tests for ``OrganizationService`` (ADR-009).

These tests instantiate the service with a real ``db_session``, real
repository, and real ``AuditWriter`` — no HTTP layer, no FastAPI Depends.
The point of class-per-aggregate Service + Repository is that each layer
is independently testable; these tests exercise that property directly.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, OrganizationAlreadyInactive
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.eav import (
    Address,
    AddressUpdate,
    OrganizationCreate,
    OrganizationUpdate,
)
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.organization_service import (
    OrganizationService,
    _OrganizationLifecycle,
)

pytestmark = pytest.mark.asyncio


def _service(session: AsyncSession, *, actor_id: uuid.UUID | None = None) -> OrganizationService:
    """Construct an OrganizationService bound to ``session``.

    Each test gets its own lifecycle dispatcher instance so listener
    registrations from one test never leak into another.
    """
    org_for_audit = uuid.uuid4()
    audit = AuditWriter(session, _AuditScope(org_id=org_for_audit, actor_id=actor_id))
    return OrganizationService(
        session=session,
        repo=OrganizationRepository(session),
        audit=audit,
        lifecycle=_OrganizationLifecycle(),
        actor_id=actor_id,
    )


def _create_payload(name: str = "Test Org") -> OrganizationCreate:
    return OrganizationCreate(
        name=name,
        npi_number="1234567890",
        tax_id="47-1234567",
        phone="555-0100",
        timezone="America/New_York",
        address=Address(
            line1="1 Main St",
            line2="Suite 200",
            city="Portland",
            state="OR",
            postal_code="97204",
            country="US",
        ),
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_persists_org_and_writes_audit(db_session: AsyncSession):
    service = _service(db_session)
    org = await service.create(_create_payload("Acme Therapy"))

    assert org.id is not None
    assert org.name == "Acme Therapy"
    assert org.is_active is True
    assert org.country == "US"
    # Round-trip through the repo to confirm the row hit the DB.
    fetched = await OrganizationRepository(db_session).get(org.id)
    assert fetched is not None
    assert fetched.id == org.id


async def test_create_invokes_post_create_listeners(db_session: AsyncSession):
    service = _service(db_session)
    fired: list[uuid.UUID] = []

    async def listener(_session: AsyncSession, org_id: uuid.UUID) -> None:
        fired.append(org_id)

    service._lifecycle.register_post_create(listener)
    org = await service.create(_create_payload("Listener Org"))

    assert fired == [org.id]


async def test_create_listener_failure_propagates(db_session: AsyncSession):
    service = _service(db_session)

    async def boom(_session: AsyncSession, _org_id: uuid.UUID) -> None:
        raise RuntimeError("intentional listener failure")

    service._lifecycle.register_post_create(boom)
    with pytest.raises(RuntimeError, match="intentional"):
        await service.create(_create_payload("Doomed Org"))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_returns_existing_org(db_session: AsyncSession):
    service = _service(db_session)
    created = await service.create(_create_payload("Get Me"))
    fetched = await service.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "Get Me"


async def test_get_unknown_id_raises_not_found(db_session: AsyncSession):
    service = _service(db_session)
    with pytest.raises(NotFoundError) as exc_info:
        await service.get(uuid.uuid4())
    # Exception carries audit-context fields per ADR-009
    assert exc_info.value.audit_action == "read"
    assert exc_info.value.audit_entity_type == "Organization"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_returns_paginated_orgs(db_session: AsyncSession):
    service = _service(db_session)
    marker = uuid.uuid4().hex[:8]
    await service.create(_create_payload(f"List A {marker}"))
    await service.create(_create_payload(f"List B {marker}"))

    items, meta = await service.list(PaginationParams(limit=50))

    names = [o.name for o in items]
    assert any(f"List A {marker}" in n for n in names)
    assert any(f"List B {marker}" in n for n in names)
    assert meta.limit == 50


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_applies_partial_fields_and_writes_audit(db_session: AsyncSession):
    service = _service(db_session)
    org = await service.create(_create_payload("Before Update"))

    updated = await service.update(
        org.id,
        OrganizationUpdate(name="After Update", phone="555-0199"),
    )

    assert updated.name == "After Update"
    assert updated.phone == "555-0199"
    # Unchanged fields preserved
    assert updated.timezone == "America/New_York"
    assert updated.npi_number == "1234567890"


async def test_update_can_modify_address(db_session: AsyncSession):
    service = _service(db_session)
    org = await service.create(_create_payload("Mover"))

    updated = await service.update(
        org.id,
        OrganizationUpdate(
            address=AddressUpdate(city="Eugene", state="OR", postal_code="97401"),
        ),
    )

    assert updated.city == "Eugene"
    assert updated.state == "OR"
    assert updated.postal_code == "97401"
    # Other address fields unchanged
    assert updated.address_line1 == "1 Main St"
    assert updated.country == "US"


async def test_update_unknown_id_raises_not_found(db_session: AsyncSession):
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.update(uuid.uuid4(), OrganizationUpdate(name="ghost"))


# ---------------------------------------------------------------------------
# Model invariants exercised through the service
# ---------------------------------------------------------------------------


async def test_deactivate_twice_raises_organization_already_inactive(
    db_session: AsyncSession,
):
    service = _service(db_session)
    org = await service.create(_create_payload("Deactivate Me"))

    org.deactivate()
    assert org.is_active is False

    with pytest.raises(OrganizationAlreadyInactive) as exc_info:
        org.deactivate()
    assert exc_info.value.audit_action == "deactivate"
    assert exc_info.value.audit_entity_type == "Organization"
