"""
Tests for Person model, service, and API endpoints (TASK-012 / SPEC-002 §2, §8, §9).

Acceptance criteria from TASK-012:
  test_create_person_returns_201
  test_list_people_returns_paginated_response
  test_get_person_returns_200
  test_update_person_returns_200
  test_delete_person_returns_204
  test_create_person_writes_audit_entry
  test_update_person_writes_audit_entry
  test_delete_person_writes_audit_entry
  test_soft_deleted_person_excluded_from_list   (named SPEC-002 §11 test)
  test_person_audit_snapshot_excludes_date_of_birth   (BR-08)
  test_list_only_returns_people_with_active_role_in_requested_org   (SPEC-002 §9)
  test_list_excludes_revoked_role_assignments   (SPEC-002 §4 revocation rule)
  test_get_returns_404_when_person_has_no_role_in_org
  test_get_returns_404_for_cross_tenant_person
  test_duplicate_email_returns_409
  test_invalid_email_format_returns_422
  test_create_person_with_phi_dob_strips_from_audit

Note: ``test_soft_deleted_person_returns_401`` is intentionally absent here —
that path lives in the auth middleware and is owned by TASK-014. See the
matching deferral note on TASK-014.

Test strategy
-------------
Service-level tests use ``db_session`` + factories directly (mirrors
``tests/test_services/test_entity_instance_service.py``). HTTP-level tests
exercise the router using the conftest ``client`` fixture so the route
wiring, permission gating, and Pydantic envelopes are also covered.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.exceptions import ConflictError, NotFoundError
from app.core.phi import PHI_EXCLUDED_FIELDS
from app.enums.identity import RoleDomain
from app.main import create_app
from app.models.compliance import AuditLog
from app.models.eav import Organization
from app.models.identity import Person
from app.schemas.identity import PersonCreate, PersonUpdate
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.identity_service import PersonService
from tests.factories.identity import create_person, create_person_role, create_role

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, *, name: str | None = None) -> Organization:
    """Insert an Organization row.

    Audit writes have an FK to ``organizations.id``; service-level tests must
    use a real org id to exercise create/update/delete code paths.
    """
    org = Organization(
        id=uuid.uuid4(),
        name=name or f"Org {uuid.uuid4().hex[:8]}",
        timezone="UTC",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    session.add(org)
    await session.flush()
    return org


def _service(
    session: AsyncSession, tenant_id: uuid.UUID, actor_id: uuid.UUID | None = None
) -> PersonService:
    audit = AuditWriter(session, _AuditScope(org_id=tenant_id, actor_id=actor_id))
    return PersonService(session=session, audit=audit, tenant_id=tenant_id, actor_id=actor_id)


async def _seed_role_for_org(
    session: AsyncSession, organization_id: uuid.UUID, *, domain: RoleDomain = RoleDomain.ADMIN
):
    """Insert a per-org Role row so tests can attach PersonRoles to it."""
    return await create_role(
        session,
        organization_id=organization_id,
        primary_domain=domain,
    )


async def _attach_role(
    session: AsyncSession,
    *,
    person_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    revoked_at: datetime | None = None,
):
    """Convenience: create a PersonRole binding."""
    return await create_person_role(
        session,
        person_id=person_id,
        organization_id=organization_id,
        role_id=role_id,
        revoked_at=revoked_at,
    )


# ---------------------------------------------------------------------------
# Service: create
# ---------------------------------------------------------------------------


async def test_service_create_persists_person(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    svc = _service(db_session, org_id)

    person = await svc.create(
        PersonCreate(first_name="Avery", last_name="Quinn", email="avery@example.test")
    )

    assert person.id is not None
    assert person.first_name == "Avery"
    assert person.last_name == "Quinn"
    assert person.email == "avery@example.test"
    assert person.is_active is True
    assert person.deleted_at is None


async def test_service_create_with_phi_dob_strips_from_audit(db_session: AsyncSession) -> None:
    """BR-08: date_of_birth must never appear in AuditLog snapshots."""
    org_id = (await _make_org(db_session)).id
    svc = _service(db_session, org_id)

    person = await svc.create(
        PersonCreate(
            first_name="DOB",
            last_name="Holder",
            email=f"dob-{uuid.uuid4().hex[:8]}@example.test",
            date_of_birth=date(1990, 4, 12),
        )
    )

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Person",
            AuditLog.resource_id == person.id,
            AuditLog.action == "create",
        )
    )
    row = result.scalar_one()
    assert row.next_state is not None
    for snapshot in (row.previous_state, row.next_state):
        if snapshot is not None:
            for forbidden in PHI_EXCLUDED_FIELDS:
                assert (
                    forbidden not in snapshot
                ), f"PHI field '{forbidden}' leaked into audit snapshot: {snapshot}"


async def test_duplicate_email_returns_409(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    svc = _service(db_session, org_id)
    email = f"dup-{uuid.uuid4().hex[:8]}@example.test"

    await svc.create(PersonCreate(first_name="First", last_name="One", email=email))

    with pytest.raises(ConflictError) as exc:
        await svc.create(PersonCreate(first_name="Second", last_name="Two", email=email))
    assert exc.value.status_code == 409
    assert "email" in exc.value.message


async def test_duplicate_auth_subject_returns_409(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    svc = _service(db_session, org_id)
    auth_subject = f"auth0|sub-{uuid.uuid4().hex[:8]}"

    await svc.create(
        PersonCreate(
            first_name="A",
            last_name="B",
            email=f"a-{uuid.uuid4().hex[:8]}@example.test",
            auth_subject=auth_subject,
        )
    )
    with pytest.raises(ConflictError):
        await svc.create(
            PersonCreate(
                first_name="C",
                last_name="D",
                email=f"c-{uuid.uuid4().hex[:8]}@example.test",
                auth_subject=auth_subject,
            )
        )


# ---------------------------------------------------------------------------
# Service: list — tenant scoping via PersonRole
# ---------------------------------------------------------------------------


async def test_list_only_returns_people_with_active_role_in_requested_org(
    db_session: AsyncSession,
) -> None:
    """SPEC-002 §9: only people with an active PersonRole in the requesting org appear."""
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)

    in_org = await create_person(db_session, last_name="InOrg")
    no_role = await create_person(db_session, last_name="NoRole")
    await _attach_role(db_session, person_id=in_org.id, organization_id=org_id, role_id=role.id)

    svc = _service(db_session, org_id)
    rows, _meta = await svc.list(PaginationParams())

    ids = {p.id for p in rows}
    assert in_org.id in ids
    assert no_role.id not in ids


async def test_list_excludes_revoked_role_assignments(db_session: AsyncSession) -> None:
    """SPEC-002 §4 revocation rule: revoked roles do not grant visibility."""
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)

    person = await create_person(db_session, last_name="Revoked")
    await _attach_role(
        db_session,
        person_id=person.id,
        organization_id=org_id,
        role_id=role.id,
        revoked_at=datetime.now(tz=UTC),
    )

    svc = _service(db_session, org_id)
    rows, _meta = await svc.list(PaginationParams())
    assert person.id not in {p.id for p in rows}


async def test_list_excludes_cross_tenant_persons(db_session: AsyncSession) -> None:
    """Tenant isolation: a person with a role only in another org is invisible here."""
    org_a = (await _make_org(db_session)).id
    org_b = (await _make_org(db_session)).id
    role_b = await _seed_role_for_org(db_session, org_b)

    person = await create_person(db_session, last_name="OtherOrg")
    await _attach_role(db_session, person_id=person.id, organization_id=org_b, role_id=role_b.id)

    svc_a = _service(db_session, org_a)
    rows, _meta = await svc_a.list(PaginationParams())
    assert person.id not in {p.id for p in rows}


async def test_soft_deleted_person_excluded_from_list(db_session: AsyncSession) -> None:
    """SPEC-002 §11 named test — soft-deleted Persons are filtered from the list."""
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)

    person = await create_person(db_session, last_name="Deleted")
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role.id)

    # Soft-delete the person directly to keep the test focused on list-filtering.
    person.deleted_at = datetime.now(tz=UTC)
    await db_session.flush()

    svc = _service(db_session, org_id)
    rows, _meta = await svc.list(PaginationParams())
    assert person.id not in {p.id for p in rows}


async def test_list_distinct_when_person_has_multiple_active_roles(
    db_session: AsyncSession,
) -> None:
    """A person with two active roles in one org appears once, not twice."""
    org_id = (await _make_org(db_session)).id
    role_a = await _seed_role_for_org(db_session, org_id)
    role_b = await _seed_role_for_org(db_session, org_id, domain=RoleDomain.PROVIDER)

    person = await create_person(db_session, last_name="Multi")
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role_a.id)
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role_b.id)

    svc = _service(db_session, org_id)
    rows, _meta = await svc.list(PaginationParams())
    assert sum(1 for p in rows if p.id == person.id) == 1


# ---------------------------------------------------------------------------
# Service: get — same scoping as list
# ---------------------------------------------------------------------------


async def test_get_returns_404_when_person_has_no_role_in_org(
    db_session: AsyncSession,
) -> None:
    org_id = (await _make_org(db_session)).id
    person = await create_person(db_session, last_name="RoleLess")

    svc = _service(db_session, org_id)
    with pytest.raises(NotFoundError) as exc:
        await svc.get(person.id)
    assert exc.value.status_code == 404


async def test_get_returns_404_for_cross_tenant_person(db_session: AsyncSession) -> None:
    """A person with a role only in another org must 404 from this org's GET."""
    org_a = (await _make_org(db_session)).id
    org_b = (await _make_org(db_session)).id
    role_b = await _seed_role_for_org(db_session, org_b)

    person = await create_person(db_session, last_name="ElsewhereOnly")
    await _attach_role(db_session, person_id=person.id, organization_id=org_b, role_id=role_b.id)

    svc_a = _service(db_session, org_a)
    with pytest.raises(NotFoundError):
        await svc_a.get(person.id)


async def test_get_succeeds_when_person_has_active_role(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)
    person = await create_person(db_session, last_name="Visible")
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role.id)

    svc = _service(db_session, org_id)
    fetched = await svc.get(person.id)
    assert fetched.id == person.id


# ---------------------------------------------------------------------------
# Service: update / delete — audit + tenant scoping
# ---------------------------------------------------------------------------


async def test_update_person_writes_audit_entry(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)
    person = await create_person(db_session, last_name="Before")
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role.id)

    svc = _service(db_session, org_id)
    await svc.update(person.id, PersonUpdate(last_name="After"))

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Person",
            AuditLog.resource_id == person.id,
            AuditLog.action == "update",
        )
    )
    row = result.scalar_one()
    assert row.previous_state["last_name"] == "Before"
    assert row.next_state["last_name"] == "After"


async def test_delete_person_soft_deletes_and_writes_audit(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)
    person = await create_person(db_session, last_name="ToDelete")
    await _attach_role(db_session, person_id=person.id, organization_id=org_id, role_id=role.id)

    svc = _service(db_session, org_id)
    await svc.delete(person.id)

    refreshed = await db_session.execute(select(Person).where(Person.id == person.id))
    refreshed_person = refreshed.scalar_one()
    assert refreshed_person.deleted_at is not None
    assert refreshed_person.updated_at == refreshed_person.deleted_at

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Person",
            AuditLog.resource_id == person.id,
            AuditLog.action == "delete",
        )
    )
    assert result.scalar_one() is not None


async def test_update_unknown_person_returns_404(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    svc = _service(db_session, org_id)
    with pytest.raises(NotFoundError):
        await svc.update(uuid.uuid4(), PersonUpdate(last_name="Anything"))


async def test_update_email_uniqueness_enforced(db_session: AsyncSession) -> None:
    org_id = (await _make_org(db_session)).id
    role = await _seed_role_for_org(db_session, org_id)

    keep = await create_person(db_session, email="keep@example.test")
    change = await create_person(db_session, email="change@example.test")
    for p in (keep, change):
        await _attach_role(db_session, person_id=p.id, organization_id=org_id, role_id=role.id)

    svc = _service(db_session, org_id)
    with pytest.raises(ConflictError):
        await svc.update(change.id, PersonUpdate(email="keep@example.test"))


# ---------------------------------------------------------------------------
# HTTP-level smoke tests (router wiring + permission gates)
#
# HTTP tests use a session-scoped client backed by the real ``get_db`` (so
# each request commits independently). Sharing the conftest ``db_session``
# across the ASGITransport boundary hangs asyncpg in this repo — see
# ``test_organizations.py`` for the same workaround. The auth context is
# overridden with ``person_id=None`` so ``audit_logs.actor_person_id`` stays
# null (system-actor) and the people FK is irrelevant for the audit rows
# these tests write.
# ---------------------------------------------------------------------------


_HTTP_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c2")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    """Session-scoped AsyncClient with real Keycloak auth (alice).

    Per ADR-010 / TASK-014, tests use real OAuth against the containerized
    Keycloak realm. Alice is seeded as a Person with the ``test-admin``
    role in ``_HTTP_ORG_ID`` (which has every default permission), and the
    returned client carries alice's bearer token + ``X-Organization-Id``
    on every request.
    """
    from tests.conftest import _fetch_keycloak_token, seed_authenticated_identity

    # Seed the http-test org via a fresh, committing session so it persists
    # across the ASGITransport boundary. INSERT-or-skip keeps it idempotent.
    session_factory = Database.get_session_factory()
    async with session_factory() as setup_session:
        exists = await setup_session.execute(
            select(Organization).where(Organization.id == _HTTP_ORG_ID)
        )
        if exists.scalar_one_or_none() is None:
            setup_session.add(
                Organization(
                    id=_HTTP_ORG_ID,
                    name="HTTP Test Org",
                    timezone="UTC",
                    is_active=True,
                    created_at=datetime.now(tz=UTC),
                )
            )
            await setup_session.commit()

        # Seed alice + role + permissions + PersonRole bound to _HTTP_ORG_ID.
        await seed_authenticated_identity(setup_session, _HTTP_ORG_ID)

    token = await _fetch_keycloak_token("alice")
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(_HTTP_ORG_ID),
        },
    ) as ac:
        yield ac


async def _commit(coro_factory):
    """Run a coroutine inside a fresh, committing DB session.

    HTTP tests need pre-seeded rows (Person, Role, PersonRole) that must be
    visible to the request transaction. Calling ``db_session`` directly
    would not commit; this helper opens a new session, runs the work, then
    commits before returning.
    """
    session_factory = Database.get_session_factory()
    async with session_factory() as session:
        result = await coro_factory(session)
        await session.commit()
        return result


async def test_create_person_returns_201(http_client: AsyncClient) -> None:
    resp = await http_client.post(
        "/api/v1/people",
        json={
            "first_name": "Casey",
            "last_name": "Reyes",
            "email": f"casey-{uuid.uuid4().hex[:8]}@example.test",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["first_name"] == "Casey"
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body


async def test_invalid_email_format_returns_422(http_client: AsyncClient) -> None:
    resp = await http_client.post(
        "/api/v1/people",
        json={"first_name": "Bad", "last_name": "Email", "email": "not-an-email"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert any("email" in d.get("field", "") for d in body["details"])


async def test_missing_required_fields_returns_422(http_client: AsyncClient) -> None:
    resp = await http_client.post("/api/v1/people", json={"first_name": "OnlyFirst"})
    assert resp.status_code == 422


async def test_duplicate_email_via_api_returns_409(http_client: AsyncClient) -> None:
    email = f"http-dup-{uuid.uuid4().hex[:8]}@example.test"
    resp = await http_client.post(
        "/api/v1/people", json={"first_name": "A", "last_name": "B", "email": email}
    )
    assert resp.status_code == 201, resp.text

    resp = await http_client.post(
        "/api/v1/people", json={"first_name": "C", "last_name": "D", "email": email}
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "conflict"


async def test_get_unknown_person_returns_404(http_client: AsyncClient) -> None:
    resp = await http_client.get(f"/api/v1/people/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


async def test_list_endpoint_returns_paginated_envelope(http_client: AsyncClient) -> None:
    """Smoke test: even with zero matching rows, the envelope is correct."""
    resp = await http_client.get("/api/v1/people")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)
    assert "limit" in body["pagination"]


async def test_list_via_api_returns_seeded_person(http_client: AsyncClient) -> None:
    """End-to-end: factory-inserted Person + PersonRole show up over HTTP."""

    async def _seed(s: AsyncSession):
        role = await _seed_role_for_org(s, _HTTP_ORG_ID)
        person = await create_person(s, last_name="HTTPListed")
        await _attach_role(s, person_id=person.id, organization_id=_HTTP_ORG_ID, role_id=role.id)
        return person

    person = await _commit(_seed)

    resp = await http_client.get("/api/v1/people")
    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()["data"]]
    assert str(person.id) in ids


async def test_patch_person_via_api_updates_fields(http_client: AsyncClient) -> None:
    """End-to-end PATCH happy path with a pre-seeded role."""

    async def _seed(s: AsyncSession):
        role = await _seed_role_for_org(s, _HTTP_ORG_ID)
        person = await create_person(s, last_name="Before")
        await _attach_role(s, person_id=person.id, organization_id=_HTTP_ORG_ID, role_id=role.id)
        return person

    person = await _commit(_seed)

    resp = await http_client.patch(
        f"/api/v1/people/{person.id}",
        json={"last_name": "After", "phone": "555-0142"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["last_name"] == "After"
    assert body["phone"] == "555-0142"


async def test_delete_person_via_api_returns_204(http_client: AsyncClient) -> None:
    async def _seed(s: AsyncSession):
        role = await _seed_role_for_org(s, _HTTP_ORG_ID)
        person = await create_person(s, last_name="HTTPDeleted")
        await _attach_role(s, person_id=person.id, organization_id=_HTTP_ORG_ID, role_id=role.id)
        return person

    person = await _commit(_seed)

    resp = await http_client.delete(f"/api/v1/people/{person.id}")
    assert resp.status_code == 204

    # After delete, the same row is invisible to the next GET (soft delete excluded).
    resp = await http_client.get(f"/api/v1/people/{person.id}")
    assert resp.status_code == 404
