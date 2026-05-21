"""
Shared pytest fixtures for async database testing.

The backend container runs in real-auth mode (``AUTH_STUB_ENABLED=false`` in
``backend/.env.backend``), so the test process inherits the same mode.
Every test that hits an HTTP endpoint authenticates against the
containerized Keycloak realm per ADR-010.

There is no ``monkeypatch`` of ``settings`` anywhere in this file and no
mocking. The ``client`` fixture seeds a default "alice" identity (Person +
Organization + Role + Permissions + RolePermissions + PersonRole) on first
use and reuses those rows idempotently across the session. Each test that
needs an HTTP client gets one that auto-attaches ``Authorization: Bearer
<alice-token>`` and ``X-Organization-Id: <alice-org-id>`` so legacy tests
authored against the stub identity keep working unchanged.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, Database
from app.core.dependencies import get_db
from app.enums.identity import RoleDomain
from app.main import create_app
from app.models.eav import Organization
from app.models.identity import Permission, Person, PersonRole, Role, RolePermission

# Tracks every db_session instance so create_tables teardown can close them
# before drop_all, releasing any table locks held by open/aborted transactions.
_open_sessions: list[AsyncSession] = []


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialize_database() -> AsyncGenerator[None, None]:
    """Initialize the production Database singleton against the test DB."""
    Database.initialize(settings.test_database_url, poolclass=NullPool)
    yield
    await Database.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """Create a single async engine for the entire test session."""
    engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def create_tables(test_engine):
    """Create all tables once at the start of the test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    for session in _open_sessions:
        with contextlib.suppress(Exception):
            await session.close()
    _open_sessions.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test database session backed by the Database singleton (NullPool)."""
    session: AsyncSession = Database.get_session_factory()()
    _open_sessions.append(session)
    try:
        yield session
    finally:
        with contextlib.suppress(Exception):
            await session.close()


# ---------------------------------------------------------------------------
# Keycloak token-factory fixtures (ADR-010)
# ---------------------------------------------------------------------------

KEYCLOAK_BASE_URL = "http://keycloak-test:8080"
KEYCLOAK_REALM = "groundwork-test"
KEYCLOAK_CLIENT_ID = "groundwork-backend-test"
KEYCLOAK_CLIENT_SECRET = "test-client-secret"
KEYCLOAK_EXPIRING_CLIENT_ID = "groundwork-backend-test-expiring"
KEYCLOAK_EXPIRING_CLIENT_SECRET = "test-client-secret-expiring"

# Deterministic test user IDs matching the realm-import JSON. The Keycloak
# ``sub`` claim equals the user's ``id`` field, so these are the values
# Persons are seeded with in ``auth_subject``.
KEYCLOAK_USER_ALICE = "11111111-1111-1111-1111-111111111111"
KEYCLOAK_USER_BOB = "22222222-2222-2222-2222-222222222222"
KEYCLOAK_USER_CAROL = "33333333-3333-3333-3333-333333333333"
KEYCLOAK_USER_DAVE = "44444444-4444-4444-4444-444444444444"
KEYCLOAK_USER_EVE = "55555555-5555-5555-5555-555555555555"
KEYCLOAK_USER_FRANK = "66666666-6666-6666-6666-666666666666"
KEYCLOAK_USER_GRACE = "77777777-7777-7777-7777-777777777777"
KEYCLOAK_USER_HENRY = "88888888-8888-8888-8888-888888888888"

KEYCLOAK_PASSWORDS: dict[str, str] = {
    "alice": "alice-password",
    "bob": "bob-password",
    "carol": "carol-password",
    "dave": "dave-password",
    "eve": "eve-password",
    "frank": "frank-password",
    "grace": "grace-password",
    "henry": "henry-password",
}

# Session-scoped token cache so we don't pay the Keycloak round-trip per
# test. Tokens are reused until the realm's ``accessTokenLifespan`` elapses;
# tests don't run long enough for that to matter.
_token_cache: dict[tuple[str, str], str] = {}


TokenFactory = Callable[..., Any]


async def _fetch_keycloak_token(
    username: str,
    *,
    client_id: str = KEYCLOAK_CLIENT_ID,
    client_secret: str = KEYCLOAK_CLIENT_SECRET,
) -> str:
    """Fetch an access token via Direct Access Grants (password) flow."""
    cache_key = (username, client_id)
    if cache_key in _token_cache:
        return _token_cache[cache_key]

    password = KEYCLOAK_PASSWORDS.get(username)
    if password is None:
        raise KeyError(f"Unknown Keycloak test user: {username!r}")

    token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
            },
        )
        response.raise_for_status()
        body = response.json()
    token = str(body["access_token"])
    _token_cache[cache_key] = token
    return token


@pytest_asyncio.fixture
async def keycloak_token() -> TokenFactory:
    """Return an async callable that mints a Keycloak token for ``username``."""

    async def _mint(username: str, **overrides: Any) -> str:
        return await _fetch_keycloak_token(username, **overrides)

    return _mint


@pytest_asyncio.fixture
async def expired_token() -> str:
    """Return a Keycloak token that has already expired."""
    import time

    token = await _fetch_keycloak_token(
        "grace",
        client_id=KEYCLOAK_EXPIRING_CLIENT_ID,
        client_secret=KEYCLOAK_EXPIRING_CLIENT_SECRET,
    )
    time.sleep(2)
    # Re-fetch never caches expired-mode tokens — each call is a fresh one.
    _token_cache.pop(("grace", KEYCLOAK_EXPIRING_CLIENT_ID), None)
    return token


# ---------------------------------------------------------------------------
# Default-identity seeding (used by the ``client`` fixture)
# ---------------------------------------------------------------------------
#
# These constants match the stub UUIDs from ``app/core/security.py``. Tests
# that hardcoded ``_STUB_PERSON_ID`` / ``_STUB_ORG_ID`` keep working because
# the default authenticated identity uses the same IDs.

DEFAULT_PERSON_ID = UUID("00000000-0000-0000-0000-0000000000b1")
DEFAULT_ORG_ID = UUID("00000000-0000-0000-0000-0000000000b2")
DEFAULT_ROLE_SLUG = "test-admin"

# Every permission slug that any router declares — plus the
# ``{system_entity_type}.{action}`` permutations the dynamic
# ``require_type_permission`` will check. Granting all of these to alice's
# test role lets legacy tests that don't authenticate explicitly still pass.
_DEFAULT_PERMISSIONS: tuple[str, ...] = (
    "settings.read",
    "settings.write",
    "people.read",
    "people.write",
    "people.delete",
    "entity_types.read",
    "entity_types.write",
    "entity_types.delete",
    "audit.read",
    "provider.read",
    "provider.write",
    "provider.delete",
    "client.read",
    "client.write",
    "client.delete",
    "admin.read",
    "admin.write",
    "admin.delete",
)


async def _ensure_default_org(session: AsyncSession) -> UUID:
    """Idempotent seed of alice's organization."""
    existing = await session.execute(select(Organization).where(Organization.id == DEFAULT_ORG_ID))
    if existing.scalar_one_or_none() is not None:
        return DEFAULT_ORG_ID
    org = Organization(
        id=DEFAULT_ORG_ID,
        name="Test Default Organization",
        timezone="UTC",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    session.add(org)
    await session.commit()
    return DEFAULT_ORG_ID


async def _ensure_default_person(session: AsyncSession) -> UUID:
    """Idempotent seed of alice's Person row (auth_subject matches Keycloak alice)."""
    existing = await session.execute(
        select(Person).where(Person.auth_subject == KEYCLOAK_USER_ALICE)
    )
    person = existing.scalar_one_or_none()
    if person is not None:
        return person.id
    person = Person(
        id=DEFAULT_PERSON_ID,
        auth_subject=KEYCLOAK_USER_ALICE,
        first_name="Alice",
        last_name="Admin",
        email=f"alice-{uuid.uuid4().hex[:8]}@groundwork.test",
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    session.add(person)
    await session.commit()
    return DEFAULT_PERSON_ID


async def _ensure_default_role_and_grants(
    session: AsyncSession,
    organization_id: UUID,
) -> UUID:
    """Idempotent seed of the test-admin role + all default permissions + grants."""
    # Role
    role_q = await session.execute(
        select(Role).where(
            Role.organization_id == organization_id,
            Role.slug == DEFAULT_ROLE_SLUG,
        )
    )
    role = role_q.scalar_one_or_none()
    if role is None:
        role = Role(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name="Test Admin",
            slug=DEFAULT_ROLE_SLUG,
            primary_domain=RoleDomain.ADMIN,
            is_system_role=False,
            created_at=datetime.now(tz=UTC),
        )
        session.add(role)
        await session.flush()

    # Permissions + grants
    for slug in _DEFAULT_PERMISSIONS:
        resource_slug, action = slug.rsplit(".", 1)
        perm_q = await session.execute(
            select(Permission).where(
                Permission.slug == slug,
                Permission.organization_id.is_(None),
            )
        )
        perm = perm_q.scalar_one_or_none()
        if perm is None:
            perm = Permission(
                id=uuid.uuid4(),
                organization_id=None,
                resource_slug=resource_slug,
                action=action,
                slug=slug,
                is_system_permission=True,
                created_at=datetime.now(tz=UTC),
            )
            session.add(perm)
            await session.flush()

        grant_q = await session.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == perm.id,
                RolePermission.revoked_at.is_(None),
            )
        )
        if grant_q.scalar_one_or_none() is None:
            grant = RolePermission(
                id=uuid.uuid4(),
                organization_id=organization_id,
                role_id=role.id,
                permission_id=perm.id,
                granted_at=datetime.now(tz=UTC),
            )
            session.add(grant)
    await session.commit()
    return role.id


async def _ensure_default_person_role(
    session: AsyncSession,
    *,
    person_id: UUID,
    organization_id: UUID,
    role_id: UUID,
) -> None:
    """Idempotent seed of alice's PersonRole binding."""
    pr_q = await session.execute(
        select(PersonRole).where(
            PersonRole.person_id == person_id,
            PersonRole.organization_id == organization_id,
            PersonRole.role_id == role_id,
            PersonRole.entity_instance_id.is_(None),
            PersonRole.revoked_at.is_(None),
        )
    )
    if pr_q.scalar_one_or_none() is not None:
        return
    pr = PersonRole(
        id=uuid.uuid4(),
        person_id=person_id,
        organization_id=organization_id,
        role_id=role_id,
    )
    session.add(pr)
    await session.commit()


async def _seed_default_identity(session: AsyncSession) -> UUID:
    """Run all default-identity seeding steps idempotently. Returns the org id."""
    org_id = await _ensure_default_org(session)
    person_id = await _ensure_default_person(session)
    role_id = await _ensure_default_role_and_grants(session, org_id)
    await _ensure_default_person_role(
        session, person_id=person_id, organization_id=org_id, role_id=role_id
    )
    return org_id


async def seed_authenticated_identity(
    session: AsyncSession,
    organization_id: UUID,
) -> tuple[UUID, UUID]:
    """Seed alice + admin role + permissions + grants + PersonRole for ``organization_id``.

    Re-usable from per-file ``http_client`` fixtures that pin a specific
    ``organization_id`` (e.g. ``_HTTP_ORG_ID`` in test_people.py). Returns
    ``(person_id, role_id)``. Idempotent.

    The caller is responsible for ensuring the ``Organization`` row exists
    before calling this — typically by inserting one with the desired UUID.
    """
    person_id = await _ensure_default_person(session)
    role_id = await _ensure_default_role_and_grants(session, organization_id)
    await _ensure_default_person_role(
        session, person_id=person_id, organization_id=organization_id, role_id=role_id
    )
    return person_id, role_id


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient with auto-authentication as alice.

    Seeds alice (Person + Organization + admin Role + Permissions + grants
    + PersonRole) on first call, reuses on subsequent. Every request the
    client makes carries ``Authorization: Bearer <alice-token>`` and
    ``X-Organization-Id: <alice-org-id>`` so legacy endpoint tests don't
    need to authenticate explicitly.
    """
    org_id = await _seed_default_identity(db_session)
    token = await _fetch_keycloak_token("alice")

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(org_id),
        },
    ) as ac:
        yield ac


@pytest_asyncio.fixture(loop_scope="session")
async def auth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx client WITHOUT auto-authentication.

    Pairs with ``test_auth/`` tests that need to control the Authorization
    header themselves — including the negative-path tests that send
    malformed/expired/missing tokens.
    """
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
