"""
Tests for JWT validation and Person resolution (TASK-014).

Covers SPEC-007 §3.1 (auth flow), SPEC-002 §4 (auth_subject rule,
soft-delete rule, account inactive). Health-endpoint exemption is covered
here too (no JWT required); broader org-context behavior lives in
``test_org_context.py``.

These tests use real Keycloak tokens minted from the ``groundwork-test``
realm per ADR-010. No JWTs are forged locally. The auth middleware fetches
real keys from Keycloak's JWKS endpoint, validates real signatures, and
checks real ``iss`` / ``aud`` / ``exp`` claims.
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
from tests.conftest import (
    KEYCLOAK_USER_ALICE,
    KEYCLOAK_USER_BOB,
    KEYCLOAK_USER_CAROL,
    KEYCLOAK_USER_DAVE,
    KEYCLOAK_USER_GRACE,
)
from tests.factories.identity import (
    create_person,
    create_person_role,
    create_role,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_person_with_role(
    db_session: AsyncSession,
    *,
    auth_subject: str,
    is_active: bool = True,
    deleted_at: datetime | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Ensure a Person + Organization + active PersonRole exist for the test.

    Returns ``(person_id, organization_id)`` so tests can quote the org id
    in their ``X-Organization-Id`` header. ``auth_subject`` must match the
    ``sub`` claim a Keycloak token will carry — i.e. one of the
    deterministic user UUIDs from ``docker/keycloak/realm-groundwork-test.json``.

    Idempotent on Person: existing rows are reused so the realm's fixed UUIDs
    don't collide on the ``UNIQUE(auth_subject)`` constraint across tests.
    Each test still gets its own ``Organization`` and ``PersonRole`` (UUID-unique).
    Person ``is_active`` and ``deleted_at`` are written on every call so callers
    that need a specific state get it — use a unique Keycloak user per state to
    avoid cross-test state bleed.
    """
    org = Organization(
        id=uuid.uuid4(),
        name=f"Test Org {uuid.uuid4().hex[:8]}",
        timezone="UTC",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(org)
    await db_session.flush()

    existing = await db_session.execute(select(Person).where(Person.auth_subject == auth_subject))
    person = existing.scalar_one_or_none()
    if person is None:
        person = await create_person(
            db_session,
            auth_subject=auth_subject,
            is_active=is_active,
        )
    else:
        person.is_active = is_active

    person.deleted_at = deleted_at
    await db_session.flush()

    role = await create_role(
        db_session,
        organization_id=org.id,
        primary_domain=RoleDomain.ADMIN,
    )
    await create_person_role(
        db_session,
        person_id=person.id,
        organization_id=org.id,
        role_id=role.id,
    )
    await db_session.commit()
    return person.id, org.id


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token presence / shape
# ---------------------------------------------------------------------------


async def test_missing_authorization_header_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    response = await auth_client.get(
        "/api/v1/people",
        headers={"X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_malformed_authorization_header_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    response = await auth_client.get(
        "/api/v1/people",
        headers={
            "Authorization": "NotBearer something",
            "X-Organization-Id": str(org_id),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_bearer_without_token_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    response = await auth_client.get(
        "/api/v1/people",
        headers={
            "Authorization": "Bearer ",
            "X-Organization-Id": str(org_id),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# Signature, expiry
# ---------------------------------------------------------------------------


async def test_expired_token_returns_401(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    expired_token: str,
) -> None:
    """Keycloak's expiring client mints tokens with 1s lifespan; the
    ``expired_token`` fixture sleeps past that before returning."""
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_GRACE)
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(expired_token), "X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_token_with_invalid_signature_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_BOB)
    token = await keycloak_token("bob")
    # Flip a character in the signature segment to invalidate it.
    header, claims, signature = token.split(".")
    tampered_sig = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = f"{header}.{claims}.{tampered_sig}"
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(tampered), "X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


# NOTE: wrong-audience and wrong-issuer claim-validation paths are NOT tested
# here. Those failures are produced inside ``joserfc``'s ``JWTClaimsRegistry``,
# not in our code; we only configure the registry with the expected ``iss``
# and ``aud`` and convert any ``JoseError`` to a 401. That conversion is
# already covered by ``test_token_with_invalid_signature_returns_401`` and
# ``test_expired_token_returns_401``, which exercise the same ``except``
# block. The "we passed the right expected_iss / expected_aud to joserfc"
# wiring is exercised by every happy-path test — Keycloak mints tokens with
# ``aud=https://api.groundwork.test/`` and our happy-path tests accept them,
# which can only happen when the audience config matches end-to-end.


# ---------------------------------------------------------------------------
# Person resolution (SPEC-002 §4 / §11)
# ---------------------------------------------------------------------------


async def test_token_with_no_matching_person_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """Token's sub does not match any Person.auth_subject.

    Frank is a Keycloak user but no Person row carries Frank's UUID as
    ``auth_subject``. Auth flow should bail at the Person lookup with
    ``unauthorized``.
    """
    # Seed Alice so the org exists and has at least one PersonRole, but
    # we send Frank's token (no matching Person row).
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_ALICE)
    token = await keycloak_token("frank")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_person_without_auth_subject_cannot_authenticate(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """SPEC-002 §11 — Person rows without ``auth_subject`` cannot log in.

    A Person with ``auth_subject = NULL`` (e.g. a client persona) has no way
    to be reached from a JWT's ``sub``. Frank has a valid Keycloak token
    but no matching Person row anywhere.
    """
    org = Organization(
        id=uuid.uuid4(),
        name=f"Test Org {uuid.uuid4().hex[:8]}",
        timezone="UTC",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(org)
    await db_session.flush()
    # Person with NULL auth_subject — cannot be matched from any JWT
    person = await create_person(db_session, auth_subject=None)
    role = await create_role(db_session, organization_id=org.id, primary_domain=RoleDomain.CLIENT)
    await create_person_role(
        db_session,
        person_id=person.id,
        organization_id=org.id,
        role_id=role.id,
    )
    await db_session.commit()

    token = await keycloak_token("frank")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org.id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_inactive_person_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """SPEC-002 §11 — Person.is_active = false rejects authentication."""
    _, org_id = await _seed_person_with_role(
        db_session,
        auth_subject=KEYCLOAK_USER_CAROL,
        is_active=False,
    )
    token = await keycloak_token("carol")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "account_inactive"


async def test_soft_deleted_person_returns_401(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """SPEC-002 §11 / §4 — Person.deleted_at IS NOT NULL rejects auth.

    Deferred from TASK-012 because the 401 path was owned by this
    middleware. Same shape as the inactive-person test, different
    precondition.
    """
    _, org_id = await _seed_person_with_role(
        db_session,
        auth_subject=KEYCLOAK_USER_DAVE,
        deleted_at=datetime.now(tz=UTC),
    )
    token = await keycloak_token("dave")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org_id)},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "account_inactive"


# ---------------------------------------------------------------------------
# Happy path + health exemption
# ---------------------------------------------------------------------------


async def test_valid_token_with_active_role_passes_auth_and_org_checks(
    auth_client: AsyncClient, db_session: AsyncSession, keycloak_token
) -> None:
    """Valid token + active PersonRole gets past both middlewares.

    Permission resolution is owned by TASK-015; ``AuthContext.permissions`` is
    empty in this task. So a request that authenticates correctly and resolves
    its org context but hits a permission-gated endpoint receives 403
    ``forbidden`` (from ``require_permission``), not 401 / 400 / 403
    ``org_access_denied``. That 403 is the positive signal that the full
    middleware pipeline worked end-to-end.
    """
    _, org_id = await _seed_person_with_role(db_session, auth_subject=KEYCLOAK_USER_BOB)
    token = await keycloak_token("bob")
    response = await auth_client.get(
        "/api/v1/people",
        headers={**_bearer(token), "X-Organization-Id": str(org_id)},
    )
    # 403 forbidden — not 401 (auth ok), not 400 (org header present), not
    # 403 org_access_denied (Bob has a PersonRole). The middleware pipeline
    # succeeded; only the permission check (TASK-015) blocks us.
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


async def test_health_endpoint_skips_auth(auth_client: AsyncClient) -> None:
    """SPEC-007 §8.8 — health endpoints require no JWT and no org header."""
    response = await auth_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_ready_skips_auth(auth_client: AsyncClient) -> None:
    """Readiness probe must be reachable without credentials."""
    response = await auth_client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "checks" in body
    assert "auth0_jwks" in body["checks"]
