"""
Tests for X-Organization-Id resolution and tenant isolation (TASK-014).

Covers SPEC-007 §3.2 (org context) and SPEC-002 §4 (tenant isolation,
revocation rule) plus §11 ``test_person_role_cross_tenant_returns_403``.

Pairs with ``test_jwt_validation.py``. Both use real Keycloak tokens per
ADR-010.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.identity import RoleDomain
from app.models.eav import Organization
from app.models.identity import Person
from tests.conftest import KEYCLOAK_USER_ALICE, KEYCLOAK_USER_EVE, KEYCLOAK_USER_HENRY
from tests.factories.identity import (
    create_person,
    create_person_role,
    create_role,
)


async def _ensure_person(
    db_session: AsyncSession,
    *,
    auth_subject: str,
) -> Person:
    """Idempotent Person creator — reuse if a row with this auth_subject exists.

    Same rationale as the helper in ``test_jwt_validation.py``: Keycloak's
    fixed user UUIDs would otherwise collide on ``UNIQUE(auth_subject)``
    when the same user is referenced by multiple tests across the session.
    """
    existing = await db_session.execute(
        select(Person).where(Person.auth_subject == auth_subject)
    )
    person = existing.scalar_one_or_none()
    if person is not None:
        return person
    return await create_person(db_session, auth_subject=auth_subject)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_org(db_session: AsyncSession) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name=f"Test Org {uuid.uuid4().hex[:8]}",
        timezone="UTC",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(org)
    await db_session.flush()
    return org


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Missing / invalid X-Organization-Id (SPEC-007 §3.2)
# ---------------------------------------------------------------------------


async def test_missing_x_organization_id_returns_400(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    org = await _create_org(db_session)
    person = await _ensure_person(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    role = await create_role(
        db_session, organization_id=org.id, primary_domain=RoleDomain.ADMIN
    )
    await create_person_role(
        db_session, person_id=person.id, organization_id=org.id, role_id=role.id
    )
    await db_session.commit()

    token = await keycloak_token("alice")
    response = await auth_client.get("/api/v1/people", headers=_bearer(token))
    assert response.status_code == 400
    assert response.json()["error"] == "organization_required"


async def test_invalid_uuid_x_organization_id_returns_400(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    org = await _create_org(db_session)
    person = await _ensure_person(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    role = await create_role(
        db_session, organization_id=org.id, primary_domain=RoleDomain.ADMIN
    )
    await create_person_role(
        db_session, person_id=person.id, organization_id=org.id, role_id=role.id
    )
    await db_session.commit()

    token = await keycloak_token("alice")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": "not-a-uuid"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "organization_required"


# ---------------------------------------------------------------------------
# Cross-tenant isolation (SPEC-002 §11)
# ---------------------------------------------------------------------------


async def test_person_role_cross_tenant_returns_403(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """SPEC-002 §11 — a Person with no active role in the requested org
    receives 403 ``org_access_denied``.

    Setup: Eve has an active role in org_a, no role in org_b. Request
    targets org_b. Auth succeeds (valid token, real Person, is_active),
    but org-context resolution fails because no PersonRole row matches.
    """
    org_a = await _create_org(db_session)
    org_b = await _create_org(db_session)
    person = await _ensure_person(db_session, auth_subject=KEYCLOAK_USER_EVE)
    role_in_a = await create_role(
        db_session, organization_id=org_a.id, primary_domain=RoleDomain.ADMIN
    )
    await create_person_role(
        db_session,
        person_id=person.id,
        organization_id=org_a.id,
        role_id=role_in_a.id,
    )
    await db_session.commit()

    token = await keycloak_token("eve")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org_b.id)},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "org_access_denied"


async def test_revoked_role_excluded_from_org_resolution(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """SPEC-002 §4 — a revoked PersonRole does not satisfy the org check."""
    org = await _create_org(db_session)
    person = await _ensure_person(db_session, auth_subject=KEYCLOAK_USER_HENRY)
    role = await create_role(
        db_session, organization_id=org.id, primary_domain=RoleDomain.ADMIN
    )
    await create_person_role(
        db_session,
        person_id=person.id,
        organization_id=org.id,
        role_id=role.id,
        revoked_at=datetime.now(tz=UTC),
    )
    await db_session.commit()

    token = await keycloak_token("henry")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org.id)},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "org_access_denied"


# ---------------------------------------------------------------------------
# Health-endpoint exemption (SPEC-007 §8.8)
# ---------------------------------------------------------------------------


async def test_health_endpoint_skips_org_requirement(auth_client: AsyncClient) -> None:
    """Health endpoints work with no X-Organization-Id."""
    response = await auth_client.get("/api/v1/health")
    assert response.status_code == 200


async def test_health_ready_skips_org_requirement(auth_client: AsyncClient) -> None:
    """Readiness probe works with no org header."""
    response = await auth_client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
